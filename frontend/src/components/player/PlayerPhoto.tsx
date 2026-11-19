import { useMutation } from '@tanstack/react-query'
import { ImageOff, Loader2, Upload } from 'lucide-react'
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

/** The player's photo (heads/p<id>.dds, 128×128 in the game): the user's picture or the game's. */
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
  const shown = pending && pending !== 'remove' ? pending.url : pending === 'remove' ? `/api/image/photo/${player.id}?size=256&game_only=true&v=${token}` : `/api/image/photo/${player.id}?size=256&own=${player.own_photo ?? 0}&v=${token}`
  const available = pending === 'remove' ? player.has_photo && !player.own_photo : player.has_photo || hasOwn
  return (
    <Section title={t('photo.title')} description={t('photo.description')}>
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex size-32 shrink-0 items-center justify-center rounded-md bg-muted/40 p-2">
          {available || (pending && pending !== 'remove') ? <img src={shown} alt="" className="size-28 object-contain" /> : <span className="text-xs text-muted-foreground">{t('photo.none')}</span>}
        </div>
        <div className="min-w-0 flex-1 basis-48 space-y-2">
          {pending && <p className="text-xs text-amber-600 dark:text-amber-400">{t(pending !== 'remove' && 'pack' in pending ? 'photo.fromPackPending' : 'photo.pending')}</p>}
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
              {choose.isPending ? <Loader2 className="animate-spin" /> : <Upload />} {t('photo.upload')}
            </Button>
            {hasOwn && (
              <Button variant="ghost" size="sm" onClick={() => setPending(player.own_photo ? 'remove' : null)}>
                <ImageOff /> {t('photo.remove')}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Section>
  )
}
