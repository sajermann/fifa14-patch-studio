"""Export and import through the API: the tree of what goes, the zip, and the zip coming back with new ids."""
import io
import zipfile

import fakegame
from conftest import wait


def test_export_then_import_into_the_same_project(client):
    team = client.post('/api/teams', json={'names': {'full': {'*': 'T01 Export'}}, 'template': fakegame.TEAM,
                                           'league_ids': [fakegame.PLAIN_LEAGUE]}).json()
    tid = team['id']
    a = client.post('/api/players', json={'fields': {'name.common': 'A01 Export'}, 'template': fakegame.STAR}).json()
    b = client.post('/api/players', json={'fields': {'name.common': 'A02 Export'}, 'template': fakegame.STAR}).json()
    rows = [{'player': a['id'], 'jersey': 10, 'slot': 25}, {'player': b['id'], 'jersey': 1, 'slot': 0}]
    assert client.put(f'/api/teams/{tid}/roster', json={'rows': rows}).status_code == 200

    r = client.post('/api/share/export', json={'kind': 'team', 'id': tid})
    assert r.status_code == 200, r.text
    tree = r.json()
    assert tree['roots'] == [f'team:{tid}']
    assert set(tree['nodes'][f'team:{tid}']['children']) == {f"player:{a['id']}", f"player:{b['id']}"}
    assert tree['nodes'][f"player:{a['id']}"]['name'] == 'A01 Export'

    # the second player left out: the zip has the team and the first one only, and the team does not point at him
    keys = [f'team:{tid}', f"player:{a['id']}"]
    r = client.post(f"/api/share/export/{tree['token']}/zip", json={'keys': keys})
    assert r.status_code == 200 and 'T01-Export.zip' in r.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        import json
        manifest = json.loads(z.read('manifest.json'))
    assert manifest['format'] == 'fifa14-patch-studio'
    assert [(i['kind'], i['id']) for i in manifest['items']] == [('team', tid), ('player', a['id'])]
    squad = [row['player_id'] for row in manifest['items'][0]['tables']['team_rosters']]
    assert squad == [a['id']]

    r = client.post('/api/share/inspect', content=r.content, headers={'content-type': 'application/zip'})
    assert r.status_code == 200, r.text
    found = r.json()
    assert found['origin'] == 'own'
    new_team = found['nodes'][f'team:{tid}']
    new_player = found['nodes'][f"player:{a['id']}"]
    assert new_team['reason'] == 'taken' and new_team['new_id'] != tid
    assert new_player['reason'] == 'taken' and new_player['new_id'] not in (a['id'], b['id'])
    r = client.post('/api/share/apply', json={'token': found['token'], 'keys': list(found['nodes'])})
    assert r.status_code == 200, r.text
    assert r.json()['kind'] == 'import'
    wait(lambda: client.get('/api/job').json()['state'] != 'running')
    job = client.get('/api/job').json()
    assert job['state'] == 'done', job
    assert job['result']['count'] == 2
    prog = client.get('/api/share/apply/progress').json()
    assert not prog['running'] and prog['step'] == 'save' and prog['result']['count'] == 2 and prog['elapsed'] >= 0

    copy = client.get(f"/api/teams/{new_team['new_id']}").json()
    assert [p['id'] for p in copy['roster']] == [new_player['new_id']]
    assert new_team['new_id'] in client.get(f'/api/leagues/{fakegame.PLAIN_LEAGUE}').json()['team_ids']
    assert client.get(f"/api/players/{new_player['new_id']}").json()['saved']['name.common'] == 'A01 Export'
    # the token is used up
    assert client.post('/api/share/apply', json={'token': found['token'], 'keys': []}).status_code == 404

    # the other tests count on the ids they create: everything created here leaves the project
    for kind, ids in (('team', [tid, new_team['new_id']]), ('player', [a['id'], b['id'], new_player['new_id']])):
        r = client.post('/api/bulk-delete', json={'kind': kind, 'ids': ids})
        assert sorted(r.json()['deleted']) == sorted(ids), r.json()


def test_import_refuses_what_it_does_not_know(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('other.txt', 'x')
    r = client.post('/api/share/inspect', content=buf.getvalue())
    assert r.status_code == 400 and r.json()['detail']['code'] == 'unknown_zip'
    r = client.post('/api/share/inspect', content=b'not a zip')
    assert r.status_code == 400 and r.json()['detail']['code'] == 'not_a_zip'


def test_an_untouched_game_entity_has_nothing_to_export(client):
    r = client.post('/api/share/export', json={'kind': 'player', 'id': fakegame.STAR})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'share_nothing_to_export'
