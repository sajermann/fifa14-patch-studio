"""The originals of the clean game in a SQLite file: built once per game (minutes at most), then every list, filter,
search and page is a query, so the app never keeps the whole database in memory.

The file is a cache: it can be deleted at any time and is built again from the game. Its key (`fingerprint`) changes
when the game's database or language archive changes.
"""
import hashlib
import json
import os
import re
import sqlite3
import time
import unicodedata

from . import fifa14, installer, kitfonts, t3db, teamkits
from .gamefs import DATABASE, GameFiles

SCHEMA_VERSION = 4  # 2: country names and flags; 3: formations and the kit files of each team; 4: kit print, fonts
LOCALE = 'data/loc/locale.big'

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE languages (code TEXT PRIMARY KEY);
CREATE TABLE names (kind TEXT, id INTEGER, key TEXT, lang TEXT, text TEXT, PRIMARY KEY (kind, id, key, lang));
CREATE TABLE nations (id INTEGER PRIMARY KEY, name TEXT, has_flag INTEGER, search TEXT);
CREATE TABLE leagues (id INTEGER PRIMARY KEY, db_name TEXT, country_id INTEGER, level INTEGER, has_logo INTEGER,
                      search TEXT, raw TEXT);
CREATE TABLE teams (id INTEGER PRIMARY KEY, db_name TEXT, overall INTEGER, attack INTEGER, midfield INTEGER,
                    defense INTEGER, color TEXT, national_of INTEGER, has_crest INTEGER, search TEXT, raw TEXT);
CREATE TABLE league_teams (league_id INTEGER, team_id INTEGER, PRIMARY KEY (league_id, team_id));
CREATE TABLE players (id INTEGER PRIMARY KEY, name TEXT, first TEXT, last TEXT, common TEXT, jersey_name TEXT,
                      overall INTEGER, potential INTEGER, position INTEGER, nationality INTEGER, birthdate TEXT,
                      height INTEGER, has_photo INTEGER, search TEXT, raw TEXT);
CREATE TABLE team_players (team_id INTEGER, player_id INTEGER, jersey INTEGER, position INTEGER,
                           PRIMARY KEY (team_id, player_id));
CREATE TABLE formations (team_id INTEGER, formation_id INTEGER, generic INTEGER, base INTEGER, name TEXT,
                         positions TEXT, PRIMARY KEY (team_id, formation_id));
CREATE TABLE team_kits (team_id INTEGER, kind INTEGER, PRIMARY KEY (team_id, kind));
CREATE TABLE kit_print (team_id INTEGER, kind INTEGER, print TEXT, PRIMARY KEY (team_id, kind));
CREATE TABLE kit_fonts (kind TEXT, font INTEGER, color INTEGER, name TEXT, ink TEXT, PRIMARY KEY (kind, font, color));
CREATE INDEX names_lookup ON names (kind, key, lang, id);
CREATE INDEX team_players_player ON team_players (player_id);
CREATE INDEX league_teams_team ON league_teams (team_id);
CREATE INDEX players_overall ON players (overall);
"""

TEAM_KEYS = fifa14.TEAM_NAME_STRINGS     # full, abbr15, abbr10, abbr7, abbr3, commentary
LEAGUE_KEYS = fifa14.LEAGUE_NAME_STRINGS  # full, abbr15, abbr, trophy, trophy_abbr15
COUNTRY_KEYS = fifa14.COUNTRY_NAME_STRINGS  # full, abbr3


def fold(text) -> str:
    """Lower case without accents, for searching."""
    nfd = unicodedata.normalize('NFD', str(text or '').lower())
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


def open_game(game_dir: str) -> GameFiles:
    """The clean game's files, even with a patch of this app installed (its files are read from the backups)."""
    ignore, substitutes = installer.originals_view(game_dir)
    return GameFiles(game_dir, ignore=ignore, substitutes=substitutes)


def fingerprint(files: GameFiles) -> str:
    h = hashlib.sha1(f'v{SCHEMA_VERSION}'.encode())
    h.update(files.read(DATABASE) or b'')
    locale = files._loose.get(LOCALE)  # noqa: SLF001 - the language archive itself, not an entry
    if locale and os.path.isfile(locale):
        st = os.stat(locale)
        h.update(f'{st.st_size}:{int(st.st_mtime)}'.encode())
    return h.hexdigest()[:16]


def _language_strings(files: GameFiles, lang: str, prefixes: tuple) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in (lang, f'{lang}_upd'):
        raw = files.read(f'data/loc/{name}.db')
        if raw is None:
            continue
        out.update(t3db.read_strings(raw, lambda sid: sid.startswith(prefixes)))
    return out


def _split_names(strings: dict[str, str], table: dict[str, str]) -> dict[int, dict[str, str]]:
    prefixes = sorted(table.items(), key=lambda kv: -len(kv[1]))  # longest first: Abbr15 before ''
    out: dict[int, dict[str, str]] = {}
    for sid, text in strings.items():
        for key, prefix in prefixes:
            rest = sid[len(prefix):]
            if sid.startswith(prefix) and rest.isdigit():
                out.setdefault(int(rest), {})[key] = text
                break
    return out


def build(game_dir: str, path: str, progress=None) -> str:
    """Builds the cache file at `path` (replaced when it exists); returns its fingerprint."""
    def step(message: str, done: float):
        if progress:
            progress(message, done)

    step('database', 0.0)
    files = open_game(game_dir)
    src = fifa14.Fifa14Source(game_dir, files=files)
    key = fingerprint(files)
    tmp = path + '.building'
    if os.path.exists(tmp):
        os.remove(tmp)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    langs = src.languages()
    con.executemany('INSERT INTO languages VALUES (?)', [(c,) for c in langs])

    search_team: dict[int, set[str]] = {}
    search_league: dict[int, set[str]] = {}
    search_country: dict[int, set[str]] = {}
    prefixes = tuple(TEAM_KEYS.values()) + tuple(LEAGUE_KEYS.values()) + tuple(COUNTRY_KEYS.values())
    for i, lang in enumerate(langs):
        step(f'language {lang}', 0.1 + 0.5 * i / max(1, len(langs)))
        strings = _language_strings(files, lang, prefixes)
        rows = []
        for kind, table, search in (('team', TEAM_KEYS, search_team), ('league', LEAGUE_KEYS, search_league),
                                    ('country', COUNTRY_KEYS, search_country)):
            for oid, names in _split_names(strings, table).items():
                for k, text in names.items():
                    rows.append((kind, oid, k, lang, text))
                    search.setdefault(oid, set()).add(fold(text))
        con.executemany('INSERT OR REPLACE INTO names VALUES (?,?,?,?,?)', rows)

    step('teams', 0.65)
    con.executemany('INSERT INTO nations VALUES (?,?,?,?)', [
        (nid, src.nation_name(nid), int(files.exists(fifa14.FLAG_PICTURE.format(nid))),
         ' '.join(sorted({str(nid), fold(src.nation_name(nid))} | search_country.get(nid, set()))))
        for nid in src.nations])
    con.executemany('INSERT INTO leagues VALUES (?,?,?,?,?,?,?)', [
        (lid, r.get('leaguename'), r.get('countryid'), r.get('level'), int('logo' in src.league_image_paths(lid)),
         ' '.join(sorted({str(lid), fold(r.get('leaguename'))} | search_league.get(lid, set()))),
         json.dumps(r, ensure_ascii=False))
        for lid, r in src.leagues.items()])
    con.executemany('INSERT INTO teams VALUES (?,?,?,?,?,?,?,?,?,?,?)', [
        (tid, r.get('teamname'), r.get('overallrating'), r.get('attackrating'), r.get('midfieldrating'),
         r.get('defenserating'), json.dumps([r.get('teamcolor1r'), r.get('teamcolor1g'), r.get('teamcolor1b')]),
         src.national_teams.get(tid), int(src.crest_path(tid) is not None),
         ' '.join(sorted({str(tid), fold(r.get('teamname'))} | search_team.get(tid, set()))),
         json.dumps(r, ensure_ascii=False))
        for tid, r in src.teams.items()])
    con.executemany('INSERT OR IGNORE INTO league_teams VALUES (?,?)',
                    [(lid, tid) for lid, tids in src.league_teams.items() for tid in tids])

    step('players', 0.8)
    photos = {p for p in files.list('data/ui/imgassets/heads/')}
    rows = []
    for pid, r in src.players.items():
        n = src.player_names(pid)
        display = src.player_display_name(pid)
        rows.append((pid, display, n.get('first'), n.get('last'), n.get('common'), n.get('jersey'),
                     r.get('overallrating'), r.get('potential'), r.get('preferredposition1'), r.get('nationality'),
                     fifa14.to_date(r.get('birthdate')), r.get('height'),
                     int(fifa14.PHOTO.format(pid) in photos),
                     ' '.join([str(pid), *sorted({fold(v) for v in n.values()})]),
                     json.dumps(r, ensure_ascii=False)))
    con.executemany('INSERT INTO players VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
    con.executemany('INSERT OR IGNORE INTO team_players VALUES (?,?,?,?)', [
        (ln['teamid'], ln['playerid'], ln.get('jerseynumber'), ln.get('position'))
        for links in src.team_links.values() for ln in links])
    # formations: the 33 generic ones (teamid -1, `relativeformationid` 1-33) and each team's own (a copy of one)
    # base = which of the 33 generic ones the row is (or was copied from)
    con.executemany('INSERT OR IGNORE INTO formations VALUES (?,?,?,?,?,?)', [
        (r['teamid'], r['relativeformationid'] if r['teamid'] == -1 else r['formationid'], int(r['teamid'] == -1),
         r.get('relativeformationid'), r.get('formationname'), json.dumps([r.get(f'position{i}') for i in range(11)]))
        for r in src.rows('formations')])
    kit_rows = set()
    for kit_path in files.list('data/sceneassets/kit/kit_'):
        m = re.match(r'data/sceneassets/kit/kit_(\d+)_(\d+)_0\.rx3$', kit_path)
        if m:
            kit_rows.add((int(m.group(1)), int(m.group(2))))
    con.executemany('INSERT INTO team_kits VALUES (?,?)', sorted(kit_rows))
    # name and numbers of each current kit (year 0), and the fonts the game has: a name font per .ttf (its family
    # name), a number font per (font, color) file (the color the digits really show)
    con.executemany('INSERT OR IGNORE INTO kit_print VALUES (?,?,?)', [
        (r['teamtechid'], r['teamkittypetechid'], json.dumps(teamkits.print_of(r)))
        for r in src.rows('teamkits') if r.get('year', 0) == 0])
    fonts = []
    for font_path in files.list('data/sceneassets/jerseyfonts/'):
        m = re.search(r'font_(\d+)\.ttf$', font_path)
        if m:
            fonts.append(('name', int(m.group(1)), 0, kitfonts.family_name(files.read(font_path) or b''), None))
    for font_path in files.list('data/sceneassets/kitnumbers/'):
        m = re.search(r'kitnumbers_(\d+)_(\d+)\.rx3$', font_path)
        if m:
            ink = kitfonts.ink_color(files.read(font_path) or b'') if m.group(1) == '1' else None
            fonts.append(('number', int(m.group(1)), int(m.group(2)), None, json.dumps(ink) if ink else None))
    con.executemany('INSERT OR IGNORE INTO kit_fonts VALUES (?,?,?,?,?)', fonts)
    con.executemany('INSERT INTO meta VALUES (?,?)', [
        ('fingerprint', key), ('schema', str(SCHEMA_VERSION)), ('built_at', str(int(time.time()))),
        ('game_dir', files.root), ('database_from', src.database_source or '')])
    con.commit()
    con.close()
    os.replace(tmp, path)
    step('done', 1.0)
    return key


def read_meta(path: str) -> dict:
    try:
        con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        try:
            return dict(con.execute('SELECT key, value FROM meta'))
        finally:
            con.close()
    except sqlite3.Error:
        return {}
