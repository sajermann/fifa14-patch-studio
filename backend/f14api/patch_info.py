"""Which project the built patch came from, like the Street Studio's patch.json: the interface says "patch up to date"
or "changes not built yet" and asks before building the same project again.

The record lives next to the patch folder (patch.json in the data folder), never inside it: the patch folder is what
gets installed. The project's hash is the SHA-256 of its file (without SQLite's change counters), kept while its size and date stay the same (the status
is asked often, the file only changes when the user saves).
"""
import datetime
import hashlib
import json
import logging
import os
import threading

from . import settings

log = logging.getLogger('f14api')

_lock = threading.Lock()
_hash_of: dict = {}  # path -> ((size, mtime_ns), sha256)


def record_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(settings.PATCH_DIR)), 'patch.json')


def project_hash(path: str) -> str | None:
    """SHA-256 of the project file (None when it cannot be read)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    stamp = (st.st_size, st.st_mtime_ns)
    with _lock:
        known = _hash_of.get(path)
        if known and known[0] == stamp:
            return known[1]
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            header = bytearray(f.read(100))
            # SQLite's change counters (offsets 24 and 92) move on every write, even one that changes nothing
            header[24:28] = header[92:96] = bytes(4)
            h.update(header)
            for block in iter(lambda: f.read(1 << 20), b''):
                h.update(block)
    except OSError:
        return None
    with _lock:
        _hash_of[path] = (stamp, h.hexdigest())
    return h.hexdigest()


def patch_files(patch_dir: str) -> list[str]:
    """['data/db/fifa_ng_db.db', 'patch.bh', ...]: what the patch copies over the game folder."""
    return sorted(os.path.relpath(os.path.join(root, n), patch_dir).replace(os.sep, '/')
                  for root, _, names in os.walk(patch_dir) for n in names)


def hashes_path() -> str:
    """The SHA-1 of each file of the built patch (its own file: patch.json is read at every status call)."""
    return os.path.join(os.path.dirname(os.path.abspath(settings.PATCH_DIR)), 'patch.hashes.json')


def write(patch_dir: str, built_from: str | None, hashes: dict[str, str] | None = None) -> None:
    """Records the patch just built (built_from: the project's hash when the build started; hashes: {file: SHA-1}
    of what the build wrote, kept with each file's size and date so the install can trust them)."""
    info = {'built_at': datetime.datetime.now().isoformat(timespec='seconds'), 'project_hash': built_from,
            'files': patch_files(patch_dir)}
    known = {}
    for rel, digest in (hashes or {}).items():
        try:
            st = os.stat(os.path.join(patch_dir, *rel.split('/')))
        except OSError:
            continue
        known[rel] = [st.st_size, st.st_mtime_ns, digest]
    _write_json(hashes_path(), known)
    _write_json(record_path(), info, indent=2)


def known_hashes(patch_dir: str) -> dict[str, str]:
    """{file: SHA-1} of the built patch's files still as the build wrote them (same size and date); files changed
    since, or a patch built by an older version, are left out (the install copies those)."""
    try:
        with open(hashes_path(), encoding='utf-8') as f:
            recorded = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for rel, entry in recorded.items() if isinstance(recorded, dict) else ():
        try:
            size, mtime, digest = entry
            st = os.stat(os.path.join(patch_dir, *rel.split('/')))
        except (OSError, ValueError, TypeError):
            continue
        if [st.st_size, st.st_mtime_ns] == [size, mtime]:
            out[rel] = digest
    return out


def _write_json(path: str, data, indent=None) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, separators=None if indent else (',', ':'))
    os.replace(tmp, path)


def status(patch_dir: str, project_path: str) -> dict:
    """Whether a patch was built and from the saved project. Never fails: a patch without a record (built by an
    older version) or a record that cannot be read count as "not up to date"."""
    if not os.path.isdir(patch_dir) or not os.listdir(patch_dir):
        return {'built': False, 'up_to_date': False}
    try:
        with open(record_path(), encoding='utf-8') as f:
            info = json.load(f)
        built_at, files, built_from = info['built_at'], info['files'], info.get('project_hash')
    except FileNotFoundError:
        return {'built': True, 'up_to_date': False}
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.warning('patch record %s could not be read (%s: %s): build the patch again', record_path(),
                    type(e).__name__, e)
        return {'built': True, 'up_to_date': False}
    current = project_hash(project_path)
    return {'built': True, 'built_at': built_at, 'files': files,
            'up_to_date': current is not None and built_from == current}
