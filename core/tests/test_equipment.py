"""Boots, goalkeeper gloves and balls: the texture files written in the game's layout, the project's storage and what
the patch gets (fake game)."""
import os
import sqlite3

import fakegame
import pytest
from PIL import Image

from f14mod import builder, equipment, rx3, t3db
from f14mod.dbedit import Database, LanguageStrings
from f14mod.fifa14 import META
from f14mod.gamefs import DATABASE, GameFiles
from f14mod.project import SCHEMA_VERSION, EQUIPMENT_PICTURE, Project


@pytest.fixture
def game(tmp_path):
    return fakegame.build(str(tmp_path / 'game'))


def _read(out, path):
    with open(os.path.join(out, *path.split('/')), 'rb') as f:
        return f.read()


def test_texture_file_in_the_game_layout():
    data = fakegame.equipment_textures('boot', (200, 20, 20))
    found = rx3.textures(data)
    assert [t['name'] for t in found] == ['shoe_cm', 'shoe_nm', 'shoe_coeff']
    assert all(t['fmt'] == 0 and (t['w'], t['h']) == (16, 16) and t['mips'] == 5 for t in found)  # down to 1x1
    r, g, b = rx3.to_image(data, found[0]).convert('RGB').getpixel((8, 8))
    assert r > 150 and g < 60 and b < 60
    # the game reads these formats: kept as they are
    assert equipment.game_textures('boot', data) is data


def test_normal_map_gets_its_z():
    flat = Image.new('RGB', (4, 4), (128, 128, 0))  # x, y only (a BC5 map read as RGB)
    assert equipment.full_normal(flat).getpixel((0, 0))[2] > 240


def test_project_keeps_the_files_and_the_dates(tmp_path):
    p = Project(str(tmp_path / 'p.sqlite'))
    p.create('boot', 233, fields={'name': 'B01'})
    p.set_equipment_files('boot', 233, {'mesh': b'mesh', 'texture': b'tex'})
    assert p.equipment_files('boot', 233) == {'mesh': b'mesh', 'texture': b'tex'}
    assert p.with_equipment_files('boot') == [233] and p.created('boot') == [233]
    p.set_equipment_files('boot', 233, {'mesh': None})  # one file dropped, the other kept
    assert p.equipment_files('boot', 233) == {'texture': b'tex'}
    # a game glove: a new name keeps it edited, restoring gives the game's back (no dates left)
    p.save('glove', 1, fields={'name': 'G01'})
    p.set_equipment_files('glove', 1, {'texture': b'tex'})
    assert p.edited('glove') == [1] and p.dates('glove', 1)[1]
    p.save('glove', 1, fields={})  # the name gone, the file still there: still edited
    assert p.edited('glove') == [1]
    p.reset('glove', 1)
    assert p.edited('glove') == [] and p.equipment_files('glove', 1) == {} and p.dates('glove', 1) == (None, None)
    # the same id in two kinds never mixes
    p.create('ball', 233, fields={'name': 'L01'})
    assert p.equipment_files('ball', 233) == {}


def test_older_project_opens(tmp_path):
    path = str(tmp_path / 'p.sqlite')
    Project(path)
    con = sqlite3.connect(path)
    con.execute('DROP TABLE equipment_files')
    con.execute("UPDATE meta SET value = '12' WHERE key = 'schema'")
    con.commit()
    con.close()
    p = Project(path)
    assert p.equipment_files('boot', 1) == {}
    con = sqlite3.connect(path)
    assert con.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()[0] == str(SCHEMA_VERSION)
    con.close()


def test_patch_gets_boots_gloves_and_balls(game, tmp_path):
    files = GameFiles(game)
    assert equipment.game_codes(files, 'boot') == [fakegame.GAME_BOOT]
    p = Project(str(tmp_path / 'p.sqlite'))
    boot = equipment.free_codes(files, 'boot')[0]
    glove = equipment.free_codes(files, 'glove')[0]
    ball = equipment.free_codes(files, 'ball')[0]
    game_mesh = files.read(f'data/sceneassets/shoe/shoe_{fakegame.GAME_BOOT}.rx3')
    p.create('boot', boot, fields={'name': 'B01'})
    p.set_equipment_files('boot', boot, {'mesh': game_mesh, 'texture': fakegame.equipment_textures('boot', (1, 2, 3))})
    p.create('glove', glove, fields={'name': 'G01'})
    p.set_equipment_files('glove', glove, {'texture': fakegame.equipment_textures('glove', (200, 0, 0))})
    p.save('glove', fakegame.GAME_GLOVE, fields={'name': 'G02'})  # a game glove renamed (its files stay)
    p.create('ball', ball, fields={'name': 'L01'})
    p.set_equipment_files('ball', ball, {'mesh': files.read(f'data/sceneassets/ball/ball_{fakegame.GAME_BALL}.rx3'),
                                         'texture': fakegame.equipment_textures('ball', (0, 0, 200))})
    p.save('player', fakegame.KEEPER, fields={'shoetypecode': boot, 'gkglovetypecode': glove})
    p.save('team', fakegame.TEAM, fields={'balltype': ball})
    out = str(tmp_path / 'out')
    summary = builder.build(files, p, out, worker_count=1)
    assert summary['equipment'] == {'boot': 1, 'glove': 1, 'ball': 1}

    assert _read(out, f'data/sceneassets/shoe/shoe_{boot}.rx3') == game_mesh  # already in the game's layout
    assert rx3.textures(_read(out, f'data/sceneassets/shoe/shoe_{boot}_0_textures.rx3'))
    assert _read(out, f'data/sceneassets/gkglove/gkglove_{glove}.rx3') == files.read(equipment.GLOVE_MESH)
    assert rx3.textures(_read(out, f'data/sceneassets/gkglove/gkglove_{glove}_textures.rx3'))
    assert not os.path.exists(os.path.join(out, 'data', 'sceneassets', 'gkglove',
                                           f'gkglove_{fakegame.GAME_GLOVE}_textures.rx3'))  # only renamed
    assert rx3.textures(_read(out, f'data/sceneassets/ball/ball_{ball}_textures.rx3'))
    assert os.path.exists(os.path.join(out, 'data', 'ui', 'artassets', 'settingsimg', f'ball_{ball}.big'))

    out_files = GameFiles(out)
    db = Database(out_files.read(DATABASE), t3db.load_meta(out_files.read(META)))
    players = db.table('players')
    row = players.find(playerid=fakegame.KEEPER)[0]
    assert [players.get(row, c) for c in ('shoetypecode', 'shoecolorcode1', 'shoecolorcode2', 'shoedesigncode',
                                          'gkglovetypecode')] == [boot, 30, 31, 0, glove]
    teams = db.table('teams')
    assert teams.get(teams.find(teamid=fakegame.TEAM)[0], 'balltype') == ball
    boots = db.table('playerboots')
    new = [r for r in boots.records if boots.get(r, 'shoetype') == boot]
    assert len(new) == 1 and boots.get(new[0], 'powid') == -1 and boots.get(new[0], 'isavailableinstore') == 1
    balls = db.table('teamballs')
    assert sorted(balls.get(r, 'ballid') for r in balls.records) == [fakegame.GAME_BALL, ball]

    strings = LanguageStrings(out_files.read('data/loc/eng_us.db'))
    assert strings.get(f'CreatePlayerBoot_{boot}') == 'B01' and strings.get(f'Boot_{boot}') == 'B01'
    assert strings.get(f'GkGlovePattern_{fakegame.GAME_GLOVE}') == 'G02'
    assert strings.get(f'BallName_{ball}') == 'L01'


def test_hidden_item_stays_out(game, tmp_path):
    files = GameFiles(game)
    p = Project(str(tmp_path / 'p.sqlite'))
    ball = equipment.free_codes(files, 'ball')[0]
    p.create('ball', ball, fields={'name': 'L01'})
    p.set_equipment_files('ball', ball, {'texture': fakegame.equipment_textures('ball', (0, 0, 200))})
    p.set_hidden('ball', ball, True)
    summary = builder.build(files, p, str(tmp_path / 'out'), worker_count=1)
    assert 'equipment' not in summary


def test_user_picture_goes_to_the_match_settings(game, tmp_path):
    import io
    files = GameFiles(game)
    p = Project(str(tmp_path / 'p.sqlite'))
    buf = io.BytesIO()
    Image.new('RGB', (40, 40), (255, 0, 0)).save(buf, 'PNG')
    p.set_picture('ball', fakegame.GAME_BALL, EQUIPMENT_PICTURE, buf.getvalue())  # a game ball's new picture
    out = str(tmp_path / 'out')
    builder.build(files, p, out, worker_count=1)
    from f14mod import images
    picture = images.apt_picture(_read(out, f'data/ui/artassets/settingsimg/ball_{fakegame.GAME_BALL}.big'))
    assert picture.convert('RGBA').getpixel((picture.width // 2, picture.height // 2))[0] > 200


def test_triangles_list_and_strip():
    # a list (boots, gloves) may repeat an index across two triangles: still a list
    assert equipment.triangles([0, 1, 2, 2, 3, 4, 4, 5, 6]).tolist() == [[0, 1, 2], [2, 3, 4], [4, 5, 6]]
    # a strip (balls): every other triangle turned back, the degenerate joins dropped
    assert equipment.triangles([0, 1, 2, 3, 3, 4, 4, 5, 6]).tolist() == [[0, 1, 2], [2, 1, 3], [4, 5, 6]]
