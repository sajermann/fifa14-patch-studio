"""Builds the patch: the changed game files, laid out like the game folder, ready to be installed.

How each changed file reaches the game:
  - an entry of an archive with a .bh index (data0..7.big, patch.big): written loose at its game path, and every .bh
    whose archive lists it gets that record's hash words zeroed, so the game opens the loose file;
  - an entry of data/loc/locale.big (no .bh): the whole archive is written again with the new entry;
  - an entry removed (PatchBuilder.remove: a part a chosen face does not bring): its .bh record is zeroed and no loose
    file is written, so the game finds it nowhere (tested in the game: a missing hair model or LOD is not drawn, a
    missing eyes texture shows the game's checkered texture).
The patch never holds the big archives themselves.

The build goes in BUILD_STEPS, like the Street Studio's: the language texts start first in worker processes
(f14mod.workers: pure Python, the slow part), the database is edited meanwhile, the pictures (kits, crests, photos,
league pictures, flags: Pillow) and the pack faces in a newer FIFA format (converted into FIFA 14's by
f14mod.faceconv, a few seconds each) are made in a thread pool, then everything is written. Texts, pictures and
converted faces are kept in the build cache (f14mod.buildcache): building again only makes what changed. The other
faces are copied as they are.
"""
import functools
import os
import shutil
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_futures

import re

from PIL import Image

from . import bh, buildcache, faceconv, fields, fifa14, flags, images, t3db, teamkits, workers
from .big import BigArchive, normalize, rebuild
from .dbedit import Database, LanguageStrings, Table
from .gamefs import DATABASE, GameFiles
from .project import DEFAULT_LANG, Project

LOCALE = 'data/loc/locale.big'


BUILD_STEPS = ('database', 'images', 'texts', 'files')


class BuildCancelled(Exception):
    """The user stopped the build (build(cancel=...)). What was made so far stays in the cache."""
    code = 'build_cancelled'  # what the interface shows (f14api Jobs: job code)


class PatchBuilder:
    def __init__(self, files: GameFiles, pool: ThreadPoolExecutor | None = None,
                 cache: buildcache.BuildCache | None = None, name_of=None):
        self.files = files
        self.entries: dict[str, bytes] = {}  # game path -> new bytes
        self.removed: set[str] = set()  # game paths the game must no longer find (no loose file, record zeroed)
        self.pool = pool  # threads for the pictures (None = made at once)
        self.cache = cache
        self.game_key = ''  # buildcache.game_fingerprint of files (set by build when there is a cache)
        self.name_of = name_of  # (kind, id) -> shown name, for the progress
        self.jobs: list[tuple[Future, str, str]] = []  # pictures being made: (future of {path: bytes}, kind, name)
        self.from_cache: set[str] = set()  # game paths whose bytes the build cache gave

    def put_all(self, files: dict[str, bytes], cached: bool) -> None:
        for path, data in files.items():
            self.put(path, data)
            if cached:
                self.from_cache.add(normalize(path))
            else:
                self.from_cache.discard(normalize(path))

    def put(self, game_path: str, data: bytes) -> None:
        self.entries[normalize(game_path)] = data
        self.removed.discard(normalize(game_path))

    def remove(self, game_path: str) -> None:
        """The game no longer finds this archive entry (nothing happens to a path no indexed archive has)."""
        self.entries.pop(normalize(game_path), None)
        self.removed.add(normalize(game_path))

    def name(self, kind: str, oid: int, project: 'Project | None' = None) -> str:
        """What the progress says about an entity: its shown name, else the project's name, else its id."""
        shown = self.name_of(kind, oid) if self.name_of else None
        if not shown and project is not None:
            shown = _shown_name(project.names(kind, oid))
        return shown or str(oid)

    def key(self, kind: str, modules: tuple, *parts) -> str | None:
        """Cache key of a picture job (None when there is no cache)."""
        if self.cache is None or not self.cache.folder:
            return None
        return buildcache.key(kind, buildcache.code_version(*modules), self.game_key, *parts)

    def later(self, kind: str, name: str, key: str | None, make) -> None:
        """make() -> {game path: bytes}, run in the thread pool (Pillow releases the GIL) or reused from the cache
        under key; collect() puts the files in once they are all made. kind / name: what the progress says while the
        build waits for it (kit, crest, photo, league, flag)."""
        def run():
            if key is not None:
                found = self.cache.get(key)
                if found is not None:
                    return found, True
            made = make()
            if key is not None:
                self.cache.put(key, made)
            return made, False
        if self.pool is None:
            future: Future = Future()
            future.set_result(run())
        else:
            future = self.pool.submit(run)
        self.jobs.append((future, kind, name))

    def collect(self, progress=None, check=None) -> None:
        """Waits for the pictures (progress('images', done, total, kind=..., name=...) while waiting; check() may
        stop the build) and puts their files in, in the order they were asked."""
        total = len(self.jobs)
        for k, (future, kind, name) in enumerate(self.jobs):
            while not future.done():
                if check:
                    check()
                if progress:
                    done = k + sum(1 for f, _, _ in self.jobs[k:] if f.done())
                    progress('images', done, total, kind=kind, name=name)
                wait_futures([future], timeout=0.5)
            self.put_all(*future.result())
        self.jobs = []

    def write(self, out_dir: str, progress=None) -> dict:
        """Writes the patch into out_dir (emptied first); returns a summary. progress('files', done, total)."""
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir)
        locale_path = self.files._loose.get(LOCALE)  # noqa: SLF001 - the archive file (or its backup)
        locale_entries = BigArchive(locale_path).entries if locale_path else {}
        to_locale = {k: v for k, v in self.entries.items() if k in locale_entries}
        loose = {k: v for k, v in self.entries.items() if k not in locale_entries}
        total = len(loose) + 1
        for k, (path, data) in enumerate(loose.items()):
            if progress and k % 20 == 0:
                progress('files', k, total)
            target = os.path.join(out_dir, *path.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as f:
                f.write(data)
        indexes = self._zero_indexes(set(loose) | self.removed, out_dir)
        if to_locale:
            target = os.path.join(out_dir, *LOCALE.split('/'))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as f:
                f.write(rebuild(locale_path, to_locale))
        if progress:
            progress('files', total, total)
        # files of the patch the build cache gave whole: "N files, X new and Y reused from the cache"
        reused = sum(1 for k in loose if k in self.from_cache)
        if to_locale and all(k in self.from_cache for k in to_locale):
            reused += 1
        return {'reused_files': reused, 'loose': sorted(loose), 'locale': sorted(to_locale), 'indexes': indexes,
                'removed': sorted(self.removed)}

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
    'team': {'abbr15': lambda t: t[:15].strip(), 'abbr10': lambda t: t[:10].strip(), 'abbr7': lambda t: t[:7].strip(),
             'abbr3': lambda t: _initials(t, 3) if len(t.split()) > 1 else t[:3].upper(), 'commentary': lambda t: t},
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


FILL_ONLY = '*fill'  # key of language_edits: "every language" values that only fill the texts the game lacks
# names edited in a grid where the game's text of each language is a value of its own (the "All" row of an original
# country or league only fills the languages without a text; a created one has none, so it goes everywhere)
FILL_ONLY_KINDS = ('country', 'league')


def language_edits(project: Project) -> dict[str, dict[str, str]]:
    """{language, '*' or FILL_ONLY: {stringid: text}} of every team, league and country name saved in the project."""
    out: dict[str, dict[str, str]] = {}
    for kind, prefixes in NAME_STRINGS.items():
        created = set(project.created(kind)) if kind in DERIVED_NAMES or kind in FILL_ONLY_KINDS else set()
        for oid, names in project.all_names(kind).items():
            if oid in created and kind in DERIVED_NAMES:
                names = with_derived_names(kind, names)
            for key, by_lang in names.items():
                prefix = prefixes.get(key)
                if not prefix:
                    continue
                for lang, text in by_lang.items():
                    if lang == DEFAULT_LANG and kind in FILL_ONLY_KINDS and oid not in created:
                        lang = FILL_ONLY
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
            columns_values = fields.to_columns(kind, values)
            if kind == 'player' and values.get('traits') is not None and {'trait1', 'trait2'} <= columns:
                current = {c: table.get(row, c) for c in ('trait1', 'trait2')}
                columns_values.update(fields.trait_columns(current, values['traits']))
            for column, value in columns_values.items():
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
        for column, value in fifa14.new_league_values(lid).items():
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
    out = project.all_hidden_members()  # a team left out of the patch in a league has no link to it
    members = {lid: [tid for tid in team_ids if tid not in out.get(lid, ())] for lid, team_ids in members.items()}
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


def _renumber_links(links) -> None:
    if _has(links, 'artificialkey'):
        for i, row in enumerate(links.records):  # the key stays unique: every link numbered again
            links.set(row, 'artificialkey', i)


def write_visibility(db: Database, project: Project) -> dict:
    """Countries, leagues and teams hidden in the game, and leagues shown in several countries (tests OC1/OC2/LC1):
    - a league is listed under its country: one `leagues` row per country, all with the league's id (the team links
      stay once), none for a country where the user hid it (`hidden_in_countries`); a league hidden in the game, or
      whose countries are all hidden, gets one row with country 0;
    - a team hidden in the game keeps only its links to hidden leagues (or gets one to HIDDEN_LEAGUE);
    - a league the user changed or created that is left without any team is hidden too (the game would fill an empty
      list with a random team)."""
    hidden_countries = project.hidden_in_game('country')
    hidden_leagues = project.hidden_in_game('league')
    hidden_teams = project.hidden_in_game('team')
    league_fields = project.all_fields('league')
    if not (hidden_countries or hidden_leagues or hidden_teams
            or any(f.get('extra_countries') or f.get('hidden_in_countries') for f in league_fields.values()))             and not project.all_members():
        return {}
    leagues = db.table('leagues')
    rows: dict[int, list] = {}
    for r in leagues.records:
        rows.setdefault(leagues.get(r, 'leagueid'), []).append(r)
    countries = {lid: list(dict.fromkeys(
        [leagues.get(rs[0], 'countryid'), *league_fields.get(lid, {}).get('extra_countries', [])]))
        for lid, rs in rows.items()}
    # a league hidden in one of its countries (hidden_in_countries) is not listed there; hidden in all of them, it is
    # hidden in the game
    shown = {lid: [c for c in cs if c != fifa14.HIDDEN_COUNTRY and c not in hidden_countries
                   and c not in league_fields.get(lid, {}).get('hidden_in_countries', [])]
             for lid, cs in countries.items()}
    out_leagues = {lid for lid, cs in shown.items() if lid in hidden_leagues or not cs}
    # teams hidden in the game: only their links to hidden leagues stay
    links = db.table('leagueteamlinks')
    moved = 0
    if hidden_teams:
        kept, raws = [], links.raw_records + [bytes(links.rec_size)] * (len(links.records) - len(links.raw_records))
        kept_raw, linked = [], set()
        for row, raw in zip(links.records, raws):
            tid, lid = links.get(row, 'teamid'), links.get(row, 'leagueid')
            if tid in hidden_teams and lid not in out_leagues:
                moved += 1
                continue
            kept.append(row)
            kept_raw.append(raw)
            linked.add(tid)
        template = next((r for r in links.records if links.get(r, 'leagueid') == fifa14.HIDDEN_LEAGUE), None)
        if fifa14.HIDDEN_LEAGUE in rows:  # without that league the team stays with no league (also hidden: OC2)
            for tid in sorted(hidden_teams - linked):
                row = list(template or links.records[0])
                for column, value in (('teamid', tid), ('leagueid', fifa14.HIDDEN_LEAGUE),
                                      ('prevleagueid', fifa14.HIDDEN_LEAGUE)):
                    if _has(links, column):
                        links.set(row, column, value)
                kept.append(row)
                kept_raw.append(bytes(links.rec_size))
        links.records, links.raw_records = kept, kept_raw
        _renumber_links(links)
    # a changed or created league left without a visible team is hidden too
    teams_in = {}
    for r in links.records:
        teams_in.setdefault(links.get(r, 'leagueid'), set()).add(links.get(r, 'teamid'))
    empty = {lid for lid in project.all_members() if lid in rows and not (teams_in.get(lid, set()) - hidden_teams)}
    out_leagues |= empty
    records, raw_records = [], []
    raws = leagues.raw_records + [bytes(leagues.rec_size)] * (len(leagues.records) - len(leagues.raw_records))
    extra_rows = 0
    for r, raw in zip(leagues.records, raws):
        lid = leagues.get(r, 'leagueid')
        if r is not rows[lid][0]:
            continue  # a league with more rows already: written again below from its first row
        if lid in out_leagues:
            leagues.set(r, 'countryid', fifa14.HIDDEN_COUNTRY)
            records.append(r)
            raw_records.append(raw)
            continue
        for i, country in enumerate(shown[lid]):
            row = r if i == 0 else list(r)
            leagues.set(row, 'countryid', country)
            records.append(row)
            raw_records.append(raw)  # the same bits outside the fields as the league's row
            extra_rows += i > 0
    leagues.records, leagues.raw_records = records, raw_records
    already = {lid for lid, cs in countries.items() if cs[0] == fifa14.HIDDEN_COUNTRY}  # the game hides them itself
    return {'hidden_leagues': sorted((out_leagues & set(rows)) - already), 'extra_country_rows': extra_rows,
            'team_links_removed': moved}


def created_pictures(files: GameFiles, project: Project, builder: 'PatchBuilder') -> int:
    """Pictures of leagues (from the user's picture, else, for a created league, a plain tile with the short name)
    and the flags the user chose: a created country copies the flag of the country chosen (Rest of World by default),
    a country of the game can take another one's flag too."""
    count = 0
    logos = project.with_picture('league', 'logo')
    for lid in logos:  # the user's picture: the eight league pictures drawn from it
        png_data = project.picture('league', lid, 'logo')[0]
        builder.later('league', builder.name('league', lid, project),
                      builder.key('league_logo', ('images',), lid, png_data, fifa14.LEAGUE_PICTURES),
                      functools.partial(_league_logo_files, lid, png_data))
        count += len(fifa14.LEAGUE_PICTURES)
    for lid in project.created('league'):
        if lid in logos:
            continue
        names = project.names('league', lid)
        text = _shown_name(names, 'abbr') or _shown_name(names, 'abbr15') or _shown_name(names) or str(lid)
        builder.later('league', builder.name('league', lid, project),
                      builder.key('league_tile', ('images',), lid, text, fifa14.LEAGUE_PICTURES),
                      functools.partial(_league_tile_files, lid, text))
        count += len(fifa14.LEAGUE_PICTURES)
    drawn = project.with_picture('country', 'flag')
    for nid in drawn:  # the user's picture: the four flag files drawn from it
        png_data = project.picture('country', nid, 'flag')[0]
        builder.later('flag', builder.name('country', nid, project),
                      builder.key('flag', ('flags',), nid, png_data),
                      functools.partial(_flag_files, files, nid, png_data))
        count += len(fifa14.FLAG_FILES)
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


def _league_logo_files(lid: int, png_data: bytes) -> dict[str, bytes]:
    return {pattern.format(lid): images.league_from_picture(png_data, size)
            for pattern, (size, _dark) in fifa14.LEAGUE_PICTURES.items()}


def _league_tile_files(lid: int, text: str) -> dict[str, bytes]:
    return {pattern.format(lid): images.league_picture(size, dark, text)
            for pattern, (size, dark) in fifa14.LEAGUE_PICTURES.items()}


def _flag_files(files: GameFiles, nid: int, png_data: bytes) -> dict[str, bytes]:
    return {pattern.format(nid): data for pattern, data in flags.flag_files(files, png_data).items()}


# ---- teams (test TN1) ----------------------------------------------------------------------------------------------

TEAM_COPIED_FILES = re.compile(r'data/sceneassets/(?:warmup|warmup/tra|adboard|banner|flag)/')  # copied from the model
TEAM_LOOKS = re.compile(r'data/(?:sceneassets/kit/|ui/imgassets/(?:crest|crest16x16|crest32x32|crest50x50|kits)/)')
STARTERS = 11
BENCH, RESERVE = 28, 29  # teamplayerlinks.position of a substitute and of a player out of the squad


def _team_source(project: Project, tid: int) -> tuple[int, bool]:
    return project.team_source(tid) or (teamkits.MODEL_TEAM, False)


def _next(table, column: str) -> int:
    if not _has(table, column):
        return 0
    return max((table.get(r, column) for r in table.records), default=0) + 1


def _clone(table, row, **values) -> list:
    new = list(row)
    for column, value in values.items():
        if _has(table, column):
            table.set(new, column, value)
    table.records.append(new)
    return new


def add_created_teams(db: Database, project: Project) -> int:
    """Rows of the teams the user created: a copy of the model team's rows (team, stadium, Rest of World link,
    formation, kits of year 0) under the new id; the squad comes from write_rosters (or the model's, when copied)."""
    created = project.created('team')
    if not created:
        return 0
    teams, kits, formations = db.table('teams'), db.table('teamkits'), db.table('formations')
    stadiums, row_links = _table(db, 'teamstadiumlinks'), _table(db, 'rowteamnationlinks')
    links = db.table('teamplayerlinks')
    for tid in created:
        if teams.find(teamid=tid):
            raise BuildError('team_id_taken', str(tid))
        template, copy = _team_source(project, tid)
        if not copy and not project.roster(tid):
            raise BuildError('team_too_few_players', str(tid))
        rows = teams.find(teamid=template) or teams.find(teamid=teamkits.MODEL_TEAM)
        name = _shown_name(project.names('team', tid)) or f'Team {tid}'
        _clone(teams, rows[0], teamid=tid, assetid=tid, teamname=name[:30])
        for table in (stadiums, row_links):
            if table is not None and table.find(teamid=template):
                _clone(table, table.find(teamid=template)[0], teamid=tid)
        own = formations.find(teamid=template)
        if own:
            _clone(formations, own[0], teamid=tid, formationid=_next(formations, 'formationid'))
        for r in [r for r in kits.records if kits.get(r, 'teamtechid') == template and kits.get(r, 'year') == 0]:
            _clone(kits, r, teamtechid=tid, teamkitid=_next(kits, 'teamkitid'))
        if copy and project.roster(tid) is None:  # the copied team's squad (the players are in both teams)
            key = _next(links, 'artificialkey')
            for r in [r for r in links.records if links.get(r, 'teamid') == template]:
                _clone(links, r, teamid=tid, artificialkey=key)
                key += 1
    return len(created)


def write_formations(db: Database, project: Project) -> int:
    """The formation each team got (field `formation` = one of the game's 33): its own row takes the positions."""
    formations, teams = db.table('formations'), db.table('teams')
    generic = {formations.get(r, 'relativeformationid'): r for r in formations.records
               if formations.get(r, 'teamid') == -1}
    count = 0
    for tid, values in project.all_fields('team').items():
        chosen = generic.get(values.get('formation'))
        if chosen is None or not teams.find(teamid=tid):
            continue
        own = formations.find(teamid=tid)
        if own:
            for f in formations.fields:
                if f.name not in ('teamid', 'formationid'):
                    formations.set(own[0], f.name, formations.get(chosen, f.name))
        else:
            _clone(formations, chosen, teamid=tid, formationid=_next(formations, 'formationid'))
        count += 1
    return count


def lineup(rows: list[dict], positions: list[int]) -> list[dict]:
    """The squad (at most MAX_SQUAD: the rest stays out of the patch) with one starter in each slot of the
    formation: a starter whose slot the formation has keeps it; the other starters take the free slots in order;
    with fewer than 11 starters the next players step up. A starter left without a slot goes to the bench."""
    rows = [dict(r, slot=r.get('slot', RESERVE)) for r in rows][:fifa14.MAX_SQUAD]
    free = list(positions)
    placed = set()
    for i, r in enumerate(rows):
        if r['slot'] < BENCH and r['slot'] in free:
            free.remove(r['slot'])
            placed.add(i)
    for wanted in (lambda r: r['slot'] < BENCH, lambda r: True):  # other starters first, then anyone
        for i, r in enumerate(rows):
            if free and i not in placed and wanted(r):
                r['slot'] = free.pop(0)
                placed.add(i)
    for i, r in enumerate(rows):
        if i not in placed and r['slot'] < BENCH:
            r['slot'] = BENCH
    return rows


def write_rosters(db: Database, project: Project) -> int:
    """The squad of every team whose squad the user changed: its teamplayerlinks rows replaced (jersey number and
    lineup slot); a captain or taker outside the new squad becomes its last starter."""
    rosters = project.all_rosters()
    if not rosters:
        return 0
    teams, links, formations = db.table('teams'), db.table('teamplayerlinks'), db.table('formations')
    count = 0
    for tid, rows in rosters.items():
        rows = [r for r in rows if not r.get('hidden')]  # hidden in this team: out of the patch, kept on the screen
        team_rows = teams.find(teamid=tid)
        if not team_rows:
            continue
        own = formations.find(teamid=tid)
        positions = [formations.get(own[0], f'position{i}') for i in range(STARTERS)] if own else list(range(STARTERS))
        rows = lineup(rows, positions)
        if len(rows) < STARTERS:
            raise BuildError('team_too_few_players', str(tid))
        model = next((r for r in links.records if links.get(r, 'teamid') == tid), links.records[0])
        keep = [i for i, r in enumerate(links.records) if links.get(r, 'teamid') != tid]
        raws = links.raw_records + [bytes(links.rec_size)] * (len(links.records) - len(links.raw_records))
        links.records, links.raw_records = [links.records[i] for i in keep], [raws[i] for i in keep]
        key = _next(links, 'artificialkey')
        for r in rows:
            new = list(model)
            for f in links.fields:  # the counters of a new link start at zero
                if f.type == 3 and f.name not in ('teamid', 'playerid', 'artificialkey', 'position', 'jerseynumber'):
                    links.set(new, f.name, max(0, f.rangelow))
            for column, value in (('teamid', tid), ('playerid', r['player']), ('artificialkey', key),
                                  ('position', r['slot']), ('jerseynumber', r.get('jersey') or 0),
                                  ('form', 3), ('prevform', 3)):
                if _has(links, column):
                    links.set(new, column, value)
            links.records.append(new)
            links.raw_records.append(bytes(links.rec_size))
            key += 1
        squad = {r['player'] for r in rows}
        starters = [r['player'] for r in rows if r['slot'] < BENCH]
        for column in ('captainid', *fifa14.TAKERS.values()):
            if _has(teams, column) and teams.get(team_rows[0], column) not in squad:
                teams.set(team_rows[0], column, starters[-1])
        count += 1
    return count


# ---- players ---------------------------------------------------------------------------------------------------

def add_created_players(db: Database, project: Project) -> int:
    """Rows of the players the user created: a copy of the row of the player each one starts from (a game player, or
    the model player) under the new id; names, values, face and teams come after (saved fields, write_rosters)."""
    created = project.created('player')
    if not created:
        return 0
    players = db.table('players')
    by_id = {players.get(r, 'playerid'): r for r in players.records}
    for pid in created:
        if pid in by_id:
            raise BuildError('player_id_taken', str(pid))
        template = project.player_source(pid) or fifa14.MODEL_PLAYER
        model = by_id.get(template) or by_id.get(fifa14.MODEL_PLAYER) or players.records[0]
        by_id[pid] = _clone(players, model, playerid=pid)
    return len(created)


def write_player_files(files: GameFiles, db: Database, project: Project, builder: 'PatchBuilder') -> dict:
    """The head of every player whose face the user chose (headclasscode 0 = his own face files, named after his id:
    copied from another game player or from the pack face kept in the project; 1 = the generic head of his look
    codes) and the photo of every player with a picture (heads/p<id>.dds). A part the chosen face does not bring is
    removed (PatchBuilder.remove), never left to the game's file of that id."""
    players = db.table('players')
    rows = {players.get(r, 'playerid'): r for r in players.records}
    has_class = _has(players, 'headclasscode')
    counts = {'faces': 0, 'photos': 0}
    template = None  # faceconv's template files, read once the first face needs converting
    for pid, values in project.all_fields('player').items():
        face, row = values.get('face'), rows.get(pid)
        if not face or row is None:
            continue
        if face['source'] == 'generic':
            if has_class:
                players.set(row, 'headclasscode', 1)
            continue
        if face['source'] == 'player':
            own = {kind: files.read(path.format(face['player'])) for kind, path in fifa14.PLAYER_FACE_FILES.items()}
        else:
            own = project.player_files(pid)
        own = {kind: data for kind, data in own.items() if data is not None and kind in fifa14.PLAYER_FACE_FILES}
        if not all(kind in own for kind in fifa14.FACE_REQUIRED):
            raise BuildError('player_face_missing', str(pid))
        if face['source'] != 'player' or face['player'] != pid:
            for kind, path in fifa14.PLAYER_FACE_FILES.items():
                if kind in own:
                    builder.put(path.format(pid), own[kind])
                else:  # never the part the game has under his id (another face's): the face goes without it
                    builder.remove(path.format(pid))
            if face['source'] != 'player' and faceconv.face_needs_conversion(own):
                if template is None:
                    template = _face_template(files)
                builder.later('face', builder.name('player', pid, project),
                              builder.key('face', ('faceconv',), pid, *[x for k in sorted(own) for x in (k, own[k])]),
                              functools.partial(_converted_face, template, pid, own))
        if has_class:
            players.set(row, 'headclasscode', 0)
        counts['faces'] += 1
    for pid in project.with_picture('player', 'photo'):
        if pid not in rows:
            continue
        png_data = project.picture('player', pid, 'photo')[0]
        builder.later('photo', builder.name('player', pid, project),
                      builder.key('photo', ('teamkits', 'images'), pid, png_data),
                      functools.partial(_photo_files, files, pid, png_data))
        counts['photos'] += 1
    return {k: v for k, v in counts.items() if v}


def _face_template(files: GameFiles) -> dict[str, bytes]:
    """The game's files of faceconv.TEMPLATE that pack faces are converted on."""
    template = faceconv.game_template(files)
    if template is None:
        raise BuildError('face_template_missing', str(faceconv.TEMPLATE))
    return template


def _converted_face(template: dict[str, bytes], pid: int, own: dict[str, bytes]) -> dict[str, bytes]:
    """{game path: bytes} of the meshes of a pack face converted into FIFA 14's format (faceconv); the textures and
    the parts it lacks were already put / removed by write_player_files."""
    try:
        converted = faceconv.convert_face(template, own)
    except faceconv.FaceFormatError as e:
        raise BuildError('player_face_format', str(pid)) from e
    return {fifa14.PLAYER_FACE_FILES[kind].format(pid): converted[kind] for kind in faceconv.MESHES if own.get(kind)}


def _photo_files(files: GameFiles, pid: int, png_data: bytes) -> dict[str, bytes]:
    model = files.read(fifa14.PHOTO.format(pid)) or files.read(fifa14.PHOTO.format(fifa14.MODEL_PLAYER))
    picture = images.fit(images.decode_png(png_data), fifa14.PHOTO_SIZE)
    return {fifa14.PHOTO.format(pid): teamkits.dds_like(model, picture) if model else images.dds(picture)}


def _picture(project: Project, kind: str, oid: int, slot: str) -> Image.Image | None:
    found = project.picture(kind, oid, slot)
    return images.decode_png(found[0]) if found else None


def _team_color(db: Database, project: Project, tid: int, n: int) -> list[int]:
    saved = project.fields('team', tid).get(f'teamcolor{n}')
    if saved:
        return list(saved)
    teams = db.table('teams')
    rows = teams.find(teamid=tid)
    return [teams.get(rows[0], f'teamcolor{n}{c}') for c in 'rgb'] if rows else [128, 128, 128]


def _renamed(name: str, old: int, new: int) -> str | None:
    """The file name of team `old` with the id of team `new`; None when the name is not one of `old`'s."""
    if not re.search(rf'(?:^|_|^l){old}(?=[_.])', name):
        return None
    return re.sub(rf'(?<!\d){old}(?!\d)', str(new), name, count=1)


def team_files(files: GameFiles, db: Database, project: Project, builder: 'PatchBuilder') -> dict:
    """Crest, kit and minikit files of the teams the user changed or created, and the model's other files (warm-up,
    banners, flags, adboards) for a created team; kit colors and collar go into its teamkits rows."""
    created = set(project.created('team'))
    all_kits = project.all_kits()
    teams = created | set(project.with_picture('team', 'crest')) | set(all_kits)
    teams = {t for t in teams if db.table('teams').find(teamid=t)}
    if not teams:
        return {}
    kits_table = db.table('teamkits')
    listed = [p for p in files.list('data/') if TEAM_COPIED_FILES.match(p) or TEAM_LOOKS.match(p)] if created else []
    counts = {'crests': 0, 'kits': 0, 'copied': 0}
    for tid in sorted(teams):
        team_name = builder.name('team', tid, project)
        template, copy = _team_source(project, tid) if tid in created else (tid, True)
        if tid in created:  # the model's files under the new id (and its crest and kits when the team is a copy)
            for path in listed:
                if TEAM_LOOKS.match(path) and not copy:
                    continue
                folder, name = path.rsplit('/', 1)
                new_name = _renamed(name, template, tid)
                if new_name:
                    builder.put(f'{folder}/{new_name}', files.read(path))
                    counts['copied'] += 1
        crest = _picture(project, 'team', tid, 'crest')
        if crest is None and tid in created and not copy:
            names = with_derived_names('team', project.names('team', tid))
            crest = teamkits.plain_crest(_shown_name(names, 'abbr3'), _team_color(db, project, tid, 1),
                                         _team_color(db, project, tid, 2))
        if crest is not None:
            builder.later('crest', team_name, builder.key('crest', ('teamkits',), tid, template, crest),
                          functools.partial(teamkits.crest_files, files, crest, tid, template))
            counts['crests'] += 1
        else:
            game_crest = files.read(teamkits.CREST_FILE.format('crest', template))
            crest = images.decode_dds(game_crest) if game_crest is not None else None
        configs = dict(all_kits.get(tid, {}))
        if tid in created and not copy:  # made from scratch: generic kits until the user picks others
            c1, c2 = _team_color(db, project, tid, 1), _team_color(db, project, tid, 2)
            defaults = {0: {'source': 'generic', 'model': teamkits.DEFAULT_MASKS[0], 'colors': [c1, c2]},
                        1: {'source': 'generic', 'model': teamkits.DEFAULT_MASKS[1], 'colors': [c2, c1]},
                        2: {'source': 'game', 'team': teamkits.GENERIC_GOALKEEPER, 'kind': 2}}
            for kind, default in defaults.items():
                own = configs.get(kind)
                if own is None or own.get('source') == 'keep':  # 'keep' = the default kit with the user's print
                    configs[kind] = {**default, **{k: v for k, v in (own or {}).items() if k != 'source'}}
        kit_rows = {kits_table.get(r, 'teamkittypetechid'): r for r in kits_table.records
                    if kits_table.get(r, 'teamtechid') == tid and kits_table.get(r, 'year') == 0}
        for kind, config in sorted(configs.items()):
            pics = {name: p for name in ('jersey', 'shorts')
                    if (p := _picture(project, 'team', tid, f'kit{kind}_{name}')) is not None}
            keep = config.get('source') == 'keep'  # only the name and numbers change
            if not keep:
                tint = config if config.get('colors') or 'jersey' not in pics else {
                    **config, 'colors': [list(pics['jersey'].convert('RGB').resize((1, 1)).getpixel((0, 0)))]}
                mini = _picture(project, 'team', tid, f'kit{kind}_mini')
                builder.later('kit', team_name,
                              builder.key('kit', ('teamkits',), tid, kind, template, config, tint, crest,
                                          sorted(pics), *[pics[n] for n in sorted(pics)], mini),
                              functools.partial(_kit_files, files, tid, kind, template, config, tint, crest, pics,
                                                mini))
            row = kit_rows.get(kind)
            if row is None and keep:
                continue  # nothing to print on: the team has no such kit
            if row is None:  # a kit type the team did not have
                model = kit_rows.get(0) or next((r for r in kits_table.records
                                                 if kits_table.get(r, 'teamtechid') == template), kits_table.records[0])
                row = _clone(kits_table, model, teamtechid=tid, teamkitid=_next(kits_table, 'teamkitid'),
                             teamkittypetechid=kind, year=0)
            for prefix, color in zip(('teamcolorprim', 'teamcolorsec'), config.get('colors') or []):
                for c, v in zip('rgb', color):
                    if _has(kits_table, f'{prefix}{c}'):
                        kits_table.set(row, f'{prefix}{c}', int(v))
            if config.get('collar') is not None and _has(kits_table, 'jerseycollargeometrytype'):
                kits_table.set(row, 'jerseycollargeometrytype', int(config['collar']))
            teamkits.apply_print(kits_table, row, config.get('print') or {})
            counts['kits'] += 1
    return counts


def _kit_files(files: GameFiles, tid: int, kind: int, template: int, config: dict, tint: dict,
               crest: Image.Image | None, pics: dict, mini: Image.Image | None) -> dict[str, bytes]:
    """The kit file and the minikit of one kit of a team."""
    return {teamkits.KIT_FILE.format(tid, kind): teamkits.kit_file(files, config, kind, template, crest, pics),
            teamkits.MINIKIT.format(kind, tid): teamkits.minikit(files, tint, kind, template, mini)}


def write_database(files: GameFiles, project: Project, builder: 'PatchBuilder') -> dict | None:
    """The database with the project's fields, created entities and league teams, loose (with its meta file)."""
    has_created = bool(project.created('country') or project.created('league') or project.created('team')
                       or project.created('player'))
    hiding = any(project.hidden_in_game(kind) for kind in ('country', 'league', 'team'))
    team_work = project.all_rosters() or project.all_kits() or project.with_picture('team', 'crest') \
        or project.with_picture('player', 'photo')
    if not any(project.all_fields(kind) for kind in ID_COLUMNS) and not has_created and not project.all_members() \
            and not hiding and not team_work:
        return None
    meta_raw, raw = files.read(fifa14.META), files.read(DATABASE)
    if meta_raw is None or raw is None:
        raise ValueError('database not found')
    db = Database(raw, t3db.load_meta(meta_raw))
    created = add_created(db, project)
    if new_teams := add_created_teams(db, project):
        created['team'] = new_teams
    if new_players := add_created_players(db, project):
        created['player'] = new_players
    result = apply_database(db, project)
    result['created'] = created
    for key, value in (('formations', write_formations(db, project)), ('rosters', write_rosters(db, project)),
                       ('team_files', team_files(files, db, project, builder)),
                       ('player_files', write_player_files(files, db, project, builder))):
        if value:
            result[key] = value
    result['league_links'] = write_members(db, project)
    visibility = write_visibility(db, project)
    if visibility:
        result['visibility'] = visibility
    builder.put(DATABASE, db.build())
    builder.put(fifa14.META, meta_raw)
    return result


def language_files(lang: str, base: bytes | None, upd: bytes | None, wanted: dict[str, str],
                   fill: dict[str, str]) -> dict[str, bytes]:
    """The changed language databases of one language (run in a worker process: top level, plain arguments).
    The base database gets every string (a new one with its hashid) and, for the texts it lacks, the "every
    language" value of an original (fill); the _upd one only overrides its own strings."""
    out = {}
    for name, raw in ((lang, base), (f'{lang}_upd', upd)):
        if raw is None:
            continue
        strings = LanguageStrings(raw)
        todo = wanted if name == lang else {k: v for k, v in wanted.items() if strings.get(k) is not None}
        if name == lang:
            todo = {**{k: v for k, v in fill.items() if strings.get(k) is None}, **todo}
        changed = False
        for sid, text in todo.items():
            if strings.get(sid) != text:
                strings.set(sid, text)
                changed = True
        if changed:
            out[f'data/loc/{name}.db'] = strings.build()
    return out


def build(files: GameFiles, project: Project, out_dir: str, progress=None, worker_count: int | None = None,
          cache: buildcache.BuildCache | None = None, cancel=None, log=None, name_of=None) -> dict:
    """The patch of the project over the clean game.
    progress(step, done, total, kind=None, name=None): step of BUILD_STEPS; the 'images' step also says what it waits
    for (kind: kit, crest, photo, league, flag; name: the team, player...). worker_count: processes for the language
    texts and threads for the pictures (None = workers.plan(), the machine's defaults). cache: a
    buildcache.BuildCache whose folder keeps texts and pictures between builds (None = no cache); entries this build
    did not use are deleted at the end. cancel: a threading.Event; once set, the build stops (BuildCancelled) at the
    next check and leaves out_dir as it was. log(line): what the build is doing. name_of(kind, id): shown names."""
    step = progress or (lambda *_, **__: None)
    say = log or (lambda _line: None)

    def check():
        if cancel is not None and cancel.is_set():
            raise BuildCancelled()

    worker_count = workers.plan() if worker_count is None else max(1, int(worker_count))
    if cache is not None and not cache.folder:
        cache = None
    project = project.visible()  # what is left out of the patch is not built
    step('database', 0, 1)
    pool = ThreadPoolExecutor(max_workers=worker_count)
    builder = PatchBuilder(files, pool, cache, name_of)
    if cache is not None:
        builder.game_key = buildcache.game_fingerprint(files)
    say(f'{worker_count} worker(s)' + (', cache on' if cache is not None else ', no cache'))

    # ---- the language texts first: they run in worker processes while the database is edited
    edits = language_edits(project)
    languages = sorted({os.path.basename(p)[:-3] for p in files.list('data/loc/') if p.endswith('.db')})
    base_languages = [n for n in languages if not n.endswith('_upd')]
    text_version = buildcache.code_version('dbedit') + buildcache.function_source(language_files)
    texts = []  # (lang, files made or a workers.Task)
    to_make = []
    for lang in base_languages:
        wanted = {**edits.get(DEFAULT_LANG, {}), **edits.get(lang, {})}
        fill = {k: v for k, v in edits.get(FILL_ONLY, {}).items() if k not in wanted}
        if not wanted and not fill:
            continue
        args = (lang, files.read(f'data/loc/{lang}.db'), files.read(f'data/loc/{lang}_upd.db'), wanted, fill)
        k = buildcache.key('language', text_version, *args) if cache is not None else None
        found = cache.get(k) if k is not None else None
        texts.append([lang, k, found])
        if found is None:
            to_make.append((texts[-1], args))
    procs = workers.Pool(min(worker_count, len(to_make)) if len(to_make) > 1 else 1, log_fn=say)
    try:
        for entry, args in to_make:
            task = entry[2] = procs.submit(language_files, *args)
            if entry[1] is not None:  # kept as soon as its worker ends, even if the build stops later
                task.on_success(functools.partial(cache.put, entry[1]))
        check()

        # ---- database (its pictures go to the thread pool)
        database = write_database(files, project, builder)
        step('database', 1, 1)
        check()
        pictures = created_pictures(files, project, builder)

        # ---- pictures
        step('images', 0, len(builder.jobs))
        builder.collect(step, check)
        step('images', 1, 1)
        check()

        # ---- texts
        total = len(base_languages)
        skipped = total - len(texts)
        for k, entry in enumerate(texts):
            lang, key, made = entry
            cached = not isinstance(made, workers.Task)
            if isinstance(made, workers.Task):
                while not made.finished():
                    check()
                    step('texts', skipped + k, total, kind='language', name=lang)
                    if made.future is None:
                        break  # runs here, in result()
                    made.wait(0.5)
                check()
                step('texts', skipped + k, total, kind='language', name=lang)
                made = made.result()
                if key is not None:  # already there when its worker ended (put keeps the first)
                    cache.put(key, made)
            builder.put_all(made, cached)
        step('texts', total, total)
        check()
    finally:
        pool.shutdown(cancel_futures=True)
        procs.shutdown()  # waits for the languages being made: they still go to the cache
    if cache is not None:
        removed = cache.prune()
        say(f'cache: {cache.hits} reused, {cache.misses} made, {removed} old entries removed')

    # ---- files
    step('files', 0, 1)
    summary = builder.write(out_dir, step)
    summary['missing_strings'] = []
    summary['database'] = database
    summary['pictures'] = pictures
    return summary
