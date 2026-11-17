import os

import fakegame
from conftest import wait

from f14api import main


def test_status_and_check(client, game_dir, tmp_path):
    s = client.get('/api/status').json()
    assert s['game']['state'] == 'ready'
    assert s['game']['check']['state'] == 'clean'
    assert client.post('/api/game/check', json={'path': str(tmp_path)}).json()['state'] == 'not_found'
    r = client.post('/api/game', json={'path': str(tmp_path)})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'game_not_usable'


def test_lists_page_filter_sort(client):
    teams = client.get('/api/teams').json()
    assert teams['total'] == 2
    assert [t['name'] for t in teams['items']] == ['Small Team FC', 'Test Athletic Club']
    assert client.get('/api/teams', params={'q': 'athletic'}).json()['total'] == 1
    assert client.get('/api/teams', params={'league': fakegame.PLAIN_LEAGUE}).json()['items'][0]['id'] == \
        fakegame.SMALL_TEAM
    players = client.get('/api/players', params={'size': 25, 'sort': 'overall', 'dir': 'desc'}).json()
    assert players['total'] == fakegame.COUNTS['players']
    assert players['items'][0]['id'] == fakegame.STAR
    page2 = client.get('/api/players', params={'size': 25, 'page': 2}).json()
    assert page2['page'] == 1  # only one page: clamped
    assert client.get('/api/players', params={'team': fakegame.SMALL_TEAM}).json()['total'] == 6
    assert client.get('/api/leagues').json()['total'] == 2


def test_team_names_crud(client):
    tid = fakegame.TEAM
    team = client.get(f'/api/teams/{tid}').json()
    assert team['original_names']['abbr15']['eng_us'] == 'Test Athletic'
    assert team['saved_names'] == {}
    assert len(team['roster']) == 16
    r = client.put(f'/api/teams/{tid}', json={'names': {'abbr15': {'*': 'New Name', 'por_br': 'Nome Novo'},
                                                       'abbr3': {'eng_us': 'TAT'}}})
    assert r.status_code == 200
    assert r.json()['saved_names'] == {'abbr15': {'*': 'New Name', 'por_br': 'Nome Novo'}}  # same as game: dropped
    assert client.get('/api/teams', params={'edited': 'yes'}).json()['items'][0]['abbr15'] == 'New Name'
    bad = client.put(f'/api/teams/{tid}', json={'names': {'abbr3': {'*': 'TOOLONG'}}})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'name_too_long'
    assert client.delete(f'/api/teams/{tid}/edits').json()['saved_names'] == {}
    assert client.get('/api/status').json()['project'] == {}


def test_details_and_pictures(client):
    assert client.get(f'/api/players/{fakegame.STAR}').json()['teams'][0]['id'] == fakegame.TEAM
    assert client.get(f'/api/leagues/{fakegame.LEAGUE}').json()['teams'][0]['id'] == fakegame.TEAM
    assert client.get('/api/teams/999').status_code == 404
    assert client.get(f'/api/image/crest/{fakegame.TEAM}?size=32').status_code == 200
    assert client.get('/api/image/crest/999').status_code == 404


def test_build_install_uninstall(client, game_dir):
    client.put(f'/api/teams/{fakegame.TEAM}', json={'names': {'full': {'*': 'Installed'}}})
    for step in ('build', 'install', 'uninstall'):
        job = client.post(f'/api/patch/{step}').json()
        assert job['kind'] == step
        wait(lambda: client.get('/api/job').json()['state'] != 'running')
        assert client.get('/api/job').json()['state'] == 'done', client.get('/api/job').json()
        if step == 'install':
            assert client.get('/api/status').json()['game']['check']['state'] == 'patched'
            assert os.path.exists(os.path.join(game_dir, 'fifa14-patch-studio.install.json'))
    assert client.get('/api/status').json()['game']['check']['state'] == 'clean'
    client.delete(f'/api/teams/{fakegame.TEAM}/edits')
    assert main.game.state == 'ready'
