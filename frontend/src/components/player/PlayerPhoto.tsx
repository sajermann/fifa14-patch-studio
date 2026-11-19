import { useMutation } from '@tanstack/react-query'
import { Loader2, Trash2, Upload } from 'lucide-react'
import { useRef } from 'react'
import type { PlayerDetail } from '@/api/types'
import { Section } from '@/components/common/detail'
import { readPicture } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { toast } from '@/lib/notify'
import { useToken } from '@/state/queries'

/** A photo chosen on the screen and not saved yet: a picture (base64 + a local URL), the photo a pack ships with a
 * face, or the user's photo removed. */
export type PendingPhoto = { data: string; url: string } | { pack: string; face: number; url: string } | 'remove' | null

/** The player's photo (heads/p<id>.dds, 128×128 in the game): the user's picture or the game's. Laid out like the
 * Street Studio's photo card: a checkered drop area (click or drop a picture) with replace and remove below it. */
export function PlayerPhoto({ player, pending, setPending }: { player: PlayerDetail; pending: PendingPhoto; setPending: (p: PendingPhoto) => void }) {
  const { t } = useI18n()
  const token = useToken()
  const input = useRef<HTMLInputElement>(null)
  const choose = useMutation({
    mutationFn: async (file: File) => ({ data: await readPicture(file), url: URL.createObjectURL(file) }),
    onSuccess: (p) => setPending(p),
    onError: (e: Error) => toast.error(e.message),
  })
  const hasOwn = pending === 'remove' ? false : !!pending || !!player.own_photo
  const shown =
    pending && pending !== 'remove'
      ? pending.url
      : pending === 'remove'
        ? `/api/image/photo/${player.id}?size=256&game_only=true&v=${token}`
        : `/api/image/photo/${player.id}?size=256&own=${player.own_photo ?? 0}&v=${token}`
  const available = pending === 'remove' ? player.has_photo && !player.own_photo : player.has_photo || hasOwn
  return (
    <Section title={t('photo.title')} description={t('photo.description')}>
      <div className="space-y-3">
        <div
          className="mx-auto flex size-40 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-dashed bg-[repeating-conic-gradient(var(--muted)_0_25%,transparent_0_50%)] bg-[length:16px_16px]"
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            const f = e.dataTransfer.files[0]
            if (f) choose.mutate(f)
          }}
          title={t('image.clickOrDrop')}
        >
          {choose.isPending ? (
            <Loader2 className="animate-spin" />
          ) : available || (pending && pending !== 'remove') ? (
            <img src={shown} alt={t('photo.title')} className="size-full object-contain" />
          ) : (
            <span className="flex flex-col items-center gap-2 p-2 text-center text-xs text-muted-foreground">
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
        {pending && <p className="text-center text-xs text-amber-600 dark:text-amber-400">{t(pending !== 'remove' && 'pack' in pending ? 'photo.fromPackPending' : 'photo.pending')}</p>}
        {hasOwn && (
          <div className="flex justify-center gap-2">
            <Button variant="outline" size="sm" disabled={choose.isPending} onClick={() => input.current?.click()}>
              <Upload /> {t('common.replace')}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPending(player.own_photo ? 'remove' : null)}>
              <Trash2 /> {t('common.remove')}
            </Button>
          </div>
        )}
      </div>
    </Section>
  )
}
