"""What the backend keeps while it runs: the chosen game (its check and the originals cache, built in a thread),
the user's project and the one long job at a time (build, install, uninstall)."""
import logging
import os
import threading
import time
import uuid

from f14mod import catalog, install_check
from f14mod.gamefs import GameFiles
from f14mod.project import Project

from . import settings

log = logging.getLogger('f14api')

READY_STATES = ('clean', 'patched')


class GameState:
    """The installation in the config: its check, the originals cache (built once per game) and its files."""

    def __init__(self):
        self.lock = threading.Lock()
        self.game_dir: str | None = None
        self.check: dict | None = None
        self.catalog_path: str | None = None
        self.state = 'empty'  # empty | invalid | building | ready | error
        self.progress: dict = {'step': '', 'done': 0.0}
        self.error: str | None = None
        self.token = ''  # changes when the cache changes (image URLs carry it)
        self._files: GameFiles | None = None

    def open(self, game_dir: str | None) -> None:
        """Checks the game; when it can be patched, opens (or builds) its originals cache."""
        with self.lock:
            if self.state == 'building':
                raise RuntimeError('busy')
            self.game_dir, self.check, self.catalog_path, self._files, self.error = game_dir, None, None, None, None
            if not game_dir:
                self.state = 'empty'
                return
            self.check = install_check.check(game_dir)
            if self.check['state'] not in READY_STATES:
                self.state = 'invalid'
                return
            self.state, self.progress = 'building', {'step': 'start', 'done': 0.0}
        threading.Thread(target=self._prepare, daemon=True).start()

    def recheck(self) -> None:
        if self.game_dir:
            self.check = install_check.check(self.game_dir)

    def _prepare(self) -> None:
        started = time.time()
        try:
            files = catalog.open_game(self.game_dir)
            key = catalog.fingerprint(files)
            path = os.path.join(settings.CACHE_DIR, 'originals', f'{key}.sqlite')
            if catalog.read_meta(path).get('fingerprint') != key:
                catalog.build(self.game_dir, path, self._step)
                log.info('originals cache built in %.1f s', time.time() - started)
        except Exception as e:  # noqa: BLE001 - shown on screen; the cause goes to the log
            log.exception('preparing %s failed', self.game_dir)
            with self.lock:
                self.state, self.error = 'error', f'{type(e).__name__}: {e}'
            return
        with self.lock:
            self.catalog_path, self._files, self.state = path, files, 'ready'
            self.token = key[:8]

    def _step(self, message: str, done: float) -> None:
        self.progress = {'step': message, 'done': round(done, 3)}

    def files(self) -> GameFiles:
        """The clean game's files (rebuilt after an install changed the folder)."""
        with self.lock:
            if self._files is None:
                self._files = catalog.open_game(self.game_dir)
            return self._files

    def forget_files(self) -> None:
        with self.lock:
            self._files = None

    def status(self) -> dict:
        return {'state': self.state, 'game_dir': self.game_dir, 'check': self.check, 'progress': self.progress,
                'error': self.error, 'token': self.token}


class Jobs:
    """One long task at a time (build, install, uninstall), run in a thread; the interface polls its state."""

    def __init__(self):
        self.lock = threading.Lock()
        self.current: dict | None = None

    def start(self, kind: str, work) -> dict:
        with self.lock:
            if self.current and self.current['state'] == 'running':
                raise RuntimeError('busy')
            job = {'id': uuid.uuid4().hex[:8], 'kind': kind, 'state': 'running', 'step': '', 'done': 0.0,
                   'result': None, 'error': None, 'started_at': time.time()}
            self.current = job

        def progress(step: str, done: float):
            job['step'], job['done'] = step, round(done, 3)

        def run():
            try:
                job['result'] = work(progress)
                job['state'], job['done'] = 'done', 1.0
            except Exception as e:  # noqa: BLE001
                log.exception('%s failed', kind)
                job['state'], job['error'] = 'error', f'{type(e).__name__}: {e}'
        threading.Thread(target=run, daemon=True).start()
        return dict(job)

    def view(self) -> dict | None:
        return dict(self.current) if self.current else None


def project() -> Project:
    os.makedirs(settings.PROJECT_DIR, exist_ok=True)
    return Project(os.path.join(settings.PROJECT_DIR, 'project.sqlite'))
