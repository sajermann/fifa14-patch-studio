"""HTTP API of the FIFA 14 Patch Studio (FastAPI). The interface is served from the same address (frontend/dist)."""
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import settings  # noqa: I001 - first: it puts the core folder on the path

from f14mod import (buildcache, builder, fields, fifa14, flags, images, install_check, installer, kitprint,  # noqa: E402
                    preview, teamkits, workers)

from . import diagnostics, dialogs, patch_info, queries, validation  # noqa: E402
from .state import GameState, Jobs, project  # noqa: E402

log = logging.getLogger('f14api')

game = GameState()
jobs = Jobs()
build_progress: dict = {'running': False}  # last/current build, read by GET /api/patch/progress
build_cancel = threading.Event()  # set by POST /api/patch/build/cancel: the build stops at its next check
BUILD_CACHE_DIR = os.path.join(settings.CACHE_DIR, 'build')  # f14mod.buildcache


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

@app.get('/api/issues')
def get_issues():
    """The project's problems (errors stop the build, warnings do not); empty while the game is not ready."""
    if game.state != 'ready' or not game.catalog_path:
        return {'issues': []}
    with db() as con:
        return {'issues': validation.issues(con, lang())}


@app.get('/api/status')
def get_status():
    cfg = settings.load()
    return {'version': settings.APP_VERSION, 'config': cfg.model_dump(), 'names_language': cfg.shown_language(),
            'game': game.status(), 'project': project().counts(), 'job': jobs.view(),
            'patch_built': os.path.isdir(settings.PATCH_DIR) and bool(os.listdir(settings.PATCH_DIR)),
            'patch': patch_info.status(settings.PATCH_DIR, project().path),
            'folders': _folders(cfg), 'setup': _setup_state(cfg)}


def _setup_state(cfg: settings.Config) -> dict:
    """What the first-run screen needs (the Street Studio's): done when a usable game is chosen and the current
    notice was accepted; nothing else opens before it."""
    reasons = [r for r, bad in (('game_dir', not cfg.game_dir or game.state in ('empty', 'invalid')),
                                ('terms', cfg.terms_version != settings.TERMS_VERSION)) if bad]
    return {'required': bool(reasons), 'reasons': reasons, 'terms_version': settings.TERMS_VERSION}


def _folders(cfg: settings.Config) -> dict:
    """The app's folders the Settings show: the project (the user can change it), the install backups (inside the
    game folder: uninstalling puts them back), the built patch and the logs."""
    return {'project': cfg.project_folder(), 'default_project': settings.PROJECT_DIR,
            'backups': os.path.join(game.game_dir, installer.BACKUP_DIR) if game.game_dir else None,
            'patch': settings.PATCH_DIR, 'logs': settings.LOG_DIR}


@app.get('/api/machine')
def machine():
    """What the build may use on this machine (f14mod.workers.describe): cores and memory the system reports (None
    when it does not tell), the defaults and the worker processes the current settings give."""
    cfg = settings.load()
    return workers.describe(cfg.build_cores, cfg.build_memory_percent)


class SettingsBody(BaseModel):
    language: Optional[settings.Language] = None
    names_language: Optional[str] = None
    face_pack_dirs: Optional[list[str]] = None
    build_cores: Optional[int] = None  # null = the default
    build_memory_percent: Optional[int] = None
    project_dir: Optional[str] = None  # null or empty = the default folder


@app.put('/api/settings')
def put_settings(body: SettingsBody):
    cfg = settings.load()
    if 'project_dir' in body.model_fields_set:
        folder = (body.project_dir or '').strip()
        body.project_dir = None if not folder or os.path.normcase(os.path.abspath(folder)) == os.path.normcase(
            os.path.abspath(settings.PROJECT_DIR)) else os.path.abspath(folder)
        if body.project_dir != cfg.project_dir:
            if (jobs.view() or {}).get('state') == 'running':
                raise ApiError(409, 'busy')
            try:  # a folder the app can write to (the project is created there on first use)
                os.makedirs(body.project_dir or settings.PROJECT_DIR, exist_ok=True)
            except OSError as e:
                raise ApiError(400, 'project_dir_invalid', str(e))
    # validated again: the build settings are brought into range (settings.Config)
    return settings.save(settings.Config.model_validate(
        {**cfg.model_dump(), **body.model_dump(exclude_unset=True)})).model_dump()


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


class SetupBody(BaseModel):
    game_dir: str
    face_pack_dirs: list[str] = []
    terms_version: int
    build_cores: Optional[int] = None  # brought into range by settings.Config
    build_memory_percent: Optional[int] = None


@app.post('/api/setup/apply')
def setup_apply(body: SetupBody):
    """Saves the first-run choices (the Street Studio's setup): the notice, a usable game, the face pack folders and
    the build settings; then the app starts reading the game."""
    if body.terms_version != settings.TERMS_VERSION:
        raise ApiError(409, 'terms_not_accepted')
    result = install_check.check(body.game_dir.strip().strip('"'))
    if result['state'] not in ('clean', 'patched'):
        raise ApiError(400, 'game_not_usable', result['state'])
    cfg = settings.load()
    changed = cfg.game_dir != result['game_dir'] or game.state not in ('ready', 'building')
    cfg = settings.save(settings.Config.model_validate({
        **cfg.model_dump(), 'game_dir': result['game_dir'],
        'face_pack_dirs': [f.strip() for f in body.face_pack_dirs if f.strip()],
        'terms_version': body.terms_version, 'build_cores': body.build_cores,
        'build_memory_percent': body.build_memory_percent}))
    if changed:
        try:
            game.open(cfg.game_dir)
        except RuntimeError:
            raise ApiError(409, 'busy')
    return {'game': game.status(), 'setup': _setup_state(cfg)}


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
                 page: int = 1, size: int = queries.DEFAULT_PAGE_SIZE, ids: Optional[str] = None):
    """`ids` (comma separated) = only these leagues (the list a page is editing)."""
    with db() as con:
        return queries.leagues(con, lang(), q, sort, dir, page, size, country=country, ids=_id_list(ids))


def _id_list(ids: Optional[str]) -> Optional[list[int]]:
    try:
        return [int(x) for x in ids.split(',') if x.strip()] if ids is not None else None
    except ValueError:
        raise ApiError(400, 'bad_request', 'ids')


@app.get('/api/teams')
def list_teams(q: str = '', league: Optional[int] = None, edited: Optional[str] = None, sort: Optional[str] = None,
               dir: Optional[str] = None, page: int = 1, size: int = queries.DEFAULT_PAGE_SIZE,
               ids: Optional[str] = None):
    """`ids` (comma separated) = only these teams (the list a page is editing)."""
    try:
        only_ids = [int(x) for x in ids.split(',') if x.strip()] if ids is not None else None
    except ValueError:
        raise ApiError(400, 'bad_request', 'ids')
    with db() as con:
        return queries.teams(con, lang(), q, league, _yes_no(edited), sort, dir, page, size, ids=only_ids)


@app.get('/api/players')
def list_players(q: str = '', team: Optional[int] = None, position: Optional[int] = None,
                 sort: Optional[str] = None, dir: Optional[str] = None, page: int = 1,
                 size: int = queries.DEFAULT_PAGE_SIZE, origin: Optional[str] = None, status: Optional[str] = None,
                 face: Optional[str] = None):
    with db() as con:
        return queries.players(con, lang(), q, team, position, sort, dir, page, size, origin, status, face == 'yes')


@app.get('/api/options')
def filter_options():
    """Small lists for the filter selects and the language fields."""
    with db() as con:
        return {
            # sorted outside: inside the select, fold(name) would sort by the table's own name column
            'leagues': [dict(r) for r in con.execute(
                f'SELECT * FROM (SELECT l.id, {queries._league_name()} AS name FROM v_leagues l) '  # noqa: SLF001
                'ORDER BY fold(name)', {'lang': lang()})],
            'positions': [{'id': i, 'name': n} for i, n in enumerate(fifa14.POSITIONS[:28])],
            'languages': queries.languages(con),
            'nations': [dict(r) for r in con.execute(
                f'SELECT * FROM (SELECT n.id, {queries._country_name()} AS name, n.is_new FROM v_nations n) '  # noqa: SLF001
                'ORDER BY fold(name)', {'lang': lang()})],
            'teams': [dict(r) for r in con.execute(
                f"SELECT * FROM (SELECT t.id, {queries._team_name('full')} AS name FROM v_teams t) ORDER BY fold(name)",  # noqa: SLF001
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
        if spec.kind == 'nations' and any(
                not con.execute('SELECT 1 FROM v_nations WHERE id = ?', (v,)).fetchone() for v in value):
            raise ApiError(400, 'field_out_of_range', name)
        if spec.kind == 'nation' and not (spec.optional and value == 0) and                 not con.execute('SELECT 1 FROM v_nations WHERE id = ?', (value,)).fetchone():
            raise ApiError(400, 'field_out_of_range', name)
        if spec.kind == 'team' and not con.execute('SELECT 1 FROM v_teams WHERE id = ?', (value,)).fetchone():
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


# ---- free countries and leagues (created by the user) --------------------------------------------------------------

@app.get('/api/countries')
def list_countries(q: str = '', origin: Optional[str] = None, status: Optional[str] = None,
                   sort: Optional[str] = None, dir: Optional[str] = None, page: int = 1,
                   size: int = queries.DEFAULT_PAGE_SIZE):
    with db() as con:
        return queries.countries(con, lang(), q, sort, dir, page, size, origin=origin, status=status)


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


class LeaguesBody(BaseModel):
    league_ids: list[int]
    # leagues of league_ids left out of the patch in this country only (League.hidden_in_countries); None = unchanged
    hidden_league_ids: Optional[list[int]] = None


@app.put('/api/countries/{cid}/leagues')
def save_country_leagues(cid: int, body: LeaguesBody):
    """The whole list of leagues shown in a country. A league added gets the country as its own (when it has none)
    or as one more country; a league removed loses it (its next country becomes its own, or it is left without).
    `hidden_league_ids`: the leagues left out of the patch in this country only (they stay in it in the app)."""
    wanted = list(dict.fromkeys(body.league_ids))
    with db() as con:
        if queries.country(con, lang(), cid) is None:
            raise ApiError(404, 'not_found')
        now = {r[0] for r in con.execute(
            f"SELECT l.id FROM v_leagues l WHERE {queries._in_country('l', '?')}", (cid, cid))}  # noqa: SLF001
        hidden_now = {r[0] for r in con.execute(
            "SELECT f.id FROM p.fields f, json_each(f.value) j WHERE f.kind = 'league' "
            "AND f.field = 'hidden_in_countries' AND j.value = ?", (cid,))}
        hidden_wanted = hidden_now if body.hidden_league_ids is None else set(body.hidden_league_ids)
        hidden_wanted &= set(wanted)
        changes: dict[int, dict] = {}
        for lid in (set(wanted) ^ now) | (hidden_wanted ^ (hidden_now & set(wanted))):
            detail = queries.league(con, lang(), lid)
            if detail is None:
                raise ApiError(400, 'unknown_league', str(lid))
            values = {**detail['values'], **detail['saved']}
            own, extra = values.get('countryid') or 0, list(values.get('extra_countries') or [])
            hidden = [c for c in values.get('hidden_in_countries') or [] if c != cid]
            if lid not in wanted:  # removed
                if own == cid:
                    own, extra = (extra[0], extra[1:]) if extra else (0, extra)
                else:
                    extra = [c for c in extra if c != cid]
            elif lid in now:
                pass  # stays: only shown or hidden here
            elif not own:
                own = cid
            else:
                extra.append(cid)
            if lid in hidden_wanted:
                hidden.append(cid)
            form = {**detail['saved'], 'countryid': own, 'extra_countries': extra, 'hidden_in_countries': hidden}
            changes[lid] = _clean_fields(con, 'league', lid, form, detail)
    for lid, kept in changes.items():
        project().save('league', lid, project().names('league', lid), kept)
    with db() as con:
        return queries.country(con, lang(), cid)


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
        if con.execute(f"SELECT 1 FROM v_leagues l WHERE {queries._in_country('l', '?')}",  # noqa: SLF001
                       (cid, cid)).fetchone():
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
        kept.setdefault('countryid', 0)  # no country yet: added to one in the country's page (hidden until then)
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
    hidden_team_ids: list[int] = []  # out of the patch in this league only


@app.put('/api/leagues/{lid}/teams')
def save_league_teams(lid: int, body: TeamsBody):
    """The whole team list of a league (a team can be in several leagues)."""
    team_ids = list(dict.fromkeys(body.team_ids))
    with db() as con:
        if queries.league(con, lang(), lid) is None:
            raise ApiError(404, 'not_found')
        if team_ids:
            marks = ','.join('?' * len(team_ids))
            found = {r[0] for r in con.execute(f'SELECT id FROM v_teams WHERE id IN ({marks})', team_ids)}
            missing = [t for t in team_ids if t not in found]
            if missing:
                raise ApiError(400, 'unknown_team', str(missing[0]))
        others = con.execute('SELECT COUNT(*) FROM v_league_teams WHERE league_id != ?', (lid,)).fetchone()[0]
        if others + len(team_ids) > fifa14.MAX_LEAGUE_LINKS:
            raise ApiError(409, 'limit_league_links', str(fifa14.MAX_LEAGUE_LINKS))
    project().set_members(lid, team_ids, {t for t in body.hidden_team_ids if t in team_ids})
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


class TeamLeaguesBody(BaseModel):
    league_ids: list[int]
    hidden_league_ids: list[int] = []  # leagues where the team is out of the patch


@app.put('/api/teams/{tid}/leagues')
def save_team_leagues(tid: int, body: TeamLeaguesBody):
    """The leagues the team plays in, set from the team's screen: each league that gains or loses it keeps its own
    team list (the same one the league's screen edits; a league left with the game's teams follows the game again)."""
    wanted = list(dict.fromkeys(body.league_ids))
    with db() as con:
        if queries.team(con, lang(), tid) is None:
            raise ApiError(404, 'not_found')
        if wanted:
            marks = ','.join('?' * len(wanted))
            found = {r[0] for r in con.execute(f'SELECT id FROM v_leagues WHERE id IN ({marks})', wanted)}
            missing = [lid for lid in wanted if lid not in found]
            if missing:
                raise ApiError(400, 'unknown_league', str(missing[0]))
        current = {r[0] for r in con.execute('SELECT league_id FROM v_league_teams WHERE team_id = ?', (tid,))}
        now_hidden = {r[0] for r in con.execute(
            'SELECT league_id FROM v_league_teams WHERE team_id = ? AND hidden = 1', (tid,))}
        want_hidden = {lid for lid in body.hidden_league_ids if lid in wanted}
        changed = (current ^ set(wanted)) | (now_hidden ^ want_hidden)
        lists = {lid: [r[0] for r in con.execute('SELECT team_id FROM v_league_teams WHERE league_id = ? ORDER BY ord',
                                                 (lid,))] for lid in changed}
        hidden_in = {lid: {r[0] for r in con.execute(
            'SELECT team_id FROM v_league_teams WHERE league_id = ? AND hidden = 1', (lid,))} for lid in changed}
        game = {lid: [r[0] for r in con.execute('SELECT team_id FROM league_teams WHERE league_id = ?', (lid,))]
                for lid in changed}
        links = queries.league_link_count(con) + len(set(wanted) - current) - len(current - set(wanted))
        if links > fifa14.MAX_LEAGUE_LINKS:
            raise ApiError(409, 'limit_league_links', str(fifa14.MAX_LEAGUE_LINKS))
    for lid, ids in lists.items():
        team_ids = [*ids, tid] if lid in wanted else [x for x in ids if x != tid]
        hidden = (hidden_in[lid] - {tid}) | ({tid} if lid in want_hidden else set())
        follows_game = not hidden and not project().is_created('league', lid) and sorted(team_ids) == sorted(game[lid])
        project().set_members(lid, None if follows_game else team_ids, hidden)
    with db() as con:
        return queries.team(con, lang(), tid)


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
def crest_image(tid: int, size: Optional[int] = None, game_only: bool = False):
    """The team's crest: the user's picture, else the game's file (a created team: the one of the team it copies, or
    the plain crest with its short name). `game_only` skips the user's picture."""
    own = None if game_only else project().picture('team', tid, 'crest')
    if own:
        return _png_response(images.fit(images.decode_png(own[0]), (256, 256)), size)
    source = project().team_source(tid)
    if source and project().is_created('team', tid):
        template, copy = source
        if copy:
            return _picture('crest', template, fifa14.CREST.format(template), size)
        with db() as con:
            team = _team(con, tid)
        names = builder.with_derived_names('team', team['saved_names'])
        c1 = team['saved'].get('teamcolor1') or team['values'].get('teamcolor1') or [128, 128, 128]
        c2 = team['saved'].get('teamcolor2') or team['values'].get('teamcolor2') or [255, 255, 255]
        return _png_response(teamkits.plain_crest(builder._shown_name(names, 'abbr3'), c1, c2), size)  # noqa: SLF001
    return _picture('crest', tid, fifa14.CREST.format(tid), size)


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


@app.post('/api/league-logo-preview')
def league_logo_preview(body: PictureBody, size: Optional[int] = None):
    """A chosen picture fitted as the league's logo, without saving it (the page saves it with Save)."""
    import base64
    import binascii
    try:
        png = images.normalize_picture(base64.b64decode(body.data, validate=True))
    except (images.PictureError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))
    img = images.fit(images.decode_png(png), (256, 256))
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
def league_image(lid: int, size: Optional[int] = None, game_only: bool = False):
    """The league's logo: the user's picture (as it goes to the game, fitted in the square), else the game's file.
    `game_only` skips the user's picture."""
    own = None if game_only else project().picture('league', lid, 'logo')
    if own:
        img = images.fit(images.decode_png(own[0]), (256, 256))
        if size:
            img = images.thumbnail(img, min(max(size, 16), 512))
        return Response(images.png(img), media_type='image/png', headers={'Cache-Control': 'no-cache'})
    return _picture('league', lid, fifa14.LEAGUE_IMAGES['logo'].format(lid), size)


@app.put('/api/leagues/{lid}/logo')
def upload_league_logo(lid: int, body: PictureBody):
    """The league's own picture: the patch draws the eight league pictures from it."""
    import base64
    import binascii
    with db() as con:
        if queries.league(con, lang(), lid) is None:
            raise ApiError(404, 'not_found')
    try:
        png = images.normalize_picture(base64.b64decode(body.data, validate=True))
    except (images.PictureError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))
    project().set_picture('league', lid, 'logo', png)
    with db() as con:
        return queries.league(con, lang(), lid)


@app.delete('/api/leagues/{lid}/logo')
def remove_league_logo(lid: int):
    project().set_picture('league', lid, 'logo', None)
    with db() as con:
        out = queries.league(con, lang(), lid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


class HiddenBody(BaseModel):
    # the Hide button (same rule as the Street Studio): a created entity hidden is out of the patch, an original one
    # is hidden in the game by the project
    hidden: bool


def _set_hidden(kind: str, oid: int, body: HiddenBody):
    with db() as con:
        if DETAILS[kind](con, lang(), oid) is None:
            raise ApiError(404, 'not_found')
    project().set_hidden(kind, oid, body.hidden)
    with db() as con:
        return DETAILS[kind](con, lang(), oid)


@app.put('/api/leagues/{lid}/hidden')
def set_league_hidden(lid: int, body: HiddenBody):
    """Hide: a created league is left out of the patch; a league of the game is hidden in it (country 0)."""
    return _set_hidden('league', lid, body)


@app.put('/api/countries/{cid}/hidden')
def set_country_hidden(cid: int, body: HiddenBody):
    """Hide: a created country is left out of the patch; a country of the game is hidden in it (its leagues leave
    it; a league with no other country is hidden)."""
    return _set_hidden('country', cid, body)


@app.put('/api/teams/{tid}/hidden')
def set_team_hidden(tid: int, body: HiddenBody):
    """Hide: a team of the game is hidden in it (linked only to a hidden league)."""
    return _set_hidden('team', tid, body)


# ---- teams: create, delete, squad, crest, kits (test TN1) -------------------------------------------------------

class CreateTeamBody(BaseModel):
    names: dict[str, dict[str, str]] = {}
    fields: dict = {}  # e.g. the colors of a team made from scratch
    template: Optional[int] = None  # the team it starts from (its values; its crest and kits too when `copy`)
    copy: bool = False  # a copy of `template`: its crest, kits, formation (and squad with `copy_squad`)
    copy_squad: bool = False
    league_ids: list[int] = []


def _team(con, tid: int) -> dict:
    out = queries.team(con, lang(), tid)
    if out is None:
        raise ApiError(404, 'not_found')
    return out


@app.post('/api/teams')
def create_team(body: CreateTeamBody):
    """A new team: made from scratch (the values of a model team, a plain crest with its short name, generic kits,
    no players) or a copy of a team of the game (its crest, kits and formation; its squad when asked)."""
    _required_name('team', body.names)
    template = body.template if body.template is not None else teamkits.MODEL_TEAM
    with db() as con:
        if not con.execute('SELECT 1 FROM teams WHERE id = ?', (template,)).fetchone():
            raise ApiError(400, 'unknown_team', str(template))
        for lid in body.league_ids:
            if queries.league(con, lang(), lid) is None:
                raise ApiError(400, 'unknown_league', str(lid))
        tid = queries.free_team_id(con)
        names = _clean_names('team', body.names, {}, set(queries.languages(con)))
        values = fields.original_values('team', json.loads(
            con.execute('SELECT raw FROM teams WHERE id = ?', (template,)).fetchone()[0]))
        kept = _clean_fields(con, 'team', tid, body.fields, {'values': values, 'roster': []})
        members = {lid: [r[0] for r in con.execute(
            'SELECT team_id FROM v_league_teams WHERE league_id = ? ORDER BY ord, team_id', (lid,))]
            for lid in body.league_ids}
    project().create('team', tid, names, kept)
    project().set_team_source(tid, template, body.copy)
    if not (body.copy and body.copy_squad):
        project().set_roster(tid, [])
    for lid, team_ids in members.items():
        project().set_members(lid, team_ids + [tid])
    with db() as con:
        return _team(con, tid)


@app.delete('/api/teams/{tid}')
def delete_team(tid: int):
    if not project().is_created('team', tid):
        raise ApiError(400, 'not_created')
    project().delete('team', tid)
    return {'deleted': tid}


class RosterRow(BaseModel):
    player: int
    jersey: Optional[int] = None
    slot: int = 29  # 0-27 = starter in that position, 28 = bench, 29 = out of the squad
    hidden: bool = False  # out of the patch in this team only (kept in the squad on the screen)


class RosterBody(BaseModel):
    rows: Optional[list[RosterRow]] = None  # None = the game's squad again


@app.put('/api/teams/{tid}/roster')
def save_team_roster(tid: int, body: RosterBody):
    """The whole squad of a team, in order (a player can be in several teams); more than the game shows (41) stay
    out of the patch."""
    rows = None
    with db() as con:
        _team(con, tid)
        if body.rows is not None:
            seen = set()
            for r in body.rows:
                if r.player in seen:
                    raise ApiError(400, 'duplicate_player', str(r.player))
                seen.add(r.player)
                if not 0 <= r.slot <= 29 or (r.jersey is not None and not 1 <= r.jersey <= 99):
                    raise ApiError(400, 'field_out_of_range', str(r.player))
                if not con.execute('SELECT 1 FROM v_players WHERE id = ?', (r.player,)).fetchone():
                    raise ApiError(400, 'unknown_player', str(r.player))
            rows = [r.model_dump() for r in body.rows]
    if rows is None and project().is_created('team', tid):
        rows = []  # a created team has no game squad to go back to
    project().set_roster(tid, rows)
    with db() as con:
        return _team(con, tid)


def _png_of(data: str) -> bytes:
    import base64
    import binascii
    try:
        return images.normalize_picture(base64.b64decode(data, validate=True))
    except (images.PictureError, binascii.Error) as e:
        raise ApiError(400, 'bad_picture', str(e))


@app.put('/api/teams/{tid}/crest')
def upload_team_crest(tid: int, body: PictureBody):
    """The team's crest picture: the patch draws every crest size from it."""
    with db() as con:
        _team(con, tid)
    project().set_picture('team', tid, 'crest', _png_of(body.data))
    with db() as con:
        return _team(con, tid)


@app.delete('/api/teams/{tid}/crest')
def remove_team_crest(tid: int):
    project().set_picture('team', tid, 'crest', None)
    with db() as con:
        return _team(con, tid)


class KitBody(BaseModel):
    config: Optional[dict] = None  # None = the game's kit (or the team it copies) again
    pictures: dict[str, Optional[str]] = {}  # jersey / shorts / mini: base64 to set, null to remove, absent = kept


KIT_PARTS = ('jersey', 'shorts', 'mini')


def _check_kit(con, config: dict) -> dict:
    source = config.get('source')
    out: dict = {'source': source}
    if source == 'game':
        team, kind = int(config.get('team', 0)), int(config.get('kind', 0))
        if not con.execute('SELECT 1 FROM team_kits WHERE team_id = ? AND kind = ?', (team, kind)).fetchone():
            raise ApiError(400, 'unknown_kit', f'{team}:{kind}')
        out.update(team=team, kind=kind)
    elif source == 'generic':
        model = int(config.get('model', 0))
        if model not in queries.kit_models(con):
            raise ApiError(400, 'unknown_kit', str(model))
        colors = config.get('colors') or []
        if len(colors) != 2 or any(len(c) != 3 or any(not 0 <= int(v) <= 255 for v in c) for c in colors):
            raise ApiError(400, 'field_bad_value', 'colors')
        out.update(model=model, colors=[[int(v) for v in c] for c in colors])
    elif source not in ('upload', 'keep'):
        raise ApiError(400, 'field_bad_value', 'source')
    if config.get('collar') is not None:
        collar = int(config['collar'])
        if collar not in teamkits.COLLARS:
            raise ApiError(400, 'field_out_of_range', 'collar')
        out['collar'] = collar
    if config.get('print'):
        out['print'] = _check_print(con, config['print'])
    return out


def _check_print(con, values: dict) -> dict:
    """Name and numbers of a kit (f14mod.teamkits.PRINT), checked against what the game has."""
    fonts = queries.kit_fonts(con)
    name_fonts = {f['id'] for f in fonts['name']}
    out: dict = {}
    for key, value in values.items():
        if value is None:
            continue
        if key not in teamkits.PRINT:
            raise ApiError(400, 'field_unknown_field', key)
        if key in teamkits.BOOL_PRINT:
            out[key] = bool(value)
        elif key == 'name_color':
            if len(value) != 3 or any(not 0 <= int(v) <= 255 for v in value):
                raise ApiError(400, 'field_bad_value', key)
            out[key] = [int(v) for v in value]
        else:
            v = int(value)
            ok = {'number_color': 0 <= v <= 19, 'shorts_number_color': 0 <= v <= 19, 'name_layout': v in (0, 1),
                  'name_font': v in name_fonts, 'number_font': v in fonts['number'],
                  'shorts_number_font': v in fonts['number']}[key]
            if not ok:
                raise ApiError(400, 'field_out_of_range', key)
            out[key] = v
    return out


@app.put('/api/teams/{tid}/kits/{kind}')
def save_team_kit(tid: int, kind: int, body: KitBody):
    """One kit of a team: a kit of the game, the user's pictures (FIFA 14-16 layout) or a generic kit (one of the
    game's mask kits painted with two colors)."""
    if kind not in queries.KIT_KINDS:
        raise ApiError(404, 'not_found')
    with db() as con:
        _team(con, tid)
        config = _check_kit(con, body.config) if body.config is not None else None
    for part, data in body.pictures.items():
        if part not in KIT_PARTS:
            raise ApiError(400, 'bad_request', part)
        project().set_picture('team', tid, f'kit{kind}_{part}', _png_of(data) if data else None)
    if config is None:
        for part in KIT_PARTS:
            project().set_picture('team', tid, f'kit{kind}_{part}', None)
    project().set_kit(tid, kind, config)
    with db() as con:
        return _team(con, tid)


@app.get('/api/kit-fonts')
def kit_fonts():
    with db() as con:
        return queries.kit_fonts(con)


@app.get('/api/kit-models')
def kit_models():
    with db() as con:
        return {'models': queries.kit_models(con)}


def _hex(value: Optional[str], default) -> list[int]:
    try:
        return [int(value[i:i + 2], 16) for i in (0, 2, 4)] if value and len(value) == 6 else list(default)
    except ValueError:
        return list(default)


def _png_response(img, size: Optional[int], cache: str = 'no-cache'):
    if size:
        img = images.thumbnail(img, min(max(size, 16), 1024))
    return Response(images.png(img), media_type='image/png', headers={'Cache-Control': cache})


@app.get('/api/image/kitmodel/{model}')
def kit_model_image(model: int, c1: Optional[str] = None, c2: Optional[str] = None, part: str = 'mini',
                    size: Optional[int] = None):
    """A generic mask kit painted with two colors (hex RRGGBB): its minikit, or the jersey/shorts texture."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    files = game.files()
    config = {'source': 'generic', 'model': model, 'colors': [_hex(c1, (255, 255, 255)), _hex(c2, (30, 30, 30))]}
    if part in ('jersey', 'shorts'):
        data = files.read(teamkits.KIT_FILE.format(model, 0))
        if data is None:
            raise ApiError(404, 'not_found')
        img = teamkits.paint_mask(teamkits.textures(data)[part], *config['colors'])
    else:
        img = images.decode_dds(teamkits.minikit(files, config, 0, teamkits.MODEL_TEAM, None))
    return _png_response(img, size, IMAGE_HEADERS['Cache-Control'])


def _saved_kit_config(team: dict, tid: int, kind: int) -> dict:
    """The kit as the patch makes it (the user's config, else the team's default); 404 when the team has none."""
    kit = next((k for k in team['kits'] if k['kind'] == kind), None)
    if kit is None:
        raise ApiError(404, 'not_found')
    template = team['template'] or tid
    config = kit['config']
    if config is None and kit['default'] == 'generic':
        color = lambda n, default: team['saved'].get(f'teamcolor{n}') or team['values'].get(f'teamcolor{n}') or default  # noqa: E731
        c1, c2 = color(1, [200, 200, 200]), color(2, [255, 255, 255])
        defaults = {0: {'source': 'generic', 'model': teamkits.DEFAULT_MASKS[0], 'colors': [c1, c2]},
                    1: {'source': 'generic', 'model': teamkits.DEFAULT_MASKS[1], 'colors': [c2, c1]},
                    2: {'source': 'game', 'team': teamkits.GENERIC_GOALKEEPER, 'kind': 2}}
        config = defaults[kind]
    elif config is None and kit['default'] == 'game':
        config = {'source': 'game', 'team': template if team['copied'] else tid, 'kind': kind}
    if config is None:
        raise ApiError(404, 'not_found')
    return config


def _team_crest(team: dict, tid: int, pending=None):
    """The crest the patch puts on a generic kit (same rule as the builder): the user's picture, a plain crest for a
    team made from scratch, else the game's crest of the team (or of its model). pending = a crest chosen on the page
    and not saved yet (a picture, or 'remove')."""
    if pending is not None and pending != 'remove':
        return pending
    found = project().picture('team', tid, 'crest') if pending is None else None
    if found:
        return images.decode_png(found[0])
    if team['is_new'] and not team['copied']:
        color = lambda n, default: team['saved'].get(f'teamcolor{n}') or team['values'].get(f'teamcolor{n}') or default  # noqa: E731
        return teamkits.plain_crest(team.get('abbr3') or '', color(1, [200, 200, 200]), color(2, [255, 255, 255]))
    data = game.files().read(teamkits.CREST_FILE.format('crest', team['template'] or tid))
    try:
        return images.decode_dds(data) if data is not None else None
    except images.UNREADABLE:
        return None


@app.get('/api/image/kit/{tid}/{kind}')
def team_kit_image(tid: int, kind: int, part: str = 'mini', size: Optional[int] = None):
    """A kit of a team as the patch makes it: the minikit (`part=mini`) or the jersey/shorts texture."""
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    with db() as con:
        team = _team(con, tid)
    files, p = game.files(), project()
    template = team['template'] or tid
    config = _saved_kit_config(team, tid, kind)
    pics = {}
    for name in KIT_PARTS:
        found = p.picture('team', tid, f'kit{kind}_{name}')
        if found:
            pics[name] = images.decode_png(found[0])
    try:
        if part == 'mini':
            tint = config if config.get('colors') or 'jersey' not in pics else \
                {**config, 'colors': [list(pics['jersey'].convert('RGB').resize((1, 1)).getpixel((0, 0)))]}
            img = images.decode_dds(teamkits.minikit(files, tint, kind, template, pics.get('mini')))
        elif config['source'] == 'upload':
            img = pics.get(part if part in ('jersey', 'shorts') else 'jersey')
            if img is None:
                raise ApiError(404, 'not_found')
        elif config['source'] == 'generic':
            data = files.read(teamkits.KIT_FILE.format(config['model'], 0))
            img = teamkits.paint_mask(teamkits.textures(data)['jersey' if part != 'shorts' else 'shorts'],
                                      *config['colors'])
        else:
            data = files.read(teamkits.KIT_FILE.format(config['team'], config.get('kind', kind)))
            img = teamkits.textures(data)['jersey' if part != 'shorts' else 'shorts']
    except (FileNotFoundError, KeyError, TypeError, images.UNREADABLE) as e:
        raise ApiError(404, 'not_found', str(e))
    return _png_response(img, size)


# ---- 3D preview of a kit: game meshes (GLB) and textures (PNG) of the player that wears it -------------------------

class KitPrintBody(BaseModel):
    part: str = 'jersey'
    config: Optional[dict] = None
    values: dict = {}
    number: Optional[int] = None
    name: Optional[str] = None
    crest: Optional[str] = None  # the crest chosen on the page and not saved yet: base64 picture, or 'remove'


@app.get('/api/preview/kit-print/{tid}/{kind}.png')
def preview_kit_print(tid: int, kind: int, part: str = 'jersey', config: Optional[str] = None,
                      values: Optional[str] = None, number: Optional[int] = None, name: Optional[str] = None):
    """What the game draws over a kit's jersey or shorts texture (crest, name, numbers) as a transparent picture with
    the same UVs. config = the kit's config still being edited (JSON; none = the saved one); values = its name and
    numbers (JSON, teamkits.PRINT keys); number/name = the player who wears it."""
    import json as json_lib
    try:
        cfg = json_lib.loads(config) if config else None
        shown = json_lib.loads(values) if values else {}
    except ValueError:
        raise ApiError(400, 'bad_request')
    return _kit_print(tid, kind, part, cfg, shown, number, name, None)


@app.post('/api/preview/kit-print/{tid}/{kind}.png')
def preview_kit_print_pending(tid: int, kind: int, body: KitPrintBody):
    """The same layer with a crest not saved yet (too big for a query)."""
    import base64
    import binascii
    crest = None
    if body.crest == 'remove':
        crest = 'remove'
    elif body.crest:
        try:
            crest = images.decode_png(images.normalize_picture(base64.b64decode(body.crest, validate=True)))
        except (binascii.Error, *images.UNREADABLE) as e:
            raise ApiError(400, 'bad_picture', str(e))
    return _kit_print(tid, kind, body.part, body.config, body.values, body.number, body.name, crest)


def _kit_print(tid: int, kind: int, part: str, cfg, shown, number, name, crest):
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    if part not in ('jersey', 'shorts'):
        raise ApiError(404, 'not_found')
    with db() as con:
        team = _team(con, tid)
    if not isinstance(cfg, dict) or cfg.get('source') in (None, 'keep'):
        cfg = _saved_kit_config(team, tid, kind)
    if not isinstance(shown, dict):
        shown = {}
    files, template = game.files(), team['template'] or tid
    crest_picture = None  # the kit file's own crest_cm
    if cfg['source'] == 'game':
        data = files.read(teamkits.KIT_FILE.format(cfg.get('team'), cfg.get('kind', kind)))
    elif cfg['source'] == 'generic':
        data = files.read(teamkits.KIT_FILE.format(cfg.get('model'), 0))
        crest_picture = _team_crest(team, tid, crest) or teamkits.EMPTY
    else:  # upload: the model kit's table; the pictures already carry the crest
        data = next((d for t, k in ((template, kind), (template, 0), (teamkits.MODEL_TEAM, kind),
                                    (teamkits.MODEL_TEAM, 0)) if (d := files.read(teamkits.KIT_FILE.format(t, k)))),
                    None)
        crest_picture = teamkits.EMPTY
    size = (1024, 1024) if part == 'jersey' else (1024, 512)
    try:
        img = kitprint.decal(files, data, part, size, shown, number=number, name=name, crest_picture=crest_picture)
    except (ValueError, KeyError, TypeError, images.UNREADABLE) as e:
        raise ApiError(404, 'not_found', str(e))
    return Response(images.png(img), media_type='image/png', headers={'Cache-Control': 'no-cache'})


# ---- patch: build, install, uninstall -------------------------------------------------------------------------------

def _start(kind: str, work):
    try:
        return jobs.start(kind, work)
    except RuntimeError:
        raise ApiError(409, 'busy')


NAME_SQL = {'team': f'SELECT {queries._team_name("full")} FROM v_teams t WHERE t.id = :id',  # noqa: SLF001
            'league': f'SELECT {queries._league_name()} FROM v_leagues l WHERE l.id = :id',  # noqa: SLF001
            'player': f'SELECT {queries._player_name()} FROM v_players pl WHERE pl.id = :id',  # noqa: SLF001
            'country': f'SELECT {queries._country_name()} FROM v_nations n WHERE n.id = :id'}  # noqa: SLF001


def _name_lookup():
    """(kind, id) -> the shown name, for the build's progress (its own connection: the build runs in a thread)."""
    path, project_path, shown = game.catalog_path, project().path, lang()
    lock, con = threading.Lock(), [None]

    def name_of(kind: str, oid: int):
        if kind not in NAME_SQL:
            return None
        with lock:
            try:
                if con[0] is None:
                    con[0] = queries.connect(path, project_path)
                row = con[0].execute(NAME_SQL[kind], {'lang': shown, 'id': oid}).fetchone()
            except Exception:  # noqa: BLE001 - only the progress text: the id is shown instead
                log.debug('name of %s %s not found', kind, oid, exc_info=True)
                return None
        return row[0] if row else None

    def close():
        if con[0] is not None:
            con[0].close()
    return name_of, close


@app.post('/api/patch/build')
def build_patch():
    """Starts the build (a job); GET /api/patch/progress says where it is, POST /api/patch/build/cancel stops it.
    Texts and pictures go to the build cache (f14mod.buildcache): building again only makes what changed."""
    global build_progress
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    files, proj, cfg = game.files(), project(), settings.load()
    cache = buildcache.BuildCache(BUILD_CACHE_DIR)
    prog = {'running': True, 'steps': list(builder.BUILD_STEPS), 'step': None, 'done': 0, 'total': 0, 'message': '',
            'started_at': time.time(), 'finished_at': None, 'error': None, 'item': None, 'stopping': False,
            'cancelled': False, 'cache': {'reused': 0, 'made': 0}}

    def work(job_progress):
        name_of, close = _name_lookup()
        built_from = patch_info.project_hash(proj.path)  # changes saved during the build leave it "not up to date"
        steps = builder.BUILD_STEPS

        def progress(step, done, total, kind=None, name=None):
            # item: what the 'images' / 'texts' steps wait for; cache: entries reused / made so far
            prog.update(step=step, done=done, total=total, item={'kind': kind, 'name': name} if kind else None,
                        cache={'reused': cache.hits, 'made': cache.misses})
            share = done / total if total else 0
            job_progress(step, (steps.index(step) + min(1, share)) / len(steps))

        def log_line(line):  # the log only: the dialog shows the step and what it waits for
            log.info('build: %s', line)
        try:
            summary = builder.build(files, proj, settings.PATCH_DIR, progress,
                                    worker_count=workers.plan(cfg.build_cores, cfg.build_memory_percent),
                                    cache=cache, cancel=build_cancel, log=log_line, name_of=name_of)
            patch_info.write(settings.PATCH_DIR, built_from)
        except builder.BuildCancelled:
            prog['cancelled'] = True
            raise
        except Exception as e:
            prog['error'] = str(e)
            raise
        finally:
            close()
            prog.update(running=False, finished_at=time.time())
        status = patch_info.status(settings.PATCH_DIR, proj.path)
        # for "N files, X new and Y reused from the cache, in T"
        return {**summary, 'cache_reused_files': summary['reused_files'], 'files': len(status.get('files', [])),
                'duration_s': round(prog['finished_at'] - prog['started_at'], 1)}

    build_cancel.clear()
    job = _start('build', work)
    build_progress = prog
    return job


@app.post('/api/patch/build/cancel')
def cancel_build():
    """Asks the running build to stop. It stops at its next check, after the languages being made end (they go to
    the build cache, like everything made before: building again starts from there)."""
    if not build_progress.get('running'):
        return {'stopping': False}
    build_cancel.set()
    build_progress['stopping'] = True
    return {'stopping': True}


@app.get('/api/patch/progress')
def get_build_progress():
    """Where the current (or last) build is: step (builder.BUILD_STEPS), done/total of that step, last message."""
    prog = dict(build_progress)
    if prog.get('started_at'):
        prog['elapsed'] = round((prog['finished_at'] or time.time()) - prog['started_at'], 1)
    return prog


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


@app.get('/api/logs/report')
def logs_report():
    """Plain-text report for support: machine, settings, game, project, patch and the end of the log files."""
    def part(fn):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 - the report says what failed
            return [f'(failed: {type(e).__name__}: {e})']

    def game_lines():
        st = game.status()
        return [f'state: {st["state"]} | folder: {st["game_dir"]}', f'check: {st["check"]}', f'error: {st["error"]}']

    def project_lines():
        proj = project()
        return [f'file: {proj.path} ({os.path.getsize(proj.path)} bytes)', f'edited: {proj.counts()}']

    def patch_lines():
        last = {k: v for k, v in build_progress.items() if k != 'steps'}
        return [f'folder: {settings.PATCH_DIR}', f'status: {patch_info.status(settings.PATCH_DIR, project().path)}',
                f'last build: {last}', f'last job: {jobs.view()}']

    return Response(diagnostics.report({
        'settings': part(lambda: [f'{k}: {v}' for k, v in settings.load().model_dump().items()]),
        'game': part(game_lines), 'project': part(project_lines), 'patch': part(patch_lines)}),
        media_type='text/plain; charset=utf-8')


@app.post('/api/logs/open')
def logs_open():
    """Opens the log folder in the Windows Explorer (desktop app; development logs to the console)."""
    if not diagnostics.log_files():
        raise ApiError(404, 'logs_not_found')
    if hasattr(os, 'startfile'):
        os.startfile(settings.LOG_DIR)  # noqa: S606 - the app's own folder, opened in Explorer
    return {'folder': settings.LOG_DIR}


@app.post('/api/patch/open-folder')
def open_patch_folder():
    os.makedirs(settings.PATCH_DIR, exist_ok=True)
    if hasattr(os, 'startfile'):
        os.startfile(settings.PATCH_DIR)  # noqa: S606 - the app's own folder, opened in Explorer
    return {'path': settings.PATCH_DIR}


@app.get('/api/job')
def job_status():
    return jobs.view()


from . import player_routes  # noqa: E402,F401 - the player routes (before the interface's catch-all)


# ---- bulk delete (the lists' checkboxes) ----------------------------------------------------------------------------

class BulkDeleteBody(BaseModel):
    kind: str
    ids: list[int]


@app.post('/api/bulk-delete')
def bulk_delete(body: BulkDeleteBody):
    """Delete what a list picked, like the Street Studio: a created item leaves the project, an edited one of the game
    goes back to the game's. One that cannot go (a country that still has leagues) is skipped with its error code."""
    deletes = {'country': delete_country, 'league': delete_league, 'team': delete_team,
               'player': player_routes.delete_player}
    resets = {'country': reset_country, 'league': reset_league, 'team': reset_team,
              'player': player_routes.reset_player}
    if body.kind not in deletes:
        raise ApiError(400, 'bad_request', 'kind')
    deleted, reset, skipped = [], [], []
    for oid in dict.fromkeys(body.ids):
        created = project().is_created(body.kind, oid)
        try:
            (deletes if created else resets)[body.kind](oid)
        except HTTPException as e:
            skipped.append({'id': oid, 'code': (e.detail or {}).get('code', 'error') if isinstance(e.detail, dict) else 'error'})
            continue
        (deleted if created else reset).append(oid)
    return {'deleted': deleted, 'reset': reset, 'skipped': skipped}


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
