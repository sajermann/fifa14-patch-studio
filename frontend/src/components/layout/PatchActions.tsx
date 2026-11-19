import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Download, FolderOpen, Hammer, Loader2, RotateCcw } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { api } from '@/api/client'
import type { Job } from '@/api/types'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { toast } from '@/lib/notify'
import { useStatus } from '@/state/queries'

export type PatchJobKind = Job['kind']

/** Starts a build / install / uninstall job; the status is polled while it runs. */
export function usePatchJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kind: PatchJobKind) => (kind === 'build' ? api.buildPatch() : kind === 'install' ? api.installPatch() : api.uninstallPatch()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['status'] }),
    onError: (e: Error) => toast.error(e.message),
  })
}

/** Tells the user when a job ends, whatever screen is open (mounted once, in the shell). */
export function JobWatcher() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const job = useStatus().data?.job
  const last = useRef<string | null>(null)
  useEffect(() => {
    if (!job) return
    const key = `${job.id}:${job.state}`
    if (last.current === key) return
    const first = last.current === null
    last.current = key
    if (job.state === 'running' || first) return // still running, or ended before the app opened
    if (job.state === 'done') toast.success(t(`patch.done.${job.kind}` as MessageKey))
    else if (job.code && hasMessage(`buildError.${job.code}`)) toast.error(t(`buildError.${job.code}` as MessageKey, { detail: job.detail ?? '' }))
    else toast.error(job.error ?? t('patch.failed'))
    void qc.invalidateQueries()
  }, [job, qc, t])
  return null
}

/** Header actions: build the patch (the main action), install it, and the rest in a menu (uninstall last). */
export function PatchActions() {
  const { t } = useI18n()
  const status = useStatus().data
  const start = usePatchJob()
  if (status?.game.state !== 'ready') return null
  const job = status.job
  const running = job?.state === 'running' || start.isPending
  const busy = (kind: PatchJobKind) => job?.state === 'running' && job.kind === kind
  return (
    <div className="flex items-center gap-2">
      {job?.state === 'running' && (
        <span className="text-xs text-muted-foreground tabular-nums">
          {t(`patch.running.${job.kind}` as MessageKey)} {Math.round(job.done * 100)}%
        </span>
      )}
      <Button size="sm" disabled={running} onClick={() => start.mutate('build')}>
        {busy('build') ? <Loader2 className="animate-spin" /> : <Hammer />} {t('patch.build')}
      </Button>
      <Button variant="outline" size="sm" disabled={running || !status.patch_built} onClick={() => start.mutate('install')}>
        {busy('install') ? <Loader2 className="animate-spin" /> : <Download />} {t('patch.install')}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon-sm" aria-label={t('patch.more')} title={t('patch.more')}>
            <ChevronDown />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem disabled={!status.patch_built} onSelect={() => void api.openPatchFolder()}>
            <FolderOpen /> {t('patch.openFolder')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" disabled={running || status.game.check?.state !== 'patched'} onSelect={() => start.mutate('uninstall')}>
            {busy('uninstall') ? <Loader2 className="animate-spin" /> : <RotateCcw />} {t('patch.uninstall')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
