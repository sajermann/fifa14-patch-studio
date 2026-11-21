import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FolderOpen, Loader2, XCircle } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from '@/lib/notify'
import { api } from '@/api/client'
import { BuildResourcesFields } from '@/components/common/BuildResources'
import { FacePackFolders } from '@/components/common/FacePackFolders'
import { cleanFolders } from '@/lib/folders'
import type { GameCheck, Status } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PreferencesMenu } from '@/components/layout/PreferencesMenu'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { rich } from '@/i18n/rich'
import { APP_VERSION } from '@/lib/about'
import { buildResourcesErrors, useMachine, type BuildResourcesValue } from '@/lib/buildResources'

// The Street Studio's setup screen (SetupPage.tsx). FIFA 14 has no save folder to set: the steps are the game,
// the face packs and the build settings, then the notice.

/** Folder field with a "browse" button (Windows folder picker opened by the backend). */
function FolderInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  const { t } = useI18n()
  const browse = async () => {
    try {
      const { path } = await api.pickFolder(value || null, t('setup.pickTitle'))
      if (path) onChange(path)
    } catch (e) {
      toast.error((e as Error).message || t('folder.dialogFailed'))
    }
  }
  return (
    <div className="flex gap-1">
      <Input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="font-mono" />
      <Button variant="outline" onClick={() => void browse()} title={t('folder.browseHint')}>
        <FolderOpen /> {t('common.browse')}
      </Button>
    </div>
  )
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">
        <span className="mr-2 inline-flex size-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
          {n}
        </span>
        {title}
      </p>
      {children}
    </div>
  )
}

/** What the check of the game folder found: a FIFA 14 the app can patch, or what is wrong with it. */
function GameCheckResult({ check }: { check: GameCheck }) {
  const { t } = useI18n()
  const ok = check.state === 'clean' || check.state === 'patched'
  const tone = ok
    ? 'text-emerald-700 dark:text-emerald-400'
    : check.state === 'modified'
      ? 'text-amber-700 dark:text-amber-400'
      : 'text-destructive'
  const Icon = ok ? CheckCircle2 : check.state === 'modified' ? AlertTriangle : XCircle
  return (
    <div className="space-y-1 text-sm">
      <p className={`flex items-center gap-2 ${tone}`}>
        <Icon className="size-4" /> {t(`check.state.${check.state}` as MessageKey)}
      </p>
      {check.installed && (
        <p className="ml-6 text-xs text-muted-foreground">
          {t('check.installedAt', { date: check.installed.installed_at, version: check.installed.version || '?' })}
        </p>
      )}
      {check.issues.length > 0 && (
        <ul className={`ml-6 list-disc space-y-0.5 pl-4 text-xs ${tone}`}>
          {check.issues.map((i, n) => {
            const key = `check.issue.${i.code}`
            return (
              <li key={n}>
                {hasMessage(key) ? t(key) : i.code}
                {i.detail && <span className="ml-1 font-mono">{i.detail}</span>}
              </li>
            )
          })}
        </ul>
      )}
      {check.state === 'modified' && <p className="ml-6 text-xs text-muted-foreground">{t('check.modifiedHint')}</p>}
    </div>
  )
}

/** First-run setup: game folder (checked), optional face packs and build settings, and the notice that must be
 * accepted before going on. Also reachable from the settings to change the game folder. */
export function SetupPage({ status }: { status: Status }) {
  const { t } = useI18n()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const cfg = status.config
  const [gameDir, setGameDir] = useState(cfg.game_dir ?? '')
  const [facePackDirs, setFacePackDirs] = useState(cfg.face_pack_dirs ?? [])
  // the game already chosen was checked when the app opened: no need to check it again
  const [check, setCheck] = useState<GameCheck | null>(cfg.game_dir ? (status.game.check ?? null) : null)
  const [checking, setChecking] = useState(false)
  const [accepted, setAccepted] = useState(cfg.terms_version === status.setup.terms_version)
  const [applying, setApplying] = useState(false)
  const [build, setBuild] = useState<BuildResourcesValue>({
    build_cores: cfg.build_cores ?? null,
    build_memory_percent: cfg.build_memory_percent ?? null,
  })
  const firstRun = status.setup.required

  const runCheck = async (dir = gameDir) => {
    if (!dir.trim()) return
    setChecking(true)
    setCheck(null)
    try {
      setCheck(await api.checkGame(dir.trim()))
    } catch (e) {
      toast.error((e as Error).message || t('setup.checkFailed'))
    } finally {
      setChecking(false)
    }
  }

  const gameOk = check?.state === 'clean' || check?.state === 'patched'
  const buildErrors = buildResourcesErrors(useMachine(), build)
  const canGo = gameOk && accepted && !applying && !buildErrors.cores && !buildErrors.memory

  const apply = async () => {
    setApplying(true)
    try {
      const folders = cleanFolders(facePackDirs)
      if (folders.length) {
        const { packs } = await api.checkFacePacks(folders) // checks the folders before keeping them
        const missing = packs.find((p) => p.error)
        if (missing) {
          toast.error(t('settings.facePackInvalid', { folder: missing.folder }))
          return
        }
      }
      await api.setupApply({
        game_dir: check?.game_dir ?? gameDir.trim(),
        face_pack_dirs: folders,
        terms_version: status.setup.terms_version,
        build_cores: build.build_cores ?? null,
        build_memory_percent: build.build_memory_percent ?? null,
      })
      await queryClient.invalidateQueries()
      navigate('/teams')
    } catch (e) {
      toast.error((e as Error).message || t('setup.saveFailed'))
    } finally {
      setApplying(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{firstRun ? t('setup.titleFirstRun') : t('setup.title')}</h1>
          <p className="text-muted-foreground">{firstRun ? t('setup.descriptionFirstRun') : t('setup.description')}</p>
        </div>
        <PreferencesMenu />
      </div>
      <Card>
        <CardContent className="space-y-6 pt-6">
          <Step n={1} title={t('setup.step1')}>
            <FolderInput
              value={gameDir}
              onChange={(v) => {
                setGameDir(v)
                setCheck(null)
              }}
              placeholder={t('setup.gameDirPlaceholder')}
            />
            <div className="flex items-center gap-3">
              <Button variant="secondary" onClick={() => void runCheck()} disabled={checking || !gameDir.trim()}>
                {checking && <Loader2 className="animate-spin" />} {t('setup.check')}
              </Button>
              {checking && <span className="text-sm text-muted-foreground">{t('setup.checking')}</span>}
            </div>
            {check && <GameCheckResult check={check} />}
            <p className="text-xs text-muted-foreground">{t('setup.cleanOnly')}</p>
          </Step>
          <Step n={2} title={t('settings.facePackDir')}>
            <FacePackFolders value={facePackDirs} onChange={setFacePackDirs} />
            <p className="text-xs text-muted-foreground">{t('setup.facePackHint')}</p>
          </Step>
          <details className="group rounded-md border px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium">{t('setup.advanced')}</summary>
            <div className="mt-3 space-y-3">
              <p className="text-xs text-muted-foreground">{t('setup.advancedHint')}</p>
              <BuildResourcesFields value={build} onChange={(patch) => setBuild({ ...build, ...patch })} />
            </div>
          </details>
        </CardContent>
      </Card>

      <Card className="border-amber-500/50">
        <CardHeader>
          <CardTitle>{t('setup.noticeTitle')}</CardTitle>
          <CardDescription>{t('setup.noticeDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <ul className="list-disc space-y-2 pl-5">
            <li>{rich(t('setup.notice1'))}</li>
            <li>{rich(t('setup.notice2'))}</li>
            <li>{rich(t('setup.notice3'))}</li>
            <li>{t('setup.notice4')}</li>
          </ul>
          <div className="flex items-start gap-2">
            <Checkbox id="accept" checked={accepted} onCheckedChange={(v) => setAccepted(v === true)} />
            <Label htmlFor="accept" className="leading-snug">
              {t('setup.accept')}
            </Label>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        <span className="mr-auto text-xs text-muted-foreground">
          {t('app.version')} {APP_VERSION}
        </span>
        {!firstRun && (
          <Button variant="ghost" onClick={() => navigate('/settings')} disabled={applying}>
            {t('common.cancel')}
          </Button>
        )}
        <Button onClick={() => void apply()} disabled={!canGo} title={canGo ? undefined : t('setup.cannotGo')}>
          {applying && <Loader2 className="animate-spin" />} {t('setup.next')}
        </Button>
      </div>
    </div>
  )
}
