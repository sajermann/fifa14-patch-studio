import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, CircleAlert, Download, FolderOpen, Hammer, Loader2, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import type { Job, ProjectIssue } from '@/api/types'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { BuildProgressDialog } from '@/components/layout/BuildProgress'
import { ImportProgressDialog } from '@/components/layout/ImportProgress'
import { issueLink, issueText } from '@/lib/issues'
import { toast } from '@/lib/notify'
import { useProjectIssues, useStatus } from '@/state/queries'

export type PatchJobKind = Exclude<Job['kind'], 'import'>

/** Starts a build / install / uninstall job; the status is polled while it runs. */
export function usePatchJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kind: PatchJobKind) => (kind === 'build' ? api.buildPatch() : kind === 'install' ? api.installPatch() : api.uninstallPatch()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['status'] }),
    onError: (e: Error) => toast.error(e.message),
  })
}

/** "Gerar patch" like the Street Studio's: a patch already up to date is built again only if the user confirms.
 * Returns the click handler and the confirmation dialog to render. */
export function useBuildPatch() {
  const { t } = useI18n()
  const status = useStatus().data
  const start = usePatchJob()
  const [rebuildOpen, setRebuildOpen] = useState(false)
  const build = () => {
    if (status?.patch?.up_to_date) setRebuildOpen(true)
    else start.mutate('build')
  }
  const confirm = (
    <AlertDialog open={rebuildOpen} onOpenChange={setRebuildOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('patch.rebuildTitle')}</AlertDialogTitle>
          <AlertDialogDescription>{t('patch.rebuildDescription')}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
          <AlertDialogAction onClick={() => start.mutate('build')}>{t('patch.rebuild')}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
  return { build, confirm, pending: start.isPending }
}

/** "1 min 5 s" / "12 s" (the Street Studio's build time). */
function duration(t: ReturnType<typeof useI18n>['t'], total: number) {
  const seconds = Math.round(total)
  return seconds < 60
    ? t('patch.durationSeconds', { seconds })
    : t('patch.durationMinutes', { minutes: Math.floor(seconds / 60), seconds: seconds % 60 })
}

// the menu name of each kind an import brings (nav.<name> in the dictionaries)
const IMPORT_NAV: Record<string, string> = {
  country: 'countries', league: 'leagues', team: 'teams', player: 'players', stadium: 'stadiums',
  adboard: 'adboards', boot: 'boots', glove: 'gloves', ball: 'balls',
}

/** Tells the user when a job ends, whatever screen is open (mounted once, in the shell), and shows the build's
 * progress while it runs. */
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
    if (job.kind === 'import') {
      const r = job.result as { count?: number; imported?: Record<string, number[]> } | null
      if (job.state === 'done') {
        const what = Object.entries(r?.imported ?? {})
          .map(([k, ids]) => `${t(`nav.${IMPORT_NAV[k] ?? k}` as MessageKey)}: ${ids.length}`)
          .join(' · ')
        toast.success(t('share.imported', { count: r?.count ?? 0, what }))
      } else if (job.code === 'import_cancelled') toast.info(t('import.stopped'))
      else toast.error(t('import.failed', { detail: job.error ?? '' }))
      void qc.invalidateQueries()
      return
    }
    if (job.state === 'done' && job.kind === 'build') {
      const r = (job.result ?? {}) as { files?: number; cache_reused_files?: number; duration_s?: number }
      const count = r.files ?? 0
      const reused = Math.min(r.cache_reused_files ?? 0, count)
      toast.success(t('patch.built'), {
        description: t('patch.builtDetail', { count, made: count - reused, reused, time: duration(t, r.duration_s ?? 0) }),
      })
    } else if (job.state === 'done') toast.success(t(`patch.done.${job.kind}` as MessageKey))
    else if (job.code === 'build_cancelled') {
      // stopped by the user: what was made is in the build cache, building again continues from there
      toast.info(t('patch.buildStopped'), {
        description: t('patch.buildStoppedDetail'),
        duration: 10000,
        action: {
          label: t('patch.buildContinue'),
          onClick: () =>
            void api
              .buildPatch()
              .then(() => qc.invalidateQueries({ queryKey: ['status'] }))
              .catch((e: Error) => toast.error(e.message)),
        },
      })
    } else if (job.code && hasMessage(`buildError.${job.code}`)) toast.error(t(`buildError.${job.code}` as MessageKey, { detail: job.detail ?? '' }))
    else toast.error(job.error ?? t('patch.failed'))
    void qc.invalidateQueries()
  }, [job, qc, t])
  return (
    <>
      <BuildProgressDialog open={job?.kind === 'build' && job.state === 'running'} />
      <ImportProgressDialog open={job?.kind === 'import' && job.state === 'running'} />
    </>
  )
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
  const rebuild = useBuildPatch()
  const issues = useProjectIssues()
  const [issuesOpen, setIssuesOpen] = useState(false)
  if (status?.game.state !== 'ready') return null
  const errors = issues.filter((i) => i.severity === 'error').length
  const warnings = issues.length - errors
  const job = status.job
  const running = job?.state === 'running' || start.isPending || rebuild.pending
  const busy = (kind: PatchJobKind) => job?.state === 'running' && job.kind === kind
  const patch = status.patch
  const canInstall = !!patch?.up_to_date
  const patchBadge = !patch?.built ? (
    <Badge variant="outline">{t('patch.badgeNeverBuilt')}</Badge>
  ) : patch.up_to_date ? (
    <Badge variant="secondary">{t('patch.badgeUpToDate')}</Badge>
  ) : (
    <Badge variant="outline" className="border-amber-500 text-amber-700 dark:text-amber-400">
      {t('patch.badgeNotBuilt')}
    </Badge>
  )
  return (
    <div className="flex items-center gap-2">
      {patchBadge}
      {job?.state === 'running' && job.kind !== 'build' && job.kind !== 'import' && (
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
            <Button size="sm" disabled={running || errors > 0} onClick={rebuild.build}>
              {busy('build') ? <Loader2 className="animate-spin" /> : <Hammer />} {t('patch.build')}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{errors > 0 ? t('patch.fixErrorsFirst') : t('patch.buildHint')}</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button variant="outline" size="sm" disabled={running || !canInstall} onClick={() => start.mutate('install')}>
              {busy('install') ? <Loader2 className="animate-spin" /> : <Download />} {t('patch.install')}
            </Button>
          </span>
        </TooltipTrigger>
        {!canInstall && <TooltipContent>{t('patch.buildBeforeInstall')}</TooltipContent>}
      </Tooltip>
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
      {rebuild.confirm}
    </div>
  )
}
