import type { ReactNode } from 'react'
import { AlertTriangle, ChevronLeft, ChevronRight, CircleAlert } from 'lucide-react'
import type { ProjectIssue } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useI18n } from '@/i18n'
import { issueText } from '@/lib/issues'
import { cn } from '@/lib/utils'
import { useIssues } from '@/state/queries'

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

export type RGB = [number, number, number]
export const toHex = (rgb: number[]) => '#' + rgb.map((v) => v.toString(16).padStart(2, '0')).join('')
export const fromHex = (hex: string): RGB => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as RGB

/** A color: the picker square and, beside it, the hex code to type (same as the Street Studio's). */
export function ColorInput({ value, onChange }: { value: number[]; onChange: (v: RGB) => void }) {
  const { t } = useI18n()
  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        value={toHex(value)}
        onChange={(e) => onChange(fromHex(e.target.value))}
        className="h-9 w-12 cursor-pointer rounded-md border bg-transparent p-1"
        aria-label={t('form.pickColor')}
      />
      <Input
        value={toHex(value).toUpperCase()}
        onChange={(e) => /^#[0-9a-fA-F]{6}$/.test(e.target.value) && onChange(fromHex(e.target.value))}
        className="w-28 font-mono"
      />
    </div>
  )
}

/** Validation messages of one entity field. */
export function FieldIssues({ issues }: { issues: ProjectIssue[] }) {
  const { t } = useI18n()
  if (!issues.length) return null
  return (
    <ul className="mt-1 space-y-0.5">
      {issues.map((i, k) => (
        <li
          key={k}
          className={cn(
            'flex items-start gap-1 text-xs',
            i.severity === 'error' ? 'text-destructive' : 'text-amber-600 dark:text-amber-500',
          )}
        >
          {i.severity === 'error' ? <CircleAlert className="mt-0.5 size-3 shrink-0" /> : <AlertTriangle className="mt-0.5 size-3 shrink-0" />}
          {issueText(t, i)}
        </li>
      ))}
    </ul>
  )
}

/** Error/warning counts of a league/team/player, with the messages in a tooltip (lists and edit screens). */
export function EntityIssues({ kind, id }: { kind: 'league' | 'team' | 'player' | 'stadium' | 'adboard'; id: number }) {
  const issues = useIssues(kind, id)
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  if (!issues.length) return null
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex cursor-help gap-2 text-xs">
          {errors > 0 && (
            <span className="inline-flex items-center gap-1 text-destructive">
              <CircleAlert className="size-3" /> {errors}
            </span>
          )}
          {warnings > 0 && (
            <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-500">
              <AlertTriangle className="size-3" /> {warnings}
            </span>
          )}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm">
        <IssueList issues={issues} />
      </TooltipContent>
    </Tooltip>
  )
}

function IssueList({ issues }: { issues: ProjectIssue[] }) {
  const { t } = useI18n()
  const sorted = [...issues].sort((a, b) => (a.severity === 'error' ? 0 : 1) - (b.severity === 'error' ? 0 : 1))
  return (
    <ul className="space-y-1">
      {sorted.map((i, k) => (
        <li key={k} className="flex items-start gap-1.5">
          {i.severity === 'error' ? (
            <CircleAlert className="mt-0.5 size-3 shrink-0 text-red-400 dark:text-red-600" />
          ) : (
            <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-400 dark:text-amber-600" />
          )}
          <span>{issueText(t, i)}</span>
        </li>
      ))}
    </ul>
  )
}

/** Label + control + hint (the Street Studio's Field, without its per-field issues). */
export function Field({ label, hint, className, children }: { label: ReactNode; hint?: string; className?: string; children: ReactNode }) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** A number field; empty = undefined (the Street Studio's NumberInput). */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  placeholder,
  className,
}: {
  value: number | undefined
  onChange: (v: number | undefined) => void
  min?: number
  max?: number
  placeholder?: string
  className?: string
}) {
  return (
    <Input
      type="number"
      value={value ?? ''}
      min={min}
      max={max}
      placeholder={placeholder}
      className={className}
      onChange={(e) => onChange(e.target.value === '' ? undefined : Number(e.target.value))}
    />
  )
}
