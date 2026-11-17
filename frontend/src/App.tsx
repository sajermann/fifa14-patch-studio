import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { api } from '@/api/client'
import { AppShell, RequireGame } from '@/components/layout/AppShell'
import { I18nProvider, useI18n } from '@/i18n'
import { ThemeProvider } from '@/lib/theme'
import { CountriesPage } from '@/pages/CountriesPage'
import { CountryPage } from '@/pages/CountryPage'
import { GamePage } from '@/pages/GamePage'
import { LeaguePage } from '@/pages/LeaguePage'
import { LeaguesPage } from '@/pages/LeaguesPage'
import { PatchPage } from '@/pages/PatchPage'
import { PlayerPage } from '@/pages/PlayerPage'
import { PlayersPage } from '@/pages/PlayersPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { TeamPage } from '@/pages/TeamPage'
import { TeamsPage } from '@/pages/TeamsPage'
import { useStatus } from '@/state/queries'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } })

/** The interface language saved in the backend wins when the app opens; the first choice is saved there. */
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
  return null
}

function Home() {
  const game = useStatus().data?.game
  if (!game) return null
  return <Navigate to={game.state === 'ready' || game.state === 'building' ? '/teams' : '/game'} replace />
}

// a data router: the edit screens can hold the user back when there are unsaved changes (useBlocker)
const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },
      { path: 'game', element: <GamePage /> },
      { path: 'settings', element: <SettingsPage /> },
      {
        element: <RequireGame />,
        children: [
          { path: 'countries', element: <CountriesPage /> },
          { path: 'countries/:id', element: <CountryPage /> },
          { path: 'leagues', element: <LeaguesPage /> },
          { path: 'leagues/:id', element: <LeaguePage /> },
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
