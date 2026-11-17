"""What the screens show, straight from SQLite: the originals cache (main database) with the user's project attached
as `p`. Filters, search, sorting and pages are SQL; only the page being shown is loaded."""
import json
import math
import sqlite3

from f14mod import catalog, fifa14

PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 50
FALLBACK_LANG = 'eng_us'

TEAM_NAME_KEYS = list(fifa14.TEAM_NAME_STRINGS)  # full, abbr15, abbr10, abbr7, abbr3, commentary
LEAGUE_NAME_KEYS = list(fifa14.LEAGUE_NAME_STRINGS)


def connect(catalog_path: str, project_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f'file:{catalog_path}?mode=ro', uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.create_function('fold', 1, catalog.fold, deterministic=True)
    con.execute('ATTACH DATABASE ? AS p', (project_path,))
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


def _league_name(alias: str = 'l') -> str:
    return f"""COALESCE(
        (SELECT text FROM names WHERE kind = 'league' AND id = {alias}.id AND key = 'full' AND lang = :lang),
        (SELECT text FROM names WHERE kind = 'league' AND id = {alias}.id AND key = 'full' AND lang = '{FALLBACK_LANG}'),
        {alias}.db_name)"""


def _first_league(team_alias: str = 't') -> str:
    return f'(SELECT MIN(league_id) FROM league_teams WHERE team_id = {team_alias}.id)'


def _search(column: str, q: str, params: dict) -> str:
    words = catalog.fold(q).split()
    parts = []
    for i, w in enumerate(words[:8]):
        params[f'w{i}'] = f'%{w}%'
        parts.append(f'{column} LIKE :w{i}')
    return ' AND '.join(parts)


def _page(con, select: str, where: list[str], params: dict, sorts: dict[str, str], sort: str | None,
          direction: str | None, default: tuple[str, str], page_no: int, size: int) -> dict:
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
    rows = con.execute(
        f'SELECT * FROM ({select} {clause}) ORDER BY ({order}) IS NULL, {order} {"DESC" if desc else "ASC"}, id '
        f'LIMIT :limit OFFSET :offset', {**params, 'limit': size, 'offset': (page_no - 1) * size}).fetchall()
    return {'items': [dict(r) for r in rows], 'total': total, 'page': page_no, 'size': size, 'pages': pages,
            'sort': key, 'dir': 'desc' if desc else 'asc'}


# ---- lists ----------------------------------------------------------------------------------------------------------

def leagues(con, lang: str, q='', sort=None, direction=None, page=1, size=DEFAULT_PAGE_SIZE) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT l.id, {_league_name()} AS name, l.db_name, l.level, l.country_id,
                 (SELECT name FROM nations WHERE id = l.country_id) AS country, l.has_logo,
                 (SELECT COUNT(*) FROM league_teams WHERE league_id = l.id) AS team_count, l.search AS search
                 FROM leagues l"""
    where = []
    if q.strip():
        where.append(_search('fold(name) || \' \' || search', q, params))
    sorts = {'name': 'fold(name)', 'id': 'id', 'level': 'level', 'country': 'fold(country)',
             'team_count': 'team_count'}
    out = _page(con, select, where, params, sorts, sort, direction, ('name', 'asc'), page, size)
    for r in out['items']:
        r.pop('search', None)
    return out


def teams(con, lang: str, q='', league: int | None = None, edited: bool | None = None, sort=None, direction=None,
          page=1, size=DEFAULT_PAGE_SIZE, only: int | None = None) -> dict:
    params: dict = {'lang': lang}
    select = f"""SELECT t.id, {_team_name('full')} AS name, {_team_name('abbr15')} AS abbr15,
                 {_team_name('abbr3')} AS abbr3, t.overall, t.attack, t.midfield, t.defense, t.color, t.has_crest,
                 t.national_of, {_first_league()} AS league_id,
                 (SELECT {_league_name('l')} FROM leagues l WHERE l.id = {_first_league()}) AS league,
                 (SELECT COUNT(*) FROM team_players WHERE team_id = t.id) AS player_count,
                 EXISTS (SELECT 1 FROM p.edited WHERE kind = 'team' AND id = t.id) AS edited,
                 t.search AS search
                 FROM teams t"""
    where = []
    if only is not None:
        params['only'] = only
        where.append('id = :only')
    if league is not None:
        params['league'] = league
        where.append('id IN (SELECT team_id FROM league_teams WHERE league_id = :league)')
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
    return out


def players(con, lang: str, q='', team: int | None = None, position: int | None = None, sort=None, direction=None,
            page=1, size=DEFAULT_PAGE_SIZE) -> dict:
    params: dict = {'lang': lang}
    club = '(SELECT MIN(tp.team_id) FROM team_players tp JOIN teams x ON x.id = tp.team_id ' \
           'WHERE tp.player_id = pl.id AND x.national_of IS NULL)'
    select = f"""SELECT pl.id, pl.name, pl.overall, pl.potential, pl.position, pl.birthdate, pl.height,
                 pl.nationality, (SELECT name FROM nations WHERE id = pl.nationality) AS nationality_name,
                 pl.has_photo, {club} AS team_id,
                 (SELECT {_team_name('abbr15')} FROM teams t WHERE t.id = {club}) AS team, pl.search AS search
                 FROM players pl"""
    where = []
    if team is not None:
        params['team'] = team
        where.append('id IN (SELECT player_id FROM team_players WHERE team_id = :team)')
    if position is not None:
        params['position'] = position
        where.append('position = :position')
    if q.strip():
        where.append(_search('search', q, params))
    sorts = {'name': 'fold(name)', 'id': 'id', 'overall': 'overall', 'potential': 'potential',
             'position': 'position', 'team': 'fold(team)', 'height': 'height', 'birthdate': 'birthdate'}
    out = _page(con, select, where, params, sorts, sort, direction, ('overall', 'desc'), page, size)
    for r in out['items']:
        r.pop('search', None)
        r['has_photo'] = bool(r['has_photo'])
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


def team(con, lang: str, tid: int) -> dict | None:
    row = con.execute('SELECT * FROM teams WHERE id = ?', (tid,)).fetchone()
    if not row:
        return None
    head = teams(con, lang, only=tid)['items'][0]
    saved: dict[str, dict[str, str]] = {}
    for r in con.execute('SELECT key, lang, text FROM p.team_names WHERE team_id = ?', (tid,)):
        saved.setdefault(r['key'], {})[r['lang']] = r['text']
    roster = [dict(r) for r in con.execute(
        """SELECT pl.id, pl.name, pl.overall, pl.position, tp.jersey, tp.position AS link_position, pl.has_photo
           FROM team_players tp JOIN players pl ON pl.id = tp.player_id WHERE tp.team_id = ?
           ORDER BY tp.position, pl.overall DESC""", (tid,))]
    for r in roster:
        r['position_name'] = fifa14.position_name(r['position'])
        r['link_position_name'] = fifa14.position_name(r['link_position'])
        r['has_photo'] = bool(r['has_photo'])
    leagues_of = [dict(r) for r in con.execute(
        f'SELECT l.id, {_league_name()} AS name FROM leagues l WHERE l.id IN '
        '(SELECT league_id FROM league_teams WHERE team_id = :tid)', {'lang': lang, 'tid': tid})]
    return {**head, 'db_name': row['db_name'], 'name_keys': TEAM_NAME_KEYS, 'languages': languages(con),
            'original_names': _names(con, 'team', tid), 'saved_names': saved, 'roster': roster,
            'leagues': leagues_of, 'raw': json.loads(row['raw'])}


def league(con, lang: str, lid: int) -> dict | None:
    row = con.execute('SELECT * FROM leagues WHERE id = ?', (lid,)).fetchone()
    if not row:
        return None
    head = con.execute(f"""SELECT l.id, {_league_name()} AS name, l.level, l.country_id,
                           (SELECT name FROM nations WHERE id = l.country_id) AS country, l.has_logo
                           FROM leagues l WHERE l.id = :lid""", {'lang': lang, 'lid': lid}).fetchone()
    return {**dict(head), 'db_name': row['db_name'], 'has_logo': bool(row['has_logo']),
            'names': _names(con, 'league', lid), 'name_keys': LEAGUE_NAME_KEYS,
            'teams': teams(con, lang, league=lid, size=100)['items'], 'raw': json.loads(row['raw'])}


def player(con, lang: str, pid: int) -> dict | None:
    row = con.execute('SELECT * FROM players WHERE id = ?', (pid,)).fetchone()
    if not row:
        return None
    raw = json.loads(row['raw'])
    links = [dict(r) for r in con.execute(
        f"""SELECT t.id, {_team_name('abbr15')} AS name, tp.jersey, tp.position, t.national_of
            FROM team_players tp JOIN teams t ON t.id = tp.team_id WHERE tp.player_id = :pid""",
        {'lang': lang, 'pid': pid})]
    for r in links:
        r['position_name'] = fifa14.position_name(r['position'])
    return {
        'id': pid, 'name': row['name'],
        'names': {k: row[k] for k in ('first', 'last', 'common', 'jersey_name') if row[k]},
        'overall': row['overall'], 'potential': row['potential'], 'position': row['position'],
        'position_name': fifa14.position_name(row['position']), 'birthdate': row['birthdate'],
        'height': row['height'], 'weight': raw.get('weight'), 'nationality': row['nationality'],
        'nationality_name': (con.execute('SELECT name FROM nations WHERE id = ?', (row['nationality'],)).fetchone()
                             or [None])[0],
        'has_photo': bool(row['has_photo']),
        'attributes': {name: raw[col] for col, name in fifa14.ATTRIBUTES.items() if col in raw},
        'teams': links, 'raw': raw,
    }
