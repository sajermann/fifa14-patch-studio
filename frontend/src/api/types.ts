// What the backend sends (backend/f14api). Field names follow the API.

export type Raw = Record<string, string | number | null>

export interface Config {
  language: 'pt-BR' | 'en' | null
  game_dir: string | null
  names_language: string | null
}

export interface Issue {
  code: string
  detail: string
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
}

export interface Status {
  version: string
  config: Config
  names_language: string
  game: GameStatus
  project: Partial<Record<'team' | 'league' | 'player', number>>
  job: Job | null
  patch_built: boolean
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
  sort: string
  dir: 'asc' | 'desc'
}

export interface Ref {
  id: number
  name: string
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
  has_crest: boolean
  national_of: number | null
  league_id: number | null
  league: string | null
  player_count: number
  edited: boolean
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
}

/** {name key: {language code or '*': text}} */
export type NameTable = Record<string, Record<string, string>>

export type FieldKind = 'int' | 'select' | 'text' | 'date' | 'color' | 'nation' | 'team' | 'roster' | 'position'
export type FieldValue = string | number | number[] | null

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
  has_photo: boolean
}

export interface TeamDetail extends TeamRow, EditForm {
  db_name: string | null
  name_keys: string[]
  languages: string[]
  original_names: NameTable
  saved_names: NameTable
  roster: RosterRow[]
  leagues: Ref[]
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
  is_new: boolean
  names: NameTable
  original_names: NameTable
  saved_names: NameTable
  languages: string[]
  name_keys: string[]
  team_ids: number[]
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
  attributes: Record<string, number>
  teams: PlayerTeam[]
  raw: Raw
}

export interface Options {
  leagues: Ref[]
  positions: Ref[]
  languages: string[]
  nations: Ref[]
  teams: Ref[]
}
