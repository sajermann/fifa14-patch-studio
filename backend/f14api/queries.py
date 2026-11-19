"""What the screens show, straight from SQLite: the originals cache (main database) with the user's project attached
as `p`. Filters, search, sorting and pages are SQL; only the page being shown is loaded."""
import json
import math
import sqlite3

from f14mod import catalog, fields, fifa14

PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 50
FALLBACK_LANG = 'eng_us'


def _saved_sql(kind: str, alias: str, field: str) -> str:
    return (f"(SELECT json_extract(value, '$') FROM p.fields WHERE kind = '{kind}' AND id = {alias}.id "
            f"AND field = '{field}')")


# the originals and what the project created, as one table each (temporary views of this connection)
VIEWS = [
    f"""CREATE TEMP VIEW v_nations AS
        SELECT id, name, 0 AS is_new, has_flag, search FROM nations
        UNION ALL
        SELECT c.id, COALESCE(
            (SELECT text FROM p.country_names WHERE country_id = c.id AND key = 'full' AND lang = '*'),
            (SELECT text FROM p.country_names WHERE country_id = c.id AND key = 'full' ORDER BY lang LIMIT 1),
            'Country ' || c.id), 1, 1, ''
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
    """CREATE TEMP VIEW v_league_teams AS
        SELECT league_id, team_id, 0 AS ord FROM league_teams
        WHERE league_id NOT IN (SELECT league_id FROM p.league_members_set)
        UNION ALL
        SELECT league_id, team_id, ord FROM p.league_members""",
]

TEAM_NAME_KEYS = list(fifa14.TEAM_NAME_STRINGS)  # full, abbr15, abbr10, abbr7, abbr3, commentary
LEAGUE_NAME_KEYS = list(fifa14.LEAGUE_NAME_STRINGS)


def connect(catalog_path: str, project_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f'file:{catalog_path}?mode=ro', uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.create_function('fold', 1, catalog.fold, deterministic=True)
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


def _edited(kind: str, alias: str) -> str:
    return f"EXISTS (SELECT 1 FROM p.edited WHERE kind = '{kind}' AND id = {alias}.id)"


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
    before the game's, whatever the sort."""
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
    return {'items': [dict(r) for r in rows], 'total': total, 'page': page_no, 'size': size, 'pages': pages,
            'sort': key, 'dir': 'desc' if desc else 'asc'}


# ---- lists ----------------------------------------------------------------------------------------------------------

def leagues(con, lang: str, q='', sort=None, direction=None, page=1, size=DEFAULT_PAGE_SIZE,
            country: int | None = None, ids: list[int] | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT l.id, {_league_name()} AS name, l.db_name, l.level, l.country_id,
                 (SELECT name FROM v_nations WHERE id = l.country_id) AS country, l.has_logo, l.is_new,
                 (SELECT COUNT(*) FROM v_league_teams WHERE league_id = l.id) AS team_count,
                 {_edited('league', 'l')} AS edited, l.search AS search,
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
    sorts = {'name': 'fold(name)', 'id': 'id', 'level': 'level', 'country': 'fold(country)',
             'team_count': 'team_count'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size, new_first=True)
    for r in out['items']:
        r.pop('search', None)
        r['edited'] = bool(r['edited'])
        r['is_new'] = bool(r['is_new'])
        r['hidden'] = bool(r['hidden'])
        r['game_hidden'] = bool(r['game_hidden'])  # the game itself never lists it
        r['extra_countries'] = json.loads(r['extra_countries']) if r['extra_countries'] else []
        r['hidden_in_countries'] = json.loads(r['hidden_in_countries']) if r['hidden_in_countries'] else []
        r['has_logo'] = bool(r['has_logo'] or r['own_logo'])
    return out


def teams(con, lang: str, q='', league: int | None = None, edited: bool | None = None, sort=None, direction=None,
          page=1, size=DEFAULT_PAGE_SIZE, only: int | None = None, ids: list[int] | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT t.id, {_team_name('full')} AS name, {_team_name('abbr15')} AS abbr15,
                 {_team_name('abbr3')} AS abbr3, t.overall, t.attack, t.midfield, t.defense, t.color, t.has_crest,
                 t.national_of, {_first_league()} AS league_id,
                 (SELECT {_league_name('l')} FROM v_leagues l WHERE l.id = {_first_league()}) AS league,
                 (SELECT COUNT(*) FROM team_players WHERE team_id = t.id) AS player_count,
                 {_edited('team', 't')} AS edited,
                 {_flag('hidden', 'team', 't')} AS hidden,
                 t.search AS search
                 FROM teams t"""
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
             'player_count': 'player_count'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size)
    for r in out['items']:
        r.pop('search', None)
        r['color'] = json.loads(r['color']) if r['color'] else None
        r['has_crest'] = bool(r['has_crest'])
        r['edited'] = bool(r['edited'])
        r['hidden'] = bool(r['hidden'])
    return out


def players(con, lang: str, q='', team: int | None = None, position: int | None = None, sort=None, direction=None,
            page=1, size=DEFAULT_PAGE_SIZE) -> dict:
    params: dict = {'lang': lang}
    club = '(SELECT MIN(tp.team_id) FROM team_players tp JOIN teams x ON x.id = tp.team_id ' \
           'WHERE tp.player_id = pl.id AND x.national_of IS NULL)'
    select = f"""SELECT pl.id, {_player_name()} AS name, pl.overall, pl.potential, pl.position, pl.birthdate, pl.height,
                 pl.nationality, (SELECT name FROM v_nations WHERE id = pl.nationality) AS nationality_name,
                 pl.has_photo, {club} AS team_id,
                 (SELECT {_team_name('abbr15')} FROM teams t WHERE t.id = {club}) AS team,
                 {_edited('player', 'pl')} AS edited, pl.search || ' ' || fold({_player_name()}) AS search_all
                 FROM players pl"""
    where = []
    if team is not None:
        params['team'] = team
        where.append('id IN (SELECT player_id FROM team_players WHERE team_id = :team)')
    if position is not None:
        params['position'] = position
        where.append('position = :position')
    if q.strip():
        where.append(_search('search_all', q, params))
    sorts = {'name': 'fold(name)', 'id': 'id', 'overall': 'overall', 'potential': 'potential',
             'position': 'position', 'team': 'fold(team)', 'height': 'height', 'birthdate': 'birthdate'}
    out = _page(con, select, where, params, sorts, sort, direction, ('overall', 'desc'), page, size)
    for r in out['items']:
        r.pop('search', None)
        r.pop('search_all', None)
        r['has_photo'] = bool(r['has_photo'])
        r['edited'] = bool(r['edited'])
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
                     'country': ('country_names', 'country_id')}[kind]
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
    row = con.execute('SELECT * FROM teams WHERE id = ?', (tid,)).fetchone()
    if not row:
        return None
    head = teams(con, lang, only=tid)['items'][0]
    saved = _project_names(con, 'team', tid)
    raw = json.loads(row['raw'])
    roster = [dict(r) for r in con.execute(
        f"""SELECT pl.id, {_player_name()} AS name, pl.overall, pl.position, tp.jersey, tp.position AS link_position, pl.has_photo
           FROM team_players tp JOIN players pl ON pl.id = tp.player_id WHERE tp.team_id = ?
           ORDER BY tp.position, pl.overall DESC""", (tid,))]
    for r in roster:
        r['position_name'] = fifa14.position_name(r['position'])
        r['link_position_name'] = fifa14.position_name(r['link_position'])
        r['has_photo'] = bool(r['has_photo'])
    leagues_of = [dict(r) for r in con.execute(
        f'SELECT l.id, {_league_name()} AS name, l.is_new FROM v_leagues l WHERE l.id IN '
        '(SELECT league_id FROM v_league_teams WHERE team_id = :tid)', {'lang': lang, 'tid': tid})]
    return {**head, 'db_name': row['db_name'], 'name_keys': TEAM_NAME_KEYS, 'languages': languages(con),
            'original_names': _names(con, 'team', tid), 'saved_names': saved, 'roster': roster,
            'leagues': leagues_of, **_form(con, 'team', tid, raw), 'raw': raw}


def league(con, lang: str, lid: int) -> dict | None:
    row = con.execute('SELECT * FROM v_leagues WHERE id = ?', (lid,)).fetchone()
    if not row:
        return None
    head = con.execute(f"""SELECT l.id, {_league_name()} AS name, l.level, l.country_id,
                           (SELECT name FROM v_nations WHERE id = l.country_id) AS country, l.has_logo, l.is_new
                           FROM v_leagues l WHERE l.id = :lid""", {'lang': lang, 'lid': lid}).fetchone()
    raw = json.loads(row['raw'])
    original = _names(con, 'league', lid)
    team_ids = [r[0] for r in con.execute(
        'SELECT team_id FROM v_league_teams WHERE league_id = ? ORDER BY ord, team_id', (lid,))]
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
            'teams_changed': custom, 'teams': teams(con, lang, league=lid, size=100)['items'],
            **_form(con, 'league', lid, raw), 'raw': raw}


def player(con, lang: str, pid: int) -> dict | None:
    row = con.execute(f'SELECT pl.*, {_player_name()} AS shown FROM players pl WHERE pl.id = ?', (pid,)).fetchone()
    if not row:
        return None
    raw = json.loads(row['raw'])
    names = {k: row[k] for k in ('first', 'last', 'common', 'jersey_name') if row[k]}
    links = [dict(r) for r in con.execute(
        f"""SELECT t.id, {_team_name('abbr15')} AS name, tp.jersey, tp.position, t.national_of
            FROM team_players tp JOIN teams t ON t.id = tp.team_id WHERE tp.player_id = :pid""",
        {'lang': lang, 'pid': pid})]
    for r in links:
        r['position_name'] = fifa14.position_name(r['position'])
    return {
        'id': pid, 'name': row['shown'], 'names': names,
        'overall': row['overall'], 'potential': row['potential'], 'position': row['position'],
        'position_name': fifa14.position_name(row['position']), 'birthdate': row['birthdate'],
        'height': row['height'], 'weight': raw.get('weight'), 'nationality': row['nationality'],
        'nationality_name': (con.execute('SELECT name FROM v_nations WHERE id = ?', (row['nationality'],)).fetchone()
                             or [None])[0],
        'has_photo': bool(row['has_photo']),
        'attributes': {name: raw[col] for col, name in fifa14.ATTRIBUTES.items() if col in raw},
        'teams': links, **_form(con, 'player', pid, raw, names), 'raw': raw,
    }


# ---- countries ------------------------------------------------------------------------------------------------------

COUNTRY_NAME_KEYS = list(fifa14.COUNTRY_NAME_STRINGS)


def _country_name(alias: str = 'n') -> str:
    return f"""COALESCE(
        (SELECT text FROM p.country_names WHERE country_id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM p.country_names WHERE country_id = {alias}.id AND key = 'full' AND lang = '*'),
        (SELECT text FROM names WHERE kind = 'country' AND id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM names WHERE kind = 'country' AND id = {alias}.id AND key = 'full' AND lang = '{FALLBACK_LANG}'),
        {alias}.name)"""


def countries(con, lang: str, q='', sort=None, direction=None, page=1, size=DEFAULT_PAGE_SIZE,
              only: int | None = None, origin: str | None = None, status: str | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT n.id, {_country_name()} AS name, n.is_new, n.has_flag,
                 COALESCE({_saved('country', 'n', 'flag_from')}, n.id) AS flag_id,
                 (SELECT updated_at FROM p.pictures WHERE kind = 'country' AND id = n.id AND slot = 'flag')
                     AS own_flag,
                 (SELECT COUNT(*) FROM v_leagues l WHERE {_in_country('l', 'n.id')}) AS league_count,
                 {_flag('hidden', 'country', 'n')} AS hidden,
                 n.id IN ({', '.join(map(str, fifa14.UNLISTED_NATIONS))}) AS game_hidden,
                 {_edited('country', 'n')} AS edited, n.search AS search
                 FROM v_nations n"""
    where = []
    if only is not None:
        params['only'] = only
        where.append('id = :only')
    if q.strip():
        where.append(_search("fold(name) || ' ' || id || ' ' || search", q, params))
    if origin == 'project':
        where.append(f'(n.is_new = 1 OR {_edited("country", "n")})')
    elif origin == 'original':
        where.append('n.is_new = 0')
    hidden_sql = f'({_flag("hidden", "country", "n")} OR n.id IN ({", ".join(map(str, fifa14.UNLISTED_NATIONS))}))'
    if status == 'visible':
        where.append(f'NOT {hidden_sql}')
    elif status == 'hidden':
        where.append(hidden_sql)
    sorts = {'name': 'fold(name)', 'id': 'id', 'league_count': 'league_count'}
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
