"""Builds the patch: the changed game files, laid out like the game folder, ready to be installed.

How each changed file reaches the game:
  - an entry of an archive with a .bh index (data0..7.big, patch.big): written loose at its game path, and every .bh
    whose archive lists it gets that record's hash words zeroed, so the game opens the loose file;
  - an entry of data/loc/locale.big (no .bh): the whole archive is written again with the new entry.
The patch never holds the big archives themselves.
"""
import os
import shutil

from . import bh, fields, fifa14, flags, images, t3db
from .big import BigArchive, normalize, rebuild
from .dbedit import Database, LanguageStrings, Table
from .gamefs import DATABASE, GameFiles
from .project import DEFAULT_LANG, Project

LOCALE = 'data/loc/locale.big'


class PatchBuilder:
    def __init__(self, files: GameFiles):
        self.files = files
        self.entries: dict[str, bytes] = {}  # game path -> new bytes

    def put(self, game_path: str, data: bytes) -> None:
        self.entries[normalize(game_path)] = data

    def write(self, out_dir: str) -> dict:
        """Writes the patch into out_dir (emptied first); returns a summary."""
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir)
        locale_path = self.files._loose.get(LOCALE)  # noqa: SLF001 - the archive file (or its backup)
        locale_entries = BigArchive(locale_path).entries if locale_path else {}
        to_locale = {k: v for k, v in self.entries.items() if k in locale_entries}
        loose = {k: v for k, v in self.entries.items() if k not in locale_entries}
        for path, data in loose.items():
            target = os.path.join(out_dir, *path.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as f:
                f.write(data)
        indexes = self._zero_indexes(set(loose), out_dir)
        if to_locale:
            target = os.path.join(out_dir, *LOCALE.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as f:
                f.write(rebuild(locale_path, to_locale))
        return {'loose': sorted(loose), 'locale': sorted(to_locale), 'indexes': indexes}

    def _zero_indexes(self, paths: set[str], out_dir: str) -> dict[str, int]:
        """Writes each .bh that lists one of the paths, with those records zeroed; {bh name: records zeroed}."""
        out = {}
        for archive in self.files.archives:
            if os.path.dirname(os.path.abspath(archive.path)) != os.path.abspath(self.files.root):
                continue  # archives under data/ have no .bh
            hits = [i for i, name in enumerate(archive.order) if name in paths]
            if not hits:
                continue
            bh_name = archive.name[:-4] + '.bh'
            source = self.files._loose.get(bh_name) or os.path.join(self.files.root, bh_name)  # noqa: SLF001
            with open(self._original(bh_name, source), 'rb') as f:
                data = f.read()
            if not bh.entry_count_matches(data, len(archive.order)):
                raise ValueError(f'{bh_name} does not match {archive.name}')
            with open(os.path.join(out_dir, bh_name), 'wb') as f:
                f.write(bh.zero(data, hits))
            out[bh_name] = len(hits)
        return out

    def _original(self, rel: str, default: str) -> str:
        """The clean copy of a file of the game folder (its backup when a patch of this app replaced it)."""
        return self.files._substitutes.get(normalize(rel), default)  # noqa: SLF001


NAME_STRINGS = {'team': fifa14.TEAM_NAME_STRINGS, 'league': fifa14.LEAGUE_NAME_STRINGS,
                'country': fifa14.COUNTRY_NAME_STRINGS}
ID_COLUMNS = {'player': ('players', 'playerid'), 'team': ('teams', 'teamid'), 'league': ('leagues', 'leagueid')}
MAX_NAME_ID = (1 << 15) - 1  # playernames.nameid has 15 bits


def _initials(text: str, size: int) -> str:
    words = [w for w in text.split() if w[:1].isalnum()]
    letters = ''.join(w[0] for w in words) if len(words) > 1 else text
    return letters[:size].upper()


# a created league or country needs every name the game shows: the missing ones come from its full name
DERIVED_NAMES = {
    'league': {'abbr15': lambda t: t[:15].strip(), 'abbr': lambda t: _initials(t, 4), 'trophy': lambda t: t,
               'trophy_abbr15': lambda t: t[:15].strip()},
    'country': {'abbr3': lambda t: _initials(t, 3) if len(t.split()) > 2 else t[:3].upper()},
}


def with_derived_names(kind: str, names: dict) -> dict:
    """The names of a created entity with the missing ones filled from the full name (per language)."""
    rules = DERIVED_NAMES.get(kind)
    full = names.get('full') or {}
    if not rules or not full:
        return names
    out = {k: dict(v) for k, v in names.items()}
    for key, rule in rules.items():
        user = names.get(key) or {}  # what the user wrote wins: a value for every language covers them all
        have = out.setdefault(key, {})
        for lang, text in full.items():
            if text and not user.get(lang) and not (lang != DEFAULT_LANG and user.get(DEFAULT_LANG)):
                have[lang] = rule(text)
    return out


def language_edits(project: Project) -> dict[str, dict[str, str]]:
    """{language or '*': {stringid: text}} of every team and league name saved in the project."""
    out: dict[str, dict[str, str]] = {}
    for kind, prefixes in NAME_STRINGS.items():
        created = set(project.created(kind)) if kind in DERIVED_NAMES else set()
        for oid, names in project.all_names(kind).items():
            if oid in created:
                names = with_derived_names(kind, names)
            for key, by_lang in names.items():
                prefix = prefixes.get(key)
                if not prefix:
                    continue
                for lang, text in by_lang.items():
                    out.setdefault(lang, {})[f'{prefix}{oid}'] = text
    return out


def team_language_edits(project: Project) -> dict[str, dict[str, str]]:
    """Kept for older callers: the language edits of teams and leagues."""
    return language_edits(project)


class PlayerNameTable:
    """playernames: the id of a text (an existing row with the same text, else a new row after the last id)."""

    def __init__(self, table: Table):
        self.table = table
        self.ids: dict[str, int] = {}
        for row in table.records:
            text = table.get(row, 'name')
            if text and text not in self.ids:
                self.ids[text] = table.get(row, 'nameid')
        self.next_id = max((table.get(r, 'nameid') for r in table.records), default=0) + 1

    def id_for(self, text: str) -> int:
        if text in self.ids:
            return self.ids[text]
        if self.next_id > MAX_NAME_ID:
            raise ValueError('the name table is full')
        row = list(self.table.records[-1])
        self.table.set(row, 'nameid', self.next_id)
        if any(f.name == 'commentaryid' for f in self.table.fields):
            self.table.set(row, 'commentaryid', 900000)  # the clean game's "no commentary name"
        self.table.set(row, 'name', text)
        self.table.records.append(row)
        self.ids[text] = self.next_id
        self.next_id += 1
        return self.ids[text]


def apply_database(db: Database, project: Project) -> dict:
    """Writes every saved field into the database; returns what changed and what could not be written."""
    changed: dict[str, int] = {}
    skipped: list[str] = []
    names_table = None
    for kind, (table_name, id_column) in ID_COLUMNS.items():
        saved = project.all_fields(kind)
        if not saved:
            continue
        table = db.table(table_name)
        rows = {table.get(r, id_column): r for r in table.records}
        columns = {f.name for f in table.fields}
        for oid, values in saved.items():
            row = rows.get(oid)
            if row is None:
                skipped.append(f'{kind} {oid}')
                continue
            for column, value in fields.to_columns(kind, values).items():
                if column not in columns:
                    skipped.append(f'{kind} {oid}: {column}')
                    continue
                table.set(row, column, value)
            if kind == 'player':
                for field, column in fields.NAME_FIELDS.items():
                    text = values.get(field)
                    if text:
                        if names_table is None:
                            names_table = PlayerNameTable(db.table('playernames'))
                        table.set(row, column, names_table.id_for(text))
            changed[kind] = changed.get(kind, 0) + 1
    return {'changed': changed, 'skipped': skipped}


class BuildError(ValueError):
    """The project cannot become a patch (a limit of the game); `code` names the message."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(f'{code}: {detail}')
        self.code, self.detail = code, detail


def _table(db: Database, name: str):
    try:
        return db.table(name)
    except KeyError:
        return None


def _has(table, column: str) -> bool:
    return any(f.name == column for f in table.fields)


def _model_row(table, column: str, preferred: int) -> list:
    rows = table.find(**{column: preferred})
    return list(rows[0] if rows else table.records[0])


def _shown_name(names: dict, key: str = 'full') -> str:
    by_lang = names.get(key) or {}
    return by_lang.get(DEFAULT_LANG) or by_lang.get('eng_us') or next(iter(by_lang.values()), '')


def add_created(db: Database, project: Project) -> dict:
    """Rows of the countries and leagues the user created (before the saved fields are written over them)."""
    added = {}
    nations = _table(db, 'nations')
    for nid in project.created('country'):
        if nations is None or nations.find(nationid=nid):
            raise BuildError('country_id_taken', str(nid))
        row = _model_row(nations, 'nationid', fifa14.TEMPLATE_NATION)
        name = _shown_name(project.names('country', nid)) or f'Country {nid}'
        for column, value in (('nationid', nid), ('nationname', name[:44]), ('top_tier', 0), ('teamid', -1)):
            if _has(nations, column):
                nations.set(row, column, value)
        nations.records.append(row)
        added['country'] = added.get('country', 0) + 1
    leagues = db.table('leagues')
    refs = _table(db, 'leaguerefereelinks')
    for lid in project.created('league'):
        if leagues.find(leagueid=lid):
            raise BuildError('league_id_taken', str(lid))
        row = _model_row(leagues, 'leagueid', fifa14.TEMPLATE_LEAGUE)
        for column, value in (('leagueid', lid), ('leaguename', f'League {lid}'), ('level', 1),
                              ('leaguetimeslice', 0), ('iswithintransferwindow', 0)):
            if _has(leagues, column):
                leagues.set(row, column, value)
        leagues.records.append(row)
        if refs is not None:
            for r in list(refs.find(leagueid=fifa14.TEMPLATE_LEAGUE)):
                new = list(r)
                refs.set(new, 'leagueid', lid)
                refs.records.append(new)
        added['league'] = added.get('league', 0) + 1
    return added


def write_members(db: Database, project: Project) -> int:
    """The team list of every league whose teams the user changed (the league's links replaced, in order)."""
    members = project.all_members()
    if not members:
        return 0
    links = db.table('leagueteamlinks')
    keep = [i for i, r in enumerate(links.records) if links.get(r, 'leagueid') not in members]
    if len(keep) + sum(len(v) for v in members.values()) > fifa14.MAX_LEAGUE_LINKS:
        raise BuildError('too_many_league_links', str(fifa14.MAX_LEAGUE_LINKS))
    model = {}
    for r in links.records:
        model.setdefault(links.get(r, 'leagueid'), r)
    template = model.get(fifa14.TEMPLATE_LEAGUE) or links.records[0]
    raws = links.raw_records + [bytes(links.rec_size)] * (len(links.records) - len(links.raw_records))
    records = [links.records[i] for i in keep]
    raw_records = [raws[i] for i in keep]
    for lid, team_ids in members.items():
        base = model.get(lid, template)
        for pos, tid in enumerate(team_ids):
            row = list(base)
            for f in links.fields:  # the table's counters start at zero for a new link
                if f.type == 3 and f.name not in ('teamid', 'leagueid', 'prevleagueid', 'artificialkey'):
                    links.set(row, f.name, max(0, f.rangelow))
            for column, value in (('teamid', tid), ('leagueid', lid), ('prevleagueid', lid),
                                  ('currenttableposition', pos % fifa14.TABLE_POSITIONS + 1)):
                if _has(links, column):
                    links.set(row, column, value)
            records.append(row)
            raw_records.append(bytes(links.rec_size))
    if _has(links, 'artificialkey'):
        for i, row in enumerate(records):  # the key stays unique: every link numbered again
            links.set(row, 'artificialkey', i)
    links.records, links.raw_records = records, raw_records
    return sum(len(v) for v in members.values())


def created_pictures(files: GameFiles, project: Project, builder: 'PatchBuilder') -> int:
    """Pictures of created leagues (a plain tile with the short name) and the flags the user chose: a created
    country copies the flag of the country chosen (Rest of World by default), a country of the game can take another
    one's flag too."""
    count = 0
    for lid in project.created('league'):
        names = project.names('league', lid)
        text = _shown_name(names, 'abbr') or _shown_name(names, 'abbr15') or _shown_name(names) or str(lid)
        for pattern, (size, dark) in fifa14.LEAGUE_PICTURES.items():
            builder.put(pattern.format(lid), images.league_picture(size, dark, text))
            count += 1
    drawn = project.with_picture('country', 'flag')
    for nid in drawn:  # the user's picture: the four flag files drawn from it
        for pattern, data in flags.flag_files(files, project.picture('country', nid, 'flag')[0]).items():
            builder.put(pattern.format(nid), data)
            count += 1
    countries = set(project.created('country')) | {nid for nid, f in project.all_fields('country').items()
                                                       if f.get('flag_from')}
    for nid in sorted(countries - set(drawn)):
        source = project.fields('country', nid).get('flag_from') or fifa14.TEMPLATE_NATION
        if source == nid:
            continue
        for pattern in fifa14.FLAG_FILES:
            data = files.read(pattern.format(source))
            if data is not None:
                builder.put(pattern.format(nid), data)
                count += 1
    return count


def write_database(files: GameFiles, project: Project, builder: 'PatchBuilder') -> dict | None:
    """The database with the project's fields, created entities and league teams, loose (with its meta file)."""
    has_created = bool(project.created('country') or project.created('league'))
    if not any(project.all_fields(kind) for kind in ID_COLUMNS) and not has_created and not project.all_members():
        return None
    meta_raw, raw = files.read(fifa14.META), files.read(DATABASE)
    if meta_raw is None or raw is None:
        raise ValueError('database not found')
    db = Database(raw, t3db.load_meta(meta_raw))
    created = add_created(db, project)
    result = apply_database(db, project)
    result['created'] = created
    result['league_links'] = write_members(db, project)
    builder.put(DATABASE, db.build())
    builder.put(fifa14.META, meta_raw)
    return result


def build(files: GameFiles, project: Project, out_dir: str, progress=None) -> dict:
    """The patch of the project over the clean game."""
    builder = PatchBuilder(files)
    if progress:
        progress('database', 0.0)
    database = write_database(files, project, builder)
    pictures = created_pictures(files, project, builder)
    edits = language_edits(project)
    missing: set[str] = set()
    languages = sorted({os.path.basename(p)[:-3] for p in files.list('data/loc/') if p.endswith('.db')})
    base_languages = [n for n in languages if not n.endswith('_upd')]
    for i, lang in enumerate(base_languages):
        wanted = {**edits.get(DEFAULT_LANG, {}), **edits.get(lang, {})}
        if progress:
            progress(f'language {lang}', i / max(1, len(base_languages)))
        if not wanted:
            continue
        for name in (lang, f'{lang}_upd'):
            path = f'data/loc/{name}.db'
            raw = files.read(path)
            if raw is None:
                continue
            strings = LanguageStrings(raw)
            # the base database gets every string (a new one with its hashid); the _upd one only overrides its own
            todo = wanted if name == lang else {k: v for k, v in wanted.items() if strings.get(k) is not None}
            changed = False
            for sid, text in todo.items():
                if strings.get(sid) != text:
                    strings.set(sid, text)
                    changed = True
            if changed:
                builder.put(path, strings.build())
    summary = builder.write(out_dir)
    summary['missing_strings'] = sorted(missing)
    summary['database'] = database
    summary['pictures'] = pictures
    if progress:
        progress('done', 1.0)
    return summary
