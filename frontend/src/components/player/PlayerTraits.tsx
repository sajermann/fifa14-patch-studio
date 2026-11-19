import type { FieldValue } from '@/api/types'
import { Section } from '@/components/common/detail'
import { Checkbox } from '@/components/ui/checkbox'
import { useI18n, type MessageKey } from '@/i18n'

// the traits as the game groups them (fifa14.TRAITS keys)
const GOALKEEPER = ['pushes_up_for_corners', 'puncher', 'gk_long_thrower', 'gk_one_on_one', 'gk_flat_kick']
const SKILLS = ['fancy_feet', 'fancy_passes', 'fancy_flicks', 'stutter_penalty', 'chipped_penalty', 'bicycle_kicks', 'diving_header', 'driven_pass']

/** The player's traits (bits of trait1/trait2 in the database; the ones the app does not know stay as they are). */
export function PlayerTraits({ all, value, original, onChange }: { all: string[]; value: FieldValue | undefined; original: FieldValue | undefined; onChange: (v: string[]) => void }) {
  const { t } = useI18n()
  const chosen = (Array.isArray(value) ? value : Array.isArray(original) ? original : []) as string[]
  const groups: [MessageKey, string[]][] = [
    ['traits.general', all.filter((k) => !GOALKEEPER.includes(k) && !SKILLS.includes(k))],
    ['traits.skills', all.filter((k) => SKILLS.includes(k))],
    ['traits.goalkeeper', all.filter((k) => GOALKEEPER.includes(k))],
  ]
  const toggle = (key: string, on: boolean) => onChange(all.filter((k) => (k === key ? on : chosen.includes(k))))
  return (
    <Section title={t('traits.title')} description={`${t('traits.hint')} ${t('traits.count', { count: chosen.length })}`}>
      <div className="grid gap-6 lg:grid-cols-3">
        {groups.map(([label, keys]) => (
          <div key={label} className="space-y-2">
            <h3 className="border-b pb-1 text-sm font-semibold text-muted-foreground">{t(label)}</h3>
            {keys.map((key) => {
              const was = Array.isArray(original) && (original as string[]).includes(key)
              const on = chosen.includes(key)
              return (
                <label key={key} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox checked={on} onCheckedChange={(v) => toggle(key, v === true)} />
                  <span className={on !== was ? 'font-medium text-primary' : undefined}>{t(`trait.${key}` as MessageKey)}</span>
                </label>
              )
            })}
          </div>
        ))}
      </div>
    </Section>
  )
}
