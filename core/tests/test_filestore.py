"""The project's files live in folders next to the database (f14mod.filestore), never inside it."""
import os
import sqlite3

import pytest

from f14mod import filestore, share
from f14mod.project import Project, ProjectError
from test_share import FakeDest


def _files(p: Project) -> list[str]:
    """Every file kept in the project's folders (relative paths)."""
    out = []
    for folder in filestore.FOLDERS:
        base = os.path.join(p.files.root, folder)
        if os.path.isdir(base):
            out += [f'{folder}/{n}' for n in os.listdir(base)]
    return sorted(out)


def _blob_columns(path: str) -> list[str]:
    con = sqlite3.connect(path)
    try:
        return [f'{t}.{c[1]}' for t in filestore.FILE_TABLES
                for c in con.execute(f'PRAGMA table_info({t})') if c[2].upper() == 'BLOB']
    finally:
        con.close()


def test_the_database_keeps_paths_not_bytes(tmp_path):
    p = Project(os.path.join(tmp_path, 'project.sqlite'))
    p.create('player', 300001, fields={'name.common': 'A01'})
    p.set_picture('player', 300001, 'photo', b'A01 photo')
    p.set_player_files(300001, {'head': b'A01 head'})
    p.create('stadium', 266)
    p.set_stadium_scene(266, {'data/sceneassets/stadium/stadium_#.rx3': b'S01 scene'})
    p.create('boot', 100, fields={'name': 'C01'})
    p.set_equipment_files('boot', 100, {'mesh': b'C01 mesh'})
    assert _blob_columns(p.path) == []
    assert p.files.root == os.path.join(tmp_path, 'project_files')
    assert len(_files(p)) == 4
    assert p.picture('player', 300001, 'photo')[0] == b'A01 photo'
    assert p.player_files(300001) == {'head': b'A01 head'}
    assert p.stadium_scene_file(266, 'data/sceneassets/stadium/stadium_#.rx3') == b'S01 scene'
    assert p.stadium_scene_list(266) == {'data/sceneassets/stadium/stadium_#.rx3': len(b'S01 scene')}
    assert p.equipment_files('boot', 100) == {'mesh': b'C01 mesh'}


def test_equal_files_are_kept_once(tmp_path):
    p = Project(os.path.join(tmp_path, 'project.sqlite'))
    for oid in (400, 401, 402):
        p.create('league', oid)
        p.set_picture('league', oid, 'logo', b'same logo')
    assert _files(p) == [f'images/{filestore.digest(b"same logo")}.png']


def test_editing_one_of_three_equal_files_leaves_the_other_two_as_they_were(tmp_path):
    """Three items with the same file; the second one changes: only its row points to a new file."""
    p = Project(os.path.join(tmp_path, 'project.sqlite'))
    for oid in (400, 401, 402):
        p.create('league', oid)
        p.set_picture('league', oid, 'logo', b'L01 logo')
    p.set_picture('league', 401, 'logo', b'L02 logo')
    assert p.picture('league', 400, 'logo')[0] == b'L01 logo'
    assert p.picture('league', 401, 'logo')[0] == b'L02 logo'
    assert p.picture('league', 402, 'logo')[0] == b'L01 logo'
    assert len(_files(p)) == 2
    # the same for the scene files of two stadiums that shared everything
    scene = {'data/sceneassets/stadium/stadium_#.rx3': b'S01 scene', 'data/sceneassets/stadium/stadium_#_textures.rx3': b'S01 tex'}
    for sid in (266, 267):
        p.create('stadium', sid)
        p.set_stadium_scene(sid, scene)
    p.set_stadium_scene(267, {**scene, 'data/sceneassets/stadium/stadium_#_textures.rx3': b'S02 tex'})
    assert p.stadium_scene_file(266, 'data/sceneassets/stadium/stadium_#_textures.rx3') == b'S01 tex'
    assert p.stadium_scene_file(267, 'data/sceneassets/stadium/stadium_#_textures.rx3') == b'S02 tex'
    assert p.stadium_scene_file(267, 'data/sceneassets/stadium/stadium_#.rx3') == b'S01 scene'


def test_a_file_goes_only_when_nothing_points_to_it(tmp_path):
    p = Project(os.path.join(tmp_path, 'project.sqlite'))
    for oid in (400, 401):
        p.create('league', oid)
        p.set_picture('league', oid, 'logo', b'L01 logo')
    p.delete('league', 400)
    assert p.picture('league', 401, 'logo')[0] == b'L01 logo'  # still used by 401
    assert len(_files(p)) == 1
    p.set_picture('league', 401, 'logo', None)
    assert _files(p) == []
    p.create('player', 300001)
    p.set_player_files(300001, {'head': b'A01 head', 'hair': b'A01 hair'})
    p.set_player_files(300001, {'head': b'A01 head'})
    assert len(_files(p)) == 1
    p.reset('player', 300001)
    assert _files(p) == []


def test_prune_removes_what_no_row_uses(tmp_path):
    p = Project(os.path.join(tmp_path, 'project.sqlite'))
    p.create('league', 400)
    p.set_picture('league', 400, 'logo', b'L01 logo')
    p.files.put(filestore.PICTURES, b'left by a cancelled import', '.png')
    assert len(_files(p)) == 2
    assert p.prune_files(min_age=60) == 0  # too young: its row may still be on its way
    assert p.prune_files(min_age=0) == 1
    assert p.picture('league', 400, 'logo')[0] == b'L01 logo'


def test_export_and_import_carry_the_files(tmp_path):
    src = Project(os.path.join(tmp_path, 'src.sqlite'))
    src.create('player', 300001, fields={'name.common': 'A01'})
    src.set_player_source(300001, None)
    src.set_picture('player', 300001, 'photo', b'A01 photo')
    src.set_player_files(300001, {'head': b'A01 head'})
    src.create('stadium', 266)
    src.set_stadium_scene(266, {'data/sceneassets/stadium/stadium_#.rx3': b'S01 scene'})
    writer = share.Writer()
    writer.add(src, 'player', 300001)
    writer.add(src, 'stadium', 266)
    zip_path = os.path.join(tmp_path, 'out.zip')
    writer.write(zip_path)

    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    bundle = share.read(zip_path)
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    share.apply(dst, bundle, ids, set(ids), dest)
    new_player = ids['player:300001']['id']
    new_stadium = ids['stadium:266']['id']
    assert dst.picture('player', new_player, 'photo')[0] == b'A01 photo'
    assert dst.player_files(new_player) == {'head': b'A01 head'}
    assert dst.stadium_scene_file(new_stadium, 'data/sceneassets/stadium/stadium_#.rx3') == b'S01 scene'
    assert dst.files.root != src.files.root and len(_files(dst)) == 3


def test_an_older_project_with_the_files_inside_is_refused(tmp_path):
    path = os.path.join(tmp_path, 'project.sqlite')
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)')
    con.execute("INSERT INTO meta VALUES ('schema', '14')")
    con.execute('CREATE TABLE pictures (kind TEXT, id INTEGER, slot TEXT, data BLOB, updated_at INTEGER)')
    con.commit()
    con.close()
    with pytest.raises(ProjectError):
        Project(path)
