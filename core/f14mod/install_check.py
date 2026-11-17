"""Is this folder a FIFA 14 (PC) installation the app can patch, and is it clean?

The app always builds its patch over the clean game, so it needs the game as it was installed: every archive with its
.bh index, no entry redirected to a loose file and no loose file in place of an archive entry. What this app installed
itself (its install manifest) does not count as a change: the app reads the originals through the backups.

Result: {'state': 'not_found' | 'invalid' | 'modified' | 'clean' | 'patched', 'game_dir', 'issues': [{code, detail}]}
  - not_found: no game in the folder;
  - invalid: a required file is missing or cannot be read;
  - modified: another tool changed the game (the app cannot know the originals);
  - clean / patched: ready (patched = clean plus a patch of this app).
"""
import os

from . import bh, installer
from .big import BigArchive, BigError, normalize
from .gamefs import find_game_dir

EXECUTABLE = 'fifa14.exe'
REQUIRED_ARCHIVES = ('data0', 'data1', 'data2', 'data3', 'data5', 'data6', 'data7', 'patch')
LOCALE = 'data/loc/locale.big'


def _issue(code: str, detail: str = '') -> dict:
    return {'code': code, 'detail': detail}


def check(path: str) -> dict:
    try:
        game_dir = find_game_dir(path)
    except FileNotFoundError:
        return {'state': 'not_found', 'game_dir': None, 'issues': [_issue('game_not_found', path or '')]}
    issues: list[dict] = []
    if not os.path.isfile(os.path.join(game_dir, EXECUTABLE)):
        issues.append(_issue('missing_file', EXECUTABLE))
    manifest = installer.read_manifest(game_dir)
    ours_added, ours_replaced = installer.originals_view(game_dir)
    ours = ours_added | set(ours_replaced)

    archive_names: set[str] = set()
    for name in REQUIRED_ARCHIVES:
        big_path, bh_path = (os.path.join(game_dir, name + ext) for ext in ('.big', '.bh'))
        if not os.path.isfile(big_path) or not os.path.isfile(bh_path):
            issues.append(_issue('missing_file', name + ('.big' if not os.path.isfile(big_path) else '.bh')))
            continue
        try:
            big = BigArchive(big_path)
        except (BigError, OSError) as e:
            issues.append(_issue('unreadable_file', f'{name}.big: {e}'))
            continue
        archive_names.update(big.order)
        bh_rel = f'{name}.bh'
        bh_file = ours_replaced.get(bh_rel, bh_path)  # with our patch installed, judge the original index
        try:
            with open(bh_file, 'rb') as f:
                data = f.read()
            if not bh.entry_count_matches(data, len(big.order)):
                issues.append(_issue('index_mismatch', bh_rel))
                continue
            redirected = [big.order[i] for i in bh.zeroed(data)]
        except (OSError, bh.BhError) as e:
            issues.append(_issue('unreadable_file', f'{bh_rel}: {e}'))
            continue
        if redirected:
            issues.append(_issue('redirected_entries', f'{bh_rel}: {len(redirected)}'))

    locale = ours_replaced.get(LOCALE, os.path.join(game_dir, *LOCALE.split('/')))
    try:
        loc = BigArchive(locale)
        if not any(k.endswith('.db') for k in loc.order):
            issues.append(_issue('no_languages', LOCALE))
    except (BigError, OSError) as e:
        issues.append(_issue('missing_file' if isinstance(e, FileNotFoundError) else 'unreadable_file', LOCALE))

    foreign = [rel for rel in _loose_files(game_dir) if rel in archive_names and rel not in ours]
    if foreign:
        issues.append(_issue('loose_overrides', f'{len(foreign)}: {", ".join(foreign[:5])}'))

    if manifest:
        changed = installer.changed_after_install(game_dir)
        if changed:
            issues.append(_issue('patch_changed', ', '.join(changed[:5])))

    blocking = {'missing_file', 'unreadable_file', 'index_mismatch', 'no_languages'}
    if any(i['code'] in blocking for i in issues):
        state = 'invalid'
    elif issues:
        state = 'modified'
    else:
        state = 'patched' if manifest else 'clean'
    return {'state': state, 'game_dir': game_dir, 'issues': issues,
            'installed': {k: manifest.get(k) for k in ('version', 'installed_at')} if manifest else None}


def _loose_files(game_dir: str) -> list[str]:
    data = os.path.join(game_dir, 'data')
    out = []
    for folder, _, names in os.walk(data):
        for n in names:
            out.append(normalize(os.path.relpath(os.path.join(folder, n), game_dir)))
    return out
