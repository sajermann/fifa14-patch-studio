"""Boots, gloves and balls through the API: create, files (checked), picture, who wears them, hide, delete and restore,
and the player's and team's choice saved with their fields."""
import base64
import io

import fakegame
from PIL import Image


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _png(color) -> str:
    buf = io.BytesIO()
    Image.new('RGB', (40, 40), color).save(buf, 'PNG')
    return _b64(buf.getvalue())


def test_boot_crud_and_wearers(client):
    assert client.post('/api/equipment/boot', json={'name': ' '}).status_code == 400  # a name is required
    assert client.get('/api/equipment/shoe').status_code == 404
    listing = client.get('/api/equipment/boot').json()
    assert [(e['code'], e['is_new']) for e in listing['items']] == [(fakegame.GAME_BOOT, False)]
    r = client.post('/api/equipment/boot', json={'name': 'B01', 'credits': 'C01'})
    assert r.status_code == 200, r.text
    boot = r.json()
    code = boot['code']
    assert boot['is_new'] and not boot['complete'] and boot['needs'] == ['mesh', 'texture'] and code != fakegame.GAME_BOOT

    bad = client.post(f'/api/equipment/boot/{code}/files', json={'texture': _b64(b'not a file')})
    assert bad.status_code == 400 and bad.json()['detail']['code'] == 'equipment_not_pc'
    game_texture = fakegame.equipment_textures('boot', (0, 0, 200))
    r = client.post(f'/api/equipment/boot/{code}/files', json={'texture': _b64(game_texture)})
    assert r.status_code == 200 and r.json()['files'] == ['texture'] and not r.json()['complete']
    assert client.get(f'/api/equipment/boot/{code}/picture.png').headers['content-type'] == 'image/png'

    r = client.put(f'/api/players/{fakegame.STAR}', json={'fields': {'shoetypecode': code}})
    assert r.status_code == 200, r.text
    boot = client.get(f'/api/equipment/boot/{code}').json()
    assert [w['id'] for w in boot['wearers']] == [fakegame.STAR]

    assert client.put(f'/api/equipment/boot/{code}/hidden', json={'hidden': True}).json()['hidden']
    r = client.post('/api/bulk-delete', json={'kind': 'boot', 'ids': [code]})
    assert r.json()['deleted'] == [code]
    assert client.get(f'/api/equipment/boot/{code}').status_code == 404
    player = client.get(f'/api/players/{fakegame.STAR}').json()
    assert 'shoetypecode' not in player['saved']  # its wearer went back to the game's boot


def test_game_glove_edit_and_restore(client):
    glove = fakegame.GAME_GLOVE
    r = client.put(f'/api/equipment/glove/{glove}', json={'name': 'G01'})
    assert r.status_code == 200 and r.json()['edited'] and r.json()['listed'] and r.json()['name'] == 'G01'
    r = client.put(f'/api/equipment/glove/{glove}/picture', json={'data': _png((200, 0, 0))})
    assert r.json()['picture']
    keepers = client.get(f'/api/equipment/glove/{glove}').json()['wearers']
    assert {w['id'] for w in keepers} >= {fakegame.KEEPER}
    r = client.delete(f'/api/equipment/glove/{glove}')  # a game glove: restored
    assert r.status_code == 200 and not r.json()['edited'] and r.json()['name'] == ''
    new = client.post('/api/equipment/glove', json={'name': 'G02'}).json()
    assert not new['listed'] and new['needs'] == ['texture']  # a new glove: not in the game's own editor list
    assert client.delete(f"/api/equipment/glove/{new['code']}").json() == {'deleted': True}


def test_team_ball(client):
    ball = client.post('/api/equipment/ball', json={'name': 'L01'}).json()
    r = client.put(f'/api/teams/{fakegame.TEAM}', json={'fields': {'balltype': ball['code']}})
    assert r.status_code == 200, r.text
    assert [w['id'] for w in client.get(f"/api/equipment/ball/{ball['code']}").json()['wearers']] == [fakegame.TEAM]
    game_ball = client.get(f'/api/equipment/ball/{fakegame.GAME_BALL}').json()
    assert game_ball['wearer_count'] == 0
    client.delete(f"/api/equipment/ball/{ball['code']}")
    assert 'balltype' not in client.get(f'/api/teams/{fakegame.TEAM}').json()['saved']
