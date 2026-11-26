"""Import and export (f14mod.share): one Import page for any zip of the app or package of the extractor, and the
Export button of each entity's screen. Both show the same tree of what goes (the item, what it takes along) before
anything happens. Registered by main (imported before the interface's catch-all route).

Import: POST /api/share/inspect (the zip as the request body) keeps it in cache/share/ and answers the tree, the id
each item gets and why; POST /api/share/apply {token, keys} starts writing the chosen items into the project (a job:
GET /api/share/apply/progress, POST /api/share/apply/cancel).
Export: POST /api/share/export {kind, id} answers the tree of the entity and what it takes along (only what the
project created or changed: the game's own entities are the extractor's job); POST /api/share/export/{token}/zip
{keys} answers the zip.
"""
import logging
import os
import re
import threading
import time
import uuid

from fastapi import Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from f14mod import adboards, equipment, facefill, fifa14, share, workers
from f14mod.project import (EQUIPMENT_KINDS, FIRST_OWN_ADBOARD, FIRST_OWN_STADIUM, GAME_ADBOARD_MAX, KINDS,
                            MAX_STADIUM_ID)

from . import queries, settings
from .main import ApiError, app, db, game, jobs, lang, project

log = logging.getLogger('f14api')

STAGING_DIR = os.path.join(settings.CACHE_DIR, 'share')
STAGING_TTL = 24 * 3600
MAX_UPLOAD = share.MAX_TOTAL
FIRST_OWN_TEAM = 131001
MAX_TEAM_ID = 262143  # teamid as the database fields that point to a team hold it
PICTURE_SLOTS = {'country': ('flag',), 'league': ('logo',), 'team': ('crest',), 'player': ('photo',),
                 'adboard': ('board',), 'boot': ('thumbnail',), 'glove': ('thumbnail',), 'ball': ('thumbnail',),
                 'stadium': ('menu_0', 'menu_1', 'menu_3', 'menu_4')}

_staged: dict[str, dict] = {}
_lock = threading.Lock()


def _forget_old() -> None:
    now = time.time()
    with _lock:
        for token in [t for t, s in _staged.items() if now - s['time'] > STAGING_TTL]:
            path = _staged.pop(token).get('path')
            if path and os.path.exists(path):
                os.remove(path)
    if os.path.isdir(STAGING_DIR):  # zips of a run that ended
        for name in os.listdir(STAGING_DIR):
            full = os.path.join(STAGING_DIR, name)
            if now - os.path.getmtime(full) > STAGING_TTL:
                os.remove(full)


def _get(token: str, kind: str) -> dict:
    with _lock:
        found = _staged.get(token)
    if not found or found['kind'] != kind:
        raise ApiError(404, 'share_expired')
    return found


# ---------------------------------------------------------------- the project and the game as share.Destination

class GameDestination:
    """The ids of the game (the originals cache) and of the project, for share.plan/apply."""

    def __init__(self, con):
        self.con = con
        self.p = project()
        self._created = {k: set(self.p.created(k)) for k in KINDS}
        self._edited = {k: set(self.p.edited(k)) for k in KINDS}
        self._game: dict[str, set[int]] = {}
        self._taken_players: set[int] | None = None

    def _game_ids(self, kind: str) -> set[int]:
        if kind not in self._game:
            table = {'country': 'nations', 'league': 'leagues', 'team': 'teams', 'player': 'players',
                     'stadium': 'stadiums'}.get(kind)
            if table:
                ids = {r[0] for r in self.con.execute(f'SELECT id FROM {table}')}
            elif kind == 'adboard':
                ids = {b for b in adboards.game_boards(game.files()) if b <= GAME_ADBOARD_MAX}
            else:
                ids = set(equipment.game_codes(game.files(), kind))
            self._game[kind] = ids
        return self._game[kind]

    def in_game(self, kind, oid):
        return oid in self._game_ids(kind)

    def used(self, kind, oid):
        if oid in self._game_ids(kind) or oid in self._created[kind]:
            return True
        if kind == 'team':  # a team id some kit file of the game is named after
            return self.con.execute('SELECT 1 FROM team_kits WHERE team_id = ?', (oid,)).fetchone() is not None
        if kind == 'player':
            return oid in self._taken()
        return False

    def _taken(self) -> set[int]:
        if self._taken_players is None:
            from .player_routes import _taken_ids
            self._taken_players = _taken_ids()
        return self._taken_players

    def in_range(self, kind, oid):
        return {
            'country': 1 <= oid <= fifa14.MAX_NATION_ID,
            'league': fifa14.FIRST_FREE_LEAGUE <= oid <= fifa14.MAX_LEAGUE_ID and oid not in fifa14.RESERVED_LEAGUES,
            'team': FIRST_OWN_TEAM <= oid <= MAX_TEAM_ID,
            'player': fifa14.FIRST_FREE_PLAYER <= oid <= fifa14.MAX_PLAYER_ID,
            'stadium': FIRST_OWN_STADIUM <= oid <= MAX_STADIUM_ID,
            'adboard': oid >= FIRST_OWN_ADBOARD,
        }.get(kind, oid in equipment.CODES.get(kind, ()))

    def allocate(self, kind, reserved):
        if kind in EQUIPMENT_KINDS:
            free = equipment.free_codes(game.files(), kind, self._created[kind] | reserved)
            return free[0] if free else None
        if kind == 'adboard':
            oid = max([FIRST_OWN_ADBOARD - 1, *self._created['adboard'], *reserved]) + 1
            return oid
        first, last = {'country': (1, fifa14.MAX_NATION_ID),
                       'league': (fifa14.FIRST_FREE_LEAGUE, fifa14.MAX_LEAGUE_ID),
                       'team': (FIRST_OWN_TEAM, MAX_TEAM_ID),
                       'player': (fifa14.FIRST_FREE_PLAYER, fifa14.MAX_PLAYER_ID),
                       'stadium': (FIRST_OWN_STADIUM, MAX_STADIUM_ID)}[kind]
        return next((i for i in range(first, last + 1)
                     if i not in reserved and self.in_range(kind, i) and not self.used(kind, i)), None)

    def changed(self, kind, oid):
        return oid in self._edited[kind]

    def league_members(self, league_id):
        return [r[0] for r in self.con.execute(
            'SELECT team_id FROM v_league_teams WHERE league_id = ? ORDER BY ord, team_id', (league_id,))]

    def team_roster(self, team_id):
        return [{'player': r[0], 'jersey': r[1], 'slot': r[2]} for r in self.con.execute(
            'SELECT player_id, jersey, position FROM v_team_players WHERE team_id = ? ORDER BY ord, player_id',
            (team_id,))]


# ---------------------------------------------------------------- names and the tree

NAME_SQL = {
    'country': lambda: f'SELECT {queries._country_name("n")} FROM v_nations n WHERE n.id = :id',  # noqa: SLF001
    'league': lambda: f'SELECT {queries._league_name("l")} FROM v_leagues l WHERE l.id = :id',  # noqa: SLF001
    'team': lambda: f'SELECT {queries._team_name("full", "t")} FROM v_teams t WHERE t.id = :id',  # noqa: SLF001
    'player': lambda: f'SELECT {queries._player_name("pl")} FROM v_players pl WHERE pl.id = :id',  # noqa: SLF001
    'stadium': lambda: f'SELECT {queries._stadium_name("s")} FROM v_stadiums s WHERE s.id = :id',  # noqa: SLF001
}


def _shown_name(con, kind: str, oid: int) -> str | None:
    """The name the app shows for an entity of the game or the project."""
    if kind in NAME_SQL:
        row = con.execute(NAME_SQL[kind](), {'id': oid, 'lang': lang()}).fetchone()
        return row[0] if row else None
    name = project().fields(kind, oid).get('name')
    if name:
        return name
    if kind in EQUIPMENT_KINDS:
        from .equipment_routes import _game_names  # noqa: PLC0415
        return _game_names(kind).get(oid)
    return None


def _record_name(r: dict) -> str | None:
    """The name a record carries itself (the names language first, then any)."""
    names = (r.get('names') or {}).get('full') or {}
    text = names.get(lang()) or names.get('*') or next(iter(names.values()), None)
    if text:
        return text
    f = r.get('fields') or {}
    if r['kind'] == 'player':
        common = f.get('name.common')
        full = ' '.join(x for x in (f.get('name.first'), f.get('name.last')) if x)
        return common or full or None
    return f.get('leaguename') or f.get('name')


def _picture_slot(r: dict) -> str | None:
    return next((s for s in PICTURE_SLOTS.get(r['kind'], ()) if s in (r.get('pictures') or {})), None)


def _tree(con, bundle: share.Bundle, ids: dict | None) -> dict:
    """{nodes: {key: node}, roots: [keys]} as the screen draws it."""
    children = share.children(bundle)
    nodes = {}
    for r in bundle.records:
        key = bundle.key(r)
        name = _record_name(r)
        if name is None and (not r['created'] or bundle.origin == 'own') and r['id'] >= 0:
            try:
                name = _shown_name(con, r['kind'], r['id']) if not r['created'] else None
            except Exception:  # noqa: BLE001 - a name is only shown
                name = None
        node = {'key': key, 'kind': r['kind'], 'id': r['id'], 'name': name, 'created': r['created'],
                'picture': _picture_slot(r), 'children': children.get(key, [])}
        if ids is not None:
            plan = ids.get(key) or {}
            node.update({'new_id': plan.get('id'), 'reason': plan.get('reason'), 'error': plan.get('error'),
                         'default': plan.get('default', False), 'game_has': bool(plan.get('game_has'))})
        nodes[key] = node
    roots = share.roots(bundle, children)
    # the countries the game already has (only there because the package's players are of them) go last
    last = [k for k in roots if nodes[k].get('game_has') and not nodes[k]['children']]
    return {'nodes': nodes, 'roots': [k for k in roots if k not in last] + last}


# ---------------------------------------------------------------- import

@app.post('/api/share/inspect')
async def inspect(request: Request):
    """The zip as the request body (application/zip): what it holds, as a tree, and the id each item gets."""
    _forget_old()
    os.makedirs(STAGING_DIR, exist_ok=True)
    token = uuid.uuid4().hex
    path = os.path.join(STAGING_DIR, f'{token}.zip')
    size = 0
    with open(path, 'wb') as out:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_UPLOAD:
                out.close()
                os.remove(path)
                raise ApiError(413, 'zip_too_big')
            out.write(chunk)
    try:
        with db() as con:  # the game's formations: a team of a package without its own gets the one of its starters
            formations = {f['id']: f['positions'] for f in queries.formations(con)}
        bundle = share.read(path, formations)
    except share.ShareError as e:
        os.remove(path)
        raise ApiError(400, e.code, e.detail) from None
    if not bundle.records:
        os.remove(path)
        raise ApiError(400, 'share_empty')
    with db() as con:
        ids = share.plan(bundle, GameDestination(con))
        tree = _tree(con, bundle, ids)
    with _lock:
        _staged[token] = {'kind': 'import', 'bundle': bundle, 'ids': ids, 'path': path, 'time': time.time()}
    meta = bundle.meta or {}
    # players whose face lacks its eyes or hair (the import may complete them: fill_missing)
    fillable = sum(1 for r in bundle.records if r.get('fill'))
    return {'token': token, 'origin': bundle.origin, 'warnings': bundle.warnings, 'fillable': fillable,
            'patch_name': meta.get('patch_name'), 'credits': meta.get('credits'), **tree}


class ApplyBody(BaseModel):
    token: str
    keys: list[str]
    # complete the faces of a package that lack their eyes or hair with the generic ones (share._fill)
    fill_missing: bool = True


# the last / current import, read by GET /api/share/apply/progress (an import runs as a job: a package of thousands
# of items takes minutes, and the screen shows where it is)
import_progress: dict = {'running': False}
import_cancel = threading.Event()


@app.post('/api/share/apply')
def apply_import(body: ApplyBody):
    """Starts writing the chosen items into the project (a job, one at a time with the build); GET
    /api/share/apply/progress says where it is, POST /api/share/apply/cancel stops it (nothing changes)."""
    global import_progress
    staged = _get(body.token, 'import')
    bundle, ids = staged['bundle'], staged['ids']
    known = {bundle.key(r) for r in bundle.records}
    chosen = {k for k in body.keys if k in known and ids.get(k, {}).get('id') is not None}
    if not chosen:
        raise ApiError(400, 'share_nothing_chosen')
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')
    cfg = settings.load()
    prog = {'running': True, 'steps': list(share.APPLY_STEPS), 'step': None, 'done': 0, 'total': 0, 'item': None,
            'started_at': time.time(), 'finished_at': None, 'error': None, 'stopping': False, 'cancelled': False,
            'result': None}

    def work(job_progress):
        steps = share.APPLY_STEPS

        def progress(step, done, total, item):
            prog.update(step=step, done=done, total=total, item=item)
            job_progress(step, (steps.index(step) + (done / total if total else 0)) / len(steps))
        try:
            with db() as con:
                files = game.files()
                generic = {'eyes': set(facefill.eyes_codes(files)), 'hair': set(facefill.hair_codes(files))}
                done = share.apply(project(), bundle, ids, chosen, GameDestination(con), progress, import_cancel,
                                   workers=workers.plan(cfg.build_cores, cfg.build_memory_percent),
                                   fill_missing=body.fill_missing, generic=generic)
        except share.ImportCancelled:
            prog['cancelled'] = True
            raise
        except Exception as e:
            prog['error'] = {'code': getattr(e, 'code', None) or 'share_import_failed', 'detail': str(e)}
            raise
        finally:
            prog.update(running=False, finished_at=time.time())
        with _lock:
            _staged.pop(body.token, None)
        if os.path.exists(staged['path']):
            os.remove(staged['path'])
        prog['result'] = {'imported': done, 'count': sum(len(v) for v in done.values())}
        log.info('import: %s item(s) in %.1f s', prog['result']['count'], prog['finished_at'] - prog['started_at'])
        return prog['result']

    import_cancel.clear()
    try:
        job = jobs.start('import', work)
    except RuntimeError:
        raise ApiError(409, 'busy') from None
    import_progress = prog
    return job


@app.post('/api/share/apply/cancel')
def cancel_import():
    """Asks the running import to stop: it stops before the next item and nothing it wrote stays (one transaction)."""
    if not import_progress.get('running'):
        return {'stopping': False}
    import_cancel.set()
    import_progress['stopping'] = True
    return {'stopping': True}


@app.get('/api/share/apply/progress')
def get_import_progress():
    """Where the current (or last) import is: step (share.APPLY_STEPS), done/total of that step, the item."""
    prog = dict(import_progress)
    if prog.get('started_at'):
        prog['elapsed'] = round((prog['finished_at'] or time.time()) - prog['started_at'], 1)
    return prog


@app.get('/api/share/{token}/picture')
def staged_picture(token: str, key: str):
    """The picture of one item of an inspected zip or of an export (its own picture, PNG)."""
    with _lock:
        staged = _staged.get(token)
    if not staged:
        raise ApiError(404, 'share_expired')
    bundle = staged['bundle']
    rec = bundle.by_key().get(key)
    slot = _picture_slot(rec) if rec else None
    if slot is None:
        raise ApiError(404, 'not_found')
    try:
        data = bundle.read_file(rec['pictures'][slot])
    except share.ShareError:
        raise ApiError(404, 'not_found') from None
    return Response(data, media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})


@app.delete('/api/share/{token}')
def forget(token: str):
    with _lock:
        staged = _staged.pop(token, None)
    if staged and staged.get('path') and os.path.exists(staged['path']):
        os.remove(staged['path'])
    return {'forgotten': bool(staged)}


# ---------------------------------------------------------------- export

class ExportBody(BaseModel):
    kind: str
    id: int


def _changed(p, kind: str, oid: int) -> bool:
    return p.is_created(kind, oid) or oid in p.edited(kind)


def _collect(con, writer: share.Writer, kind: str, oid: int, seen: set) -> None:
    """The entity (when the project created or changed it) and what it takes along, the same way down."""
    key = f'{kind}:{oid}'
    if key in seen:
        return
    seen.add(key)
    p = project()
    if _changed(p, kind, oid):
        links = {}
        if kind == 'team':
            links['leagues'] = [r[0] for r in con.execute(
                'SELECT DISTINCT league_id FROM v_league_teams WHERE team_id = ? ORDER BY league_id', (oid,))]
        if kind == 'player':
            links['teams'] = [{'team': r[0], 'jersey': r[1], 'slot': r[2]} for r in con.execute(
                'SELECT team_id, jersey, position FROM v_team_players WHERE player_id = ? ORDER BY team_id', (oid,))]
        writer.add(p, kind, oid, links)
    for child_kind, child in _takes(con, kind, oid):
        _collect(con, writer, child_kind, child, seen)


def _value(con, kind: str, oid: int, field: str):
    """A field of an entity as the app shows it: the project's, else the game's row."""
    saved = project().fields(kind, oid).get(field)
    if saved is not None:
        return saved
    view = {'team': 'v_teams', 'player': 'v_players'}[kind]
    row = con.execute(f"SELECT json_extract(raw, '$.{field}') FROM {view} WHERE id = ?", (oid,)).fetchone()
    return row[0] if row else None


def _takes(con, kind: str, oid: int) -> list[tuple[str, int]]:
    """What an entity takes along in an export (the same links as the tree of share.children)."""
    p = project()
    out = []
    if kind == 'country':
        out += [('league', r[0]) for r in con.execute(
            f'SELECT l.id FROM v_leagues l WHERE {queries._in_country("l", "?")} ORDER BY l.id', (oid, oid))]  # noqa: SLF001
    elif kind == 'league':
        out += [('team', r[0]) for r in con.execute(
            'SELECT team_id FROM v_league_teams WHERE league_id = ? ORDER BY ord, team_id', (oid,))]
        board = p.adboard_link('league', oid)
        if board is not None:
            out.append(('adboard', board))
    elif kind == 'team':
        found = con.execute('SELECT stadium_id FROM v_team_stadiums WHERE team_id = ? LIMIT 1', (oid,)).fetchone()
        if found and found[0] is not None:
            out.append(('stadium', found[0]))
        ball = _value(con, 'team', oid, 'balltype')
        if ball:
            out.append(('ball', int(ball)))
        board = p.adboard_link('team', oid)
        if board is not None:
            out.append(('adboard', board))
        out += [('player', r[0]) for r in con.execute(
            'SELECT player_id FROM v_team_players WHERE team_id = ? ORDER BY ord, player_id', (oid,))]
    elif kind == 'player':
        for field, gear in (('shoetypecode', 'boot'), ('gkglovetypecode', 'glove')):
            code = _value(con, 'player', oid, field)
            if code:
                out.append((gear, int(code)))
    return out


@app.post('/api/share/export')
def start_export(body: ExportBody):
    """The tree of what an export of this entity takes (what the project created or changed)."""
    if body.kind not in KINDS:
        raise ApiError(400, 'bad_request', 'kind')
    _forget_old()
    writer = share.Writer()
    with db() as con:
        _collect(con, writer, body.kind, body.id, set())
        if not writer.records:
            raise ApiError(409, 'share_nothing_to_export')
        bundle = share.Bundle(writer.records, 'own', files=writer.files)
        tree = _tree(con, bundle, None)
    token = uuid.uuid4().hex
    with _lock:
        _staged[token] = {'kind': 'export', 'bundle': bundle, 'writer': writer, 'time': time.time(),
                          'name': next((n['name'] for n in tree['nodes'].values() if n['name']), None),
                          'root': f'{body.kind}:{body.id}'}
    return {'token': token, **tree}


class ExportZipBody(BaseModel):
    keys: list[str]


def _file_name(name: str | None) -> str:
    base = re.sub(r'[^\w\- ]+', '', name or '', flags=re.UNICODE).strip().replace(' ', '-')[:60]
    return f'{base or "export"}.zip'


@app.post('/api/share/export/{token}/zip')
def export_zip(token: str, body: ExportZipBody):
    staged = _get(token, 'export')
    writer: share.Writer = staged['writer']
    known = {f"{r['kind']}:{r['id']}" for r in writer.records}
    keep = {k for k in body.keys if k in known}
    if not keep:
        raise ApiError(400, 'share_nothing_chosen')
    os.makedirs(STAGING_DIR, exist_ok=True)
    path = os.path.join(STAGING_DIR, f'{token}-out.zip')
    p = project()
    writer.write(path, {'name': 'fifa14-patch-studio', 'version': settings.APP_VERSION}, keep,
                 is_created=p.is_created)
    root = next((r for r in writer.records if f"{r['kind']}:{r['id']}" == staged['root']), None)
    name = _record_name(root) if root else None
    return FileResponse(path, media_type='application/zip', filename=_file_name(name or staged.get('name')),
                        background=_remove_after(path))


def _remove_after(path: str):
    from starlette.background import BackgroundTask

    return BackgroundTask(lambda: os.path.exists(path) and os.remove(path))

