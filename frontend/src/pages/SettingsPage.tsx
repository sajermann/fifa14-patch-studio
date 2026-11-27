import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, CircleAlert, Loader2, Settings2, Trash2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api/client'
import type { Config, Status } from '@/api/types'
import { BuildResourcesFields } from '@/components/common/BuildResources'
import { CacheClearProgressDialog } from '@/components/common/CacheClearProgress'
import { Facts } from '@/components/common/detail'
import { FacePackFolders } from '@/components/common/FacePackFolders'
import { Field } from '@/components/common/form'
import { SupportActions } from '@/components/common/SupportActions'
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
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useI18n, type MessageKey } from '@/i18n'
import { rich } from '@/i18n/rich'
import { APP_NAME, APP_VERSION, AUTHOR_GITHUB, AUTHOR_NAME, REPO_URL } from '@/lib/about'
import { buildResourcesErrors, useMachine, type BuildResourcesValue } from '@/lib/buildResources'
import { cleanFolders } from '@/lib/folders'
import { toast } from '@/lib/notify'
import { fileSize } from '@/lib/size'
import { useOptions, useStatus } from '@/state/queries'

// The Street Studio's settings screen, card by card; FIFA 14 has no save to delete
// nor project database to export, and keeps its "names language" and "about" cards.

function Line({ ok, warn, children }: { ok: boolean; warn?: boolean; children: ReactNode }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />
      ) : warn ? (
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
      ) : (
        <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />
      )}
      <span>{children}</span>
    </li>
  )
}

/** The game: its folder, the check of its files, the originals the app read and what is installed. */
function GameCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { game } = status
  const check = game.check
  const usable = check?.state === 'clean' || check?.state === 'patched'
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.gameTitle')}</CardTitle>
        <CardDescription>{t('settings.gameDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
          <dt className="text-muted-foreground">{t('settings.gameDir')}</dt>
          <dd className="font-mono break-all">{status.config.game_dir ?? '—'}</dd>
        </dl>
        {status.config.game_dir && (
          <ul className="space-y-1 text-sm">
            <Line ok={usable} warn={check?.state === 'modified'}>
              {check ? t(`check.state.${check.state}` as MessageKey) : t('settings.gameNotChecked')}
            </Line>
            <Line ok={game.state === 'ready'} warn={game.state === 'building'}>
              {game.state === 'ready'
                ? t('settings.originalsOk')
                : game.state === 'building'
                  ? t('game.preparing', { percent: Math.round(game.progress.done * 100) })
                  : t('settings.originalsBad')}
            </Line>
            <Line ok={!!check?.installed} warn>
              {check?.installed
                ? t('check.installedAt', { date: check.installed.installed_at, version: check.installed.version || '?' })
                : t('settings.notInstalled')}
            </Line>
          </ul>
        )}
        <Button variant="outline" onClick={() => navigate('/setup')}>
          <Settings2 /> {t('settings.changeFolders')}
        </Button>
      </CardContent>
    </Card>
  )
}

/** Where the project is, where the install backups are (inside the game folder) and the face pack folders. */
function FoldersCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [config, setConfig] = useState<Config | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (!config) setConfig({ ...status.config, project_dir: status.folders?.project ?? status.config.project_dir ?? '' })
  }, [status, config])
  if (!config) return null
  const set = (patch: Partial<Config>) => setConfig({ ...config, ...patch })

  const save = async () => {
    setSaving(true)
    try {
      const facePackDirs = cleanFolders(config.face_pack_dirs ?? [])
      if (facePackDirs.length) {
        const { packs } = await api.checkFacePacks(facePackDirs) // checks the folders before keeping them
        const missing = packs.find((p) => p.error)
        if (missing) {
          toast.error(t('settings.facePackInvalid', { folder: missing.folder }))
          return
        }
        toast.info(t('settings.facePackFound', { count: packs.reduce((n, p) => n + p.count, 0), packs: facePackDirs.length }))
      }
      // the game folder changes only through the setup screen (it checks the installation)
      await api.saveSettings({ project_dir: config.project_dir?.trim() || null, face_pack_dirs: facePackDirs })
      await qc.invalidateQueries() // another project folder changes every screen
      toast.success(t('settings.saved'))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.foldersTitle')}</CardTitle>
        <CardDescription>{t('settings.foldersDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label={t('settings.projectDir')} hint={t('settings.projectDirHint')}>
          <Input
            value={config.project_dir ?? ''}
            placeholder={status.folders?.default_project}
            onChange={(e) => set({ project_dir: e.target.value })}
            className="font-mono"
          />
        </Field>
        <Field label={t('settings.backupsDir')} hint={t('settings.backupsDirHint')}>
          <Input value={status.folders?.backups ?? '—'} readOnly disabled className="font-mono" />
        </Field>
        <Field label={t('settings.facePackDir')} hint={t('settings.facePackDirHint')}>
          <FacePackFolders value={config.face_pack_dirs ?? []} onChange={(face_pack_dirs) => set({ face_pack_dirs })} />
        </Field>
        <Button onClick={() => void save()} disabled={saving}>
          {saving && <Loader2 className="animate-spin" />} {t('settings.save')}
        </Button>
      </CardContent>
    </Card>
  )
}

/** How much of the machine the build may use (the Street Studio's BuildCard; saved on its own). */
function BuildCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const [value, setValue] = useState<BuildResourcesValue>({
    build_cores: status.config.build_cores ?? null,
    build_memory_percent: status.config.build_memory_percent ?? null,
  })
  const [saving, setSaving] = useState(false)
  const errors = buildResourcesErrors(useMachine(), value)
  const invalid = !!(errors.cores || errors.memory)
  const save = async () => {
    setSaving(true)
    try {
      await api.saveSettings({ build_cores: value.build_cores ?? null, build_memory_percent: value.build_memory_percent ?? null })
      await qc.invalidateQueries({ queryKey: ['status'] })
      await qc.invalidateQueries({ queryKey: ['machine'] })
      toast.success(t('settings.saved'))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('buildResources.title')}</CardTitle>
        <CardDescription>{t('buildResources.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <BuildResourcesFields value={value} onChange={(patch) => setValue({ ...value, ...patch })} />
        <Button onClick={() => void save()} disabled={saving || invalid}>
          {saving && <Loader2 className="animate-spin" />} {t('settings.save')}
        </Button>
      </CardContent>
    </Card>
  )
}

/** Which game language the lists show the names in. */
function NamesCard({ status }: { status: Status }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: (fields: Partial<Config>) => api.saveSettings(fields),
    onSuccess: () => qc.invalidateQueries(),
    onError: (e: Error) => toast.error(e.message),
  })
  const languages = useOptions().data?.languages ?? []
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings.gameNames')}</CardTitle>
        <CardDescription>{t('settings.gameNamesHint')}</CardDescription>
      </CardHeader>
      <CardContent>
        <Select value={status.config.names_language ?? 'auto'} onValueChange={(v) => save.mutate({ names_language: v === 'auto' ? null : v })}>
          <SelectTrigger className="w-60">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">{t('settings.namesAuto', { lang: status.names_language })}</SelectItem>
            {languages.map((l) => (
              <SelectItem key={l} value={l}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardContent>
    </Card>
  )
}

/** The app's cache folder: its size, and clearing what the app makes again (asks first, then shows the progress). */
function CacheCard() {
  const { t, lang } = useI18n()
  const qc = useQueryClient()
  const { data: info } = useQuery({ queryKey: ['cache'], queryFn: api.cacheInfo })
  const [asking, setAsking] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [finished, setFinished] = useState(false)

  const clear = async () => {
    setAsking(false)
    setFinished(false)
    setClearing(true)
    try {
      await api.clearCache()
      await qc.invalidateQueries({ queryKey: ['cache-clear-progress'] }) // the last numbers, for the result
      setFinished(true)
    } catch (e) {
      setClearing(false)
      toast.error((e as Error).message)
    } finally {
      void qc.invalidateQueries({ queryKey: ['cache'] })
    }
  }
  const size = (bytes: number, files: number) => t('cache.size', { size: fileSize(bytes, lang), files })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('cache.title')}</CardTitle>
        <CardDescription>{t('cache.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted-foreground">{t('cache.folder')}</dt>
          <dd className="font-mono break-all">{info?.folder ?? '—'}</dd>
          <dt className="text-muted-foreground">{t('cache.total')}</dt>
          <dd className="tabular-nums">{info ? size(info.bytes, info.files) : <Loader2 className="size-4 animate-spin" />}</dd>
          <dt className="text-muted-foreground">{t('cache.clearable')}</dt>
          <dd className="tabular-nums">{info ? size(info.clearable_bytes, info.clearable_files) : '—'}</dd>
        </dl>
        <p className="text-xs text-muted-foreground">{t('cache.keptHint')}</p>
        <div className="flex items-center gap-3">
          <Button variant="destructive" onClick={() => setAsking(true)} disabled={!info?.clearable_files || clearing}>
            <Trash2 /> {t('cache.clear')}
          </Button>
          {info && !info.clearable_files && <span className="text-sm text-muted-foreground">{t('cache.empty')}</span>}
        </div>
      </CardContent>
      <AlertDialog open={asking} onOpenChange={setAsking}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('cache.confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('cache.confirmDescription', { size: fileSize(info?.clearable_bytes ?? 0, lang), files: info?.clearable_files ?? 0 })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => (e.preventDefault(), void clear())}>
              <Trash2 /> {t('cache.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <CacheClearProgressDialog open={clearing} finished={finished} onClose={() => (setClearing(false), setFinished(false))} />
    </Card>
  )
}

export function SettingsPage() {
  const { t } = useI18n()
  const status = useStatus().data
  if (!status) return <Loader2 className="animate-spin" />
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{t('settings.title')}</h1>
      <GameCard status={status} />
      <FoldersCard status={status} />
      <BuildCard status={status} />
      <NamesCard status={status} />
      <CacheCard />
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.patchTitle')}</CardTitle>
          <CardDescription>{rich(t('settings.patchDescription', { folder: status.folders?.patch ?? '' }))}</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {status.patch?.built && status.patch.built_at ? t('settings.lastPatch', { date: status.patch.built_at }) : t('settings.noPatch')}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t('support.title')}</CardTitle>
          <CardDescription>{t('support.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <SupportActions />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.about')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Facts
            items={[
              [t('settings.app'), `${APP_NAME} ${APP_VERSION}`],
              [
                t('settings.author'),
                <a key="a" href={AUTHOR_GITHUB} target="_blank" rel="noreferrer" className="hover:underline">
                  {AUTHOR_NAME}
                </a>,
              ],
              [
                t('settings.code'),
                <a key="c" href={REPO_URL} target="_blank" rel="noreferrer" className="hover:underline">
                  {REPO_URL}
                </a>,
              ],
              [t('settings.license'), 'GPL-3.0'],
            ]}
          />
          <p className="mt-4 text-xs text-muted-foreground">{t('settings.disclaimer')}</p>
        </CardContent>
      </Card>
    </div>
  )
}
