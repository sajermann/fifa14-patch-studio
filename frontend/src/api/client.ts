import { hasMessage, translate } from '@/i18n'
import type { Config, CountryDetail, CountryRow, FaceChoice, FacePackFolder, FacePage, FieldValue, GameCheck, GameStatus, Job, LeagueDetail, LeagueRow, Limits, NameTable, Options, Page, PlayerDetail, PlayerOptions, PlayerRow, Status, TeamDetail, TeamRow, SquadRow, KitConfig, KitFonts, KitPart, KitPrintBody, PreviewLook } from './types'

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
  return (await send(method, url, body)).json() as Promise<T>
}

/** The response of a call, a failed one turned into an ApiError. */
async function send(method: string, url: string, body?: unknown): Promise<Response> {
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
  return res
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

/** A team of a player as his screen keeps it (number and whether he is hidden in it). */
export interface PlayerTeamBody {
  team: number
  jersey: number | null
  hidden: boolean
}

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
  createTeam: (body: { names: NameTable; fields?: Fields; template?: number; copy?: boolean; copy_squad?: boolean }) =>
    post<TeamDetail>('/api/teams', body),
  deleteTeam: (id: number) => request<{ deleted: number }>('DELETE', `/api/teams/${id}`),
  saveTeamRoster: (id: number, rows: SquadRow[] | null) => request<TeamDetail>('PUT', `/api/teams/${id}/roster`, { rows }),
  uploadTeamCrest: (id: number, data: string) => request<TeamDetail>('PUT', `/api/teams/${id}/crest`, { data }),
  removeTeamCrest: (id: number) => request<TeamDetail>('DELETE', `/api/teams/${id}/crest`),
  saveTeamKit: (id: number, kind: number, config: KitConfig | null, pictures: Partial<Record<KitPart, string | null>>) =>
    request<TeamDetail>('PUT', `/api/teams/${id}/kits/${kind}`, { config, pictures }),
  kitModels: () => get<{ models: number[] }>('/api/kit-models'),
  kitFonts: () => get<KitFonts>('/api/kit-fonts'),
  saveLeague: (id: number, names: NameTable, fields: Fields) => request<LeagueDetail>('PUT', `/api/leagues/${id}`, { names, fields }),
  resetLeague: (id: number) => request<LeagueDetail>('DELETE', `/api/leagues/${id}/edits`),
  createLeague: (names: NameTable, fields: Fields) => post<LeagueDetail>('/api/leagues', { names, fields }),
  deleteLeague: (id: number) => request<{ deleted: number }>('DELETE', `/api/leagues/${id}`),
  saveLeagueTeams: (id: number, teamIds: number[]) => request<LeagueDetail>('PUT', `/api/leagues/${id}/teams`, { team_ids: teamIds }),
  resetLeagueTeams: (id: number) => request<LeagueDetail>('DELETE', `/api/leagues/${id}/teams`),
  uploadLeagueLogo: (id: number, data: string) => request<LeagueDetail>('PUT', `/api/leagues/${id}/logo`, { data }),
  removeLeagueLogo: (id: number) => request<LeagueDetail>('DELETE', `/api/leagues/${id}/logo`),
  /** A chosen picture fitted as the league's logo, not saved yet. */
  leagueLogoPreview: async (data: string, size: number) => (await send('POST', `/api/league-logo-preview?size=${size}`, { data })).blob(),
  /** The Hide button: a created item hidden is out of the patch, an original one is hidden in the game. */
  setLeagueHidden: (id: number, hidden: boolean) => request<LeagueDetail>('PUT', `/api/leagues/${id}/hidden`, { hidden }),
  setCountryHidden: (id: number, hidden: boolean) => request<CountryDetail>('PUT', `/api/countries/${id}/hidden`, { hidden }),
  /** The whole list of leagues shown in a country. */
  saveCountryLeagues: (id: number, leagueIds: number[], hiddenLeagueIds: number[]) =>
    request<CountryDetail>('PUT', `/api/countries/${id}/leagues`, { league_ids: leagueIds, hidden_league_ids: hiddenLeagueIds }),
  setTeamHidden: (id: number, hidden: boolean) => request<TeamDetail>('PUT', `/api/teams/${id}/hidden`, { hidden }),
  countries: (p: ListParams) => get<Page<CountryRow>>(`/api/countries${query(p)}`),
  country: (id: number) => get<CountryDetail>(`/api/countries/${id}`),
  createCountry: (names: NameTable, fields: Fields = {}) => post<CountryDetail>('/api/countries', { names, fields }),
  saveCountry: (id: number, names: NameTable, fields: Fields) => request<CountryDetail>('PUT', `/api/countries/${id}`, { names, fields }),
  uploadCountryFlag: (id: number, data: string) => request<CountryDetail>('PUT', `/api/countries/${id}/flag`, { data }),
  removeCountryFlag: (id: number) => request<CountryDetail>('DELETE', `/api/countries/${id}/flag`),
  /** A chosen picture drawn as the flag, not saved yet. */
  /** How the kit preview dresses a player (0 or unknown = the model). */
  previewLook: (pid: number) => get<PreviewLook>(`/api/preview/look/${pid}`),
  /** The crest/name/numbers layer of the kit preview with a crest not saved yet. */
  kitPrintPreview: async (tid: number, kind: number, body: KitPrintBody) => (await send('POST', `/api/preview/kit-print/${tid}/${kind}.png`, body)).blob(),
  flagPreview: async (data: string, size: number) => (await send('POST', `/api/flag-preview?size=${size}`, { data })).blob(),
  resetCountry: (id: number) => request<CountryDetail>('DELETE', `/api/countries/${id}/edits`),
  deleteCountry: (id: number) => request<{ deleted: number }>('DELETE', `/api/countries/${id}`),
  limits: () => get<Limits>('/api/limits'),
  player: (id: number) => get<PlayerDetail>(`/api/players/${id}`),
  /** The whole form of a player: fields (face included) and, when given, his teams. */
  savePlayer: (id: number, fields: Fields, teams?: PlayerTeamBody[]) => request<PlayerDetail>('PUT', `/api/players/${id}`, { fields, teams }),
  resetPlayer: (id: number) => request<PlayerDetail>('DELETE', `/api/players/${id}/edits`),
  /** A new player: from scratch (template null) or a copy of a player; optionally straight into a team. */
  generatePlayers: (team: number, count: number, goalkeepers = 0) => post<PlayerDetail[]>(`/api/teams/${team}/generate-players`, { count, goalkeepers }),
  createPlayer: (body: { fields: Fields; template?: number | null; team?: number | null }) => post<PlayerDetail>('/api/players', body),
  deletePlayer: (id: number) => request<{ deleted: number }>('DELETE', `/api/players/${id}`),
  setPlayerHidden: (id: number, hidden: boolean) => request<PlayerDetail>('PUT', `/api/players/${id}/hidden`, { hidden }),
  uploadPlayerPhoto: (id: number, data: string) => request<PlayerDetail>('PUT', `/api/players/${id}/photo`, { data }),
  /** The photo a pack ships with a face. */
  playerPhotoFromPack: (id: number, pack: string, face: number) => request<PlayerDetail>('PUT', `/api/players/${id}/photo`, { pack, face }),
  removePlayerPhoto: (id: number) => request<PlayerDetail>('DELETE', `/api/players/${id}/photo`),
  playerOptions: () => get<PlayerOptions>('/api/player-options'),
  /** How the 3D preview dresses a player with the values of his screen (saved or not). */
  playerLook: (id: number, values: Record<string, FieldValue>, face: FaceChoice | null) => post<PreviewLook>(`/api/preview/player-look/${id}`, { values, face }),
  facePacks: () => get<FacePackFolder[]>('/api/facepacks'),
  /** One page of the faces of the packs (all, one pack, or only a folder opened on the picker for this visit). */
  facePage: (p: { offset: number; limit: number; q?: string; pack?: string; folder?: string }) => get<FacePage>(`/api/facepack/page${query(p)}`),

  buildPatch: () => post<Job>('/api/patch/build'),
  installPatch: () => post<Job>('/api/patch/install'),
  uninstallPatch: () => post<Job>('/api/patch/uninstall'),
  openPatchFolder: () => post<{ path: string }>('/api/patch/open-folder'),
}
