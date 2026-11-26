"""The project's files on disk, next to project.sqlite in project_files/ (the Street Studio keeps them the same way,
beside its database.json): the database keeps only the relative path, size and digest of each one.

A file is named after the SHA-1 of its bytes (`<folder>/<digest><ext>`), so:
  - equal files are kept once (two stadiums with the same texture share one file);
  - a file is never written over: changing one entity's file writes a new file and points only that entity's row to
    it, the others that had the same bytes keep the old one untouched;
  - a file is removed only when no row points to it any more (`release`, `prune`).
"""
import hashlib
import os
import threading
import time
import uuid

# folder of each kind of file, inside the project folder
PICTURES = 'images'
FACES = 'faces'
STADIUMS = 'stadiums'
EQUIPMENT = {'boot': 'boots', 'glove': 'gloves', 'ball': 'balls'}
FOLDERS = (PICTURES, FACES, STADIUMS, *EQUIPMENT.values())
# the tables whose rows point to files (column `file`)
FILE_TABLES = ('pictures', 'player_files', 'equipment_files', 'stadium_scene')

_lock = threading.Lock()  # a file being released is not taken by a put at the same time


def digest(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


class FileStore:
    def __init__(self, root: str):
        self.root = root

    def path(self, rel: str) -> str:
        return os.path.join(self.root, *rel.split('/'))

    def put(self, folder: str, data: bytes, ext: str = '') -> tuple[str, int, str]:
        """Keeps the bytes; (relative path, size, digest). Equal bytes give the same file (written once)."""
        data = bytes(data)
        d = digest(data)
        rel = f'{folder}/{d}{ext.lower()}'
        full = self.path(rel)
        with _lock:
            if not os.path.isfile(full):
                os.makedirs(os.path.dirname(full), exist_ok=True)
                tmp = f'{full}.{uuid.uuid4().hex}.tmp'  # a half-written file never takes the real name
                try:
                    with open(tmp, 'wb') as f:
                        f.write(data)
                    os.replace(tmp, full)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
            else:
                os.utime(full)  # just taken: prune leaves it alone while its row is being written
        return rel, len(data), d

    def read(self, rel: str) -> bytes | None:
        try:
            with open(self.path(rel), 'rb') as f:
                return f.read()
        except OSError:
            return None

    def release(self, con, files) -> None:
        """Removes the files no row points to any more (`files` = the ones some rows just left)."""
        with _lock:
            for rel in set(f for f in files if f):
                if not any(con.execute(f'SELECT 1 FROM {t} WHERE file = ? LIMIT 1', (rel,)).fetchone()
                           for t in FILE_TABLES):
                    try:
                        os.remove(self.path(rel))
                    except OSError:
                        pass

    def prune(self, con, min_age: float = 60.0) -> int:
        """Removes every file of the folders no row points to (left by a cancelled import, say); a file younger than
        `min_age` seconds is kept (its row may not be committed yet). How many were removed."""
        used = set()
        for t in FILE_TABLES:
            used.update(r[0] for r in con.execute(f'SELECT file FROM {t}'))
        now, removed = time.time(), 0
        with _lock:
            for folder in FOLDERS:
                base = os.path.join(self.root, folder)
                if not os.path.isdir(base):
                    continue
                for name in os.listdir(base):
                    full = os.path.join(base, name)
                    if f'{folder}/{name}' in used or not os.path.isfile(full):
                        continue
                    try:
                        if now - os.path.getmtime(full) >= min_age:
                            os.remove(full)
                            removed += 1
                    except OSError:
                        pass
        return removed
