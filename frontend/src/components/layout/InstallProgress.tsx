import { useQuery } from '@tanstack/react-query'
import { Check, Circle, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api/client'
import type { InstallPhase } from '@/api/types'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useI18n, type MessageKey } from '@/i18n'
import { clock } from '@/lib/clock'
import { cn } from '@/lib/utils'

const POLL_MS = 400
const STEPS: Record<'install' | 'uninstall', InstallPhase[]> = {
  install: ['checking', 'restoring', 'copying', 'verifying'],
  uninstall: ['restoring', 'verifying'],
}
const LABELS: Record<'install' | 'uninstall', Partial<Record<InstallPhase, MessageKey>>> = {
  install: {
    checking: 'install.stepChecking',
    restoring: 'install.stepRestoring',
    copying: 'install.stepCopying',
    verifying: 'install.stepVerifying',
  },
  uninstall: { restoring: 'install.stepUninstalling', verifying: 'install.stepVerifying' },
}

const megabytes = (bytes: number, lang: string) =>
  (bytes / (1024 * 1024)).toLocaleString(lang, { maximumFractionDigits: bytes < 10 * 1024 * 1024 ? 1 : 0 })

/** Step by step progress of installing / uninstalling the patch in the game (GET /api/patch/install/progress), shown
 * while the job runs (it cannot be closed meanwhile): which step, which file, how much was copied. */
export function InstallProgressDialog({ action, open }: { action: 'install' | 'uninstall'; open: boolean }) {
  const { t, lang } = useI18n()
  const [seen, setSeen] = useState(false) // this run answered at least once (the data is not the previous run's)
  const { data } = useQuery({
    queryKey: ['install-progress'],
    queryFn: api.installProgress,
    enabled: open,
    refetchInterval: open ? POLL_MS : false,
    gcTime: 0,
  })
  if (open && !seen && data?.running && data.action === action) setSeen(true)
  if (!open && seen) setSeen(false)

  const prog = seen && data?.action === action ? data : undefined
  const steps = STEPS[action]
  const phase = prog?.phase
  const finished = !!prog && !prog.running
  const current = finished ? steps.length : phase ? steps.indexOf(phase) : 0
  const share = prog?.bytes_total ? prog.bytes_done / prog.bytes_total : prog?.total ? prog.done / prog.total : 0
  const overall = finished ? 100 : Math.round(((Math.max(current, 0) + share) / steps.length) * 100)

  const detail = (() => {
    if (!prog) return t('install.starting')
    if (finished) return t('install.finishing')
    if (prog.name) return prog.name
    return null
  })()

  return (
    <Dialog open={open}>
      <DialogContent width="md" showCloseButton={false} onEscapeKeyDown={(e) => e.preventDefault()} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>{t(action === 'install' ? 'install.title' : 'install.titleUninstall')}</DialogTitle>
          <DialogDescription>{t('install.description')}</DialogDescription>
        </DialogHeader>
        <div className="min-w-0 space-y-1.5">
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full bg-primary transition-[width] duration-300" style={{ width: `${overall}%` }} />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
            <span>{overall}%</span>
            <span>{prog?.elapsed !== undefined ? clock(prog.elapsed) : '0:00'}</span>
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
                <span className="flex-1">{t(LABELS[action][step]!)}</span>
                {state === 'running' && prog && prog.total > 0 && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {t('build.count', { done: prog.done, total: prog.total })}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
        <div className="min-w-0 space-y-1 text-xs text-muted-foreground">
          {detail && <p className={cn('truncate', detail === prog?.name && 'font-mono')}>{detail}</p>}
          {phase === 'copying' && prog && !!prog.kept && (
            <p className="tabular-nums">{t('install.kept', { count: prog.kept })}</p>
          )}
          {phase === 'copying' && prog && prog.bytes_total > 0 && (
            <p className="tabular-nums">
              {t('install.bytes', { done: megabytes(prog.bytes_done, lang), total: megabytes(prog.bytes_total, lang) })}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
