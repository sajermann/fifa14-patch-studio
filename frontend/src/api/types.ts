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
  terms_version?: number | null // version of the first-run notice the user accepted
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
export type BuildItemKind = 'face' | 'kit' | 'crest' | 'photo' | 'league' | 'flag' | 'language' | 'adboard' | 'stadium' | 'part'
/** What the 'database' step is doing (item kind 'part'; builder.DATABASE_PARTS). */
export type BuildPart = 'check' | 'read' | 'created' | 'fields' | 'rosters' | 'kits' | 'faces' | 'links' | 'save' | 'adboards' | 'equipment' | 'stadiums'

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
  /** count: [done, total] of the part being done (the 'database' step's done/total is its whole share instead) */
  item?: { kind: BuildItemKind; name: string; count?: [number, number] } | null
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

export type ImportStep = 'prepare' | 'write' | 'links' | 'save'

/** GET /api/share/apply/progress: the current (or last) import. */
export interface ImportProgress {
  running: boolean
  steps: ImportStep[]
  step: ImportStep | null
  done: number
  total: number
  elapsed?: number
  /** the item being written */
  item?: { kind: ShareKind; name: string | null; id: number } | null
  error: { code: string; detail: string } | null
  stopping?: boolean
  cancelled?: boolean
  result?: { imported: Partial<Record<ShareKind, number[]>>; count: number } | null
}

/** A problem of the project (backend f14api.validation): an error stops the build, a warning does not. */
export interface ProjectIssue {
  code: string
  severity: 'error' | 'warning'
  kind: 'league' | 'team' | 'player' | 'stadium' | null
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
  kind: 'build' | 'install' | 'uninstall' | 'import'
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
  /** how many of each kind the project has: <kind> = edited from the game, new_<kind> = created (Project.counts) */
  project: Record<string, number>
  job: Job | null
  patch_built: boolean
  patch?: PatchStatus
  /** the app's folders shown in the Settings (backups: inside the game folder, null without a game) */
  folders?: { project: string; default_project: string; backups: string | null; patch: string; logs: string }
  /** the first-run screen: nothing else opens while it is required (no usable game, or the notice not accepted) */
  setup: { required: boolean; reasons: ('game_dir' | 'terms')[]; terms_version: number }
}

/** POST /api/setup/apply: the first-run choices. */
export interface SetupRequest {
  game_dir: string
  face_pack_dirs: string[]
  terms_version: number
  build_cores: number | null
  build_memory_percent: number | null
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
export type BulkKind = 'country' | 'league' | 'team' | 'player' | 'stadium' | 'adboard' | 'boot' | 'glove' | 'ball'

/** Where the running (or last) bulk delete is: items gone through and how each ended. */
export interface BulkDeleteProgress {
  running: boolean
  kind?: BulkKind
  done: number
  total: number
  deleted: number
  reset: number
  skipped: number
  elapsed?: number
  stopping?: boolean
  cancelled?: boolean
}

export interface Ref {
  id: number
  name: string
  /** Created in the project (countries list of the options). */
  is_new?: boolean
}

/** When an entity of the project was created and last changed (ISO 8601, UTC), set by the backend on save; a game
 * entity the project does not change has none (and one edited before they existed has no creation date). */
export interface Dated {
  created_at?: string | null
  updated_at?: string | null
}

export interface LeagueRow extends Dated {
  id: number
  name: string
  db_name: string | null
  level: number | null
  country_id: number | null
  country: string | null
  has_logo: number | boolean
  is_new: boolean
  team_count: number
  /** The advertising board of the league, null = the game's boards. */
  adboard_id: number | null
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

export interface CountryRow extends Dated {
  id: number
  name: string
  is_new: boolean
  has_flag: boolean
  flag_id: number
  /** The flag shown when the country has no picture of its own. */
  base_flag_id: number
  own_flag: number | null
  league_count: number
  /** Players whose nationality is this country (the game's and the project's). */
  player_count: number
  /** The database's confederation code (1 = none/other, 2 = UEFA, 3 = CAF, 4 = CONMEBOL, 5 = AFC, 6 = OFC, 7 = CONCACAF). */
  confederation: number | null
  edited: boolean
  /** Hidden by the project (Hide button). */
  hidden: boolean
  /** The game itself never lists it (no button to show it). */
  game_hidden: boolean
}

/** One stadium of the game, read-only (GET /api/teams/<id> `stadiums`; the same as the extractor's). */
export interface StadiumInfo {
  id: number
  name: string
  names: Record<string, string>
  capacity: number | null
  year_built: number | null
  country_id: number | null
  country: string | null
  home_team: Ref | null
  team_count: number
  /** times of day the match screen offers in this stadium (1 = day, 3 = night) and the weather allowed in each */
  conditions: { time_of_day: number; rain: boolean; snow: boolean }[]
  pictures: number[]
  /** where = the archive or 'project' (a created stadium's own files, with their size) */
  files: { path: string; where: string | null; size?: number }[]
  /** times of day the 3D preview can show (1 = day, 3 = night); empty = no 3D files */
  times: number[]
  raw: Raw
}

/** A row of the stadiums list (the project's changes over the game's values). */
export interface StadiumRow extends Dated {
  id: number
  /** the database name (the one the game shows), else the language text */
  name: string
  /** the StadiumName_ text in the names language */
  language_name: string | null
  country_id: number | null
  country: string | null
  home_team_id: number | null
  home_team: string | null
  capacity: number | null
  team_count: number
  /** the first menu picture variant, null = none */
  picture: number | null
  has_3d: boolean
  edited: boolean
  /** a stadium the user created */
  is_new: boolean
  /** a created stadium left out of the patch (Hide) */
  hidden: boolean
}

/** A team that plays in the stadium (the user's choices included). */
export interface StadiumTeam {
  id: number
  name: string
  league: string | null
  has_crest: boolean
  is_new: boolean
  edited: boolean
  stadium_custom_name: string | null
}

/** The stadium screen: what the extractor shows, the edit form and the teams that play in it. */
export interface StadiumDetail extends StadiumInfo, EditForm, Dated {
  is_new: boolean
  /** a created stadium left out of the patch (Hide) */
  hidden: boolean
  /** a created stadium: the game stadium it starts from (its row; its scene and pictures until it has its own) */
  template: number | null
  template_name: string | null
  /** a created stadium: the scene comes from a stadium's folder (else the template's) */
  own_scene: boolean
  /** the menu pictures (variants) the user replaced, on any stadium */
  own_pictures: number[]
  /** the game stadium the files of the stadium's folder were made for (its data fit them), or null */
  folder_stadium: number | null
  folder_stadium_name: string | null
  name_keys: string[]
  languages: string[]
  original_names: NameTable
  saved_names: NameTable
  teams: StadiumTeam[]
}

export interface CountryDetail extends CountryRow, EditForm {
  name_keys: string[]
  languages: string[]
  original_names: NameTable
  saved_names: NameTable
  leagues: LeagueRow[]
  /** The game's national team of the country (nations.teamid), if any. */
  national_team: Ref | null
  top_tier: number | null
  /** The country's row of the audionation table (commentary and crowd sound regions); null = none. */
  audio: Raw | null
  /** The country's row of the nations table (the game's; empty for a created country). */
  raw: Raw
}

export interface Limits {
  countries_free: number
  league_links: number
  max_league_links: number
  max_squad: number
}

export interface TeamRow extends Dated {
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
  /** How many kits the team has (the ones set in the project, the game's and, for a team made from scratch, the
   * generic ones). */
  kit_count: number
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

export interface PlayerRow extends Dated {
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
  /** A real face: the game's, a pack's or another player's (not a generic one). */
  has_face: boolean
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

/** The game's generic eyes / hair a pack face lacking them is filled in with (codes of the game's files; the hair is painted with his hair color). */
export interface FaceFill {
  eyes?: number
  hair?: number
  /** only the hair seen from afar (a face with its own hair but not this one); the hair brings its own */
  hairlod?: number
}

/** Where a player's head comes from (field `face`; none = his own: his real face when the game has one). */
export type FaceChoice =
  | { source: 'generic' }
  | { source: 'player'; player: number }
  | { source: 'pack'; pack: string; id: number; pack_name?: string; part?: string; name?: string; credits?: string; credits_url?: string; fill?: FaceFill }

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
  /** the game has the player's own face */
  has_face: boolean
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
  /** The team's stadium (the user's choice, else the game's) and the name the team gives its stadium. */
  stadium_ids: number[]
  /** The user chose the stadium (not the game's). */
  stadium_changed: boolean
  /** The game's stadium of the team (a created team: the one of the team it starts from); null = none. */
  game_stadium_id: number | null
  stadiums: StadiumInfo[]
  stadium_custom_name: string | null
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
  /** The advertising board of the team (its home games), null = the game's boards. */
  adboard_id: number | null
  raw: Raw
}

export interface LeagueDetail extends EditForm, Dated {
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
  /** The advertising board of the league, null = the game's boards. */
  adboard_id: number | null
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

export interface PlayerDetail extends EditForm, Dated {
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
  /** Optional parts the saved pack face does not bring (only with `face_stored`). */
  face_missing?: FacePart[]
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
  /** generic eyes and hair styles the game has files of (what a face lacking them can be filled in with) */
  fill?: { eyes: number[]; hair: number[]; hairlod: number[] }
  /** the accessory codes each place of the body can hold (accessorycode1-4 are slots of a list) */
  accessories?: AccessoryOptions
}

export interface AccessoryOptions {
  places: Record<string, number[]>
  slots: number
  colours: number[]
  /** drawn from their own picture: only colour 0 */
  textured: number[]
  /** the colour picks the glove model */
  model: number[]
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
  stadiums: Ref[]
  /** Confederation codes in use (countries filter). */
  confederations: number[]
  /** Division levels in use (leagues filter). */
  levels: number[]
  /** Countries that are the main country of a league (leagues filter). */
  league_countries: number[]
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

/** An advertising board: one the user created (is_new) or one of the game's (edited = its picture replaced). A
 * picture of 512x1024 = 16 bands; linked to teams and leagues. */
export interface Adboard extends EditForm, Dated {
  id: number
  is_new: boolean
  /** The name of a board the user created ('' for the game's: the screen names them by number). */
  name: string
  hidden: boolean
  /** The picture's version: when the user's picture was saved, 0 = the game's own picture, null = no picture yet. */
  picture: number | null
  teams: (Ref & { is_new: boolean })[]
  leagues: (Ref & { is_new: boolean })[]
  /** A game board: the competitions the game shows it in (name null = not a league of the database). */
  competitions?: { id: number; name: string | null }[]
  /** A game board: the one of every competition the game's table lacks (friendlies, cups, new leagues). */
  default?: boolean
}

export interface AdboardList {
  items: Adboard[]
  /** The board picture's size in the game and its number of bands. */
  size: [number, number]
  bands: number
  default_board: number
}

export interface AdboardBody {
  name: string
  /** A new picture (base64); omitted = keep the one it has. */
  picture?: string
  remove_picture?: boolean
  /** Create: a copy of this board (its picture; the game's own one for a game board not edited). */
  copy_of?: number
}

/** Boots, goalkeeper gloves and balls (f14mod.equipment). */
export type EquipmentKind = 'boot' | 'glove' | 'ball'

/** A boot, glove or ball: one the user created (is_new, its own code) or one of the game's (edited = a new name, files
 * or picture). Players wear one (their boot and glove), teams play with one (their ball). */
export interface Equipment extends EditForm, Dated {
  kind: EquipmentKind
  id: number
  /** Its code in the game (players.shoetypecode, players.gkglovetypecode, teams.balltype). */
  code: number
  is_new: boolean
  name: string
  /** A game item: its own name in the game (in the shown language), null = it has none. */
  game_name: string | null
  credits: string
  credits_url: string | null
  hidden: boolean
  /** The pack's files saved ('mesh', 'texture') and the ones a new item needs. */
  files: string[]
  needs: string[]
  complete: boolean
  /** The user's picture (its version), null = drawn from the files. */
  picture: number | null
  version: number
  /** False for a new glove: the game's edit player screen does not list it. */
  listed: boolean
  /** Players (boot, glove) or teams (ball) wearing it. */
  wearers: (Ref & { is_new: boolean })[]
  wearer_count: number
}

export interface EquipmentList {
  items: Equipment[]
  /** Free codes left for new items. */
  free: number
}

export interface EquipmentBody {
  name: string
  credits?: string
  credits_url?: string | null
  /** Create: a copy of this item (its files; a created one's picture and credits too). */
  copy_of?: number
}

export interface EquipmentFiles {
  mesh?: string
  texture?: string
  remove?: string[]
}

/** Import and export (backend share_routes): one item of the tree of what goes. */
export type ShareKind = 'country' | 'league' | 'team' | 'player' | 'stadium' | 'adboard' | 'boot' | 'glove' | 'ball'
export interface ShareNode {
  key: string
  kind: ShareKind
  id: number
  name: string | null
  /** false = a change to one of the game's own items (the same id in every game) */
  created: boolean
  /** the slot of its own picture in the zip, or null */
  picture: string | null
  children: string[]
  /** import only: the id it gets in the project, why it changes, picked at first, why it cannot come in */
  new_id?: number | null
  reason?: 'taken' | 'range' | 'replaces' | 'updates' | null
  default?: boolean
  error?: 'not_in_game' | 'limit' | null
  /** a country of a package the game already has (left out at first: whoever uses it keeps the game's) */
  game_has?: boolean
  /** an update (it came in from the same origin before): the user changed it since */
  changed?: boolean
  /** an update: the id it takes if it comes in as a new item instead (null = none left), and why */
  alt_id?: number | null
  alt_reason?: 'taken' | 'range' | null
}
export interface ShareTree {
  token: string
  nodes: Record<string, ShareNode>
  roots: string[]
}
export interface ShareInspect extends ShareTree {
  origin: 'own' | 'package'
  warnings: string[]
  /** players whose face lacks its eyes or hair (the import may complete them with the generic ones) */
  fillable?: number
  patch_name?: string | null
  credits?: { text?: string; url?: string } | null
}
