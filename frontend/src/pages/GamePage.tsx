import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FolderOpen, Loader2, RefreshCw, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { api } from '@/api/client'
import type { GameCheck } from '@/api/types'
import { Section } from '@/components/common/detail'
import { hasMessage, useI18n, type MessageKey } from '@/i18n'
import { useStatus } from '@/state/queries'

/** The result of checking a folder: is it a FIFA 14 the app can patch, and what is wrong when it is not. */
function CheckResult({ check }: { check: GameCheck }) {
  const { t } = useI18n()
  const ok = check.state === 'clean' || check.state === 'patched'
  const Icon = ok ? CheckCircle2 : check.state === 'modified' ? AlertTriangle : XCircle
  return (
    <div className="space-y-2 rounded-md border p-3 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <Icon className={ok ? 'size-4 text-emerald-600' : check.state === 'modified' ? 'size-4 text-amber-600' : 'size-4 text-red-600'} />
        {t(`check.state.${check.state}` as MessageKey)}
      </p>
      {check.game_dir && <p className="font-mono text-xs text-muted-foreground">{check.game_dir}</p>}
      {check.installed && <p className="text-xs text-muted-foreground">{t('check.installedAt', { date: check.installed.installed_at, version: check.installed.version || '?' })}</p>}
      {check.issues.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs">
          {check.issues.map((i, n) => {
            const key = `check.issue.${i.code}`
            return (
              <li key={n}>
                {hasMessage(key) ? t(key) : i.code}
                {i.detail && <span className="ml-1 font-mono text-muted-foreground">{i.detail}</span>}
              </li>
            )
          })}
        </ul>
      )}
      {check.state === 'modified' && <p className="text-xs text-muted-foreground">{t('check.modifiedHint')}</p>}
    </div>
  )
}

export function GamePage() {
  const { t } = useI18n()
  const status = useStatus().data
  const qc = useQueryClient()
  const navigate = useNavigate()
  const game = status?.game
  const [path, setPath] = useState('')
  const [checked, setChecked] = useState<GameCheck | null>(null)
  const check = useMutation({
    mutationFn: (p: string) => api.checkGame(p),
    onSuccess: setChecked,
    onError: (e: Error) => toast.error(e.message),
  })
  const choose = useMutation({
    mutationFn: (p: string) => api.chooseGame(p),
    onSuccess: async () => {
      setChecked(null)
      setPath('')
      await qc.invalidateQueries()
      navigate('/teams')
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const recheck = useMutation({
    mutationFn: api.recheckGame,
    onSuccess: () => qc.invalidateQueries(),
    onError: (e: Error) => toast.error(e.message),
  })
  const browse = async () => {
    try {
      const r = await api.pickFolder(path || status?.config.game_dir, t('game.pickTitle'))
      if (r.path) {
        setPath(r.path)
        check.mutate(r.path)
      }
    } catch (e) {
      toast.error((e as Error).message)
    }
  }
  const usable = checked && (checked.state === 'clean' || checked.state === 'patched')
  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{t('game.title')}</h1>
        <p className="text-sm text-muted-foreground">{t('game.subtitle')}</p>
      </div>

      {game && game.state !== 'empty' && (
        <Section
          title={t('game.current')}
          action={
            <Button variant="outline" size="sm" disabled={game.state === 'building' || recheck.isPending} onClick={() => recheck.mutate()}>
              <RefreshCw /> {t('game.recheck')}
            </Button>
          }
        >
          {game.state === 'building' && (
            <p className="mb-3 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> {t('game.preparing', { percent: Math.round(game.progress.done * 100) })}
            </p>
          )}
          {game.state === 'error' && <p className="mb-3 text-sm text-red-600">{game.error}</p>}
          {game.check && <CheckResult check={game.check} />}
        </Section>
      )}

      <Section title={game?.game_dir ? t('game.change') : t('game.choose')}>
        <div className="flex flex-wrap gap-2">
          <Input
            value={path}
            onChange={(e) => {
              setPath(e.target.value)
              setChecked(null)
            }}
            placeholder={t('game.placeholder')}
            className="min-w-72 flex-1"
          />
          <Button variant="outline" onClick={browse}>
            <FolderOpen /> {t('game.browse')}
          </Button>
          <Button variant="outline" disabled={!path.trim() || check.isPending} onClick={() => check.mutate(path.trim())}>
            {t('game.check')}
          </Button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{t('game.cleanOnly')}</p>
        {checked && (
          <div className="mt-4 space-y-3">
            <CheckResult check={checked} />
            <Button disabled={!usable || choose.isPending} onClick={() => choose.mutate(path.trim())}>
              {t('game.use')}
            </Button>
          </div>
        )}
      </Section>
    </div>
  )
}
