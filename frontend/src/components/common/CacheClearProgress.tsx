import { useQuery } from '@tanstack/react-query'
import { CircleAlert, HardDrive, Loader2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n } from '@/i18n'
import { clock } from '@/lib/clock'
import { fileSize } from '@/lib/size'
import { cn } from '@/lib/utils'

const POLL_MS = 300

/** Progress of clearing the cache (same layout as BulkDeleteProgressDialog), polled while `open`: files deleted,
 * space freed and the clock. `finished` = the request answered: the dialog shows the result and can be closed. */
export function CacheClearProgressDialog({ open, finished, onClose }: { open: boolean; finished: boolean; onClose: () => void }) {
  const { t, lang } = useI18n()
  const [seen, setSeen] = useState(false) // this clearing answered at least once (the data is not the previous one's)
  const { data } = useQuery({
    queryKey: ['cache-clear-progress'],
    queryFn: api.cacheClearProgress,
    enabled: open,
    refetchInterval: open && !finished ? POLL_MS : false,
    gcTime: 0,
  })
  if (open && !seen && (data?.running || finished)) setSeen(true)
  if (!open && seen) setSeen(false)
  const prog = seen && data ? data : undefined
  const done = !!prog && !prog.running && finished
  const overall = done ? 100 : prog?.total ? Math.round((prog.done / prog.total) * 100) : 0
  const failed = prog?.failed ?? 0
  const rows = [
    { key: 'files', label: t('cache.filesDeleted'), Icon: Trash2, value: prog ? String(prog.done - failed) : '0' },
    { key: 'bytes', label: t('cache.freed'), Icon: HardDrive, value: fileSize(prog?.bytes_done ?? 0, lang) },
  ]

  return (
    <Dialog open={open}>
      <DialogContent width="md" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{done ? t('cache.doneTitle') : t('cache.progressTitle')}</DialogTitle>
          <DialogDescription>{t('cache.progressDescription')}</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-1.5">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
          </div>
          <div className="flex justify-between gap-3 text-xs text-muted-foreground tabular-nums">
            <span>
              {overall}% · {t('import.count', { done: prog?.done ?? 0, total: prog?.total ?? 0 })}
            </span>
            <span>{t('import.elapsed', { time: clock(prog?.elapsed ?? 0) })}</span>
          </div>
        </div>
        <ul className="space-y-2 text-sm">
          {rows.map(({ key, label, Icon, value }) => (
            <li key={key} className="flex items-center gap-2">
              <Icon className={cn('size-4', done && 'text-emerald-600')} />
              <span className="flex-1">{label}</span>
              <span className="text-xs tabular-nums">{value}</span>
            </li>
          ))}
          {failed > 0 && (
            <li className="flex items-center gap-2">
              <CircleAlert className="size-4 text-amber-600" />
              <span className="flex-1">{t('cache.failed')}</span>
              <span className="text-xs tabular-nums">{failed}</span>
            </li>
          )}
        </ul>
        <div className="flex items-center gap-3 border-t pt-3">
          <p className="flex flex-1 items-center gap-1.5 text-xs text-muted-foreground">
            {done ? (
              t('cache.done', { size: fileSize(prog.bytes_done, lang), time: clock(prog.elapsed ?? 0) })
            ) : (
              <>
                <Loader2 className="size-3 animate-spin" /> {prog ? null : t('cache.starting')}
              </>
            )}
          </p>
          <Button variant="outline" size="sm" onClick={onClose} disabled={!done}>
            {t('common.close')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
