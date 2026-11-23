import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Navigate, Outlet, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import { AppShell, RequireGame } from '@/components/layout/AppShell'
import { LoadingBlock } from '@/components/layout/LoadingBlock'
import { I18nProvider, onLanguageChange, useI18n } from '@/i18n'
import { ThemeProvider } from '@/lib/theme'
import { CountriesPage } from '@/pages/CountriesPage'
import { CountryPage } from '@/pages/CountryPage'
import { LeaguePage } from '@/pages/LeaguePage'
import { StadiumPage } from '@/pages/StadiumPage'
import { StadiumsPage } from '@/pages/StadiumsPage'
import { LeaguesPage } from '@/pages/LeaguesPage'
import { PatchPage } from '@/pages/PatchPage'
import { PlayerPage } from '@/pages/PlayerPage'
import { PlayersPage } from '@/pages/PlayersPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { SetupPage } from '@/pages/SetupPage'
import { TeamPage } from '@/pages/TeamPage'
import { TeamsPage } from '@/pages/TeamsPage'
import { useStatus } from '@/state/queries'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } })

/** The interface language saved in the backend wins when the app opens; the first choice is saved there, and so is
 * every switch (sidebar menu or Settings): the names shown follow it (the names language defaults to the interface's),
 * so everything is fetched again. */
function LanguageSync() {
  const { lang, setLang } = useI18n()
  const config = useStatus().data?.config
  const applied = useRef(false)
  useEffect(() => {
    if (!config || applied.current) return
    applied.current = true
    if (config.language && config.language !== lang) setLang(config.language)
    else if (!config.language) void api.saveSettings({ language: lang }).then(() => queryClient.invalidateQueries()).catch(() => undefined)
  }, [config, lang, setLang])
  useEffect(
    () =>
      onLanguageChange((next) => {
        void api
          .saveSettings({ language: next })
          .then(() => queryClient.invalidateQueries())
          .catch(() => undefined)
      }),
    [],
  )
  return null
}

/** First run (no usable game, or the notice not accepted): nothing else opens before the setup screen. */
function Gate() {
  const { data: status } = useStatus()
  if (!status)
    return (
      <div className="p-8">
        <LoadingBlock />
      </div>
    )
  if (status.setup.required) return <SetupPage status={status} />
  return <Outlet />
}

/** The setup screen opened from the Settings (to change the game folder). */
function SetupRoute() {
  const status = useStatus().data
  return status ? <SetupPage status={status} /> : null
}

// a data router: the edit screens can hold the user back when there are unsaved changes (useBlocker)
const router = createBrowserRouter([
  {
    element: <Gate />,
    children: [
      { path: 'setup', element: <SetupRoute /> },
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/teams" replace /> },
          { path: 'settings', element: <SettingsPage /> },
      {
        element: <RequireGame />,
        children: [
          { path: 'countries', element: <CountriesPage /> },
          { path: 'countries/:id', element: <CountryPage /> },
          { path: 'leagues', element: <LeaguesPage /> },
          { path: 'leagues/:id', element: <LeaguePage /> },
          { path: 'stadiums', element: <StadiumsPage /> },
          { path: 'stadiums/:id', element: <StadiumPage /> },
          { path: 'teams', element: <TeamsPage /> },
          { path: 'teams/:id', element: <TeamPage /> },
          { path: 'players', element: <PlayersPage /> },
          { path: 'players/:id', element: <PlayerPage /> },
          { path: 'patch', element: <PatchPage /> },
            ],
          },
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
])

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <LanguageSync />
            <RouterProvider router={router} />
            <Toaster richColors position="bottom-right" />
          </TooltipProvider>
        </QueryClientProvider>
      </I18nProvider>
    </ThemeProvider>
  )
}
