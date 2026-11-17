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


def test_player_fields_crud(client):
    pid = fakegame.STAR
    player = client.get(f'/api/players/{pid}').json()
    assert player['values']['name.common'] == 'Starman' and player['values']['height'] == 180
    assert player['saved'] == {} and not player['edited']
    r = client.put(f'/api/players/{pid}', json={'fields': {
        'name.common': 'Renamed', 'height': 180, 'birthdate': '1991-02-03', 'finishing': 99}})
    assert r.status_code == 200, r.text
    assert r.json()['saved'] == {'name.common': 'Renamed', 'birthdate': '1991-02-03', 'finishing': 99}
    assert r.json()['name'] == 'Renamed' and r.json()['edited']
    listed = client.get('/api/players', params={'q': 'renamed'}).json()['items']
    assert [p['id'] for p in listed] == [pid] and listed[0]['edited']
    for body, code in (({'height': 300}, 'field_out_of_range'), ({'nationality': 999}, 'field_out_of_range'),
                       ({'bogus': 1}, 'field_unknown_field'), ({'birthdate': 'x'}, 'field_bad_value')):
        bad = client.put(f'/api/players/{pid}', json={'fields': body})
        assert bad.status_code == 400 and bad.json()['detail']['code'] == code
    assert client.delete(f'/api/players/{pid}/edits').json()['saved'] == {}
    assert client.get('/api/status').json()['project'] == {}


def test_league_and_team_fields(client):
    lid, tid = fakegame.LEAGUE, fakegame.TEAM
    r = client.put(f'/api/leagues/{lid}', json={'names': {'abbr15': {'*': 'Short League'}},
                                                'fields': {'leaguename': 'DB Name', 'level': 2}})
    assert r.status_code == 200, r.text
    assert r.json()['saved_names'] == {'abbr15': {'*': 'Short League'}}
    assert r.json()['saved'] == {'leaguename': 'DB Name', 'level': 2}
    assert client.get('/api/leagues').json()['items'][0]['edited'] in (True, False)
    assert client.get(f'/api/leagues/{lid}').json()['edited']
    too_long = client.put(f'/api/leagues/{lid}', json={'names': {'abbr15': {'*': 'x' * 16}}})
    assert too_long.json()['detail']['code'] == 'name_too_long'
    team = client.put(f'/api/teams/{tid}', json={'fields': {'teamcolor1': [1, 2, 3], 'captainid': 8004}}).json()
    assert team['saved'] == {'teamcolor1': [1, 2, 3], 'captainid': 8004}
    outsider = client.put(f'/api/teams/{tid}', json={'fields': {'captainid': fakegame.SMALL_TEAM_PLAYERS[1]}})
    assert outsider.json()['detail']['code'] == 'field_out_of_range'
    options = client.get('/api/options').json()
    assert {n['id'] for n in options['nations']} == {52, 54} and len(options['teams']) == 2
    client.delete(f'/api/leagues/{lid}/edits')
    client.delete(f'/api/teams/{tid}/edits')
    assert client.get('/api/status').json()['project'] == {}


def test_free_country_and_league_crud(client):
    r = client.post('/api/countries', json={'names': {'full': {'*': ''}}})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'name_required'
    country = client.post('/api/countries', json={'names': {'full': {'*': 'Free Land'}, 'abbr3': {'*': 'FRL'}},
                                                  'fields': {'flag_from': 54}}).json()
    cid = country['id']
    assert country['is_new'] and country['name'] == 'Free Land' and country['saved']['flag_from'] == 54
    assert client.get('/api/countries', params={'q': 'free'}).json()['total'] == 1
    bad = client.post('/api/leagues', json={'names': {'full': {'*': 'No Country'}}})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'field_out_of_range'
    league = client.post('/api/leagues', json={'names': {'full': {'*': 'Free League'}},
                                               'fields': {'countryid': cid}}).json()
    lid = league['id']
    assert lid >= 400 and league['is_new'] and league['country_id'] == cid and league['team_ids'] == []
    assert [x['id'] for x in client.get(f'/api/countries/{cid}').json()['leagues']] == [lid]
    assert client.get('/api/leagues', params={'country': cid}).json()['total'] == 1

    # a team in several leagues: the free league and its own
    r = client.put(f'/api/leagues/{lid}/teams', json={'team_ids': [fakegame.SMALL_TEAM, fakegame.TEAM]})
    assert r.status_code == 200 and r.json()['team_ids'] == [fakegame.SMALL_TEAM, fakegame.TEAM]
    team = client.get(f'/api/teams/{fakegame.TEAM}').json()
    assert {x['id'] for x in team['leagues']} == {fakegame.LEAGUE, lid}
    assert client.put(f'/api/leagues/{lid}/teams', json={'team_ids': [1]}).json()['detail']['code'] == 'unknown_team'
    # the teams of an original league can change too, and come back
    r = client.put(f'/api/leagues/{fakegame.LEAGUE}/teams', json={'team_ids': [fakegame.SMALL_TEAM]})
    assert r.json()['team_ids'] == [fakegame.SMALL_TEAM] and r.json()['teams_changed']
    assert client.delete(f'/api/leagues/{fakegame.LEAGUE}/teams').json()['team_ids'] == [fakegame.TEAM]

    assert client.get('/api/limits').json()['league_links'] == 4
    r = client.delete(f'/api/countries/{cid}')
    assert r.status_code == 409 and r.json()['detail']['code'] == 'country_has_leagues'
    assert client.delete(f'/api/leagues/{fakegame.LEAGUE}').json()['detail']['code'] == 'not_created'
    assert client.delete(f'/api/leagues/{lid}').json() == {'deleted': lid}
    assert client.delete(f'/api/countries/{cid}').json() == {'deleted': cid}
    assert client.get('/api/status').json()['project'] == {}


def test_country_limit(client, monkeypatch):
    from f14mod import fifa14
    monkeypatch.setattr(fifa14, 'MAX_NATION_ID', 0)
    r = client.post('/api/countries', json={'names': {'full': {'*': 'Too Many'}}})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'limit_countries'


def test_original_country_names_and_flag(client):
    countries = client.get('/api/countries', params={'q': 'nowhereland'}).json()['items']
    assert [(c['id'], c['name'], c['has_flag']) for c in countries] == [(54, 'Nowhereland of Tests', True)]
    assert client.get('/api/image/flag/54').status_code == 200
    assert client.get('/api/image/flag/52').status_code == 404
    country = client.get('/api/countries/54').json()
    assert not country['is_new'] and country['original_names']['abbr3']['eng_us'] == 'NWL'
    saved = client.put('/api/countries/54', json={'names': {'full': {'por_br': 'Terra Nenhuma'}},
                                                  'fields': {'flag_from': 52}}).json()
    assert saved['edited'] and saved['saved_names'] == {'full': {'por_br': 'Terra Nenhuma'}} and saved['flag_id'] == 52
    assert client.delete('/api/countries/54').json()['detail']['code'] == 'not_created'
    restored = client.delete('/api/countries/54/edits').json()
    assert not restored['edited'] and restored['flag_id'] == 54
