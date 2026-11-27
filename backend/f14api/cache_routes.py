"""The app's cache folder on the settings screen: its size, and clearing what the app makes again by itself (the build
cache and the pictures drawn for the screens). Registered by main (imported before the interface's catch-all route).

Left alone: the game's originals read into the cache (the app works from them: deleting them would make it read the
game again) and the files of an import in progress."""
import os
import shutil
import threading
import time

from . import settings
from .main import ApiError, app, jobs, log

# the parts the app makes again by itself (f14mod.buildcache, and the pictures of main and player_routes)
CLEARABLE = ('build', 'images', 'faces', 'appearance')

# the current / last clearing, read by GET /api/cache/progress while the request runs
clear_progress: dict = {'running': False}
_lock = threading.Lock()


def _files(parts) -> list[tuple[str, int]]:
    """(path, size) of every file under the given parts of the cache folder."""
    out = []
    for part in parts:
        for root, _, names in os.walk(os.path.join(settings.CACHE_DIR, part)):
            for name in names:
                path = os.path.join(root, name)
                try:
                    out.append((path, os.path.getsize(path)))
                except OSError:
                    pass
    return out


def _parts() -> list[str]:
    try:
        return sorted(e.name for e in os.scandir(settings.CACHE_DIR) if e.is_dir())
    except OSError:
        return []


@app.get('/api/cache')
def get_cache():
    """The cache folder: where it is, its whole size and the size of what clearing deletes."""
    clearable = _files(CLEARABLE)
    every = _files(_parts())
    return {'folder': settings.CACHE_DIR, 'bytes': sum(s for _, s in every), 'files': len(every),
            'clearable_bytes': sum(s for _, s in clearable), 'clearable_files': len(clearable)}


@app.post('/api/cache/clear')
def clear_cache():
    """Deletes the parts of the cache the app makes again (CLEARABLE), file by file (GET /api/cache/progress says
    where it is). Not while a build, an install or an import runs: they read and write these files."""
    from . import share_routes  # noqa: PLC0415 - imported by main after this module
    global clear_progress
    view = jobs.view()
    if (view and view['state'] == 'running') or share_routes.import_progress.get('running'):
        raise ApiError(409, 'busy')
    if not _lock.acquire(blocking=False):
        raise ApiError(409, 'busy')
    try:
        files = _files(CLEARABLE)
        prog = {'running': True, 'done': 0, 'total': len(files), 'bytes_done': 0,
                'bytes_total': sum(s for _, s in files), 'failed': 0, 'started_at': time.time(), 'finished_at': None}
        clear_progress = prog
        try:
            for path, size in files:
                try:
                    os.remove(path)
                    prog['bytes_done'] += size
                except OSError:
                    prog['failed'] += 1  # in use (a picture being read): left for the next time
                prog['done'] += 1
            for part in CLEARABLE:  # the empty folders left
                shutil.rmtree(os.path.join(settings.CACHE_DIR, part), ignore_errors=True)
        finally:
            prog.update(running=False, finished_at=time.time())
        log.info('cache cleared: %s files, %s bytes in %.1f s (%s left in use)', prog['done'] - prog['failed'],
                 prog['bytes_done'], prog['finished_at'] - prog['started_at'], prog['failed'])
        return {'files': prog['done'] - prog['failed'], 'bytes': prog['bytes_done'], 'failed': prog['failed']}
    finally:
        _lock.release()


@app.get('/api/cache/progress')
def get_clear_progress():
    """Where the current (or last) clearing is: files done/total and bytes freed."""
    prog = dict(clear_progress)
    if prog.get('started_at'):
        prog['elapsed'] = round((prog['finished_at'] or time.time()) - prog['started_at'], 1)
    return prog
