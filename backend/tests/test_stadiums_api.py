"""Stadiums the user creates, through the API: a copy of a game stadium or a downloaded stadium's folder, its scene,
its menu picture, a team moved to it, and delete."""
import base64
import io
import os

import fakegame
from PIL import Image


def _png(color) -> str:
    buf = io.BytesIO()
    Image.new('RGB', (80, 40), color).save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _folder(root, sid=158):
    """A downloaded stadium's folder: scene, day and night textures, crowd and glares."""
    folder = os.path.join(root, 'A01 Stadium')
    for name, data in ((f'stadium_{sid}.rx3', b'A01 scene'), (f'stadium_{sid}_1_textures.rx3', b'day'),
                       (f'stadium_{sid}_3_textures.rx3', b'night'), (f'crowd_{sid}_1.dat', b'crowd'),
                       (f'glares_{sid}_1.lnx', f'<Effect name="glares_{sid}_1">'.encode())):
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(data)
    return folder


def test_created_stadium_crud(client, tmp_path):
    assert client.post('/api/stadiums', json={'names': {'full': {'*': ' '}}}).status_code == 400  # name required
    bad = client.post('/api/stadiums', json={'names': {'full': {'*': 'A01'}}, 'folder': str(tmp_path)})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'stadium_no_stadium'
    assert client.post('/api/stadiums', json={'names': {'full': {'*': 'A01'}}, 'template': 9999}).status_code == 400

    # a copy of the game's stadium 3
    r = client.post('/api/stadiums', json={'names': {'full': {'*': 'A01 Copy'}}, 'template': 3})
    assert r.status_code == 200, r.text
    copy = r.json()
    assert copy['id'] == 266 and copy['is_new'] and copy['template'] == 3 and copy['template_name'] == 'Test Ground'
    assert copy['name'] == 'A01 Copy' and copy['capacity'] == 12345 and copy['home_team'] is None
    assert not copy['own_scene'] and copy['files'] == []  # the fake game's stadium has no scene

    # from a folder: the folder's stadium (158) is not in the fake game, so the generic row is the template
    r = client.post('/api/stadiums', json={'names': {'full': {'*': 'A02 Folder'}}, 'folder': _folder(str(tmp_path))})
    assert r.status_code == 200, r.text
    own = r.json()
    sid = own['id']
    assert sid == 267 and own['own_scene'] and own['times'] == [1, 3]
    assert [f['path'] for f in own['files']] == [f'data/sceneassets/crowdplacement/crowd_{sid}_1.dat',
                                                 f'data/sceneassets/fx/glares_{sid}_1.lnx',
                                                 f'data/sceneassets/stadium/stadium_{sid}.rx3',
                                                 f'data/sceneassets/stadium/stadium_{sid}_1_textures.rx3',
                                                 f'data/sceneassets/stadium/stadium_{sid}_3_textures.rx3']

    listed = {s['id']: s for s in client.get('/api/stadiums', params={'origin': 'project'}).json()['items']}
    assert listed[sid]['is_new'] and listed[sid]['has_3d'] and listed[sid]['name'] == 'A02 Folder'
    assert {s['id'] for s in client.get('/api/options').json()['stadiums']} >= {266, sid}

    # the edit form, a menu picture, a team moved to it
    r = client.put(f'/api/stadiums/{sid}', json={'names': {'full': {'*': 'A02 Renamed'}}, 'fields': {'capacity': 1000}})
    assert r.status_code == 200 and r.json()['name'] == 'A02 Renamed' and r.json()['capacity'] == 1000
    r = client.put(f'/api/stadiums/{sid}/picture/1', json={'data': _png((0, 0, 200))})
    assert r.json()['own_pictures'] == [1]
    assert client.get(f'/api/image/stadium/{sid}/1').headers['content-type'] == 'image/png'
    assert client.put(f'/api/stadiums/{sid}/picture/2', json={'data': _png((0, 0, 200))}).status_code == 404
    # a game stadium's picture too: it becomes edited, and back to the game's
    r = client.put('/api/stadiums/3/picture/0', json={'data': _png((0, 200, 0))})
    assert r.json()['own_pictures'] == [0] and r.json()['edited']
    assert client.delete('/api/stadiums/3/picture/0').json()['own_pictures'] == []
    assert client.put(f'/api/teams/{fakegame.SMALL_TEAM}/stadium', json={'stadium': sid}).status_code == 200
    assert [t['id'] for t in client.get(f'/api/stadiums/{sid}').json()['teams']] == [fakegame.SMALL_TEAM]

    # the scene back to the template's, then deleted: the team goes back to the game's stadium
    assert not client.delete(f'/api/stadiums/{sid}/scene').json()['own_scene']
    assert client.delete('/api/stadiums/3').status_code == 400  # not created
    r = client.post('/api/bulk-delete', json={'kind': 'stadium', 'ids': [266, sid]})
    assert sorted(r.json()['deleted']) == [266, sid]
    assert client.get(f'/api/stadiums/{sid}').status_code == 404
    assert client.get(f'/api/teams/{fakegame.SMALL_TEAM}').json()['stadium_changed'] is False
