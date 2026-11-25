import { FolderOpen, Loader2, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { api } from '@/api/client'
import type { StadiumDetail } from '@/api/types'
import { readPicture, StadiumImage } from '@/components/common/pictures'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { toast } from '@/lib/notify'

/** A created stadium's 3D folder chosen and not saved yet (null = none). */
export type PendingScene = string | null
/** A menu picture chosen and not saved yet: the file (base64 + a local URL to show it), or 'remove' (back to the
 * stadium's own). */
export type PendingPicture = { data: string; url: string } | 'remove'
/** The pending menu pictures, by variant. */
export type PendingPictures = Record<number, PendingPicture>

const MB = 1024 * 1024

/** One menu picture of the stadium, editable like the team's crest: a click or a dropped file replaces it, Remove
 * brings back the stadium's own (the game's, the folder's or the copied stadium's). Saved with the screen's Save. */
export function StadiumPictureEdit({
  stadium: s,
  variant,
  pending,
  setPending,
}: {
  stadium: StadiumDetail
  variant: number
  pending: PendingPicture | undefined
  setPending: (p: PendingPicture | undefined) => void
}) {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const [reading, setReading] = useState(false)
  const saved = s.own_pictures.includes(variant)
  const hasOwn = pending === 'remove' ? false : !!pending || saved
  const choose = async (file: File) => {
    setReading(true)
    try {
      setPending({ data: await readPicture(file), url: URL.createObjectURL(file) })
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setReading(false)
    }
  }
  const imageClass = 'aspect-[23/10] w-full rounded border bg-muted/40 object-cover'
  return (
    <figure className="space-y-1">
      <div
        className="cursor-pointer"
        title={t('stadium.pictureClick')}
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const f = e.dataTransfer.files[0]
          if (f) void choose(f)
        }}
      >
        {reading ? (
          <span className={`${imageClass} flex items-center justify-center`}>
            <Loader2 className="animate-spin" />
          </span>
        ) : pending && pending !== 'remove' ? (
          <img src={pending.url} alt="" className={imageClass} />
        ) : (
          // 'remove' pending: the stadium's own picture is only known after Save, so the saved one stays shown
          <StadiumImage id={s.id} variant={variant} size={512} version={s.updated_at} className={imageClass} />
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/bmp,image/gif"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (file) void choose(file)
        }}
      />
      <figcaption className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {t('stadium.picture', { variant })}
          {hasOwn && ` · ${t('stadium.pictureOwn')}`}
        </span>
        <span className="flex gap-1">
          <Button variant="outline" size="sm" disabled={reading} onClick={() => input.current?.click()}>
            <Upload /> {t('common.replace')}
          </Button>
          {hasOwn && (
            <Button variant="outline" size="sm" onClick={() => setPending(saved ? 'remove' : undefined)}>
              <Trash2 /> {t('common.remove')}
            </Button>
          )}
        </span>
      </figcaption>
      {pending && <p className="text-xs text-amber-600 dark:text-amber-400">{t(pending === 'remove' ? 'stadium.pictureRemovePending' : 'stadium.picturePending')}</p>}
    </figure>
  )
}

/** A created stadium's 3D: where it comes from (the chosen folder, or the stadium it starts from), as a line. */
export function StadiumSceneNotice({ stadium: s, scene }: { stadium: StadiumDetail; scene: PendingScene }) {
  const { t } = useI18n()
  const size = s.files.reduce((sum, f) => sum + (f.size ?? 0), 0)
  return (
    <div className="mb-3 space-y-1 text-xs">
      <p className="text-muted-foreground">
        {scene
          ? t('stadium.scenePendingFolder', { folder: scene })
          : s.own_scene
            ? t('stadium.sceneOwn', { count: s.files.length, size: (size / MB).toFixed(0) })
            : t('stadium.sceneTemplate', { name: s.template_name ?? `#${s.template}` })}
      </p>
      {scene && <p className="text-amber-600 dark:text-amber-400">{t('stadium.scenePending')}</p>}
    </div>
  )
}

/** "Change the 3D folder…": a downloaded stadium's folder (saved with the screen's Save). */
export function StadiumFolderButton({ scene, setScene }: { scene: PendingScene; setScene: (v: PendingScene) => void }) {
  const { t } = useI18n()
  const [browsing, setBrowsing] = useState(false)
  const browse = async () => {
    setBrowsing(true)
    try {
      const { path } = await api.pickFolder(scene, t('stadium.newFolderTitle'))
      if (path) setScene(path)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBrowsing(false)
    }
  }
  return (
    <Button variant="outline" size="sm" disabled={browsing} onClick={browse}>
      {browsing ? <Loader2 className="animate-spin" /> : <FolderOpen />} {t('stadium.sceneFolder')}
    </Button>
  )
}
