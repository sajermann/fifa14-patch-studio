import { hasMessage, translate } from '@/i18n'
import type { Config, CountryDetail, CountryRow, FieldValue, GameCheck, GameStatus, Job, LeagueDetail, LeagueRow, Limits, NameTable, Options, Page, PlayerDetail, PlayerRow, Status, TeamDetail, TeamRow } from './types'

/** Error of the backend; `message` is in the interface language when the app knows its code. */
export class ApiError extends Error {
  status: number
  code?: string
  constructor(status: number, code: string | undefined, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'backend_unreachable', translate('apiError.backend_unreachable'))
  }
  if (!res.ok) {
    let detail: unknown = null
    try {
      detail = (await res.json()).detail
    } catch {
      /* not JSON */
    }
    const d = (detail && typeof detail === 'object' ? detail : {}) as { code?: string; detail?: string }
    const key = `apiError.${d.code}`
    const text = d.code && hasMessage(key) ? translate(key) : translate('apiError.status', { status: res.status })
    throw new ApiError(res.status, d.code, d.detail ? `${text} (${d.detail})` : text)
  }
  return (await res.json()) as T
}

const get = <T>(url: string) => request<T>('GET', url)
const post = <T>(url: string, body: unknown = {}) => request<T>('POST', url, body)

/** Query string of the set values only. */
export function query(params: Record<string, string | number | boolean | null | undefined>) {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

type Fields = Record<string, FieldValue>

export type ListParams = Record<string, string | number | undefined>

export const api = {
  status: () => get<Status>('/api/status'),
  saveSettings: (fields: Partial<Config>) => request<Config>('PUT', '/api/settings', fields),
  pickFolder: (initial?: string | null, title?: string) => post<{ path: string | null }>('/api/dialog/folder', { initial, title }),

  checkGame: (path: string) => post<GameCheck>('/api/game/check', { path }),
  chooseGame: (path: string) => post<GameStatus>('/api/game', { path }),
  recheckGame: () => post<GameStatus>('/api/game/recheck'),

  leagues: (p: ListParams) => get<Page<LeagueRow>>(`/api/leagues${query(p)}`),
  teams: (p: ListParams) => get<Page<TeamRow>>(`/api/teams${query(p)}`),
  players: (p: ListParams) => get<Page<PlayerRow>>(`/api/players${query(p)}`),
  options: () => get<Options>('/api/options'),
  league: (id: number) => get<LeagueDetail>(`/api/leagues/${id}`),
  team: (id: number) => get<TeamDetail>(`/api/teams/${id}`),
  saveTeam: (id: number, names: NameTable, fields: Fields) => request<TeamDetail>('PUT', `/api/teams/${id}`, { names, fields }),
  resetTeam: (id: number) => request<TeamDetail>('DELETE', `/api/teams/${id}/edits`),
  saveLeague: (id: number, names: NameTable, fields: Fields) => request<LeagueDetail>('PUT', `/api/leagues/${id}`, { names, fields }),
  resetLeague: (id: number) => request<LeagueDetail>('DELETE', `/api/leagues/${id}/edits`),
  createLeague: (names: NameTable, fields: Fields) => post<LeagueDetail>('/api/leagues', { names, fields }),
  deleteLeague: (id: number) => request<{ deleted: number }>('DELETE', `/api/leagues/${id}`),
  saveLeagueTeams: (id: number, teamIds: number[]) => request<LeagueDetail>('PUT', `/api/leagues/${id}/teams`, { team_ids: teamIds }),
  resetLeagueTeams: (id: number) => request<LeagueDetail>('DELETE', `/api/leagues/${id}/teams`),
  countries: (p: ListParams) => get<Page<CountryRow>>(`/api/countries${query(p)}`),
  country: (id: number) => get<CountryDetail>(`/api/countries/${id}`),
  createCountry: (names: NameTable, fields: Fields = {}) => post<CountryDetail>('/api/countries', { names, fields }),
  saveCountry: (id: number, names: NameTable, fields: Fields) => request<CountryDetail>('PUT', `/api/countries/${id}`, { names, fields }),
  resetCountry: (id: number) => request<CountryDetail>('DELETE', `/api/countries/${id}/edits`),
  deleteCountry: (id: number) => request<{ deleted: number }>('DELETE', `/api/countries/${id}`),
  limits: () => get<Limits>('/api/limits'),
  player: (id: number) => get<PlayerDetail>(`/api/players/${id}`),
  savePlayer: (id: number, fields: Fields) => request<PlayerDetail>('PUT', `/api/players/${id}`, { fields }),
  resetPlayer: (id: number) => request<PlayerDetail>('DELETE', `/api/players/${id}/edits`),

  buildPatch: () => post<Job>('/api/patch/build'),
  installPatch: () => post<Job>('/api/patch/install'),
  uninstallPatch: () => post<Job>('/api/patch/uninstall'),
  openPatchFolder: () => post<{ path: string }>('/api/patch/open-folder'),
}
