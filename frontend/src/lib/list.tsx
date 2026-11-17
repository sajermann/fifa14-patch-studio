import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown, Search, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { TableHead } from '@/components/ui/table'
import { useI18n } from '@/i18n'
import { cn } from '@/lib/utils'

export const ALL = 'all'
export const PAGE_SIZES = [25, 50, 100]
const LIST_KEYS = ['page', 'size', 'sort', 'dir'] as const

/** The state of a list lives in the URL (?q=…&league=…&sort=…&page=…): reload, back/forward and a copied link
 * open the same page. Every filter, the sort and the page go to the backend as they are. */
export function useListState<K extends string>(filters: readonly K[]) {
  const [params, setParams] = useSearchParams()
  const values = Object.fromEntries(filters.map((k) => [k, params.get(k) ?? ''])) as Record<K, string>
  const page = Math.max(1, Number(params.get('page')) || 1)
  const size = PAGE_SIZES.includes(Number(params.get('size'))) ? Number(params.get('size')) : 50
  const sort = params.get('sort') ?? ''
  const dir = params.get('dir') ?? ''

  const update = (changes: Record<string, string | number | null>, resetPage = true) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p)
        for (const [k, v] of Object.entries(changes)) {
          if (v === null || v === '' || v === ALL) next.delete(k)
          else next.set(k, String(v))
        }
        if (resetPage && !('page' in changes)) next.delete('page')
        return next
      },
      { replace: true },
    )

  const active = filters.some((k) => values[k] !== '')
  const clear = () =>
    setParams(
      (p) => {
        const next = new URLSearchParams()
        for (const k of LIST_KEYS) if (k !== 'page' && p.get(k)) next.set(k, p.get(k)!)
        return next
      },
      { replace: true },
    )
  /** The parameters sent to the backend. */
  const request = { ...Object.fromEntries(filters.map((k) => [k, values[k] || undefined])), page, size, sort: sort || undefined, dir: dir || undefined }
  return { values, page, size, sort, dir, update, active, clear, request }
}

/** Search box that writes to the URL a moment after typing stops. */
export function SearchInput({ value, onChange, placeholder, className = 'w-64' }: { value: string; onChange: (v: string) => void; placeholder: string; className?: string }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  useEffect(() => {
    if (text === value) return
    const id = setTimeout(() => onChange(text), 300)
    return () => clearTimeout(id)
  }, [text]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className={cn('relative', className)}>
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} className="w-full pl-8" />
    </div>
  )
}

export interface FilterOption {
  value: string
  label: string
}

export function FilterSelect({ value, onChange, options, allLabel, className = 'w-48' }: { value: string; onChange: (v: string) => void; options: FilterOption[]; allLabel: string; className?: string }) {
  return (
    <Select value={value || ALL} onValueChange={onChange}>
      <SelectTrigger className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{allLabel}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function FilterBar({ children, active, onClear }: { children: ReactNode; active: boolean; onClear: () => void }) {
  const { t } = useI18n()
  return (
    <div className="flex flex-wrap items-center gap-2">
      {children}
      {active && (
        <Button variant="ghost" size="sm" onClick={onClear}>
          <X /> {t('list.clearFilters')}
        </Button>
      )}
    </div>
  )
}

/** Column header that sorts the list (on the backend); a second click flips the direction. */
export function SortHead({ field, label, state, className }: { field: string; label: ReactNode; state: { sort: string; dir: string; update: (c: Record<string, string | null>) => void; current: string; currentDir: string }; className?: string }) {
  const active = state.current === field
  const Icon = !active ? ChevronsUpDown : state.currentDir === 'asc' ? ArrowUp : ArrowDown
  return (
    <TableHead className={className}>
      <button
        type="button"
        className={cn('inline-flex items-center gap-1 hover:text-foreground', active && 'text-foreground')}
        onClick={() => state.update({ sort: field, dir: active ? (state.currentDir === 'asc' ? 'desc' : 'asc') : null })}
      >
        {label}
        <Icon className="size-3.5 opacity-60" />
      </button>
    </TableHead>
  )
}

export function Pager({ page, pages, total, size, onPage }: { page: number; pages: number; total: number; size: number; onPage: (page: number, size?: number) => void }) {
  const { t } = useI18n()
  const first = total ? (page - 1) * size + 1 : 0
  return (
    <div className="flex flex-wrap items-center justify-end gap-2 text-sm text-muted-foreground">
      <span className="tabular-nums">{t('list.range', { first, last: Math.min(page * size, total), total })}</span>
      <Select value={String(size)} onValueChange={(v) => onPage(1, Number(v))}>
        <SelectTrigger size="sm" className="w-36">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PAGE_SIZES.map((n) => (
            <SelectItem key={n} value={String(n)}>
              {t('list.perPage', { count: n })}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="ghost" size="icon" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label={t('list.previousPage')}>
        <ChevronLeft />
      </Button>
      <span className="tabular-nums">
        {page}/{pages}
      </span>
      <Button variant="ghost" size="icon" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label={t('list.nextPage')}>
        <ChevronRight />
      </Button>
    </div>
  )
}

export const LIST_PAGE = 'flex h-full min-h-[24rem] flex-col gap-4'

/** Table that fills the rest of the page and scrolls inside (the header sticks). */
export function ScrollTable({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-md border">
      <table
        className={
          'w-full caption-bottom text-sm [&_td]:whitespace-nowrap [&_th]:whitespace-nowrap ' +
          '[&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 [&_thead]:bg-background [&_thead]:shadow-[inset_0_-1px_0_var(--border)] ' +
          '[&_[data-grow]]:w-full [&_[data-grow]]:whitespace-normal [&_td_img]:max-w-none'
        }
      >
        {children}
      </table>
    </div>
  )
}
