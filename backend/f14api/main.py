"""HTTP API of the FIFA 14 Patch Studio (FastAPI). The interface is served from the same address (frontend/dist)."""
import logging
import os
from contextlib import asynccontextmanager, contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import settings  # noqa: I001 - first: it puts the core folder on the path

from f14mod import builder, fields, fifa14, flags, images, install_check, installer  # noqa: E402

from . import dialogs, queries  # noqa: E402
from .state import GameState, Jobs, project  # noqa: E402

log = logging.getLogger('f14api')

game = GameState()
jobs = Jobs()


class ApiError(HTTPException):
    """An error the interface translates: `code` names the message, `detail` adds context."""

    def __init__(self, status: int, code: str, detail: str = ''):
        super().__init__(status_code=status, detail={'code': code, 'detail': detail})


@contextmanager
def db():
    """The originals cache with the project attached; 409 while the game is not ready."""
    if game.state != 'ready' or not game.catalog_path:
        raise ApiError(409, 'game_not_ready')
    con = queries.connect(game.catalog_path, project().path)
    try:
        yield con
    finally:
        con.close()


def lang() -> str:
    return settings.load().shown_language()


@asynccontextmanager
async def lifespan(_: FastAPI):
    cfg = settings.load()
    if cfg.game_dir:
        game.open(cfg.game_dir)
    yield


app = FastAPI(title='FIFA 14 Patch Studio', version=settings.APP_VERSION, lifespan=lifespan)


# ---- status, settings and the game --------------------------------------------------------------------------------

@app.get('/api/status')
def get_status():
    cfg = settings.load()
    return {'version': settings.APP_VERSION, 'config': cfg.model_dump(), 'names_language': cfg.shown_language(),
            'game': game.status(), 'project': project().counts(), 'job': jobs.view(),
            'patch_built': os.path.isdir(settings.PATCH_DIR) and bool(os.listdir(settings.PATCH_DIR))}


class SettingsBody(BaseModel):
    language: Optional[settings.Language] = None
    names_language: Optional[str] = None


@app.put('/api/settings')
def put_settings(body: SettingsBody):
    cfg = settings.load()
    return settings.save(cfg.model_copy(update=body.model_dump(exclude_unset=True))).model_dump()


@app.post('/api/dialog/folder')
def pick_folder(body: dict):
    try:
        return {'path': dialogs.browse_folder(body.get('initial'), body.get('title') or 'Choose a folder')}
    except dialogs.DialogError as e:
        raise ApiError(500, 'dialog_failed', str(e))


class GameBody(BaseModel):
    path: str


@app.post('/api/game/check')
def check_game(body: GameBody):
    """Checks a folder without choosing it."""
    return install_check.check(body.path.strip().strip('"'))


@app.post('/api/game')
def choose_game(body: GameBody):
    path = body.path.strip().strip('"')
    result = install_check.check(path)
    if result['state'] not in ('clean', 'patched'):
        raise ApiError(400, 'game_not_usable', result['state'])
    cfg = settings.load()
    cfg.game_dir = result['game_dir']
    settings.save(cfg)
    try:
        game.open(cfg.game_dir)
    except RuntimeError:
        raise ApiError(409, 'busy')
    return game.status()


@app.post('/api/game/recheck')
def recheck_game():
    cfg = settings.load()
    try:
        game.open(cfg.game_dir)
    except RuntimeError:
        raise ApiError(409, 'busy')
    return game.status()


# ---- lists --------------------------------------------------------------------------------------------------------

def _yes_no(value: Optional[str]):
    return {'yes': True, 'no': False}.get(value or '')


@app.get('/api/leagues')
def list_leagues(q: str = '', country: Optional[int] = None, sort: Optional[str] = None, dir: Optional[str] = None,
                 page: int = 1, size: int = queries.DEFAULT_PAGE_SIZE):
    with db() as con:
        return queries.leagues(con, lang(), q, sort, dir, page, size, country=country)


@app.get('/api/teams')
def list_teams(q: str = '', league: Optional[int] = None, edited: Optional[str] = None, sort: Optional[str] = None,
               dir: Optional[str] = None, page: int = 1, size: int = queries.DEFAULT_PAGE_SIZE):
    with db() as con:
        return queries.teams(con, lang(), q, league, _yes_no(edited), sort, dir, page, size)


@app.get('/api/players')
def list_players(q: str = '', team: Optional[int] = None, position: Optional[int] = None,
                 sort: Optional[str] = None, dir: Optional[str] = None, page: int = 1,
                 size: int = queries.DEFAULT_PAGE_SIZE):
    with db() as con:
        return queries.players(con, lang(), q, team, position, sort, dir, page, size)


@app.get('/api/options')
def filter_options():
    """Small lists for the filter selects and the language fields."""
    with db() as con:
        return {
            'leagues': [dict(r) for r in con.execute(
                f'SELECT l.id, {queries._league_name()} AS name FROM v_leagues l ORDER BY fold(name)',  # noqa: SLF001
                {'lang': lang()})],
            'positions': [{'id': i, 'name': n} for i, n in enumerate(fifa14.POSITIONS[:28])],
            'languages': queries.languages(con),
            'nations': [dict(r) for r in con.execute('SELECT id, name, is_new FROM v_nations ORDER BY fold(name)')],
            'teams': [dict(r) for r in con.execute(
                f"SELECT t.id, {queries._team_name('full')} AS name FROM teams t ORDER BY fold(name)",  # noqa: SLF001
                {'lang': lang()})],
        }


# ---- details and saving -------------------------------------------------------------------------------------------

@app.get('/api/leagues/{lid}')
def league_detail(lid: int):
    with db() as con:
        out = queries.league(con, lang(), lid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


@app.get('/api/teams/{tid}')
def team_detail(tid: int):
    with db() as con:
        out = queries.team(con, lang(), tid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


class EntityBody(BaseModel):
    names: dict[str, dict[str, str]] = {}  # {name key: {language or '*': text}} (teams and leagues)
    fields: dict = {}  # {field: value} (see f14mod.fields)


NAME_LIMITS = {'team': {'abbr15': 15, 'abbr10': 10, 'abbr7': 7, 'abbr3': 3},
               'league': {'abbr15': 15, 'trophy_abbr15': 15},
               'country': {'full': 40, 'abbr3': 3}}
NAME_KEYS = {'team': queries.TEAM_NAME_KEYS, 'league': queries.LEAGUE_NAME_KEYS,
             'country': queries.COUNTRY_NAME_KEYS}


def _clean_names(kind: str, body: dict, original: dict, langs: set[str]) -> dict:
    """The names of the form that differ from the game, checked."""
    keys, limits = set(NAME_KEYS[kind]), NAME_LIMITS[kind]
    names: dict[str, dict[str, str]] = {}
    for key, by_lang in body.items():
        if key not in keys:
            raise ApiError(400, 'bad_request', key)
        for code, text in by_lang.items():
            if code != '*' and code not in langs:
                raise ApiError(400, 'bad_request', code)
            text = (text or '').strip()
            if not text:
                continue
            limit = limits.get(key)
            if limit and len(text) > limit:
                raise ApiError(400, 'name_too_long', f'{key}:{limit}')
            if code != '*' and text == original.get(key, {}).get(code):
                continue  # same as the game: nothing to keep
            names.setdefault(key, {})[code] = text
    return names


def _clean_fields(con, kind: str, oid: int, body: dict, detail: dict) -> dict:
    try:
        kept = fields.clean(kind, body, detail['values'])
    except fields.FieldError as e:
        raise ApiError(400, f'field_{e.code}', e.field)
    for name, value in kept.items():
        spec = fields.BY_NAME[kind][name]
        if spec.kind == 'nation' and not (spec.optional and value == 0) and                 not con.execute('SELECT 1 FROM v_nations WHERE id = ?', (value,)).fetchone():
            raise ApiError(400, 'field_out_of_range', name)
        if spec.kind == 'team' and not con.execute('SELECT 1 FROM teams WHERE id = ?', (value,)).fetchone():
            raise ApiError(400, 'field_out_of_range', name)
        if spec.kind == 'roster' and value not in {p['id'] for p in detail['roster']}:
            raise ApiError(400, 'field_out_of_range', name)
    return kept


DETAILS = {'team': queries.team, 'league': queries.league, 'player': queries.player, 'country': queries.country}


def _save(kind: str, oid: int, body: EntityBody):
    """Saves the whole form of one entity (only what differs from the game is kept)."""
    with db() as con:
        detail = DETAILS[kind](con, lang(), oid)
        if detail is None:
            raise ApiError(404, 'not_found')
        names = {}
        if kind in NAME_KEYS:
            names = _clean_names(kind, body.names, detail['original_names'], set(queries.languages(con)))
        elif body.names:
            raise ApiError(400, 'bad_request', 'names')
        kept = _clean_fields(con, kind, oid, body.fields, detail)
    project().save(kind, oid, names, kept)
    with db() as con:
        return DETAILS[kind](con, lang(), oid)


def _reset(kind: str, oid: int):
    project().reset(kind, oid)
    with db() as con:
        return DETAILS[kind](con, lang(), oid)


@app.put('/api/teams/{tid}')
def save_team(tid: int, body: EntityBody):
    return _save('team', tid, body)


@app.delete('/api/teams/{tid}/edits')
def reset_team(tid: int):
    return _reset('team', tid)


@app.put('/api/leagues/{lid}')
def save_league(lid: int, body: EntityBody):
    if project().is_created('league', lid):
        _required_name('league', body.names)
        if not body.fields.get('countryid'):
            raise ApiError(400, 'field_out_of_range', 'countryid')
    return _save('league', lid, body)


@app.delete('/api/leagues/{lid}/edits')
def reset_league(lid: int):
    if project().is_created('league', lid):
        raise ApiError(400, 'created_has_no_original')
    return _reset('league', lid)


@app.put('/api/players/{pid}')
def save_player(pid: int, body: EntityBody):
    return _save('player', pid, body)


@app.delete('/api/players/{pid}/edits')
def reset_player(pid: int):
    return _reset('player', pid)


@app.get('/api/players/{pid}')
def player_detail(pid: int):
    with db() as con:
        out = queries.player(con, lang(), pid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


# ---- free countries and leagues (created by the user) --------------------------------------------------------------

@app.get('/api/countries')
def list_countries(q: str = '', sort: Optional[str] = None, dir: Optional[str] = None, page: int = 1,
                   size: int = queries.DEFAULT_PAGE_SIZE):
    with db() as con:
        return queries.countries(con, lang(), q, sort, dir, page, size)


@app.get('/api/countries/{cid}')
def country_detail(cid: int):
    with db() as con:
        out = queries.country(con, lang(), cid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


class CreateBody(BaseModel):
    names: dict[str, dict[str, str]] = {}
    fields: dict = {}


def _required_name(kind: str, names: dict):
    if not any((t or '').strip() for t in (names.get('full') or {}).values()):
        raise ApiError(400, 'name_required', 'full')


@app.post('/api/countries')
def create_country(body: CreateBody):
    _required_name('country', body.names)
    with db() as con:
        cid = queries.free_country_id(con)
        if cid is None:
            raise ApiError(409, 'limit_countries', str(fifa14.MAX_NATION_ID))
        names = _clean_names('country', body.names, {}, set(queries.languages(con)))
        kept = _clean_fields(con, 'country', cid, body.fields, {'values': fields.original_values('country', {})})
    project().create('country', cid, names, kept)
    with db() as con:
        return queries.country(con, lang(), cid)


@app.put('/api/countries/{cid}')
def save_country(cid: int, body: EntityBody):
    """A created country or one of the game (its names by language and the flag copied from another country)."""
    if project().is_created('country', cid):
        _required_name('country', body.names)
    return _save('country', cid, body)


@app.delete('/api/countries/{cid}/edits')
def reset_country(cid: int):
    if project().is_created('country', cid):
        raise ApiError(400, 'created_has_no_original')
    return _reset('country', cid)


@app.delete('/api/countries/{cid}')
def delete_country(cid: int):
    if not project().is_created('country', cid):
        raise ApiError(400, 'not_created')
    with db() as con:
        if con.execute('SELECT 1 FROM v_leagues WHERE country_id = ?', (cid,)).fetchone():
            raise ApiError(409, 'country_has_leagues')
    project().delete('country', cid)
    return {'deleted': cid}


@app.post('/api/leagues')
def create_league(body: CreateBody):
    _required_name('league', body.names)
    with db() as con:
        lid = queries.free_league_id(con)
        if lid is None:
            raise ApiError(409, 'limit_leagues', str(fifa14.MAX_LEAGUE_ID))
        names = _clean_names('league', body.names, {}, set(queries.languages(con)))
        values = {'leaguename': None, 'level': None, 'countryid': None}
        kept = _clean_fields(con, 'league', lid, body.fields, {'values': values})
        if not kept.get('countryid'):
            raise ApiError(400, 'field_out_of_range', 'countryid')
        kept.setdefault('level', 1)
        kept.setdefault('leaguename', _first_text(names.get('full', {}))[:60])
    project().create('league', lid, names, kept)
    project().set_members(lid, [])
    with db() as con:
        return queries.league(con, lang(), lid)


def _first_text(by_lang: dict) -> str:
    return by_lang.get('*') or next(iter(by_lang.values()), '')


@app.delete('/api/leagues/{lid}')
def delete_league(lid: int):
    if not project().is_created('league', lid):
        raise ApiError(400, 'not_created')
    project().delete('league', lid)
    return {'deleted': lid}


class TeamsBody(BaseModel):
    team_ids: list[int]


@app.put('/api/leagues/{lid}/teams')
def save_league_teams(lid: int, body: TeamsBody):
    """The whole team list of a league (a team can be in several leagues)."""
    team_ids = list(dict.fromkeys(body.team_ids))
    with db() as con:
        if queries.league(con, lang(), lid) is None:
            raise ApiError(404, 'not_found')
        if team_ids:
            marks = ','.join('?' * len(team_ids))
            found = {r[0] for r in con.execute(f'SELECT id FROM teams WHERE id IN ({marks})', team_ids)}
            missing = [t for t in team_ids if t not in found]
            if missing:
                raise ApiError(400, 'unknown_team', str(missing[0]))
        others = con.execute('SELECT COUNT(*) FROM v_league_teams WHERE league_id != ?', (lid,)).fetchone()[0]
        if others + len(team_ids) > fifa14.MAX_LEAGUE_LINKS:
            raise ApiError(409, 'limit_league_links', str(fifa14.MAX_LEAGUE_LINKS))
    project().set_members(lid, team_ids)
    with db() as con:
        return queries.league(con, lang(), lid)


@app.delete('/api/leagues/{lid}/teams')
def reset_league_teams(lid: int):
    """The game's teams again (a created league: no teams)."""
    project().set_members(lid, [] if project().is_created('league', lid) else None)
    with db() as con:
        out = queries.league(con, lang(), lid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


@app.get('/api/limits')
def limits():
    with db() as con:
        return {'countries_free': sum(1 for i in range(1, fifa14.MAX_NATION_ID + 1)
                                      if not con.execute('SELECT 1 FROM v_nations WHERE id = ?', (i,)).fetchone()),
                'league_links': queries.league_link_count(con), 'max_league_links': fifa14.MAX_LEAGUE_LINKS,
                'max_squad': fifa14.MAX_SQUAD}


# ---- pictures (cached on disk per game) ------------------------------------------------------------------------------

IMAGE_HEADERS = {'Cache-Control': 'max-age=86400'}


def _picture(kind: str, oid: int, path: Optional[str], size: Optional[int]):
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    size = min(max(size, 16), 512) if size else None
    cache = os.path.join(settings.CACHE_DIR, 'images', game.token, f'{kind}_{oid}_{size or 0}.png')
    if os.path.isfile(cache):
        return FileResponse(cache, media_type='image/png', headers=IMAGE_HEADERS)
    data = game.files().read(path) if path else None
    if data is None:
        raise ApiError(404, 'not_found')
    try:
        img = images.decode_dds(data)
        if size:
            img = images.thumbnail(img, size)
        png = images.png(img)
    except images.UNREADABLE as e:
        raise ApiError(422, 'unreadable_file', str(e))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, 'wb') as f:
        f.write(png)
    return Response(png, media_type='image/png', headers=IMAGE_HEADERS)


@app.get('/api/image/crest/{tid}')
def crest_image(tid: int, size: Optional[int] = None):
    return _picture('crest', tid, fifa14.CREST.format(tid), size)


@app.get('/api/image/photo/{pid}')
def photo_image(pid: int, size: Optional[int] = None):
    return _picture('photo', pid, fifa14.PHOTO.format(pid), size)


@app.get('/api/image/flag/{cid}')
def flag_image(cid: int, size: Optional[int] = None, game_only: bool = False):
    """The flag of a country: its own picture drawn as the game will show it, else the game's file (a created country
    without a picture shows the flag it copies: see the list's flag_id). `game_only` skips the own picture."""
    own = None if game_only else project().picture('country', cid, 'flag')
    if own:
        if game.state != 'ready':
            raise ApiError(409, 'game_not_ready')
        try:
            img = flags.preview(game.files(), own[0])
        except flags.FlagError as e:
            raise ApiError(422, 'unreadable_file', str(e))
        if size:
            img = images.thumbnail(img, min(max(size, 16), 512))
        return Response(images.png(img), media_type='image/png', headers={'Cache-Control': 'no-cache'})
    return _picture('flag', cid, fifa14.FLAG_PICTURE.format(cid), size)


class PictureBody(BaseModel):
    data: str  # the picture's file, base64


@app.post('/api/flag-preview')
def flag_preview(body: PictureBody, size: Optional[int] = None):
    """A chosen picture drawn as the game will show the flag, without saving it (the page saves it with Save)."""
    import base64
    import binascii
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    try:
        img = flags.preview(game.files(), flags.normalize_picture(base64.b64decode(body.data, validate=True)))
    except (flags.FlagError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))
    if size:
        img = images.thumbnail(img, min(max(size, 16), 512))
    return Response(images.png(img), media_type='image/png', headers={'Cache-Control': 'no-store'})


@app.put('/api/countries/{cid}/flag')
def upload_flag(cid: int, body: PictureBody):
    import base64
    import binascii
    with db() as con:
        if queries.country(con, lang(), cid) is None:
            raise ApiError(404, 'not_found')
    try:
        png = flags.normalize_picture(base64.b64decode(body.data, validate=True))
    except (flags.FlagError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))
    project().set_picture('country', cid, 'flag', png)
    with db() as con:
        return queries.country(con, lang(), cid)


@app.delete('/api/countries/{cid}/flag')
def remove_flag(cid: int):
    project().set_picture('country', cid, 'flag', None)
    with db() as con:
        out = queries.country(con, lang(), cid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


@app.get('/api/image/league/{lid}')
def league_image(lid: int, size: Optional[int] = None):
    return _picture('league', lid, fifa14.LEAGUE_IMAGES['logo'].format(lid), size)


# ---- patch: build, install, uninstall -------------------------------------------------------------------------------

def _start(kind: str, work):
    try:
        return jobs.start(kind, work)
    except RuntimeError:
        raise ApiError(409, 'busy')


@app.post('/api/patch/build')
def build_patch():
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    files, proj = game.files(), project()
    return _start('build', lambda progress: builder.build(files, proj, settings.PATCH_DIR, progress))


@app.post('/api/patch/install')
def install_patch():
    if game.state != 'ready' or not game.game_dir:
        raise ApiError(409, 'game_not_ready')
    if not os.path.isdir(settings.PATCH_DIR) or not os.listdir(settings.PATCH_DIR):
        raise ApiError(400, 'no_patch')
    game_dir = game.game_dir

    def work(progress):
        manifest = installer.install(settings.PATCH_DIR, game_dir, settings.APP_VERSION,
                                     lambda i, n: progress('copy', i / n))
        game.forget_files()
        game.recheck()
        return {'files': len(manifest['added']) + len(manifest['replaced'])}
    return _start('install', work)


@app.post('/api/patch/uninstall')
def uninstall_patch():
    if not game.game_dir:
        raise ApiError(409, 'game_not_ready')
    game_dir = game.game_dir

    def work(progress):
        manifest = installer.uninstall(game_dir)
        game.forget_files()
        game.recheck()
        return {'removed': bool(manifest)}
    return _start('uninstall', work)


@app.post('/api/patch/open-folder')
def open_patch_folder():
    os.makedirs(settings.PATCH_DIR, exist_ok=True)
    if hasattr(os, 'startfile'):
        os.startfile(settings.PATCH_DIR)  # noqa: S606 - the app's own folder, opened in Explorer
    return {'path': settings.PATCH_DIR}


@app.get('/api/job')
def job_status():
    return jobs.view()


# ---- errors and the interface ---------------------------------------------------------------------------------------

@app.exception_handler(ApiError)
def api_error(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={'detail': exc.detail})


if os.path.isdir(settings.FRONTEND_DIST):
    assets = os.path.join(settings.FRONTEND_DIST, 'assets')
    if os.path.isdir(assets):
        app.mount('/assets', StaticFiles(directory=assets), name='assets')

    @app.get('/{path:path}', include_in_schema=False)
    def spa(path: str):
        full = os.path.normpath(os.path.join(settings.FRONTEND_DIST, path))
        if path and full.startswith(os.path.normpath(settings.FRONTEND_DIST)) and os.path.isfile(full):
            return FileResponse(full)
        if path.startswith('api/'):
            raise ApiError(404, 'not_found')
        return FileResponse(os.path.join(settings.FRONTEND_DIST, 'index.html'), headers={'Cache-Control': 'no-cache'})
