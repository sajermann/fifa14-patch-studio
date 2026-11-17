import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import fakegame  # noqa: E402


@pytest.fixture(scope='session')
def loose_game(tmp_path_factory):
    """Fake installation with loose files (tests/fakegame.py), built once per run."""
    return fakegame.build(str(tmp_path_factory.mktemp('loose')))


@pytest.fixture(scope='session')
def archived_game(tmp_path_factory):
    """The same fake data inside BIG archives."""
    return fakegame.build_archived(str(tmp_path_factory.mktemp('archived')))


@pytest.fixture(scope='session', params=['loose', 'archived'])
def game(request, loose_game, archived_game):
    return loose_game if request.param == 'loose' else archived_game
