"""Advertising boards through the API: the user's boards (create, copy, picture, links, hide, delete) and the game's
(edit the picture, restore, link)."""
import base64
import io

import fakegame
from PIL import Image

GAME_BOARD = 1  # the fake game's board file (adboard_1_0.rx3)


def _picture(color, size=(256, 512)) -> str:
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return base64.b64encode(buf.getvalue()).decode()


def _color(client, bid, **params):
    r = client.get(f'/api/image/adboard/{bid}', params=params)
    return Image.open(io.BytesIO(r.content)).convert('RGB').getpixel((2, 2))


def test_board_crud_and_links(client):
    assert client.post('/api/adboards', json={'name': '  '}).status_code == 400  # a name is required
    r = client.post('/api/adboards', json={'name': 'A01', 'picture': _picture((200, 0, 0))})
    assert r.status_code == 200, r.text
    board = r.json()
    assert board['name'] == 'A01' and board['is_new'] and board['picture'] and board['teams'] == [] and board['created_at']
    bid = board['id']
    assert bid > 1000  # never a game board's number
    img = client.get(f'/api/image/adboard/{bid}')
    assert Image.open(io.BytesIO(img.content)).size == (512, 1024)  # stretched to the game's board size
    small = client.get(f'/api/image/adboard/{bid}', params={'width': 64})
    assert Image.open(io.BytesIO(small.content)).size == (64, 128)

    r = client.put(f'/api/teams/{fakegame.TEAM}/adboard', json={'adboard': bid})
    assert r.status_code == 200 and r.json()['adboard_id'] == bid and r.json()['edited']
    r = client.put(f'/api/leagues/{fakegame.LEAGUE}/adboard', json={'adboard': bid})
    assert r.status_code == 200 and r.json()['adboard_id'] == bid
    assert client.put(f'/api/leagues/{fakegame.LEAGUE}/adboard', json={'adboard': 999}).status_code == 400
    board = client.get(f'/api/adboards/{bid}').json()
    assert [t['id'] for t in board['teams']] == [fakegame.TEAM] and [lg['id'] for lg in board['leagues']] == [fakegame.LEAGUE]

    r = client.put(f'/api/adboards/{bid}', json={'name': 'A01 new', 'remove_picture': True})
    assert r.json()['name'] == 'A01 new' and r.json()['picture'] is None
    assert client.put(f'/api/adboards/{bid}/hidden', json={'hidden': True}).json()['hidden']
    items = client.get('/api/adboards').json()['items']
    assert [(b['id'], b['is_new']) for b in items] == [(bid, True), (GAME_BOARD, False)]  # the user's, then the game's

    r = client.post('/api/bulk-delete', json={'kind': 'adboard', 'ids': [bid]})
    assert r.json()['deleted'] == [bid]
    assert client.get(f'/api/adboards/{bid}').status_code == 404
    team = client.get(f'/api/teams/{fakegame.TEAM}').json()
    assert team['adboard_id'] is None and not team['edited']  # the board was all the project had of it
    assert client.get(f'/api/leagues/{fakegame.LEAGUE}').json()['adboard_id'] is None


def test_game_board_edit_restore_copy_and_link(client):
    board = client.get(f'/api/adboards/{GAME_BOARD}').json()
    assert not board['is_new'] and not board['edited'] and board['picture'] == 0 and board['default']
    assert _color(client, GAME_BOARD) == (90, 90, 90)  # the game's own picture
    assert client.delete(f'/api/adboards/{GAME_BOARD}').status_code == 400  # a game board is restored, not deleted

    r = client.put(f'/api/adboards/{GAME_BOARD}', json={'picture': _picture((0, 150, 0))})
    assert r.status_code == 200 and r.json()['edited'] and r.json()['updated_at']
    assert _color(client, GAME_BOARD) == (0, 150, 0) and _color(client, GAME_BOARD, game_only=True) == (90, 90, 90)

    copy = client.post('/api/adboards', json={'name': 'Copy', 'copy_of': GAME_BOARD}).json()  # the edited picture
    assert copy['is_new'] and _color(client, copy['id']) == (0, 150, 0)

    r = client.put(f'/api/leagues/{fakegame.LEAGUE}/adboard', json={'adboard': GAME_BOARD})  # a game board, edited
    assert r.json()['adboard_id'] == GAME_BOARD

    r = client.post('/api/bulk-delete', json={'kind': 'adboard', 'ids': [GAME_BOARD, copy['id']]})
    assert r.json()['reset'] == [GAME_BOARD] and r.json()['deleted'] == [copy['id']]
    board = client.get(f'/api/adboards/{GAME_BOARD}').json()
    assert not board['edited'] and [lg['id'] for lg in board['leagues']] == [fakegame.LEAGUE]  # the link stays
    client.put(f'/api/leagues/{fakegame.LEAGUE}/adboard', json={'adboard': None})
