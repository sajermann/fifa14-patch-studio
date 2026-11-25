import { Flag, ImageOff, Shield, User } from 'lucide-react'
import { useState } from 'react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { useToken } from '@/state/queries'
import { cn } from '@/lib/utils'

/** The URL of the same picture at its full size (no `size`), for the zoom. */
function fullSize(url: string) {
  const [path, query = ''] = url.split('?')
  const q = new URLSearchParams(query)
  q.delete('size')
  const rest = q.toString()
  return rest ? `${path}?${rest}` : path
}

/** Picture of the loaded game (the URL carries the game's token); a missing or broken file shows `fallback`. With
 * `zoom`, a click opens it big in a dialog (the extractor's zoom; off by default here: many pictures sit in buttons). */
function GameImage({ url, alt, className, fallback, available = true, zoom = false }: { url: string; alt: string; className?: string; fallback: React.ReactNode; available?: boolean; zoom?: boolean }) {
  const token = useToken()
  const [failed, setFailed] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const src = `${url}${url.includes('?') ? '&' : '?'}v=${token}`
  if (!available || failed === src) return <span className={cn('inline-flex items-center justify-center text-muted-foreground/50', className)}>{fallback}</span>
  const big = `${fullSize(url)}${fullSize(url).includes('?') ? '&' : '?'}v=${token}`
  return (
    <>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        className={cn('object-contain', zoom && 'cursor-zoom-in', className)}
        onError={() => setFailed(src)}
        onClick={
          zoom
            ? (e) => {
                e.stopPropagation() // a picture inside a clickable row opens itself, not the row
                setOpen(true)
              }
            : undefined
        }
      />
      {zoom && (
        // React events of the dialog (a portal) still bubble up the component tree: a row around the picture must
        // not get the clicks of the dialog or of its backdrop
        <span className="contents" onClick={(e) => e.stopPropagation()}>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent width="picture">
              <DialogTitle className="sr-only">{alt || 'picture'}</DialogTitle>
              <div className="flex max-h-[80vh] items-center justify-center overflow-auto rounded bg-[repeating-conic-gradient(#8881_0_25%,transparent_0_50%)] bg-[length:16px_16px]">
                {open && <img src={big} alt={alt} className="h-[70vh] w-full object-contain" />}
              </div>
            </DialogContent>
          </Dialog>
        </span>
      )}
    </>
  )
}

/** A team's crest (`version` = when the user's picture was saved, so a new one is fetched). */
/** A team's crest (`plain` = a copied team's choice not saved yet: true = the plain crest, false = the copied one). */
export function Crest({ id, size = 64, className, available, version, plain }: { id: number; size?: number; className?: string; available?: boolean; version?: number | null; plain?: boolean }) {
  return (
    <GameImage
      url={`/api/image/crest/${id}?size=${size}${version ? `&own=${version}` : ''}${plain === undefined ? '' : `&plain=${plain}`}`}
      alt=""
      className={className}
      available={available}
      fallback={<Shield className="size-1/2" />}
    />
  )
}

export function Photo({ id, size = 64, className, available }: { id: number; size?: number; className?: string; available?: boolean }) {
  return <GameImage url={`/api/image/photo/${id}?size=${size}`} alt="" className={className} available={available} fallback={<User className="size-1/2" />} />
}

/** A league's logo (`version` = when the user's picture was saved, so a new one is fetched; `gameOnly` = the game's
 * logo even when the user has a picture). */
export function LeagueImage({ id, size, className, available, version, gameOnly }: { id: number; size?: number; className?: string; available?: boolean; version?: number | null; gameOnly?: boolean }) {
  const params = [size ? `size=${size}` : '', version ? `own=${version}` : '', gameOnly ? 'game_only=true' : ''].filter(Boolean).join('&')
  return <GameImage url={`/api/image/league/${id}${params ? `?${params}` : ''}`} alt="" className={className} available={available} fallback={<ImageOff className="size-1/2" />} />
}

/** A country's flag (`id` = the country whose flag is shown: a created country shows the one it copies). */
export function CountryFlag({ id, size = 64, className, available, version, gameOnly }: { id: number; size?: number; className?: string; available?: boolean; version?: number | null; gameOnly?: boolean }) {
  const url = `/api/image/flag/${id}?size=${size}${version ? `&own=${version}` : ''}${gameOnly ? '&game_only=true' : ''}`
  return <GameImage url={url} alt="" className={className} available={available} fallback={<Flag className="size-1/2" />} />
}

/** A menu picture of a stadium (`variant` = which of the game's pictures). */
/** `version` = changes when the picture does (a created stadium's picture comes from the project). */
export function StadiumImage({ id, variant, size, className, zoom, version }: { id: number; variant: number; size?: number; className?: string; zoom?: boolean; version?: string | null }) {
  const query = [size ? `size=${size}` : '', version ? `v=${encodeURIComponent(version)}` : ''].filter(Boolean).join('&')
  return <GameImage url={`/api/image/stadium/${id}/${variant}${query ? `?${query}` : ''}`} alt="" className={className} zoom={zoom} fallback={<ImageOff className="size-1/3" />} />
}

/** Reads a picture file the user chose as base64 (without the data: prefix). */
export function readPicture(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] ?? '')
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

export function ColorDot({ rgb, className }: { rgb: (number | null)[] | null | undefined; className?: string }) {
  if (!rgb || rgb.some((v) => v === null)) return null
  return <span className={cn('inline-block size-4 rounded-full border', className)} style={{ background: `rgb(${rgb.join(',')})` }} title={`RGB ${rgb.join(', ')}`} />
}
