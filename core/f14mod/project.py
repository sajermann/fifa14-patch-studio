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
"""
import json
import sqlite3
import time

SCHEMA_VERSION = 4
DEFAULT_LANG = '*'
KINDS = ('team', 'league', 'player', 'country')
NAME_TABLES = {'team': ('team_names', 'team_id'), 'league': ('league_names', 'league_id'),
               'country': ('country_names', 'country_id')}

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
CREATE TABLE IF NOT EXISTS league_members (league_id INTEGER, team_id INTEGER, ord INTEGER,
                                           PRIMARY KEY (league_id, team_id));
CREATE TABLE IF NOT EXISTS pictures (kind TEXT, id INTEGER, slot TEXT, data BLOB, updated_at INTEGER,
                                     PRIMARY KEY (kind, id, slot));
CREATE TABLE IF NOT EXISTS hidden (kind TEXT, id INTEGER, PRIMARY KEY (kind, id));
"""

Names = dict[str, dict[str, str]]  # {name key: {language or '*': text}}


class ProjectError(ValueError):
    pass


class Project:
    def __init__(self, path: str):
        self.path = path
        con = self.connect()
        try:
            found = con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
            if found:
                row = con.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
                if row and int(row[0]) > SCHEMA_VERSION:
                    raise ProjectError('project made by a newer version of the app')
            con.executescript(SCHEMA)
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
            if name_rows or field_rows:
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', (kind, oid, int(time.time())))
            else:
                con.execute('DELETE FROM edited WHERE kind = ? AND id = ?', (kind, oid))
            con.commit()
        finally:
            con.close()

    def reset(self, kind: str, oid: int) -> None:
        self.save(kind, oid)
        con = self.connect()
        try:
            con.execute('DELETE FROM pictures WHERE kind = ? AND id = ?', (kind, oid))
            con.commit()
        finally:
            con.close()

    # ---- pictures -------------------------------------------------------------------------------------------

    def set_picture(self, kind: str, oid: int, slot: str, data: bytes | None) -> None:
        """Keeps (or, with None, removes) a picture of the entity; a picture marks the entity as edited."""
        con = self.connect()
        try:
            if data is None:
                con.execute('DELETE FROM pictures WHERE kind = ? AND id = ? AND slot = ?', (kind, oid, slot))
            else:
                con.execute('INSERT OR REPLACE INTO pictures VALUES (?, ?, ?, ?, ?)',
                            (kind, oid, slot, data, int(time.time())))
                con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', (kind, oid, int(time.time())))
            if data is None and not con.execute(
                    'SELECT 1 FROM fields WHERE kind = ? AND id = ? UNION SELECT 1 FROM pictures '
                    'WHERE kind = ? AND id = ?', (kind, oid, kind, oid)).fetchone():
                table = NAME_TABLES.get(kind)
                if not table or not con.execute(f'SELECT 1 FROM {table[0]} WHERE {table[1]} = ?', (oid,)).fetchone():
                    con.execute('DELETE FROM edited WHERE kind = ? AND id = ?', (kind, oid))
            con.commit()
        finally:
            con.close()

    def picture(self, kind: str, oid: int, slot: str) -> tuple[bytes, int] | None:
        """(PNG bytes, saved at) or None."""
        con = self.connect()
        try:
            r = con.execute('SELECT data, updated_at FROM pictures WHERE kind = ? AND id = ? AND slot = ?',
                            (kind, oid, slot)).fetchone()
            return (bytes(r[0]), r[1]) if r else None
        finally:
            con.close()

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

    # ---- created entities -------------------------------------------------------------------------------------

    def create(self, kind: str, oid: int, names: Names | None = None, fields: dict | None = None) -> None:
        if kind not in KINDS:
            raise ProjectError(f'unknown kind {kind}')
        con = self.connect()
        try:
            con.execute('INSERT INTO created VALUES (?, ?, ?)', (kind, oid, int(time.time())))
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
        """Removes a created entity and everything saved for it."""
        self.reset(kind, oid)
        con = self.connect()
        try:
            con.execute('DELETE FROM created WHERE kind = ? AND id = ?', (kind, oid))
            con.execute('DELETE FROM hidden WHERE kind = ? AND id = ?', (kind, oid))
            if kind == 'league':
                con.execute('DELETE FROM league_members WHERE league_id = ?', (oid,))
                con.execute('DELETE FROM league_members_set WHERE league_id = ?', (oid,))
            if kind == 'team':
                con.execute('DELETE FROM league_members WHERE team_id = ?', (oid,))
            con.commit()
        finally:
            con.close()

    # ---- left out of the patch ---------------------------------------------------------------------------------

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
        """The project without the hidden created entities (what the builder reads)."""
        out = {kind: self.hidden(kind) & set(self.created(kind)) for kind in KINDS}
        return VisibleProject(self, out) if any(self.hidden(kind) for kind in KINDS) else self

    # ---- teams of a league ------------------------------------------------------------------------------------

    def set_members(self, league_id: int, team_ids: list[int] | None) -> None:
        """The whole team list of a league, in order; None = the game's teams again."""
        con = self.connect()
        try:
            con.execute('DELETE FROM league_members WHERE league_id = ?', (league_id,))
            con.execute('DELETE FROM league_members_set WHERE league_id = ?', (league_id,))
            if team_ids is not None:
                con.execute('INSERT INTO league_members_set VALUES (?)', (league_id,))
                con.executemany('INSERT OR IGNORE INTO league_members VALUES (?, ?, ?)',
                                [(league_id, tid, i) for i, tid in enumerate(team_ids)])
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

    def all_members(self) -> dict[int, list[int]]:
        con = self.connect()
        try:
            out: dict[int, list[int]] = {r[0]: [] for r in con.execute('SELECT league_id FROM league_members_set')}
            for r in con.execute('SELECT league_id, team_id FROM league_members ORDER BY league_id, ord'):
                out.setdefault(r[0], []).append(r[1])
            return out
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

    def all_team_names(self) -> dict[int, Names]:
        return self.all_names('team')

    def team_names(self, team_id: int) -> Names:
        return self.names('team', team_id)

    def visible(self) -> 'VisibleProject':
        return self
