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

from f14mod import builder, fifa14, images, install_check, installer  # noqa: E402

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
def list_leagues(q: str = '', sort: Optional[str] = None, dir: Optional[str] = None, page: int = 1,
                 size: int = queries.DEFAULT_PAGE_SIZE):
    with db() as con:
        return queries.leagues(con, lang(), q, sort, dir, page, size)


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
                f'SELECT l.id, {queries._league_name()} AS name FROM leagues l ORDER BY fold(name)',  # noqa: SLF001
                {'lang': lang()})],
            'positions': [{'id': i, 'name': n} for i, n in enumerate(fifa14.POSITIONS[:28])],
            'languages': queries.languages(con),
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


class TeamBody(BaseModel):
    names: dict[str, dict[str, str]] = {}  # {name key: {language or '*': text}}


@app.put('/api/teams/{tid}')
def save_team(tid: int, body: TeamBody):
    """Saves the whole team form (only what differs from the original is kept)."""
    with db() as con:
        original = queries.team(con, lang(), tid)
        if original is None:
            raise ApiError(404, 'not_found')
        langs = set(queries.languages(con))
    keys = set(queries.TEAM_NAME_KEYS)
    names: dict[str, dict[str, str]] = {}
    for key, by_lang in body.names.items():
        if key not in keys:
            raise ApiError(400, 'bad_request', key)
        for code, text in by_lang.items():
            if code != '*' and code not in langs:
                raise ApiError(400, 'bad_request', code)
            text = (text or '').strip()
            if not text:
                continue
            if key == 'abbr3' and len(text) > 3:
                raise ApiError(400, 'name_too_long', f'{key}:3')
            limit = {'abbr15': 15, 'abbr10': 10, 'abbr7': 7}.get(key)
            if limit and len(text) > limit:
                raise ApiError(400, 'name_too_long', f'{key}:{limit}')
            if code != '*' and text == original['original_names'].get(key, {}).get(code):
                continue  # same as the game: nothing to keep
            names.setdefault(key, {})[code] = text
    project().save_team(tid, names)
    with db() as con:
        return queries.team(con, lang(), tid)


@app.delete('/api/teams/{tid}/edits')
def reset_team(tid: int):
    project().reset_team(tid)
    with db() as con:
        return queries.team(con, lang(), tid)


@app.get('/api/players/{pid}')
def player_detail(pid: int):
    with db() as con:
        out = queries.player(con, lang(), pid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


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
