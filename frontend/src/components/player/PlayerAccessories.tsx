import { Eraser } from 'lucide-react'
import type { AccessoryOptions, PlayerDetail } from '@/api/types'
import { Section } from '@/components/common/detail'
import { Stepper } from '@/components/common/form'
import { Button } from '@/components/ui/button'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'

/** The game keeps a player's accessories in 4 slots (accessorycode1-4 + accessorycolourcode1-4, any order); the
 * screen shows them by place of the body, like the game's own Accessories screen (plus the ones it does not list). */
type Slot = { code: number; colour: number }

const SLOT_FIELDS = [1, 2, 3, 4].flatMap((n) => [`accessorycode${n}`, `accessorycolourcode${n}`])
// the game's screen first (ankle, gloves, wrists), then what it only draws on the pitch
const PLACE_ORDER = ['ankle_left', 'ankle_right', 'hands', 'wrist_left', 'wrist_right', 'knee_left', 'knee_right', 'fingers_left', 'fingers_right', 'hand_left', 'hand_right', 'ear']

const num = (v: unknown) => (typeof v === 'number' ? v : 0)

export function PlayerAccessories({ player, fields, setField, options }: { player: PlayerDetail; fields: Record<string, unknown>; setField: (n: string, v: number | null) => void; options: AccessoryOptions | undefined }) {
  const { t } = useI18n()
  if (!options) return null
  const original: Slot[] = [1, 2, 3, 4].map((n) => ({ code: num(player.values[`accessorycode${n}`]), colour: num(player.values[`accessorycolourcode${n}`]) }))
  const edited = SLOT_FIELDS.some((f) => typeof fields[f] === 'number')
  const slots: Slot[] = original.map((s, i) => ({
    code: typeof fields[`accessorycode${i + 1}`] === 'number' ? (fields[`accessorycode${i + 1}`] as number) : s.code,
    colour: typeof fields[`accessorycolourcode${i + 1}`] === 'number' ? (fields[`accessorycolourcode${i + 1}`] as number) : s.colour,
  }))
  const placeOf = (code: number) => Object.keys(options.places).find((p) => options.places[p].includes(code))
  const known = new Set(Object.values(options.places).flat())
  const others = slots.filter((s) => s.code && !known.has(s.code)).length
  const used = slots.filter((s) => s.code).length

  const write = (next: Slot[]) => {
    const same = next.every((s, i) => s.code === original[i].code && s.colour === original[i].colour)
    next.forEach((s, i) => {
      setField(`accessorycode${i + 1}`, same ? null : s.code)
      setField(`accessorycolourcode${i + 1}`, same ? null : s.colour)
    })
  }
  /** Puts `code` (0 = nothing) in the place: replaces what the place has, else takes a free slot. */
  const setPlace = (place: string, code: number, colour: number) => {
    const next = slots.map((s) => ({ ...s }))
    const mine = next.map((s, i) => (placeOf(s.code) === place ? i : -1)).filter((i) => i >= 0)
    mine.slice(1).forEach((i) => (next[i] = { code: 0, colour: 0 })) // one thing per place
    let at = mine[0] ?? -1
    if (at < 0) {
      if (!code) return
      at = next.findIndex((s) => !s.code)
      if (at < 0) return void toast.error(t('accessories.full', { count: options.slots }))
    }
    next[at] = code ? { code, colour } : { code: 0, colour: 0 }
    write(next)
  }

  const codeLabel = (place: string) => (code: number) => {
    if (!code) return t(options.places[place].length === 1 ? 'accessories.no' : 'accessories.nothing')
    if (options.places[place].length === 1) return t('accessories.yes')
    const k = `accessories.code.${code}`
    return hasMessage(k) ? t(k as MessageKey) : String(code)
  }
  const colourLabel = (code: number) => (colour: number) =>
    options.model.includes(code) ? t('accessories.model', { value: colour }) : t(`accessories.colour.${colour}` as MessageKey)

  return (
    <Section
      title={t('fieldGroup.accessories')}
      description={t('accessories.hint', { count: options.slots })}
      action={
        edited && (
          <Button variant="ghost" size="sm" onClick={() => SLOT_FIELDS.forEach((f) => setField(f, null))}>
            <Eraser /> {t('playerEdit.resetDefault')}
          </Button>
        )
      }
    >
      <p className="mb-4 text-sm text-muted-foreground">
        {t('accessories.used', { used, count: options.slots })}
        {others > 0 && ` ${t('accessories.others', { count: others })}`}
      </p>
      <div className="grid gap-x-8 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
        {PLACE_ORDER.filter((p) => options.places[p]).map((place) => {
          const slot = slots.find((s) => placeOf(s.code) === place)
          const code = slot?.code ?? 0
          const colour = slot?.colour ?? 0
          const firstOriginal = original.find((s) => placeOf(s.code) === place)
          // "default" per place: only the places changed lose it
          const codeChanged = code !== (firstOriginal?.code ?? 0)
          const colourChanged = codeChanged || colour !== (firstOriginal?.colour ?? 0)
          const codes = [0, ...options.places[place]]
          const colours = options.model.includes(code) ? [...Array(16).keys()] : options.colours
          const colourFixed = !code || options.textured.includes(code)
          return (
            <div key={place} className="grid gap-1.5">
              <p className="text-sm font-medium">{t(`accessories.place.${place}` as MessageKey)}</p>
              <Stepper
                value={codeChanged ? code : undefined}
                inherited={firstOriginal?.code ?? 0}
                options={codes}
                onChange={(v) => setPlace(place, v ?? 0, options.textured.includes(v ?? 0) ? 0 : colour)}
                label={codeLabel(place)}
                wide
              />
              {colourFixed ? (
                <div className="flex h-9 items-center px-11 text-sm text-muted-foreground">{code ? t('accessories.ownPicture') : '—'}</div>
              ) : (
                <Stepper
                  value={colourChanged ? colour : undefined}
                  inherited={firstOriginal?.colour ?? 0}
                  options={colours}
                  onChange={(v) => setPlace(place, code, v ?? 0)}
                  label={colourLabel(code)}
                  wide
                />
              )}
            </div>
          )
        })}
      </div>
    </Section>
  )
}
