"""Builds the patch: the changed game files, laid out like the game folder, ready to be installed.

How each changed file reaches the game:
  - an entry of an archive with a .bh index (data0..7.big, patch.big): written loose at its game path, and every .bh
    whose archive lists it gets that record's hash words zeroed, so the game opens the loose file;
  - an entry of data/loc/locale.big (no .bh): the whole archive is written again with the new entry.
The patch never holds the big archives themselves.
"""
import os
import shutil

from . import bh, fifa14
from .big import BigArchive, normalize, rebuild
from .dbedit import LanguageStrings
from .gamefs import GameFiles
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


def team_language_edits(project: Project) -> dict[str, dict[str, str]]:
    """{language or '*': {stringid: text}} of every team name saved in the project."""
    out: dict[str, dict[str, str]] = {}
    for team_id, names in project.all_team_names().items():
        for key, by_lang in names.items():
            prefix = fifa14.TEAM_NAME_STRINGS.get(key)
            if not prefix:
                continue
            for lang, text in by_lang.items():
                out.setdefault(lang, {})[f'{prefix}{team_id}'] = text
    return out


def build(files: GameFiles, project: Project, out_dir: str, progress=None) -> dict:
    """The patch of the project over the clean game."""
    builder = PatchBuilder(files)
    edits = team_language_edits(project)
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
            # only strings the game already has: a new string needs a key (hashid) this app cannot make yet
            todo = {k: v for k, v in wanted.items() if strings.get(k) is not None}
            if name == lang:
                missing.update(k for k in wanted if k not in todo)
            changed = False
            for sid, text in todo.items():
                if strings.get(sid) != text:
                    strings.set(sid, text)
                    changed = True
            if changed:
                builder.put(path, strings.build())
    summary = builder.write(out_dir)
    summary['missing_strings'] = sorted(missing)
    if progress:
        progress('done', 1.0)
    return summary
