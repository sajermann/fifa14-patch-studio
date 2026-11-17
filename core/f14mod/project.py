"""The user's work: what was changed over the clean game, in a SQLite file, one entity at a time.

Every save writes one entity whole (its form, as the screen sends it); nothing is kept as a global draft. The file
holds only differences from the originals: deleting an entity's rows gives the original back.

Team names: one row per (team, name key, language); language '*' is the value for every language that has no value
of its own.
"""
import sqlite3
import time

SCHEMA_VERSION = 1
DEFAULT_LANG = '*'

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS edited (kind TEXT, id INTEGER, updated_at INTEGER, PRIMARY KEY (kind, id));
CREATE TABLE IF NOT EXISTS team_names (team_id INTEGER, key TEXT, lang TEXT, text TEXT,
                                       PRIMARY KEY (team_id, key, lang));
"""


class ProjectError(ValueError):
    pass


class Project:
    def __init__(self, path: str):
        self.path = path
        con = self.connect()
        try:
            con.executescript(SCHEMA)
            found = con.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
            if found and int(found[0]) > SCHEMA_VERSION:
                raise ProjectError('project made by a newer version of the app')
            con.execute("INSERT OR REPLACE INTO meta VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
            con.commit()
        finally:
            con.close()

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    # ---- teams ------------------------------------------------------------------------------------------------

    def team_names(self, team_id: int) -> dict[str, dict[str, str]]:
        """{name key: {language or '*': text}}."""
        con = self.connect()
        try:
            out: dict[str, dict[str, str]] = {}
            for r in con.execute('SELECT key, lang, text FROM team_names WHERE team_id = ?', (team_id,)):
                out.setdefault(r['key'], {})[r['lang']] = r['text']
            return out
        finally:
            con.close()

    def save_team(self, team_id: int, names: dict[str, dict[str, str]]) -> None:
        """Replaces everything saved for the team; empty texts are dropped (= original)."""
        rows = [(team_id, key, lang, text.strip()) for key, by_lang in names.items()
                for lang, text in by_lang.items() if text and text.strip()]
        con = self.connect()
        try:
            con.execute('DELETE FROM team_names WHERE team_id = ?', (team_id,))
            con.executemany('INSERT INTO team_names VALUES (?,?,?,?)', rows)
            if rows:
                con.execute("INSERT OR REPLACE INTO edited VALUES ('team', ?, ?)", (team_id, int(time.time())))
            else:
                con.execute("DELETE FROM edited WHERE kind = 'team' AND id = ?", (team_id,))
            con.commit()
        finally:
            con.close()

    def reset_team(self, team_id: int) -> None:
        self.save_team(team_id, {})

    def all_team_names(self) -> dict[int, dict[str, dict[str, str]]]:
        con = self.connect()
        try:
            out: dict[int, dict[str, dict[str, str]]] = {}
            for r in con.execute('SELECT team_id, key, lang, text FROM team_names'):
                out.setdefault(r['team_id'], {}).setdefault(r['key'], {})[r['lang']] = r['text']
            return out
        finally:
            con.close()

    def counts(self) -> dict[str, int]:
        con = self.connect()
        try:
            return {r['kind']: r['n'] for r in con.execute('SELECT kind, COUNT(*) AS n FROM edited GROUP BY kind')}
        finally:
            con.close()
