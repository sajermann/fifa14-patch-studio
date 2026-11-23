import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Badge as UiBadge } from '@/components/ui/badge'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import type { Raw } from '@/api/types'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

/** Max height for a scroll box so that, with the page scrolled to the top, it ends at the bottom of the visible area
 * (the scrolling <main>): the box scrolls instead of the page. Follows window resizes and the content above it. */
export function useFillHeight<E extends HTMLElement>(min = 120, reserve = 0) {
  const ref = useRef<E>(null)
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    const el = ref.current
    const scroller = el?.closest('main')
    if (!el || !scroller) return
    const card = el.closest('[data-slot=card]') ?? el
    const measure = () => {
      const box = el.getBoundingClientRect()
      const top = box.top - scroller.getBoundingClientRect().top + scroller.scrollTop
      const below = card.getBoundingClientRect().bottom - box.bottom // the card's padding under the box
      const padding = parseFloat(getComputedStyle(scroller).paddingBottom) || 0
      setHeight(Math.max(min, Math.floor(scroller.clientHeight - top - below - padding - reserve)))
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(scroller)
    if (scroller.firstElementChild) observer.observe(scroller.firstElementChild)
    return () => observer.disconnect()
  }, [min, reserve])
  return { ref, style: height ? { maxHeight: height } : undefined }
}

/** A box that scrolls on its own and is as tall as what is left of the screen, so the page itself does not scroll.
 * A table inside keeps its header sticky (the table's own container stops being a scroll box). `reserve`: height left
 * free under the box for something that must stay in view (the box is then at least 240 tall). */
export function FillScroll({ children, className, reserve }: { children: ReactNode; className?: string; reserve?: number }) {
  const fill = useFillHeight<HTMLDivElement>(reserve ? 240 : 120, reserve)
  return (
    <div ref={fill.ref} style={fill.style} className={cn('overflow-auto [&>[data-slot=table-container]]:overflow-visible', className)}>
      {children}
    </div>
  )
}

/** A card: title, optional description and action (top right), then the content. */
/** A card with a title. `scroll`: the card takes the height it is given and its content scrolls inside it (as in the
 * extractor). */
export function Section({ title, description, children, action, className, scroll }: { title: ReactNode; description?: ReactNode; children: ReactNode; action?: ReactNode; className?: string; scroll?: boolean }) {
  return (
    <Card className={cn(scroll && 'flex min-h-0 flex-col', className)}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
        {action && <CardAction>{action}</CardAction>}
      </CardHeader>
      <CardContent className={scroll ? 'min-h-0 flex-1 overflow-auto' : undefined}>{children}</CardContent>
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

/** "original" for a game item the project does not change; "updated" when the project saved changes to it; "new" for
 * an item the user created. */
export function OriginalBadge({ edited, isNew }: { edited?: boolean; isNew?: boolean }) {
  const { t } = useI18n()
  if (isNew) return <UiBadge className="font-normal">{t('common.new')}</UiBadge>
  return (
    <UiBadge variant="secondary" className="font-normal" title={edited ? t('common.wasOriginalHint') : undefined}>
      {edited ? t('common.wasOriginal') : t('common.original')}
    </UiBadge>
  )
}
