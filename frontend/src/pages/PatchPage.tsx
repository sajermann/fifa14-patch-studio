import { Download, FolderOpen, Hammer, Loader2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api } from '@/api/client'
import { useBuildPatch, usePatchJob } from '@/components/layout/PatchActions'
import { Facts, Section } from '@/components/common/detail'
import { useI18n, type MessageKey } from '@/i18n'
import { useStatus } from '@/state/queries'

export function PatchPage() {
  const { t } = useI18n()
  const status = useStatus().data
  const job = status?.job
  const running = job?.state === 'running'
  const start = usePatchJob()
  const rebuild = useBuildPatch()
  const check = status?.game.check
  const edited = status?.project ?? {}
  const result = job?.state === 'done' && job.kind === 'build' ? job.result : null
  const missing = (result?.missing_strings as string[] | undefined) ?? []
  return (
    <div className="max-w-4xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{t('patch.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('patch.subtitle')}</p>
      </div>

      <Section title={t('patch.project')}>
        <Facts items={[[t('nav.teams'), edited.team ?? 0]]} />
      </Section>

      <Section title={t('patch.steps')}>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" disabled={running || start.isPending || rebuild.pending} onClick={rebuild.build}>
              {running && job.kind === 'build' ? <Loader2 className="animate-spin" /> : <Hammer />} {t('patch.build')}
            </Button>
            <Button variant="outline" size="sm" disabled={!status?.patch_built} onClick={() => void api.openPatchFolder()}>
              <FolderOpen /> {t('patch.openFolder')}
            </Button>
            <p className="text-xs text-muted-foreground">{t('patch.buildHint')}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="outline" size="sm" disabled={running || !status?.patch?.up_to_date || start.isPending} onClick={() => start.mutate('install')}>
              <Download /> {t('patch.install')}
            </Button>
            <Button variant="outline" size="sm" disabled={running || check?.state !== 'patched' || start.isPending} onClick={() => start.mutate('uninstall')}>
              <RotateCcw /> {t('patch.uninstall')}
            </Button>
            <p className="text-xs text-muted-foreground">{check?.state === 'patched' ? t('patch.installed') : t('patch.notInstalled')}</p>
          </div>
          {running && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> {t(`patch.running.${job.kind}` as MessageKey)} {Math.round(job.done * 100)}%
            </p>
          )}
          {missing.length > 0 && (
            <p className="text-sm text-amber-700 dark:text-amber-300">
              {t('patch.missingStrings', {
                list: missing.slice(0, 10).join(', '),
              })}
            </p>
          )}
        </div>
      </Section>

      <Section title={t('patch.howTitle')}>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>{t('patch.how1')}</li>
          <li>{t('patch.how2')}</li>
          <li>{t('patch.how3')}</li>
        </ul>
      </Section>
      {rebuild.confirm}
    </div>
  )
}
