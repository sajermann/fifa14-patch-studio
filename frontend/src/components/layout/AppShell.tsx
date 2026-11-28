import { AlertTriangle, FileDown, Flag, Footprints, Hammer, Hand, Heart, Landmark, LayoutGrid, Loader2, Megaphone, Settings, Shield, Trophy, Users, Volleyball } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useI18n, type MessageKey } from '@/i18n'
import { APP_NAME, APP_VERSION, AUTHOR_GITHUB, AUTHOR_NAME, DONATE_URL, REPO_URL } from '@/lib/about'
import { cn } from '@/lib/utils'
import { useStatus } from '@/state/queries'
import { LoadingBlock } from './LoadingBlock'
import { JobWatcher, PatchActions } from './PatchActions'
import { PreferencesMenu } from './PreferencesMenu'

// kind: the project's entities of the menu (status.project: <kind> = edited from the game, new_<kind> = created)
const NAV: { to: string; label: MessageKey; icon: typeof Trophy; kind: string }[] = [
  { to: '/countries', label: 'nav.countries', icon: Flag, kind: 'country' },
  { to: '/leagues', label: 'nav.leagues', icon: Trophy, kind: 'league' },
  { to: '/teams', label: 'nav.teams', icon: Shield, kind: 'team' },
  { to: '/players', label: 'nav.players', icon: Users, kind: 'player' },
  { to: '/stadiums', label: 'nav.stadiums', icon: Landmark, kind: 'stadium' },
  { to: '/formations', label: 'nav.formations', icon: LayoutGrid, kind: 'formation' },
  { to: '/adboards', label: 'nav.adboards', icon: Megaphone, kind: 'adboard' },
  { to: '/boots', label: 'nav.boots', icon: Footprints, kind: 'boot' },
  { to: '/gloves', label: 'nav.gloves', icon: Hand, kind: 'glove' },
  { to: '/balls', label: 'nav.balls', icon: Volleyball, kind: 'ball' },
]

function NavItem({ to, label, icon: Icon, extra }: { to: string; label: MessageKey; icon: typeof Trophy; extra?: React.ReactNode }) {
  const { t } = useI18n()
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn('flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent', isActive && 'bg-accent font-medium')
      }
    >
      <Icon className="size-4" />
      <span className="flex-1">{t(label)}</span>
      {extra}
    </NavLink>
  )
}

function GithubMark() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" fill="currentColor" className="size-4">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

/** Pages that need the game ready: they show it being prepared, or what went wrong reading it. */
export function RequireGame() {
  const { t } = useI18n()
  const game = useStatus().data?.game
  if (!game) return <LoadingBlock />
  if (game.state === 'building')
    return (
      <div className="flex items-center gap-2 py-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> {t('game.preparing', { percent: Math.round(game.progress.done * 100) })}
      </div>
    )
  if (game.state !== 'ready')
    return (
      <div className="space-y-3 py-10 text-sm">
        {game.error && <p className="text-destructive">{game.error}</p>}
        <Button variant="outline" asChild>
          <NavLink to="/setup">{t('settings.changeFolders')}</NavLink>
        </Button>
      </div>
    )
  return <Outlet />
}

export function AppShell() {
  const { t } = useI18n()
  const status = useStatus().data
  const { pathname } = useLocation()
  const game = status?.game
  const project = status?.project ?? {}
  const edited = Object.values(project).reduce((a, b) => a + (b ?? 0), 0)
  // how many of each the project has, created or edited (the Street Studio's menu counts)
  const countOf = (kind: string) => (project[kind] ?? 0) + (project[`new_${kind}`] ?? 0)
  const check = game?.check
  const warning =
    check?.state === 'modified' || check?.state === 'invalid'
      ? t('header.gameChanged')
      : check?.issues.some((i) => i.code === 'patch_changed')
        ? t('header.patchChanged')
        : null
  return (
    <div className="flex h-svh overflow-hidden">
      <aside className="flex w-56 shrink-0 flex-col overflow-y-auto border-r bg-muted/30 p-3">
        <div className="mb-6 flex items-center gap-2 px-3 pt-2">
          <img src="/favicon.png" alt="" className="size-7" />
          <div>
            <p className="text-sm font-semibold leading-tight">{APP_NAME}</p>
            <p className="text-xs text-muted-foreground">{t('app.subtitle')}</p>
          </div>
        </div>
        <nav className="space-y-1">
          {NAV.map(({ kind, ...n }) => (
            <NavItem
              key={n.to}
              {...n}
              extra={countOf(kind) > 0 ? <span className="text-xs text-muted-foreground tabular-nums">{countOf(kind)}</span> : undefined}
            />
          ))}
          <div className="my-2 border-t" />
          <NavItem to="/import" label="nav.import" icon={FileDown} />
          <NavItem
            to="/patch"
            label="nav.patch"
            icon={Hammer}
            extra={edited > 0 ? <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums">{edited}</span> : undefined}
          />
        </nav>
        <div className="mt-auto space-y-2">
          <NavItem to="/settings" label="nav.settings" icon={Settings} />
          <div className="px-1">
            <PreferencesMenu />
          </div>
          <div className="space-y-0.5 px-3 pt-2 text-xs text-muted-foreground">
            <p className="flex items-center justify-between gap-2">
              <span>
                {t('app.credits')}{' '}
                <a href={AUTHOR_GITHUB} target="_blank" rel="noreferrer" className="underline-offset-2 hover:text-foreground hover:underline">
                  {AUTHOR_NAME}
                </a>
              </span>
              <Button variant="ghost" size="icon-sm" asChild>
                <a href={REPO_URL} target="_blank" rel="noreferrer" title={t('app.sourceCode')} aria-label={t('app.sourceCode')}>
                  <GithubMark />
                </a>
              </Button>
            </p>
            <p>
              {t('app.version')} {APP_VERSION}
            </p>
            <Button variant="outline" size="sm" className="mt-2 w-full" asChild>
              <a href={DONATE_URL} target="_blank" rel="noreferrer">
                <Heart className="text-rose-500" /> {t('app.donate')}
              </a>
            </Button>
          </div>
        </div>
      </aside>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="z-10 flex shrink-0 items-center gap-2 border-b bg-background/95 px-6 py-3 backdrop-blur">
          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
            {game?.state === 'ready' ? (
              <>
                <span className="font-medium text-foreground">{t('header.game')}</span> <span className="font-mono text-xs">{game.game_dir}</span>
                {game.check?.state === 'patched' && (
                  <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-700 dark:text-emerald-300">
                    {t('header.patchInstalled')}
                  </span>
                )}
              </>
            ) : game?.state === 'building' ? (
              t('game.preparing', {
                percent: Math.round(game.progress.done * 100),
              })
            ) : (
              t('header.noGame')
            )}
          </span>
          <PatchActions />
        </header>
        {warning && (
          <div className="space-y-1 border-b border-amber-500/40 bg-amber-500/10 px-6 py-2 text-sm text-amber-800 dark:text-amber-300">
            <p className="flex items-center gap-2">
              <AlertTriangle className="size-4 shrink-0" /> {warning}
            </p>
          </div>
        )}
        <JobWatcher />
        <main key={pathname.split('/')[1]} className="min-h-0 flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
