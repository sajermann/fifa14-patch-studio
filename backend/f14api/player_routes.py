"""Players: create (from scratch or a copy), delete, save (fields, teams, face), photo, face packs, the options of the
look codes and the 3D preview of a player with the screen's values. Registered by main (imported before the
interface's catch-all route)."""
import base64
import binascii
import datetime
import hashlib
import json
import os
import random
import re
from typing import Optional
from urllib.parse import quote

from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from f14mod import appearance_thumbs, builder, facepack, fields, fifa14, images, preview
from f14mod.project import BENCH, RESERVE

from . import queries, settings
from .main import IMAGE_HEADERS, ApiError, DETAILS, EntityBody, _clean_fields, _picture, app, db, game, lang, project

BENCH_SIZE = 12  # a player added to a team goes to the bench while it has fewer, else out of the squad


# ---- detail with what only the backend knows ------------------------------------------------------------------------

def _detail(con, pid: int) -> dict:
    out = queries.player(con, lang(), pid)
    if out is None:
        raise ApiError(404, 'not_found')
    saved_face = out['saved'].get('face')
    if saved_face and saved_face.get('source') == 'pack':
        out['face_stored'] = bool(project().player_files(pid))
    return out


# ---- create, copy, delete, hide ---------------------------------------------------------------------------------------

class CreatePlayerBody(BaseModel):
    fields: dict = {}  # at least a name (name.first/name.last/name.common)
    template: Optional[int] = None  # copy of this player (game or project); None = from scratch (the model player)
    team: Optional[int] = None  # a team he joins at once


def _taken_ids() -> set[int]:
    """Ids from FIRST_FREE_PLAYER that some file of the game is named after (face, hair, photo)."""
    out = set()
    for folder in ('data/sceneassets/heads/', 'data/sceneassets/faces/', 'data/sceneassets/hair/',
                   'data/ui/imgassets/heads/'):
        for path in game.files().list(folder):
            m = re.search(r'(?:_|/p)(\d+)_|/p(\d+)\.dds$', path)
            if m:
                n = int(m.group(1) or m.group(2))
                if n >= fifa14.FIRST_FREE_PLAYER:
                    out.add(n)
    return out


def _model_player(con) -> int:
    row = con.execute('SELECT id FROM players WHERE id = ?', (fifa14.MODEL_PLAYER,)).fetchone() or \
        con.execute('SELECT id FROM players ORDER BY id LIMIT 1').fetchone()
    return row[0]


def _has_game_face(pid: int) -> bool:
    files = game.files()
    return all(files.exists(fifa14.PLAYER_FACE_FILES[k].format(pid)) for k in fifa14.FACE_REQUIRED)


@app.post('/api/players')
def create_player(body: CreatePlayerBody):
    """A new player: from scratch (the values of a plain player of the game, a generic head) or a copy of a player
    (his values, his face and photo); his own id from 300001; optionally straight into a team."""
    if not any((body.fields.get(k) or '').strip() for k in ('name.first', 'name.last', 'name.common')):
        raise ApiError(400, 'name_required')
    p = project()
    with db() as con:
        source = None
        if body.template is not None:
            source = queries.player(con, lang(), body.template)
            if source is None:
                raise ApiError(400, 'unknown_player', str(body.template))
        if body.team is not None and queries.team(con, lang(), body.team) is None:
            raise ApiError(400, 'unknown_team', str(body.team))
        pid = queries.free_player_id(con, _taken_ids())
        if pid > fifa14.MAX_PLAYER_ID:
            raise ApiError(400, 'too_many_players')
        if source is None:
            template, start = _model_player(con), {'face': {'source': 'generic'}}
        else:  # a copy: the values the source shows now (game + project), his face and photo
            template = source['template'] if source['is_new'] else body.template
            start = {k: v for k, v in {**source['values'], **source['saved']}.items()
                     if k not in fields.NAME_FIELDS and v is not None}
            if 'face' not in source['saved']:
                start['face'] = {'source': 'player', 'player': body.template} if source['game_face'] \
                    else {'source': 'generic'}
        values = fields.original_values('player', json.loads(
            con.execute('SELECT raw FROM players WHERE id = ?', (template,)).fetchone()[0]))
        kept = _clean_fields(con, 'player', pid, {**start, **body.fields},
                             {'values': {**values, **{k: '' for k in fields.NAME_FIELDS}, 'face': None}, 'roster': []})
    p.create('player', pid, fields=kept)
    p.set_player_source(pid, template)
    if source is not None:
        if kept.get('face', {}).get('source') == 'pack':
            p.set_player_files(pid, p.player_files(body.template))
        own = p.picture('player', body.template, 'photo')
        photo = own[0] if own else None
        if photo is None and source['has_photo']:
            data = game.files().read(fifa14.PHOTO.format(body.template))
            if data is not None:
                try:
                    photo = images.png(images.decode_dds(data))
                except images.UNREADABLE:
                    photo = None
        if photo:
            p.set_picture('player', pid, 'photo', photo)
    if body.team is not None:
        with db() as con:
            _join_team(con, pid, body.team)
    with db() as con:
        return _detail(con, pid)


# ---- generated players -------------------------------------------------------------------------------------------------

MAX_GENERATED = 60
GENERATED_POSITION = 25  # ST
GOALKEEPER = 0
GENERATED_BIRTHDATES = (datetime.date(1980, 1, 1), datetime.date(1994, 12, 31))
# the look codes drawn for a generic head (the body type stays the model player's)
GENERATED_LOOK = ('headtypecode', 'hairtypecode', 'haircolorcode', 'facialhairtypecode', 'facialhaircolorcode',
                  'eyebrowcode', 'sideburnscode', 'eyecolorcode', 'skintypecode', 'skintonecode')


LAST_POSITION = 27  # LW: 28 (SUB) and 29 (RES) are places in a squad, not positions


class GeneratePlayersBody(BaseModel):
    count: int = 0
    goalkeepers: int = 0  # how many of them are goalkeepers (the rest are strikers)
    positions: list[int] | None = None  # the position of each one, in order (replaces count and goalkeepers)


@app.post('/api/teams/{tid}/generate-players')
def generate_players(tid: int, body: GeneratePlayersBody):
    """New random players for a team: strikers (and goalkeepers) with every rating at the middle, named Player 01, Player 02... (the
    first names no created player has), a generic head and the rest drawn; `goalkeepers` of them play in goal, or each one plays in its
    place of `positions`. They are created in the project, not put in the squad: the screen adds them to the squad it is editing (Save keeps them
    there)."""
    if body.positions is not None:
        if not all(0 <= code <= LAST_POSITION for code in body.positions):
            raise ApiError(400, 'bad_request', 'positions')
        positions = body.positions
    else:
        if not 0 <= body.goalkeepers <= body.count:
            raise ApiError(400, 'bad_request', 'count')
        positions = [GOALKEEPER] * body.goalkeepers + [GENERATED_POSITION] * (body.count - body.goalkeepers)
    if not 1 <= len(positions) <= MAX_GENERATED:
        raise ApiError(400, 'bad_request', 'count')
    with db() as con:
        if queries.team(con, lang(), tid) is None:
            raise ApiError(400, 'unknown_team', str(tid))
        nations = [r[0] for r in con.execute('SELECT id FROM nations WHERE has_flag = 1 AND id BETWEEN 1 AND 4095')]
        taken = {r[0] for r in con.execute("SELECT json_extract(value, '$') FROM p.fields WHERE kind = 'player' "
                                           "AND field = 'name.last'")}
    codes = player_options()['codes']
    faces = _generic_faces()
    first_day, last_day = (d.toordinal() for d in GENERATED_BIRTHDATES)
    middle = {spec.name: (spec.min + spec.max) // 2 for spec in fields.PLAYER
              if spec.group in ('physical', 'mental', 'skill', 'goalkeeper')}
    out, index = [], 0
    for position in positions:
        index += 1
        while f'{index:02d}' in taken:
            index += 1
        height = random.randint(165, 195)
        values = {'name.first': 'Player', 'name.last': f'{index:02d}', 'name.jersey': f'PLAYER {index:02d}',
                  'preferredposition1': position, 'height': height, 'weight': random.randint(60, 90),
                  'birthdate': datetime.date.fromordinal(random.randint(first_day, last_day)).isoformat(),
                  'preferredfoot': random.choice((1, 2)), **middle,
                  **{c: random.choice(codes[c]) for c in GENERATED_LOOK if codes.get(c)}}
        if faces:  # the face codes go together: one face texture the game has, not each code on its own
            values.update(preview.codes_of_face(random.choice(faces), codes.get('skintonecode', [])))
        if nations:
            values['nationality'] = random.choice(nations)
        out.append(create_player(CreatePlayerBody(fields=values)))
    return out


@app.delete('/api/players/{pid}')
def delete_player(pid: int):
    if not project().is_created('player', pid):
        raise ApiError(400, 'not_created')
    project().delete('player', pid)
    return {'deleted': pid}


class PlayerHiddenBody(BaseModel):
    hidden: bool


@app.put('/api/players/{pid}/hidden')
def set_player_hidden(pid: int, body: PlayerHiddenBody):
    """Hide (same rule as the Street Studio): a created player is left out of the patch, kept in the project."""
    if not project().is_created('player', pid):
        raise ApiError(400, 'not_created')
    project().set_hidden('player', pid, body.hidden)
    with db() as con:
        return _detail(con, pid)


# ---- teams of a player ------------------------------------------------------------------------------------------------

def _roster_rows(con, tid: int) -> list[dict]:
    return [{'player': r[0], 'jersey': r[1], 'slot': r[2], 'hidden': bool(r[3])} for r in con.execute(
        'SELECT player_id, jersey, position, hidden FROM v_team_players WHERE team_id = ? ORDER BY ord, position',
        (tid,))]


def _free_number(rows: list[dict]) -> int | None:
    used = {r['jersey'] for r in rows}
    return next((n for n in range(1, 100) if n not in used), None)


def _join_team(con, pid: int, tid: int, jersey: int | None = None, hidden: bool = False) -> None:
    rows = _roster_rows(con, tid)
    if any(r['player'] == pid for r in rows):
        return
    bench = sum(1 for r in rows if r['slot'] == BENCH and not r['hidden'])
    rows.append({'player': pid, 'jersey': jersey or _free_number(rows),
                 'slot': BENCH if bench < BENCH_SIZE else RESERVE, 'hidden': hidden})
    project().set_roster(tid, rows)


class PlayerTeamRow(BaseModel):
    team: int
    jersey: Optional[int] = None
    hidden: bool = False  # out of the patch in this team only
    slot: Optional[int] = None  # lineup position (0-27), bench (28) or out of the squad (29); None = as it is


def _save_teams(con, pid: int, wanted: list[PlayerTeamRow]) -> None:
    """The teams of the player as the screen has them: joins the new ones, leaves the others, keeps his number and
    whether he is hidden in each (the rest of every squad as it is)."""
    current = {r[0] for r in con.execute('SELECT team_id FROM v_team_players WHERE player_id = ?', (pid,))}
    by_team = {}
    for w in wanted:
        if w.team in by_team:
            raise ApiError(400, 'duplicate_team', str(w.team))
        if w.jersey is not None and not 1 <= w.jersey <= 99:
            raise ApiError(400, 'field_out_of_range', 'jersey')
        if w.slot is not None and not 0 <= w.slot <= RESERVE:
            raise ApiError(400, 'field_out_of_range', 'slot')
        if queries.team(con, lang(), w.team) is None:
            raise ApiError(400, 'unknown_team', str(w.team))
        by_team[w.team] = w
    for tid in current - set(by_team):
        project().set_roster(tid, [r for r in _roster_rows(con, tid) if r['player'] != pid])
    for tid, w in by_team.items():
        if tid not in current:
            _join_team(con, pid, tid, w.jersey, w.hidden)
            continue
        rows = _roster_rows(con, tid)
        mine = next(r for r in rows if r['player'] == pid)
        jersey = w.jersey if w.jersey is not None else mine['jersey']
        if mine['jersey'] != jersey or mine['hidden'] != w.hidden:
            mine.update(jersey=jersey, hidden=w.hidden)
            project().set_roster(tid, rows)
    for tid, w in by_team.items():  # his position in each team (a starter taking a place sends its holder to the bench)
        if w.slot is None:
            continue
        rows = _roster_rows(con, tid)
        mine = next(r for r in rows if r['player'] == pid)
        if mine['slot'] == w.slot:
            continue
        for r in rows:
            if w.slot < BENCH and r['slot'] == w.slot and r['player'] != pid:
                r['slot'] = BENCH
        mine['slot'] = w.slot
        project().set_roster(tid, rows)


# ---- save -------------------------------------------------------------------------------------------------------------

class PlayerBody(EntityBody):
    teams: Optional[list[PlayerTeamRow]] = None  # None = the teams stay as they are


_browsed_folders: set[str] = set()  # folders opened on the face picker for one visit ("browse another folder")


def _pack_folders() -> list[str]:
    return [d for d in settings.load().face_pack_dirs if d and os.path.isdir(d)]


def _parts_of(folder: str) -> list[tuple[str, str]]:
    """(asset folder, shown name) of every pack under a folder (a folder with one pack: its name)."""
    return [(assets, label or facepack.pack_name(assets)) for assets, label in facepack.find_parts(folder)]


def _check_pack(assets: str) -> str:
    """A pack folder the screen sent: one of the packs of the configured folders or of a folder opened on the face
    picker (nothing else is ever read)."""
    norm = os.path.normcase(os.path.normpath(assets))
    for folder in [*_pack_folders(), *_browsed_folders]:
        for part, _label in _parts_of(folder):
            if os.path.normcase(os.path.normpath(part)) == norm:
                return part
    raise ApiError(400, 'unknown_pack')


@app.put('/api/players/{pid}')
def save_player(pid: int, body: PlayerBody):
    """Saves the whole form of a player: fields (only what differs from the game), his face (a pack face's files are
    copied into the project) and his teams."""
    p = project()
    with db() as con:
        detail = _detail(con, pid)
        if body.names:
            raise ApiError(400, 'bad_request', 'names')
        if detail['is_new'] and not any((body.fields.get(k) or '').strip()
                                        for k in ('name.first', 'name.last', 'name.common')):
            raise ApiError(400, 'name_required')
        kept = _clean_fields(con, 'player', pid, body.fields, detail)
    face, before = kept.get('face'), p.fields('player', pid).get('face')
    files = None  # None = the stored files stay
    if face and face['source'] == 'player' and not _has_game_face(face['player']):
        raise ApiError(400, 'unknown_face', str(face['player']))
    if face and face['source'] == 'pack':
        if face != before or not p.player_files(pid):
            assets = _check_pack(face['pack'])
            try:
                files = facepack.read_face(assets, face['id'])
            except facepack.FaceFormatError as e:
                raise ApiError(400, 'face_unreadable', str(e))
            if not all(k in files for k in fifa14.FACE_REQUIRED):
                raise ApiError(400, 'unknown_face', str(face['id']))
    elif p.player_files(pid):
        files = {}
    if files is not None:
        p.set_player_files(pid, files)
    p.save('player', pid, None, kept)
    if body.teams is not None:
        with db() as con:
            _save_teams(con, pid, body.teams)
    with db() as con:
        return _detail(con, pid)


@app.delete('/api/players/{pid}/edits')
def reset_player(pid: int):
    if project().is_created('player', pid):
        raise ApiError(400, 'created_has_no_original')
    project().reset('player', pid)
    with db() as con:
        return _detail(con, pid)


@app.get('/api/players/{pid}')
def player_detail(pid: int):
    with db() as con:
        return _detail(con, pid)


# ---- photo ------------------------------------------------------------------------------------------------------------

class PhotoBody(BaseModel):
    data: Optional[str] = None  # base64 picture
    pack: Optional[str] = None  # or the photo a pack ships with a face
    face: Optional[int] = None


@app.put('/api/players/{pid}/photo')
def upload_player_photo(pid: int, body: PhotoBody):
    with db() as con:
        _detail(con, pid)
    if body.pack is not None and body.face is not None:
        img = facepack.photo(_check_pack(body.pack), body.face)
        if img is None:
            raise ApiError(404, 'not_found')
        data = images.png(img)
    else:
        try:
            data = images.normalize_picture(base64.b64decode(body.data or '', validate=True))
        except (binascii.Error, images.PictureError) as e:
            raise ApiError(400, 'bad_picture', str(e))
    project().set_picture('player', pid, 'photo', data)
    with db() as con:
        return _detail(con, pid)


@app.delete('/api/players/{pid}/photo')
def remove_player_photo(pid: int):
    project().set_picture('player', pid, 'photo', None)
    with db() as con:
        return _detail(con, pid)


# ---- face packs ---------------------------------------------------------------------------------------------------

class FacePackCheckBody(BaseModel):
    folders: list[str]


@app.post('/api/facepacks/check')
def check_face_packs(body: FacePackCheckBody):
    """What the Settings show under each face folder being typed (not saved yet), like the Street Studio's: every
    pack found in it (index = the folder's position), with its faces and the problems of its manifest.json; a folder
    without faces gives one entry with an error."""
    packs = []
    for index, folder in enumerate(body.folders):
        parts = facepack.find_parts(folder) if os.path.isdir(folder) else []
        root = os.path.basename(os.path.normpath(folder)) or folder  # the folder set: first part of every name
        if not parts:
            packs.append({'index': index, 'folder': folder, 'name': root,
                          'count': 0, 'warnings': [], 'error': 'no_faces'})
        for assets, label in parts:
            manifest, warnings = facepack.read_manifest(assets, folder)
            # "folder / part" like the Street Studio (the screen shows the folder's name for several parts)
            packs.append({'index': index, 'folder': assets, 'name': root + (f' / {label}' if label else ''),
                          'count': len(facepack.list_faces(assets)), 'warnings': warnings, 'error': None})
    return {'packs': packs}


@app.get('/api/facepacks')
def face_packs():
    """The configured folders and the packs (parts) found in each one, with how many faces each has."""
    out = []
    for folder in settings.load().face_pack_dirs:
        parts = []
        if os.path.isdir(folder):
            for assets, label in facepack.find_parts(folder):
                manifest, warnings = facepack.read_manifest(assets, folder)
                parts.append({'path': assets, 'label': label or facepack.pack_name(assets),
                              'count': len(facepack.list_faces(assets)), 'named': len(manifest),
                              'warnings': warnings})
        out.append({'folder': folder, 'exists': os.path.isdir(folder), 'parts': parts})
    return out


@app.get('/api/facepack/page')
def face_pack_page(offset: int = 0, limit: int = 50, q: str = '', pack: Optional[str] = None,
                   folder: Optional[str] = None):
    """One page of the faces of every pack of the configured folders (or of one pack, `pack`), or only of a folder
    opened on the face picker for this visit (`folder`), as the Street Studio's gallery: the name and credits of the
    manifest, and the search looks at the name, the id, the credits and the pack."""
    if folder is not None:
        if not os.path.isdir(folder):
            raise ApiError(400, 'unknown_pack')
        _browsed_folders.add(os.path.normpath(folder))
        roots = [folder]
    else:
        roots = _pack_folders()
    packs, items = [], []
    for root in roots:
        parts = _parts_of(root)
        if not parts:
            packs.append({'folder': root, 'name': os.path.basename(os.path.normpath(root)), 'count': 0,
                          'warnings': [], 'error': 'no_faces'})
        for assets, label in parts:
            manifest, warnings = facepack.read_manifest(assets, root)
            faces = facepack.list_faces(assets)
            packs.append({'folder': assets, 'name': label, 'count': len(faces), 'warnings': warnings, 'error': None})
            if pack is None or os.path.normcase(assets) == os.path.normcase(pack):
                items += [{**f, **manifest.get(f['id'], {}), 'folder': assets, 'pack': label} for f in faces]
    words = queries.catalog.fold(q).split()
    if words:
        items = [f for f in items if all(w in queries.catalog.fold(
            f"{f.get('name') or ''} {f['id']} {f.get('credits') or ''} {f['pack']}") for w in words)]
    limit = min(max(limit, 1), 200)
    return {'packs': packs, 'items': items[max(0, offset):max(0, offset) + limit], 'total': len(items)}


def _cache_file(*parts) -> str:
    key = hashlib.sha1('|'.join(map(str, parts)).encode()).hexdigest()[:20]
    return os.path.join(settings.CACHE_DIR, 'faces', f'{key}.png')


THUMB_VERSION = 2  # raised when facepack.thumbnail draws differently (2: missing eyes checkered)


@app.get('/api/facepack/thumb')
def face_pack_thumb(pack: str, id: int):  # noqa: A002 - the face id
    assets = _check_pack(pack)
    head = os.path.join(assets, *facepack.FILES['head'].format(id).split('/'))
    stamp = os.path.getmtime(head) if os.path.isfile(head) else 0
    cache = _cache_file('thumb', THUMB_VERSION, assets, id, stamp)
    if os.path.isfile(cache):
        return FileResponse(cache, media_type='image/png', headers=IMAGE_HEADERS)
    try:
        png = facepack.thumbnail(facepack.read_face(assets, id), 160)
    except (facepack.FaceFormatError, *images.UNREADABLE) as e:
        raise ApiError(422, 'face_unreadable', str(e))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, 'wb') as f:
        f.write(png)
    return Response(png, media_type='image/png', headers=IMAGE_HEADERS)


@app.get('/api/facepack/photo')
def face_pack_photo(pack: str, id: int):  # noqa: A002
    img = facepack.photo(_check_pack(pack), id)
    if img is None:
        raise ApiError(404, 'not_found')
    return Response(images.png(img), media_type='image/png', headers=IMAGE_HEADERS)


@app.get('/api/game-face/thumb/{pid}')
def game_face_thumb(pid: int):
    """Front view of the real face of a player of the game (the face picker's 'from another player')."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    cache = os.path.join(settings.CACHE_DIR, 'faces', game.token, f'game_{pid}.png')
    if os.path.isfile(cache):
        return FileResponse(cache, media_type='image/png', headers=IMAGE_HEADERS)
    files = game.files()
    data = {k: files.read(path.format(pid)) for k, path in fifa14.PLAYER_FACE_FILES.items()}
    data = {k: v for k, v in data.items() if v is not None}
    if not all(k in data for k in fifa14.FACE_REQUIRED):
        raise ApiError(404, 'not_found')
    try:
        png = facepack.thumbnail(data, 160)
    except images.UNREADABLE as e:
        raise ApiError(422, 'face_unreadable', str(e))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, 'wb') as f:
        f.write(png)
    return Response(png, media_type='image/png', headers=IMAGE_HEADERS)


# ---- options of the look codes, thumbnails --------------------------------------------------------------------

_options_cache: dict[str, dict] = {}
_faces_cache: dict[str, list] = {}


def _generic_faces() -> list[tuple[int, ...]]:
    if game.token not in _faces_cache:
        _faces_cache[game.token] = preview.generic_faces(game.files())
    return _faces_cache[game.token]


def _file_codes(folder: str, pattern: str) -> list[int]:
    rx = re.compile(pattern)
    return sorted({int(m.group(1)) for p in game.files().list(folder) if (m := rx.search(p))})


@app.get('/api/player-options')
def player_options():
    """The values the screen offers for each code of the player (`code` fields): the generic heads and hairs the game
    has files of, the other codes every value its players use (and the field's whole range for small fields), and the
    traits."""
    if game.token in _options_cache:
        return _options_cache[game.token]
    with db() as con:
        codes = {}
        for spec in fields.PLAYER:
            if spec.kind != 'code':
                continue
            used = {r[0] for r in con.execute(
                f"SELECT DISTINCT json_extract(raw, '$.{spec.name}') FROM players") if r[0] is not None}
            if spec.max - spec.min <= 15:
                used |= set(range(spec.min, spec.max + 1))
            codes[spec.name] = sorted(used)
    heads = _file_codes('data/sceneassets/heads/', r'/head_(\d+)_1\.rx3$')
    hairs = _file_codes('data/sceneassets/hair/', r'/hair_(\d+)_1_0\.rx3$')
    for field, (name, shift) in appearance_thumbs.READY.items():  # the colors the game has a Create Player picture of
        ready = [c for c in codes.get(field, []) if game.files().exists(
            appearance_thumbs.CREATE_PLAYER.format(name.format(c + shift)))]
        if ready:
            codes[field] = ready
    if heads:
        codes['headtypecode'] = heads
    if hairs:
        codes['hairtypecode'] = [0, *hairs]  # 0 = bald
    for spec in fields.PLAYER:  # what the database can store (the game has hair files it cannot point to)
        if spec.name in codes:
            codes[spec.name] = [c for c in codes[spec.name] if spec.min <= c <= spec.max]
    faces = _generic_faces()
    if faces:  # a generic head with a value no face texture has shows a checkered face in the game
        for field in preview.FACE_CODES:
            codes[field] = [c for c in codes.get(field, []) if preview.face_codes_allowed(field, c, faces)]
    out = {'codes': codes, 'traits': list(fifa14.TRAITS), 'thumbs': list(appearance_thumbs.FIELDS),
           'hair_colors': ['#%06x' % c for c in preview.HAIR_COLORS]}
    _options_cache[game.token] = out
    return out


@app.get('/api/appearance/{field}/{code}.png')
def appearance_thumb(field: str, code: int, variant: int = 0):
    """Picture of one value of a look code (f14mod.appearance_thumbs: the game's Create Player pictures, or the
    generic head drawn with it; `variant` = the hair or beard color the hair/beard pictures come in)."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    if field not in appearance_thumbs.FIELDS:
        raise ApiError(404, 'not_found')
    cache = os.path.join(settings.CACHE_DIR, 'appearance', game.token, f'{field}_{code}_{variant}.png')
    if os.path.isfile(cache):
        return FileResponse(cache, media_type='image/png', headers=IMAGE_HEADERS)
    try:
        png = images.png(appearance_thumbs.thumbnail(game.files(), field, code, variant))
    except appearance_thumbs.ThumbError as e:
        raise ApiError(404, 'not_found', str(e))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, 'wb') as f:
        f.write(png)
    return Response(png, media_type='image/png', headers=IMAGE_HEADERS)


# ---- 3D preview of a player with the screen's values ----------------------------------------------------------------

def _face_files(face_pack: Optional[str], face_id: Optional[int], face_stored: Optional[int]):
    """The game's files, with the face of a pack or the one kept in the project for a player put under its id."""
    files = game.files()
    if face_pack and face_id is not None:
        assets = _check_pack(face_pack)
        try:
            data = facepack.read_face(assets, face_id)
        except facepack.FaceFormatError as e:
            raise ApiError(422, 'face_unreadable', str(e))
        return preview.FaceFiles(files, f'pack:{assets}:{face_id}', face_id, data)
    if face_stored is not None:
        data = project().player_files(face_stored)
        stamp = hashlib.sha1(b''.join(data.get(k, b'')[:4096] for k in sorted(data))).hexdigest()[:12]
        return preview.FaceFiles(files, f'stored:{face_stored}:{stamp}', face_stored, data)
    return files


class LookBody(BaseModel):
    values: dict = {}  # field values of the screen (saved and not saved)
    face: Optional[dict] = None  # the face choice of the screen (None = the player's own)


def _player_look(pid: int, values: dict, face: Optional[dict]) -> dict:
    with db() as con:
        row = con.execute('SELECT raw FROM v_players WHERE id = ?', (pid,)).fetchone()
        created = project().is_created('player', pid)
    raw = dict(json.loads(row['raw'])) if row and row['raw'] else {}
    try:
        columns = fields.to_columns('player', {k: v for k, v in values.items()
                                               if k in fields.BY_NAME['player'] and v not in (None, '')})
    except (ValueError, TypeError):
        columns = {}
    raw.update({k: v for k, v in columns.items() if isinstance(v, int)})
    files, look_id, query = game.files(), (None if created else pid), ''
    if face:
        if face.get('source') == 'generic':
            raw['headclasscode'] = 1
        elif face.get('source') == 'player' and isinstance(face.get('player'), int):
            raw['headclasscode'], look_id = 0, face['player']
        elif face.get('source') == 'pack' and isinstance(face.get('id'), int):
            saved = project().fields('player', pid).get('face')
            if saved == face and project().player_files(pid):
                files, query = _face_files(None, None, pid), f'face_stored={pid}'
                raw['headclasscode'], look_id = 0, pid
            else:
                files = _face_files(face.get('pack'), face['id'], None)
                query = f"face_pack={quote(face['pack'])}&face_id={face['id']}"
                raw['headclasscode'], look_id = 0, face['id']
    elif created:
        raw['headclasscode'] = 1
    out = preview.look(files, look_id, raw or None)
    out['query'] = query if out['real'] else ''
    return out


@app.post('/api/preview/player-look/{pid}')
def preview_player_look(pid: int, body: LookBody):
    """How the preview dresses a player with the values of his screen (also the ones not saved yet)."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    return _player_look(pid, body.values, body.face)


@app.get('/api/preview/look/{pid}')
def preview_look(pid: int):
    """How the preview dresses a player with what is saved (the team's kit preview)."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    with db() as con:
        if not con.execute('SELECT 1 FROM v_players WHERE id = ?', (pid,)).fetchone():
            return preview.look(game.files(), None, None)
    saved = project().fields('player', pid)
    return _player_look(pid, saved, saved.get('face'))


@app.get('/api/preview/mesh/{part}/{code}.glb')
def preview_mesh(part: str, code: int, collar: int = 0, real: bool = False, face_pack: Optional[str] = None,
                 face_id: Optional[int] = None, face_stored: Optional[int] = None):
    """A part of the player as GLB (preview.MESHES; `collar` for the jersey); real = head/hair of a player's own face
    (code = his id), with a pack face (`face_pack` + `face_id`) or the one kept for a player (`face_stored`)."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    try:
        data = preview.mesh_glb(_face_files(face_pack, face_id, face_stored), part, code, collar, real)
    except preview.PreviewError as e:
        raise ApiError(404, 'not_found', str(e))
    return Response(data, media_type='model/gltf-binary', headers={'Cache-Control': 'max-age=3600'})


@app.get('/api/preview/texture/{name}/{code}.png')
def preview_texture(name: str, code: int, real: bool = False, face_pack: Optional[str] = None,
                    face_id: Optional[int] = None, face_stored: Optional[int] = None):
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    try:
        data = preview.texture_png(_face_files(face_pack, face_id, face_stored), name, code, real)
    except preview.PreviewError as e:
        raise ApiError(404, 'not_found', str(e))
    return Response(data, media_type='image/png', headers={'Cache-Control': 'max-age=3600'})


@app.get('/api/preview/face/{key}.png')
def preview_face(key: str, face_pack: Optional[str] = None, face_id: Optional[int] = None,
                 face_stored: Optional[int] = None):
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    try:
        data = preview.face_png(_face_files(face_pack, face_id, face_stored), key)
    except preview.PreviewError as e:
        raise ApiError(404, 'not_found', str(e))
    return Response(data, media_type='image/png', headers={'Cache-Control': 'max-age=3600'})


@app.get('/api/image/photo/{pid}')
def photo_image(pid: int, size: Optional[int] = None, game_only: bool = False):
    """The player's photo: the user's picture, else the game's file."""
    own = None if game_only else project().picture('player', pid, 'photo')
    if own:
        img = images.fit(images.decode_png(own[0]), fifa14.PHOTO_SIZE)
        if size:
            img = images.thumbnail(img, min(max(size, 16), 512))
        return Response(images.png(img), media_type='image/png', headers={'Cache-Control': 'no-cache'})
    return _picture('photo', pid, fifa14.PHOTO.format(pid), size)


_ = (DETAILS, builder)  # imported for the routes' callers
