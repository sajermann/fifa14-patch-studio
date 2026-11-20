import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, CircleAlert, Download, FolderOpen, Hammer, Loader2, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import type { Job, ProjectIssue } from '@/api/types'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { issueLink, issueText } from '@/lib/issues'
import { toast } from '@/lib/notify'
import { useProjectIssues, useStatus } from '@/state/queries'

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

/** The issues, errors first, each with a link to its league/team/player. */
function IssueList({ issues, onNavigate }: { issues: ProjectIssue[]; onNavigate: () => void }) {
  const { t } = useI18n()
  const sorted = useMemo(() => [...issues].sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1)), [issues])
  if (sorted.length === 0) return <p className="text-sm text-muted-foreground">{t('issues.none')}</p>
  return (
    <ul className="space-y-2">
      {sorted.map((i, k) => {
        const link = issueLink(t, i)
        return (
          <li key={k} className="flex items-start gap-2 text-sm">
            {i.severity === 'error' ? (
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
            ) : (
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
            )}
            <div>
              {link && (
                <Link to={link.to} className="font-medium underline-offset-4 hover:underline" onClick={onNavigate}>
                  {link.label}
                </Link>
              )}
              <p className="text-muted-foreground">{issueText(t, i)}</p>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function IssuesDialog({ open, onOpenChange, issues }: { open: boolean; onOpenChange: (v: boolean) => void; issues: ProjectIssue[] }) {
  const { t } = useI18n()
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent width="lg">
        <DialogHeader>
          <DialogTitle>{t('issues.title')}</DialogTitle>
          <DialogDescription>{t('issues.description')}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh] pr-3">
          <IssueList issues={issues} onNavigate={() => onOpenChange(false)} />
        </ScrollArea>
      </DialogContent>
    </Dialog>
  )
}

/** Header actions: build the patch (the main action), install it, and the rest in a menu (uninstall last). */
export function PatchActions() {
  const { t } = useI18n()
  const status = useStatus().data
  const start = usePatchJob()
  const issues = useProjectIssues()
  const [issuesOpen, setIssuesOpen] = useState(false)
  if (status?.game.state !== 'ready') return null
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
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
      <Button variant="ghost" size="sm" onClick={() => setIssuesOpen(true)}>
        <CircleAlert className={errors ? 'text-destructive' : 'text-muted-foreground'} /> {errors}
        <AlertTriangle className={warnings ? 'text-amber-600' : 'text-muted-foreground'} /> {warnings}
      </Button>
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button size="sm" disabled={running || errors > 0} onClick={() => start.mutate('build')}>
              {busy('build') ? <Loader2 className="animate-spin" /> : <Hammer />} {t('patch.build')}
            </Button>
          </span>
        </TooltipTrigger>
        {errors > 0 && <TooltipContent>{t('patch.fixErrorsFirst')}</TooltipContent>}
      </Tooltip>
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
      <IssuesDialog open={issuesOpen} onOpenChange={setIssuesOpen} issues={issues} />
    </div>
  )
}
