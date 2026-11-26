"""Installing a built patch into the game folder and taking it out again.

A patch is a folder that mirrors the game folder: loose files (new or in place of an archive entry), the .bh indexes
with the hash words of the replaced entries zeroed, and whole files that replace the game's (e.g.
data/loc/locale.big). Installing:
  1. checks the patch and the free space on the game's drive;
  2. puts back the files of the patch installed before that this one no longer has;
  3. skips the files already installed with the same content (the build records each file's SHA-1); for each other
     one, moves the game file it replaces into the backup folder (inside the game folder, so it is a rename on the
     same drive, not a copy; a file the previous patch already replaced keeps its backup) and copies the patch file
     over the game, hashing it on the way;
  4. writes the install manifest (what was added, what was replaced and where its backup is, and each file's hash
     and size/date, so checking the game later only hashes the files whose size or date changed).
The manifest is written before each batch of files (marked 'complete': False until the end), so an interrupted
install can still be taken out: a replaced file whose backup is missing was never touched.
Uninstalling deletes the added files, moves the backups back and deletes the manifest and the backup folder. The
manifest lives in the game folder, so a patch can be taken out even after the app was reinstalled.

progress(phase, done=0, total=0, name=None, bytes_done=0, bytes_total=0, kept=0), phases in order: 'checking'
(listing the patch, free space), 'restoring' (putting back what left the patch; uninstalling), 'copying' (files
done/total, the one being copied, bytes copied of those to copy; kept: files already installed as they are).
"""
import datetime
import hashlib
import json
import os
import shutil

from .big import normalize

MANIFEST = 'fifa14-patch-studio.install.json'
BACKUP_DIR = 'fifa14-patch-studio-backup'
APP_ID = 'fifa14-patch-studio'
CHUNK = 4 << 20
BATCH_FILES = 500  # the manifest is written before each batch, not after each file (30 000 rewrites of a big JSON)
BATCH_BYTES = 512 << 20
SPACE_MARGIN = 64 << 20


class InstallError(Exception):
    pass


def _sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _stamp(path: str) -> list[int]:
    st = os.stat(path)
    return [st.st_size, st.st_mtime_ns]


def _files(folder: str) -> list[str]:
    """Game paths (relative, '/' separators, original case) of every file under folder."""
    out = []
    for base, _, names in os.walk(folder):
        for n in names:
            out.append(os.path.relpath(os.path.join(base, n), folder).replace(os.sep, '/'))
    return sorted(out)


def _disk(game_dir: str, rel: str) -> str:
    return os.path.join(game_dir, *rel.split('/'))


def _copy_hashed(src: str, dst: str, on_bytes) -> str:
    """Copies src to dst in one pass, returning the SHA-1 of what was written; on_bytes(n) after each block."""
    h = hashlib.sha1()
    with open(src, 'rb') as fin, open(dst, 'wb') as fout:
        while block := fin.read(CHUNK):
            fout.write(block)
            h.update(block)
            on_bytes(len(block))
    return h.hexdigest()


def _silent(*_args, **_kwargs) -> None:
    pass


def read_manifest(game_dir: str) -> dict | None:
    try:
        with open(os.path.join(game_dir, MANIFEST), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get('app') == APP_ID else None


def originals_view(game_dir: str) -> tuple[set[str], dict[str, str]]:
    """(loose files added by the installed patch, {replaced game path: backup file}) for reading the clean game."""
    manifest = read_manifest(game_dir)
    if not manifest:
        return set(), {}
    added = {normalize(p) for p in manifest.get('added', [])}
    replaced = {normalize(p): _disk(game_dir, f'{BACKUP_DIR}/{p}') for p in manifest.get('replaced', [])}
    if manifest.get('complete') is False:  # an interrupted install: only the files already moved have a backup
        replaced = {k: v for k, v in replaced.items() if os.path.isfile(v)}
    return added | set(replaced), replaced


def _batches(files: list[str], sizes: dict[str, int]):
    batch, size = [], 0
    for rel in files:
        batch.append(rel)
        size += sizes[rel]
        if len(batch) >= BATCH_FILES or size >= BATCH_BYTES:
            yield batch
            batch, size = [], 0
    if batch:
        yield batch


def install(patch_dir: str, game_dir: str, version: str = '', progress=None, known: dict[str, str] | None = None) -> dict:
    """Installs the patch folder into the game folder; returns the manifest (its 'summary': files copied, kept as
    they were and put back). known: {patch file: SHA-1} the build recorded; a file whose hash is the one already
    installed (and untouched since) is not copied again."""
    report = progress or _silent
    report('checking')
    if not os.path.isdir(patch_dir):
        raise InstallError('patch folder not found')
    files = _files(patch_dir)
    if not files:
        raise InstallError('the patch is empty')
    sizes = {rel: os.path.getsize(_disk(patch_dir, rel)) for rel in files}
    previous = read_manifest(game_dir)
    if previous and previous.get('complete') is False:
        uninstall(game_dir, progress)  # an interrupted install: start from the clean game
        previous = None
    prev = previous or {}
    prev_added, prev_replaced = set(prev.get('added', [])), set(prev.get('replaced', []))
    prev_hashes, prev_stamps = prev.get('hashes', {}), prev.get('stamps', {})
    wanted = set(files)
    known = known or {}

    def unchanged(rel):  # installed by the previous patch, same content and nothing touched it since
        digest = known.get(rel)
        if not digest or prev_hashes.get(rel) != digest or rel not in prev_stamps:
            return False
        try:
            return _stamp(_disk(game_dir, rel)) == prev_stamps[rel]
        except OSError:
            return False
    keep = {rel for rel in files if unchanged(rel)}
    to_copy = [rel for rel in files if rel not in keep]
    leaving = sorted((prev_added | prev_replaced) - wanted)
    _check_space(game_dir, to_copy, sizes, prev_added - wanted,
                 [rel for rel in to_copy if rel in prev_added or rel in prev_replaced])

    backup_root = os.path.join(game_dir, BACKUP_DIR)
    added = [rel for rel in files if rel in prev_added]
    replaced = [rel for rel in files if rel in prev_replaced]
    manifest = {'app': APP_ID, 'version': version, 'installed_at': datetime.datetime.now().isoformat(timespec='seconds'),
                'complete': False, 'added': added, 'replaced': replaced,
                'hashes': {rel: prev_hashes[rel] for rel in keep}, 'stamps': {rel: prev_stamps[rel] for rel in keep}}
    try:
        # the files of the previous patch this one no longer has go back to the original
        if leaving:
            _write_manifest(game_dir, {**prev, 'complete': False})  # a file already put back has no backup
            for i, rel in enumerate(leaving):
                report('restoring', i, len(leaving), rel)
                _put_back(game_dir, backup_root, rel, rel in prev_added, tolerant=True)
            report('restoring', len(leaving), len(leaving))
            _remove_empty_folders({os.path.dirname(_disk(game_dir, rel)) for rel in leaving}, game_dir)

        total_bytes = sum(sizes[rel] for rel in to_copy)
        copied = [0]

        def on_bytes(n):
            copied[0] += n
        done = len(keep)
        for batch in _batches(to_copy, sizes):
            fresh = {rel: os.path.isfile(_disk(game_dir, rel)) for rel in batch
                     if rel not in prev_added and rel not in prev_replaced}
            for rel, exists in fresh.items():
                (replaced if exists else added).append(rel)
            _write_manifest(game_dir, manifest)  # before touching the batch: an interruption can still be undone
            for rel in batch:
                target = _disk(game_dir, rel)
                report('copying', done, len(files), rel, copied[0], total_bytes, kept=len(keep))
                if fresh.get(rel):  # a game file this patch replaces for the first time: kept as the backup
                    backup = _disk(backup_root, rel)
                    os.makedirs(os.path.dirname(backup), exist_ok=True)
                    os.replace(target, backup)  # same drive: a rename, not a copy
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                manifest['hashes'][rel] = _copy_hashed(_disk(patch_dir, rel), target, on_bytes)
                manifest['stamps'][rel] = _stamp(target)
                done += 1
        manifest['complete'] = True
        manifest['summary'] = {'copied': len(to_copy), 'kept': len(keep), 'restored': len(leaving)}
        _write_manifest(game_dir, manifest)
        report('copying', len(files), len(files), None, copied[0], total_bytes, kept=len(keep))
    except OSError as e:
        raise InstallError(str(e)) from e
    return manifest


def _put_back(game_dir: str, backup_root: str, rel: str, was_added: bool, tolerant: bool) -> None:
    """Takes one file of the patch out: an added file is deleted, a replaced one gets its backup moved back. A
    missing backup is an error unless tolerant (an interrupted install never moved that file)."""
    path = _disk(game_dir, rel)
    if was_added:
        if os.path.isfile(path):
            os.remove(path)
        return
    backup = _disk(backup_root, rel)
    if not os.path.isfile(backup):
        if tolerant:
            return
        raise InstallError(f'backup missing: {rel}')
    os.replace(backup, path)


def _check_space(game_dir: str, to_copy: list[str], sizes: dict[str, int], leaving_added: set[str],
                 overwritten: list[str]) -> None:
    """The files to copy must fit on the game's drive. Freed first: the added files of the previous patch that
    leave (a replaced one gets its original back) and the previous copies of the files copied again."""
    try:
        free = shutil.disk_usage(game_dir).free
    except OSError:
        return
    freed = 0
    for rel in (*leaving_added, *overwritten):
        try:
            freed += os.path.getsize(_disk(game_dir, rel))
        except OSError:
            pass
    needed = sum(sizes[rel] for rel in to_copy)
    if free + freed < needed + SPACE_MARGIN:
        raise InstallError(f'not enough free space on the game drive: {needed >> 20} MB needed, '
                           f'{(free + freed) >> 20} MB free')


def _write_manifest(game_dir: str, manifest: dict) -> None:
    path = os.path.join(game_dir, MANIFEST)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)


def uninstall(game_dir: str, progress=None) -> dict | None:
    """Takes the installed patch out; returns its manifest, or None when there was none."""
    manifest = read_manifest(game_dir)
    if not manifest:
        return None
    report = progress or _silent
    interrupted = manifest.get('complete') is False  # older manifests have no 'complete': written file by file
    backup_root = os.path.join(game_dir, BACKUP_DIR)
    added, replaced = manifest.get('added', []), manifest.get('replaced', [])
    total = len(added) + len(replaced)
    try:
        for i, rel in enumerate(added):
            if i % 50 == 0:
                report('restoring', i, total, rel)
            _put_back(game_dir, backup_root, rel, True, interrupted)
        for i, rel in enumerate(replaced, len(added)):
            report('restoring', i, total, rel)
            _put_back(game_dir, backup_root, rel, False, interrupted)
        report('restoring', total, total)
        _remove_empty_folders({os.path.dirname(_disk(game_dir, rel)) for rel in added}, game_dir)
        shutil.rmtree(backup_root, ignore_errors=True)
        os.remove(os.path.join(game_dir, MANIFEST))
    except OSError as e:
        raise InstallError(str(e)) from e
    return manifest


def changed_after_install(game_dir: str) -> list[str]:
    """Files of the installed patch that something else changed or removed since. A file with the size and date the
    install recorded is taken as unchanged (hashing tens of GB at every check takes minutes); manifests without
    them (older versions) hash every file."""
    manifest = read_manifest(game_dir) or {}
    stamps = manifest.get('stamps', {})
    out = []
    for rel, digest in manifest.get('hashes', {}).items():
        path = _disk(game_dir, rel)
        try:
            stamp = _stamp(path)
        except OSError:
            out.append(rel)
            continue
        if stamps.get(rel) == stamp:
            continue
        if _sha1(path) != digest:
            out.append(rel)
    return out


def _remove_empty_folders(folders: set[str], stop: str) -> None:
    for folder in sorted(folders, key=len, reverse=True):
        _remove_empty_parents(folder, stop)


def _remove_empty_parents(folder: str, stop: str) -> None:
    stop = os.path.abspath(stop)
    folder = os.path.abspath(folder)
    while folder.startswith(stop) and folder != stop:
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)
