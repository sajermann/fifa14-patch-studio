import { useQuery } from '@tanstack/react-query'
import { Check, Circle, Loader2, Square } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { ImportStep, ShareKind } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n, type MessageKey } from '@/i18n'
import { clock } from '@/lib/clock'
import { useEta } from '@/lib/eta'
import { toast } from '@/lib/notify'
import { cn } from '@/lib/utils'

const STEP_LABELS: Record<ImportStep, MessageKey> = {
  prepare: 'import.stepPrepare',
  write: 'import.stepWrite',
  links: 'import.stepLinks',
  save: 'import.stepSave',
}
// share of the whole each step takes (writing the items is nearly all of it; saving a big package takes a while)
const STEP_WEIGHT: Record<ImportStep, number> = { prepare: 0.02, write: 0.88, links: 0.02, save: 0.08 }
const KIND_LABELS: Record<ShareKind, MessageKey> = {
  country: 'import.itemCountry',
  league: 'import.itemLeague',
  team: 'import.itemTeam',
  player: 'import.itemPlayer',
  stadium: 'import.itemStadium',
  adboard: 'import.itemAdboard',
  boot: 'import.itemBoot',
  glove: 'import.itemGlove',
  ball: 'import.itemBall',
}
const POLL_MS = 500

/** Step by step progress of an import (same layout as the build's BuildProgressDialog), polled while `open`:
 * the item being written, items left, time left and the clock. "Parar" stops it and nothing changes in the project. */
export function ImportProgressDialog({ open }: { open: boolean }) {
  const { t } = useI18n()
  const [asked, setAsked] = useState(false)
  const [seen, setSeen] = useState(false) // this import answered at least once (the data is not the previous one's)
  const { data } = useQuery({
    queryKey: ['import-progress'],
    queryFn: api.importProgress,
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
    gcTime: 0,
  })
  if (open && !seen && data?.running) setSeen(true)
  if (!open && (asked || seen)) {
    setAsked(false)
    setSeen(false)
  }
  const prog = data?.running || (seen && data) ? data : undefined
  const finished = !!prog && !prog.running
  const steps = prog?.steps ?? (Object.keys(STEP_LABELS) as ImportStep[])
  const current = finished ? steps.length : prog?.step ? steps.indexOf(prog.step) : -1
  const stepShare = prog?.total && !finished ? prog.done / prog.total : 0
  const before = steps.slice(0, Math.max(current, 0)).reduce((sum, s) => sum + STEP_WEIGHT[s], 0)
  const overall = finished ? 100 : prog?.step ? Math.round((before + STEP_WEIGHT[prog.step] * stepShare) * 100) : 0
  const elapsed = prog?.elapsed ?? 0
  const eta = useEta(prog?.running && prog.step === 'write' ? 'write' : null, prog?.done ?? 0, prog?.total ?? 0, elapsed)
  const left = prog && prog.step === 'write' && !finished ? prog.total - prog.done : 0
  const stopping = !finished && (asked || !!prog?.stopping)

  const stop = () => {
    setAsked(true)
    api.cancelImport().catch((e: Error) => toast.error(e.message))
  }

  return (
    <Dialog open={open}>
      <DialogContent width="md" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t('import.title')}</DialogTitle>
          <DialogDescription>{t('import.description')}</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-1.5">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
          </div>
          <div className="flex justify-between gap-3 text-xs text-muted-foreground tabular-nums">
            <span>{overall}%</span>
            <span className="flex gap-3">
              {eta !== null && <span>{t('import.timeLeft', { time: clock(eta) })}</span>}
              <span>{t('import.elapsed', { time: clock(elapsed) })}</span>
            </span>
          </div>
        </div>
        <ul className="space-y-2 text-sm">
          {steps.map((step, i) => {
            const state = i < current ? 'done' : i === current ? 'running' : 'pending'
            return (
              <li key={step} className={cn('flex items-center gap-2', state === 'pending' && 'text-muted-foreground')}>
                {state === 'done' ? (
                  <Check className="size-4 text-emerald-600" />
                ) : state === 'running' ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Circle className="size-4" />
                )}
                <span className="flex-1">{t(STEP_LABELS[step])}</span>
                {state === 'running' && prog!.total > 1 && (
                  <span className="text-xs text-muted-foreground tabular-nums">{t('import.count', { done: prog!.done, total: prog!.total })}</span>
                )}
              </li>
            )
          })}
        </ul>
        <div className="min-w-0 space-y-1 text-xs text-muted-foreground">
          {finished ? (
            <p>{t('import.finishing')}</p>
          ) : prog?.step === 'save' ? (
            <p>{t('import.saveHint')}</p>
          ) : (
            prog?.item && (
              <p className="truncate">{t(KIND_LABELS[prog.item.kind], { name: prog.item.name ?? `#${prog.item.id}` })}</p>
            )
          )}
          {left > 0 && <p className="tabular-nums">{t('import.left', { count: left })}</p>}
        </div>
        <div className="flex items-center gap-3 border-t pt-3">
          <p className="flex-1 text-xs text-muted-foreground">{finished ? null : stopping ? t('import.stopping') : t('import.stopHint')}</p>
          <Button variant="outline" size="sm" onClick={stop} disabled={stopping || !prog || finished || prog.step === 'save'}>
            {stopping ? <Loader2 className="animate-spin" /> : <Square />} {t('build.stop')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
