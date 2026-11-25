"""The stadiums the user creates (f14mod.stadium_files): create (a copy of a game stadium, or from the folder
of a downloaded stadium), its scene files, delete; and the menu pictures of any stadium (one per variant). Editing names and fields is the same route as the
game's stadiums (main.save_stadium). Registered by main (imported before the interface's catch-all route)."""
import base64
import binascii
import json
from typing import Optional

from pydantic import BaseModel

from f14mod import fields, fifa14, images, stadium_files
from f14mod.project import MAX_STADIUM_ID

from . import queries
from .main import ApiError, _clean_names, _png_response, _required_name, _stadium_detail, app, db, game, lang, project

class NewStadiumBody(BaseModel):
    names: dict[str, dict[str, str]] = {}
    template: Optional[int] = None  # the game stadium it copies (row, scene, pictures)
    folder: Optional[str] = None  # the folder of a downloaded stadium (its scene)


class FolderBody(BaseModel):
    folder: str


class PictureBody(BaseModel):
    data: str  # the picture's file, base64


def _detail(sid: int) -> dict:
    with db() as con:
        out = _stadium_detail(con, lang(), sid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


def _created(sid: int) -> None:
    if not project().is_created('stadium', sid):
        raise ApiError(400, 'not_created')


def _read_folder(folder: str) -> tuple[int, dict[str, bytes]]:
    try:
        return stadium_files.read_folder((folder or '').strip().strip('"'))
    except stadium_files.StadiumFolderError as e:
        raise ApiError(400, f'stadium_{e.code}', e.detail)


def _game_stadium(con, sid: Optional[int]) -> bool:
    return sid is not None and con.execute('SELECT 1 FROM stadiums WHERE id = ?', (sid,)).fetchone() is not None


@app.post('/api/stadiums')
def create_stadium(body: NewStadiumBody):
    """A new stadium with the first free id: a copy of a game stadium (its row, scene and pictures), the scene of a
    downloaded stadium's folder over the row of the stadium it replaced (or the generic stadium), or, with neither,
    from scratch (blank: it stays out of the patch until it gets a folder)."""
    _required_name('stadium', body.names)
    scene = None
    if body.folder:
        replaced, scene = _read_folder(body.folder)
    with db() as con:
        sid = queries.free_stadium_id(con)
        if sid is None:
            raise ApiError(409, 'limit_stadiums', str(MAX_STADIUM_ID))
        names = _clean_names('stadium', body.names, {}, set(queries.languages(con)))
        if body.template is not None and not _game_stadium(con, body.template):
            raise ApiError(400, 'field_out_of_range', 'template')
        template = body.template
        if template is None and scene is not None:  # the folder's stadium replaced one of the game's: its row fits
            template = replaced if _game_stadium(con, replaced) else fifa14.TEMPLATE_STADIUM
    p = project()
    p.create('stadium', sid, names)  # the database name comes from the full name (builder.add_created)
    p.set_stadium_source(sid, template)
    if scene:
        p.set_stadium_scene(sid, scene)
        p.set_stadium_folder_source(sid, replaced)
    return _detail(sid)


class HiddenBody(BaseModel):
    hidden: bool


@app.put('/api/stadiums/{sid}/hidden')
def set_stadium_hidden(sid: int, body: HiddenBody):
    """Hide: a created stadium is left out of the patch (kept in the project; its teams play in their game stadium
    meanwhile). The game's stadiums are not hidden."""
    _created(sid)
    project().set_hidden('stadium', sid, body.hidden)
    return _detail(sid)


@app.delete('/api/stadiums/{sid}')
def delete_stadium(sid: int):
    """A created stadium leaves the project (its teams play in the game's stadium again)."""
    _created(sid)
    project().delete('stadium', sid)
    return {'deleted': sid}


def _stadium(sid: int) -> None:
    """A stadium of the game or one the user created."""
    with db() as con:
        if con.execute('SELECT 1 FROM v_stadiums WHERE id = ?', (sid,)).fetchone() is None:
            raise ApiError(404, 'not_found')


@app.put('/api/stadiums/{sid}/scene')
def set_stadium_scene(sid: int, body: FolderBody):
    """The scene of a downloaded stadium's folder (replaces the one it had; a game stadium's goes into the patch
    under its id)."""
    _stadium(sid)
    replaced, scene = _read_folder(body.folder)
    project().set_stadium_scene(sid, scene)
    project().set_stadium_folder_source(sid, replaced)
    return _detail(sid)


@app.get('/api/stadiums/{sid}/defaults')
def stadium_defaults(sid: int):
    """The values a stadium can be filled with: those of the game stadium its folder was made for (they fit its 3D:
    e.g. where the boards stand), else the generic stadium's."""
    _stadium(sid)
    folder = project().stadium_folder_source(sid)
    with db() as con:
        source = folder if _game_stadium(con, folder) else fifa14.TEMPLATE_STADIUM
        row = con.execute('SELECT raw FROM stadiums WHERE id = ?', (source,)).fetchone()
        name = con.execute(f'SELECT {queries._stadium_name()} FROM v_stadiums s WHERE s.id = :id',  # noqa: SLF001
                           {'lang': lang(), 'id': source}).fetchone()
    raw = json.loads(row[0]) if row and row[0] else {}
    return {'id': source, 'name': name[0] if name else None,
            'values': {f: raw.get(f) for f in fields.STADIUM_REQUIRED if raw.get(f) is not None}}


@app.delete('/api/stadiums/{sid}/scene')
def remove_stadium_scene(sid: int):
    """Back to the game's 3D (a game stadium) or the one of the stadium it starts from."""
    _stadium(sid)
    project().set_stadium_scene(sid, None)
    project().set_stadium_folder_source(sid, None)
    return _detail(sid)


def _picture_variant(sid: int, variant: int) -> None:
    """A stadium (the game's or a created one) and one of its menu picture variants."""
    if variant not in stadium_files.PICTURE_VARIANTS:
        raise ApiError(404, 'not_found')
    _stadium(sid)


@app.put('/api/stadiums/{sid}/picture/{variant}')
def set_stadium_picture(sid: int, variant: int, body: PictureBody):
    """A menu picture of the stadium (game's or created): the patch draws it into that variant's archives (both
    sizes)."""
    _picture_variant(sid, variant)
    try:
        png = images.normalize_picture(base64.b64decode(body.data, validate=True))
    except (images.PictureError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))
    project().set_picture('stadium', sid, stadium_files.picture_slot(variant), png)
    return _detail(sid)


@app.delete('/api/stadiums/{sid}/picture/{variant}')
def remove_stadium_picture(sid: int, variant: int):
    """Back to the picture the stadium had (the game's, the folder's or the copied stadium's)."""
    _picture_variant(sid, variant)
    project().set_picture('stadium', sid, stadium_files.picture_slot(variant), None)
    return _detail(sid)


def own_image(sid: int, variant: int, size: Optional[int]):
    """The menu picture the user gave the stadium's variant, or None (called by main.stadium_image)."""
    own = project().picture('stadium', sid, stadium_files.picture_slot(variant))
    return _png_response(images.decode_png(own[0]), size) if own is not None else None


def created_image(sid: int, variant: int, size: Optional[int]):
    """The menu picture of a created stadium: its folder's, else the one of the stadium it starts from (called by
    main.stadium_image)."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    files = game.files()
    for pattern in (stadium_files.LARGE_PICTURE, stadium_files.SMALL_PICTURE):
        data = stadium_files.stadium_file(files, project(), sid, pattern.format(variant, id=sid))
        if data is not None:
            try:
                return _png_response(images.apt_picture(data), size)
            except images.UNREADABLE as e:
                raise ApiError(422, 'unreadable_file', str(e))
    raise ApiError(404, 'not_found')
