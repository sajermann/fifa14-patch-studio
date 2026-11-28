"""What the screens show, straight from SQLite: the originals cache (main database) with the user's project attached
as `p`. Filters, search, sorting and pages are SQL; only the page being shown is loaded."""
import json
import math
import sqlite3

from f14mod import catalog, fields, fifa14, formation, stadium3d, stadium_files
from f14mod.overall import compute_overall
from f14mod.teamkits import MASKS, MODEL_TEAM

PAGE_SIZES = (25, 50, 100)
# a created team made from scratch, in the views (source `s` = p.team_sources): blank, no model values
BLANK = '(s.team_id IS NOT NULL AND s.template IS NULL AND s.copy = 0)'
DEFAULT_PAGE_SIZE = 50
FALLBACK_LANG = 'eng_us'


def _saved_sql(kind: str, alias: str, field: str) -> str:
    return (f"(SELECT json_extract(value, '$') FROM p.fields WHERE kind = '{kind}' AND id = {alias}.id "
            f"AND field = '{field}')")


def _team_colors_sql() -> str:
    """The three kit colors of a team (the project's value, else the game's), one JSON [r, g, b] column each."""
    return ', '.join(
        f"COALESCE({_saved_sql('team', 't', f'teamcolor{n}')}, json_array(json_extract(t.raw, '$.teamcolor{n}r'), "
        f"json_extract(t.raw, '$.teamcolor{n}g'), json_extract(t.raw, '$.teamcolor{n}b'))) AS color{n}"
        for n in (1, 2, 3))


def _blank_team_raw(raw: str) -> str:
    """The row a team made from scratch shows (the model team's, its values blank: fields.TEAM_REQUIRED and the
    captain and takers empty, the tactics at fields.TEAM_DEFAULTS)."""
    columns = [f'{f}{c}' if f.startswith('teamcolor') else f for f in fields.TEAM_REQUIRED if f != 'formation'
               for c in ('rgb' if f.startswith('teamcolor') else ('',))]
    columns += [f.name for f in fields.TEAM if f.kind == 'roster']
    pairs = [f"'$.{c}', NULL" for c in columns] + [f"'$.{c}', {v}" for c, v in fields.TEAM_DEFAULTS.items()]
    return f"json_set(COALESCE({raw}, '{{}}'), {', '.join(pairs)})"


def _blank_player_raw(raw: str) -> str:
    """The row a player made from scratch shows (the model player's with fields.player_blank_columns over it)."""
    pairs = [f"'$.{c}', {'NULL' if v is None else v}" for c, v in fields.player_blank_columns().items()]
    return f"json_set(COALESCE({raw}, '{{}}'), {', '.join(pairs)})"


# a created player made from scratch, in the views (source `s` = p.player_sources)
BLANK_PLAYER = '(s.player_id IS NOT NULL AND s.template IS NULL)'


def _overall_sql(alias: str, raw: str, stored: str) -> str:
    """The player's overall: the game's own value, or (a player with saved edits) the one the attributes give."""
    saved = f"FROM p.fields WHERE kind = 'player' AND id = {alias}.id"
    return (f"(CASE WHEN EXISTS (SELECT 1 {saved}) THEN overall_of({raw}, (SELECT json_group_object(field, "
            f"json_extract(value, '$')) {saved}), {stored}) ELSE {stored} END)")


# the originals and what the project created, as one table each (temporary views of this connection)
VIEWS = [
    f"""CREATE TEMP VIEW v_nations AS
        SELECT id, name, 0 AS is_new, has_flag, search, confederation FROM nations
        UNION ALL
        SELECT c.id, COALESCE(
            (SELECT text FROM p.country_names WHERE country_id = c.id AND key = 'full' AND lang = '*'),
            (SELECT text FROM p.country_names WHERE country_id = c.id AND key = 'full' ORDER BY lang LIMIT 1),
            'Country ' || c.id), 1, 1, '',
            COALESCE({_saved_sql('country', 'c', 'confederation')},
                     (SELECT confederation FROM nations WHERE id = {_saved_sql('country', 'c', 'copy_of')}),
                     (SELECT confederation FROM nations WHERE id = {fifa14.TEMPLATE_NATION}))
        FROM p.created c WHERE c.kind = 'country'""",
    f"""CREATE TEMP VIEW v_leagues AS
        SELECT l.id, l.db_name, COALESCE({_saved_sql('league', 'l', 'countryid')}, l.country_id) AS country_id,
               COALESCE({_saved_sql('league', 'l', 'level')}, l.level) AS level, l.has_logo, l.search, l.raw,
               0 AS is_new
        FROM leagues l
        UNION ALL
        SELECT c.id, {_saved_sql('league', 'c', 'leaguename')}, {_saved_sql('league', 'c', 'countryid')},
               COALESCE({_saved_sql('league', 'c', 'level')}, 1), 0, '', '{{}}', 1
        FROM p.created c WHERE c.kind = 'league'""",
    # a created team shows the values of the team it starts from (its row is a copy of that one in the patch); one
    # made from scratch (a source without template) shows its fields blank and no ratings until it has players
    f"""CREATE TEMP VIEW v_teams AS
        SELECT id, db_name, overall, attack, midfield, defense, color, national_of, has_crest, search, raw,
               0 AS is_new FROM teams
        UNION ALL
        SELECT c.id, COALESCE(
                   (SELECT text FROM p.team_names WHERE team_id = c.id AND key = 'full' AND lang = '*'),
                   (SELECT text FROM p.team_names WHERE team_id = c.id AND key = 'full' ORDER BY lang LIMIT 1),
                   'Team ' || c.id),
               {', '.join(f"CASE WHEN {BLANK} THEN NULL ELSE t.{c} END" for c in ('overall', 'attack', 'midfield', 'defense'))},
               COALESCE({_saved_sql('team', 'c', 'teamcolor1')}, CASE WHEN {BLANK} THEN NULL ELSE t.color END), NULL,
               1, '', CASE WHEN {BLANK} THEN {_blank_team_raw('t.raw')} ELSE t.raw END, 1
        FROM p.created c LEFT JOIN p.team_sources s ON s.team_id = c.id
             LEFT JOIN teams t ON t.id = COALESCE(s.template, {MODEL_TEAM})
        WHERE c.kind = 'team'""",
    # squads: the game's, a squad the user set (whole), and the model's squad of a created copy not changed yet
    # (`hidden` = the player is left out of the patch in that team only)
    """CREATE TEMP VIEW v_team_players AS
        SELECT team_id, player_id, jersey, position, 0 AS ord, 0 AS hidden FROM team_players
        WHERE team_id NOT IN (SELECT team_id FROM p.team_rosters_set)
        UNION ALL
        SELECT team_id, player_id, jersey, slot, ord, COALESCE(hidden, 0) FROM p.team_rosters
        UNION ALL
        SELECT s.team_id, tp.player_id, tp.jersey, tp.position, 0, 0 FROM p.team_sources s
            JOIN team_players tp ON tp.team_id = s.template
        WHERE s.copy = 1 AND s.team_id NOT IN (SELECT team_id FROM p.team_rosters_set)""",
    # a created player shows the values of the player it starts from (its row is a copy of that one in the patch)
    f"""CREATE TEMP VIEW v_players AS
        SELECT id, name, first, last, common, jersey_name,
               {_overall_sql('players', 'raw', 'overall')} AS overall, potential, position, nationality, birthdate,
               height, has_photo OR EXISTS (SELECT 1 FROM p.pictures WHERE kind = 'player' AND id = players.id
                                            AND slot = 'photo') AS has_photo, search, raw, 0 AS is_new
        FROM players
        UNION ALL
        SELECT c.id, 'Player ' || c.id, NULL, NULL, NULL, NULL,
               {_overall_sql('c', f"(CASE WHEN {BLANK_PLAYER} THEN {_blank_player_raw('t.raw')} ELSE t.raw END)",
                             f'(CASE WHEN {BLANK_PLAYER} THEN NULL ELSE t.overall END)')},
               CASE WHEN {BLANK_PLAYER} THEN {fields.PLAYER_DEFAULTS['potential']} ELSE t.potential END,
               COALESCE({_saved_sql('player', 'c', 'preferredposition1')}, CASE WHEN {BLANK_PLAYER} THEN NULL ELSE t.position END),
               COALESCE({_saved_sql('player', 'c', 'nationality')}, CASE WHEN {BLANK_PLAYER} THEN NULL ELSE t.nationality END),
               CASE WHEN {BLANK_PLAYER} THEN '{fields.PLAYER_DEFAULTS['birthdate']}' ELSE t.birthdate END,
               COALESCE({_saved_sql('player', 'c', 'height')}, CASE WHEN {BLANK_PLAYER} THEN {fields.PLAYER_DEFAULTS['height']} ELSE t.height END),
               EXISTS (SELECT 1 FROM p.pictures WHERE kind = 'player' AND id = c.id AND slot = 'photo'), CAST(c.id AS TEXT),
               CASE WHEN {BLANK_PLAYER} THEN {_blank_player_raw('t.raw')} ELSE t.raw END, 1
        FROM p.created c LEFT JOIN p.player_sources s ON s.player_id = c.id
             LEFT JOIN players t ON t.id = CASE WHEN {BLANK_PLAYER} THEN {fifa14.MODEL_PLAYER} ELSE s.template END
        WHERE c.kind = 'player'""",
    # the stadium each team plays in: the one the user chose, else the game's (a created team: the team it copies)
    f"""CREATE TEMP VIEW v_team_stadiums AS
        SELECT team_id, stadium_id, custom_name FROM team_stadiums
        WHERE team_id NOT IN (SELECT team_id FROM p.team_stadiums)
        UNION ALL
        SELECT c.id, g.stadium_id, NULL FROM p.created c LEFT JOIN p.team_sources s ON s.team_id = c.id
            JOIN team_stadiums g ON g.team_id = CASE WHEN {BLANK} THEN NULL ELSE COALESCE(s.template, {MODEL_TEAM}) END
        WHERE c.kind = 'team' AND c.id NOT IN (SELECT team_id FROM p.team_stadiums)
        UNION ALL
        SELECT t.team_id, t.stadium_id, g.custom_name FROM p.team_stadiums t
            LEFT JOIN team_stadiums g ON g.team_id = t.team_id AND g.stadium_id = t.stadium_id""",
    # the stadiums: the game's and the user's (a created one shows the row of the stadium it starts from, under its
    # own id and without a home team; `source` = the stadium whose files it uses until it has its own; one made from
    # scratch: NULL source and its fields blank until the user fills them)
    f"""CREATE TEMP VIEW v_stadiums AS
        SELECT id, name, raw, 0 AS is_new, id AS source FROM stadiums
        UNION ALL
        SELECT c.id, NULL, CASE WHEN s.template IS NULL
                   THEN json_set(COALESCE(t.raw, '{{}}'), '$.stadiumid', c.id, '$.hometeamid', 0,
                                 '$.countrycode', 0, {', '.join(f"'$.{f}', NULL" for f in fields.STADIUM_REQUIRED)})
                   ELSE json_set(COALESCE(t.raw, '{{}}'), '$.stadiumid', c.id, '$.hometeamid', 0) END, 1,
               s.template
        FROM p.created c LEFT JOIN p.stadium_sources s ON s.stadium_id = c.id
             LEFT JOIN stadiums t ON t.id = COALESCE(s.template, {fifa14.TEMPLATE_STADIUM})
        WHERE c.kind = 'stadium'""",
    """CREATE TEMP VIEW v_league_teams AS
        SELECT league_id, team_id, 0 AS ord, 0 AS hidden FROM league_teams
        WHERE league_id NOT IN (SELECT league_id FROM p.league_members_set)
        UNION ALL
        SELECT league_id, team_id, ord, COALESCE(hidden, 0) FROM p.league_members""",
]

TEAM_NAME_KEYS = list(fifa14.TEAM_NAME_STRINGS)
# 0 home, 1 away, 2 goalkeeper, 3 third; 4, 5, 7, 8 = more outfield kits, named "Alternate" in the kit selection
# (tests GK1/GK2); type 6 shows "undefined" (the game has no name for it), 9 and 10 were not tested
KIT_KINDS = (0, 1, 2, 3, 4, 5, 7, 8)
MAIN_KITS = (0, 1, 2, 3)  # always listed; the others only when the team has them  # full, abbr15, abbr10, abbr7, abbr3, commentary
LEAGUE_NAME_KEYS = list(fifa14.LEAGUE_NAME_STRINGS)


def _overall_of(raw, saved, stored):
    """SQL function: the overall of a player row with the project's edited values over it."""
    row = json.loads(raw or '{}')
    row.update({k: v for k, v in json.loads(saved or '{}').items() if isinstance(v, (int, float))})
    return compute_overall(row) or stored


def connect(catalog_path: str, project_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f'file:{catalog_path}?mode=ro', uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.create_function('fold', 1, catalog.fold, deterministic=True)
    con.create_function('overall_of', 3, _overall_of, deterministic=True)
    con.execute('ATTACH DATABASE ? AS p', (project_path,))
    for view in VIEWS:
        con.execute(view)
    return con


def _team_name(key: str, alias: str = 't') -> str:
    """SQL for a team's shown name: the project's (language, then '*'), then the game's (language, then English),
    then the database name."""
    return f"""COALESCE(
        (SELECT text FROM p.team_names WHERE team_id = {alias}.id AND key = '{key}' AND lang = :lang),
        (SELECT text FROM p.team_names WHERE team_id = {alias}.id AND key = '{key}' AND lang = '*'),
        (SELECT text FROM names WHERE kind = 'team' AND id = {alias}.id AND key = '{key}' AND lang = :lang),
        (SELECT text FROM names WHERE kind = 'team' AND id = {alias}.id AND key = '{key}' AND lang = '{FALLBACK_LANG}'),
        {alias}.db_name)"""


def _league_name(alias: str = 'l', key: str = 'full') -> str:
    return f"""COALESCE(
        (SELECT text FROM p.league_names WHERE league_id = {alias}.id AND key = '{key}' AND lang = :lang),
        (SELECT text FROM p.league_names WHERE league_id = {alias}.id AND key = '{key}' AND lang = '*'),
        (SELECT text FROM names WHERE kind = 'league' AND id = {alias}.id AND key = '{key}' AND lang = :lang),
        (SELECT text FROM names WHERE kind = 'league' AND id = {alias}.id AND key = '{key}' AND lang = '{FALLBACK_LANG}'),
        {_saved('league', alias, 'leaguename')}, {alias}.db_name)"""


def _saved(kind: str, alias: str, field: str) -> str:
    """SQL for one saved field of the project (the value as SQL text/number)."""
    return f"(SELECT json_extract(value, '$') FROM p.fields WHERE kind = '{kind}' AND id = {alias}.id "            f"AND field = '{field}')"


def _real_face(alias: str) -> str:
    """SQL, 1 when the player has a real face: the one the project gave him (a pack's or another player's), else the
    game's own one (a generic face = 0)."""
    return (f"CASE (SELECT json_extract(value, '$.source') FROM p.fields WHERE kind = 'player' AND id = {alias}.id "
            f"AND field = 'face') WHEN 'pack' THEN 1 WHEN 'player' THEN 1 WHEN 'generic' THEN 0 "
            f"ELSE ({alias}.is_new = 0 AND json_extract({alias}.raw, '$.headclasscode') = 0) END")


def _edited(kind: str, alias: str) -> str:
    return f"EXISTS (SELECT 1 FROM p.edited WHERE kind = '{kind}' AND id = {alias}.id)"


def _dates(kind: str, alias: str) -> str:
    """The `created_at` and `updated_at` columns of an entity (ISO 8601, UTC, as the Street Studio sends them; NULL for
    a game entity the project does not change)."""
    return ', '.join(
        f"(SELECT strftime('%Y-%m-%dT%H:%M:%SZ', {col}, 'unixepoch') FROM p.dates WHERE kind = '{kind}' "
        f"AND id = {alias}.id) AS {col}" for col in ('created_at', 'updated_at'))


def _flag(table: str, kind: str, alias: str) -> str:
    """1 when the entity is hidden by the project (`hidden`: a created one is out of the patch, an original one is
    hidden in the game)."""
    return f"EXISTS (SELECT 1 FROM p.{table} WHERE kind = '{kind}' AND id = {alias}.id)"


def _in_country(alias: str, country: str) -> str:
    """The league `alias` shows in `country`: its own country or one of the extra countries saved for it."""
    return (f"({alias}.country_id = {country} OR EXISTS (SELECT 1 FROM p.fields f, json_each(f.value) j "
            f"WHERE f.kind = 'league' AND f.id = {alias}.id AND f.field = 'extra_countries' AND j.value = {country}))")


def _player_name(alias: str = 'pl') -> str:
    """The shown name: the common name (saved, then the game's), else first + last (saved or the game's)."""
    first, last = _saved('player', alias, 'name.first'), _saved('player', alias, 'name.last')
    return f"""COALESCE({_saved('player', alias, 'name.common')},
        CASE WHEN {alias}.common IS NULL AND ({first} IS NOT NULL OR {last} IS NOT NULL)
             THEN TRIM(COALESCE({first}, {alias}.first, '') || ' ' || COALESCE({last}, {alias}.last, '')) END,
        {alias}.name)"""


def _first_league(team_alias: str = 't') -> str:
    return f'(SELECT MIN(league_id) FROM v_league_teams WHERE team_id = {team_alias}.id)'


def _search(column: str, q: str, params: dict) -> str:
    words = catalog.fold(q).split()
    parts = []
    for i, w in enumerate(words[:8]):
        params[f'w{i}'] = f'%{w}%'
        parts.append(f'{column} LIKE :w{i}')
    return ' AND '.join(parts)


def _page(con, select: str, where: list[str], params: dict, sorts: dict[str, str], sort: str | None,
          direction: str | None, default: tuple[str, str], page_no: int, size: int, new_first: bool = False) -> dict:
    """One page of `select`. With `new_first` (the select has an `is_new` column) the user's created items come
    before the game's, whatever the sort, and `own_ids` lists, across every page, the ones of the project (created, or
    edited when the select has an `edited` column): what the list's checkboxes can pick."""
    key, default_dir = default
    if sort in sorts:
        key = sort
        default_dir = 'asc' if sort in ('name', 'league', 'team', 'nationality', 'country') else 'desc'
    desc = (direction or default_dir) == 'desc'
    size = size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE
    clause = f"WHERE {' AND '.join(where)}" if where else ''
    total = con.execute(f'SELECT COUNT(*) FROM ({select} {clause})', params).fetchone()[0]
    pages = max(1, math.ceil(total / size))
    page_no = min(max(1, page_no), pages)
    order = sorts[key]
    first = 'is_new DESC, ' if new_first else ''
    rows = con.execute(
        f'SELECT * FROM ({select} {clause}) ORDER BY {first}({order}) IS NULL, {order} {"DESC" if desc else "ASC"}, id '
        f'LIMIT :limit OFFSET :offset', {**params, 'limit': size, 'offset': (page_no - 1) * size}).fetchall()
    out = {'items': [dict(r) for r in rows], 'total': total, 'page': page_no, 'size': size, 'pages': pages,
           'sort': key, 'dir': 'desc' if desc else 'asc'}
    if new_first:
        mine = 'is_new OR edited' if ' AS edited' in select else 'is_new'
        out['own_ids'] = [r[0] for r in con.execute(
            f'SELECT id FROM ({select} {clause}) WHERE {mine} ORDER BY {order} {"DESC" if desc else "ASC"}, id', params)]
    return out


# ---- lists ----------------------------------------------------------------------------------------------------------

def leagues(con, lang: str, q='', sort=None, direction=None, page=1, size=DEFAULT_PAGE_SIZE,
            country: int | None = None, ids: list[int] | None = None, level: int | None = None,
            origin: str | None = None, status: str | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT l.id, {_league_name()} AS name, l.db_name, l.level, l.country_id,
                 (SELECT {_country_name()} FROM v_nations n WHERE n.id = l.country_id) AS country, l.has_logo, l.is_new,
                 (SELECT COUNT(*) FROM v_league_teams WHERE league_id = l.id) AS team_count,
                 {_edited('league', 'l')} AS edited, {_dates('league', 'l')}, l.search AS search,
                 {_flag('hidden', 'league', 'l')} AS hidden,
                 COALESCE((SELECT g.country_id FROM leagues g WHERE g.id = l.id) IN (0, {', '.join(map(str, fifa14.UNLISTED_NATIONS))}), 0) AS game_hidden,
                 (SELECT value FROM p.fields WHERE kind = 'league' AND id = l.id AND field = 'extra_countries')
                     AS extra_countries,
                 (SELECT value FROM p.fields WHERE kind = 'league' AND id = l.id AND field = 'hidden_in_countries')
                     AS hidden_in_countries,
                 (SELECT updated_at FROM p.pictures WHERE kind = 'league' AND id = l.id AND slot = 'logo') AS own_logo
                 FROM v_leagues l"""
    where = []
    if country is not None:
        params['country'] = country
        where.append(_in_country('l', ':country'))
    if ids is not None:  # these leagues only (a list the page is editing)
        listed = ','.join(str(int(i)) for i in ids) or 'NULL'
        where.append(f'l.id IN ({listed})')
    if q.strip():
        where.append(_search('fold(name) || \' \' || search', q, params))
    if level is not None:
        params['level'] = level
        where.append('level = :level')
    # the same origin and status filters as the countries list
    if origin == 'project':
        where.append('(is_new = 1 OR edited)')
    elif origin == 'original':
        where.append('is_new = 0')
    if status == 'visible':
        where.append('NOT (hidden OR game_hidden)')
    elif status == 'hidden':
        where.append('(hidden OR game_hidden)')
    sorts = {'name': 'fold(name)', 'id': 'id', 'level': 'level', 'country': 'fold(country)',
             'team_count': 'team_count', 'created_at': 'created_at',
             'updated_at': 'updated_at'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size, new_first=True)
    countries_hidden = {r[0] for r in con.execute("SELECT id FROM p.hidden WHERE kind = 'country'")}
    for r in out['items']:
        r.pop('search', None)
        r['edited'] = bool(r['edited'])
        r['is_new'] = bool(r['is_new'])
        r['hidden'] = bool(r['hidden'])
        r['game_hidden'] = bool(r['game_hidden'])  # the game itself never lists it
        r['extra_countries'] = json.loads(r['extra_countries']) if r['extra_countries'] else []
        r['hidden_in_countries'] = json.loads(r['hidden_in_countries']) if r['hidden_in_countries'] else []
        r['has_logo'] = bool(r['has_logo'] or r['own_logo'])
        # same rule as the league detail: every country it shows in is out of the patch (or out there only)
        shown_in = [c for c in dict.fromkeys([r['country_id'], *r['extra_countries']]) if c]
        gone = countries_hidden | set(r['hidden_in_countries'])
        r['hidden_by_countries'] = bool(shown_in) and all(c in gone for c in shown_in)
        r['adboard_id'] = adboard_of(con, 'league', r['id'])  # the league's board (None = the game's boards)
    return out


def _kit_count_sql(alias: str = 't') -> str:
    """How many kits the team has, by the rule of team_kits(): the kits the user set, the game's kit files of the
    team (or of the team a created copy starts from), and the three generic kits of a team made from scratch."""
    copy_of = f'(SELECT s.template FROM p.team_sources s WHERE s.team_id = {alias}.id AND s.copy = 1)'
    return f"""(SELECT COUNT(*) FROM (
        SELECT kind FROM p.team_kits WHERE team_id = {alias}.id
        UNION SELECT kind FROM team_kits
              WHERE team_id = (CASE WHEN {alias}.is_new THEN {copy_of} ELSE {alias}.id END)
        UNION SELECT value FROM json_each('[0, 1, 2]') WHERE {alias}.is_new AND {copy_of} IS NULL))"""


def teams(con, lang: str, q='', league: int | None = None, edited: bool | None = None, sort=None, direction=None,
          page=1, size=DEFAULT_PAGE_SIZE, only: int | None = None, ids: list[int] | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT t.id, {_team_name('full')} AS name, {_team_name('abbr15')} AS abbr15,
                 {_team_name('abbr3')} AS abbr3, t.overall, t.attack, t.midfield, t.defense, t.color, t.has_crest,
                 {_team_colors_sql()},
                 t.national_of, {_first_league()} AS league_id,
                 (SELECT {_league_name('l')} FROM v_leagues l WHERE l.id = {_first_league()}) AS league,
                 (SELECT COUNT(*) FROM v_team_players WHERE team_id = t.id) AS player_count,
                 {_kit_count_sql()} AS kit_count,
                 {_edited('team', 't')} AS edited, {_dates('team', 't')},
                 {_flag('hidden', 'team', 't')} AS hidden, t.is_new,
                 (SELECT updated_at FROM p.pictures WHERE kind = 'team' AND id = t.id AND slot = 'crest') AS own_crest,
                 t.search AS search
                 FROM v_teams t"""
    where = []
    if only is not None:
        params['only'] = only
        where.append('id = :only')
    if ids is not None:  # these teams only (a list the page is editing)
        listed = ','.join(str(int(i)) for i in ids) or 'NULL'
        where.append(f'id IN ({listed})')
    if league is not None:
        params['league'] = league
        where.append('id IN (SELECT team_id FROM v_league_teams WHERE league_id = :league)')
    if edited is not None:
        where.append('edited = 1' if edited else 'edited = 0')
    if q.strip():
        where.append(_search("fold(name) || ' ' || fold(abbr15) || ' ' || search", q, params))
    sorts = {'name': 'fold(name)', 'id': 'id', 'overall': 'overall', 'league': 'fold(league)',
             'player_count': 'player_count', 'kit_count': 'kit_count', 'created_at': 'created_at',
             'updated_at': 'updated_at'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size, new_first=True)
    for r in out['items']:
        r.pop('search', None)
        r['color'] = json.loads(r['color']) if r['color'] else None
        r['colors'] = [c for c in (json.loads(r.pop(f'color{n}') or 'null') for n in (1, 2, 3))
                       if c and None not in c]
        r['has_crest'] = bool(r['has_crest'])
        r['edited'] = bool(r['edited'])
        r['hidden'] = bool(r['hidden'])
        r['is_new'] = bool(r['is_new'])
    return out


def players(con, lang: str, q='', team: int | None = None, position: int | None = None, sort=None, direction=None,
            page=1, size=DEFAULT_PAGE_SIZE, origin: str | None = None, status: str | None = None,
            face: str | None = None) -> dict:
    params: dict = {'lang': lang}
    club = '(SELECT MIN(tp.team_id) FROM v_team_players tp JOIN v_teams x ON x.id = tp.team_id ' \
           'WHERE tp.player_id = pl.id AND x.national_of IS NULL)'
    select = f"""SELECT pl.id, {_player_name()} AS name, pl.overall, pl.potential, pl.position, pl.birthdate, pl.height,
                 pl.nationality, (SELECT {_country_name()} FROM v_nations n WHERE n.id = pl.nationality) AS nationality_name,
                 pl.has_photo, {_real_face('pl')} AS has_face, {club} AS team_id,
                 (SELECT {_team_name('abbr15')} FROM v_teams t WHERE t.id = {club}) AS team,
                 {_edited('player', 'pl')} AS edited, {_dates('player', 'pl')}, pl.is_new, {_flag('hidden', 'player', 'pl')} AS hidden,
                 pl.raw, pl.search || ' ' || fold({_player_name()}) AS search_all
                 FROM v_players pl"""
    where = []
    if team is not None:
        params['team'] = team
        where.append('id IN (SELECT player_id FROM v_team_players WHERE team_id = :team)')
    if position is not None:
        params['position'] = position
        where.append('position = :position')
    if origin == 'project':
        where.append('is_new = 1')
    elif origin == 'original':
        where.append('is_new = 0')
    if status == 'edited':
        where.append('edited = 1')
    if face in ('yes', 'no'):  # with / without a real face (the game's, a pack's or another player's)
        where.append(f"has_face = {1 if face == 'yes' else 0}")
    if q.strip():
        where.append(_search('search_all', q, params))
    sorts = {'name': 'fold(name)', 'id': 'id', 'overall': 'overall', 'potential': 'potential',
             'position': 'position', 'team': 'fold(team)', 'height': 'height', 'birthdate': 'birthdate',
             'created_at': 'created_at', 'updated_at': 'updated_at'}
    out = _page(con, select, where, params, sorts, sort, direction, ('overall', 'desc'), page, size, new_first=True)
    for r in out['items']:
        r.pop('search', None)
        r.pop('search_all', None)
        r.pop('raw', None)
        for key in ('has_photo', 'has_face', 'edited', 'is_new', 'hidden'):
            r[key] = bool(r[key])
        r['position_name'] = fifa14.position_name(r['position'])
    return out


# ---- details --------------------------------------------------------------------------------------------------------

def languages(con) -> list[str]:
    return [r[0] for r in con.execute('SELECT code FROM languages ORDER BY code')]


def _names(con, kind: str, oid: int) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for r in con.execute('SELECT key, lang, text FROM names WHERE kind = ? AND id = ?', (kind, oid)):
        out.setdefault(r['key'], {})[r['lang']] = r['text']
    return out


def _project_fields(con, kind: str, oid: int) -> dict:
    return {r['field']: json.loads(r['value'])
            for r in con.execute('SELECT field, value FROM p.fields WHERE kind = ? AND id = ?', (kind, oid))}


def _project_names(con, kind: str, oid: int) -> dict[str, dict[str, str]]:
    table, column = {'team': ('team_names', 'team_id'), 'league': ('league_names', 'league_id'),
                     'country': ('country_names', 'country_id'), 'stadium': ('stadium_names', 'stadium_id')}[kind]
    out: dict[str, dict[str, str]] = {}
    for r in con.execute(f'SELECT key, lang, text FROM p.{table} WHERE {column} = ?', (oid,)):
        out.setdefault(r['key'], {})[r['lang']] = r['text']
    return out


def _form(con, kind: str, oid: int, raw: dict, names: dict | None = None) -> dict:
    """What an edit screen needs: the field specs, the game's values and the project's."""
    return {'fields': fields.specs(kind), 'values': fields.original_values(kind, raw, names),
            'saved': _project_fields(con, kind, oid),
            'edited': bool(con.execute('SELECT 1 FROM p.edited WHERE kind = ? AND id = ?', (kind, oid)).fetchone())}


def team(con, lang: str, tid: int) -> dict | None:
    row = con.execute('SELECT * FROM v_teams WHERE id = ?', (tid,)).fetchone()
    if not row:
        return None
    head = teams(con, lang, only=tid)['items'][0]
    saved = _project_names(con, 'team', tid)
    raw = json.loads(row['raw'] or '{}')
    roster = [dict(r) for r in con.execute(
        f"""SELECT pl.id, {_player_name()} AS name, pl.overall, pl.position, tp.jersey, tp.position AS link_position,
                  COALESCE({_saved('player', 'pl', 'name.jersey')}, pl.jersey_name, {_saved('player', 'pl', 'name.last')},
                           pl.last, pl.name) AS back_name,
                  pl.has_photo, pl.is_new, {_edited('player', 'pl')} AS edited, tp.ord, tp.hidden,
                  {_real_face('pl')} AS has_face,
                  {_flag('hidden', 'player', 'pl')} AS player_hidden
           FROM v_team_players tp JOIN v_players pl ON pl.id = tp.player_id WHERE tp.team_id = ?
           ORDER BY tp.ord, tp.position, pl.overall DESC""", (tid,))]
    for r in roster:
        r['position_name'] = fifa14.position_name(r['position'])
        r['link_position_name'] = fifa14.position_name(r['link_position'])
        r['has_photo'] = bool(r['has_photo'])
        # a real face: the one the project gave him (a pack's or another player's), else the game's own one
        r['has_face'] = bool(r['has_face'])
        r['is_new'] = bool(r['is_new'])
        r['edited'] = bool(r['edited'])
        r['hidden'] = bool(r['hidden'])
        r['player_hidden'] = bool(r['player_hidden'])  # the player is out of the patch everywhere
    leagues_of = [dict(r) for r in con.execute(
        f'SELECT l.id, {_league_name()} AS name, l.is_new, (SELECT x.hidden FROM v_league_teams x '
        'WHERE x.league_id = l.id AND x.team_id = :tid) AS hidden FROM v_leagues l WHERE l.id IN '
        '(SELECT league_id FROM v_league_teams WHERE team_id = :tid)', {'lang': lang, 'tid': tid})]
    for r in leagues_of:
        r['hidden'] = bool(r['hidden'])
    source = con.execute('SELECT template, copy FROM p.team_sources WHERE team_id = ?', (tid,)).fetchone()
    template = source['template'] if source else (MODEL_TEAM if head['is_new'] else tid)  # None: from scratch
    copied = bool(source['copy']) if source else not head['is_new']
    look_from = template if copied else None  # where the crest and kits come from when the user set none
    form = _form(con, 'team', tid, raw)
    # the stadium: the one the user chose, else the game's (a created team: the one of the team it starts from)
    stadium_links = [dict(r) for r in con.execute(
        'SELECT stadium_id, custom_name FROM v_team_stadiums WHERE team_id = ? ORDER BY stadium_id', (tid,))]
    own = con.execute('SELECT base FROM formations WHERE team_id = ? AND generic = 0', (template,)).fetchone()
    form['values']['formation'] = own['base'] if own else None
    return {**head, 'db_name': row['db_name'], 'name_keys': TEAM_NAME_KEYS, 'languages': languages(con),
            'stadium_ids': [r['stadium_id'] for r in stadium_links],
            'stadium_changed': con.execute('SELECT 1 FROM p.team_stadiums WHERE team_id = ?', (tid,)).fetchone() is not None,
            # the game's stadium of the team (a created team: the one of the team it starts from): "back to the game's"
            'game_stadium_id': (con.execute('SELECT MIN(stadium_id) FROM team_stadiums WHERE team_id = ?',
                                            (template if head['is_new'] else tid,)).fetchone() or [None])[0],
            'stadium_custom_name': next((r['custom_name'] for r in stadium_links if r['custom_name']), None),
            # a team made from scratch: what it still needs to enter the patch (Project.missing_team_parts)
            'blank': bool(head['is_new'] and source and source['template'] is None and not copied),
            'original_names': {} if head['is_new'] else _names(con, 'team', tid), 'saved_names': saved,
            'roster': roster, 'roster_changed': con.execute(
                'SELECT 1 FROM p.team_rosters_set WHERE team_id = ?', (tid,)).fetchone() is not None,
            'leagues': leagues_of, 'template': template if head['is_new'] else None, 'copied': copied,
            'formations': formations(con) + project_formations(con), 'kits': team_kits(con, tid, look_from, bool(head['is_new'])),
            'adboard_id': adboard_of(con, 'team', tid),
            'max_squad': fifa14.MAX_SQUAD, **form, 'raw': raw}


def team_slots(con, tid: int, is_new: bool) -> list[int]:
    """The 11 lineup positions of a team's formation (the one saved for it, else its own)."""
    saved = con.execute("SELECT json_extract(value, '$') FROM p.fields WHERE kind = 'team' AND id = ? "
                        "AND field = 'formation'", (tid,)).fetchone()
    chosen = saved[0] if saved and saved[0] is not None else None
    if chosen is None:
        source = con.execute('SELECT template FROM p.team_sources WHERE team_id = ?', (tid,)).fetchone()
        template = source['template'] if source else (MODEL_TEAM if is_new else tid)
        own = con.execute('SELECT base FROM formations WHERE team_id = ? AND generic = 0', (template,)).fetchone()
        chosen = own['base'] if own else None
    if chosen is None:
        return []
    if chosen > fifa14.GAME_FORMATIONS:  # one of the project's
        row = con.execute("SELECT value FROM p.fields WHERE kind = 'formation' AND id = ? AND field = 'columns'",
                          (chosen,)).fetchone()
        return formation.positions_of(json.loads(row[0])) if row else []
    row = con.execute('SELECT positions FROM formations WHERE generic = 1 AND formation_id = ?', (chosen,)).fetchone()
    return json.loads(row['positions']) if row else []


def formations(con) -> list[dict]:
    """The game's 33 formations: {id, name, positions (11 position codes)}."""
    return [{'id': r['formation_id'], 'name': r['name'], 'positions': json.loads(r['positions'])}
            for r in con.execute('SELECT * FROM formations WHERE generic = 1 ORDER BY name, formation_id')]


def project_formations(con) -> list[dict]:
    """The formations the user created (f14mod.formation, the Formations screen): {id, name, positions, is_new,
    teams (how many have it)}; any team may take one."""
    out = []
    for (fid,) in con.execute("SELECT id FROM p.created WHERE kind = 'formation' ORDER BY id"):
        values = {r[0]: json.loads(r[1]) for r in con.execute(
            "SELECT field, value FROM p.fields WHERE kind = 'formation' AND id = ?", (fid,))}
        if not values.get('columns'):
            continue
        teams = con.execute("SELECT COUNT(*) FROM p.fields WHERE kind = 'team' AND field = 'formation' AND value = ?",
                            (json.dumps(fid),)).fetchone()[0]
        out.append({'id': fid, 'name': values.get('name') or '', 'positions': formation.positions_of(values['columns']),
                    'is_new': True, 'teams': teams})
    return out


def formation_row(con, fid: int) -> dict | None:
    """One of the game's 33 formations whole: {id, name, positions, columns (f14mod.formation.COLUMNS)}."""
    r = con.execute('SELECT * FROM formations WHERE generic = 1 AND formation_id = ?', (fid,)).fetchone()
    if r is None:
        return None
    return {'id': fid, 'name': r['name'], 'positions': json.loads(r['positions']),
            'columns': json.loads(r['row'] or '{}')}


def team_kits(con, tid: int, look_from: int | None, is_new: bool) -> list[dict]:
    """Each kit type of a team: the user's choice (`config`, with which pictures it has) or where it comes from
    without one: the game's file of the team (or of the team it copies), or, for a team made from scratch, the
    default generic kit."""
    saved = {r['kind']: json.loads(r['config']) for r in con.execute(
        'SELECT kind, config FROM p.team_kits WHERE team_id = ?', (tid,))}
    pictures = {r['slot']: r['updated_at'] for r in con.execute(
        "SELECT slot, updated_at FROM p.pictures WHERE kind = 'team' AND id = ? AND slot LIKE 'kit%'", (tid,))}
    game_kinds = {r[0] for r in con.execute('SELECT kind FROM team_kits WHERE team_id = ?', (look_from or tid,))} \
        if look_from or not is_new else set()
    # the name and numbers the kit has now: its teamkits row (a created team's are its model's; a kit type the team
    # lacks starts from its home kit's)
    source = con.execute('SELECT template FROM p.team_sources WHERE team_id = ?', (tid,)).fetchone()
    row_of = tid if not is_new else (source[0] if source else MODEL_TEAM)
    prints = {r['kind']: json.loads(r['print']) for r in con.execute(
        'SELECT kind, print FROM kit_print WHERE team_id = ?', (row_of,))}
    out = []
    for kind in KIT_KINDS:
        own = {part: pictures.get(f'kit{kind}_{part}') for part in ('jersey', 'shorts', 'mini')}
        current = prints.get(kind) or prints.get(0) or {}
        if kind in saved:
            out.append({'kind': kind, 'config': saved[kind], 'pictures': own, 'default': None, 'print': current})
        elif kind in game_kinds:
            out.append({'kind': kind, 'config': None, 'pictures': own, 'default': 'game', 'print': current})
        elif is_new and not look_from and kind in (0, 1, 2):
            out.append({'kind': kind, 'config': None, 'pictures': own, 'default': 'generic', 'print': current})
        elif kind in MAIN_KITS:
            out.append({'kind': kind, 'config': None, 'pictures': own, 'default': None, 'print': current})
    return out


def kit_fonts(con) -> dict:
    """The game's name fonts ({id, name}), number fonts ({font: [colors]}) and the color each number color shows."""
    out: dict = {'name': [], 'number': {}, 'colors': []}
    for r in con.execute('SELECT * FROM kit_fonts ORDER BY kind, font, color'):
        if r['kind'] == 'name':
            out['name'].append({'id': r['font'], 'name': r['name']})
        else:
            out['number'].setdefault(r['font'], []).append(r['color'])
            if r['font'] == 1 and r['ink']:
                out['colors'].append({'id': r['color'], 'rgb': json.loads(r['ink'])})
    return out


def kit_models(con) -> list[int]:
    """The game's generic mask kits (red = color 1, green = color 2)."""
    return [r[0] for r in con.execute('SELECT team_id FROM team_kits WHERE kind = 0 AND team_id BETWEEN ? AND ? '
                                      'ORDER BY team_id', (MASKS.start, MASKS.stop - 1))]


def free_team_id(con, first: int = fifa14.FIRST_FREE_TEAM) -> int | None:
    """The first team id the game and the project do not use (nor any file named after it), up to the highest id the
    game takes (fifa14.MAX_TEAM_ID); None when none is left."""
    used = {r[0] for r in con.execute('SELECT id FROM v_teams')} | {r[0] for r in con.execute(
        'SELECT team_id FROM team_kits WHERE team_id >= ?', (first,))}
    return next((tid for tid in range(first, fifa14.MAX_TEAM_ID + 1) if tid not in used), None)


def league(con, lang: str, lid: int) -> dict | None:
    row = con.execute('SELECT * FROM v_leagues WHERE id = ?', (lid,)).fetchone()
    if not row:
        return None
    head = con.execute(f"""SELECT l.id, {_league_name()} AS name, l.level, l.country_id,
                           (SELECT {_country_name()} FROM v_nations n WHERE n.id = l.country_id) AS country, l.has_logo, l.is_new,
                           {_dates('league', 'l')}
                           FROM v_leagues l WHERE l.id = :lid""", {'lang': lang, 'lid': lid}).fetchone()
    raw = json.loads(row['raw'])
    if head['is_new']:  # the row the patch writes: a copy of the model league's row with the new league's values
        # (a game without the model league: another of its leagues, as the patch does)
        model = con.execute('SELECT raw FROM leagues ORDER BY id = ? DESC, id LIMIT 1',
                            (fifa14.TEMPLATE_LEAGUE,)).fetchone()
        if model and model['raw']:
            raw = json.loads(model['raw'])
            raw.update({k: v for k, v in fifa14.new_league_values(lid).items() if k in raw})
    original = _names(con, 'league', lid)
    team_ids = [r[0] for r in con.execute(
        'SELECT team_id FROM v_league_teams WHERE league_id = ? ORDER BY ord, team_id', (lid,))]
    hidden_team_ids = [r[0] for r in con.execute(
        'SELECT team_id FROM v_league_teams WHERE league_id = ? AND hidden = 1 ORDER BY ord, team_id', (lid,))]
    custom = con.execute('SELECT 1 FROM p.league_members_set WHERE league_id = ?', (lid,)).fetchone() is not None
    game_team_ids = [] if head['is_new'] else [r[0] for r in con.execute(
        'SELECT team_id FROM league_teams WHERE league_id = ? ORDER BY team_id', (lid,))]
    own_logo = con.execute("SELECT updated_at FROM p.pictures WHERE kind = 'league' AND id = ? AND slot = 'logo'",
                           (lid,)).fetchone()
    hidden = con.execute("SELECT 1 FROM p.hidden WHERE kind = 'league' AND id = ?", (lid,)).fetchone() is not None
    extra = con.execute("SELECT value FROM p.fields WHERE kind = 'league' AND id = ? AND field = 'extra_countries'",
                        (lid,)).fetchone()
    shown_in = [c for c in dict.fromkeys([head['country_id'], *(json.loads(extra[0]) if extra else [])]) if c]
    countries_hidden = {r[0] for r in con.execute("SELECT id FROM p.hidden WHERE kind = 'country'")}
    hidden_here = con.execute("SELECT value FROM p.fields WHERE kind = 'league' AND id = ? "
                              "AND field = 'hidden_in_countries'", (lid,)).fetchone()
    countries_hidden |= set(json.loads(hidden_here[0])) if hidden_here else set()  # left out of the patch there
    game_country = con.execute('SELECT country_id FROM leagues WHERE id = ?', (lid,)).fetchone()
    return {**dict(head), 'db_name': row['db_name'], 'is_new': bool(head['is_new']),
            'has_logo': bool(row['has_logo']) or own_logo is not None, 'game_has_logo': bool(row['has_logo']),
            'own_logo': own_logo[0] if own_logo else None, 'hidden': hidden, 'game_team_ids': game_team_ids,
            'game_hidden': game_country is not None and game_country[0] in (0, *fifa14.UNLISTED_NATIONS),
            # every country the league shows in is hidden in the game (or the league is hidden in it): the league is
            # hidden too
            'hidden_by_countries': bool(shown_in) and all(c in countries_hidden for c in shown_in),
            'names': original, 'original_names': original, 'saved_names': _project_names(con, 'league', lid),
            'name_keys': LEAGUE_NAME_KEYS, 'languages': languages(con), 'team_ids': team_ids,
            'hidden_team_ids': hidden_team_ids,
            'teams_changed': custom, 'teams': teams(con, lang, league=lid, size=100)['items'],
            'adboard_id': adboard_of(con, 'league', lid),
            **_form(con, 'league', lid, raw), 'raw': raw}


def adboard_of(con, kind: str, oid: int) -> int | None:
    """The advertising board linked to a team or a league (f14mod.project.ADBOARD_LINKS), or None."""
    table, column = {'team': ('team_adboards', 'team_id'), 'league': ('league_adboards', 'league_id')}[kind]
    row = con.execute(f'SELECT adboard_id FROM p.{table} WHERE {column} = ?', (oid,)).fetchone()
    return row[0] if row else None


def player(con, lang: str, pid: int) -> dict | None:
    row = con.execute(f'SELECT pl.*, {_player_name()} AS shown FROM v_players pl WHERE pl.id = :pid',
                      {'pid': pid}).fetchone()
    if not row:
        return None
    raw = json.loads(row['raw'] or '{}')
    names = {k: row[k] for k in ('first', 'last', 'common', 'jersey_name') if row[k]}
    links = [dict(r) for r in con.execute(
        f"""SELECT t.id, {_team_name('abbr15')} AS name, tp.jersey, tp.position, tp.hidden, t.national_of, t.is_new,
                   {_flag('hidden', 'team', 't')} AS team_hidden,
                   (SELECT COUNT(*) FROM v_team_players x WHERE x.team_id = t.id AND x.hidden = 0) AS squad_size
            FROM v_team_players tp JOIN v_teams t ON t.id = tp.team_id WHERE tp.player_id = :pid
            ORDER BY t.national_of IS NOT NULL, tp.ord, t.id""",
        {'lang': lang, 'pid': pid})]
    for r in links:
        r['position_name'] = fifa14.position_name(r['position'])
        r['hidden'] = bool(r['hidden'])
        r['team_hidden'] = bool(r['team_hidden'])  # the team is out of the patch everywhere
        r['is_new'] = bool(r['is_new'])
        r['slots'] = team_slots(con, r['id'], r['is_new'])
    source = con.execute('SELECT template FROM p.player_sources WHERE player_id = ?', (pid,)).fetchone()
    form = _form(con, 'player', pid, raw, names)
    is_new = bool(row['is_new'])
    if is_new:  # a created player starts empty: his names are his own
        form['values'].update({k: '' for k in fields.NAME_FIELDS})
        form['values']['face'] = None
    photo = con.execute("SELECT updated_at FROM p.pictures WHERE kind = 'player' AND id = ? AND slot = 'photo'",
                        (pid,)).fetchone()
    return {
        'id': pid, 'name': row['shown'], 'names': names, 'is_new': is_new,
        **dict(con.execute(f"SELECT {_dates('player', 'x')} FROM (SELECT :pid AS id) x", {'pid': pid}).fetchone()),
        'template': source['template'] if source else None,
        'hidden': bool(con.execute("SELECT 1 FROM p.hidden WHERE kind = 'player' AND id = ?", (pid,)).fetchone()),
        'overall': row['overall'], 'potential': row['potential'], 'position': row['position'],
        'position_name': fifa14.position_name(row['position']), 'birthdate': row['birthdate'],
        'height': row['height'], 'weight': raw.get('weight'), 'nationality': row['nationality'],
        'nationality_name': (con.execute(f'SELECT {_country_name()} FROM v_nations n WHERE n.id = :id',
                                         {'lang': lang, 'id': row['nationality']}).fetchone() or [None])[0],
        'has_photo': bool(row['has_photo']), 'own_photo': photo[0] if photo else None,
        'game_face': bool(raw.get('headclasscode') == 0) and not is_new,
        'attributes': {name: raw[col] for col, name in fifa14.ATTRIBUTES.items() if col in raw},
        'teams': links, 'max_squad': fifa14.MAX_SQUAD, **form, 'raw': raw,
    }


STADIUM_NAME_KEYS = list(fifa14.STADIUM_NAME_STRINGS)


def _stadium_language_name(alias: str = 's') -> str:
    """A stadium's text in the names language (StadiumName_<id>): the project's (language, then "All"), then the
    game's (language, then English)."""
    return f"""COALESCE(
        (SELECT text FROM p.stadium_names WHERE stadium_id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM p.stadium_names WHERE stadium_id = {alias}.id AND key = 'full' AND lang = '*'),
        (SELECT text FROM names WHERE kind = 'stadium' AND id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM names WHERE kind = 'stadium' AND id = {alias}.id AND key = 'full' AND lang = '{FALLBACK_LANG}'))"""


def _stadium_name(alias: str = 's') -> str:
    """A stadium's shown name: the database name first (the saved one, then the game's), as the extractor: it is the
    one the game shows (patches leave the StadiumName_ texts behind); then the language text."""
    return f"COALESCE(NULLIF({_saved('stadium', alias, 'name')}, ''), NULLIF({alias}.name, ''), {_stadium_language_name(alias)}, '#' || {alias}.id)"


def _stadium_value(alias: str, column: str) -> str:
    """One column of a stadium: the project's value, else the game's."""
    return f"COALESCE({_saved('stadium', alias, column)}, json_extract({alias}.raw, '$.{column}'))"


def stadiums(con, lang: str, q='', sort=None, direction=None, page=1, size=DEFAULT_PAGE_SIZE,
             country: int | None = None, home: bool | None = None, origin: str | None = None,
             ids: list[int] | None = None) -> dict:
    params: dict = {'lang': lang}
    country_sql = _stadium_value('s', 'countrycode')
    home_sql = _stadium_value('s', 'hometeamid')
    select = f"""SELECT s.id, {_stadium_name()} AS name, {_stadium_language_name()} AS language_name,
                 {country_sql} AS country_id,
                 (SELECT {_country_name()} FROM v_nations n WHERE n.id = {country_sql}) AS country,
                 {home_sql} AS home_team_id,
                 (SELECT {_team_name('full')} FROM v_teams t WHERE t.id = {home_sql}) AS home_team,
                 {_stadium_value('s', 'capacity')} AS capacity,
                 (SELECT COUNT(*) FROM v_team_stadiums x WHERE x.stadium_id = s.id) AS team_count,
                 COALESCE((SELECT MIN(variant) FROM stadium_files f WHERE f.stadium_id = s.source
                           AND f.kind IN ('large', 'small')),
                          CASE WHEN s.is_new AND (EXISTS (SELECT 1 FROM p.pictures WHERE kind = 'stadium' AND id = s.id)
                               OR EXISTS (SELECT 1 FROM p.stadium_scene WHERE stadium_id = s.id
                                          AND name LIKE 'data/ui/%')) THEN 1 END) AS picture,
                 (EXISTS (SELECT 1 FROM p.stadium_scene WHERE stadium_id = s.id) OR EXISTS (
                     SELECT 1 FROM stadium_files f WHERE f.stadium_id = s.source AND f.kind = 'scene')) AS has_3d,
                 {_edited('stadium', 's')} AS edited, s.is_new, {_dates('stadium', 's')},
                 {_flag('hidden', 'stadium', 's')} AS hidden,
                 fold(COALESCE(s.name, '')) AS search
                 FROM v_stadiums s"""
    where = []
    if ids is not None:
        where.append(f"id IN ({','.join(str(int(i)) for i in ids) or 'NULL'})")
    if q.strip():
        where.append(_search("fold(name) || ' ' || fold(COALESCE(language_name, '')) || ' ' || id", q, params))
    if country is not None:
        params['country'] = country
        where.append('country_id = :country')
    if home is not None:
        where.append('home_team_id > 0' if home else 'COALESCE(home_team_id, 0) <= 0')
    if origin == 'project':
        where.append('(edited OR is_new)')
    elif origin == 'original':
        where.append('NOT edited AND NOT is_new')
    sorts = {'name': 'fold(name)', 'id': 'id', 'country': 'fold(country)', 'capacity': 'capacity',
             'team_count': 'team_count', 'created_at': 'created_at',
             'updated_at': 'updated_at'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size, new_first=True)
    for r in out['items']:
        r.pop('search', None)
        r['is_new'] = bool(r['is_new'])
        r['edited'] = bool(r['edited']) and not r['is_new']
        r['has_3d'] = bool(r['has_3d'])
        r['hidden'] = bool(r['hidden'])  # a created stadium left out of the patch (Hide)
    return out


def stadium(con, lang: str, sid: int, files, project=None) -> dict | None:
    """One stadium (the game's or one the user created) with the project's changes over it: names, capacity, year,
    country, home team, the times of day and weather it allows, its menu pictures and scene files (`files` = the
    game's files, to say where each one is and which times of day the 3D preview can show), and the edit form
    (`values` = the game's; a created stadium: the row of the stadium it starts from). `project` (a created stadium's
    own files) is needed for created stadiums."""
    row = con.execute('SELECT id, name, raw, is_new, source FROM v_stadiums WHERE id = ?', (sid,)).fetchone()
    if row is None:
        return None
    is_new = bool(row['is_new'])
    game_raw = json.loads(row['raw'] or '{}')
    saved = _project_fields(con, 'stadium', sid)
    raw = {**game_raw, **fields.to_columns('stadium', saved)}
    shown = con.execute(f'SELECT {_stadium_name()} FROM v_stadiums s WHERE s.id = :id',
                        {'lang': lang, 'id': sid}).fetchone()[0]
    # a created stadium's database name is its full name (builder.add_created), unless the user set one
    names = {'database': raw.get('name') or '' if not is_new or saved.get('name') else ''}
    full = con.execute("SELECT text FROM names WHERE kind = 'stadium' AND id = ? AND key = 'full' AND lang IN (?, ?) "
                       'ORDER BY lang = ? DESC LIMIT 1', (sid, lang, FALLBACK_LANG, lang)).fetchone()
    own = _project_names(con, 'stadium', sid).get('full') or {}
    full_text = own.get(lang) or own.get('*') or (full[0] if full else None)
    if full_text:
        names['full'] = full_text
        if is_new and not names['database']:
            names['database'] = full_text[:60]
    names = {k: v for k, v in names.items() if v}
    country_id = raw.get('countrycode')
    country = con.execute(f'SELECT {_country_name()} FROM v_nations n WHERE n.id = :id',
                          {'lang': lang, 'id': country_id}).fetchone() if country_id else None
    home_id = raw.get('hometeamid')
    home = con.execute(f'SELECT t.id, {_team_name("full")} AS name FROM v_teams t WHERE t.id = :id',
                       {'lang': lang, 'id': home_id}).fetchone() if isinstance(home_id, int) and home_id > 0 else None
    pictures: dict[str, list[int]] = {}
    scene = []
    source = row['source']
    for r in con.execute('SELECT kind, variant, path FROM stadium_files WHERE stadium_id = ? ORDER BY path', (source,)):
        if r['kind'] == 'scene':
            scene.append(r['path'])
        else:
            pictures.setdefault(r['kind'], []).append(r['variant'])
    file_rows = [{'path': p, 'where': files.where(p)} for p in scene]
    times = stadium3d.available(files, sid) if not is_new else []
    own_scene = project.stadium_scene_list(sid) if project is not None else {}
    own_pictures = stadium_files.own_pictures(project, sid) if project is not None else []
    folder_stadium = project.stadium_folder_source(sid) if project is not None else None
    if (is_new or own_scene) and project is not None:
        own_files = {stadium_files.own_name(n, sid): size for n, size in own_scene.items()}
        if own_scene:
            file_rows = [{'path': p, 'where': 'project', 'size': size} for p, size in sorted(own_files.items())
                         if not p.startswith('data/ui/')]
            for p in own_files:
                for kind, regex in fifa14.STADIUM_PICTURES.items():
                    m = regex.match(p)
                    if m:
                        pictures.setdefault(kind, []).append(int(m.group(2)))
        times = stadium3d.available(stadium_files.CreatedStadiumFiles(files, project, sid), sid)
    dates = con.execute(f"SELECT {_dates('stadium', 'x')} FROM (SELECT :id AS id) x", {'id': sid}).fetchone()
    return {
        'id': sid,
        'name': shown,
        'names': names,
        # a created stadium left out of the patch (Hide; the game's stadiums are not hidden)
        'hidden': bool(con.execute("SELECT 1 FROM p.hidden WHERE kind = 'stadium' AND id = ?", (sid,)).fetchone()),
        'capacity': raw.get('capacity'),
        'year_built': raw.get('yearbuilt'),
        'country_id': country_id,
        'country': country[0] if country else None,
        'home_team': dict(home) if home else None,
        'team_count': con.execute('SELECT COUNT(*) FROM v_team_stadiums WHERE stadium_id = ?', (sid,)).fetchone()[0],
        'conditions': fifa14.stadium_conditions(raw),
        'pictures': sorted(set(pictures.get('large') or pictures.get('small') or [])
                           | (set(own_pictures) if is_new else set())),
        'files': file_rows,
        'times': times,  # 3D preview: 1 = day, 3 = night
        'is_new': is_new, **dict(dates),
        # a created stadium: the game stadium it starts from; any stadium: whether the scene is its own (a stadium's
        # folder) and the menu pictures (variants) the user replaced
        'template': source if is_new else None,
        'template_name': (con.execute(f'SELECT {_stadium_name()} FROM v_stadiums s WHERE s.id = :id',
                                      {'lang': lang, 'id': source}).fetchone() or [None])[0] if is_new else None,
        'own_scene': bool(own_scene), 'own_pictures': own_pictures,
        # the game stadium the files of the stadium's folder were made for (its data fit them)
        'folder_stadium': folder_stadium,
        'folder_stadium_name': (con.execute(f'SELECT {_stadium_name()} FROM v_stadiums s WHERE s.id = :id',
                                            {'lang': lang, 'id': folder_stadium}).fetchone() or [None])[0]
        if folder_stadium is not None else None,
        'name_keys': STADIUM_NAME_KEYS, 'languages': languages(con),
        # a created stadium: the game's leftover StadiumName_<id> texts (some free ids have them) are not its own
        'original_names': {} if is_new else _names(con, 'stadium', sid),
        'saved_names': _project_names(con, 'stadium', sid),
        **_form(con, 'stadium', sid, game_raw),
        'raw': raw,
    }


def stadium_teams(con, lang: str, sid: int) -> list[dict]:
    """The teams that play in the stadium (the user's choices included), with the name each gives it."""
    rows = [dict(r) for r in con.execute(
        f"""SELECT t.id, {_team_name('full')} AS name, t.has_crest, t.is_new, x.custom_name AS stadium_custom_name,
                   (SELECT {_league_name('l')} FROM v_leagues l WHERE l.id = {_first_league()}) AS league,
                   {_edited('team', 't')} AS edited
            FROM v_team_stadiums x JOIN v_teams t ON t.id = x.team_id WHERE x.stadium_id = :sid
            ORDER BY fold(name)""", {'lang': lang, 'sid': sid})]
    for r in rows:
        for key in ('has_crest', 'is_new', 'edited'):
            r[key] = bool(r[key])
    return rows


def free_stadium_id(con) -> int | None:
    """The first stadium id the game and the project do not use (created ones: FIRST_OWN_STADIUM to MAX_STADIUM_ID)."""
    from f14mod.project import FIRST_OWN_STADIUM, MAX_STADIUM_ID
    used = {r[0] for r in con.execute('SELECT id FROM v_stadiums')}
    return next((i for i in range(FIRST_OWN_STADIUM, MAX_STADIUM_ID + 1) if i not in used), None)


def stadium_picture_path(con, sid: int, variant: int) -> str | None:
    """The menu picture file of the stadium's variant (the large one when the game has it)."""
    found = con.execute("SELECT path FROM stadium_files WHERE stadium_id = ? AND variant = ? AND kind IN ('large', 'small') "
                        "ORDER BY kind = 'large' DESC LIMIT 1", (sid, variant)).fetchone()
    return found[0] if found else None


def free_player_id(con, taken=frozenset()) -> int:
    """The first player id from fifa14.FIRST_FREE_PLAYER the game and the project do not use (`taken`: ids that have
    files in the game, e.g. a face or a photo)."""
    used = {r[0] for r in con.execute('SELECT id FROM v_players WHERE id >= ?', (fifa14.FIRST_FREE_PLAYER,))}
    pid = fifa14.FIRST_FREE_PLAYER
    while pid in used or pid in taken:
        pid += 1
    return pid


# ---- countries ------------------------------------------------------------------------------------------------------

COUNTRY_NAME_KEYS = list(fifa14.COUNTRY_NAME_STRINGS)


def _country_name(alias: str = 'n') -> str:
    """A country's name in the names language (`:lang`): the project's text in it, then its "All" text, then the
    game's text in it, then the game's English one. Every place that shows a country name uses it (the screen's title,
    the selects, the lists), so they all agree."""
    return f"""COALESCE(
        (SELECT text FROM p.country_names WHERE country_id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM p.country_names WHERE country_id = {alias}.id AND key = 'full' AND lang = '*'),
        (SELECT text FROM names WHERE kind = 'country' AND id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM names WHERE kind = 'country' AND id = {alias}.id AND key = 'full' AND lang = '{FALLBACK_LANG}'),
        {alias}.name)"""


def countries(con, lang: str, q='', sort=None, direction=None, page=1, size=DEFAULT_PAGE_SIZE,
              only: int | None = None, origin: str | None = None, status: str | None = None,
              ids: list[int] | None = None, confederation: int | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT n.id, {_country_name()} AS name, n.is_new, n.has_flag,
                 COALESCE({_saved('country', 'n', 'flag_from')}, n.id) AS flag_id,
                 (SELECT updated_at FROM p.pictures WHERE kind = 'country' AND id = n.id AND slot = 'flag')
                     AS own_flag,
                 (SELECT COUNT(*) FROM v_leagues l WHERE {_in_country('l', 'n.id')}) AS league_count,
                 COALESCE(pc.player_count, 0) AS player_count, n.confederation,
                 {_flag('hidden', 'country', 'n')} AS hidden,
                 n.id IN ({', '.join(map(str, fifa14.UNLISTED_NATIONS))}) AS game_hidden,
                 {_edited('country', 'n')} AS edited, {_dates('country', 'n')}, n.search AS search
                 FROM v_nations n
                 LEFT JOIN (SELECT nationality, COUNT(*) AS player_count FROM v_players GROUP BY nationality) pc
                     ON pc.nationality = n.id"""
    where = []
    if only is not None:
        params['only'] = only
        where.append('id = :only')
    if ids is not None:  # these countries only (a list the page is editing)
        listed = ','.join(str(int(i)) for i in ids) or 'NULL'
        where.append(f'id IN ({listed})')
    if q.strip():
        where.append(_search("fold(name) || ' ' || id || ' ' || search", q, params))
    if confederation is not None:
        params['confederation'] = confederation
        where.append('n.confederation = :confederation')
    if origin == 'project':
        where.append(f'(n.is_new = 1 OR {_edited("country", "n")})')
    elif origin == 'original':
        where.append('n.is_new = 0')
    hidden_sql = f'({_flag("hidden", "country", "n")} OR n.id IN ({", ".join(map(str, fifa14.UNLISTED_NATIONS))}))'
    if status == 'visible':
        where.append(f'NOT {hidden_sql}')
    elif status == 'hidden':
        where.append(hidden_sql)
    sorts = {'name': 'fold(name)', 'id': 'id', 'league_count': 'league_count', 'player_count': 'player_count',
             'confederation': 'confederation', 'created_at': 'created_at',
             'updated_at': 'updated_at'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size, new_first=True)
    for r in out['items']:
        r.pop('search', None)
        r['is_new'] = bool(r['is_new'])
        r['edited'] = bool(r['edited'])
        r['hidden'] = bool(r['hidden'])
        r['game_hidden'] = bool(r['game_hidden'])
        base = r['flag_id']
        if r['is_new'] and base == r['id']:
            base = fifa14.TEMPLATE_NATION
        r['base_flag_id'] = base  # the flag shown when the country has no picture of its own
        if r['own_flag']:
            r['flag_id'] = r['id']  # its own picture: /api/image/flag/<id> draws it
        elif r['is_new'] and r['flag_id'] == r['id']:
            r['flag_id'] = fifa14.TEMPLATE_NATION  # a created country without a choice: Rest of World's flag
        r['has_flag'] = bool(r['has_flag'])
    return out


def country(con, lang: str, cid: int) -> dict | None:
    found = countries(con, lang, only=cid)['items']
    if not found:
        return None
    head = found[0]
    leagues_in = leagues(con, lang, country=cid, size=100)['items']
    # the game's row and sound row (read-only for now; a created country has the game's model row only in the patch)
    stored = con.execute('SELECT raw, audio FROM nations WHERE id = ?', (cid,)).fetchone()
    raw = json.loads(stored['raw'] or '{}') if stored else {}
    audio = json.loads(stored['audio']) if stored and stored['audio'] else None
    if head['is_new']:  # the row the patch writes for it (builder.add_created): the model country's (or the copied
        # country's, with its sound row), with its own id
        copy_of = _project_fields(con, 'country', cid).get('copy_of')
        model = con.execute('SELECT raw, audio FROM nations ORDER BY id = ? DESC, id = ? DESC, rowid LIMIT 1',
                            (copy_of or -1, fifa14.TEMPLATE_NATION)).fetchone()
        audio = {**json.loads(model['audio']), 'nationid': cid} if copy_of and model and model['audio'] else None
        full = _project_names(con, 'country', cid).get('full') or {}
        name = full.get('*') or full.get('eng_us') or next(iter(full.values()), '') or f'Country {cid}'
        raw = {**json.loads(model['raw'] or '{}'), 'nationid': cid, 'nationname': name[:44], 'top_tier': 0,
               'teamid': -1} if model else {}
    team_id = raw.get('teamid')
    team = con.execute(f'SELECT t.id, {_team_name("full")} AS name FROM v_teams t WHERE t.id = :id',
                       {'lang': lang, 'id': team_id}).fetchone() if isinstance(team_id, int) and team_id >= 0 else None
    head = {**head, 'national_team': dict(team) if team else None, 'top_tier': raw.get('top_tier'), 'raw': raw,
            'audio': audio}
    return {**head, 'name_keys': COUNTRY_NAME_KEYS, 'languages': languages(con),
            'original_names': {} if head['is_new'] else _names(con, 'country', cid),
            'saved_names': _project_names(con, 'country', cid), 'leagues': leagues_in,
            **_form(con, 'country', cid, {})}


def free_country_id(con) -> int | None:
    used = {r[0] for r in con.execute('SELECT id FROM v_nations')}
    return next((i for i in range(1, fifa14.MAX_NATION_ID + 1) if i not in used), None)


def free_league_id(con) -> int | None:
    used = {r[0] for r in con.execute('SELECT id FROM v_leagues')} | set(fifa14.RESERVED_LEAGUES)
    return next((i for i in range(fifa14.FIRST_FREE_LEAGUE, fifa14.MAX_LEAGUE_ID + 1) if i not in used), None)


def league_link_count(con) -> int:
    return con.execute('SELECT COUNT(*) FROM v_league_teams').fetchone()[0]
