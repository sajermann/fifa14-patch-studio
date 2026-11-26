import { useQuery } from '@tanstack/react-query'
import { Ban, Loader2, RotateCcw, Square, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n, type MessageKey } from '@/i18n'
import { clock } from '@/lib/clock'
import { useEta } from '@/lib/eta'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'

const POLL_MS = 500
const ROWS: { key: 'deleted' | 'reset' | 'skipped'; label: MessageKey; Icon: typeof Trash2 }[] = [
  { key: 'deleted', label: 'bulkDelete.deleted', Icon: Trash2 },
  { key: 'reset', label: 'bulkDelete.reset', Icon: RotateCcw },
  { key: 'skipped', label: 'bulkDelete.skipped', Icon: Ban },
]

/** Progress of a bulk delete of the lists (same layout as the import's ImportProgressDialog), polled while `open`:
 * items gone through, how many were deleted / restored / skipped, time left and the clock. "Parar" stops it before
 * the next item (what was already deleted stays deleted). */
export function BulkDeleteProgressDialog({ open, total }: { open: boolean; total: number }) {
  const { t } = useI18n()
  const [asked, setAsked] = useState(false)
  const [seen, setSeen] = useState(false) // this delete answered at least once (the data is not the previous one's)
  const { data } = useQuery({
    queryKey: ['bulk-delete-progress'],
    queryFn: api.bulkDeleteProgress,
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
    gcTime: 0,
  })
  if (open && !seen && data?.running) setSeen(true)
  if (!open && (asked || seen)) {
    setAsked(false)
    setSeen(false)
  }
  const prog = seen && data ? data : undefined
  const finished = !!prog && !prog.running
  const count = prog?.total ?? total
  const done = prog?.done ?? 0
  const overall = count ? Math.round((done / count) * 100) : 0
  const elapsed = prog?.elapsed ?? 0
  const eta = useEta(prog?.running ? 'delete' : null, done, count, elapsed)
  const left = prog && !finished ? count - done : 0
  const stopping = !finished && (asked || !!prog?.stopping)

  const stop = () => {
    setAsked(true)
    api.cancelBulkDelete().catch((e: Error) => toast.error(e.message))
  }

  return (
    <Dialog open={open}>
      <DialogContent width="md" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('bulkDelete.title', { count })}</DialogTitle>
          <DialogDescription>{t('bulkDelete.description')}</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-1.5">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
          </div>
          <div className="flex justify-between gap-3 text-xs text-muted-foreground tabular-nums">
            <span>
              {overall}% · {t('import.count', { done, total: count })}
            </span>
            <span className="flex gap-3">
              {eta !== null && <span>{t('import.timeLeft', { time: clock(eta) })}</span>}
              <span>{t('import.elapsed', { time: clock(elapsed) })}</span>
            </span>
          </div>
        </div>
        <ul className="space-y-2 text-sm">
          {ROWS.map(({ key, label, Icon }) => {
            const value = prog?.[key] ?? 0
            return (
              <li key={key} className={cn('flex items-center gap-2', !value && 'text-muted-foreground')}>
                <Icon className={cn('size-4', value > 0 && key === 'deleted' && 'text-emerald-600', value > 0 && key === 'skipped' && 'text-amber-600')} />
                <span className="flex-1">{t(label)}</span>
                <span className="text-xs tabular-nums">{value}</span>
              </li>
            )
          })}
        </ul>
        <div className="min-w-0 space-y-1 text-xs text-muted-foreground">
          {finished ? (
            <p>{t('bulkDelete.finishing')}</p>
          ) : (
            !prog && (
              <p className="flex items-center gap-1.5">
                <Loader2 className="size-3 animate-spin" /> {t('bulkDelete.starting')}
              </p>
            )
          )}
          {left > 0 && <p className="tabular-nums">{t('import.left', { count: left })}</p>}
        </div>
        <div className="flex items-center gap-3 border-t pt-3">
          <p className="flex-1 text-xs text-muted-foreground">{finished ? null : stopping ? t('bulkDelete.stopping') : t('bulkDelete.stopHint')}</p>
          <Button variant="outline" size="sm" onClick={stop} disabled={stopping || !prog || finished}>
            {stopping ? <Loader2 className="animate-spin" /> : <Square />} {t('build.stop')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
