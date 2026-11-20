// What the backend sends (backend/f14api). Field names follow the API.

export type Raw = Record<string, string | number | null>

export interface Config {
  language: 'pt-BR' | 'en' | null
  game_dir: string | null
  names_language: string | null
  face_pack_dirs?: string[]
  project_dir?: string | null // where the project lives (null = the default folder)
  build_cores?: number | null // processor cores the build may use (null = all but one)
  build_memory_percent?: number | null // percent of the machine's memory the build may use (null = 50)
}

/** What the build may use on this machine (GET /api/machine); cores / memory_mb null when the system does not tell. */
export interface MachineInfo {
  cores: number | null
  memory_mb: number | null
  default_cores: number
  default_memory_percent: number
  memory_percent_range: [number, number] // allowed memory setting (10-90)
  worker_memory_mb: number
  workers: number
}

/** Whether a patch was built and from the saved project (GET /api/status → patch). */
export interface PatchStatus {
  built: boolean
  up_to_date: boolean
  built_at?: string
  files?: string[]
}

/** Steps of "Gerar patch" in order (f14mod.builder.BUILD_STEPS). */
export type BuildStep = 'database' | 'images' | 'texts' | 'files'
export type BuildItemKind = 'kit' | 'crest' | 'photo' | 'league' | 'flag' | 'language'

/** GET /api/patch/progress: the current (or last) build. */
export interface BuildProgress {
  running: boolean
  steps: BuildStep[]
  step: BuildStep | null
  done: number
  total: number
  message: string
  elapsed?: number
  error: string | null
  /** what the 'images' / 'texts' steps are waiting for (a kit, a language...) */
  item?: { kind: BuildItemKind; name: string } | null
  /** the user asked the build to stop (it ends the languages already being made first) */
  stopping?: boolean
  cancelled?: boolean
  /** build cache entries (texts and pictures) reused / made so far */
  cache?: { reused: number; made: number }
}

export interface Issue {
  code: string
  detail: string
}

/** A problem of the project (backend f14api.validation): an error stops the build, a warning does not. */
export interface ProjectIssue {
  code: string
  severity: 'error' | 'warning'
  kind: 'league' | 'team' | 'player' | null
  id: number | null
  entity: string | null // 'team:123'
  field: string | null
  params: Record<string, string | number | string[]>
  name: string | null // the entity's shown name
}

export interface GameCheck {
  state: 'not_found' | 'invalid' | 'modified' | 'clean' | 'patched'
  game_dir: string | null
  issues: Issue[]
  installed: { version: string; installed_at: string } | null
}

export interface GameStatus {
  state: 'empty' | 'invalid' | 'building' | 'ready' | 'error'
  game_dir: string | null
  check: GameCheck | null
  progress: { step: string; done: number }
  error: string | null
  token: string
}

export interface Job {
  id: string
  kind: 'build' | 'install' | 'uninstall'
  state: 'running' | 'done' | 'error'
  step: string
  done: number
  result: Record<string, unknown> | null
  error: string | null
  /** A limit of the game the build hit (buildError.<code> in the dictionaries). */
  code?: string | null
  detail?: string | null
}

export interface Status {
  version: string
  config: Config
  names_language: string
  game: GameStatus
  project: Partial<Record<'team' | 'league' | 'player', number>>
  job: Job | null
  patch_built: boolean
  patch?: PatchStatus
  /** the app's folders shown in the Settings (backups: inside the game folder, null without a game) */
  folders?: { project: string; default_project: string; backups: string | null; patch: string; logs: string }
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
  sort: string
  dir: 'asc' | 'desc'
  /** every page's items of the project (created or edited) that match the filters: what the checkboxes can pick */
  own_ids?: number[]
}

/** what the lists' bulk delete takes */
export type BulkKind = 'country' | 'league' | 'team' | 'player'

export interface Ref {
  id: number
  name: string
  /** Created in the project (countries list of the options). */
  is_new?: boolean
}

export interface LeagueRow {
  id: number
  name: string
  db_name: string | null
  level: number | null
  country_id: number | null
  country: string | null
  has_logo: number | boolean
  is_new: boolean
  team_count: number
  edited: boolean
  /** Left out of the patch (kept in the project). */
  hidden: boolean
  /** The game itself never lists it (no button to show it). */
  game_hidden: boolean
  /** Other countries the league shows in. */
  extra_countries: number[]
  /** Countries of the league where it is left out of the patch (it stays in them in the app). */
  hidden_in_countries: number[]
  /** Every country the league shows in is out of the patch: the league is out too. */
  hidden_by_countries: boolean
  own_logo: number | null
}

export interface CountryRow {
  id: number
  name: string
  is_new: boolean
  has_flag: boolean
  flag_id: number
  /** The flag shown when the country has no picture of its own. */
  base_flag_id: number
  own_flag: number | null
  league_count: number
  edited: boolean
  /** Hidden by the project (Hide button). */
  hidden: boolean
  /** The game itself never lists it (no button to show it). */
  game_hidden: boolean
}

export interface CountryDetail extends CountryRow, EditForm {
  name_keys: string[]
  languages: string[]
  original_names: NameTable
  saved_names: NameTable
  leagues: LeagueRow[]
}

export interface Limits {
  countries_free: number
  league_links: number
  max_league_links: number
  max_squad: number
}

export interface TeamRow {
  id: number
  name: string
  abbr15: string | null
  abbr3: string | null
  overall: number | null
  attack: number | null
  midfield: number | null
  defense: number | null
  color: (number | null)[] | null
  /** The kit colors the team has (1 to 3), as [r, g, b]. */
  colors: number[][]
  has_crest: boolean
  national_of: number | null
  league_id: number | null
  league: string | null
  player_count: number
  edited: boolean
  /** Hidden by the project (Hide button). */
  hidden: boolean
  /** Created in the project. */
  is_new: boolean
  /** When the user's crest picture was saved (null = none). */
  own_crest: number | null
}

export interface PlayerRow {
  id: number
  name: string
  overall: number | null
  potential: number | null
  position: number | null
  position_name: string | null
  birthdate: string | null
  height: number | null
  nationality: number | null
  nationality_name: string | null
  has_photo: boolean
  team_id: number | null
  team: string | null
  edited: boolean
  /** Created in the project. */
  is_new: boolean
  /** A created player left out of the patch (Hide). */
  hidden: boolean
}

/** {name key: {language code or '*': text}} */
export type NameTable = Record<string, Record<string, string>>

export type FieldKind = 'int' | 'select' | 'text' | 'date' | 'color' | 'nation' | 'nations' | 'team' | 'roster' | 'position' | 'code' | 'traits' | 'face'
export type FieldValue = string | number | number[] | string[] | FaceChoice | null

/** Where a player's head comes from (field `face`; none = his own: his real face when the game has one). */
export type FaceChoice =
  | { source: 'generic' }
  | { source: 'player'; player: number }
  | { source: 'pack'; pack: string; id: number; pack_name?: string; part?: string; name?: string; credits?: string; credits_url?: string }

/** One editable value of a database row (backend f14mod.fields). */
export interface FieldSpec {
  name: string
  group: string
  kind: FieldKind
  min: number | null
  max: number | null
  options: number[]
  max_length: number | null
  optional: boolean
}

/** What every edit screen gets: the specs, the game's values and the values saved in the project. */
export interface EditForm {
  fields: FieldSpec[]
  values: Record<string, FieldValue>
  saved: Record<string, FieldValue>
  edited: boolean
}

export interface RosterRow {
  id: number
  name: string
  overall: number | null
  position: number | null
  position_name: string | null
  jersey: number | null
  link_position: number | null
  link_position_name: string | null
  /** the name printed on the back of the jersey (jersey name, else last name) */
  back_name: string | null
  has_photo: boolean
  is_new: boolean
  edited: boolean
  /** out of the patch in this team only */
  hidden: boolean
  /** the player is out of the patch everywhere (Hide) */
  player_hidden: boolean
}

/** One row of a squad being edited: lineup slot = a position code (starter), 28 = bench, 29 = out of the squad. */
export interface SquadRow {
  player: number
  jersey: number | null
  slot: number
  /** out of the patch in this team only (kept in the squad on the screen) */
  hidden?: boolean
}

/** One of the game's 33 formations: the position code of each of the 11 slots. */
export interface Formation {
  id: number
  name: string
  positions: number[]
}

/** Where a kit comes from: a kit of the game, the user's pictures, or one of the game's mask kits painted. */
/** Name and numbers of a kit (teamkits columns; a value left out keeps the kit's own). */
export interface KitPrint {
  name_color?: number[]
  number_color?: number
  shorts_number_color?: number
  front_number?: boolean
  shorts_number?: boolean
  show_name?: boolean
  name_layout?: number
  name_font?: number
  number_font?: number
  shorts_number_font?: number
  collar?: number
}

interface KitExtras {
  collar?: number
  print?: KitPrint
}

export type KitConfig =
  | ({ source: 'keep' } & KitExtras)
  | ({ source: 'game'; team: number; kind: number } & KitExtras)
  | ({ source: 'upload' } & KitExtras)
  | ({ source: 'generic'; model: number; colors: number[][] } & KitExtras)

/** The game's kit fonts: name fonts, number fonts with the colors each has, and the color each number color shows. */
export interface KitFonts {
  name: { id: number; name: string | null }[]
  number: Record<string, number[]>
  colors: { id: number; rgb: number[] }[]
}

export type KitPart = 'jersey' | 'shorts' | 'mini'

/** Body of POST /api/preview/kit-print: the layer with a crest not saved yet (base64 picture, or 'remove'). */
export interface KitPrintBody {
  part: 'jersey' | 'shorts'
  values: Omit<KitPrint, 'collar'>
  number: number | null
  name: string | null
  config: KitConfig | null
  crest?: string
}

export interface TeamKit {
  kind: number
  /** The user's choice; null = `default`. */
  config: KitConfig | null
  /** When each of the user's pictures was saved. */
  pictures: Record<KitPart, number | null>
  /** Without a choice: 'game' (the team's own, or the team it copies), 'generic' (a team made from scratch), null = none. */
  default: 'game' | 'generic' | null
  /** The name and numbers the kit has now (its teamkits row; collar included). */
  print: KitPrint
}

export interface TeamDetail extends TeamRow, EditForm {
  db_name: string | null
  name_keys: string[]
  languages: string[]
  original_names: NameTable
  saved_names: NameTable
  roster: RosterRow[]
  roster_changed: boolean
  /** the leagues the team is in; hidden: out of the patch in that league only */
  leagues: (Ref & { hidden: boolean })[]
  /** A created team: the game team it starts from. */
  template: number | null
  /** The crest and kits come from the game (the team's own, or the team a created one copies). */
  copied: boolean
  formations: Formation[]
  kits: TeamKit[]
  max_squad: number
  raw: Raw
}

export interface LeagueDetail extends EditForm {
  id: number
  name: string
  db_name: string | null
  level: number | null
  country_id: number | null
  country: string | null
  has_logo: boolean
  /** The game has a logo of its own for this league. */
  game_has_logo: boolean
  /** The user's picture (saved at), null = none. */
  own_logo: number | null
  hidden: boolean
  game_hidden: boolean
  /** Every country the league shows in is hidden: the league is hidden too. */
  hidden_by_countries: boolean
  is_new: boolean
  names: NameTable
  original_names: NameTable
  saved_names: NameTable
  languages: string[]
  name_keys: string[]
  team_ids: number[]
  /** teams left out of the patch in this league only (kept in its list on the screen) */
  hidden_team_ids: number[]
  /** The league's teams in the game (a created league: none). */
  game_team_ids: number[]
  teams_changed: boolean
  teams: TeamRow[]
  raw: Raw
}

export interface PlayerTeam {
  id: number
  name: string
  jersey: number | null
  position: number | null
  position_name: string | null
  national_of: number | null
  /** out of the patch in this team only */
  hidden: boolean
  /** the team is out of the patch everywhere (Hide) */
  team_hidden: boolean
  is_new: boolean
  /** players of the team in the patch (hidden ones not counted) */
  squad_size: number
  /** the 11 lineup positions of the team's formation */
  slots: number[]
}

export interface PlayerDetail extends EditForm {
  id: number
  name: string
  names: Partial<Record<'first' | 'last' | 'common' | 'jersey_name', string>>
  overall: number | null
  potential: number | null
  position: number | null
  position_name: string | null
  birthdate: string | null
  height: number | null
  weight: number | null
  nationality: number | null
  nationality_name: string | null
  has_photo: boolean
  /** When the user's photo was saved (null = none). */
  own_photo: number | null
  /** The game has his own face (headclasscode 0). */
  game_face: boolean
  /** The pack face chosen has its files kept in the project. */
  face_stored?: boolean
  is_new: boolean
  /** A created player: the player whose values he started from. */
  template: number | null
  /** A created player left out of the patch (Hide). */
  hidden: boolean
  max_squad: number
  attributes: Record<string, number>
  teams: PlayerTeam[]
  raw: Raw
}

/** The values the screen offers for the player's codes and the traits (GET /api/player-options). */
export interface PlayerOptions {
  codes: Record<string, number[]>
  traits: string[]
  /** codes with pictures (front view of the generic head / hair) */
  thumbs: string[]
  hair_colors: string[]
}

export interface FacePackPart {
  path: string
  label: string
  count: number
  named: number
  warnings: { code: string; count?: number; detail?: string }[]
}

/** A pack found in a face folder of the Settings (POST /api/facepacks/check; index = the folder's position). */
export interface FacePackCheck extends FacePagePack {
  index: number
}

export interface FacePackFolder {
  folder: string
  exists: boolean
  parts: FacePackPart[]
}

/** A pack of the face picker's page (folder = its asset folder; error = a folder without faces). */
export interface FacePagePack {
  folder: string
  name: string
  count: number
  warnings: { code: string; count?: number; detail?: string }[]
  error: string | null
}

export interface FacePage {
  packs: FacePagePack[]
  items: (PackFace & { folder: string; pack: string })[]
  total: number
}

export type FacePart = 'eyes' | 'hair' | 'hair_textures' | 'hairlod'

export interface PackFace {
  id: number
  hair: boolean
  hairlod: boolean
  photo: boolean
  /** optional parts the pack does not bring (the app never fills them in) */
  missing?: FacePart[]
  name?: string
  credits?: string
  credits_url?: string
}

export interface Options {
  leagues: Ref[]
  positions: Ref[]
  languages: string[]
  nations: Ref[]
  teams: Ref[]
}

/** How the player looks (GET /api/preview/look/<id>, f14mod.preview.look): real = his own face files (head, hair,
 * eyes and face are then his id); hair 0 = bald; eyes null = a real face without eyes (drawn dark, never filled in);
 * scale = his height over the reference model's. */
export interface PreviewLook {
  real: boolean
  head: number
  hair: number
  hair_color: string
  eyes: number | null
  face: string
  skin: number
  sleeve: number
  socks: number
  shoe: number
  glove: number
  scale: number
  /** with a face of a pack (or kept in the project): what the face URLs carry */
  query?: string
}
