"""The files of a FIFA PC installation as the game sees them: loose files under the game folder first, then the BIG
archives (patch.big before the others, higher numbers first). Read-only: nothing here ever writes to the game folder.

To read the clean game while a patch of this app is installed, `ignore` lists the loose files the patch added and
`substitutes` points the files the patch replaced ({game path: backup file}) to the backups of the originals.

Paths are game paths: relative to the game folder (the one with the .big files), lower case, '/' separators, e.g.
'data/db/fifa_ng_db.db'.
"""
import os
import re

from . import chunk
from .big import BigArchive, BigError, normalize

DATABASE = 'data/db/fifa_ng_db.db'


def _archive_order(name: str):
    """patch.big first, then dataN.big with the highest N first, then the rest by name."""
    low = name.lower()
    if low == 'patch.big':
        return (0, 0, low)
    m = re.fullmatch(r'data(\d+)\.big', low)
    if m:
        return (1, -int(m.group(1)), low)
    return (2, 0, low)


def find_game_dir(path: str) -> str:
    """The game folder (the one holding 'data' and/or the .big archives) from the folder the user picked: the
    installation root, its 'Game' folder or the game folder itself."""
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(path)
    for candidate in (path, os.path.join(path, 'Game')):
        if not os.path.isdir(candidate):
            continue
        has_db = os.path.isfile(os.path.join(candidate, 'data', 'db', 'fifa_ng_db.db'))
        has_big = any(n.lower().endswith('.big') for n in os.listdir(candidate))
        if has_db or has_big:
            return os.path.abspath(candidate)
    raise FileNotFoundError(path)


class GameFiles:
    def __init__(self, root: str, ignore=(), substitutes: dict[str, str] | None = None):
        self.root = find_game_dir(root)
        self._ignore = {normalize(p) for p in ignore}
        self._substitutes = {normalize(k): v for k, v in (substitutes or {}).items()}
        self._loose = self._index_loose()
        self.archives: list[BigArchive] = []
        self.skipped: list[str] = []  # archives that could not be read
        for path in self._archive_paths():
            try:
                self.archives.append(BigArchive(path))
            except (BigError, OSError) as e:
                self.skipped.append(f'{os.path.basename(path)}: {e}')

    def _index_loose(self) -> dict[str, str]:
        """game path -> file on disk, for every loose file under data/."""
        out = {}
        data = os.path.join(self.root, 'data')
        for folder, _, files in os.walk(data):
            for name in files:
                full = os.path.join(folder, name)
                key = normalize(os.path.relpath(full, self.root))
                if key not in self._ignore:
                    out[key] = full
        out.update((k, v) for k, v in self._substitutes.items() if k.startswith('data/'))
        return out

    def _archive_paths(self) -> list[str]:
        found = [os.path.join(self.root, n) for n in os.listdir(self.root) if n.lower().endswith('.big')]
        found.sort(key=lambda p: _archive_order(os.path.basename(p)))
        # archives inside data/ (e.g. the language archive data/loc/locale.big) come after the root ones
        nested = sorted(p for k, p in self._loose.items() if k.endswith('.big'))
        return found + nested

    def where(self, path: str) -> str | None:
        """'loose' or the archive name that provides `path`, or None."""
        key = normalize(path)
        if key in self._loose:
            return 'loose'
        for archive in self.archives:
            if key in archive.entries:
                return archive.name
        return None

    def exists(self, path: str) -> bool:
        return self.where(path) is not None

    def read(self, path: str) -> bytes | None:
        """The file as the game reads it (chunked containers unpacked), or None when no source has it.
        Raises chunk.ChunkError for a damaged container."""
        key = normalize(path)
        loose = self._loose.get(key)
        if loose:
            with open(loose, 'rb') as f:
                data = f.read()
        else:
            data = None
            for archive in self.archives:
                data = archive.read(key)
                if data is not None:
                    break
            if data is None:
                return None
        return chunk.decode(data)

    def list(self, prefix: str) -> list[str]:
        """Every game path that starts with `prefix` (loose and archived, no duplicates)."""
        prefix = normalize(prefix)
        out = {k for k in self._loose if k.startswith(prefix)}
        for archive in self.archives:
            out.update(k for k in archive.entries if k.startswith(prefix))
        return sorted(out)
