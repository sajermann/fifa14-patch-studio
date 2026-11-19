import { useMutation } from '@tanstack/react-query'
import { ImageOff, Loader2, Upload } from 'lucide-react'
import { useRef } from 'react'
import type { TeamDetail } from '@/api/types'
import { Section } from '@/components/common/detail'
import { Crest, readPicture } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { toast } from '@/lib/notify'
import type { PendingPicture } from './pending'

/** The team's crest: the user's picture (the patch draws every crest size from it, and puts it on generic kits) or
 * the game's (a team made from scratch without one gets a plain shield with its short name). */
export function TeamCrest({ team, pending, setPending }: { team: TeamDetail; pending: PendingPicture; setPending: (p: PendingPicture) => void }) {
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
  return (
    <Section title={t('team.crest')} description={t('team.crestHint')}>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex size-36 shrink-0 items-center justify-center rounded-md bg-muted/40 p-3">
          {pending && pending !== 'remove' ? (
            <img src={pending.url} alt="" className="size-28 object-contain" />
          ) : (
            <Crest id={team.id} size={256} available={team.has_crest || team.is_new || hasOwn} version={pending === 'remove' ? null : team.own_crest} className="size-28" />
          )}
        </div>
        <div className="min-w-0 flex-1 basis-64 space-y-2">
          <p className="text-xs text-muted-foreground">{hasOwn ? t('team.crestOwn') : t(team.is_new && !team.copied ? 'team.crestPlain' : 'team.crestGame')}</p>
          {pending && <p className="text-xs text-amber-600 dark:text-amber-400">{t(pending === 'remove' ? 'team.crestRemovePending' : 'team.crestPending')}</p>}
          <div className="flex flex-wrap gap-2">
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
            <Button variant="outline" size="sm" disabled={choose.isPending} onClick={() => input.current?.click()}>
              {choose.isPending ? <Loader2 className="animate-spin" /> : <Upload />} {t('team.crestUpload')}
            </Button>
            {hasOwn && (
              <Button variant="ghost" size="sm" onClick={() => setPending(team.own_crest ? 'remove' : null)}>
                <ImageOff /> {t('team.crestRemove')}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Section>
  )
}
