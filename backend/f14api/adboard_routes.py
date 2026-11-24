"""Advertising boards: the game's boards (edit the picture, restore) and the user's boards (create, copy, save, picture,
hide, delete), and the board of a team or a league (f14mod.adboards). Registered by main (imported before the
interface's catch-all route)."""
import base64
import binascii
import datetime
from typing import Optional

from fastapi.responses import Response
from pydantic import BaseModel

from f14mod import adboards, images, rx3
from f14mod.project import ADBOARD_PICTURE, GAME_ADBOARD_MAX

from . import queries
from .main import ApiError, app, db, game, lang, project, team_detail

NAME_MAX = 60


def _iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if t else None


def _game_boards() -> list[int]:
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    return [b for b in adboards.game_boards(game.files()) if b <= GAME_ADBOARD_MAX]


def _is_game_board(bid: int) -> bool:
    return bid <= GAME_ADBOARD_MAX and bid in _game_boards()


def _exists(bid: int) -> bool:
    return project().is_created('adboard', bid) or _is_game_board(bid)


def _names(con, kind: str, ids) -> dict[int, dict]:
    if kind == 'team':
        sql = f"SELECT t.id, {queries._team_name('full')} AS name, t.is_new FROM v_teams t WHERE t.id = :id"  # noqa: SLF001
    else:
        sql = f'SELECT l.id, {queries._league_name()} AS name, l.is_new FROM v_leagues l WHERE l.id = :id'  # noqa: SLF001
    out = {}
    for oid in ids:
        row = con.execute(sql, {'id': oid, 'lang': lang()}).fetchone()
        if row:
            out[oid] = {'id': row['id'], 'name': row['name'], 'is_new': bool(row['is_new'])}
    return out


def _detail(bid: int, con=None) -> dict:
    p = project()
    created = p.is_created('adboard', bid)
    if not created and not _is_game_board(bid):
        raise ApiError(404, 'not_found')
    own = p.picture('adboard', bid, ADBOARD_PICTURE)
    users = p.adboard_users(bid)

    def build(c):
        teams, leagues = _names(c, 'team', users['team']), _names(c, 'league', users['league'])
        out = {'id': bid, 'is_new': created, 'name': p.fields('adboard', bid).get('name') or '' if created else '',
               'hidden': created and bid in p.hidden('adboard'),
               # the picture's version: when the user's picture was saved, 0 = the game's own picture, None = none yet
               'picture': own[1] if own else (None if created else 0),
               'edited': not created and own is not None,
               'teams': [teams[t] for t in users['team'] if t in teams],
               'leagues': [leagues[lg] for lg in users['league'] if lg in leagues]}
        if not created:  # where the game itself shows it (its table; the default board: also everything it lacks)
            competitions = adboards.competitions_of(bid)
            named = _names(c, 'league', competitions)
            out['competitions'] = [named.get(cid) or {'id': cid, 'name': None, 'is_new': False} for cid in competitions]
            out['default'] = bid == adboards.DEFAULT_BOARD
        return out
    if con is None:
        with db() as c:
            out = build(c)
    else:
        out = build(con)
    created_at, updated_at = p.dates('adboard', bid)
    # the edit screen's form, as the other screens (one text field: the name of a board the user created)
    return {**out, 'created_at': _iso(created_at), 'updated_at': _iso(updated_at),
            'fields': [], 'values': {'name': ''}, 'saved': {'name': out['name']} if out['name'] else {}}


def _picture_png(data: str) -> bytes:
    """The board picture the user sent (base64), as it is kept: a 512x1024 PNG."""
    try:
        png = images.normalize_picture(base64.b64decode(data, validate=True))
    except (images.PictureError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))
    return images.png(adboards.picture(png))


def _game_picture(bid: int) -> bytes:
    """The game's own picture of one of its boards, as a PNG."""
    data = game.files().read(adboards.GAME_FILE.format(bid))
    found = rx3.textures(data) if data else []
    if not found:
        raise ApiError(404, 'not_found')
    return images.png(rx3.to_image(data, found[0]))


@app.get('/api/adboards')
def list_adboards():
    """The user's boards, then the game's (original or edited)."""
    ids = project().created('adboard') + _game_boards()
    with db() as con:
        items = [_detail(bid, con) for bid in ids]
    return {'items': items, 'size': list(adboards.SIZE), 'bands': adboards.BANDS, 'default_board': adboards.DEFAULT_BOARD}


class AdboardBody(BaseModel):
    name: str = ''
    picture: Optional[str] = None  # a new picture (base64); None = keep the one it has
    remove_picture: bool = False
    copy_of: Optional[int] = None  # create: a copy of this board (its picture; the game's own one for a game board)


def _clean_name(name: str) -> str:
    name = (name or '').strip()
    if not name:
        raise ApiError(400, 'name_required', 'name')
    return name[:NAME_MAX]


@app.post('/api/adboards')
def create_adboard(body: AdboardBody):
    name = _clean_name(body.name)
    png = _picture_png(body.picture) if body.picture else None
    if png is None and body.copy_of is not None:
        if not _exists(body.copy_of):
            raise ApiError(404, 'not_found')
        own = project().picture('adboard', body.copy_of, ADBOARD_PICTURE)
        png = own[0] if own else (None if project().is_created('adboard', body.copy_of) else _game_picture(body.copy_of))
    p = project()
    bid = p.next_adboard_id()
    p.create('adboard', bid, fields={'name': name})
    if png:
        p.set_picture('adboard', bid, ADBOARD_PICTURE, png)
    return _detail(bid)


@app.get('/api/adboards/{bid}')
def adboard_detail(bid: int):
    return _detail(bid)


@app.put('/api/adboards/{bid}')
def save_adboard(bid: int, body: AdboardBody):
    """Saves the board screen: the name (a board the user created) and, when sent, the new picture (or none). A new
    picture of a game board replaces the game's in every competition the game shows that board in."""
    p = project()
    created = p.is_created('adboard', bid)
    if not created and not _is_game_board(bid):
        raise ApiError(404, 'not_found')
    png = _picture_png(body.picture) if body.picture else None
    if created:
        p.save('adboard', bid, fields={'name': _clean_name(body.name)})
    if png:
        p.set_picture('adboard', bid, ADBOARD_PICTURE, png)
    elif body.remove_picture:
        p.set_picture('adboard', bid, ADBOARD_PICTURE, None)
    return _detail(bid)


@app.delete('/api/adboards/{bid}/edits')
def reset_adboard(bid: int):
    """A game board back to the game's picture."""
    if project().is_created('adboard', bid):
        raise ApiError(400, 'created_has_no_original')
    if not _is_game_board(bid):
        raise ApiError(404, 'not_found')
    project().reset('adboard', bid)
    return _detail(bid)


@app.delete('/api/adboards/{bid}')
def delete_adboard(bid: int):
    """Deletes a board the user created; the teams and leagues it was on go back to the game's boards."""
    if not project().is_created('adboard', bid):
        raise ApiError(400 if _is_game_board(bid) else 404, 'not_created' if _is_game_board(bid) else 'not_found')
    project().delete('adboard', bid)
    return {'deleted': bid}


class AdboardHiddenBody(BaseModel):
    hidden: bool


@app.put('/api/adboards/{bid}/hidden')
def set_adboard_hidden(bid: int, body: AdboardHiddenBody):
    """Out of the patch (a board the user created): its teams and leagues show the game's boards, the links stay."""
    if not project().is_created('adboard', bid):
        raise ApiError(404, 'not_found')
    project().set_hidden('adboard', bid, body.hidden)
    return _detail(bid)


@app.get('/api/image/adboard/{bid}')
def adboard_image(bid: int, width: Optional[int] = None, game_only: bool = False):
    """The board picture (512x1024): the user's, else the game's own one; or a smaller one `width` pixels wide."""
    own = None if game_only else project().picture('adboard', bid, ADBOARD_PICTURE)
    if own:
        png = own[0]
    elif _is_game_board(bid):
        png = _game_picture(bid)
    else:
        raise ApiError(404, 'not_found')
    if width:
        img = images.decode_png(png)
        width = min(max(width, 16), adboards.SIZE[0])
        img = img.resize((width, round(width * img.height / img.width)))
        png = images.png(img)
    return Response(png, media_type='image/png', headers={'Cache-Control': 'no-cache'})


class AdboardLinkBody(BaseModel):
    adboard: Optional[int] = None  # None = no board (the game's boards)


def _check_board(bid: Optional[int]) -> None:
    if bid is not None and not _exists(bid):
        raise ApiError(400, 'field_out_of_range', 'adboard')


@app.put('/api/teams/{tid}/adboard')
def set_team_adboard(tid: int, body: AdboardLinkBody):
    """The board of the team: shown in its home games, in every mode (before the league's)."""
    with db() as con:
        if not con.execute('SELECT 1 FROM v_teams WHERE id = ?', (tid,)).fetchone():
            raise ApiError(404, 'not_found')
    _check_board(body.adboard)
    project().set_adboard_link('team', tid, body.adboard)
    return team_detail(tid)


@app.put('/api/leagues/{lid}/adboard')
def set_league_adboard(lid: int, body: AdboardLinkBody):
    """The board of the league: shown in its games (and friendlies between two of its teams) when the home team has
    none."""
    with db() as con:
        if queries.league(con, lang(), lid) is None:
            raise ApiError(404, 'not_found')
    _check_board(body.adboard)
    project().set_adboard_link('league', lid, body.adboard)
    with db() as con:
        return queries.league(con, lang(), lid)

