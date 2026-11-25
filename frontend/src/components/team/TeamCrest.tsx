import { useMutation } from '@tanstack/react-query'
import { Loader2, Trash2, Undo2, Upload } from 'lucide-react'
import { useRef } from 'react'
import type { FieldValue, TeamDetail } from '@/api/types'
import { Section } from '@/components/common/detail'
import { ColorInput } from '@/components/common/form'
import { Crest, readPicture } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import type { PendingPicture } from './pending'

const COLORS = ['teamcolor1', 'teamcolor2', 'teamcolor3'] as const
const FALLBACK = [0, 0, 0]

/** The team's crest and colors, laid out like the Street Studio's tab: the crest (the user's picture, which the patch
 * draws every size from and puts on generic kits, or the game's; a team made from scratch without one gets a plain
 * shield with its short name, and so does a copied team whose copied crest is removed: field `plain_crest`) and the
 * three team colors. Under the crest: Upload when there is none to replace, else Replace (and Remove when there is
 * something to remove). */
export function TeamCrest({
  team,
  pending,
  setPending,
  fields,
  setField,
}: {
  team: TeamDetail
  pending: PendingPicture
  setPending: (p: PendingPicture) => void
  /** the edited fields (database column -> value) */
  fields: Record<string, FieldValue>
  setField: (name: string, value: FieldValue) => void
}) {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const choose = useMutation({
    mutationFn: async (file: File) => {
      const data = await readPicture(file)
      return { data, url: URL.createObjectURL(file) }
    },
    onSuccess: (p) => setPending(p),
    onError: (e: Error) => toast.error(e.message),
  })
  const hasOwn = pending === 'remove' ? false : !!pending || !!team.own_crest
  const copy = team.is_new && team.copied
  const plainValue = 'plain_crest' in fields ? fields.plain_crest : team.saved.plain_crest
  const plain = copy && plainValue === 1 // the copied crest removed: the plain one
  // a crest the user can replace: the copied team's, or a game team's own
  const shown = hasOwn || (copy && !plain) || (!team.is_new && team.has_crest)
  const upload = (
    <Button variant="outline" size="sm" disabled={choose.isPending} onClick={() => input.current?.click()}>
      <Upload /> {t(shown ? 'common.replace' : 'team.crestUpload')}
    </Button>
  )
  const color = (column: string): number[] => {
    const edited = fields[column]
    const value = Array.isArray(edited) ? edited : team.values[column]
    return Array.isArray(value) && value.every((c) => typeof c === 'number') ? (value as number[]) : FALLBACK
  }
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title={t('team.crest')} description={t('team.crestHint')}>
        <div className="space-y-3">
          <div
            className="flex h-48 cursor-pointer items-center justify-center rounded-lg border border-dashed bg-[repeating-conic-gradient(var(--muted)_0_25%,transparent_0_50%)] bg-[length:16px_16px]"
            onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              const f = e.dataTransfer.files[0]
              if (f) choose.mutate(f)
            }}
          >
            {choose.isPending ? (
              <Loader2 className="animate-spin" />
            ) : pending && pending !== 'remove' ? (
              <img src={pending.url} alt="" className="max-h-40 max-w-full object-contain" />
            ) : team.has_crest || team.is_new || hasOwn ? (
              <Crest id={team.id} size={256} available version={pending === 'remove' ? null : team.own_crest} plain={copy ? plain : undefined} className="max-h-40 max-w-full" />
            ) : (
              <span className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
                <Upload /> {t('image.clickOrDrop')}
              </span>
            )}
          </div>
          <input
            ref={input}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/bmp,image/gif"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) choose.mutate(file)
              e.target.value = ''
            }}
          />
          <p className="text-xs text-muted-foreground">
            {hasOwn ? t('team.crestOwn') : t(team.is_new && (!team.copied || plain) ? 'team.crestPlain' : copy ? 'team.crestCopied' : 'team.crestGame')}
          </p>
          {pending && <p className="text-xs text-amber-600 dark:text-amber-400">{t(pending === 'remove' ? 'team.crestRemovePending' : 'team.crestPending')}</p>}
          <div className="flex justify-end gap-2">
            {upload}
            {hasOwn ? (
              <Button variant="outline" size="sm" onClick={() => setPending(team.own_crest ? 'remove' : null)}>
                <Trash2 /> {t('common.remove')}
              </Button>
            ) : copy && !plain ? (
              <Button variant="outline" size="sm" onClick={() => setField('plain_crest', 1)}>
                <Trash2 /> {t('common.remove')}
              </Button>
            ) : (
              plain && (
                <Button variant="outline" size="sm" onClick={() => setField('plain_crest', null)}>
                  <Undo2 /> {t('team.crestBackToCopied')}
                </Button>
              )
            )}
          </div>
        </div>
      </Section>
      <Section title={t('team.colors')}>
        <div className="space-y-4">
          {COLORS.map((column) => (
            <div key={column} className="space-y-1.5">
              <Label>{t(`field.${column}` as MessageKey)}</Label>
              <ColorInput value={color(column)} onChange={(v) => setField(column, v)} />
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}
