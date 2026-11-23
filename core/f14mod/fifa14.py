"""FIFA 14 (PC): the database, the language strings and where each picture, kit, font and face file lives.

Everything here describes the source game as it is. Nothing is adapted to any other game or tool.
"""
import datetime
import os
import re
from functools import cached_property

from . import t3db
from .gamefs import DATABASE, GameFiles

GAME = 'fifa14'
PLATFORM = 'pc'
META = 'data/db/fifa_ng_db-meta.xml'
DEFAULT_LANGUAGE = 'eng_us'

# names of the language database (data/loc/<language>.db, its _upd file overriding it): key -> stringid prefix
TEAM_NAME_STRINGS = {
    'full': 'TeamName_',
    'abbr15': 'TeamName_Abbr15_',
    'abbr10': 'TeamName_Abbr10_',
    'abbr7': 'TeamName_Abbr7_',
    'abbr3': 'TeamName_Abbr3_',
    'commentary': 'CT_TeamName_',
}
LEAGUE_NAME_STRINGS = {
    'full': 'LeagueName_',
    'abbr15': 'LeagueName_Abbr15_',
    'abbr': 'Labbr_',
    'trophy': 'TrophyName_',
    'trophy_abbr15': 'TrophyName_Abbr15_',
}

COUNTRY_NAME_STRINGS = {
    'full': 'NationName_',
    'abbr3': 'nationname_abbr3_',
}
STADIUM_NAME_STRINGS = {'full': 'StadiumName_'}
# stadium files (same layout as the extractor reads): the 3D scene (model, textures by time of day, the variants some
# patches add per home team), where the crowd sits, and the menu pictures (Apt archives; the number = the variant)
STADIUM_SCENE = re.compile(r'data/sceneassets/stadium/(?:specific)?stadium_(\d+)[._][^/]*$')
STADIUM_CROWD = re.compile(r'data/sceneassets/crowdplacement/crowd_(\d+)_[^/]*$')
STADIUM_PICTURES = {'large': re.compile(r'data/ui/artassets/stadiumsbig/st_(\d+)_(\d+)\.big$'),
                    'small': re.compile(r'data/ui/artassets/stadium/stadium_(\d+)_(\d+)\.big$')}
STADIUM_FOLDERS = ('data/sceneassets/stadium/', 'data/sceneassets/crowdplacement/', 'data/ui/artassets/stadiumsbig/',
                   'data/ui/artassets/stadium/')
# times of day and weather a stadium allows: four slots (timeofday1..4 + tod1weather..4); time 1 = day, 3 = night,
# 5 = empty slot; weather is two flags (1 = rain, 2 = snow; 0 = clear sky only)
STADIUM_SLOTS, STADIUM_NO_TIME, WEATHER_RAIN, WEATHER_SNOW = 4, 5, 1, 2
STADIUM_DAY, STADIUM_NIGHT = 1, 3  # timeofdayN values of the game's stadiums (and 5 = slot not used)


def stadium_conditions(row: dict) -> list[dict]:
    """[{time_of_day, rain, snow}] of the stadium's used slots (the match screen only offers these)."""
    out = []
    for slot in range(1, STADIUM_SLOTS + 1):
        time = row.get(f'timeofday{slot}')
        if not isinstance(time, int) or time == STADIUM_NO_TIME:
            continue
        weather = row.get(f'tod{slot}weather') or 0
        out.append({'time_of_day': time, 'rain': bool(weather & WEATHER_RAIN), 'snow': bool(weather & WEATHER_SNOW)})
    return out

# limits measured in the game and in the database fields
MAX_NATION_ID = 250        # nations.nationid has 8 bits and the meta allows up to 250
FIRST_FREE_LEAGUE = 400    # new leagues get the first free id from here (385-389 are hidden slots of the game)
MAX_LEAGUE_ID = 4095
RESERVED_LEAGUES = frozenset({2000, 2028, 385, 386, 387, 388, 389})
MAX_LEAGUE_LINKS = 4095    # leagueteamlinks.artificialkey has 12 bits: every team-league link of the game
MAX_SQUAD = 41             # players a team shows in the game (more appear as "undefined")
TEMPLATE_LEAGUE = 76       # Rest of World: the model row of a new league (no career, no competition)
TEMPLATE_NATION = 211      # Rest of World: the model row and the default flag of a new country


def new_league_values(lid: int) -> dict:
    """The columns a new league changes in its copy of the TEMPLATE_LEAGUE row (the user's fields go on top)."""
    return {'leagueid': lid, 'leaguename': f'League {lid}', 'level': 1, 'leaguetimeslice': 0,
            'iswithintransferwindow': 0}


TABLE_POSITIONS = 64       # leagueteamlinks.currenttableposition has 6 bits (1-64)

# pictures (game paths; {} = the id)
CREST = 'data/ui/imgassets/crest/l{}.dds'
PHOTO = 'data/ui/imgassets/heads/p{}.dds'
HIDDEN_COUNTRY = 0  # a league with country 0 is not listed by the game (Kick-off, tournaments; tests OC1/LC1)
HIDDEN_LEAGUE = 111  # league the game never lists (country 0): a team hidden in the game is linked only to it
UNLISTED_NATIONS = (209, 210, 216)  # countries the game never lists (Create Player, Free Agents, Creation Zone)
LEAGUE_IMAGES = {'logo': 'data/ui/imgassets/league/l{}.dds', 'banner': 'data/ui/imgassets/league512x128/l{}.dds'}
LEAGUE_PICTURES = {  # every picture of a league the game reads: game path -> (size, dark background)
    'data/ui/imgassets/league/l{}.dds': ((256, 256), False),
    'data/ui/imgassets/league/dark/l{}.dds': ((256, 256), True),
    'data/ui/imgassets/league512x128/l{}.dds': ((512, 128), False),
    'data/ui/imgassets/league512x128/dark/l{}.dds': ((512, 128), True),
    'data/ui/imgassets/leaguelogos_sm/l{}.dds': ((256, 256), False),
    'data/ui/imgassets/leaguelogos_sm/dark/l{}.dds': ((256, 256), True),
    'data/ui/imgassets/leaguelogos_tiny/l{}.dds': ((256, 64), False),
    'data/ui/imgassets/leaguelogos_tiny/dark/l{}.dds': ((256, 64), True),
}
FLAG_PICTURE = 'data/ui/imgassets/flags512x512/f_{}.dds'  # the one the screens show
FLAG_FILES = ('data/ui/artassets/cardflags/{}.big', 'data/ui/artassets/countryflags/f_{}.big',
              'data/ui/artassets/miniflags/flag_{}.big', 'data/ui/imgassets/flags512x512/f_{}.dds')
FLAG_FOLDERS = re.compile(r'data/ui/imgassets/flags(\d+)x(\d+)/')
KIT = 'data/sceneassets/kit/kit_{}_{}_0.rx3'  # team, kit type
NAME_FONT = 'data/sceneassets/jerseyfonts/font_{}.ttf'
NUMBER_FONT = 'data/sceneassets/kitnumbers/kitnumbers_{}_{}.rx3'  # font, palette color
FACE_FOLDERS = ('data/sceneassets/heads/', 'data/sceneassets/faces/', 'data/sceneassets/hair/',
                'data/sceneassets/hairlod/')
FACE_FILE = re.compile(r'data/sceneassets/(?:heads|faces|hair|hairlod)/(head|eyes|face|hair|hairlod)_(\d+)_[^/]*\.rx3$')
FACE_REQUIRED = ('head', 'face')  # a real face has at least its head model and its face textures

KIT_ROLES = {0: 'home', 1: 'away', 2: 'goalkeeper'}  # other kit types keep only their number

POSITIONS = ['GK', 'SW', 'RWB', 'RB', 'RCB', 'CB', 'LCB', 'LB', 'LWB', 'RDM', 'CDM', 'LDM', 'RM', 'RCM', 'CM',
             'LCM', 'LM', 'RAM', 'CAM', 'LAM', 'RF', 'CF', 'LF', 'RW', 'RS', 'ST', 'LS', 'LW', 'SUB', 'RES']

# database column -> neutral name of the player's ratings
ATTRIBUTES = {
    'overallrating': 'overall', 'potential': 'potential',
    'acceleration': 'acceleration', 'sprintspeed': 'sprint_speed', 'agility': 'agility', 'balance': 'balance',
    'jumping': 'jumping', 'stamina': 'stamina', 'strength': 'strength', 'reactions': 'reactions',
    'aggression': 'aggression', 'interceptions': 'interceptions', 'positioning': 'positioning', 'vision': 'vision',
    'ballcontrol': 'ball_control', 'crossing': 'crossing', 'dribbling': 'dribbling', 'finishing': 'finishing',
    'freekickaccuracy': 'freekick_accuracy', 'headingaccuracy': 'heading_accuracy', 'longpassing': 'long_passing',
    'shortpassing': 'short_passing', 'marking': 'marking', 'shotpower': 'shot_power', 'longshots': 'long_shots',
    'standingtackle': 'standing_tackle', 'slidingtackle': 'sliding_tackle', 'volleys': 'volleys', 'curve': 'curve',
    'penalties': 'penalties', 'gkdiving': 'gk_diving', 'gkhandling': 'gk_handling', 'gkkicking': 'gk_kicking',
    'gkreflexes': 'gk_reflexes', 'gkpositioning': 'gk_positioning',
    'skillmoves': 'skill_moves', 'weakfootabilitytypecode': 'weak_foot', 'internationalrep': 'international_rep',
    'attackingworkrate': 'attacking_work_rate', 'defensiveworkrate': 'defensive_work_rate',
}
APPEARANCE = ('headtypecode', 'headclasscode', 'hairtypecode', 'haircolorcode', 'skintonecode', 'skintypecode',
              'facialhairtypecode', 'facialhaircolorcode', 'eyecolorcode', 'eyebrowcode', 'sideburnscode',
              'bodytypecode', 'shoetypecode', 'shoecolorcode1', 'shoecolorcode2', 'gkglovetypecode',
              'jerseystylecode', 'jerseysleevelengthcode', 'socklengthcode', 'hashighqualityhead')
TAKERS = {'penalty': 'penaltytakerid', 'free_kick': 'freekicktakerid', 'long_free_kick': 'longkicktakerid',
          'left_corner': 'leftcornerkicktakerid', 'right_corner': 'rightcornerkicktakerid'}

# player traits: bits of players.trait1 / trait2 (bit -> key); bits not listed (trait2 11 and 12 in the clean game)
# are kept as the row has them
TRAITS1 = ('inflexible', 'long_throws', 'powerful_free_kicks', 'diver', 'injury_prone', 'injury_free',
           'avoids_weak_foot', 'dives_into_tackles', 'beat_defensive_line', 'selfish', 'leadership',
           'argues_with_officials', 'early_crosser', 'finesse_shot', 'flair', 'long_passer', 'long_shot_taker',
           'technical_dribbler', 'playmaker', 'pushes_up_for_corners', 'puncher', 'gk_long_thrower', 'power_header',
           'gk_one_on_one', 'giant_throw', 'outside_foot_shot', 'crowd_favourite', 'swerve_passer', 'second_wind',
           'acrobatic_clearance')
TRAITS2 = ('fancy_feet', 'fancy_passes', 'fancy_flicks', 'stutter_penalty', 'chipped_penalty', 'bicycle_kicks',
           'diving_header', 'driven_pass', 'gk_flat_kick', 'one_club_player', 'team_player')
TRAITS = {**{k: ('trait1', i) for i, k in enumerate(TRAITS1)}, **{k: ('trait2', i) for i, k in enumerate(TRAITS2)}}

# new players
FIRST_FREE_PLAYER = 300001  # new players get the first id from here the game does not use (nor any file named after it)
MAX_PLAYER_ID = 524287      # players.playerid has 19 bits
MODEL_PLAYER = 139541       # the row a player made from scratch starts from (a plain central midfielder of the game, no traits)
PLAYER_FACE_FILES = {       # a player's own face (headclasscode 0): every file named after his id
    'head': 'data/sceneassets/heads/head_{}_0.rx3',
    'face': 'data/sceneassets/faces/face_{}_0_0_0_0_0_0_0_0_textures.rx3',
    'eyes': 'data/sceneassets/heads/eyes_{}_0_textures.rx3',
    'hair': 'data/sceneassets/hair/hair_{}_0_0.rx3',
    'hair_textures': 'data/sceneassets/hair/hair_{}_0_textures.rx3',
    'hairlod': 'data/sceneassets/hairlod/hairlod_{}_0_0.rx3',
}
PHOTO_SIZE = (128, 128)  # heads/p<id>.dds: 128x128 DXT5

# player accessories: accessorycode1-4 + accessorycolourcode1-4 are 4 slots of a list (any order); each code is one
# thing on one side of the body, checked in the game. Places: where the screen shows them, the codes each can hold.
ACCESSORY_PLACES = {
    'ankle_left': (14,), 'ankle_right': (15,),
    'hands': (16, 18, 19),                     # gloves; 18/19 = a pair of goalkeeper gloves (colour = glove model)
    'wrist_left': (8, 6, 24, 26, 4),           # band, bandage, wide band, bracelet, watch
    'wrist_right': (9, 7, 25, 27, 5),
    'knee_left': (10, 12), 'knee_right': (11, 13),  # tape, knee support
    'fingers_left': (22,), 'fingers_right': (23,),
    'hand_left': (28, 30), 'hand_right': (29, 31),  # yellow / red card held in the hand
    'ear': (2,),                               # earphone
}
ACCESSORY_SLOTS = 4
ACCESSORY_COLOURS = tuple(range(13))           # 13-15 show as white
ACCESSORY_TEXTURED = (2, 4, 5, 28, 29, 30, 31)  # drawn from their own picture: only colour 0 (others: checkered)
ACCESSORY_MODEL = (18, 19)                     # the colour picks the glove model
# kit look codes: the values the game has (the rest show as the first one)
KIT_CODE_VALUES = {'jerseysleevelengthcode': (0, 1), 'socklengthcode': (0, 1, 2), 'jerseystylecode': (0, 1),
                   'hasseasonaljersey': (0, 1, 2, 3, 4)}  # hasseasonaljersey only shows in cold / snow matches

DATE_ZERO = datetime.date(1582, 10, 14)  # database dates are days since this day
SUSPECT_SHARE = 0.20  # a birth date shared by more than this share of the players is a placeholder


def to_date(days) -> str | None:
    if days is None:
        return None
    try:
        return (DATE_ZERO + datetime.timedelta(days=int(days))).isoformat()
    except (ValueError, OverflowError):
        return None


def position_name(code) -> str | None:
    return POSITIONS[code] if isinstance(code, int) and 0 <= code < len(POSITIONS) else None


class SourceError(Exception):
    """The folder is not a FIFA 14 installation this reader understands."""


class Fifa14Source:
    def __init__(self, path: str, language: str = DEFAULT_LANGUAGE, files: GameFiles | None = None):
        try:
            self.files = files or GameFiles(path)
        except FileNotFoundError as e:
            raise SourceError(f'game folder not found: {e}') from e
        meta_raw, db_raw = self.files.read(META), self.files.read(DATABASE)
        if meta_raw is None or db_raw is None:
            raise SourceError('database not found (data/db/fifa_ng_db.db and fifa_ng_db-meta.xml)')
        self.database_source = self.files.where(DATABASE)
        try:
            self.tables = t3db.read_tables(db_raw, t3db.load_meta(meta_raw))
        except t3db.DatabaseError as e:
            raise SourceError(str(e)) from e
        self.language = language
        self._index()
        self.warnings: list[str] = []  # language databases that could not be read
        self.team_names = self._names(TEAM_NAME_STRINGS, ('TeamName_', 'CT_TeamName_'))
        self.league_names = self._names(LEAGUE_NAME_STRINGS, ('LeagueName_', 'Labbr_', 'TrophyName_'))

    # ---- database -------------------------------------------------------------------------------------------

    def rows(self, table: str) -> list[dict]:
        return self.tables.get(table, {}).get('rows', [])

    def _index(self):
        self._lookups: dict = {}
        self.leagues = {r['leagueid']: r for r in self.rows('leagues')}
        self.teams = {r['teamid']: r for r in self.rows('teams')}
        self.players = {r['playerid']: r for r in self.rows('players')}
        self.nations = {r['nationid']: r for r in self.rows('nations')}
        self.name_texts = {r['nameid']: r['name'] for r in self.rows('playernames')}
        self.edited_names = {r['playerid']: r for r in self.rows('editedplayernames')}
        self.league_teams: dict[int, list[int]] = {}
        self.team_leagues: dict[int, list[int]] = {}
        for link in self.rows('leagueteamlinks'):
            self.league_teams.setdefault(link['leagueid'], []).append(link['teamid'])
            self.team_leagues.setdefault(link['teamid'], []).append(link['leagueid'])
        self.team_links: dict[int, list[dict]] = {}
        self.player_links: dict[int, list[dict]] = {}
        for link in self.rows('teamplayerlinks'):
            self.team_links.setdefault(link['teamid'], []).append(link)
            self.player_links.setdefault(link['playerid'], []).append(link)
        self.team_kits: dict[int, list[dict]] = {}
        for row in self.rows('teamkits'):
            self.team_kits.setdefault(row['teamtechid'], []).append(row)
        counts: dict[int, int] = {}
        for p in self.players.values():
            if p.get('birthdate') is not None:
                counts[p['birthdate']] = counts.get(p['birthdate'], 0) + 1
        total = len(self.players) or 1
        self.suspect_birthdates = {d for d, n in counts.items() if n / total > SUSPECT_SHARE}
        self.national_teams = {n['teamid']: nid for nid, n in self.nations.items() if n.get('teamid', -1) >= 0}

    def tables_with(self, column: str) -> list[str]:
        return [name for name, t in self.tables.items() if column in t['fields']]

    def related_rows(self, column: str, value: int, skip=()) -> dict[str, list[dict]]:
        """{table: rows} of every table with `column` == value (the raw layer of an exported item)."""
        out = {}
        for name in self.tables_with(column):
            if name in skip:
                continue
            found = self._by(name, column).get(value)
            if found:
                out[name] = found
        return out

    def _by(self, table: str, column: str) -> dict:
        """{value: rows} of one table by one column (built once, on first use)."""
        key = (table, column)
        if key not in self._lookups:
            index: dict = {}
            for r in self.rows(table):
                index.setdefault(r.get(column), []).append(r)
            self._lookups[key] = index
        return self._lookups[key]

    # ---- language strings --------------------------------------------------------------------------------

    def languages(self) -> list[str]:
        found = {os.path.basename(p)[:-3] for p in self.files.list('data/loc/') if p.endswith('.db')}
        return sorted(n for n in found if not n.endswith('_upd'))

    def _names(self, table: dict, starts: tuple) -> dict[int, dict[str, str]]:
        """{id: {key: text}} of the language database; the _upd database overrides the base one."""
        strings = {}
        for name in (self.language, f'{self.language}_upd'):
            raw = self.files.read(f'data/loc/{name}.db')
            if raw is None:
                continue
            try:
                strings.update(t3db.read_strings(raw, lambda sid: sid.startswith(starts)))
            except t3db.DatabaseError as e:
                self.warnings.append(f'data/loc/{name}.db: {e}')
        prefixes = sorted(table.items(), key=lambda kv: -len(kv[1]))  # longest first: Abbr15 before ''
        out: dict[int, dict[str, str]] = {}
        for sid, text in strings.items():
            for key, prefix in prefixes:
                rest = sid[len(prefix):]
                if sid.startswith(prefix) and rest.isdigit():
                    if text:
                        out.setdefault(int(rest), {})[key] = text
                    break
        return out

    # ---- names --------------------------------------------------------------------------------------------

    def player_names(self, pid: int) -> dict[str, str]:
        """first, last, common and jersey names (edited names of the database win over the name table)."""
        p = self.players.get(pid, {})
        out = {
            'first': self.name_texts.get(p.get('firstnameid'), ''),
            'last': self.name_texts.get(p.get('lastnameid'), ''),
            'common': self.name_texts.get(p.get('commonnameid'), ''),
            'jersey': self.name_texts.get(p.get('playerjerseynameid'), ''),
        }
        edited = self.edited_names.get(pid)
        if edited:
            for key, column in (('first', 'firstname'), ('last', 'surname'), ('common', 'commonname'),
                                ('jersey', 'playerjerseyname')):
                if edited.get(column):
                    out[key] = edited[column]
        return {k: v for k, v in out.items() if v}

    def player_display_name(self, pid: int) -> str:
        n = self.player_names(pid)
        return n.get('common') or ' '.join(x for x in (n.get('first'), n.get('last')) if x) or f'#{pid}'

    def team_all_names(self, tid: int) -> dict[str, str]:
        out = {'database': self.teams.get(tid, {}).get('teamname') or ''}
        out.update(self.team_names.get(tid, {}))
        return {k: v for k, v in out.items() if v}

    def team_display_name(self, tid: int) -> str:
        n = self.team_all_names(tid)
        return n.get('full') or n.get('database') or f'#{tid}'

    def league_all_names(self, lid: int) -> dict[str, str]:
        out = {'database': self.leagues.get(lid, {}).get('leaguename') or ''}
        out.update(self.league_names.get(lid, {}))
        return {k: v for k, v in out.items() if v}

    def league_display_name(self, lid: int) -> str:
        n = self.league_all_names(lid)
        return n.get('full') or n.get('database') or f'#{lid}'

    def nation_name(self, nid) -> str | None:
        return (self.nations.get(nid) or {}).get('nationname') or None

    # ---- files --------------------------------------------------------------------------------------------

    def _existing(self, path: str) -> str | None:
        return path if self.files.exists(path) else None

    def crest_path(self, tid: int) -> str | None:
        return self._existing(CREST.format(tid))

    def photo_path(self, pid: int) -> str | None:
        return self._existing(PHOTO.format(pid))

    def league_image_paths(self, lid: int) -> dict[str, str]:
        return {k: p.format(lid) for k, p in LEAGUE_IMAGES.items() if self.files.exists(p.format(lid))}

    @cached_property
    def _flag_folder(self) -> str | None:
        sizes = {m.group(0): int(m.group(1)) * int(m.group(2))
                 for p in self.files.list('data/ui/imgassets/flags') if (m := FLAG_FOLDERS.match(p))}
        return max(sizes, key=sizes.get) if sizes else None

    def flag_path(self, nid) -> str | None:
        folder = self._flag_folder
        return self._existing(f'{folder}f_{nid}.dds') if folder else None

    def current_kits(self, tid: int) -> dict[int, dict]:
        """{kit type: teamkits row} of the current kits (year 0: the ones in kit_<team>_<type>_0.rx3)."""
        return {r['teamkittypetechid']: r for r in self.team_kits.get(tid, []) if r.get('year', 0) == 0}

    def kit_paths(self, tid: int) -> dict[int, str]:
        """{kit type: game path} of every current kit file of the team."""
        prefix = f'data/sceneassets/kit/kit_{tid}_'
        out = {}
        for path in self._kit_files.get(tid, []):
            m = re.fullmatch(re.escape(prefix) + r'(\d+)_0\.rx3', path)
            if m:
                out[int(m.group(1))] = path
        return dict(sorted(out.items()))

    @cached_property
    def _kit_files(self) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for path in self.files.list('data/sceneassets/kit/kit_'):
            m = re.match(r'data/sceneassets/kit/kit_(\d+)_', path)
            if m:
                out.setdefault(int(m.group(1)), []).append(path)
        return out

    def name_font_path(self, font) -> str | None:
        return self._existing(NAME_FONT.format(font)) if font is not None else None

    def number_font_path(self, font, color) -> str | None:
        return self._existing(NUMBER_FONT.format(font, color)) if font is not None and color is not None else None

    @cached_property
    def _face_files(self) -> dict[int, dict[str, str]]:
        """{player id: {game path: kind}} of every head, eyes, face, hair and hair LOD file."""
        out: dict[int, dict[str, str]] = {}
        for folder in FACE_FOLDERS:
            for path in self.files.list(folder):
                m = FACE_FILE.match(path)
                if m:
                    out.setdefault(int(m.group(2)), {})[path] = m.group(1)
        return out

    def face_paths(self, pid: int) -> dict[str, str] | None:
        """{game path: kind} of the player's real face, or None when the game has no real face for him."""
        files = self._face_files.get(pid)
        if not files or not all(k in files.values() for k in FACE_REQUIRED):
            return None
        return dict(sorted(files.items()))

    def has_face(self, pid: int) -> bool:
        return self.face_paths(pid) is not None
