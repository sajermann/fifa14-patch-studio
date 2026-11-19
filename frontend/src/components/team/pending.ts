import type { KitConfig, KitPart } from '@/api/types'

/** A picture chosen (base64 + a local URL to show it) or removed, not saved yet: Save sends it with the rest. */
export type PendingPicture = { data: string; url: string } | 'remove' | null

/** A kit changed on the page, not saved yet: its new source (null = the default again) and its pictures. */
export interface PendingKit {
  config: KitConfig | null
  pictures: Partial<Record<KitPart, PendingPicture>>
}

export const KIT_KINDS = [0, 1, 2, 3] as const
/** More outfield kits the kit selection lists as "Alternate" (the goalkeeper always wears type 2; tests GK1/GK2).
 * Type 6 is left out: the game shows it as "undefined". */
export const EXTRA_KITS = [4, 5, 7, 8]
export const BENCH = 28
export const RESERVE = 29

export const hex = (rgb: number[]) => rgb.map((v) => v.toString(16).padStart(2, '0')).join('')
export const fromHex = (value: string) => [1, 3, 5].map((i) => parseInt(value.slice(i, i + 2), 16))
