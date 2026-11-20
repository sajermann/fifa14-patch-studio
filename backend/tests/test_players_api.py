"""Players through the API: create (from scratch or a copy), save with teams, traits and face, photo, face packs,
look options, the preview of a player with the screen's values, hide and delete."""
import base64
import io
import json

import fakegame
from PIL import Image

from f14api import main


def _b64(color, size=(32, 32)) -> str:
    buf = io.BytesIO()
    Image.new('RGBA', size, color + (255,)).save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode()


def test_create_save_and_delete_player(client):
    r = client.post('/api/players', json={'fields': {'name.first': ' '}})
    assert r.status_code == 400 and r.json()['detail']['code'] == 'name_required'
    new = client.post('/api/players', json={'fields': {'name.first': 'Zero', 'name.last': 'Player'},
                                            'team': fakegame.TEAM}).json()
    pid = new['id']
    assert pid >= 300001 and new['is_new'] and new['name'] == 'Zero Player'
    assert new['saved']['face'] == {'source': 'generic'} and new['teams'][0]['id'] == fakegame.TEAM
    assert client.get('/api/players', params={'origin': 'project'}).json()['items'][0]['id'] == pid
    # a copy brings the face of the player copied and his photo
    copy = client.post('/api/players', json={'fields': {'name.common': 'Copy'}, 'template': fakegame.STAR}).json()
    assert copy['saved']['face'] == {'source': 'player', 'player': fakegame.STAR} and copy['has_photo']
    assert copy['values']['traits'] == ['flair']
    # save: traits, a team more, hidden in the first one
    body = {'fields': {**{k: v for k, v in new['saved'].items()}, 'traits': ['playmaker'], 'hairtypecode': 3},
            'teams': [{'team': fakegame.TEAM, 'jersey': 88, 'hidden': True}, {'team': fakegame.SMALL_TEAM}]}
    saved = client.put(f'/api/players/{pid}', json=body).json()
    assert saved['saved']['traits'] == ['playmaker']
    teams = {t['id']: t for t in saved['teams']}
    assert teams[fakegame.TEAM]['jersey'] == 88 and teams[fakegame.TEAM]['hidden'] is True
    assert fakegame.SMALL_TEAM in teams
    squad = client.get(f'/api/teams/{fakegame.TEAM}').json()['roster']
    assert next(r for r in squad if r['id'] == pid)['hidden'] is True
    # leaves a team
    body['teams'] = [{'team': fakegame.SMALL_TEAM}]
    assert [t['id'] for t in client.put(f'/api/players/{pid}', json=body).json()['teams']] == [fakegame.SMALL_TEAM]
    # a face of a player without face files is refused
    bad = client.put(f'/api/players/{pid}', json={'fields': {**body['fields'], 'face': {'source': 'player',
                                                                                        'player': fakegame.KEEPER}}})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'unknown_face'
    # photo
    assert client.put(f'/api/players/{pid}/photo', json={'data': _b64((0, 0, 255))}).json()['has_photo']
    assert client.get(f'/api/image/photo/{pid}').headers['content-type'] == 'image/png'
    # hide and delete (only created ones)
    assert client.put(f'/api/players/{pid}/hidden', json={'hidden': True}).json()['hidden'] is True
    assert client.put(f'/api/players/{fakegame.STAR}/hidden', json={'hidden': True}).status_code == 400
    for p in (pid, copy['id']):
        assert client.delete(f'/api/players/{p}').status_code == 200
    assert client.get(f'/api/players/{pid}').status_code == 404
    assert all(r['id'] != pid for r in client.get(f'/api/teams/{fakegame.SMALL_TEAM}').json()['roster'])
    for tid in (fakegame.TEAM, fakegame.SMALL_TEAM):  # the squads back to the game's (the other tests use them)
        client.put(f'/api/teams/{tid}/roster', json={'rows': None})


def test_original_player_traits_and_reset(client):
    pid = fakegame.STAR
    detail = client.get(f'/api/players/{pid}').json()
    assert detail['game_face'] and detail['values']['traits'] == ['flair'] and not detail['is_new']
    out = client.put(f'/api/players/{pid}', json={'fields': {'traits': [], 'face': {'source': 'generic'}}}).json()
    assert out['saved'] == {'traits': [], 'face': {'source': 'generic'}} and out['edited']
    look = client.post(f'/api/preview/player-look/{pid}', json={'values': {}, 'face': {'source': 'generic'}}).json()
    assert look['real'] is False
    assert client.delete(f'/api/players/{pid}/edits').json()['edited'] is False


def test_face_packs_and_options(client, tmp_path):
    pack = tmp_path / 'Packs' / 'One'
    for kind in ('head', 'face'):
        path = pack / 'sceneassets' / main.player_routes.facepack.FILES[kind].format(51318)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'RX3l ' + kind.encode())
    (pack / 'manifest.json').write_text(json.dumps({'type': 'faces', 'faces': [{'id': 51318, 'name': 'Face Man'}]}),
                                        encoding='utf-8')
    client.put('/api/settings', json={'face_pack_dirs': [str(tmp_path / 'Packs')]})
    packs = client.get('/api/facepacks').json()
    part = packs[0]['parts'][0]
    assert part['label'] == 'One' and part['count'] == 1 and part['named'] == 1
    page = client.get('/api/facepack/page', params={'q': 'face man'}).json()
    assert page['items'][0]['id'] == 51318 and page['items'][0]['name'] == 'Face Man' and page['total'] == 1
    assert page['items'][0]['folder'] == part['path'] and page['packs'][0]['name'] == 'One'
    other = tmp_path / 'Other' / 'heads'
    other.mkdir(parents=True)
    (tmp_path / 'Other' / 'faces').mkdir()
    for kind in ('head', 'face'):  # a folder opened only on the picker (not in the settings)
        (tmp_path / 'Other' / main.player_routes.facepack.FILES[kind].format(7)).write_bytes(b'RX3l x')
    assert client.get('/api/facepack/thumb', params={'pack': str(tmp_path / 'Other'), 'id': 7}).status_code == 400
    browsed = client.get('/api/facepack/page', params={'folder': str(tmp_path / 'Other')}).json()
    assert [f['id'] for f in browsed['items']] == [7]  # only its faces; now it can be read
    pid = fakegame.KEEPER
    face = {'source': 'pack', 'pack': part['path'], 'id': 51318, 'name': 'Face Man'}
    saved = client.put(f'/api/players/{pid}', json={'fields': {'face': face}}).json()
    assert saved['saved']['face']['id'] == 51318 and saved['face_stored']
    assert set(main.project().player_files(pid)) == {'head', 'face'}
    look = client.post(f'/api/preview/player-look/{pid}', json={'values': {}, 'face': face}).json()
    assert look['real'] and look['query'] == f'face_stored={pid}'
    client.delete(f'/api/players/{pid}/edits')
    assert main.project().player_files(pid) == {}
    options = client.get('/api/player-options').json()
    assert 'flair' in options['traits'] and options['codes']['eyebrowcode'] == [0, 2]
    # only the values some face texture of the game has (the rest would show a checkered face)
    assert options['codes']['skintypecode'] == [0, 2] and options['codes']['sideburnscode'] == [0, 1]
    assert options['codes']['facialhaircolorcode'] == [0, 3]
    # only what the database can store (hairtypecode has 7 bits, eyecolorcode 3)
    assert all(c <= 127 for c in options['codes']['hairtypecode']) and all(c <= 8 for c in options['codes']['eyecolorcode'])
    client.put('/api/settings', json={'face_pack_dirs': []})
