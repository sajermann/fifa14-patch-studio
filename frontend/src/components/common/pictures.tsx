import { Flag, ImageOff, Shield, User } from 'lucide-react'
import { useState } from 'react'
import { useToken } from '@/state/queries'
import { cn } from '@/lib/utils'

/** Picture of the loaded game (the URL carries the game's token); a missing or broken file shows `fallback`. */
function GameImage({ url, alt, className, fallback, available = true }: { url: string; alt: string; className?: string; fallback: React.ReactNode; available?: boolean }) {
  const token = useToken()
  const [failed, setFailed] = useState<string | null>(null)
  const src = `${url}${url.includes('?') ? '&' : '?'}v=${token}`
  if (!available || failed === src) return <span className={cn('inline-flex items-center justify-center text-muted-foreground/50', className)}>{fallback}</span>
  return <img src={src} alt={alt} loading="lazy" className={cn('object-contain', className)} onError={() => setFailed(src)} />
}

export function Crest({ id, size = 64, className, available }: { id: number; size?: number; className?: string; available?: boolean }) {
  return (
    <GameImage
      url={`/api/image/crest/${id}?size=${size}`}
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

export function LeagueImage({ id, size, className, available }: { id: number; size?: number; className?: string; available?: boolean }) {
  return <GameImage url={`/api/image/league/${id}${size ? `?size=${size}` : ''}`} alt="" className={className} available={available} fallback={<ImageOff className="size-1/2" />} />
}

/** A country's flag (`id` = the country whose flag is shown: a created country shows the one it copies). */
export function CountryFlag({ id, size = 64, className, available, version, gameOnly }: { id: number; size?: number; className?: string; available?: boolean; version?: number | null; gameOnly?: boolean }) {
  const url = `/api/image/flag/${id}?size=${size}${version ? `&own=${version}` : ''}${gameOnly ? '&game_only=true' : ''}`
  return <GameImage url={url} alt="" className={className} available={available} fallback={<Flag className="size-1/2" />} />
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
