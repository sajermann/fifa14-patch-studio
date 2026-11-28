import { hasMessage, translate } from '@/i18n'
import type { ShareInspect, ShareKind, ShareTree, Adboard, AdboardBody, AdboardList, FormationBody, FormationDetail, FormationList, Equipment, EquipmentBody, EquipmentFiles, EquipmentKind, EquipmentList, BuildProgress, ImportProgress, InstallProgress, BulkKind, BulkDeleteProgress, CacheClearProgress, CacheInfo, Config, CountryDetail, CountryRow, FaceChoice, FacePackCheck, FacePackFolder, FacePage, FieldValue, GameCheck, GameStatus, Job, LeagueDetail, LeagueRow, Limits, MachineInfo, NameTable, Options, Page, PlayerDetail, PlayerOptions, PlayerRow, SetupRequest, Status, StadiumDetail, StadiumRow, TeamDetail, TeamRow, SquadRow, KitConfig, KitFonts, KitPart, KitPrintBody, PreviewLook, ProjectIssue } from './types'

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
  if (!res.ok) throw await errorOf(res)
  return res
}

/** The ApiError of a failed response (its message in the interface language when the app knows its code). */
async function errorOf(res: Response): Promise<ApiError> {
  let detail: unknown = null
  try {
    detail = (await res.json()).detail
  } catch {
    /* not JSON */
  }
  const d = (detail && typeof detail === 'object' ? detail : {}) as { code?: string; detail?: string }
  const key = `apiError.${d.code}`
  const text = d.code && hasMessage(key) ? translate(key) : translate('apiError.status', { status: res.status })
  return new ApiError(res.status, d.code, d.detail ? `${text} (${d.detail})` : text)
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
  /** lineup position (0-27), bench (28) or out of the squad (29); undefined = as it is (a new team: the bench) */
  slot?: number
}

export const api = {
  status: () => get<Status>('/api/status'),
  issues: () => get<{ issues: ProjectIssue[] }>('/api/issues'),
  saveSettings: (fields: Partial<Config>) => request<Config>('PUT', '/api/settings', fields),
  pickFolder: (initial?: string | null, title?: string) => post<{ path: string | null }>('/api/dialog/folder', { initial, title }),

  checkGame: (path: string) => post<GameCheck>('/api/game/check', { path }),
  chooseGame: (path: string) => post<GameStatus>('/api/game', { path }),
  recheckGame: () => post<GameStatus>('/api/game/recheck'),
  setupApply: (body: SetupRequest) => post<{ game: GameStatus; setup: Status['setup'] }>('/api/setup/apply', body),

  leagues: (p: ListParams) => get<Page<LeagueRow>>(`/api/leagues${query(p)}`),
  teams: (p: ListParams) => get<Page<TeamRow>>(`/api/teams${query(p)}`),
  players: (p: ListParams) => get<Page<PlayerRow>>(`/api/players${query(p)}`),
  options: () => get<Options>('/api/options'),
  league: (id: number) => get<LeagueDetail>(`/api/leagues/${id}`),
  stadiums: (p: ListParams) => get<Page<StadiumRow>>(`/api/stadiums${query(p)}`),
  stadium: (id: number) => get<StadiumDetail>(`/api/stadiums/${id}`),
  saveStadium: (id: number, names: NameTable, fields: Fields) => request<StadiumDetail>('PUT', `/api/stadiums/${id}`, { names, fields }),
  resetStadium: (id: number) => request<StadiumDetail>('DELETE', `/api/stadiums/${id}/edits`),
  /** A new stadium: a copy of a game stadium (template) or the scene of a downloaded stadium's folder. */
  createStadium: (body: { names: NameTable; template?: number | null; folder?: string | null }) => post<StadiumDetail>('/api/stadiums', body),
  deleteStadium: (id: number) => request<{ deleted: number }>('DELETE', `/api/stadiums/${id}`),
  /** A created stadium's scene from a downloaded stadium's folder; remove = the template's again. */
  setStadiumScene: (id: number, folder: string) => request<StadiumDetail>('PUT', `/api/stadiums/${id}/scene`, { folder }),
  removeStadiumScene: (id: number) => request<StadiumDetail>('DELETE', `/api/stadiums/${id}/scene`),
  stadiumDefaults: (id: number) => request<{ id: number; name: string | null; values: Record<string, FieldValue> }>('GET', `/api/stadiums/${id}/defaults`),
  setStadiumPicture: (id: number, variant: number, data: string) => request<StadiumDetail>('PUT', `/api/stadiums/${id}/picture/${variant}`, { data }),
  removeStadiumPicture: (id: number, variant: number) => request<StadiumDetail>('DELETE', `/api/stadiums/${id}/picture/${variant}`),
  /** The stadium the team plays in; null = the game's again. */
  setTeamStadium: (id: number, stadium: number | null) => request<TeamDetail>('PUT', `/api/teams/${id}/stadium`, { stadium }),
  adboards: () => get<AdboardList>('/api/adboards'),
  adboard: (id: number) => get<Adboard>(`/api/adboards/${id}`),
  createAdboard: (body: AdboardBody) => post<Adboard>('/api/adboards', body),
  saveAdboard: (id: number, body: AdboardBody) => request<Adboard>('PUT', `/api/adboards/${id}`, body),
  deleteAdboard: (id: number) => request<{ deleted: number }>('DELETE', `/api/adboards/${id}`),
  resetAdboard: (id: number) => request<Adboard>('DELETE', `/api/adboards/${id}/edits`),
  setAdboardHidden: (id: number, hidden: boolean) => request<Adboard>('PUT', `/api/adboards/${id}/hidden`, { hidden }),
  formations: () => get<FormationList>('/api/formations'),
  formation: (id: number) => get<FormationDetail>(`/api/formations/${id}`),
  createFormation: (body: FormationBody) => post<FormationDetail>('/api/formations', body),
  saveFormation: (id: number, body: FormationBody) => request<FormationDetail>('PUT', `/api/formations/${id}`, body),
  deleteFormation: (id: number) => request<{ deleted: number; base: number }>('DELETE', `/api/formations/${id}`),
  setFormationHidden: (id: number, hidden: boolean) => request<FormationDetail>('PUT', `/api/formations/${id}/hidden`, { hidden }),
  setTeamAdboard: (id: number, adboard: number | null) => request<TeamDetail>('PUT', `/api/teams/${id}/adboard`, { adboard }),
  setLeagueAdboard: (id: number, adboard: number | null) => request<LeagueDetail>('PUT', `/api/leagues/${id}/adboard`, { adboard }),
  equipmentList: (kind: EquipmentKind) => get<EquipmentList>(`/api/equipment/${kind}`),
  equipment: (kind: EquipmentKind, code: number) => get<Equipment>(`/api/equipment/${kind}/${code}`),
  createEquipment: (kind: EquipmentKind, body: EquipmentBody) => post<Equipment>(`/api/equipment/${kind}`, body),
  saveEquipment: (kind: EquipmentKind, code: number, body: EquipmentBody) => request<Equipment>('PUT', `/api/equipment/${kind}/${code}`, body),
  setEquipmentFiles: (kind: EquipmentKind, code: number, body: EquipmentFiles) => post<Equipment>(`/api/equipment/${kind}/${code}/files`, body),
  setEquipmentPicture: (kind: EquipmentKind, code: number, data: string) => request<Equipment>('PUT', `/api/equipment/${kind}/${code}/picture`, { data }),
  removeEquipmentPicture: (kind: EquipmentKind, code: number) => request<Equipment>('DELETE', `/api/equipment/${kind}/${code}/picture`),
  deleteEquipment: (kind: EquipmentKind, code: number) => request<Equipment | { deleted: boolean }>('DELETE', `/api/equipment/${kind}/${code}`),
  setEquipmentHidden: (kind: EquipmentKind, code: number, hidden: boolean) => request<Equipment>('PUT', `/api/equipment/${kind}/${code}/hidden`, { hidden }),
  team: (id: number) => get<TeamDetail>(`/api/teams/${id}`),
  saveTeam: (id: number, names: NameTable, fields: Fields) => request<TeamDetail>('PUT', `/api/teams/${id}`, { names, fields }),
  resetTeam: (id: number) => request<TeamDetail>('DELETE', `/api/teams/${id}/edits`),
  createTeam: (body: { names: NameTable; fields?: Fields; template?: number; copy?: boolean; copy_squad?: boolean }) =>
    post<TeamDetail>('/api/teams', body),
  deleteTeam: (id: number) => request<{ deleted: number }>('DELETE', `/api/teams/${id}`),
  saveTeamLeagues: (id: number, leagueIds: number[], hiddenLeagueIds: number[] = []) =>
    request<TeamDetail>('PUT', `/api/teams/${id}/leagues`, { league_ids: leagueIds, hidden_league_ids: hiddenLeagueIds }),
  saveTeamRoster: (id: number, rows: SquadRow[] | null) => request<TeamDetail>('PUT', `/api/teams/${id}/roster`, { rows }),
  uploadTeamCrest: (id: number, data: string) => request<TeamDetail>('PUT', `/api/teams/${id}/crest`, { data }),
  removeTeamCrest: (id: number) => request<TeamDetail>('DELETE', `/api/teams/${id}/crest`),
  saveTeamKit: (id: number, kind: number, config: KitConfig | null, pictures: Partial<Record<KitPart, string | null>>) =>
    request<TeamDetail>('PUT', `/api/teams/${id}/kits/${kind}`, { config, pictures }),
  kitModels: () => get<{ models: number[] }>('/api/kit-models'),
  kitFonts: () => get<KitFonts>('/api/kit-fonts'),
  saveLeague: (id: number, names: NameTable, fields: Fields) => request<LeagueDetail>('PUT', `/api/leagues/${id}`, { names, fields }),
  resetLeague: (id: number) => request<LeagueDetail>('DELETE', `/api/leagues/${id}/edits`),
  createLeague: (names: NameTable, fields: Fields, template?: number, copyTeams = false) =>
    post<LeagueDetail>('/api/leagues', { names, fields, template, copy_teams: copyTeams }),
  deleteLeague: (id: number) => request<{ deleted: number }>('DELETE', `/api/leagues/${id}`),
  saveLeagueTeams: (id: number, teamIds: number[], hiddenTeamIds: number[] = []) =>
    request<LeagueDetail>('PUT', `/api/leagues/${id}/teams`, { team_ids: teamIds, hidden_team_ids: hiddenTeamIds }),
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
  setStadiumHidden: (id: number, hidden: boolean) => request<StadiumDetail>('PUT', `/api/stadiums/${id}/hidden`, { hidden }),
  countries: (p: ListParams) => get<Page<CountryRow>>(`/api/countries${query(p)}`),
  country: (id: number) => get<CountryDetail>(`/api/countries/${id}`),
  createCountry: (names: NameTable, fields: Fields = {}, template?: number) => post<CountryDetail>('/api/countries', { names, fields, template }),
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
  /** Deletes the picked items of a list: a created one leaves the project, an edited one goes back to the game's. */
  bulkDelete: (kind: BulkKind, ids: number[]) =>
    post<{ deleted: number[]; reset: number[]; skipped: { id: number; code: string }[]; cancelled?: boolean }>('/api/bulk-delete', { kind, ids }),
  bulkDeleteProgress: () => get<BulkDeleteProgress>('/api/bulk-delete/progress'),
  /** Stops the running bulk delete before the next item: what was already deleted stays deleted. */
  cancelBulkDelete: () => post<{ stopping: boolean }>('/api/bulk-delete/cancel'),
  cacheInfo: () => get<CacheInfo>('/api/cache'),
  /** Deletes the parts of the cache the app makes again; answers when it ends (progress: cacheClearProgress). */
  clearCache: () => post<{ files: number; bytes: number; failed: number }>('/api/cache/clear'),
  cacheClearProgress: () => get<CacheClearProgress>('/api/cache/progress'),
  limits: () => get<Limits>('/api/limits'),
  player: (id: number) => get<PlayerDetail>(`/api/players/${id}`),
  /** The whole form of a player: fields (face included) and, when given, his teams. */
  savePlayer: (id: number, fields: Fields, teams?: PlayerTeamBody[]) => request<PlayerDetail>('PUT', `/api/players/${id}`, { fields, teams }),
  resetPlayer: (id: number) => request<PlayerDetail>('DELETE', `/api/players/${id}/edits`),
  /** A new player: from scratch (template null) or a copy of a player; optionally straight into a team. */
  /** New random players for a team, one per position code given (in that order). */
  generatePlayers: (team: number, positions: number[]) => post<PlayerDetail[]>(`/api/teams/${team}/generate-players`, { positions }),
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
  /** What each face folder being typed in the Settings has (not saved yet). */
  checkFacePacks: (folders: string[]) => post<{ packs: FacePackCheck[] }>('/api/facepacks/check', { folders }),
  /** Plain-text support report: machine, settings, game, project, patch and the end of the log files. */
  logsReport: () => send('GET', '/api/logs/report').then((r) => r.text()),
  openLogs: () => post<{ folder: string }>('/api/logs/open'),
  /** One page of the faces of the packs (all, one pack, or only a folder opened on the picker for this visit). */
  facePage: (p: { offset: number; limit: number; q?: string; pack?: string; folder?: string }) => get<FacePage>(`/api/facepack/page${query(p)}`),

  /** Cores and memory of this machine and the build's defaults (f14mod.workers). */
  machine: () => get<MachineInfo>('/api/machine'),
  buildPatch: () => post<Job>('/api/patch/build'),
  buildProgress: () => get<BuildProgress>('/api/patch/progress'),
  /** Asks the running build to stop; what was made stays in the build cache. */
  cancelBuild: () => post<{ stopping: boolean }>('/api/patch/build/cancel'),
  installPatch: () => post<Job>('/api/patch/install'),
  uninstallPatch: () => post<Job>('/api/patch/uninstall'),
  installProgress: () => get<InstallProgress>('/api/patch/install/progress'),
  openPatchFolder: () => post<{ path: string }>('/api/patch/open-folder'),

  /** Import: sends the zip (the app's or an extractor package); the tree of what it holds and the id each item gets. */
  /** onSent: bytes sent so far (the upload; once all is sent the backend reads it). signal: stops it (AbortError). */
  shareInspect: (file: File, opts: { onSent?: (sent: number, total: number) => void; signal?: AbortSignal } = {}) =>
    new Promise<ShareInspect>((resolve, reject) => {
      // XMLHttpRequest and not fetch: only it tells how much of the file was sent
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/share/inspect')
      xhr.setRequestHeader('Content-Type', 'application/zip')
      xhr.upload.onprogress = (e) => opts.onSent?.(e.loaded, e.lengthComputable ? e.total : file.size)
      xhr.onload = () => {
        const res = new Response(xhr.responseText, { status: xhr.status, headers: { 'Content-Type': 'application/json' } })
        if (res.ok) res.json().then((v) => resolve(v as ShareInspect), reject)
        else errorOf(res).then(reject, reject)
      }
      xhr.onerror = () => reject(new ApiError(0, 'backend_unreachable', translate('apiError.backend_unreachable')))
      xhr.onabort = () => reject(new DOMException('aborted', 'AbortError'))
      if (opts.signal?.aborted) return reject(new DOMException('aborted', 'AbortError'))
      opts.signal?.addEventListener('abort', () => xhr.abort(), { once: true })
      xhr.send(file)
    }),
  /** Starts the import of the chosen items (a job: importProgress says where it is). */
  /** asNew: items that would update what came in from the same origin before and come in as new items instead */
  shareApply: (token: string, keys: string[], fillMissing = true, asNew: string[] = []) => post<Job>('/api/share/apply', { token, keys, fill_missing: fillMissing, as_new: asNew }),
  importProgress: () => get<ImportProgress>('/api/share/apply/progress'),
  /** Asks the running import to stop: nothing it wrote stays. */
  cancelImport: () => post<{ stopping: boolean }>('/api/share/apply/cancel'),
  shareForget: (token: string) => request<{ forgotten: boolean }>('DELETE', `/api/share/${token}`),
  /** Export: the tree of what an export of this item takes (what the project created or changed). */
  shareExport: (kind: ShareKind, id: number) => post<ShareTree>('/api/share/export', { kind, id }),
  /** The zip of the chosen items of an export. */
  shareExportZip: async (token: string, keys: string[]) => {
    const res = await send('POST', `/api/share/export/${token}/zip`, { keys })
    const name = /filename="?([^";]+)"?/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'export.zip'
    return { name: decodeURIComponent(name), blob: await res.blob() }
  },
}

/** The picture of an item of an inspected zip or of an export. */
export const sharePictureUrl = (token: string, key: string) => `/api/share/${token}/picture${query({ key })}`

/** Saves a downloaded file (blob) with its name. */
export function saveBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
