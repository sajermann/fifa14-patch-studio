"""Boots, goalkeeper gloves and balls (f14mod.equipment): the game's own (edit name, files, picture; restore) and the
user's (create, save, files, picture, hide, delete), and who wears or plays with each. A player wears one through his
fields shoetypecode / gkglovetypecode, a team plays with one through balltype (saved with the player or the team).
Registered by main (imported before the interface's catch-all route)."""
import base64
import binascii
import datetime
import io
import threading
from typing import Optional

from fastapi.responses import Response
from pydantic import BaseModel

from f14mod import equipment, gltf, images, rx3, rx3mesh, t3db
from f14mod.project import EQUIPMENT_KINDS, EQUIPMENT_PICTURE

from . import queries
from .main import ApiError, app, db, game, lang, project

NAME_MAX = 60
TEXT_MAX = 200
THUMB_WIDTH = 256
_thumbs: dict[tuple, bytes] = {}  # (kind, code, version) -> PNG (drawn pictures take ~0.5 s)
_thumbs_lock = threading.Lock()


def _iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if t else None


def _kind(kind: str) -> str:
    if kind not in EQUIPMENT_KINDS:
        raise ApiError(404, 'not_found')
    return kind


def _game_codes(kind: str) -> list[int]:
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    cache = getattr(game, '_equipment_codes', None)
    if cache is None or cache[0] is not game.files():
        cache = game._equipment_codes = (game.files(), {})  # noqa: SLF001
    if kind not in cache[1]:
        cache[1][kind] = equipment.game_codes(game.files(), kind)
    return cache[1][kind]


_names_cache: dict[tuple, dict[int, str]] = {}


def _game_names(kind: str) -> dict[int, str]:
    """{code: the game's own name} in the shown language (else English): the boots' and gloves' names of the game's
    edit player screen, the balls' of the match settings."""
    files, code_lang = game.files(), lang()
    key = (id(files), kind, code_lang)
    if key not in _names_cache:
        prefixes = [equipment.NAME_STRING[kind].split('{')[0]]
        if kind == 'glove':
            prefixes += [p.split('{')[0] for p in equipment.GLOVE_NAME_SPELLINGS]
        out: dict[int, str] = {}
        for language in dict.fromkeys(('eng_us', code_lang)):  # the shown language wins
            for name in (language, f'{language}_upd'):
                raw = files.read(f'data/loc/{name}.db')
                if raw is None:
                    continue
                for sid, text in t3db.read_strings(raw, lambda s: s.startswith(tuple(prefixes))).items():
                    number = sid.rsplit('_', 1)[-1]
                    if number.isdigit() and text:
                        out[int(number)] = text
        _names_cache[key] = out
    return _names_cache[key]


def _exists(kind: str, code: int) -> bool:
    return project().is_created(kind, code) or code in _game_codes(kind)


def _wearers(con, kind: str, codes: Optional[list[int]] = None) -> dict[int, list[dict]]:
    """{code: [{id, name, is_new}]} of the players (boot, glove) or teams (ball) wearing it, as saved or the game's."""
    table, field = equipment.FIELDS[kind]
    if table == 'players':
        sql = (f"SELECT pl.id, {queries._player_name('pl')} AS name, pl.is_new, "  # noqa: SLF001
               f"COALESCE({queries._saved('player', 'pl', field)}, json_extract(pl.raw, '$.{field}')) AS code "  # noqa: SLF001
               f'FROM v_players pl')
    else:
        sql = (f"SELECT t.id, {queries._team_name('full')} AS name, t.is_new, "  # noqa: SLF001
               f"COALESCE({queries._saved('team', 't', field)}, json_extract(t.raw, '$.{field}')) AS code "  # noqa: SLF001
               f'FROM v_teams t')
    out: dict[int, list[dict]] = {}
    wanted = set(codes) if codes is not None else None
    for r in con.execute(f'SELECT * FROM ({sql}) WHERE code > 0 ORDER BY name', {'lang': lang()}):
        if wanted is None or r['code'] in wanted:
            out.setdefault(int(r['code']), []).append({'id': r['id'], 'name': r['name'], 'is_new': bool(r['is_new'])})
    return out


def _detail(kind: str, code: int, wearers: Optional[list[dict]] = None) -> dict:
    p = project()
    created = p.is_created(kind, code)
    if not created and code not in _game_codes(kind):
        raise ApiError(404, 'not_found')
    saved = p.fields(kind, code)
    files = p.equipment_files(kind, code)
    own_picture = p.picture(kind, code, EQUIPMENT_PICTURE)
    if wearers is None:
        with db() as con:
            wearers = _wearers(con, kind, [code]).get(code, [])
    created_at, updated_at = p.dates(kind, code)
    needs = ('mesh', 'texture') if kind in ('boot', 'ball') else ('texture',)
    return {
        'kind': kind, 'code': code, 'is_new': created,
        'name': saved.get('name') or '', 'game_name': None if created else _game_names(kind).get(code), 'credits': saved.get('credits') or '', 'credits_url': saved.get('credits_url'),
        'hidden': created and code in p.hidden(kind),
        'edited': not created and bool(saved or files or own_picture),
        'files': sorted(files), 'needs': list(needs), 'complete': (not created) or all(n in files for n in needs),
        # the user's picture (its version), else a picture drawn from the files
        'picture': own_picture[1] if own_picture else None,
        'version': updated_at or 0,
        # a glove the game's edit player screen does not list (a new code: its name does not show there)
        'listed': kind != 'glove' or code in _game_codes('glove'),
        'wearers': wearers, 'wearer_count': len(wearers),
        'created_at': _iso(created_at), 'updated_at': _iso(updated_at),
        # the edit screen's form, as the other screens (texts: the name, the credits and their page)
        'id': code, 'fields': [], 'values': {'name': '', 'credits': '', 'credits_url': ''},
        'saved': {k: saved[k] for k in ('name', 'credits', 'credits_url') if saved.get(k)},
    }


@app.get('/api/equipment/{kind}')
def list_equipment(kind: str):
    """The user's items, then the game's (original or edited)."""
    _kind(kind)
    p = project()
    ids = p.created(kind) + _game_codes(kind)
    with db() as con:
        wearers = _wearers(con, kind)
    items = [_detail(kind, c, wearers.get(c, [])) for c in ids]
    free = equipment.free_codes(game.files(), kind, p.created(kind))
    return {'items': items, 'free': len(free)}


@app.get('/api/equipment/{kind}/{code}')
def equipment_detail(kind: str, code: int):
    return _detail(_kind(kind), code)


class EquipmentBody(BaseModel):
    name: str = ''
    credits: str = ''
    credits_url: Optional[str] = None


def _clean(kind: str, body: EquipmentBody, required: bool) -> dict:
    name = (body.name or '').strip()[:NAME_MAX]
    if required and not name:
        raise ApiError(400, 'name_required', 'name')
    out = {'name': name or None, 'credits': (body.credits or '').strip()[:TEXT_MAX] or None}
    url = (body.credits_url or '').strip()[:TEXT_MAX]
    if url and not url.lower().startswith(('http://', 'https://')):
        raise ApiError(400, 'bad_url', 'credits_url')
    out['credits_url'] = url or None
    return {k: v for k, v in out.items() if v is not None}


@app.post('/api/equipment/{kind}')
def create_equipment(kind: str, body: EquipmentBody):
    """A new item with the first free code of the game."""
    _kind(kind)
    p = project()
    free = equipment.free_codes(game.files(), kind, p.created(kind))
    if not free:
        raise ApiError(409, 'equipment_no_free_code')
    p.create(kind, free[0], fields=_clean(kind, body, True))
    return _detail(kind, free[0])


@app.put('/api/equipment/{kind}/{code}')
def save_equipment(kind: str, code: int, body: EquipmentBody):
    _kind(kind)
    if not _exists(kind, code):
        raise ApiError(404, 'not_found')
    p = project()
    p.save(kind, code, fields=_clean(kind, body, p.is_created(kind, code)))
    return _detail(kind, code)


class FilesBody(BaseModel):
    mesh: Optional[str] = None  # base64 of the pack's mesh file (boots, balls)
    texture: Optional[str] = None  # base64 of the pack's texture file
    remove: list[str] = []  # names of files to drop (back to the game's, or none yet)


def _decoded(data: str) -> bytes:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ApiError(400, 'bad_file', str(e))


@app.post('/api/equipment/{kind}/{code}/files')
def set_equipment_files(kind: str, code: int, body: FilesBody):
    """The pack's files of an item, checked (a file the game could not use is refused with its reason)."""
    _kind(kind)
    if not _exists(kind, code):
        raise ApiError(404, 'not_found')
    out: dict[str, Optional[bytes]] = {n: None for n in body.remove if n in ('mesh', 'texture')}
    try:
        if body.mesh is not None:
            if kind == 'glove':
                raise ApiError(400, 'bad_request', 'mesh')
            out['mesh'] = equipment.check_mesh(kind, _decoded(body.mesh))
        if body.texture is not None:
            out['texture'] = equipment.check_texture(kind, _decoded(body.texture))
    except equipment.EquipmentError as e:
        raise ApiError(400, e.code, e.detail)
    project().set_equipment_files(kind, code, out)
    return _detail(kind, code)


class PictureBody(BaseModel):
    data: str  # base64 of an image


@app.put('/api/equipment/{kind}/{code}/picture')
def set_equipment_picture(kind: str, code: int, body: PictureBody):
    _kind(kind)
    if not _exists(kind, code):
        raise ApiError(404, 'not_found')
    try:
        png = images.normalize_picture(_decoded(body.data))
    except images.PictureError as e:
        raise ApiError(400, 'bad_picture', str(e))
    project().set_picture(kind, code, EQUIPMENT_PICTURE, png)
    return _detail(kind, code)


@app.delete('/api/equipment/{kind}/{code}/picture')
def remove_equipment_picture(kind: str, code: int):
    _kind(kind)
    project().set_picture(kind, code, EQUIPMENT_PICTURE, None)
    return _detail(kind, code)


def _drawn(kind: str, code: int) -> bytes:
    """The item's picture drawn from its files (the project's, else the game's)."""
    own = project().equipment_files(kind, code)
    files = game.files()
    mesh = own.get('mesh')
    if mesh is None:
        mesh = files.read(equipment.GLOVE_MESH if kind == 'glove' else equipment.mesh_path(kind, code))
    texture = own.get('texture') or files.read(equipment.texture_path(kind, code))
    if mesh is None or texture is None:
        img = equipment.placeholder(THUMB_WIDTH)
    else:
        try:
            img = equipment.thumbnail(kind, rx3.unpack(mesh), texture, THUMB_WIDTH)
        except Exception:  # noqa: BLE001 (a file the drawing cannot read: the plain picture)
            img = equipment.placeholder(THUMB_WIDTH)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


@app.get('/api/equipment/{kind}/{code}/picture.png')
def equipment_picture(kind: str, code: int, v: int = 0):
    """The user's picture, else one drawn from the files (cached per version: `v`)."""
    _kind(kind)
    if not _exists(kind, code):
        raise ApiError(404, 'not_found')
    own = project().picture(kind, code, EQUIPMENT_PICTURE)
    if own:
        data = own[0]
    else:
        key = (kind, code, project().dates(kind, code)[1] or 0, project().path)
        with _thumbs_lock:
            data = _thumbs.get(key)
        if data is None:
            data = _drawn(kind, code)
            with _thumbs_lock:
                if len(_thumbs) > 2000:
                    _thumbs.clear()
                _thumbs[key] = data
    return Response(data, media_type='image/png', headers={'Cache-Control': 'max-age=31536000'})


def _clear_wearers(kind: str, code: int) -> None:
    """A deleted item: the players or teams that wore it go back to the game's own value."""
    p = project()
    table, field = equipment.FIELDS[kind]
    owner = 'player' if table == 'players' else 'team'
    for oid, values in p.all_fields(owner).items():
        if values.get(field) == code:
            rest = {k: v for k, v in values.items() if k != field}
            p.save(owner, oid, names=p.names(owner, oid), fields=rest)


@app.delete('/api/equipment/{kind}/{code}')
def delete_equipment(kind: str, code: int):
    """A created item leaves the project (who wore it gets the game's own again); a game item is restored."""
    _kind(kind)
    p = project()
    if p.is_created(kind, code):
        _clear_wearers(kind, code)
        p.delete(kind, code)
        return {'deleted': True}
    if code not in _game_codes(kind):
        raise ApiError(404, 'not_found')
    p.reset(kind, code)
    return _detail(kind, code)


class HiddenBody(BaseModel):
    hidden: bool


@app.put('/api/equipment/{kind}/{code}/hidden')
def set_equipment_hidden(kind: str, code: int, body: HiddenBody):
    """Hide: a created item is left out of the patch (kept in the project)."""
    _kind(kind)
    if not project().is_created(kind, code):
        raise ApiError(400, 'bad_request', 'hidden')
    project().set_hidden(kind, code, body.hidden)
    return _detail(kind, code)


def _preview_files(kind: str, code: int) -> tuple[bytes | None, bytes | None]:
    """(mesh, textures) the item is drawn from: the project's files, else the game's."""
    own = project().equipment_files(kind, code)
    files = game.files()
    mesh = own.get('mesh')
    if mesh is None:
        mesh = files.read(equipment.GLOVE_MESH if kind == 'glove' else equipment.mesh_path(kind, code))
    texture = own.get('texture') or files.read(equipment.texture_path(kind, code))
    return (rx3.unpack(mesh) if mesh else None), texture


@app.get('/api/equipment/{kind}/{code}/preview.glb')
def equipment_preview_mesh(kind: str, code: int, v: int = 0):
    """The item's 3D model for the preview (geometry only: the color comes from preview.png)."""
    _kind(kind)
    if not _exists(kind, code):
        raise ApiError(404, 'not_found')
    mesh, _ = _preview_files(kind, code)
    if mesh is None:
        raise ApiError(404, 'not_found')
    try:
        found = rx3mesh.meshes(mesh)
    except Exception as e:  # noqa: BLE001
        raise ApiError(400, 'equipment_mesh_invalid', str(e))
    out = []
    for i, m in enumerate(found):
        a = m['attrs']
        out.append({'name': f'part{i}', 'positions': [p[:3] for p in a['p0']],
                    'normals': [n[:3] for n in a['n0']] if 'n0' in a else None,
                    'uvs': [t[:2] for t in a['t0']] if 't0' in a else None,
                    'indices': [int(x) for x in equipment.triangles(m['indices']).reshape(-1)]})
    return Response(gltf.write_glb(out), media_type='model/gltf-binary', headers={'Cache-Control': 'max-age=31536000'})


@app.get('/api/equipment/{kind}/{code}/preview.png')
def equipment_preview_texture(kind: str, code: int, v: int = 0):
    """The item's color texture for the preview."""
    _kind(kind)
    if not _exists(kind, code):
        raise ApiError(404, 'not_found')
    _, texture = _preview_files(kind, code)
    if texture is None:
        raise ApiError(404, 'not_found')
    t = rx3.by_name(texture, equipment.TEXTURES[kind][0])
    img = equipment.decode(texture, t).convert('RGB')
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return Response(buf.getvalue(), media_type='image/png', headers={'Cache-Control': 'max-age=31536000'})
