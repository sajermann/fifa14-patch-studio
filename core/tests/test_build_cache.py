"""The build's steps, its cache (texts and pictures kept between builds) and stopping it (fake installation only)."""
import hashlib
import io
import os
import threading

import fakegame
import pytest
from PIL import Image

from f14mod import builder, buildcache, catalog, workers
from f14mod.project import Project


@pytest.fixture
def installed(tmp_path):
    return fakegame.build_installed(str(tmp_path))


def _png(color) -> bytes:
    buf = io.BytesIO()
    Image.new('RGBA', (64, 64), color + (255,)).save(buf, 'PNG')
    return buf.getvalue()


def _tree(folder):
    out = {}
    for base, _, names in os.walk(folder):
        for n in names:
            with open(os.path.join(base, n), 'rb') as f:
                out[os.path.relpath(os.path.join(base, n), folder)] = hashlib.sha1(f.read()).hexdigest()
    return out


def _project(tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save_team(fakegame.TEAM, {'full': {'*': 'Cached FC'}})
    project.set_picture('team', fakegame.TEAM, 'crest', _png((0, 150, 0)))
    project.set_kit(fakegame.TEAM, 0, {'source': 'upload'})
    project.set_picture('team', fakegame.TEAM, 'kit0_jersey', _png((10, 20, 30)))
    return project


def test_second_build_reuses_everything_and_gives_the_same_patch(installed, tmp_path):
    project = _project(tmp_path)
    files = catalog.open_game(installed)
    folder = str(tmp_path / 'cache')
    first = buildcache.BuildCache(folder)
    one = builder.build(files, project, str(tmp_path / 'one'), worker_count=1, cache=first)
    assert first.hits == 0 and first.misses >= 3  # texts, crest, kit
    assert one['reused_files'] == 0
    second = buildcache.BuildCache(folder)
    two = builder.build(files, project, str(tmp_path / 'two'), worker_count=1, cache=second)
    assert second.misses == 0 and second.hits == first.misses
    # every file but the database (always written again) came from the cache
    written = sum(len(names) for _, _, names in os.walk(str(tmp_path / 'two')))
    database_files = sum(1 for p in two['loose'] if p.startswith('data/db/')) + len(two['indexes'])
    assert two['reused_files'] == written - database_files
    assert _tree(str(tmp_path / 'two')) == _tree(str(tmp_path / 'one'))
    # without a cache: the same patch too
    builder.build(files, project, str(tmp_path / 'three'), worker_count=1)
    assert _tree(str(tmp_path / 'three')) == _tree(str(tmp_path / 'one'))


def test_a_change_makes_only_what_it_touches(installed, tmp_path):
    project = _project(tmp_path)
    files = catalog.open_game(installed)
    folder = str(tmp_path / 'cache')
    builder.build(files, project, str(tmp_path / 'one'), worker_count=1, cache=buildcache.BuildCache(folder))
    project.set_picture('team', fakegame.TEAM, 'kit0_jersey', _png((90, 0, 0)))  # only the kit changes
    again = buildcache.BuildCache(folder)
    builder.build(files, project, str(tmp_path / 'two'), worker_count=1, cache=again)
    assert again.misses == 1 and again.hits >= 2
    # the old kit is not used any more: the folder keeps one build's entries
    entries = sum(n.endswith('.zip') for _, _, names in os.walk(folder) for n in names)
    assert entries == again.hits + again.misses


def test_progress_goes_through_the_steps_in_order(installed, tmp_path):
    seen = []
    builder.build(catalog.open_game(installed), _project(tmp_path), str(tmp_path / 'out'), worker_count=1,
                  progress=lambda step, done, total, **item: seen.append(step))
    order = [s for k, s in enumerate(seen) if k == 0 or seen[k - 1] != s]
    assert order == list(builder.BUILD_STEPS)


def test_stopped_build_leaves_the_patch_as_it_was(installed, tmp_path):
    out = str(tmp_path / 'out')
    os.makedirs(out)
    with open(os.path.join(out, 'old.txt'), 'w') as f:
        f.write('previous patch')
    cancel = threading.Event()

    def progress(step, done, total, **item):
        if step == 'images':
            cancel.set()
    with pytest.raises(builder.BuildCancelled):
        builder.build(catalog.open_game(installed), _project(tmp_path), out, progress=progress, worker_count=1,
                      cache=buildcache.BuildCache(str(tmp_path / 'cache')), cancel=cancel)
    assert os.listdir(out) == ['old.txt']


def test_languages_in_worker_processes_give_the_same_files(installed, tmp_path):
    if workers.cpu_cores() in (None, 1):
        pytest.skip('one core')
    project = _project(tmp_path)
    files = catalog.open_game(installed)
    builder.build(files, project, str(tmp_path / 'one'), worker_count=1)
    builder.build(files, project, str(tmp_path / 'two'), worker_count=2)
    assert _tree(str(tmp_path / 'two')) == _tree(str(tmp_path / 'one'))
