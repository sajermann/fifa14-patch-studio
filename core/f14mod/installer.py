"""Installing a built patch into the game folder and taking it out again.

A patch is a folder that mirrors the game folder: loose files (new or in place of an archive entry), the .bh indexes
with the hash words of the replaced entries zeroed, and whole files that replace the game's (e.g.
data/loc/locale.big). Installing:
  1. takes out the patch installed before, if any (the game is clean again);
  2. copies every game file the patch replaces into the backup folder (inside the game folder);
  3. copies the patch over the game;
  4. writes the install manifest (what was added, what was replaced and where its backup is).
Uninstalling deletes the added files, puts the backups back and deletes the manifest and the backup folder. The
manifest lives in the game folder, so a patch can be taken out even after the app was reinstalled.
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


class InstallError(Exception):
    pass


def _sha1(path: str) -> str:
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _files(folder: str) -> list[str]:
    """Game paths (relative, '/' separators, original case) of every file under folder."""
    out = []
    for base, _, names in os.walk(folder):
        for n in names:
            out.append(os.path.relpath(os.path.join(base, n), folder).replace(os.sep, '/'))
    return sorted(out)


def _disk(game_dir: str, rel: str) -> str:
    return os.path.join(game_dir, *rel.split('/'))


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
    return added | set(replaced), replaced


def install(patch_dir: str, game_dir: str, version: str = '', progress=None) -> dict:
    """Installs the patch folder into the game folder; returns the manifest."""
    if not os.path.isdir(patch_dir):
        raise InstallError('patch folder not found')
    if read_manifest(game_dir):
        uninstall(game_dir)
    files = _files(patch_dir)
    if not files:
        raise InstallError('the patch is empty')
    backup_root = os.path.join(game_dir, BACKUP_DIR)
    added, replaced = [], []
    manifest = {'app': APP_ID, 'version': version, 'installed_at': datetime.datetime.now().isoformat(timespec='seconds'),
                'added': added, 'replaced': replaced, 'hashes': {}}
    try:
        for i, rel in enumerate(files):
            target = _disk(game_dir, rel)
            if os.path.isfile(target):
                backup = _disk(backup_root, rel)
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copy2(target, backup)
                replaced.append(rel)
            else:
                added.append(rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copyfile(_disk(patch_dir, rel), target)
            manifest['hashes'][rel] = _sha1(target)
            _write_manifest(game_dir, manifest)  # kept current: an interrupted install can still be taken out
            if progress:
                progress(i + 1, len(files))
    except OSError as e:
        raise InstallError(str(e)) from e
    return manifest


def _write_manifest(game_dir: str, manifest: dict) -> None:
    path = os.path.join(game_dir, MANIFEST)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def uninstall(game_dir: str) -> dict | None:
    """Takes the installed patch out; returns its manifest, or None when there was none."""
    manifest = read_manifest(game_dir)
    if not manifest:
        return None
    backup_root = os.path.join(game_dir, BACKUP_DIR)
    try:
        for rel in manifest.get('added', []):
            path = _disk(game_dir, rel)
            if os.path.isfile(path):
                os.remove(path)
            _remove_empty_parents(os.path.dirname(path), game_dir)
        for rel in manifest.get('replaced', []):
            backup = _disk(backup_root, rel)
            if not os.path.isfile(backup):
                raise InstallError(f'backup missing: {rel}')
            shutil.copy2(backup, _disk(game_dir, rel))
        shutil.rmtree(backup_root, ignore_errors=True)
        os.remove(os.path.join(game_dir, MANIFEST))
    except OSError as e:
        raise InstallError(str(e)) from e
    return manifest


def changed_after_install(game_dir: str) -> list[str]:
    """Files of the installed patch that something else changed or removed since."""
    manifest = read_manifest(game_dir) or {}
    out = []
    for rel, digest in manifest.get('hashes', {}).items():
        path = _disk(game_dir, rel)
        if not os.path.isfile(path) or _sha1(path) != digest:
            out.append(rel)
    return out


def _remove_empty_parents(folder: str, stop: str) -> None:
    stop = os.path.abspath(stop)
    folder = os.path.abspath(folder)
    while folder.startswith(stop) and folder != stop:
        try:
            os.rmdir(folder)
        except OSError:
            return
        folder = os.path.dirname(folder)
