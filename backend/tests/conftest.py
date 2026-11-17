import os
import sys
import tempfile
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
CORE_TESTS = os.path.join(os.path.dirname(BACKEND), 'core', 'tests')
sys.path.insert(0, BACKEND)
sys.path.insert(0, CORE_TESTS)

# the app's data (config, project, caches, patch) goes to a temporary folder: tests never touch backend/data
os.environ['F14_DATA_DIR'] = tempfile.mkdtemp(prefix='f14-test-')

import fakegame  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from f14api import main  # noqa: E402


@pytest.fixture(scope='session')
def game_dir(tmp_path_factory):
    return fakegame.build_installed(str(tmp_path_factory.mktemp('game')))


def wait(predicate, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    raise TimeoutError


@pytest.fixture
def client(game_dir):
    c = TestClient(main.app)
    r = c.post('/api/game', json={'path': game_dir})
    assert r.status_code == 200, r.text
    wait(lambda: main.game.state in ('ready', 'error'))
    assert main.game.state == 'ready', main.game.error
    return c
