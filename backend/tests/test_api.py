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


def test_first_run_setup(client, game_dir, tmp_path):
    from f14api import settings
    cfg = settings.load()
    settings.save(cfg.model_copy(update={'terms_version': None}))
    setup = client.get('/api/status').json()['setup']
    assert setup['required'] and setup['reasons'] == ['terms']
    body = {'game_dir': game_dir, 'face_pack_dirs': [' ', ''], 'terms_version': setup['terms_version']}
    r = client.post('/api/setup/apply', json={**body, 'terms_version': 0})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'terms_not_accepted'
    r = client.post('/api/setup/apply', json={**body, 'game_dir': str(tmp_path)})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'game_not_usable'
    r = client.post('/api/setup/apply', json={**body, 'build_cores': 1})
    assert r.status_code == 200, r.text
    assert r.json()['setup'] == {'required': False, 'reasons': [], 'terms_version': settings.TERMS_VERSION}
    cfg = settings.load()
    assert cfg.face_pack_dirs == [] and cfg.build_cores == 1 and main.game.state == 'ready'  # same game: not read again


def test_lists_page_filter_sort(client):
    teams = client.get('/api/teams').json()
    assert teams['total'] == 2
    assert [t['name'] for t in teams['items']] == ['Small Team FC', 'Test Athletic Club']
    team = client.get(f'/api/teams/{fakegame.TEAM}').json()  # the stadium tab (read-only)
    stadium, = team['stadiums']
    assert stadium['id'] == 3 and stadium['name'] == 'Test Ground' and stadium['capacity'] == 12345
    assert stadium['home_team']['id'] == fakegame.TEAM and team['stadium_custom_name'] == 'Custom Park'
    assert stadium['conditions'] == [{'time_of_day': 1, 'rain': True, 'snow': True},
                                     {'time_of_day': 3, 'rain': True, 'snow': False}]
    assert stadium['times'] == [] and stadium['pictures'] == []  # no stadium files in the fake game
    assert client.get('/api/preview/stadium/3.glb').status_code == 404
    assert client.get('/api/image/stadium/3/1').status_code == 404
    for row in teams['items']:  # the list's kit count follows the rule of the team's Kits tab
        kits = client.get(f"/api/teams/{row['id']}").json()['kits']
        assert row['kit_count'] == sum(1 for k in kits if k['config'] is not None or k['default'] is not None)
    assert next(t for t in teams['items'] if t['id'] == fakegame.TEAM)['kit_count'] > 0
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



def test_kit_preview_files(client):
    glb = client.get('/api/preview/mesh/shorts/0.glb')
    assert glb.status_code == 200 and glb.content[:4] == b'glTF'
    assert glb.headers['content-type'] == 'model/gltf-binary'
    assert client.get('/api/preview/texture/skin/4.png').headers['content-type'] == 'image/png'
    assert client.get('/api/preview/mesh/jersey/1.glb?collar=5').status_code == 404  # not in the game
    assert client.get('/api/preview/texture/tattoo/1.png').status_code == 404
    look = client.get(f'/api/preview/look/{fakegame.STAR}').json()
    assert look['real'] is True and look['head'] == fakegame.STAR and look['scale'] > 0  # his own face files
    assert client.get(f'/api/preview/look/{fakegame.KEEPER}').json()['real'] is False  # generic head (class 1)
    assert client.get('/api/preview/look/999999').json()['head'] == 1  # not in the game: the model
    assert client.get('/api/preview/face/0_0_0_0_0_4.png').status_code == 200
    assert client.get('/api/preview/face/x.png').status_code == 404
    mask = client.get('/api/kit-models').json()['models'][0]
    assert client.get(f'/api/image/kitmodel/{mask}?part=shorts&c1=0000ff').status_code == 200
    tid = fakegame.TEAM
    values = '{"number_font": 1, "number_color": 1, "shorts_number": true, "shorts_number_font": 1, "shorts_number_color": 1}'
    layer = client.get(f'/api/preview/kit-print/{tid}/0.png', params={'values': values, 'number': 9, 'name': 'X'})
    assert layer.status_code == 200 and layer.headers['content-type'] == 'image/png'
    generic = '{"source": "generic", "model": %d, "colors": [[0, 0, 255], [255, 255, 255]]}' % mask
    assert client.get(f'/api/preview/kit-print/{tid}/0.png', params={'part': 'shorts', 'config': generic,
                                                                    'values': values, 'number': 9}).status_code == 200
    assert client.get(f'/api/preview/kit-print/{tid}/0.png', params={'config': '{"source": "upload"}'}).status_code == 200
    assert client.get(f'/api/preview/kit-print/{tid}/0.png', params={'config': '{bad'}).status_code == 400
    assert client.get(f'/api/preview/kit-print/{tid}/0.png', params={'part': 'mini'}).status_code == 404
    assert client.get(f'/api/teams/{tid}').json()['roster'][0]['back_name']
    import base64
    import io as io_lib
    from PIL import Image
    buf = io_lib.BytesIO()
    Image.new('RGBA', (32, 32), (0, 0, 255, 255)).save(buf, 'PNG')
    body = {'config': {'source': 'generic', 'model': mask, 'colors': [[0, 0, 0], [0, 0, 0]]},
            'crest': base64.b64encode(buf.getvalue()).decode()}
    pending = client.post(f'/api/preview/kit-print/{tid}/0.png', json=body)
    assert pending.status_code == 200
    # the crest rectangle of the fake kit is u/v 0.1-0.2 of the 1024 px jersey layer
    assert Image.open(io_lib.BytesIO(pending.content)).convert('RGBA').getpixel((150, 150)) == (0, 0, 255, 255)
    assert client.post(f'/api/preview/kit-print/{tid}/0.png', json={**body, 'crest': 'remove'}).status_code == 200
    assert client.post(f'/api/preview/kit-print/{tid}/0.png', json={**body, 'crest': 'nope'}).status_code == 400

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
    # the overall follows the saved attributes everywhere (detail, list, squad of a team)
    assert r.json()['overall'] != player['overall'] and listed[0]['overall'] == r.json()['overall']
    squad = client.get(f'/api/teams/{fakegame.TEAM}').json()['roster']
    assert all(row['overall'] == r.json()['overall'] for row in squad if row['id'] == pid)
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
    rows = {x['id']: x for x in client.get('/api/countries', params={'sort': 'player_count'}).json()['items']}
    assert rows[54]['confederation'] == 1 and rows[54]['player_count'] > 0 and rows[52]['player_count'] == 0
    assert rows[cid]['player_count'] == 0
    detail = client.get('/api/countries/54').json()
    assert detail['confederation'] == 1 and detail['national_team'] is None and detail['audio'] is None
    made = client.get(f'/api/countries/{cid}').json()
    assert made['national_team'] is None
    # its database row is the one the patch writes: the model country's, with its own id and name
    assert made['raw']['nationid'] == cid and made['raw']['nationname'] == 'Free Land' and made['raw']['teamid'] == -1
    assert detail['raw']['nationid'] == 54
    assert client.get('/api/countries', params={'confederation': 1}).json()['total'] >= 2
    assert client.get('/api/countries', params={'confederation': 2}).json()['total'] == 0
    options = client.get('/api/options').json()
    assert 1 in options['confederations'] and options['levels'] and options['league_countries']
    level = options['levels'][0]
    by_level = client.get('/api/leagues', params={'level': level}).json()['items']
    assert by_level and all(lg['level'] == level for lg in by_level)
    assert all(not lg['is_new'] for lg in client.get('/api/leagues', params={'origin': 'original'}).json()['items'])
    assert all(lg['hidden'] or lg['game_hidden']
               for lg in client.get('/api/leagues', params={'status': 'hidden'}).json()['items'])
    # origin filters: 'project' (created + edited) and 'original'
    assert [x['id'] for x in client.get('/api/countries', params={'origin': 'project'}).json()['items']] == [cid]
    assert cid not in [x['id'] for x in client.get('/api/countries', params={'origin': 'original'}).json()['items']]
    # status filters: 'visible' and 'hidden'
    assert cid in [x['id'] for x in client.get('/api/countries', params={'status': 'visible'}).json()['items']]
    assert cid not in [x['id'] for x in client.get('/api/countries', params={'status': 'hidden'}).json()['items']]
    # the user's created items come first, whatever the sort
    for sort, direction in (('name', 'asc'), ('name', 'desc'), ('id', 'asc'), ('league_count', 'desc')):
        first = client.get('/api/countries', params={'sort': sort, 'dir': direction}).json()['items'][0]
        assert first['id'] == cid, (sort, direction)
    # a league can start without a country (it is added to one in the country's page)
    loose = client.post('/api/leagues', json={'names': {'full': {'*': 'No Country'}}}).json()
    assert loose['country_id'] == 0 and loose['is_new']
    client.delete(f"/api/leagues/{loose['id']}")
    league = client.post('/api/leagues', json={'names': {'full': {'*': 'Free League'}},
                                               'fields': {'countryid': cid}}).json()
    lid = league['id']
    assert lid >= 400 and league['is_new'] and league['country_id'] == cid and league['team_ids'] == []
    assert league['raw'].get('leagueid') == lid  # the Database tab shows the row the patch writes
    assert [x['id'] for x in client.get(f'/api/countries/{cid}').json()['leagues']] == [lid]
    assert client.get('/api/leagues', params={'country': cid}).json()['total'] == 1
    assert client.get('/api/leagues', params={'sort': 'id'}).json()['items'][0]['id'] == lid

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


def test_country_name_follows_names_language(client):
    """The selects and lists show a country in the names language, like its screen's title: the project's text in
    that language first, then its "All" text."""
    cid = client.post('/api/countries', json={'names': {'full': {'*': 'All Land', 'eng_us': 'English Land'}}}).json()['id']

    def names():
        title = client.get(f'/api/countries/{cid}').json()['name']
        option = next(n['name'] for n in client.get('/api/options').json()['nations'] if n['id'] == cid)
        return title, option

    try:
        client.put('/api/settings', json={'names_language': 'eng_us'})
        assert names() == ('English Land', 'English Land')
        client.put('/api/settings', json={'names_language': 'por_br'})
        assert names() == ('All Land', 'All Land')
        shown = [n['name'] for n in client.get('/api/options').json()['nations']]
        assert shown == sorted(shown, key=str.casefold)  # by the name shown, not the game's own
    finally:
        client.put('/api/settings', json={'names_language': None})
        client.delete(f'/api/countries/{cid}')


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


def test_country_flag_picture(client):
    import base64
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (30, 20), (10, 200, 30)).save(buf, 'PNG')
    bad = client.put('/api/countries/54/flag', json={'data': base64.b64encode(b'nope').decode()})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'bad_picture'
    # the preview draws the picture without saving it
    preview = client.post('/api/flag-preview', params={'size': 64}, json={'data': base64.b64encode(buf.getvalue()).decode()})
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
    assert client.post('/api/flag-preview', json={'data': 'bm9wZQ=='}).json()['detail']['code'] == 'bad_picture'
    assert not client.get('/api/countries/54').json()['own_flag']
    game_flag = client.get('/api/image/flag/54').content
    r = client.put('/api/countries/54/flag', json={'data': base64.b64encode(buf.getvalue()).decode()})
    assert r.status_code == 200 and r.json()['own_flag'] and r.json()['edited'] and r.json()['base_flag_id'] == 54
    image = client.get('/api/image/flag/54')
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert image.content != game_flag
    assert client.get('/api/image/flag/54', params={'game_only': True}).content == game_flag
    assert not client.delete('/api/countries/54/flag').json()['own_flag']
    assert client.get('/api/status').json()['project'] == {}


def test_league_logo_hidden_and_team_list(client):
    import base64
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (40, 20), (200, 30, 30)).save(buf, 'PNG')
    data = base64.b64encode(buf.getvalue()).decode()
    lid = fakegame.LEAGUE
    league = client.get(f'/api/leagues/{lid}').json()
    assert not league['hidden'] and league['own_logo'] is None and league['game_team_ids'] == [fakegame.TEAM]
    # the preview draws the picture without saving it
    preview = client.post('/api/league-logo-preview', params={'size': 64}, json={'data': data})
    assert preview.status_code == 200 and preview.headers['content-type'] == 'image/png'
    assert client.get(f'/api/leagues/{lid}').json()['own_logo'] is None
    bad = client.put(f'/api/leagues/{lid}/logo', json={'data': 'bm9wZQ=='})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'bad_picture'
    saved = client.put(f'/api/leagues/{lid}/logo', json={'data': data}).json()
    assert saved['own_logo'] and saved['has_logo'] and saved['edited']
    own = client.get(f'/api/image/league/{lid}', params={'size': 64})
    assert own.status_code == 200 and own.headers['content-type'] == 'image/png'
    row = next(x for x in client.get('/api/leagues').json()['items'] if x['id'] == lid)
    assert row['has_logo'] and not row['hidden']
    assert client.delete(f'/api/leagues/{lid}/logo').json()['own_logo'] is None

    hidden = client.put(f'/api/leagues/{lid}/hidden', json={'hidden': True}).json()
    assert hidden['hidden']
    assert next(x for x in client.get('/api/leagues').json()['items'] if x['id'] == lid)['hidden']
    assert not client.put(f'/api/leagues/{lid}/hidden', json={'hidden': False}).json()['hidden']
    assert client.put('/api/leagues/999/hidden', json={'hidden': True}).status_code == 404

    # the teams a page is editing, by id
    teams = client.get('/api/teams', params={'ids': f'{fakegame.TEAM},{fakegame.SMALL_TEAM}'}).json()
    assert {t['id'] for t in teams['items']} == {fakegame.TEAM, fakegame.SMALL_TEAM}
    assert client.get('/api/teams', params={'ids': ''}).json()['total'] == 0
    assert client.get('/api/teams', params={'ids': 'x'}).status_code == 400


def test_hide_and_league_in_several_countries(client):
    lid = fakegame.LEAGUE
    # a league in another country too: the country lists it and counts it
    r = client.put(f'/api/leagues/{lid}', json={'names': {}, 'fields': {'extra_countries': [52, 52]}})
    assert r.status_code == 200 and r.json()['saved']['extra_countries'] == [52]
    assert client.put(f'/api/leagues/{lid}', json={'names': {}, 'fields': {'extra_countries': [77]}}).json()[
        'detail']['code'] == 'field_out_of_range'  # a country that does not exist
    country = client.get('/api/countries/52').json()
    assert {x['id'] for x in country['leagues']} == {fakegame.PLAIN_LEAGUE, lid}
    row = next(x for x in client.get('/api/leagues').json()['items'] if x['id'] == lid)
    assert row['extra_countries'] == [52]

    # one Hide (as in the Street Studio): an original hidden = hidden in the game by the project
    league = client.put(f'/api/leagues/{lid}/hidden', json={'hidden': True}).json()
    assert league['hidden'] and not league['game_hidden']
    assert client.put(f'/api/leagues/{lid}/hidden', json={'hidden': False}).json()['hidden'] is False
    for cid in (54, 52):
        assert client.put(f'/api/countries/{cid}/hidden', json={'hidden': True}).json()['hidden']
    assert 54 in [x['id'] for x in client.get('/api/countries', params={'status': 'hidden'}).json()['items']]
    assert 54 not in [x['id'] for x in client.get('/api/countries', params={'status': 'visible'}).json()['items']]
    assert client.get(f'/api/leagues/{lid}').json()['hidden_by_countries']  # every country of it hidden
    assert not client.put('/api/countries/52/hidden', json={'hidden': False}).json()['hidden']
    assert not client.get(f'/api/leagues/{lid}').json()['hidden_by_countries']
    assert client.put(f'/api/teams/{fakegame.TEAM}/hidden', json={'hidden': True}).json()['hidden']
    assert next(x for x in client.get('/api/teams').json()['items'] if x['id'] == fakegame.TEAM)['hidden']
    assert client.put('/api/teams/1/hidden', json={'hidden': True}).status_code == 404


def test_league_hidden_in_one_country(client):
    """The switch on the country's league list: out of the patch in this country only, kept in it."""
    lid = fakegame.LEAGUE  # country 54
    for cid in (52, 54):  # shown (an earlier test hides them)
        client.put(f'/api/countries/{cid}/hidden', json={'hidden': False})
    r = client.put('/api/countries/52/leagues', json={'league_ids': [fakegame.PLAIN_LEAGUE, lid],
                                                      'hidden_league_ids': [lid]})
    row = next(x for x in r.json()['leagues'] if x['id'] == lid)
    assert row['hidden_in_countries'] == [52]  # still listed in the country
    assert client.get(f'/api/leagues/{lid}').json()['saved']['extra_countries'] == [52]
    # without hidden_league_ids the hidden ones stay as they are
    r = client.put('/api/countries/52/leagues', json={'league_ids': [fakegame.PLAIN_LEAGUE, lid]})
    assert next(x for x in r.json()['leagues'] if x['id'] == lid)['hidden_in_countries'] == [52]
    assert not client.get(f'/api/leagues/{lid}').json()['hidden_by_countries']  # still in the patch in 54
    assert ('league_hidden_in_countries', f'league:{lid}') not in _issues(client)
    client.put('/api/countries/54/leagues', json={'league_ids': [lid], 'hidden_league_ids': [lid]})
    assert client.get(f'/api/leagues/{lid}').json()['hidden_by_countries']  # out in every country of it
    assert ('league_hidden_in_countries', f'league:{lid}') in _issues(client)  # warned: it leaves the game
    client.put('/api/countries/54/leagues', json={'league_ids': [lid], 'hidden_league_ids': []})
    assert ('league_hidden_in_countries', f'league:{lid}') not in _issues(client)
    # removed from the country: the hidden mark there goes too
    client.put('/api/countries/52/leagues', json={'league_ids': [fakegame.PLAIN_LEAGUE]})
    assert 'hidden_in_countries' not in client.get(f'/api/leagues/{lid}').json()['saved']


def test_country_leagues_list(client):
    """Add league / remove in the country's page: the league's own country or one more country."""
    lid = fakegame.LEAGUE  # country 54
    r = client.put('/api/countries/52/leagues', json={'league_ids': [fakegame.PLAIN_LEAGUE, lid]})
    assert r.status_code == 200 and {x['id'] for x in r.json()['leagues']} == {fakegame.PLAIN_LEAGUE, lid}
    league = client.get(f'/api/leagues/{lid}').json()
    assert league['country_id'] == 54 and league['saved']['extra_countries'] == [52]
    # removed from its own country: the next one becomes its own
    client.put('/api/countries/54/leagues', json={'league_ids': []})
    league = client.get(f'/api/leagues/{lid}').json()
    assert league['country_id'] == 52 and 'extra_countries' not in league['saved']
    assert client.get('/api/countries/54').json()['leagues'] == []
    # removed from its last country: no country (hidden in the game)
    client.put('/api/countries/52/leagues', json={'league_ids': [fakegame.PLAIN_LEAGUE]})
    assert client.get(f'/api/leagues/{lid}').json()['country_id'] == 0
    # and back to a country with none: it becomes its own
    client.put('/api/countries/54/leagues', json={'league_ids': [lid]})
    assert client.get(f'/api/leagues/{lid}').json()['saved'].get('countryid') is None  # the game's again
    assert client.put('/api/countries/54/leagues', json={'league_ids': [999]}).json()['detail']['code'] ==         'unknown_league'
    rows = client.get('/api/leagues', params={'ids': f'{lid}'}).json()['items']
    assert [x['id'] for x in rows] == [lid]


def test_generate_players_creates_random_strikers(client):
    r = client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'count': 3})
    assert r.status_code == 200, r.text
    made = r.json()
    assert [p['name'] for p in made] == ['Player 01', 'Player 02', 'Player 03']
    assert all(p['is_new'] and p['position'] == 25 and p['saved']['finishing'] == 50 for p in made)
    assert all(p['saved']['face']['source'] == 'generic' for p in made)
    faces = {'0_0_0_0_0_4', '2_1_3_5_2_8'}  # the generic face textures of the fake game
    for _ in range(5):  # the face codes are drawn together: always a face texture the game has
        p = client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'count': 1}).json()[0]
        look = client.get(f"/api/preview/look/{p['id']}").json()
        assert look['face'] in faces, look
        assert client.delete(f"/api/players/{p['id']}").status_code == 200
    keepers = client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'count': 3, 'goalkeepers': 2}).json()
    assert [p['position'] for p in keepers] == [0, 0, 25]
    again = client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'count': 1}).json()
    assert again[0]['name'] == 'Player 07'  # the names already taken are skipped
    assert client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'count': 0}).status_code == 400
    placed = client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'positions': [0, 3, 7, 14]}).json()
    assert [p['position'] for p in placed] == [0, 3, 7, 14]
    assert client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'positions': [28]}).status_code == 400
    assert client.post(f'/api/teams/{fakegame.TEAM}/generate-players', json={'positions': []}).status_code == 400
    for p in [*made, *keepers, *again, *placed]:  # the project is shared by the tests: leave it as it was
        assert client.delete(f"/api/players/{p['id']}").status_code == 200


def test_team_leagues_from_the_team_screen(client):
    tid, a, b = fakegame.TEAM, fakegame.LEAGUE, fakegame.PLAIN_LEAGUE
    assert [lg['id'] for lg in client.get(f'/api/teams/{tid}').json()['leagues']] == [a]
    r = client.put(f'/api/teams/{tid}/leagues', json={'league_ids': [a, b]})
    assert r.status_code == 200, r.text
    assert sorted(lg['id'] for lg in r.json()['leagues']) == [a, b]
    assert tid in client.get(f'/api/leagues/{b}').json()['team_ids']  # the league screen sees the same list
    r = client.put(f'/api/teams/{tid}/leagues', json={'league_ids': [b]})
    assert [lg['id'] for lg in r.json()['leagues']] == [b]
    assert tid not in client.get(f'/api/leagues/{a}').json()['team_ids']
    bad = client.put(f'/api/teams/{tid}/leagues', json={'league_ids': [999999]})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'unknown_league'
    client.put(f'/api/teams/{tid}/leagues', json={'league_ids': [a]})  # back to the game's lists
    assert client.get('/api/status').json()['project'] == {}


def test_team_hidden_in_one_league(client):
    tid, a = fakegame.TEAM, fakegame.LEAGUE
    r = client.put(f'/api/teams/{tid}/leagues', json={'league_ids': [a], 'hidden_league_ids': [a]})
    assert r.status_code == 200, r.text
    assert [(lg['id'], lg['hidden']) for lg in r.json()['leagues']] == [(a, True)]
    league = client.get(f'/api/leagues/{a}').json()
    assert tid in league['team_ids'] and league['hidden_team_ids'] == [tid]  # still listed, out of the patch
    # the league screen can show it again
    client.put(f'/api/leagues/{a}/teams', json={'team_ids': league['team_ids'], 'hidden_team_ids': []})
    assert client.get(f'/api/leagues/{a}').json()['hidden_team_ids'] == []
    client.delete(f'/api/leagues/{a}/teams')
    assert client.get('/api/status').json()['project'] == {}


def test_player_position_in_a_team_from_his_screen(client):
    pid, tid = fakegame.STAR, fakegame.TEAM
    player = client.get(f'/api/players/{pid}').json()
    link = next(t for t in player['teams'] if t['id'] == tid)
    assert link['slots']  # the lineup places of the team's formation
    taken = {r['link_position']: r['id'] for r in client.get(f'/api/teams/{tid}').json()['roster']}
    other = next(s for s in link['slots'] if s in taken and taken[s] != pid)  # a place somebody else holds
    holder = taken[other]
    rows = [{'team': tid, 'jersey': link['jersey'], 'hidden': False, 'slot': other}]
    r = client.put(f'/api/players/{pid}', json={'fields': {}, 'teams': rows})
    assert r.status_code == 200, r.text
    squad = {p['id']: p['link_position'] for p in client.get(f'/api/teams/{tid}').json()['roster']}
    assert squad[pid] == other and squad[holder] == 28  # the one who had that place goes to the bench
    bad = client.put(f'/api/players/{pid}', json={'fields': {}, 'teams': [{**rows[0], 'slot': 99}]})
    assert bad.status_code == 400
    client.delete(f'/api/teams/{tid}/edits')
    client.delete(f'/api/players/{pid}/edits')


def test_bulk_delete_takes_created_and_resets_edited(client):
    a = client.post('/api/leagues', json={'names': {'full': {'*': 'Bulk A'}}}).json()['id']
    b = client.post('/api/leagues', json={'names': {'full': {'*': 'Bulk B'}}}).json()['id']
    listed = client.get('/api/leagues', params={'q': 'Bulk'}).json()
    assert {a, b} <= set(listed['own_ids'])
    r = client.post('/api/bulk-delete', json={'kind': 'league', 'ids': [a, b, a]})
    assert r.status_code == 200, r.text
    assert sorted(r.json()['deleted']) == sorted([a, b]) and r.json()['skipped'] == []
    assert client.get('/api/leagues', params={'q': 'Bulk'}).json()['own_ids'] == []
    assert client.post('/api/bulk-delete', json={'kind': 'nope', 'ids': [1]}).status_code == 400


def _issues(client):
    return {(i['code'], i['entity']) for i in client.get('/api/issues').json()['issues']}


def test_issues(client):
    tid = fakegame.TEAM
    client.put(f'/api/teams/{tid}/hidden', json={'hidden': False})  # (an earlier test leaves it hidden)
    assert client.get('/api/issues').json()['issues'] == []  # the clean game has none
    squad = client.get(f'/api/teams/{tid}').json()['roster']
    captain = client.get(f'/api/teams/{tid}').json()['values']['captainid']
    rows = [{'player': r['id'], 'jersey': r['jersey'], 'slot': r['link_position'], 'hidden': r['id'] == captain}
            for r in squad]
    rows[1]['jersey'] = rows[2]['jersey'] = 7
    r = client.put(f'/api/teams/{tid}/roster', json={'rows': rows})
    assert r.status_code == 200, r.text
    found = _issues(client)
    assert ('captain_hidden', f'team:{tid}') in found and ('duplicate_number', f'team:{tid}') in found
    client.put(f'/api/teams/{tid}/roster', json={'rows': rows[:5]})
    errors = [i for i in client.get('/api/issues').json()['issues'] if i['severity'] == 'error']
    assert [(i['code'], i['entity'], i['params']['count']) for i in errors] == [('roster_too_small', f'team:{tid}', 5)]
    assert errors[0]['name'] == 'Test Athletic Club'
    client.delete(f'/api/teams/{tid}/edits')
    # created things: a league without country and teams, a team without players or league, a player without team
    lid = client.post('/api/leagues', json={'names': {'full': {'*': 'Empty League'}}}).json()['id']
    new_team = client.post('/api/teams', json={'names': {'full': {'*': 'New FC'}}, 'template': fakegame.TEAM}).json()['id']
    found = _issues(client)
    assert {('league_without_country', f'league:{lid}'), ('league_without_teams', f'league:{lid}'),
            ('roster_too_small', f'team:{new_team}'), ('team_without_league', f'team:{new_team}')} <= found
    client.put(f'/api/leagues/{lid}/hidden', json={'hidden': True})
    assert not any(e == f'league:{lid}' for _, e in _issues(client))  # left out of the patch: not checked
    client.delete(f'/api/leagues/{lid}')
    client.delete(f'/api/teams/{new_team}')
    assert client.get('/api/issues').json()['issues'] == []
    # a hidden country: its league and the team only in it leave the game (both warned)
    client.put('/api/countries/54/hidden', json={'hidden': True})  # the country of LEAGUE, TEAM's only league
    assert _issues(client) == {('league_hidden_in_countries', f'league:{fakegame.LEAGUE}'),
                               ('team_league_hidden', f'team:{tid}')}
    # one league still in the game is enough for the team
    client.put(f'/api/leagues/{fakegame.PLAIN_LEAGUE}/teams', json={'team_ids': [fakegame.SMALL_TEAM, tid]})
    assert _issues(client) == {('league_hidden_in_countries', f'league:{fakegame.LEAGUE}')}
    # ...unless the team is left out of the patch in that league
    client.put(f'/api/leagues/{fakegame.PLAIN_LEAGUE}/teams',
               json={'team_ids': [fakegame.SMALL_TEAM, tid], 'hidden_team_ids': [tid]})
    assert ('team_league_hidden', f'team:{tid}') in _issues(client)
    client.delete(f'/api/leagues/{fakegame.PLAIN_LEAGUE}/teams')
    client.put('/api/countries/54/hidden', json={'hidden': False})
    # the user's Hide on the league itself: no league warning (wanted), but its only team is warned
    client.put(f'/api/leagues/{fakegame.LEAGUE}/hidden', json={'hidden': True})
    assert _issues(client) == {('team_league_hidden', f'team:{tid}')}
    client.put(f'/api/leagues/{fakegame.LEAGUE}/hidden', json={'hidden': False})
    assert client.get('/api/issues').json()['issues'] == []


def test_build_progress_cache_and_up_to_date(client):
    client.put(f'/api/teams/{fakegame.TEAM}', json={'names': {'full': {'*': 'Progress FC'}}})
    assert client.get('/api/status').json()['patch']['up_to_date'] is False
    durations = []
    for _ in range(2):
        client.post('/api/patch/build')
        wait(lambda: client.get('/api/job').json()['state'] != 'running')
        job = client.get('/api/job').json()
        assert job['state'] == 'done', job
        durations.append(job['result'])
        prog = client.get('/api/patch/progress').json()
        assert prog['running'] is False and prog['steps'] == ['database', 'images', 'texts', 'files']
        assert prog['step'] == 'files' and prog['elapsed'] >= 0
    first, second = durations
    assert first['cache_reused_files'] == 0 and second['cache_reused_files'] > 0  # the texts came from the cache
    assert second['files'] > 0 and second['duration_s'] >= 0
    patch = client.get('/api/status').json()['patch']
    assert patch['built'] and patch['up_to_date'] and patch['files']
    client.put(f'/api/teams/{fakegame.TEAM}', json={'names': {'full': {'*': 'Changed FC'}}})
    assert client.get('/api/status').json()['patch']['up_to_date'] is False
    assert client.post('/api/patch/build/cancel').json() == {'stopping': False}  # nothing running
    client.delete(f'/api/teams/{fakegame.TEAM}/edits')


def test_machine_and_build_settings(client):
    info = client.get('/api/machine').json()
    assert info['workers'] >= 1 and info['memory_percent_range'] == [10, 90]
    cfg = client.put('/api/settings', json={'build_cores': 1, 'build_memory_percent': 500}).json()
    assert cfg['build_cores'] == 1 and cfg['build_memory_percent'] == 90  # brought into range
    assert client.get('/api/machine').json()['workers'] == 1
    cfg = client.put('/api/settings', json={'build_cores': None, 'build_memory_percent': None}).json()
    assert cfg['build_cores'] is None and cfg['build_memory_percent'] is None


def test_settings_folders_logs_and_face_check(client, tmp_path):
    folders = client.get('/api/status').json()['folders']
    assert folders['project'] == folders['default_project'] and folders['backups'].endswith('fifa14-patch-studio-backup')
    other = str(tmp_path / 'other project')
    client.put('/api/settings', json={'project_dir': other})
    assert client.get('/api/status').json()['folders']['project'] == other
    assert os.path.isfile(os.path.join(other, 'project.sqlite'))  # an empty project starts there
    assert client.get('/api/status').json()['project'] == {}
    assert client.put('/api/settings', json={'project_dir': ''}).json()['project_dir'] is None  # back to the default
    report = client.get('/api/logs/report')
    assert report.status_code == 200 and 'support report' in report.text and '== project' in report.text
    packs = client.post('/api/facepacks/check', json={'folders': [str(tmp_path / 'nothing')]}).json()['packs']
    assert packs == [{'index': 0, 'folder': str(tmp_path / 'nothing'), 'name': 'nothing', 'count': 0,
                      'warnings': [], 'error': 'no_faces'}]


def test_face_folder_with_several_packs_is_named_after_the_folder(client, tmp_path):
    """Like the Street Studio: every pack of a folder set is "<folder> / <pack>"."""
    versions = tmp_path / 'others'
    for name in ('one', 'two'):
        (versions / name / 'heads').mkdir(parents=True)
        (versions / name / 'faces').mkdir()
    packs = client.post('/api/facepacks/check', json={'folders': [str(versions)]}).json()['packs']
    assert sorted(p['name'] for p in packs) == ['others / one', 'others / two']


def test_squad_marks_real_faces(client):
    """The squad's face icon: the game's own face, or the one the project gives a player (a copy of another's)."""
    copy = client.post('/api/players', json={'fields': {'name.common': 'Copy'}, 'template': fakegame.STAR,
                                             'team': fakegame.TEAM})
    assert copy.status_code == 200, copy.text
    made = client.post('/api/players', json={'fields': {'name.common': 'Plain'}, 'team': fakegame.TEAM}).json()
    faces = {r['id']: r['has_face'] for r in client.get(f'/api/teams/{fakegame.TEAM}').json()['roster']}
    assert faces[copy.json()['id']] is True  # a created player with another player's face
    assert faces[made['id']] is False  # a generic face
    assert faces.get(fakegame.STAR, True) is True
    # the players list's face filter follows the same rule
    real = {r['id'] for r in client.get('/api/players', params={'face': 'yes', 'size': 200}).json()['items']}
    plain = {r['id'] for r in client.get('/api/players', params={'face': 'no', 'size': 200}).json()['items']}
    assert copy.json()['id'] in real and made['id'] in plain and not real & plain
    for pid in (copy.json()['id'], made['id']):  # the other tests count on the ids from 300001
        assert client.delete(f'/api/players/{pid}').status_code == 200


def test_entities_send_when_they_were_created_and_changed(client):
    tid, pid = fakegame.TEAM, fakegame.STAR
    team = client.delete(f'/api/teams/{tid}/edits').json()  # the other tests leave it changed
    assert team['created_at'] is None and team['updated_at'] is None  # the game's, not changed
    saved = client.put(f'/api/teams/{tid}', json={'names': {'abbr15': {'*': 'A01'}}}).json()
    # a game team changed by the project: only the date it was changed (the project did not create it)
    assert saved['created_at'] is None and saved['updated_at'].endswith('Z')
    listed = next(x for x in client.get('/api/teams').json()['items'] if x['id'] == tid)
    assert (listed['created_at'], listed['updated_at']) == (None, saved['updated_at'])
    player = client.put(f'/api/players/{pid}', json={'fields': {'height': 181}}).json()
    assert player['created_at'] is None and player['updated_at']
    # the lists sort by both dates; the newest first, the entities without dates (the game's) last either way
    for kind, eid in (('teams', tid), ('players', pid)):
        for direction in ('desc', 'asc'):
            out = client.get(f'/api/{kind}', params={'sort': 'updated_at', 'dir': direction}).json()
            assert (out['sort'], out['dir']) == ('updated_at', direction) and out['items'][0]['id'] == eid
        assert client.get(f'/api/{kind}', params={'sort': 'created_at'}).json()['sort'] == 'created_at'
    for kind in ('leagues', 'stadiums', 'countries'):
        assert client.get(f'/api/{kind}', params={'sort': 'updated_at'}).json()['sort'] == 'updated_at'
    assert client.delete(f'/api/teams/{tid}/edits').json()['created_at'] is None  # the game's again


def test_stadiums_list_detail_save_and_team_stadium(client):
    client.delete('/api/stadiums/3/edits')
    client.put(f'/api/teams/{fakegame.SMALL_TEAM}/stadium', json={'stadium': None})
    listed = client.get('/api/stadiums').json()
    row = next(s for s in listed['items'] if s['id'] == 3)
    assert (row['name'], row['capacity'], row['team_count'], row['edited']) == ('Test Ground', 12345, 1, False)
    detail = client.get('/api/stadiums/3').json()
    assert detail['values']['capacity'] == 12345 and [t['id'] for t in detail['teams']] == [fakegame.TEAM]
    assert detail['teams'][0]['stadium_custom_name'] == 'Custom Park'
    saved = client.put('/api/stadiums/3', json={'names': {'full': {'*': 'A01 Arena'}},
                                                'fields': {'capacity': 50000, 'yearbuilt': 1901}}).json()
    assert saved['saved'] == {'capacity': 50000} and saved['capacity'] == 50000 and saved['edited']
    # shown: the database name (the one the game shows); the language text is kept apart
    assert saved['name'] == 'Test Ground' and saved['names']['full'] == 'A01 Arena'
    assert saved['created_at'] is None and saved['updated_at']
    renamed = client.put('/api/stadiums/3', json={'names': {'full': {'*': 'A01 Arena'}},
                                                  'fields': {'name': 'A01 Ground', 'capacity': 50000}}).json()
    assert renamed['name'] == 'A01 Ground'
    row = next(s for s in client.get('/api/stadiums').json()['items'] if s['id'] == 3)
    assert (row['name'], row['language_name']) == ('A01 Ground', 'A01 Arena')
    assert client.put('/api/stadiums/3', json={'fields': {'timeofday1': 2}}).status_code == 400
    assert client.get('/api/stadiums', params={'origin': 'project'}).json()['items'][0]['capacity'] == 50000
    # a team moved to the stadium: listed there, and the team's stadium tab shows it
    team = client.put(f'/api/teams/{fakegame.SMALL_TEAM}/stadium', json={'stadium': 3}).json()
    assert team['stadium_ids'] == [3] and team['stadium_changed'] and team['edited']
    assert client.get('/api/stadiums/3').json()['team_count'] == 2
    assert client.put(f'/api/teams/{fakegame.SMALL_TEAM}/stadium', json={'stadium': 999}).status_code == 400
    back = client.put(f'/api/teams/{fakegame.SMALL_TEAM}/stadium', json={'stadium': None}).json()
    assert back['stadium_ids'] == [] and not back['stadium_changed']
    assert client.delete('/api/stadiums/3/edits').json()['saved'] == {}
