"""The app's own share zip: any mix of countries, leagues, teams, players, stadiums, boards, boots, gloves and balls,
each with everything the project keeps of it, so a zip made by the app comes back exactly as it went.

Layout (flat names under `files/`):
    manifest.json      {"format": FORMAT, "format_version": VERSION, "tool", "created_at", "items": [Record]}
    files/<kind>-<id>-<n>.bin   the binary values (pictures, face files, pack files, stadium scenes; in the project
                                they are files of its folders, f14mod.filestore)

A Record is one entity: `kind`, `id` (in the project it came from), `created` (false = a change to one of the game's own
entities: every clean game has it under the same id), `names` ({key: {language: text}}), `fields`, `hidden`, `dates`,
`pictures` ({slot: file}), `tables` (the entity's rows of its own tables, see project.OWN_TABLES and EQUIPMENT_FILES,
binary columns as file names) and `links`: where the entity is listed on its parent's side when the parent is not in
the zip (`leagues` of a team, `teams` of a player: [{team, jersey, slot}]).

Importing: plan() gives every chosen record its id in the project (a created one keeps its id when it is free and in
the range the app gives created entities; otherwise it gets a new one, the reason shown), and apply() writes them in
one transaction, every reference rewritten (project.OWN_TABLES columns, fields of kinds nation/team/roster, the boot,
glove and ball codes, a face copied from a player, a kit copied from a team). A reference to an entity of the zip that
was left out is dropped, except a change to a game entity (that entity is in every game); a reference to something
that is not in the zip is kept as it is (it is the game's, unchanged). A package of the extractor
(f14mod.package) arrives as the same records with `origin` 'package': there a reference outside the package is
dropped (its ids are another database's).

Where a record comes from (`origin` {source, id}): 'pkg:<patch name>' (package_source) and its id in the package, or
'prj:<uid>' of the project that made it and its id there. A record that came into that project by an import keeps the
origin it came in with (the manifest's `origin`), so the same thing stays the same thing however it travels. The
project keeps the origin of what it imports (Project.origin); importing from the same origin again offers to update
the entity that came in before ('updates', see plan) instead of adding a copy.
"""
import contextlib
import datetime
import json
import os
import sqlite3
import threading
import unicodedata
import zipfile
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from . import facefill, fields as fieldspecs
from .filestore import EQUIPMENT as EQUIPMENT_FOLDERS, FACES, PICTURES, STADIUMS, FileStore
from .project import EQUIPMENT_KINDS, KINDS, NAME_TABLES, OWN_TABLES, Project

FORMAT = 'fifa14-patch-studio'
VERSION = 1
MANIFEST = 'manifest.json'
FILES = 'files/'
MAX_MANIFEST = 256 * 1024 * 1024
MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 256 * 1024 ** 3  # uncompressed bytes of an import (a whole game's package with stadiums passes 40 GB)

# binary columns of the entity tables: (table, column) -> the column that names the file
BLOB_COLUMNS = {'pictures': 'data', 'player_files': 'data', 'equipment_files': 'data', 'stadium_scene': 'data'}
EQUIPMENT_FILES = ('equipment_files', 'id')

# references held in the entity tables: table -> {column: kind}
TABLE_REFS = {
    'team_sources': {'template': 'team'},
    'team_rosters': {'player_id': 'player'},
    'team_stadiums': {'stadium_id': 'stadium'},
    'team_adboards': {'adboard_id': 'adboard'},
    'league_members': {'team_id': 'team'},
    'league_adboards': {'adboard_id': 'adboard'},
    'player_sources': {'template': 'player'},
    'stadium_sources': {'template': 'stadium', 'folder_stadium': 'stadium'},
}
FIELD_KIND_REFS = {'nation': 'country', 'nations': 'country', 'team': 'team', 'roster': 'player'}
CODE_REFS = {'shoetypecode': 'boot', 'gkglovetypecode': 'glove', 'balltype': 'ball'}
# what an entity takes along (the tree): kind -> [(child kind, how it is found)]
# a package's references to these, when the package leaves them out, stay on the game's of the same id (the
# game's stadium and equipment ids are the same in every patch of the game)
GAME_SHARED = ('stadium', 'ball', 'boot', 'glove')
TREE_ORDER = ('country', 'league', 'team', 'stadium', 'adboard', 'ball', 'player', 'boot', 'glove')
PACKAGE_SOURCE, PROJECT_SOURCE = 'pkg:', 'prj:'
MAX_SOURCE = 512


def package_source(patch_name) -> str | None:
    """The origin of a package's items: its patch name, the same however it was typed (case, accents, spaces);
    None without one (nothing tells two packages apart: they come in as new)."""
    if not isinstance(patch_name, str):
        return None
    text = unicodedata.normalize('NFKD', patch_name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = ' '.join(text.split()).casefold()
    return f'{PACKAGE_SOURCE}{text}'[:MAX_SOURCE] if text else None


def project_source(uid: str) -> str:
    return f'{PROJECT_SOURCE}{uid}'


def _origin(value) -> dict | None:
    """A record's `origin` as the manifest holds it, or None."""
    if not isinstance(value, dict):
        return None
    source, oid = value.get('source'), value.get('id')
    if not isinstance(source, str) or not source or len(source) > MAX_SOURCE or not _int(oid) or oid < 0:
        return None
    return {'source': source, 'id': oid}


class ShareError(ValueError):
    def __init__(self, code: str, detail: str = ''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code, self.detail = code, detail


@dataclass
class Bundle:
    """What a zip holds: records in order and where their binary values are."""
    records: list[dict]
    origin: str = 'own'  # own | package
    meta: dict = field(default_factory=dict)
    # file name -> bytes (records read from a package) or the path of the file on disk (a project's own, Writer)
    files: dict[str, bytes | str] = field(default_factory=dict)
    zip_path: str | None = None
    warnings: list[str] = field(default_factory=list)

    def key(self, r: dict) -> str:
        return f"{r['kind']}:{r['id']}"

    def by_key(self) -> dict[str, dict]:
        return {self.key(r): r for r in self.records}

    def __post_init__(self):
        self._zip: zipfile.ZipFile | None = None  # kept open by opened(): opening reads the whole index of the zip

    @contextlib.contextmanager
    def opened(self):
        """Keeps the zip open meanwhile (read_file of a big package is many times faster: opening a zip reads the
        entry of every file in it, tens of thousands in a package). Reading from several threads is safe."""
        if self._zip is not None or not self.zip_path:
            yield self
            return
        try:
            self._zip = zipfile.ZipFile(self.zip_path)
        except (zipfile.BadZipFile, OSError) as e:
            raise ShareError('not_a_zip', str(e)) from None
        try:
            yield self
        finally:
            self._zip.close()
            self._zip = None

    def read_file(self, name: str) -> bytes:
        if name in self.files:
            value = self.files[name]
            if isinstance(value, str):
                try:
                    with open(value, 'rb') as f:
                        return f.read()
                except OSError:
                    raise ShareError('missing_file', name) from None
            return value
        if not self.zip_path:
            raise ShareError('missing_file', name)
        if self._zip is not None:
            return self._read(self._zip, name)
        with zipfile.ZipFile(self.zip_path) as z:
            return self._read(z, name)

    def file_sizes(self) -> dict[str, int]:
        """Unpacked size of every file of the open zip (empty when none is open)."""
        if self._zip is None:
            return {}
        return {i.filename: i.file_size for i in self._zip.infolist()}

    @staticmethod
    def _read(z: zipfile.ZipFile, name: str) -> bytes:
        try:
            return z.read(name)
        except KeyError:
            raise ShareError('missing_file', name) from None


class Destination(Protocol):
    """The project and game an import goes into (the backend's; tests use a fake)."""

    def in_game(self, kind: str, oid: int) -> bool: ...  # one of the game's own entities
    def used(self, kind: str, oid: int) -> bool: ...  # the game's or created by the project
    def in_range(self, kind: str, oid: int) -> bool: ...  # an id the app gives to the entities it creates
    def allocate(self, kind: str, reserved: set[int]) -> int | None: ...
    def league_members(self, league_id: int) -> list[int]: ...  # the league's teams now
    def team_roster(self, team_id: int) -> list[dict]: ...  # the team's squad now: [{player, jersey, slot}]
    # optional: the created entity that came in from (source, id) before (None = none), and whether the user changed
    # it since (without them nothing is ever an update)
    # def match(self, kind: str, source: str, source_id: int) -> int | None: ...
    # def changed_since_import(self, kind: str, oid: int) -> bool: ...


# ---------------------------------------------------------------- export

def _rows(con, table: str, column: str, oid: int, kind: str | None = None) -> list[dict]:
    extra, args = (' AND kind = ?', (oid, kind)) if kind else ('', (oid,))
    return [dict(r) for r in con.execute(f'SELECT * FROM {table} WHERE {column} = ?{extra}', args)]


class Writer:
    """Collects records and their files, then writes the zip."""

    def __init__(self):
        self.records: list[dict] = []
        self.files: dict[str, str] = {}  # file name in the zip -> the project's file on disk (read when written)
        self._seen: set[str] = set()
        self.project_uid: str | None = None

    def _file(self, kind: str, oid: int, path: str) -> str:
        name = f'{FILES}{kind}-{oid}-{len(self.files) + 1}.bin'
        self.files[name] = path
        return name

    def add(self, project: Project, kind: str, oid: int, links: dict | None = None) -> dict | None:
        """Adds one entity of the project (everything it keeps of it); None when it is already in."""
        key = f'{kind}:{oid}'
        if key in self._seen:
            return None
        self._seen.add(key)
        created_at, updated_at = project.dates(kind, oid)
        rec = {'kind': kind, 'id': oid, 'created': project.is_created(kind, oid),
               'names': project.names(kind, oid), 'fields': project.fields(kind, oid),
               'hidden': oid in project.hidden(kind), 'dates': {'created_at': created_at, 'updated_at': updated_at},
               'pictures': {}, 'tables': {}, 'links': links or {}}
        # where it comes from: where it came in from, else this project
        self.project_uid = self.project_uid or project.uid()
        came = project.origin(kind, oid)
        rec['origin'] = ({'source': came[0], 'id': came[1]} if came
                         else {'source': project_source(self.project_uid), 'id': oid})
        con = project.connect()
        try:
            for r in _rows(con, 'pictures', 'id', oid, kind):
                rec['pictures'][r['slot']] = self._file(kind, oid, project.file_path(r['file']))
            tables = list(OWN_TABLES.get(kind, ()))
            if kind in EQUIPMENT_KINDS:
                tables.append(EQUIPMENT_FILES)
            for table, column in tables:
                rows = _rows(con, table, column, oid, kind if table == 'equipment_files' else None)
                for r in rows:
                    r.pop(column, None)
                    if table == 'equipment_files':
                        r.pop('kind', None)
                    if table in BLOB_COLUMNS:  # the file goes into the zip; its path, size and digest stay here
                        rel = r.pop('file', None)
                        r.pop('size', None)
                        r.pop('digest', None)
                        if rel:
                            r[BLOB_COLUMNS[table]] = self._file(kind, oid, project.file_path(rel))
                if rows:
                    rec['tables'][table] = rows
        finally:
            con.close()
        self.records.append(rec)
        return rec

    def manifest(self, tool: dict | None = None) -> dict:
        out = {'format': FORMAT, 'format_version': VERSION, 'tool': tool or {},
               'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
               'items': self.records}
        if self.project_uid:
            out['project'] = {'uid': self.project_uid}
        return out

    def write(self, path: str, tool: dict | None = None, keep: set[str] | None = None, is_created=None) -> None:
        """The zip; `keep` = the keys (kind:id) to write (None = all). `is_created(kind, id)`: a reference to an
        entity the project created that does not go is dropped (in another project that id is someone else)."""
        records = [r for r in self.records if keep is None or f"{r['kind']}:{r['id']}" in keep]
        if is_created is not None:
            kept = {f"{r['kind']}:{r['id']}" for r in records}

            def fix(kind, oid):
                if not _int(oid) or f'{kind}:{oid}' in kept or not is_created(kind, oid):
                    return oid
                return None
            records = [json.loads(json.dumps(r)) for r in records]
            for r in records:
                _walk(r, fix)
        used = {name for r in records for name in _record_files(r)}
        manifest = {**self.manifest(tool), 'items': records}
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
            for name in sorted(used):
                z.write(self.files[name], name)  # streamed from disk: a stadium's files are hundreds of MB


def _record_files(rec: dict) -> list[str]:
    out = list(rec.get('pictures', {}).values())
    for table, rows in rec.get('tables', {}).items():
        col = BLOB_COLUMNS.get(table)
        if col:
            out += [r[col] for r in rows if isinstance(r.get(col), str)]
    return out


# ---------------------------------------------------------------- references

def refs(rec: dict) -> list[tuple[str, int]]:
    """Every (kind, id) the record points to."""
    out = []
    _walk(rec, lambda kind, oid: out.append((kind, oid)) or oid)
    return [(k, int(i)) for k, i in out if isinstance(i, int) and not isinstance(i, bool)]


def _walk(rec: dict, fix) -> None:
    """Calls fix(kind, id) on every reference of the record and stores what it returns (None = dropped)."""
    kind = rec['kind']
    specs = fieldspecs.BY_NAME.get(kind, {})
    values = rec.get('fields') or {}
    for name in list(values):
        value, spec = values[name], specs.get(name)
        target = CODE_REFS.get(name) if kind in ('player', 'team') else None
        if target is None and spec is not None:
            target = FIELD_KIND_REFS.get(spec.kind)
        if target is None or value is None:
            if name == 'face' and isinstance(value, dict) and value.get('source') == 'player':
                new = fix('player', value.get('player'))
                if new is None:
                    del values[name]
                else:
                    values[name] = {**value, 'player': new}
            continue
        if name in CODE_REFS and not value:  # code 0 = none
            continue
        if isinstance(value, list):
            kept = [n for n in (fix(target, v) for v in value) if n is not None]
            if kept:
                values[name] = kept
            else:
                del values[name]
        else:
            new = fix(target, value)
            if new is None:
                del values[name]
            else:
                values[name] = new
    for table, rows in (rec.get('tables') or {}).items():
        columns = TABLE_REFS.get(table, {})
        kept = []
        for r in rows:
            drop = False
            for column, target in columns.items():
                if r.get(column) is None:
                    continue
                new = fix(target, r[column])
                if new is None:
                    if table in ('team_rosters', 'league_members'):
                        drop = True  # the row is the link itself
                    elif table in ('team_stadiums', 'team_adboards', 'league_adboards'):
                        drop = True
                    else:
                        r[column] = None
                else:
                    r[column] = new
            if table == 'team_kits' and isinstance(r.get('config'), str):
                config = json.loads(r['config'])
                if config.get('source') == 'game' and config.get('team') is not None:
                    new = fix('team', config['team'])
                    if new is None:
                        drop = True
                    else:
                        r['config'] = json.dumps({**config, 'team': new}, ensure_ascii=False)
            if not drop:
                kept.append(r)
        rec['tables'][table] = kept
    links = rec.get('links') or {}
    if 'leagues' in links:
        links['leagues'] = [n for n in (fix('league', v) for v in links['leagues']) if n is not None]
    if 'teams' in links:
        links['teams'] = [{**t, 'team': n} for t in links['teams'] if (n := fix('team', t['team'])) is not None]


def children(bundle: Bundle) -> dict[str, list[str]]:
    """The tree: key -> the keys of the zip it takes along (a league its teams and board, a team its stadium, ball,
    board and players, a player his boot and glove, a country its leagues)."""
    keys = bundle.by_key()
    out: dict[str, list[str]] = {k: [] for k in keys}

    def add(parent, kind, oid):
        k = f'{kind}:{oid}'
        if k in keys and k != parent and k not in out[parent]:
            out[parent].append(k)

    for k, r in keys.items():
        f, t = r.get('fields') or {}, r.get('tables') or {}
        if r['kind'] == 'league':
            for row in t.get('league_members', []):
                add(k, 'team', row['team_id'])
            for row in t.get('league_adboards', []):
                add(k, 'adboard', row['adboard_id'])
        elif r['kind'] == 'team':
            for row in t.get('team_stadiums', []):
                add(k, 'stadium', row['stadium_id'])
            if f.get('balltype'):
                add(k, 'ball', f['balltype'])
            for row in t.get('team_adboards', []):
                add(k, 'adboard', row['adboard_id'])
            for row in t.get('team_rosters', []):
                add(k, 'player', row['player_id'])
        elif r['kind'] == 'player':
            if f.get('shoetypecode'):
                add(k, 'boot', f['shoetypecode'])
            if f.get('gkglovetypecode'):
                add(k, 'glove', f['gkglovetypecode'])
        elif r['kind'] == 'country':
            # its own leagues and the ones added to it (the league's extra_countries)
            for other in bundle.records:
                of = other.get('fields') or {}
                if other['kind'] == 'league' and (of.get('countryid') == r['id']
                                                  or r['id'] in (of.get('extra_countries') or [])):
                    add(k, 'league', other['id'])
    # a team listed by a league of the zip through its links only (a package)
    for k, r in keys.items():
        if r['kind'] == 'team':
            for lid in (r.get('links') or {}).get('leagues', []):
                if f'league:{lid}' in out:
                    add(f'league:{lid}', 'team', r['id'])
        if r['kind'] == 'player':
            for t in (r.get('links') or {}).get('teams', []):
                if f"team:{t['team']}" in out:
                    add(f"team:{t['team']}", 'player', r['id'])
    return out


def roots(bundle: Bundle, tree: dict[str, list[str]]) -> list[str]:
    inside = {c for cs in tree.values() for c in cs}
    order = {kind: i for i, kind in enumerate(TREE_ORDER)}
    keys = [bundle.key(r) for r in bundle.records if bundle.key(r) not in inside]
    return sorted(keys, key=lambda k: order.get(k.split(':')[0], 99))


# ---------------------------------------------------------------- reading

def is_own(z: zipfile.ZipFile) -> bool:
    return MANIFEST in z.namelist()


def read(path: str, formations: dict[int, list[int]] | None = None) -> Bundle:
    """A zip of the app, or a package of the extractor (converted; formations: see package.convert); raises
    ShareError."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ShareError('not_a_zip', str(e)) from None
    with z:
        if sum(i.file_size for i in z.infolist()) > MAX_TOTAL:
            raise ShareError('zip_too_big')
        from . import package
        if package.is_package(z):
            bundle = package.convert(z, formations)
            bundle.zip_path = path
            return bundle
        if not is_own(z):
            raise ShareError('unknown_zip')
        info = z.getinfo(MANIFEST)
        if info.file_size > MAX_MANIFEST:
            raise ShareError('invalid_manifest', 'too big')
        try:
            manifest = json.loads(z.read(MANIFEST))
        except (ValueError, UnicodeDecodeError) as e:
            raise ShareError('invalid_manifest', str(e)) from None
        names = set(z.namelist())
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
        raise ShareError('unknown_zip')
    version = manifest.get('format_version')
    if not isinstance(version, int) or version < 1:
        raise ShareError('invalid_manifest', 'format_version')
    if version > VERSION:
        raise ShareError('zip_too_new', str(version))
    records, warnings = [], []
    seen = set()
    made_by = manifest.get('project') if isinstance(manifest.get('project'), dict) else {}
    uid = made_by.get('uid') if isinstance(made_by.get('uid'), str) and 0 < len(made_by['uid']) <= 64 else None
    for item in manifest.get('items') or []:
        rec = _checked(item)
        if rec is None:
            warnings.append('item_out_of_format')
            continue
        key = f"{rec['kind']}:{rec['id']}"
        if key in seen:
            continue
        seen.add(key)
        missing = [n for n in _record_files(rec) if n not in names]
        if missing:
            warnings.append(f'missing_file:{key}')
            _drop_files(rec, set(missing))
        if rec['origin'] is None and uid:  # an item of the project that made the zip
            rec['origin'] = {'source': project_source(uid), 'id': rec['id']}
        records.append(rec)
    return Bundle(records, 'own', {k: manifest.get(k) for k in ('tool', 'created_at')} | {'project_uid': uid},
                  zip_path=path, warnings=warnings)


def _drop_files(rec: dict, missing: set[str]) -> None:
    rec['pictures'] = {s: n for s, n in rec.get('pictures', {}).items() if n not in missing}
    for table, rows in rec.get('tables', {}).items():
        col = BLOB_COLUMNS.get(table)
        if col:
            rec['tables'][table] = [r for r in rows if r.get(col) not in missing]


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _checked(item) -> dict | None:
    """A record of the manifest with the shape apply() needs, or None."""
    if not isinstance(item, dict) or item.get('kind') not in KINDS or not _int(item.get('id')) or item['id'] < 0:
        return None
    names = item.get('names') or {}
    if not isinstance(names, dict) or not all(
            isinstance(v, dict) and all(isinstance(t, str) for t in v.values()) for v in names.values()):
        return None
    tables = item.get('tables') or {}
    allowed = {t for t, _ in OWN_TABLES.get(item['kind'], ())} | (
        {'equipment_files'} if item['kind'] in EQUIPMENT_KINDS else set())
    if not isinstance(tables, dict) or not all(
            t in allowed and isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
            for t, rows in tables.items()):
        return None
    pictures = item.get('pictures') or {}
    if not isinstance(pictures, dict) or not all(isinstance(v, str) for v in pictures.values()):
        return None
    dates = item.get('dates') if isinstance(item.get('dates'), dict) else {}
    return {'kind': item['kind'], 'id': item['id'], 'created': bool(item.get('created')),
            'names': {k: dict(v) for k, v in names.items()} if item['kind'] in NAME_TABLES else {},
            'fields': dict(item.get('fields') or {}) if isinstance(item.get('fields'), dict) else {},
            'hidden': bool(item.get('hidden')),
            'dates': {k: dates.get(k) if _int(dates.get(k)) else None for k in ('created_at', 'updated_at')},
            'pictures': dict(pictures), 'tables': {t: [dict(r) for r in rows] for t, rows in tables.items()},
            'links': item.get('links') if isinstance(item.get('links'), dict) else {},
            'origin': _origin(item.get('origin'))}


# ---------------------------------------------------------------- the plan

def plan(bundle: Bundle, dest: Destination) -> dict[str, dict]:
    """For every record: {'id': the id it gets, 'reason': None | 'taken' | 'range' | 'replaces' | 'updates',
    'default': picked at first, 'error': a record that cannot come in, 'game_has': a country of a package the game
    already has}. 'updates': a created record whose origin came in before (Destination.match) takes the id of what came
    in then and replaces it; 'changed' = the user changed that entity since, 'alt' = {id, reason} it takes if it comes
    in as a new one instead (as_new), None when no id is left."""
    out: dict[str, dict] = {}
    reserved: dict[str, set[int]] = {k: set() for k in KINDS}
    matched: dict[str, int] = {}  # key -> the entity of the project it updates
    match = getattr(dest, 'match', None)
    if match is not None:
        for r in bundle.records:
            origin = r.get('origin')
            if not r['created'] or not origin:
                continue
            found = match(r['kind'], origin['source'], origin['id'])
            if found is not None and found not in reserved[r['kind']]:
                matched[bundle.key(r)] = found
                reserved[r['kind']].add(found)
    for r in bundle.records:  # first the ones that keep their id
        key, kind, oid = bundle.key(r), r['kind'], r['id']
        if key in matched:
            continue
        default = True
        if bundle.origin == 'package' and kind == 'country' and dest.in_game(kind, oid):
            default = False  # the game has it: left out, whoever uses it keeps the game's
        if not r['created']:
            if not dest.in_game(kind, oid):
                out[key] = {'id': None, 'reason': None, 'default': False, 'error': 'not_in_game'}
            else:
                out[key] = {'id': oid, 'reason': 'replaces' if dest.used(kind, oid) and _changed(dest, kind, oid)
                            else None, 'default': default}
            continue
        if not dest.used(kind, oid) and dest.in_range(kind, oid) and oid not in reserved[kind]:
            out[key] = {'id': oid, 'reason': None, 'default': default}
            reserved[kind].add(oid)
    # a country of a package the game already has: left out at first (whoever uses it keeps the game's), so it takes
    # a new id only after everything else, and having none left is not an error (it only cannot come in as a new one)
    def game_has(r):
        return (bundle.origin == 'package' and r['kind'] == 'country' and dest.in_game('country', r['id'])
                and bundle.key(r) not in matched)  # brought in as a new country before: that one is updated
    for r in sorted(bundle.records, key=game_has):  # then the new ids
        key, kind, oid = bundle.key(r), r['kind'], r['id']
        if key in out or key in matched:
            continue
        new = dest.allocate(kind, reserved[kind])
        if new is None:
            out[key] = ({'id': None, 'reason': None, 'default': False} if game_has(r)
                        else {'id': None, 'reason': None, 'default': False, 'error': 'limit'})
            continue
        reserved[kind].add(new)
        out[key] = {'id': new, 'reason': 'taken' if dest.used(kind, oid) else 'range', 'default': not game_has(r)}
    # last, the ids the updates would take as new items (reserved too: choosing one changes no other id)
    since = getattr(dest, 'changed_since_import', None)
    for r in bundle.records:
        key, kind, oid = bundle.key(r), r['kind'], r['id']
        if key not in matched:
            continue
        if not dest.used(kind, oid) and dest.in_range(kind, oid) and oid not in reserved[kind]:
            alt = {'id': oid, 'reason': None}
        else:
            new = dest.allocate(kind, reserved[kind])
            alt = None if new is None else {'id': new, 'reason': 'taken' if dest.used(kind, oid) else 'range'}
        if alt is not None:
            reserved[kind].add(alt['id'])
        out[key] = {'id': matched[key], 'reason': 'updates', 'default': True,
                    'changed': bool(since(kind, matched[key])) if since else False, 'alt': alt}
    for r in bundle.records:
        if game_has(r):
            out[bundle.key(r)]['game_has'] = True
    return out


def as_new(ids: dict[str, dict], keys) -> dict[str, dict]:
    """The plan with these updates coming in as new items instead (their `alt` id); the rest as planned."""
    out = dict(ids)
    for key in keys:
        plan = ids.get(key) or {}
        if plan.get('reason') == 'updates' and plan.get('alt'):
            out[key] = {'id': plan['alt']['id'], 'reason': plan['alt']['reason'], 'default': True, 'as_new': True}
    return out


def _changed(dest, kind, oid) -> bool:
    check = getattr(dest, 'changed', None)
    return bool(check(kind, oid)) if check else False


def resolver(bundle: Bundle, ids: dict[str, dict], chosen: set[str], dest: Destination | None = None):
    """fix(kind, id) for _walk: the id a reference takes in the project (None = dropped)."""
    keys = bundle.by_key()

    def in_game(kind, oid):
        return dest is not None and dest.in_game(kind, oid)

    def fix(kind, oid):
        if not _int(oid):
            return oid
        key = f'{kind}:{oid}'
        rec = keys.get(key)
        if rec is None:  # not in the zip: the game's (a package's ids are another database's)
            if bundle.origin != 'package':
                return oid
            return oid if kind in GAME_SHARED and in_game(kind, oid) else None
        if key in chosen and ids.get(key, {}).get('id') is not None:
            return ids[key]['id']
        if not rec['created']:
            return oid if ids.get(key, {}).get('error') is None else None  # the game's entity, unchanged here
        if bundle.origin == 'package' and kind in ('country', *GAME_SHARED) and in_game(kind, oid):
            return oid  # left out: the game's under the same id
        return None
    return fix


# ---------------------------------------------------------------- apply

APPLY_STEPS = ('prepare', 'write', 'links', 'save')  # the steps apply() reports, in order


class ImportCancelled(ShareError):
    def __init__(self):
        super().__init__('import_cancelled')


def label(rec: dict) -> str | None:
    """The name an import shows while it writes the record (any language), or None."""
    names, fields = rec.get('names') or {}, rec.get('fields') or {}

    def text(key):
        by = names.get(key) or {}
        found = next((t.strip() for t in by.values() if isinstance(t, str) and t.strip()), None)
        value = fields.get(f'name.{key}') if found is None else found  # players and equipment keep them as fields
        return value.strip() if isinstance(value, str) and value.strip() else None
    if rec.get('kind') == 'player':
        return text('common') or ' '.join(t for t in (text('first'), text('last')) if t) or None
    named = fields.get('name')
    if isinstance(named, str) and named.strip():
        return named.strip()
    return next((t for t in (text(k) for k in ('full', 'name', 'short', *names)) if t), None)


def _prefetched(bundle: Bundle, records: list, workers: int, budget: int):
    """((id, record), {file: bytes}) in order, the files read (and unpacked) ahead by `workers` threads while the
    caller writes; about `budget` bytes waiting at most (a package may hold tens of GB)."""
    def load(rec):
        return {n: bundle.read_file(n) for n in dict.fromkeys(_record_files(rec))}
    if workers <= 1:
        for item in records:
            yield item, load(item[1])
        return
    sizes = bundle.file_sizes()
    pending: deque = deque()
    waiting = 0
    it = iter(records)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            while True:
                while len(pending) < workers * 4 and (not pending or waiting < budget):
                    item = next(it, None)
                    if item is None:
                        break
                    size = sum(sizes.get(n, 0) for n in _record_files(item[1]))
                    pending.append((item, size, pool.submit(load, item[1])))
                    waiting += size
                if not pending:
                    return
                item, size, future = pending.popleft()
                waiting -= size
                yield item, future.result()
        finally:
            for _, _, future in pending:
                future.cancel()


def _fill(rec: dict, wanted: bool, game: dict[str, set[int]] | None) -> None:
    """A face of a package that lacks its eyes, hair or hair seen from afar (rec['fill'], package.fill): completed
    as the source game
    shows it when the user wants. With the generic files the package brings: they become the player's own (the hair
    painted with his hair color, as facefill does); without them: the game's generic part of the same code (the
    face's `fill`), when the game has it. Not wanted: the face goes as the package has it."""
    fill = rec.pop('fill', None)
    if not wanted or not fill or rec.get('kind') != 'player':
        return
    face = rec.get('fields', {}).get('face')
    if not isinstance(face, dict) or face.get('source') != 'pack':
        return
    rows = rec.setdefault('tables', {}).setdefault('player_files', [])
    codes = {}
    for key in facefill.GROUPS:
        part = fill.get(key)
        if not part:
            continue
        files = part.get('files') or {}
        if files:
            for kind in facefill.GROUPS[key]:
                rows[:] = [r for r in rows if r.get('name') != kind]
            for kind, name in files.items():
                row = {'name': kind, 'data': name}
                if kind == 'hair_textures':
                    row['paint'] = facefill.hair_rgb(part.get('hair_color'))
                rows.append(row)
        elif part.get('code') in (game or {}).get(key, ()):
            codes[key] = part['code']
    if codes:
        face['fill'] = {**(face.get('fill') or {}), **codes}


def apply(project: Project, bundle: Bundle, ids: dict[str, dict], chosen: set[str], dest: Destination,
          progress=None, cancel: threading.Event | None = None, workers: int = 1,
          memory_budget: int = 512 * 2 ** 20, fill_missing: bool = False,
          generic: dict[str, set[int]] | None = None) -> dict:
    """Writes the chosen records into the project, in one transaction; {kind: [ids]} of what came in.
    progress(step, done, total, item): step of APPLY_STEPS, item = {'kind', 'name', 'id'} of the record being
    written. cancel: set it to stop (ImportCancelled; the transaction is rolled back, nothing changes). workers:
    threads that read the files of the next records ahead (unpacking the zip entries is the slow part).
    fill_missing: complete the faces of a package that lack their eyes or hair (_fill; generic = the codes of the
    game's generic eyes and hair, {'eyes': {...}, 'hair': {...}})."""
    def report(step, done=0, total=0, item=None):
        if progress:
            progress(step, done, total, item)

    def check():
        if cancel is not None and cancel.is_set():
            raise ImportCancelled()

    fix = resolver(bundle, ids, chosen, dest)
    picked = [r for r in bundle.records
              if bundle.key(r) in chosen and ids.get(bundle.key(r), {}).get('id') is not None]
    records = []
    for i, r in enumerate(picked):
        if i % 200 == 0:
            report('prepare', i, len(picked))
            check()
        rec = json.loads(json.dumps(r))  # a copy: the bundle stays as read
        if ids[bundle.key(r)].get('as_new'):
            rec['origin'] = None  # a copy of its own: the next import from that origin updates the other one
        _fill(rec, fill_missing, generic)
        _walk(rec, fix)
        records.append((ids[bundle.key(r)]['id'], rec))
    done: dict[str, list[int]] = {}
    imported = {(rec['kind'], new) for new, rec in records}
    con = project.connect()
    columns: dict[str, list[str]] = {}
    try:
        con.execute('BEGIN')
        with bundle.opened():
            report('write', 0, len(records))
            for i, ((new, rec), data) in enumerate(_prefetched(bundle, records, workers, memory_budget)):
                check()
                report('write', i, len(records), {'kind': rec['kind'], 'name': label(rec), 'id': new})
                _write(con, bundle, rec, new, data, columns, project.files)
                done.setdefault(rec['kind'], []).append(new)
            report('write', len(records), len(records))
        # links on the parent's side when the parent did not come in
        for i, (new, rec) in enumerate(records):
            if i % 200 == 0:
                report('links', i, len(records))
                check()
            links = rec.get('links') or {}
            if rec['kind'] == 'team':
                for lid in links.get('leagues', []):
                    if ('league', lid) not in imported:
                        _join_league(con, dest, lid, new)
            if rec['kind'] == 'player':
                for t in links.get('teams', []):
                    if ('team', t['team']) not in imported:
                        _join_team(con, dest, t, new)
        check()
        report('save')
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
        # the files of the entities it replaced, and of a cancelled import, are not used any more (a file a screen is
        # saving right now was just written or touched by its put: younger than min_age, it stays)
        try:
            project.prune_files(min_age=30)
        except OSError:
            pass
    return done


def _write(con: sqlite3.Connection, bundle: Bundle, rec: dict, oid: int, data: dict[str, bytes] | None = None,
           columns: dict[str, list[str]] | None = None, store: FileStore | None = None) -> None:
    """data: the record's files already read (the rest is read here); columns: a cache of the tables' columns;
    store: the project's files (where the record's files are kept)."""
    def read(name):
        return data[name] if data is not None and name in data else bundle.read_file(name)

    def folder(table):
        if table == 'player_files':
            return FACES, '.rx3'
        if table == 'equipment_files':
            return EQUIPMENT_FOLDERS[kind], '.rx3'
        return STADIUMS, None

    def known(table):
        if columns is not None and table in columns:
            return columns[table]
        found = [c[1] for c in con.execute(f'PRAGMA table_info({table})')]
        if columns is not None:
            columns[table] = found
        return found
    kind = rec['kind']
    # an update keeps the date the entity was first created in this project
    before = con.execute('SELECT COALESCE(d.created_at, c.created_at) FROM created c LEFT JOIN dates d '
                         'ON d.kind = c.kind AND d.id = c.id WHERE c.kind = ? AND c.id = ?', (kind, oid)).fetchone()
    _clear(con, kind, oid)
    dates = rec.get('dates') or {}
    now = int(datetime.datetime.now().timestamp())
    updated = dates.get('updated_at') or now
    if before is not None and before[0] is not None and rec['created']:
        dates = {**dates, 'created_at': before[0]}
    origin = rec.get('origin')
    if origin:
        con.execute('INSERT INTO origins VALUES (?, ?, ?, ?, ?)',
                    (kind, oid, origin['source'], origin['id'], max(now, updated)))
    if rec['created']:
        created = dates.get('created_at') or now
        con.execute('INSERT INTO created VALUES (?, ?, ?)', (kind, oid, created))
    if kind in NAME_TABLES:
        table, _ = NAME_TABLES[kind]
        con.executemany(f'INSERT INTO {table} VALUES (?, ?, ?, ?)',
                        [(oid, key, lang, text) for key, by in rec['names'].items() for lang, text in by.items()
                         if isinstance(text, str) and text.strip()])
    con.executemany('INSERT INTO fields VALUES (?, ?, ?, ?)',
                    [(kind, oid, n, json.dumps(v, ensure_ascii=False)) for n, v in rec['fields'].items()
                     if v is not None])
    for slot, name in rec['pictures'].items():
        rel, size, dig = store.put(PICTURES, read(name), '.png')
        con.execute('INSERT INTO pictures (kind, id, slot, file, size, digest, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (kind, oid, slot, rel, size, dig, updated))
    if rec['hidden']:
        con.execute('INSERT OR IGNORE INTO hidden VALUES (?, ?)', (kind, oid))
    tables = dict(OWN_TABLES.get(kind, ()))
    if kind in EQUIPMENT_KINDS:
        tables['equipment_files'] = 'id'
    for table, rows in rec['tables'].items():
        column = tables.get(table)
        if column is None:
            continue
        if table in ('team_rosters_set', 'league_members_set'):
            con.execute(f'INSERT OR IGNORE INTO {table} VALUES (?)', (oid,))
            continue
        for r in rows:
            row = dict(r)
            col = BLOB_COLUMNS.get(table)
            if col:
                name = row.pop(col, None)
                row.pop('file', None)  # never a path of another project
                if not isinstance(name, str):
                    continue
                content = read(name)
                if table == 'player_files' and row.get('paint') is not None:  # a generic hair of the package (_fill)
                    content = facefill.paint_hair(content, row.pop('paint'))
                where, ext = folder(table)
                if ext is None:  # a stadium file: the extension of its game path
                    ext = os.path.splitext(str(row.get('name', '')))[1]
                row['file'], row['size'], row['digest'] = store.put(where, content, ext)
            if table == 'equipment_files':
                row['kind'] = kind
            row[column] = oid
            cols = known(table)
            row = {c: v for c, v in row.items() if c in cols}
            con.execute(f'INSERT OR REPLACE INTO {table} ({", ".join(row)}) VALUES ({", ".join("?" * len(row))})',
                        list(row.values()))
    # a squad / team list given without its "set" row (a zip of another tool): it is set
    if kind == 'team' and 'team_rosters' in rec['tables'] and 'team_rosters_set' not in rec['tables']:
        con.execute('INSERT OR IGNORE INTO team_rosters_set VALUES (?)', (oid,))
    if kind == 'league' and 'league_members' in rec['tables'] and 'league_members_set' not in rec['tables']:
        con.execute('INSERT OR IGNORE INTO league_members_set VALUES (?)', (oid,))
    con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', (kind, oid, updated))
    con.execute('INSERT OR REPLACE INTO dates VALUES (?, ?, ?, ?)',
                (kind, oid, (dates.get('created_at') or now) if rec['created'] else None, updated))


def _clear(con: sqlite3.Connection, kind: str, oid: int) -> None:
    """Everything the project had of the entity (an import replaces it whole)."""
    if kind in NAME_TABLES:
        table, column = NAME_TABLES[kind]
        con.execute(f'DELETE FROM {table} WHERE {column} = ?', (oid,))
    for table in ('fields', 'pictures', 'hidden', 'created', 'edited', 'dates', 'origins'):
        con.execute(f'DELETE FROM {table} WHERE kind = ? AND id = ?', (kind, oid))
    for table, column in OWN_TABLES.get(kind, ()):
        con.execute(f'DELETE FROM {table} WHERE {column} = ?', (oid,))
    if kind in EQUIPMENT_KINDS:
        con.execute('DELETE FROM equipment_files WHERE kind = ? AND id = ?', (kind, oid))


def _join_league(con, dest: Destination, league_id: int, team_id: int) -> None:
    if con.execute('SELECT 1 FROM league_members_set WHERE league_id = ?', (league_id,)).fetchone():
        if con.execute('SELECT 1 FROM league_members WHERE league_id = ? AND team_id = ?',
                       (league_id, team_id)).fetchone():
            return
        last = con.execute('SELECT COALESCE(MAX(ord), -1) FROM league_members WHERE league_id = ?',
                           (league_id,)).fetchone()[0]
        con.execute('INSERT INTO league_members (league_id, team_id, ord, hidden) VALUES (?, ?, ?, 0)',
                    (league_id, team_id, last + 1))
    else:
        teams = [t for t in dest.league_members(league_id) if t != team_id] + [team_id]
        con.execute('INSERT INTO league_members_set VALUES (?)', (league_id,))
        con.executemany('INSERT OR IGNORE INTO league_members (league_id, team_id, ord, hidden) VALUES (?, ?, ?, 0)',
                        [(league_id, t, i) for i, t in enumerate(teams)])
    _touch(con, 'league', league_id)


def _join_team(con, dest: Destination, link: dict, player_id: int) -> None:
    team_id = link['team']
    row = (link.get('jersey'), link.get('slot') if _int(link.get('slot')) else 29)
    if con.execute('SELECT 1 FROM team_rosters_set WHERE team_id = ?', (team_id,)).fetchone():
        if con.execute('SELECT 1 FROM team_rosters WHERE team_id = ? AND player_id = ?',
                       (team_id, player_id)).fetchone():
            return
        last = con.execute('SELECT COALESCE(MAX(ord), -1) FROM team_rosters WHERE team_id = ?',
                           (team_id,)).fetchone()[0]
        con.execute('INSERT INTO team_rosters (team_id, player_id, ord, jersey, slot, hidden) VALUES (?, ?, ?, ?, ?, 0)',
                    (team_id, player_id, last + 1, *row))
    else:
        squad = [r for r in dest.team_roster(team_id) if r['player'] != player_id]
        squad.append({'player': player_id, 'jersey': row[0], 'slot': row[1]})
        con.execute('INSERT INTO team_rosters_set VALUES (?)', (team_id,))
        con.executemany('INSERT OR IGNORE INTO team_rosters (team_id, player_id, ord, jersey, slot, hidden) '
                        'VALUES (?, ?, ?, ?, ?, 0)',
                        [(team_id, r['player'], i, r.get('jersey'), r.get('slot', 29)) for i, r in enumerate(squad)])
    _touch(con, 'team', team_id)


def _touch(con, kind: str, oid: int) -> None:
    now = int(datetime.datetime.now().timestamp())
    con.execute('INSERT OR REPLACE INTO edited VALUES (?, ?, ?)', (kind, oid, now))
    created = con.execute('SELECT 1 FROM created WHERE kind = ? AND id = ?', (kind, oid)).fetchone()
    con.execute('INSERT INTO dates VALUES (?, ?, ?, ?) ON CONFLICT (kind, id) DO UPDATE SET updated_at = '
                'excluded.updated_at', (kind, oid, now if created else None, now))
