import { ArrowLeft } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { Raw } from '@/api/types'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

/** "←": back to where the user came from (the list keeps its filters in the URL), or to `fallback`. */
export function BackButton({ fallback }: { fallback: string }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()
  return (
    <Button variant="ghost" size="sm" onClick={() => (location.key !== 'default' ? navigate(-1) : navigate(fallback))}>
      <ArrowLeft /> {t('common.back')}
    </Button>
  )
}

export function Section({ title, children, action, className }: { title: ReactNode; children: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle className="text-base">{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

/** Label/value pairs in a grid. */
export function Facts({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd className="min-w-0 break-words">{v ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Every column of the item's database row, with a filter. */
export function RawTable({ raw }: { raw: Raw }) {
  const { t } = useI18n()
  const [q, setQ] = useState('')
  const rows = useMemo(() => Object.entries(raw).filter(([k]) => k.toLowerCase().includes(q.trim().toLowerCase())).sort(([a], [b]) => a.localeCompare(b)), [raw, q])
  return (
    <div className="space-y-3">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('raw.filter')} className="max-w-xs" />
      <div className="grid grid-cols-1 gap-x-8 gap-y-1 font-mono text-xs sm:grid-cols-2 xl:grid-cols-3">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 border-b border-dashed py-1">
            <span className="text-muted-foreground">{k}</span>
            <span className="truncate text-right">{v === null ? '∅' : String(v)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Badge({ children, tone = 'muted', className }: { children: ReactNode; tone?: 'muted' | 'warn' | 'ok'; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium',
        tone === 'muted' && 'bg-muted text-muted-foreground',
        tone === 'warn' && 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
        tone === 'ok' && 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300',
        className,
      )}
    >
      {children}
    </span>
  )
}

/** Rating bar 0–99 colored by value. */
export function Rating({ label, value }: { label: string; value: number | null | undefined }) {
  const v = typeof value === 'number' ? value : null
  const color = v === null ? 'bg-muted' : v >= 80 ? 'bg-emerald-500' : v >= 70 ? 'bg-lime-500' : v >= 60 ? 'bg-amber-500' : v >= 50 ? 'bg-orange-500' : 'bg-red-500'
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 text-sm">
      <span className="truncate text-muted-foreground">{label}</span>
      <span className="w-7 text-right font-medium tabular-nums">{v ?? '—'}</span>
      <div className="col-span-2 h-1.5 overflow-hidden rounded bg-muted">
        <div className={cn('h-full rounded', color)} style={{ width: `${Math.min(100, v ?? 0)}%` }} />
      </div>
    </div>
  )
}

export function OverallBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">—</span>
  const tone = value >= 80 ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : value >= 70 ? 'bg-lime-500/15 text-lime-700 dark:text-lime-300' : value >= 60 ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300' : 'bg-muted text-muted-foreground'
  return <span className={cn('inline-block w-9 rounded py-0.5 text-center text-xs font-semibold tabular-nums', tone)}>{value}</span>
}
