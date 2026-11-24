"""Advertising boards: the user's boards, the game's boards, their links to teams and leagues and what the patch gets
(fake game)."""
import io
import os
import sqlite3

import fakegame
import pytest
from PIL import Image

from f14mod import adboards, builder, rx3
from f14mod.gamefs import GameFiles
from f14mod.project import ADBOARD_PICTURE, FIRST_OWN_ADBOARD, Project

SCRIPT = os.path.join('data', 'fifarna', 'lua', 'assets', 'stadium.lua')
GAME_BOARD = 1  # the fake game's board file (adboard_1_0.rx3)


@pytest.fixture
def game(tmp_path):
    return fakegame.build(str(tmp_path / 'game'))


def _png(color, size=(512, 1024)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def _board(project: Project, name: str, color) -> int:
    bid = project.next_adboard_id()
    project.create('adboard', bid, fields={'name': name})
    project.set_picture('adboard', bid, ADBOARD_PICTURE, _png(color))
    return bid


def _color(path: str):
    with open(path, 'rb') as f:
        data = f.read()
    texture = rx3.textures(data)[0]
    return texture, rx3.to_image(data, texture).convert('RGB').getpixel((8, 16))


def test_links_follow_the_board_and_the_team(tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    a01 = _board(project, 'A01', (200, 0, 0))
    a02 = _board(project, 'A02', (0, 0, 200))
    assert (a01, a02) == (FIRST_OWN_ADBOARD, FIRST_OWN_ADBOARD + 1)  # never a game board's number
    project.set_adboard_link('team', fakegame.TEAM, a01)
    project.set_adboard_link('team', fakegame.SMALL_TEAM, a01)  # one board on two teams
    project.set_adboard_link('league', fakegame.LEAGUE, a02)
    assert project.adboard_users(a01) == {'team': [fakegame.TEAM, fakegame.SMALL_TEAM], 'league': []}
    assert project.counts() == {'team': 2, 'league': 1, 'new_adboard': 2}  # a board keeps a game team edited
    assert project.dates('team', fakegame.TEAM)[1]
    project.reset('team', fakegame.SMALL_TEAM)  # back to the game's: no board
    assert project.adboard_link('team', fakegame.SMALL_TEAM) is None
    project.set_adboard_link('team', fakegame.TEAM, None)  # nothing else changed: the game's team again
    assert 'team' not in project.counts() and project.dates('team', fakegame.TEAM) == (None, None)
    project.delete('adboard', a02)  # a deleted board leaves its leagues
    assert project.adboard_link('league', fakegame.LEAGUE) is None and 'league' not in project.counts()
    assert project.created('adboard') == [a01]


def test_patch_gets_each_board_once_and_the_script(game, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    a01 = _board(project, 'A01', (200, 0, 0))
    a02 = _board(project, 'A02', (0, 0, 200))
    a03 = _board(project, 'A03', (0, 200, 0))  # linked to nothing: not in the patch
    project.set_adboard_link('team', fakegame.TEAM, a01)
    project.set_adboard_link('team', fakegame.SMALL_TEAM, a01)
    project.set_adboard_link('league', fakegame.LEAGUE, a02)
    project.set_adboard_link('league', fakegame.PLAIN_LEAGUE, GAME_BOARD)  # a board of the game, as it is
    out = str(tmp_path / 'patch')
    summary = builder.build(GameFiles(game), project, out, worker_count=1)
    assert summary['adboards'] == {'boards': 2, 'game_boards': 0, 'teams': 2, 'leagues': 2}
    folder = os.path.join(out, 'data', 'sceneassets', 'adboard')
    assert sorted(os.listdir(folder)) == [f'studioadboard_{a01}.rx3', f'studioadboard_{a02}.rx3']
    texture, color = _color(os.path.join(folder, f'studioadboard_{a01}.rx3'))
    assert (texture['name'], texture['w'], texture['h']) == ('adboard_1', 16, 32)  # the game's file, the user's picture
    assert color == (200, 0, 0)
    with open(os.path.join(out, SCRIPT), 'rb') as f:
        script = f.read().decode()
    assert (f'StudioTeamAdboards = {{ [{fakegame.TEAM}] = "studioadboard_{a01}", '
            f'[{fakegame.SMALL_TEAM}] = "studioadboard_{a01}" }}') in script
    assert (f'StudioLeagueAdboards = {{ [{fakegame.LEAGUE}] = "studioadboard_{a02}", '
            f'[{fakegame.PLAIN_LEAGUE}] = "adboard_{GAME_BOARD}_0" }}') in script
    assert 'return "data/sceneassets/adboard/" .. board .. ".rx3;"' in script
    assert 'db.stadium[idx].matchLeagueID = as:GetInt(wipe, "leagueID")' in script
    assert '"${StudioAdboardSrc(?)}data/sceneassets/adboard/adboard_${db.stadium[?].adboardID}_' in script
    assert script.count('\r\n') > fakegame.STADIUM_SCRIPT.count(b'\r\n') and '\n' not in script.replace('\r\n', '')
    assert f'studioadboard_{a03}' not in script


def test_edited_game_board_goes_into_its_own_file(game, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.set_picture('adboard', GAME_BOARD, ADBOARD_PICTURE, _png((0, 150, 0)))  # an original edited
    assert project.counts() == {'adboard': 1} and not project.is_created('adboard', GAME_BOARD)
    project.set_picture('adboard', 77, ADBOARD_PICTURE, _png((0, 0, 0)))  # a number the game has no file for: skipped
    out = str(tmp_path / 'patch')
    summary = builder.build(GameFiles(game), project, out, worker_count=1)
    assert summary['adboards'] == {'boards': 0, 'game_boards': 1, 'teams': 0, 'leagues': 0}
    assert not os.path.exists(os.path.join(out, SCRIPT))  # no links: the game's script stays
    texture, color = _color(os.path.join(out, 'data', 'sceneassets', 'adboard', f'adboard_{GAME_BOARD}_0.rx3'))
    assert color == (0, 150, 0)
    project.reset('adboard', GAME_BOARD)  # Restore: the game's board again
    project.reset('adboard', 77)
    assert 'adboard' not in project.counts()


def test_hidden_board_and_no_links_leave_the_game_alone(game, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    a01 = _board(project, 'A01', (200, 0, 0))
    bare = project.next_adboard_id()
    project.create('adboard', bare, fields={'name': 'A02'})  # no picture yet
    project.set_adboard_link('league', fakegame.LEAGUE, bare)
    project.set_adboard_link('team', fakegame.TEAM, a01)
    project.set_hidden('adboard', a01, True)  # out of the patch: its teams show the game's boards
    out = str(tmp_path / 'patch')
    summary = builder.build(GameFiles(game), project, out, worker_count=1)
    assert 'adboards' not in summary
    assert not os.path.exists(os.path.join(out, SCRIPT))
    assert not os.path.exists(os.path.join(out, 'data', 'sceneassets', 'adboard'))


def test_schema_11_boards_get_their_own_numbers(tmp_path):
    """A project of schema 11 numbered the created boards from 1: they move to FIRST_OWN_ADBOARD with their links."""
    path = str(tmp_path / 'p.sqlite')
    project = Project(path)
    a01 = _board(project, 'A01', (200, 0, 0))
    a02 = _board(project, 'A02', (0, 0, 200))
    project.set_adboard_link('team', fakegame.TEAM, a02)
    con = sqlite3.connect(path)
    for old, new in ((a01, 1), (a02, 2)):  # as schema 11 wrote them
        for table in ('created', 'fields', 'pictures', 'hidden', 'dates', 'edited'):
            con.execute(f"UPDATE {table} SET id = ? WHERE kind = 'adboard' AND id = ?", (new, old))
        con.execute('UPDATE team_adboards SET adboard_id = ? WHERE adboard_id = ?', (new, old))
    con.execute("UPDATE meta SET value = '11' WHERE key = 'schema'")
    con.commit()
    con.close()
    project = Project(path)
    assert project.created('adboard') == [FIRST_OWN_ADBOARD, FIRST_OWN_ADBOARD + 1]
    assert project.fields('adboard', FIRST_OWN_ADBOARD + 1) == {'name': 'A02'}
    assert project.picture('adboard', FIRST_OWN_ADBOARD, ADBOARD_PICTURE)
    assert project.adboard_link('team', fakegame.TEAM) == FIRST_OWN_ADBOARD + 1


def test_script_of_another_patch_is_refused():
    script = adboards.script(fakegame.STADIUM_SCRIPT, {1: FIRST_OWN_ADBOARD}, {})
    with pytest.raises(adboards.AdboardError):
        adboards.script(script, {1: FIRST_OWN_ADBOARD}, {})  # already has boards
    with pytest.raises(adboards.AdboardError):
        adboards.script(b'function StadiumUpdate(idx)\nend\n', {1: FIRST_OWN_ADBOARD}, {})


def test_picture_is_stretched_to_the_board_size():
    img = adboards.picture(_png((10, 20, 30), (256, 256)))
    assert img.size == adboards.SIZE


def test_game_table():
    assert adboards.competitions_of(5) == [53, 54] and adboards.file_name(5) == 'adboard_5_0'
    assert adboards.file_name(FIRST_OWN_ADBOARD) == f'studioadboard_{FIRST_OWN_ADBOARD}'
