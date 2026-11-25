"""Teams through the API: create (from scratch or a copy), squad and lineup, crest, kits, delete."""
import base64
import io

import fakegame
from PIL import Image

from conftest import wait


def _b64(color, size=(32, 32)) -> str:
    buf = io.BytesIO()
    Image.new('RGBA', size, color + (255,)).save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _build(client):
    client.post('/api/patch/build')
    wait(lambda: client.get('/api/job').json()['state'] != 'running')
    return client.get('/api/job').json()


def test_team_from_scratch(client):
    r = client.post('/api/teams', json={'names': {'full': {'*': ''}}})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'name_required'
    team = client.post('/api/teams', json={
        'names': {'full': {'*': 'Scratch United'}}, 'template': fakegame.TEAM,
        'fields': {'teamcolor1': [0, 0, 200], 'teamcolor2': [255, 255, 255]},
        'league_ids': [fakegame.PLAIN_LEAGUE]}).json()
    tid = team['id']
    assert tid == 131001 and team['is_new'] and team['roster'] == [] and team['template'] == fakegame.TEAM
    assert not team['copied'] and [k['default'] for k in team['kits']] == ['generic', 'generic', 'generic', None]
    assert len(team['formations']) == 2 and team['values']['formation'] == 13
    league = client.get(f'/api/leagues/{fakegame.PLAIN_LEAGUE}').json()
    assert tid in league['team_ids']
    # new teams come first in the list
    assert client.get('/api/teams').json()['items'][0]['id'] == tid
    # the plain crest and the generic minikit are drawn for the screen
    assert client.get(f'/api/image/crest/{tid}').headers['content-type'] == 'image/png'
    assert client.get(f'/api/image/kit/{tid}/0').status_code == 200
    assert client.get(f'/api/image/kit/{tid}/0?part=jersey').status_code == 200

    # without players the patch cannot be built
    job = _build(client)
    assert job['state'] == 'error' and 'team_too_few_players' in str(job)

    source = client.get(f'/api/teams/{fakegame.TEAM}').json()['roster']
    rows = [{'player': p['id'], 'jersey': i + 1, 'slot': 28} for i, p in enumerate(source[:14])]
    r = client.put(f'/api/teams/{tid}/roster', json={'rows': rows + [rows[0]]})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'duplicate_player'
    team = client.put(f'/api/teams/{tid}/roster', json={'rows': rows}).json()
    assert [p['id'] for p in team['roster']] == [r['player'] for r in rows] and team['roster_changed']
    team = client.put(f'/api/teams/{tid}', json={'names': {'full': {'*': 'Scratch United'}},
                                                  'fields': {'formation': 8, 'captainid': rows[3]['player']}}).json()
    assert team['saved']['formation'] == 8

    # kits: a generic one with two colors, an uploaded one, then back to the default
    r = client.put(f'/api/teams/{tid}/kits/0', json={'config': {'source': 'generic', 'model': 1, 'colors': [[1, 2, 3]]}})
    assert r.status_code == 400
    team = client.put(f'/api/teams/{tid}/kits/0', json={
        'config': {'source': 'generic', 'model': 7600, 'colors': [[255, 220, 0], [0, 0, 0]]}}).json()
    assert team['kits'][0]['config']['model'] == 7600
    team = client.put(f'/api/teams/{tid}/kits/1', json={
        'config': {'source': 'upload', 'collar': 4}, 'pictures': {'jersey': _b64((10, 200, 10)), 'mini': _b64((1, 2, 3))}}).json()
    assert team['kits'][1]['pictures']['jersey'] and team['kits'][1]['pictures']['mini']
    jersey = Image.open(io.BytesIO(client.get(f'/api/image/kit/{tid}/1?part=jersey').content)).convert('RGB')
    assert jersey.getpixel((3, 3)) == (10, 200, 10)
    team = client.put(f'/api/teams/{tid}/crest', json={'data': _b64((0, 150, 0))}).json()
    assert team['own_crest']

    job = _build(client)
    assert job['state'] == 'done', job
    assert job['result']['database']['created']['team'] == 1

    team = client.put(f'/api/teams/{tid}/kits/1', json={'config': None}).json()
    assert team['kits'][1]['config'] is None and not team['kits'][1]['pictures']['jersey']
    assert client.delete(f'/api/teams/{fakegame.TEAM}').status_code == 400
    assert client.delete(f'/api/teams/{tid}').json() == {'deleted': tid}
    assert tid not in client.get(f'/api/leagues/{fakegame.PLAIN_LEAGUE}').json()['team_ids']
    assert client.get(f'/api/teams/{tid}').status_code == 404


def test_copied_team_and_game_team_squad(client):
    team = client.post('/api/teams', json={'names': {'full': {'*': 'Copy FC'}}, 'template': fakegame.TEAM,
                                           'copy': True, 'copy_squad': True}).json()
    tid = team['id']
    original = client.get(f'/api/teams/{fakegame.TEAM}').json()
    assert [p['id'] for p in team['roster']] == [p['id'] for p in original['roster']]
    assert team['copied'] and [k['default'] for k in team['kits']][:3] == ['game', 'game', 'game']
    no_squad = client.post('/api/teams', json={'names': {'full': {'*': 'Copy Two'}}, 'template': fakegame.TEAM,
                                               'copy': True}).json()
    assert no_squad['roster'] == [] and no_squad['id'] == tid + 1

    # a squad of a game team: changed, then the game's again
    rows = [{'player': p['id'], 'jersey': p['jersey'], 'slot': 29} for p in original['roster'][:12]]
    assert len(client.put(f'/api/teams/{fakegame.TEAM}/roster', json={'rows': rows}).json()['roster']) == 12
    back = client.put(f'/api/teams/{fakegame.TEAM}/roster', json={'rows': None}).json()
    assert len(back['roster']) == len(original['roster']) and not back['roster_changed']
    for t in (tid, tid + 1):
        client.delete(f'/api/teams/{t}')


def test_extra_kits_are_listed_when_set(client):
    team = client.get(f'/api/teams/{fakegame.TEAM}').json()
    assert [k['kind'] for k in team['kits']] == [0, 1, 2, 3]
    team = client.put(f'/api/teams/{fakegame.TEAM}/kits/7', json={
        'config': {'source': 'generic', 'model': 7500, 'colors': [[1, 2, 3], [4, 5, 6]]}}).json()
    assert [k['kind'] for k in team['kits']] == [0, 1, 2, 3, 7]
    assert client.put(f'/api/teams/{fakegame.TEAM}/kits/6', json={'config': None}).status_code == 404
    team = client.put(f'/api/teams/{fakegame.TEAM}/kits/7', json={'config': None}).json()
    assert [k['kind'] for k in team['kits']] == [0, 1, 2, 3]


def test_kit_print_options(client):
    team = client.get(f'/api/teams/{fakegame.TEAM}').json()
    assert team['kits'][0]['print']['collar'] == 3 and team['kits'][0]['print']['number_color'] == 1
    r = client.put(f'/api/teams/{fakegame.TEAM}/kits/0', json={'config': {'source': 'keep', 'print': {'number_color': 25}}})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'field_out_of_range'
    r = client.put(f'/api/teams/{fakegame.TEAM}/kits/0', json={'config': {'source': 'keep', 'print': {'bogus': 1}}})
    assert r.status_code == 400
    team = client.put(f'/api/teams/{fakegame.TEAM}/kits/0', json={'config': {
        'source': 'keep', 'collar': 15, 'print': {'name_color': [1, 2, 3], 'front_number': 1, 'name_layout': 1}}}).json()
    assert team['kits'][0]['config'] == {'source': 'keep', 'collar': 15,
                                         'print': {'name_color': [1, 2, 3], 'front_number': True, 'name_layout': 1}}
    client.put(f'/api/teams/{fakegame.TEAM}/kits/0', json={'config': None})
    fonts = client.get('/api/kit-fonts').json()
    assert fonts['name'] == [{'id': 2, 'name': None}] and fonts['number'] == {'1': [1, 2]}
    assert fonts['colors'][0] == {'id': 1, 'rgb': [250, 250, 250]}  # the color the digits really show


def test_blank_team(client):
    """From scratch without a template: blank fields (the tactics at 50), no stadium, warnings, out of the patch."""
    team = client.post('/api/teams', json={'names': {'full': {'*': 'A01 Blank'}},
                                           'league_ids': [fakegame.PLAIN_LEAGUE]}).json()
    tid = team['id']
    assert team['blank'] and team['template'] is None and not team['copied'] and team['roster'] == []
    values = team['values']
    assert all(values[f] is None for f in ('teamcolor1', 'teamcolor2', 'teamcolor3', 'domesticprestige',
                                           'internationalprestige', 'rivalteam', 'transferbudget', 'balltype',
                                           'formation', 'captainid'))
    assert values['busbuildupspeed'] == 50 and values['buspositioning'] == 1
    assert team['stadium_ids'] == [] and team['overall'] is None
    assert client.get(f'/api/image/crest/{tid}').status_code == 200  # the plain crest, in neutral colors
    issues = {i['code']: i for i in client.get('/api/issues').json()['issues'] if i['id'] == tid}
    assert set(issues) >= {'team_missing_fields', 'team_without_stadium', 'roster_too_small'}
    assert all(i['severity'] == 'warning' for i in issues.values())
    assert issues['team_missing_fields']['params']['count'] == 9
    job = _build(client)
    assert job['state'] == 'done', job
    assert 'team' not in job['result']['database'].get('created', {})


def test_copy_goes_into_the_leagues_and_its_crest_can_be_removed(client):
    """A copy joins the leagues of the team it copies: out of the patch where the league already has as many teams
    as in the game; its copied crest can give way to the plain one (field plain_crest)."""
    team = client.post('/api/teams', json={'names': {'full': {'*': 'A01 Copy'}}, 'template': fakegame.TEAM,
                                           'copy': True}).json()
    tid = team['id']
    league = client.get(f'/api/leagues/{fakegame.LEAGUE}').json()
    assert tid in league['team_ids'] and tid in league['hidden_team_ids']  # the game's league already had its 1 team
    # a league the user created is never full: the copy is in the patch there
    created = client.post('/api/leagues', json={'names': {'full': {'*': 'A01 League'}}}).json()['id']
    client.put(f'/api/leagues/{created}/teams', json={'team_ids': [fakegame.TEAM]})
    other = client.post('/api/teams', json={'names': {'full': {'*': 'A02 Copy'}}, 'template': fakegame.TEAM,
                                            'copy': True}).json()['id']
    room = client.get(f'/api/leagues/{created}').json()
    assert other in room['team_ids'] and other not in room['hidden_team_ids']

    copied = client.get(f'/api/image/crest/{tid}').content
    team = client.put(f'/api/teams/{tid}', json={'names': {'full': {'*': 'A01 Copy'}},
                                                  'fields': {'plain_crest': 1}}).json()
    assert team['saved']['plain_crest'] == 1
    assert client.get(f'/api/image/crest/{tid}').content != copied
    assert client.get(f'/api/image/crest/{tid}?plain=false').content == copied


def test_country_and_league_copies(client):
    blank = client.post('/api/countries', json={'names': {'full': {'*': 'A01 Country'}}}).json()
    assert blank['saved'] == {} and blank['audio'] is None
    country = client.post('/api/countries', json={'names': {'full': {'*': 'A02 Country'}}, 'template': 54}).json()
    assert country['saved'] == {'flag_from': 54, 'copy_of': 54}
    assert country['audio'] == {'nationid': country['id'], 'chantregionindex': 9, 'crowdbedsregionindex': 8}
    again = client.post('/api/countries', json={'names': {'full': {'*': 'A03 Country'}},
                                                'template': country['id']}).json()
    assert again['saved'] == {'flag_from': 54, 'copy_of': 54}  # a copy of a copy: the game country's rows
    scratch = client.post('/api/leagues', json={'names': {'full': {'*': 'A00 League'}}}).json()
    assert 'level' not in scratch['saved'] or scratch['saved']['level'] != scratch['values']['level']
    source = client.get(f'/api/leagues/{fakegame.LEAGUE}').json()
    league = client.post('/api/leagues', json={'names': {'full': {'*': 'A03 League'}}, 'template': fakegame.LEAGUE,
                                               'copy_teams': True}).json()
    assert {**league['values'], **league['saved']}['countryid'] == 54 and fakegame.TEAM in league['team_ids']
    assert (league['team_ids'], league['hidden_team_ids']) == (source['team_ids'], source['hidden_team_ids'])
    assert league['own_logo']
    empty = client.post('/api/leagues', json={'names': {'full': {'*': 'A04 League'}}, 'template': fakegame.LEAGUE}).json()
    assert empty['team_ids'] == [] and {**empty['values'], **empty['saved']}['countryid'] == 54
