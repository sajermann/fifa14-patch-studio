"""The user's work: what was changed over the clean game, in a SQLite file, one entity at a time.

Every save writes one entity whole (its form, as the screen sends it); nothing is kept as a global draft. The file
holds only differences from the originals: deleting an entity's rows gives the original back.

Names of teams and leagues (language strings): one row per (entity, name key, language); language '*' is the value
for every language that has no value of its own.
Fields (database values, see f14mod.fields): one row per (kind, entity, field) with the value as JSON.

Schema 2 (adds league names and fields) opens schema 1 files as they are: the new tables start empty.
Schema 3 (17/11/2026) adds what the user creates (free countries and leagues; later teams and players) and the teams
of a league: `created` lists the new entities (their names and fields live in the same tables as the edits), and
`league_members` holds the whole team list of every league whose teams were changed (`league_members_set`), in order;
a league without a row there keeps the game's teams; `pictures` keeps the user's pictures (PNG) of an entity by
slot (a country's 'flag', a league's 'logo'), so the project stays one file. Older files open as they are (the new
tables start empty).
Schema 4 (17/11/2026) adds `hidden` (the Hide button, same rule as the Street Studio): a created entity that is
hidden is left out of the patch (kept in the project, nothing of it is built); an original one is hidden in the game by
the project (Kick-off and tournament lists; see builder.write_visibility). `visible()` is the project the builder
sees: without the hidden created entities, and with `hidden_in_game` = the hidden originals.
Schema 5 (19/11/2026) adds the team's own things (test TN1): `team_sources` (a created team: the game team it starts
from and whether its crest and kits are copied), `team_rosters` (the whole squad of a team whose squad was changed,
`team_rosters_set`: player, order, jersey number and lineup slot: a position code 0-27 for the 11 starters, 28 bench,
29 out of the squad) and `team_kits` (each kit of a team the user changed: where it comes from, as JSON; its pictures
live in `pictures`, slots `kit<type>_jersey`/`_shorts`/`_mini`). A team's crest picture is slot `crest`. Older files
open as they are.
Schema 6 (19/11/2026) adds the player's own things: `player_sources` (a created player: the game player whose row it
starts from), `player_files` (the files of the face picked from a pack, kept in the project so it stays one file:
name = the kind of fifa14.PLAYER_FACE_FILES) and `team_rosters.hidden` (a player left out of the patch in that team
only, kept in its squad on the screen: same rule as the Street Studio). A player's photo is picture slot `photo`.
Older files open as they are (the new column is added).
Schema 7 (19/11/2026) adds `league_members.hidden` (a team left out of the patch in that league only, kept in its list
on the screen). Older files open as they are (the new column is added).
Schema 8 (23/11/2026) adds `dates`: when each entity of the project was created and last changed (Unix time, UTC;
same rule as the Street Studio). A created entity is created when the user creates it; a game entity when it is first
changed. `updated_at` only moves when something of the entity really changed (saving the same form again keeps it);
an original whose changes are all undone leaves the project, and its dates with it. Older files get their dates from
what they had: a created entity's `created.created_at`, and the last save of `edited` (an original edited before
schema 8 has no creation date, as in the Street Studio).
Schema 9 (23/11/2026) adds the stadiums: `stadium` is a kind of entity (its names in `stadium_names`, its fields in
`fields`; only the game's stadiums, none created yet) and `team_stadiums` holds the stadium a team plays in when the
user changed it (one per team, as in the game's teamstadiumlinks). Older files open as they are (the new tables start
empty).
Schema 10 (23/11/2026): a game entity changed by the project only has `updated_at` (the project never created it, same
rule as the Street Studio); files of schemas 8 and 9 lose the creation date they gave the game's entities.
Schema 11 (24/11/2026) adds the advertising boards (tests PL1-PL5): `adboard` is a kind the user creates (its name in
`fields` as 'name', its picture in `pictures`, slot 'board'), and `team_adboards` / `league_adboards` link a team or a
league to one board (one each; a board may be linked to many). Older files open as they are (the new tables start
empty).
Schema 12 (24/11/2026): the game's boards are entities too (kind `adboard`, id = the game's board number, at most
GAME_ADBOARD_MAX; edited = its picture replaced, like any original) and the boards the user creates take ids from
FIRST_OWN_ADBOARD, so the two never meet; schema 11 files get their created boards (and their links) renumbered.
Schema 13 (24/11/2026) adds boots, goalkeeper gloves and balls (f14mod.equipment): kinds `boot`,
`glove` and `ball`, id = their code in the game (the game's own items are edited like any original; a new one takes a
free code when it is created); their name, credits and credits page are fields ('name', 'credits', 'credits_url'), the
files of the pack they come from are kept in `equipment_files` (name 'mesh' or 'texture') and their picture in
`pictures` (slot 'thumbnail'). A player wears one through his fields shoetypecode / gkglovetypecode and a team plays
with one through balltype. Older files open as they are (the new table starts empty).
Schema 14 (25/11/2026) adds the stadiums the user creates: kind `stadium` in `created` (ids from
FIRST_OWN_STADIUM, above the clean game's), `stadium_sources` (the game stadium whose database row it starts from and
whose scene and menu pictures it uses until it has its own) and `stadium_scene` (the scene files of a downloaded
stadium: name = the game path with STADIUM_ID_MARK for the stadium id, data, and a digest so a change is found
without reading the files). A stadium made from scratch has template NULL: blank (no scene, no pictures) until the
user gives it a folder and fills the fields the game needs (fields.STADIUM_REQUIRED); until then it stays out of the
patch (Project.incomplete_stadiums). `folder_stadium` = the game stadium the folder's files were made for (its row
fits the scene: the screen offers its values). A game stadium can take a folder too: its row in `stadium_sources` has
template NULL and the folder's stadium; its files go into the patch under its own id. The menu pictures the user gives a stadium (the game's or a created one) are picture
slots STADIUM_PICTURE, one per variant. Older files open as they are (the new
tables start empty).
Since 25/11/2026 a team made from scratch has `team_sources.template` NULL (no table changes): blank like a stadium from
scratch (fields.TEAM_REQUIRED, its stadium and squad empty, the tactics at fields.TEAM_DEFAULTS) and out of the patch
until it has them (Project.incomplete_teams). Teams made from scratch before keep the model team they started from.
Same for a player made from scratch since 25/11/2026: `player_sources.template` NULL, blank (fields.PLAYER_DEFAULTS,
fields.PLAYER_REQUIRED empty) and out of the patch until those are filled (Project.incomplete_players); the ones made
before keep the model player's values.
Schema 15 (26/11/2026): the files (pictures, face files, pack files, stadium scenes) leave the database: they live in
folders next to it, under `<name>_files/` (f14mod.filestore, as the Street Studio keeps its files beside
database.json), each named after its digest, and the rows of `pictures`, `player_files`, `equipment_files` and `stadium_scene` keep only `file` (the path
in the project folder), `size` and `digest`. Older files (the bytes inside the database) are not converted: they are
refused (ProjectError) and a new project starts.
Schema 16 (26/11/2026) adds `origins`: where an entity that came in by an import came from (`source` = 'pkg:<patch
name>' of an extractor's package or 'prj:<uid>' of a project, `source_id` = its id there, `imported_at`), so importing
from the same source again updates it instead of adding a copy (f14mod.share.plan). `meta` 'uid' = the project's own
id, made the first time it exports. Older files open as they are (the table starts empty).
"""
import json
import os
import sqlite3
import time

from .filestore import EQUIPMENT as EQUIPMENT_FOLDERS, FACES, PICTURES, STADIUMS, FileStore

SCHEMA_VERSION = 16
FILES_SUFFIX = '_files'  # project.sqlite keeps its files in project_files/ (f14mod.filestore)
DEFAULT_LANG = '*'
KINDS = ('team', 'league', 'player', 'country', 'stadium', 'adboard', 'boot', 'glove', 'ball')
EQUIPMENT_KINDS = ('boot', 'glove', 'ball')
# the pack files a created item needs before it enters the patch (every glove wears the game's one glove mesh)
EQUIPMENT_NEEDS = {'boot': ('mesh', 'texture'), 'glove': ('texture',), 'ball': ('mesh', 'texture')}
NAME_TABLES = {'team': ('team_names', 'team_id'), 'league': ('league_names', 'league_id'),
               'country': ('country_names', 'country_id'), 'stadium': ('stadium_names', 'stadium_id')}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS edited (kind TEXT, id INTEGER, updated_at INTEGER, PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS team_names (team_id INTEGER, key TEXT, lang TEXT, text TEXT,
                                       PRIMARY KEY (team_id, key, lang));
CREATE TABLE IF NOT EXISTS league_names (league_id INTEGER, key TEXT, lang TEXT, text TEXT,
                                         PRIMARY KEY (league_id, key, lang));
CREATE TABLE IF NOT EXISTS fields (kind TEXT, id INTEGER, field TEXT, value TEXT, PRIMARY KEY (kind, id, field));
CREATE TABLE IF NOT EXISTS country_names (country_id INTEGER, key TEXT, lang TEXT, text TEXT,
                                          PRIMARY KEY (country_id, key, lang));
CREATE TABLE IF NOT EXISTS created (kind TEXT, id INTEGER, created_at INTEGER, PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS league_members_set (league_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS league_members (league_id INTEGER, team_id INTEGER, ord INTEGER, hidden INTEGER DEFAULT 0,
                                           PRIMARY KEY (league_id, team_id));
CREATE TABLE IF NOT EXISTS pictures (kind TEXT, id INTEGER, slot TEXT, file TEXT, size INTEGER, digest TEXT,
                                     updated_at INTEGER, PRIMARY KEY (kind, id, slot));
CREATE TABLE IF NOT EXISTS hidden (kind TEXT, id INTEGER, PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS team_sources (team_id INTEGER PRIMARY KEY, template INTEGER, copy INTEGER);
CREATE TABLE IF NOT EXISTS team_rosters_set (team_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS team_rosters (team_id INTEGER, player_id INTEGER, ord INTEGER, jersey INTEGER,
                                         slot INTEGER, PRIMARY KEY (team_id, player_id));
CREATE TABLE IF NOT EXISTS team_kits (team_id INTEGER, kind INTEGER, config TEXT, PRIMARY KEY (team_id, kind));
CREATE TABLE IF NOT EXISTS player_sources (player_id INTEGER PRIMARY KEY, template INTEGER);
CREATE TABLE IF NOT EXISTS player_files (player_id INTEGER, name TEXT, file TEXT, size INTEGER, digest TEXT,
                                         PRIMARY KEY (player_id, name));
CREATE TABLE IF NOT EXISTS dates (kind TEXT, id INTEGER, created_at INTEGER, updated_at INTEGER,
                                  PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS stadium_names (stadium_id INTEGER, key TEXT, lang TEXT, text TEXT,
                                          PRIMARY KEY (stadium_id, key, lang));
CREATE TABLE IF NOT EXISTS team_stadiums (team_id INTEGER PRIMARY KEY, stadium_id INTEGER);
CREATE TABLE IF NOT EXISTS team_adboards (team_id INTEGER PRIMARY KEY, adboard_id INTEGER);
CREATE TABLE IF NOT EXISTS league_adboards (league_id INTEGER PRIMARY KEY, adboard_id INTEGER);
CREATE TABLE IF NOT EXISTS equipment_files (kind TEXT, id INTEGER, name TEXT, file TEXT, size INTEGER, digest TEXT,
                                            PRIMARY KEY (kind, id, name));
CREATE TABLE IF NOT EXISTS stadium_sources (stadium_id INTEGER PRIMARY KEY, template INTEGER, folder_stadium INTEGER);
CREATE TABLE IF NOT EXISTS stadium_scene (stadium_id INTEGER, name TEXT, file TEXT, size INTEGER, digest TEXT,
                                          PRIMARY KEY (stadium_id, name));
CREATE TABLE IF NOT EXISTS origins (kind TEXT, id INTEGER, source TEXT, source_id INTEGER, imported_at INTEGER,
                                    PRIMARY KEY (kind, id));
CREATE INDEX IF NOT EXISTS origins_source ON origins (source, kind, source_id);
CREATE INDEX IF NOT EXISTS pictures_file ON pictures (file);
CREATE INDEX IF NOT EXISTS player_files_file ON player_files (file);
CREATE INDEX IF NOT EXISTS equipment_files_file ON equipment_files (file);
CREATE INDEX IF NOT EXISTS stadium_scene_file ON stadium_scene (file);
"""
ADBOARD_PICTURE = 'board'  # picture slot of an advertising board
EQUIPMENT_PICTURE = 'thumbnail'  # picture slot of a boot, glove or ball (the user's; none = drawn from its files)
GAME_ADBOARD_MAX = 999  # the game's boards are numbered below this (teams.adboardid: 8 bits in the game)
FIRST_OWN_ADBOARD = 1001  # the boards the user creates
FIRST_OWN_STADIUM = 266  # the stadiums the user creates (the clean game's go up to 265; stadiumid has 9 bits)
MAX_STADIUM_ID = 511
STADIUM_ID_MARK = '#'  # stands for the stadium id in the names of stadium_scene
STADIUM_SCENE_NAME = f'data/sceneassets/stadium/stadium_{STADIUM_ID_MARK}.rx3'  # the scene a stadium needs
STADIUM_PICTURE = 'menu_{}'  # picture slot of a stadium's menu picture, per variant (0 1 3 4)
BENCH, RESERVE = 28, 29  # team_rosters.slot of a substitute and of a player out of the squad

Names = dict[str, dict[str, str]]  # {name key: {language or '*': text}}


class ProjectError(ValueError):
    pass


# what the project keeps of each kind of entity besides its names, fields, pictures and hidden flag:
# (table, id column); a change in any of these rows changes the entity's `updated_at`
OWN_TABLES = {
    'league': (('league_members_set', 'league_id'), ('league_members', 'league_id'), ('league_adboards', 'league_id')),
    'team': (('team_sources', 'team_id'), ('team_rosters_set', 'team_id'), ('team_rosters', 'team_id'),
             ('team_kits', 'team_id'), ('team_stadiums', 'team_id'), ('team_adboards', 'team_id')),
    'player': (('player_sources', 'player_id'), ('player_files', 'player_id')),
    'country': (),
    'stadium': (('stadium_sources', 'stadium_id'), ('stadium_scene', 'stadium_id')),
    'adboard': (),
    'boot': (),
    'glove': (),
    'ball': (),
}
# where a team or a league keeps its board: (table, id column)
ADBOARD_LINKS = {'team': ('team_adboards', 'team_id'), 'league': ('league_adboards', 'league_id')}


def _renumber_boards(con: sqlite3.Connection) -> None:
    """Schema 11 -> 12: the boards the user created (numbered from 1) take ids from FIRST_OWN_ADBOARD."""
    old = [r[0] for r in con.execute("SELECT id FROM created WHERE kind = 'adboard' AND id < ? ORDER BY id",
                                     (FIRST_OWN_ADBOARD,))]
    for k, oid in enumerate(old):
        new = FIRST_OWN_ADBOARD + 1000 + k  # past any id a renumbered board could take before it moves
        for table in ('created', 'fields', 'pictures', 'hidden', 'dates', 'edited'):
            con.execute(f"UPDATE {table} SET id = ? WHERE kind = 'adboard' AND id = ?", (new, oid))
        for table in ('team_adboards', 'league_adboards'):
            con.execute(f'UPDATE {table} SET adboard_id = ? WHERE adboard_id = ?', (new, oid))
    for k in range(len(old)):  # then down to FIRST_OWN_ADBOARD, FIRST_OWN_ADBOARD + 1, ...
        for table in ('created', 'fields', 'pictures', 'hidden', 'dates', 'edited'):
            con.execute(f"UPDATE {table} SET id = ? WHERE kind = 'adboard' AND id = ?",
                        (FIRST_OWN_ADBOARD + k, FIRST_OWN_ADBOARD + 1000 + k))
        for table in ('team_adboards', 'league_adboards'):
            con.execute(f'UPDATE {table} SET adboard_id = ? WHERE adboard_id = ?',
                        (FIRST_OWN_ADBOARD + k, FIRST_OWN_ADBOARD + 1000 + k))


def _snapshot(con: sqlite3.Connection, kind: str, oid: int) -> list:
    """Everything the project keeps of one entity, to tell whether a change really changed it."""
    out = []
    tables = [(NAME_TABLES[kind][0], NAME_TABLES[kind][1], '')] if kind in NAME_TABLES else []
    tables += [('fields', 'id', ' AND kind = :kind'), ('pictures', 'id', ' AND kind = :kind'),
               ('hidden', 'id', ' AND kind = :kind')]
    if kind in EQUIPMENT_KINDS:
        tables.append(('equipment_files', 'id', ' AND kind = :kind'))
    tables += [(table, column, '') for table, column in OWN_TABLES.get(kind, ())]
    for table, column, extra in tables:
        skip = {'updated_at'} if table == 'pictures' else set()  # the picture's own save time is not its content
        rows = con.execute(f'SELECT * FROM {table} WHERE {column} = :id{extra}',  # files: their digest, not bytes
                           {'id': oid, 'kind': kind}).fetchall()
        out.append((table, sorted(tuple(v for k, v in zip(r.keys(), r) if k not in skip) for r in rows)))
    return out


def _dated(method):
    """Keeps the entity's dates (table `dates`) after a change made by `method(self, kind?, id, ...)`: every real change
    updates it now (a created entity got its creation date from create(); a game entity never has one); an original
    left with nothing of the project loses its dates (it is the game's again)."""
    import functools
    import inspect
    params = list(inspect.signature(method).parameters)
    fixed = {'set_members': 'league', 'set_team_source': 'team', 'set_roster': 'team', 'set_kit': 'team',
             'set_team_stadium': 'team', 'set_player_source': 'player',
             'set_player_files': 'player', 'set_stadium_source': 'stadium',
             'set_stadium_scene': 'stadium'}.get(method.__name__)

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        bound = dict(zip(params[1:], args), **kwargs)
        kind = fixed or bound['kind']
        oid = bound[params[1]] if fixed else bound['oid']
        con = self.connect()
        try:
            before = _snapshot(con, kind, oid) if kind in KINDS else None
        finally:
            con.close()
        result = method(self, *args, **kwargs)
        if before is not None:
            self._stamp(kind, oid, before)
        return result
    return wrapper


class Project:
    def __init__(self, path: str):
        self.path = path
        # the files live next to the database, in a folder of its own (two projects in one folder never share it)
        self.files = FileStore(os.path.splitext(os.path.abspath(path))[0] + FILES_SUFFIX)
        con = self.connect()
        try:
            found = con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
            row = None
            if found:
                row = con.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
                if row and int(row[0]) > SCHEMA_VERSION:
                    raise ProjectError('project made by a newer version of the app')
            if 'data' in {r[1] for r in con.execute('PRAGMA table_info(pictures)')}:  # schema 14 and older
                raise ProjectError('project made by an older version of the app (files inside the database): '
                                   'it is not converted, start a new project')
            had_dates = found and con.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'dates'").fetchone()
            con.executescript(SCHEMA)
            if found and row and int(row[0]) == 11:  # created boards move out of the game's numbers
                _renumber_boards(con)
            if found and row and int(row[0]) < 10:  # a game entity was never created by the project
                con.execute('UPDATE dates SET created_at = NULL WHERE NOT EXISTS (SELECT 1 FROM created c '
                            'WHERE c.kind = dates.kind AND c.id = dates.id)')
            if found and not had_dates:  # schema 7 and older: the dates they had
                con.execute('INSERT OR IGNORE INTO dates SELECT kind, id, created_at, created_at FROM created')
                con.execute('INSERT OR IGNORE INTO dates SELECT kind, id, NULL, updated_at FROM edited')
                con.execute('UPDATE dates SET updated_at = (SELECT MAX(dates.updated_at, e.updated_at) FROM edited e '
                            'WHERE e.kind = dates.kind AND e.id = dates.id) WHERE EXISTS (SELECT 1 FROM edited e '
                            'WHERE e.kind = dates.kind AND e.id = dates.id)')
            if 'hidden' not in {r[1] for r in con.execute('PRAGMA table_info(team_rosters)')}:  # schema 5 and older
                con.execute('ALTER TABLE team_rosters ADD COLUMN hidden INTEGER DEFAULT 0')
            if 'hidden' not in {r[1] for r in con.execute('PRAGMA table_info(league_members)')}:  # schema 6 and older
                con.execute('ALTER TABLE league_members ADD COLUMN hidden INTEGER DEFAULT 0')
            if 'folder_stadium' not in {r[1] for r in con.execute('PRAGMA table_info(stadium_sources)')}:
                con.execute('ALTER TABLE stadium_sources ADD COLUMN folder_stadium INTEGER')
            if not row or row[0] != str(SCHEMA_VERSION):  # opening an up-to-date project never writes to it (the
                # patch's "up to date" compares the file: f14api.patch_info)
                con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
            con.commit()
        finally:
            con.close()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    # ---- any entity -------------------------------------------------------------------------------------------

    def names(self, kind: str, oid: int) -> Names:
        if kind not in NAME_TABLES:
            return {}
        table, column = NAME_TABLES[kind]
        con = self.connect()
        try:
            out: Names = {}
            for r in con.execute(f'SELECT key, lang, text FROM {table} WHERE {column} = ?', (oid,)):
                out.setdefault(r['key'], {})[r['lang']] = r['text']
            return out
        finally:
            con.close()

    def fields(self, kind: str, oid: int) -> dict:
        con = self.connect()
        try:
            return {r['field']: json.loads(r['value'])
                    for r in con.execute('SELECT field, value FROM fields WHERE kind = ? AND id = ?', (kind, oid))}
        finally:
            con.close()

    @_dated
    def save(self, kind: str, oid: int, names: Names | None = None, fields: dict | None = None) -> None:
        """Replaces everything saved for the entity; empty texts are dropped (= original)."""
        if kind not in KINDS:
            raise ProjectError(f'unknown kind {kind}')
        name_rows = [(oid, key, lang, text.strip()) for key, by_lang in (names or {}).items()
                     for lang, text in by_lang.items() if text and text.strip()]
        if name_rows and kind not in NAME_TABLES:
            raise ProjectError(f'{kind} has no language names')
        field_rows = [(kind, oid, name, json.dumps(value, ensure_ascii=False))
                      for name, value in (fields or {}).items() if value is not None]
        con = self.connect()
        try:
            if kind in NAME_TABLES:
                table, column = NAME_TABLES[kind]
                con.execute(f'DELETE FROM {table} WHERE {column} = ?', (oid,))
                con.executemany(f'INSERT INTO {table} VALUES (?,?,?,?)', name_rows)
            con.execute('DELETE FROM fields WHERE kind = ? AND id = ?', (kind, oid))
            con.executemany('INSERT INTO fields VALUES (?,?,?,?)', field_rows)
            own = kind == 'team' and con.execute(  # a team's squad, kits, pictures, stadium or board keep it edited
                'SELECT 1 FROM team_rosters_set WHERE team_id = ? UNION SELECT 1 FROM team_kits WHERE team_id = ? '
                "UNION SELECT 1 FROM pictures WHERE kind = 'team' AND id = ? "
                'UNION SELECT 1 FROM team_stadiums WHERE team_id = ? UNION SELECT 1 FROM team_adboards WHERE team_id = ?',
                (oid, oid, oid, oid, oid)).fetchone()
            own = own or kind == 'league' and con.execute(  # a league's board too
                'SELECT 1 FROM league_adboards WHERE league_id = ?', (oid,)).fetchone()
            own = own or kind == 'player' and con.execute(  # a player's photo or face files too
                "SELECT 1 FROM pictures WHERE kind = 'player' AND id = ? UNION "
                'SELECT 1 FROM player_files WHERE player_id = ?', (oid, oid)).fetchone()
            own = own or kind in EQUIPMENT_KINDS and con.execute(  # an item's files or picture too
                'SELECT 1 FROM equipment_files WHERE kind = ? AND id = ? UNION '
                'SELECT 1 FROM pictures WHERE kind = ? AND id = ?', (kind, oid, kind, oid)).fetchone()
            own = own or kind == 'stadium' and con.execute(  # a stadium's scene or menu picture too
                "SELECT 1 FROM stadium_scene WHERE stadium_id = ? UNION "
                "SELECT 1 FROM pictures WHERE kind = 'stadium' AND id = ?", (oid, oid)).fetchone()
            if name_rows or field_rows or own:
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', (kind, oid, int(time.time())))
            else:
                con.execute('DELETE FROM edited WHERE kind = ? AND id = ?', (kind, oid))
            con.commit()
        finally:
            con.close()

    @_dated
    def reset(self, kind: str, oid: int) -> None:
        con = self.connect()
        try:
            left = self._entity_files(con, kind, oid)
            con.execute('DELETE FROM pictures WHERE kind = ? AND id = ?', (kind, oid))
            if kind == 'team':
                for table in ('team_rosters', 'team_rosters_set', 'team_kits', 'team_stadiums', 'team_adboards'):
                    con.execute(f'DELETE FROM {table} WHERE team_id = ?', (oid,))
            if kind == 'league':
                con.execute('DELETE FROM league_adboards WHERE league_id = ?', (oid,))
            if kind == 'player':
                con.execute('DELETE FROM player_files WHERE player_id = ?', (oid,))
            if kind in EQUIPMENT_KINDS:
                con.execute('DELETE FROM equipment_files WHERE kind = ? AND id = ?', (kind, oid))
            if kind == 'stadium':
                con.execute('DELETE FROM stadium_scene WHERE stadium_id = ?', (oid,))
                if not con.execute("SELECT 1 FROM created WHERE kind = 'stadium' AND id = ?", (oid,)).fetchone():
                    con.execute('DELETE FROM stadium_sources WHERE stadium_id = ?', (oid,))  # a game stadium's folder
            con.execute('DELETE FROM origins WHERE kind = ? AND id = ?', (kind, oid))  # no longer what came in
            con.commit()
            self.files.release(con, left)
        finally:
            con.close()
        self.save(kind, oid)

    # ---- files (f14mod.filestore) ---------------------------------------------------------------------------

    @staticmethod
    def _entity_files(con: sqlite3.Connection, kind: str, oid: int) -> set[str]:
        """The files the entity's rows point to."""
        out = {r[0] for r in con.execute('SELECT file FROM pictures WHERE kind = ? AND id = ?', (kind, oid))}
        if kind == 'player':
            out.update(r[0] for r in con.execute('SELECT file FROM player_files WHERE player_id = ?', (oid,)))
        if kind in EQUIPMENT_KINDS:
            out.update(r[0] for r in con.execute('SELECT file FROM equipment_files WHERE kind = ? AND id = ?',
                                                 (kind, oid)))
        if kind == 'stadium':
            out.update(r[0] for r in con.execute('SELECT file FROM stadium_scene WHERE stadium_id = ?', (oid,)))
        return out

    def file_bytes(self, rel: str | None) -> bytes | None:
        return self.files.read(rel) if rel else None

    def file_path(self, rel: str) -> str:
        """Where a file of the project is on disk."""
        return self.files.path(rel)

    def prune_files(self, min_age: float = 60.0) -> int:
        """Removes the files no row points to (a cancelled import leaves some); how many."""
        con = self.connect()
        try:
            return self.files.prune(con, min_age)
        finally:
            con.close()

    # ---- pictures -------------------------------------------------------------------------------------------

    @_dated
    def set_picture(self, kind: str, oid: int, slot: str, data: bytes | None) -> None:
        """Keeps (or, with None, removes) a picture of the entity; a picture marks the entity as edited."""
        con = self.connect()
        try:
            old = con.execute('SELECT file FROM pictures WHERE kind = ? AND id = ? AND slot = ?',
                              (kind, oid, slot)).fetchone()
            if data is None:
                con.execute('DELETE FROM pictures WHERE kind = ? AND id = ? AND slot = ?', (kind, oid, slot))
            else:
                rel, size, dig = self.files.put(PICTURES, data, '.png')
                con.execute('INSERT OR REPLACE INTO pictures (kind, id, slot, file, size, digest, updated_at) '
                            'VALUES (?, ?, ?, ?, ?, ?, ?)', (kind, oid, slot, rel, size, dig, int(time.time())))
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', (kind, oid, int(time.time())))
            if data is None and not con.execute(
                    'SELECT 1 FROM fields WHERE kind = ? AND id = ? UNION SELECT 1 FROM pictures '
                    'WHERE kind = ? AND id = ?', (kind, oid, kind, oid)).fetchone():
                table = NAME_TABLES.get(kind)
                if not table or not con.execute(f'SELECT 1 FROM {table[0]} WHERE {table[1]} = ?', (oid,)).fetchone():
                    con.execute('DELETE FROM edited WHERE kind = ? AND id = ?', (kind, oid))
            con.commit()
            if old:
                self.files.release(con, [old[0]])
        finally:
            con.close()

    def picture(self, kind: str, oid: int, slot: str) -> tuple[bytes, int] | None:
        """(PNG bytes, saved at) or None."""
        con = self.connect()
        try:
            r = con.execute('SELECT file, updated_at FROM pictures WHERE kind = ? AND id = ? AND slot = ?',
                            (kind, oid, slot)).fetchone()
        finally:
            con.close()
        data = self.file_bytes(r[0]) if r else None
        return (data, r[1]) if data is not None else None

    def with_picture(self, kind: str, slot: str) -> list[int]:
        con = self.connect()
        try:
            return [r[0] for r in con.execute('SELECT id FROM pictures WHERE kind = ? AND slot = ? ORDER BY id',
                                              (kind, slot))]
        finally:
            con.close()

    def all_names(self, kind: str) -> dict[int, Names]:
        table, column = NAME_TABLES[kind]
        con = self.connect()
        try:
            out: dict[int, Names] = {}
            for r in con.execute(f'SELECT {column} AS id, key, lang, text FROM {table}'):
                out.setdefault(r['id'], {}).setdefault(r['key'], {})[r['lang']] = r['text']
            return out
        finally:
            con.close()

    def all_fields(self, kind: str) -> dict[int, dict]:
        con = self.connect()
        try:
            out: dict[int, dict] = {}
            for r in con.execute('SELECT id, field, value FROM fields WHERE kind = ?', (kind,)):
                out.setdefault(r['id'], {})[r['field']] = json.loads(r['value'])
            return out
        finally:
            con.close()

    def counts(self) -> dict[str, int]:
        con = self.connect()
        try:
            out = {r['kind']: r['n'] for r in con.execute(
                'SELECT kind, COUNT(*) AS n FROM edited e WHERE NOT EXISTS '
                '(SELECT 1 FROM created c WHERE c.kind = e.kind AND c.id = e.id) GROUP BY kind')}  # a created one counts once
            for r in con.execute('SELECT kind, COUNT(*) AS n FROM created GROUP BY kind'):
                out[f'new_{r["kind"]}'] = r['n']
            return out
        finally:
            con.close()

    # ---- dates ----------------------------------------------------------------------------------------------------

    def now(self) -> int:
        return int(time.time())

    def _stamp(self, kind: str, oid: int, before: list) -> None:
        con = self.connect()
        try:
            after = _snapshot(con, kind, oid)
            created = con.execute('SELECT 1 FROM created WHERE kind = ? AND id = ?', (kind, oid)).fetchone()
            if not created and not any(rows for _, rows in after):
                con.execute('DELETE FROM dates WHERE kind = ? AND id = ?', (kind, oid))
            elif after != before:
                now = self.now()
                # only an entity the user created has a creation date (create() sets it); an entity that already has
                # dates keeps its creation date, even none (edited before schema 8)
                con.execute('INSERT INTO dates VALUES (?, ?, ?, ?) ON CONFLICT (kind, id) DO UPDATE SET '
                            'updated_at = excluded.updated_at', (kind, oid, now if created else None, now))
            con.commit()
        finally:
            con.close()

    def dates(self, kind: str, oid: int) -> tuple[int | None, int | None]:
        """(created at, updated at) of the entity, Unix time; (None, None) for a game entity the project does not
        change."""
        con = self.connect()
        try:
            r = con.execute('SELECT created_at, updated_at FROM dates WHERE kind = ? AND id = ?', (kind, oid)).fetchone()
            return (r[0], r[1]) if r else (None, None)
        finally:
            con.close()

    # ---- where imported entities came from (f14mod.share) ------------------------------------------------------

    def uid(self, create: bool = True) -> str | None:
        """The project's own id (made the first time it is asked for, unless `create` is false: then None until it
        has one): the source of what it exports."""
        con = self.connect()
        try:
            row = con.execute("SELECT value FROM meta WHERE key = 'uid'").fetchone()
            if row or not create:
                return row[0] if row else None
            import uuid
            value = uuid.uuid4().hex
            con.execute("INSERT INTO meta VALUES ('uid', ?)", (value,))
            con.commit()
            return value
        finally:
            con.close()

    def origin(self, kind: str, oid: int) -> tuple[str, int] | None:
        """(source, id it had there) of an entity that came in by an import; None for any other."""
        con = self.connect()
        try:
            r = con.execute('SELECT source, source_id FROM origins WHERE kind = ? AND id = ?', (kind, oid)).fetchone()
            return (r[0], r[1]) if r else None
        finally:
            con.close()

    def find_origin(self, kind: str, source: str, source_id: int) -> int | None:
        """The entity that came in from (source, source_id), when it is still in the project."""
        con = self.connect()
        try:
            r = con.execute('SELECT o.id FROM origins o WHERE o.kind = ? AND o.source = ? AND o.source_id = ? AND '
                            'EXISTS (SELECT 1 FROM created c WHERE c.kind = o.kind AND c.id = o.id) ORDER BY o.id',
                            (kind, source, source_id)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def changed_since_import(self, kind: str, oid: int) -> bool:
        """The user changed the entity after it came in."""
        con = self.connect()
        try:
            r = con.execute('SELECT 1 FROM origins o JOIN dates d ON d.kind = o.kind AND d.id = o.id '
                            'WHERE o.kind = ? AND o.id = ? AND d.updated_at > o.imported_at', (kind, oid)).fetchone()
            return r is not None
        finally:
            con.close()

    # ---- created entities -------------------------------------------------------------------------------------

    def create(self, kind: str, oid: int, names: Names | None = None, fields: dict | None = None) -> None:
        if kind not in KINDS:
            raise ProjectError(f'unknown kind {kind}')
        con = self.connect()
        try:
            now = self.now()
            con.execute('INSERT INTO created VALUES (?, ?, ?)', (kind, oid, now))
            con.execute('INSERT OR REPLACE INTO dates VALUES (?, ?, ?, ?)', (kind, oid, now, now))
            con.commit()
        except sqlite3.IntegrityError:
            raise ProjectError(f'{kind} {oid} exists') from None
        finally:
            con.close()
        self.save(kind, oid, names, fields)

    def is_created(self, kind: str, oid: int) -> bool:
        con = self.connect()
        try:
            return con.execute('SELECT 1 FROM created WHERE kind = ? AND id = ?', (kind, oid)).fetchone() is not None
        finally:
            con.close()

    def created(self, kind: str) -> list[int]:
        con = self.connect()
        try:
            return [r[0] for r in con.execute('SELECT id FROM created WHERE kind = ? ORDER BY id', (kind,))]
        finally:
            con.close()

    def delete(self, kind: str, oid: int) -> None:
        """Removes a created entity and everything saved for it (a board leaves the teams and leagues it was on)."""
        if kind == 'adboard':
            users = self.adboard_users(oid)
            for user_kind, ids in users.items():
                for user in ids:
                    self.set_adboard_link(user_kind, user, None)
        self.reset(kind, oid)
        con = self.connect()
        try:
            con.execute('DELETE FROM created WHERE kind = ? AND id = ?', (kind, oid))
            con.execute('DELETE FROM hidden WHERE kind = ? AND id = ?', (kind, oid))
            con.execute('DELETE FROM dates WHERE kind = ? AND id = ?', (kind, oid))
            if kind == 'league':
                con.execute('DELETE FROM league_members WHERE league_id = ?', (oid,))
                con.execute('DELETE FROM league_members_set WHERE league_id = ?', (oid,))
                con.execute('DELETE FROM league_adboards WHERE league_id = ?', (oid,))
            if kind == 'team':
                con.execute('DELETE FROM league_members WHERE team_id = ?', (oid,))
                for table in ('team_sources', 'team_rosters', 'team_rosters_set', 'team_kits', 'team_stadiums',
                              'team_adboards'):
                    con.execute(f'DELETE FROM {table} WHERE team_id = ?', (oid,))
            if kind == 'player':  # out of every squad the user set too
                con.execute('DELETE FROM player_sources WHERE player_id = ?', (oid,))
                con.execute('DELETE FROM team_rosters WHERE player_id = ?', (oid,))
            if kind == 'stadium':  # its teams play in the game's stadium again
                con.execute('DELETE FROM stadium_sources WHERE stadium_id = ?', (oid,))
                con.execute('DELETE FROM team_stadiums WHERE stadium_id = ?', (oid,))
            con.commit()
        finally:
            con.close()

    # ---- left out of the patch ---------------------------------------------------------------------------------

    @_dated
    def set_hidden(self, kind: str, oid: int, hidden: bool) -> None:
        con = self.connect()
        try:
            if hidden:
                con.execute('INSERT OR IGNORE INTO hidden VALUES (?, ?)', (kind, oid))
            else:
                con.execute('DELETE FROM hidden WHERE kind = ? AND id = ?', (kind, oid))
            con.commit()
        finally:
            con.close()

    def hidden(self, kind: str) -> set[int]:
        con = self.connect()
        try:
            return {r[0] for r in con.execute('SELECT id FROM hidden WHERE kind = ?', (kind,))}
        finally:
            con.close()

    def hidden_in_game(self, kind: str) -> set[int]:
        """The hidden originals: the patch hides them in the game."""
        return self.hidden(kind) - set(self.created(kind))

    def visible(self) -> 'Project':
        """The project without the hidden created entities and the created stadiums that cannot enter the game yet
        (what the builder reads)."""
        out = {kind: self.hidden(kind) & set(self.created(kind)) for kind in KINDS}
        out['stadium'] |= self.incomplete_stadiums()
        out['team'] |= self.incomplete_teams()
        out['player'] |= self.incomplete_players()
        for kind in EQUIPMENT_KINDS:
            out[kind] |= self.incomplete_equipment(kind)
        return VisibleProject(self, out) if any(self.hidden(kind) for kind in KINDS) or any(out.values()) else self

    def incomplete_stadiums(self) -> set[int]:
        """Created stadiums made from scratch still without a 3D scene or a field the game needs: left out of the
        patch."""
        con = self.connect()
        try:
            scratch = [r[0] for r in con.execute(
                "SELECT c.id FROM created c LEFT JOIN stadium_sources s ON s.stadium_id = c.id "
                "WHERE c.kind = 'stadium' AND s.template IS NULL")]
            scenes = {r[0] for r in con.execute('SELECT stadium_id FROM stadium_scene WHERE name = ?',
                                                (STADIUM_SCENE_NAME,))}
        finally:
            con.close()
        return {sid for sid in scratch if sid not in scenes or self.missing_stadium_fields(sid)}

    def incomplete_teams(self) -> set[int]:
        """Created teams made from scratch (blank, no template) still missing something every team of the game has:
        left out of the patch until it is set (missing_team_parts)."""
        con = self.connect()
        try:
            scratch = [r[0] for r in con.execute(
                "SELECT c.id FROM created c JOIN team_sources s ON s.team_id = c.id "
                "WHERE c.kind = 'team' AND s.template IS NULL AND s.copy = 0")]
        finally:
            con.close()
        if not scratch:
            return set()
        out_of_patch = self.incomplete_players()  # once for all the teams, not once per team
        return {tid for tid in scratch if self.missing_team_parts(tid, out_of_patch)}

    def missing_team_parts(self, team_id: int, out_of_patch: set[int] | None = None) -> dict:
        """What a team made from scratch still needs: {'fields': fields.TEAM_REQUIRED not saved, 'stadium': no stadium
        chosen, 'players': players in its squad (fewer than a lineup)}; empty = complete. out_of_patch: the
        incomplete_players() already known (checking many teams)."""
        from .fields import TEAM_REQUIRED
        saved = self.fields('team', team_id)
        out = {}
        missing = [f for f in TEAM_REQUIRED if saved.get(f) is None]
        if missing:
            out['fields'] = missing
        if self.team_stadium(team_id) is None:
            out['stadium'] = True
        con = self.connect()
        try:
            players = con.execute(
                "SELECT r.player_id FROM team_rosters r WHERE r.team_id = ? AND COALESCE(r.hidden, 0) = 0 AND NOT EXISTS "
                "(SELECT 1 FROM hidden h WHERE h.kind = 'player' AND h.id = r.player_id)", (team_id,)).fetchall()
        finally:
            con.close()
        if out_of_patch is None:
            out_of_patch = self.incomplete_players()
        players = len([r for r in players if r[0] not in out_of_patch])
        if players < 11:
            out['players'] = players
        return out

    def incomplete_equipment(self, kind: str) -> set[int]:
        """Created boots, gloves or balls still without the files they need (EQUIPMENT_NEEDS): left out of the
        patch (no row in the game's lists, no files) until they have them."""
        return {code for code in self.created(kind)
                if not all(n in self.equipment_files(kind, code) for n in EQUIPMENT_NEEDS[kind])}

    def blank_players(self) -> set[int]:
        """Created players made from scratch (no template): blank until the user fills fields.PLAYER_REQUIRED."""
        con = self.connect()
        try:
            return {r[0] for r in con.execute(
                "SELECT c.id FROM created c JOIN player_sources s ON s.player_id = c.id "
                "WHERE c.kind = 'player' AND s.template IS NULL")}
        finally:
            con.close()

    def missing_player_fields(self, player_id: int) -> list[str]:
        """The fields a player made from scratch still needs (fields.PLAYER_REQUIRED not saved yet)."""
        from .fields import PLAYER_REQUIRED
        saved = self.fields('player', player_id)
        return [f for f in PLAYER_REQUIRED if saved.get(f) is None]

    def incomplete_players(self) -> set[int]:
        """Players made from scratch still missing a required field: left out of the patch until it is saved.
        One query for all of them (a big import brings thousands)."""
        from .fields import PLAYER_REQUIRED
        blank = self.blank_players()
        if not blank:
            return set()
        con = self.connect()
        try:
            marks = ','.join('?' * len(PLAYER_REQUIRED))
            saved: dict[int, set[str]] = {}
            for pid, field, value in con.execute(
                    f"SELECT id, field, value FROM fields WHERE kind = 'player' AND field IN ({marks})",
                    tuple(PLAYER_REQUIRED)):
                if pid in blank and value is not None and json.loads(value) is not None:
                    saved.setdefault(pid, set()).add(field)
        finally:
            con.close()
        need = set(PLAYER_REQUIRED)
        return {pid for pid in blank if not need <= saved.get(pid, set())}

    def missing_stadium_fields(self, stadium_id: int) -> list[str]:
        """The fields a stadium made from scratch still needs (fields.STADIUM_REQUIRED not saved yet)."""
        from .fields import STADIUM_REQUIRED
        saved = self.fields('stadium', stadium_id)
        return [f for f in STADIUM_REQUIRED if saved.get(f) is None]

    # ---- teams of a league ------------------------------------------------------------------------------------

    @_dated
    def set_members(self, league_id: int, team_ids: list[int] | None, hidden=None) -> None:
        """The whole team list of a league, in order; None = the game's teams again. `hidden`: the teams left out of
        the patch in this league only (None = the ones that were hidden stay hidden)."""
        con = self.connect()
        try:
            if hidden is None:
                hidden = {r[0] for r in con.execute(
                    'SELECT team_id FROM league_members WHERE league_id = ? AND hidden = 1', (league_id,))}
            con.execute('DELETE FROM league_members WHERE league_id = ?', (league_id,))
            con.execute('DELETE FROM league_members_set WHERE league_id = ?', (league_id,))
            if team_ids is not None:
                con.execute('INSERT INTO league_members_set VALUES (?)', (league_id,))
                con.executemany('INSERT OR IGNORE INTO league_members VALUES (?, ?, ?, ?)',
                                [(league_id, tid, i, int(tid in hidden)) for i, tid in enumerate(team_ids)])
            con.commit()
        finally:
            con.close()

    def members(self, league_id: int) -> list[int] | None:
        con = self.connect()
        try:
            if not con.execute('SELECT 1 FROM league_members_set WHERE league_id = ?', (league_id,)).fetchone():
                return None
            return [r[0] for r in con.execute(
                'SELECT team_id FROM league_members WHERE league_id = ? ORDER BY ord', (league_id,))]
        finally:
            con.close()

    def all_hidden_members(self) -> dict[int, set[int]]:
        """The teams left out of the patch in a league only: {league: team ids}."""
        con = self.connect()
        try:
            out: dict[int, set[int]] = {}
            for r in con.execute('SELECT league_id, team_id FROM league_members WHERE hidden = 1'):
                out.setdefault(r[0], set()).add(r[1])
            return out
        finally:
            con.close()

    def all_members(self) -> dict[int, list[int]]:
        con = self.connect()
        try:
            out: dict[int, list[int]] = {r[0]: [] for r in con.execute('SELECT league_id FROM league_members_set')}
            for r in con.execute('SELECT league_id, team_id FROM league_members ORDER BY league_id, ord'):
                out.setdefault(r[0], []).append(r[1])
            return out
        finally:
            con.close()

    # ---- teams: source, squad, kits ---------------------------------------------------------------------------

    @_dated
    def set_team_source(self, team_id: int, template: int | None, copy: bool) -> None:
        """template None = made from scratch (blank: fields.TEAM_REQUIRED unset, out of the patch until filled)."""
        con = self.connect()
        try:
            con.execute('INSERT OR REPLACE INTO team_sources VALUES (?, ?, ?)', (team_id, template, int(copy)))
            con.commit()
        finally:
            con.close()

    def team_source(self, team_id: int) -> tuple[int | None, bool] | None:
        """(template team, crest and kits copied) of a created team; template None = made from scratch (blank)."""
        con = self.connect()
        try:
            r = con.execute('SELECT template, copy FROM team_sources WHERE team_id = ?', (team_id,)).fetchone()
            return (r[0], bool(r[1])) if r else None
        finally:
            con.close()

    @_dated
    def set_roster(self, team_id: int, rows: list[dict] | None) -> None:
        """The whole squad of a team, in order: [{'player', 'jersey', 'slot', 'hidden'}]; None = the game's squad
        again. `hidden` = out of the patch in this team only."""
        con = self.connect()
        try:
            con.execute('DELETE FROM team_rosters WHERE team_id = ?', (team_id,))
            con.execute('DELETE FROM team_rosters_set WHERE team_id = ?', (team_id,))
            if rows is not None:
                con.execute('INSERT INTO team_rosters_set VALUES (?)', (team_id,))
                con.executemany('INSERT OR IGNORE INTO team_rosters (team_id, player_id, ord, jersey, slot, hidden) '
                                'VALUES (?, ?, ?, ?, ?, ?)',
                                [(team_id, r['player'], i, r.get('jersey'), r.get('slot', RESERVE),
                                  int(bool(r.get('hidden')))) for i, r in enumerate(rows)])
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', ('team', team_id, int(time.time())))
            con.commit()
        finally:
            con.close()

    def roster(self, team_id: int) -> list[dict] | None:
        con = self.connect()
        try:
            if not con.execute('SELECT 1 FROM team_rosters_set WHERE team_id = ?', (team_id,)).fetchone():
                return None
            return [{'player': r[0], 'jersey': r[1], 'slot': r[2], 'hidden': bool(r[3])} for r in con.execute(
                'SELECT player_id, jersey, slot, hidden FROM team_rosters WHERE team_id = ? ORDER BY ord', (team_id,))]
        finally:
            con.close()

    def all_rosters(self) -> dict[int, list[dict]]:
        con = self.connect()
        try:
            out: dict[int, list[dict]] = {r[0]: [] for r in con.execute('SELECT team_id FROM team_rosters_set')}
            for r in con.execute('SELECT team_id, player_id, jersey, slot, hidden FROM team_rosters '
                                 'ORDER BY team_id, ord'):
                out.setdefault(r[0], []).append({'player': r[1], 'jersey': r[2], 'slot': r[3], 'hidden': bool(r[4])})
            return out
        finally:
            con.close()

    @_dated
    def set_kit(self, team_id: int, kind: int, config: dict | None) -> None:
        """Where one kit of the team comes from (see f14mod.teamkits); None = the game's (or the template's)."""
        con = self.connect()
        try:
            if config is None:
                con.execute('DELETE FROM team_kits WHERE team_id = ? AND kind = ?', (team_id, kind))
            else:
                con.execute('INSERT OR REPLACE INTO team_kits VALUES (?, ?, ?)',
                            (team_id, kind, json.dumps(config, ensure_ascii=False)))
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', ('team', team_id, int(time.time())))
            con.commit()
        finally:
            con.close()

    def kits(self, team_id: int) -> dict[int, dict]:
        con = self.connect()
        try:
            return {r[0]: json.loads(r[1]) for r in con.execute(
                'SELECT kind, config FROM team_kits WHERE team_id = ? ORDER BY kind', (team_id,))}
        finally:
            con.close()

    def all_kits(self) -> dict[int, dict[int, dict]]:
        con = self.connect()
        try:
            out: dict[int, dict[int, dict]] = {}
            for r in con.execute('SELECT team_id, kind, config FROM team_kits ORDER BY team_id, kind'):
                out.setdefault(r[0], {})[r[1]] = json.loads(r[2])
            return out
        finally:
            con.close()

    @_dated
    def set_team_stadium(self, team_id: int, stadium_id: int | None) -> None:
        """The stadium the team plays in; None = the game's (or, for a created team, the one of the team it copies)."""
        con = self.connect()
        try:
            if stadium_id is None:
                con.execute('DELETE FROM team_stadiums WHERE team_id = ?', (team_id,))
            else:
                con.execute('INSERT OR REPLACE INTO team_stadiums VALUES (?, ?)', (team_id, stadium_id))
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', ('team', team_id, int(time.time())))
            if stadium_id is None and not con.execute(  # nothing else of the team left: it is the game's again
                    "SELECT 1 FROM fields WHERE kind = 'team' AND id = ? UNION SELECT 1 FROM team_names WHERE team_id = ? "
                    "UNION SELECT 1 FROM pictures WHERE kind = 'team' AND id = ? UNION SELECT 1 FROM team_kits "
                    'WHERE team_id = ? UNION SELECT 1 FROM team_rosters_set WHERE team_id = ? '
                    'UNION SELECT 1 FROM team_adboards WHERE team_id = ?',
                    (team_id,) * 6).fetchone():
                con.execute("DELETE FROM edited WHERE kind = 'team' AND id = ?", (team_id,))
            con.commit()
        finally:
            con.close()

    def team_stadium(self, team_id: int) -> int | None:
        con = self.connect()
        try:
            r = con.execute('SELECT stadium_id FROM team_stadiums WHERE team_id = ?', (team_id,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def all_team_stadiums(self) -> dict[int, int]:
        con = self.connect()
        try:
            return {r[0]: r[1] for r in con.execute('SELECT team_id, stadium_id FROM team_stadiums')}
        finally:
            con.close()

    # ---- advertising boards -------------------------------------------------------------------------------------

    @_dated
    def set_adboard_link(self, kind: str, oid: int, adboard_id: int | None) -> None:
        """The board of a team or a league (kind 'team' / 'league'); None = none (the game's own boards)."""
        table, column = ADBOARD_LINKS[kind]
        con = self.connect()
        try:
            if adboard_id is None:
                con.execute(f'DELETE FROM {table} WHERE {column} = ?', (oid,))
            else:
                con.execute(f'INSERT OR REPLACE INTO {table} VALUES (?, ?)', (oid, adboard_id))
            con.commit()
        finally:
            con.close()
        self.save(kind, oid, self.names(kind, oid), self.fields(kind, oid))  # keeps `edited` right

    def adboard_link(self, kind: str, oid: int) -> int | None:
        table, column = ADBOARD_LINKS[kind]
        con = self.connect()
        try:
            r = con.execute(f'SELECT adboard_id FROM {table} WHERE {column} = ?', (oid,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def all_adboard_links(self, kind: str) -> dict[int, int]:
        """{team or league id: board id}."""
        table, column = ADBOARD_LINKS[kind]
        con = self.connect()
        try:
            return {r[0]: r[1] for r in con.execute(f'SELECT {column}, adboard_id FROM {table}')}
        finally:
            con.close()

    def adboard_users(self, adboard_id: int) -> dict[str, list[int]]:
        """The teams and leagues a board is on: {'team': [...], 'league': [...]}."""
        con = self.connect()
        try:
            return {kind: [r[0] for r in con.execute(
                f'SELECT {column} FROM {table} WHERE adboard_id = ? ORDER BY {column}', (adboard_id,))]
                for kind, (table, column) in ADBOARD_LINKS.items()}
        finally:
            con.close()

    def next_adboard_id(self) -> int:
        con = self.connect()
        try:
            r = con.execute("SELECT MAX(id) FROM created WHERE kind = 'adboard'").fetchone()
            return max(FIRST_OWN_ADBOARD, (r[0] or 0) + 1)
        finally:
            con.close()

    # ---- players: source and face files ------------------------------------------------------------------------

    @_dated
    def set_player_source(self, player_id: int, template: int | None) -> None:
        """template None = made from scratch (blank, see fields.PLAYER_DEFAULTS)."""
        con = self.connect()
        try:
            con.execute('INSERT OR REPLACE INTO player_sources VALUES (?, ?)', (player_id, template))
            con.commit()
        finally:
            con.close()

    def player_sources(self) -> dict[int, int | None]:
        """{created player: the game player its row starts from} of all of them at once."""
        con = self.connect()
        try:
            return {r[0]: r[1] for r in con.execute('SELECT player_id, template FROM player_sources')}
        finally:
            con.close()

    def player_source(self, player_id: int) -> int | None:
        """The game player whose row a created player starts from."""
        con = self.connect()
        try:
            r = con.execute('SELECT template FROM player_sources WHERE player_id = ?', (player_id,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    @_dated
    def set_player_files(self, player_id: int, files: dict[str, bytes] | None) -> None:
        """The face files of a player (kind -> bytes, see fifa14.PLAYER_FACE_FILES); None or {} = none."""
        rows = [(player_id, name, *self.files.put(FACES, data, '.rx3')) for name, data in (files or {}).items()]
        con = self.connect()
        try:
            old = [r[0] for r in con.execute('SELECT file FROM player_files WHERE player_id = ?', (player_id,))]
            con.execute('DELETE FROM player_files WHERE player_id = ?', (player_id,))
            con.executemany('INSERT INTO player_files (player_id, name, file, size, digest) VALUES (?, ?, ?, ?, ?)',
                            rows)
            con.commit()
            self.files.release(con, old)
        finally:
            con.close()

    def player_files(self, player_id: int) -> dict[str, bytes]:
        con = self.connect()
        try:
            rows = con.execute('SELECT name, file FROM player_files WHERE player_id = ?', (player_id,)).fetchall()
        finally:
            con.close()
        out = {name: self.file_bytes(rel) for name, rel in rows}
        return {k: v for k, v in out.items() if v is not None}

    # ---- stadiums the user creates -----------------------------------------------------------------------------

    @_dated
    def set_stadium_source(self, stadium_id: int, template: int | None) -> None:
        """The game stadium a created stadium starts from (its row; its scene and pictures until it has its own);
        None = from scratch (blank)."""
        con = self.connect()
        try:
            con.execute('INSERT INTO stadium_sources (stadium_id, template) VALUES (?, ?) '
                        'ON CONFLICT (stadium_id) DO UPDATE SET template = excluded.template', (stadium_id, template))
            con.commit()
        finally:
            con.close()

    def set_stadium_folder_source(self, stadium_id: int, folder_stadium: int | None) -> None:
        """The game stadium the files of the stadium's folder were made for."""
        con = self.connect()
        try:
            con.execute('INSERT INTO stadium_sources (stadium_id, folder_stadium) VALUES (?, ?) ON CONFLICT (stadium_id) '
                        'DO UPDATE SET folder_stadium = excluded.folder_stadium', (stadium_id, folder_stadium))
            con.commit()
        finally:
            con.close()

    def stadium_folder_source(self, stadium_id: int) -> int | None:
        con = self.connect()
        try:
            r = con.execute('SELECT folder_stadium FROM stadium_sources WHERE stadium_id = ?', (stadium_id,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def stadium_source(self, stadium_id: int) -> int | None:
        con = self.connect()
        try:
            r = con.execute('SELECT template FROM stadium_sources WHERE stadium_id = ?', (stadium_id,)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    @_dated
    def set_stadium_scene(self, stadium_id: int, files: dict[str, bytes] | None) -> None:
        """Replaces the stadium's scene files ({name with STADIUM_ID_MARK: bytes}); None or {} = none (the
        template's)."""
        rows = [(stadium_id, name, *self.files.put(STADIUMS, data, os.path.splitext(name)[1]))
                for name, data in (files or {}).items()]
        con = self.connect()
        try:
            old = [r[0] for r in con.execute('SELECT file FROM stadium_scene WHERE stadium_id = ?', (stadium_id,))]
            con.execute('DELETE FROM stadium_scene WHERE stadium_id = ?', (stadium_id,))
            con.executemany('INSERT INTO stadium_scene (stadium_id, name, file, size, digest) VALUES (?, ?, ?, ?, ?)',
                            rows)
            con.commit()
            self.files.release(con, old)
        finally:
            con.close()
        self.save('stadium', stadium_id, self.names('stadium', stadium_id), self.fields('stadium', stadium_id))

    def with_stadium_scene(self) -> list[int]:
        """The stadiums (created or the game's) with scene files of their own."""
        con = self.connect()
        try:
            return [r[0] for r in con.execute('SELECT DISTINCT stadium_id FROM stadium_scene ORDER BY stadium_id')]
        finally:
            con.close()

    def stadium_scene_list(self, stadium_id: int) -> dict[str, int]:
        """{name: size} of the stadium's scene files (without reading them)."""
        con = self.connect()
        try:
            return {r[0]: r[1] for r in con.execute(
                'SELECT name, size FROM stadium_scene WHERE stadium_id = ? ORDER BY name', (stadium_id,))}
        finally:
            con.close()

    def stadium_scene_file(self, stadium_id: int, name: str) -> bytes | None:
        con = self.connect()
        try:
            r = con.execute('SELECT file FROM stadium_scene WHERE stadium_id = ? AND name = ?',
                            (stadium_id, name)).fetchone()
        finally:
            con.close()
        return self.file_bytes(r[0]) if r else None

    def stadium_scene_digest(self, stadium_id: int) -> str:
        """One text that changes when any scene file of the stadium changes."""
        con = self.connect()
        try:
            return ';'.join(f'{r[0]}={r[1]}' for r in con.execute(
                'SELECT name, digest FROM stadium_scene WHERE stadium_id = ? ORDER BY name', (stadium_id,)))
        finally:
            con.close()

    # ---- boots, gloves and balls ------------------------------------------------------------------------------

    @_dated
    def set_equipment_files(self, kind: str, oid: int, files: dict[str, bytes | None]) -> None:
        """Sets the item's files by name ('mesh', 'texture'); None removes one, names not given are kept."""
        stored = {name: self.files.put(EQUIPMENT_FOLDERS[kind], data, '.rx3')
                  for name, data in files.items() if data is not None}
        con = self.connect()
        try:
            old = []
            for name in files:
                r = con.execute('SELECT file FROM equipment_files WHERE kind = ? AND id = ? AND name = ?',
                                (kind, oid, name)).fetchone()
                if r:
                    old.append(r[0])
                con.execute('DELETE FROM equipment_files WHERE kind = ? AND id = ? AND name = ?', (kind, oid, name))
                if name in stored:
                    con.execute('INSERT INTO equipment_files (kind, id, name, file, size, digest) '
                                'VALUES (?, ?, ?, ?, ?, ?)', (kind, oid, name, *stored[name]))
            con.commit()
            self.files.release(con, old)
        finally:
            con.close()
        self.save(kind, oid, fields=self.fields(kind, oid))

    def equipment_files(self, kind: str, oid: int) -> dict[str, bytes]:
        con = self.connect()
        try:
            rows = con.execute('SELECT name, file FROM equipment_files WHERE kind = ? AND id = ?',
                               (kind, oid)).fetchall()
        finally:
            con.close()
        out = {name: self.file_bytes(rel) for name, rel in rows}
        return {k: v for k, v in out.items() if v is not None}

    def with_equipment_files(self, kind: str) -> list[int]:
        con = self.connect()
        try:
            return [r[0] for r in con.execute(
                'SELECT DISTINCT id FROM equipment_files WHERE kind = ? ORDER BY id', (kind,))]
        finally:
            con.close()

    def edited(self, kind: str) -> list[int]:
        """The game's entities of this kind the project changed (not the created ones)."""
        con = self.connect()
        try:
            return [r[0] for r in con.execute(
                'SELECT id FROM edited WHERE kind = ? AND id NOT IN (SELECT id FROM created WHERE kind = ?) '
                'ORDER BY id', (kind, kind))]
        finally:
            con.close()

    # ---- teams (names only; kept for the callers of schema 1) --------------------------------------------------

    def team_names(self, team_id: int) -> Names:
        return self.names('team', team_id)

    def save_team(self, team_id: int, names: Names, fields: dict | None = None) -> None:
        self.save('team', team_id, names, fields)

    def reset_team(self, team_id: int) -> None:
        self.reset('team', team_id)

    def all_team_names(self) -> dict[int, Names]:
        return self.all_names('team')


class VisibleProject:
    """A read view of a project without the entities left out of the patch (`hidden`: {kind: ids of hidden created
    entities})."""

    def __init__(self, project: Project, hidden: dict[str, set[int]]):
        self._project = project
        self._hidden = hidden

    def __getattr__(self, name):
        return getattr(self._project, name)

    def _out(self, kind: str, oid: int) -> bool:
        return oid in self._hidden.get(kind, ())

    def names(self, kind: str, oid: int) -> Names:
        return {} if self._out(kind, oid) else self._project.names(kind, oid)

    def fields(self, kind: str, oid: int) -> dict:
        return {} if self._out(kind, oid) else self._project.fields(kind, oid)

    def picture(self, kind: str, oid: int, slot: str):
        return None if self._out(kind, oid) else self._project.picture(kind, oid, slot)

    def with_picture(self, kind: str, slot: str) -> list[int]:
        return [i for i in self._project.with_picture(kind, slot) if not self._out(kind, i)]

    def all_names(self, kind: str) -> dict[int, Names]:
        return {i: v for i, v in self._project.all_names(kind).items() if not self._out(kind, i)}

    def all_fields(self, kind: str) -> dict[int, dict]:
        return {i: v for i, v in self._project.all_fields(kind).items() if not self._out(kind, i)}

    def created(self, kind: str) -> list[int]:
        return [i for i in self._project.created(kind) if not self._out(kind, i)]

    def is_created(self, kind: str, oid: int) -> bool:
        return not self._out(kind, oid) and self._project.is_created(kind, oid)

    def members(self, league_id: int) -> list[int] | None:
        return None if self._out('league', league_id) else self._project.members(league_id)

    def hidden_in_game(self, kind: str) -> set[int]:
        return self._project.hidden_in_game(kind)

    def all_members(self) -> dict[int, list[int]]:
        return {i: v for i, v in self._project.all_members().items() if not self._out('league', i)}

    def all_rosters(self) -> dict[int, list[dict]]:
        """Squads without the created players left out of the patch."""
        return {t: [r for r in rows if not self._out('player', r['player'])]
                for t, rows in self._project.all_rosters().items()}

    def player_files(self, player_id: int) -> dict[str, bytes]:
        return {} if self._out('player', player_id) else self._project.player_files(player_id)

    def all_adboard_links(self, kind: str) -> dict[int, int]:
        """Without the boards left out of the patch and the teams/leagues left out of it."""
        return {oid: board for oid, board in self._project.all_adboard_links(kind).items()
                if not self._out(kind, oid) and not self._out('adboard', board)}

    def all_team_names(self) -> dict[int, Names]:
        return self.all_names('team')

    def team_names(self, team_id: int) -> Names:
        return self.names('team', team_id)

    def visible(self) -> 'VisibleProject':
        return self
