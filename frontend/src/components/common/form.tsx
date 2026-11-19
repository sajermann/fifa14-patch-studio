import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

/** "n/total" of a value in its list (the same as the Street Studio's); a value not set shows the inherited one (the
 * game's) with "default". */
export function OptionCount({ value, options, inherited, label }: {
  value: number | undefined
  options: number[]
  inherited?: number | null
  label?: (option: number) => string
}) {
  const { t } = useI18n()
  const idx = value === undefined ? -1 : options.indexOf(value)
  const inheritedIdx = inherited === undefined || inherited === null ? -1 : options.indexOf(inherited)
  if (label) {
    if (idx >= 0) return <span>{label(options[idx])}</span>
    if (inheritedIdx >= 0) return <span className="text-muted-foreground">{label(options[inheritedIdx])} <span className="text-xs">{t('common.default')}</span></span>
    return <span className="text-muted-foreground">{t('common.default')}</span>
  }
  if (value !== undefined) {
    return (
      <span className="tabular-nums">
        {idx + 1}
        <span className="text-xs text-muted-foreground">/{options.length}</span>
      </span>
    )
  }
  if (inheritedIdx >= 0) {
    return (
      <span className="text-muted-foreground tabular-nums">
        {inheritedIdx + 1}
        <span className="text-xs">
          /{options.length} {t('common.default')}
        </span>
      </span>
    )
  }
  return <span className="text-muted-foreground">{t('common.default')}</span>
}

/** A value of a list chosen with the arrows (the same as the Street Studio's). */
export function Stepper({
  value,
  options,
  onChange,
  inherited,
  label,
  wide,
}: {
  value: number | undefined
  options: number[]
  onChange: (v: number | undefined) => void
  inherited?: number | null
  label?: (option: number) => string
  wide?: boolean // the middle takes the free width (long labels)
}) {
  const { t } = useI18n()
  const idx = value === undefined ? -1 : options.indexOf(value)
  const inheritedIdx = inherited === undefined || inherited === null ? -1 : options.indexOf(inherited)
  const go = (delta: number) => {
    if (!options.length) return
    const from = idx >= 0 ? idx : inheritedIdx // on a default value, the next one after it
    const next = from < 0 ? (delta > 0 ? 0 : options.length - 1) : (from + delta + options.length) % options.length
    onChange(options[next])
  }
  return (
    <div className="flex items-center gap-1">
      <Button type="button" variant="outline" size="icon" onClick={() => go(-1)} aria-label={t('form.previous')}>
        <ChevronLeft />
      </Button>
      <div className={cn('min-w-0 shrink rounded-md border px-2 py-1.5 text-center text-sm whitespace-nowrap', wide ? 'flex-1 truncate' : 'w-28')}>
        <OptionCount value={value} options={options} inherited={inherited} label={label} />
      </div>
      <Button type="button" variant="outline" size="icon" onClick={() => go(1)} aria-label={t('form.next')}>
        <ChevronRight />
      </Button>
    </div>
  )
}
