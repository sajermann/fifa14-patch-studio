"""Formations: the game's 33 (read only: copy one to change it) and the user's (create, copy, save, hide, delete),
each written as a generic formation the teams with it point at (f14mod.formation, builder.add_project_formations).
Registered by main (imported before the interface's catch-all route)."""
import datetime
from typing import Optional

from pydantic import BaseModel

from f14mod import fifa14, formation

from . import queries
from .main import ApiError, app, db, game, lang, project


def _iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if t else None


def _ready():
    if game.state != 'ready':
        raise ApiError(409, 'game_not_ready')


def _teams(con, fid: int) -> list[dict]:
    """The teams whose saved formation is this one."""
    sql = f"SELECT t.id, {queries._team_name('full')} AS name, t.is_new FROM v_teams t WHERE t.id = :id"  # noqa: SLF001
    out = []
    for tid in project().formation_users(fid):
        row = con.execute(sql, {'id': tid, 'lang': lang()}).fetchone()
        if row:
            out.append({'id': row['id'], 'name': row['name'], 'is_new': bool(row['is_new'])})
    return out


def _detail(con, fid: int) -> dict:
    p = project()
    shape = p.formation(fid) if fid > fifa14.GAME_FORMATIONS else None
    if shape is not None:
        base = queries.formation_row(con, shape['base']) or {'columns': {}}
        columns = {**base['columns'], **shape['columns']}  # what the drawing leaves out is its base's
        created_at, updated_at = p.dates('formation', fid)
        out = {'id': fid, 'is_new': True, 'name': shape['name'], 'base': shape['base'],
               'hidden': fid in p.hidden('formation'), 'created_at': _iso(created_at), 'updated_at': _iso(updated_at)}
    else:
        row = queries.formation_row(con, fid)
        if row is None:
            raise ApiError(404, 'not_found')
        columns = row['columns']
        out = {'id': fid, 'is_new': False, 'name': row['name'], 'base': fid, 'hidden': False,
               'created_at': None, 'updated_at': None}
    columns = {c: columns[c] for c in formation.COLUMNS if c in columns}
    # the edit screen's form, as the other screens: the name and the drawing of a formation of the user
    return {**out, 'columns': columns, 'positions': formation.positions_of(columns), 'teams': _teams(con, fid),
            'fields': [], 'values': {'name': '', 'columns': None}, 'edited': False,
            'saved': {'name': out['name'], 'columns': columns} if out['is_new'] else {}}


@app.get('/api/formations')
def list_formations():
    """The user's formations, then the game's 33."""
    _ready()
    p = project()
    with db() as con:
        own = queries.project_formations(con)
        hidden = p.hidden('formation')
        for f in own:
            f['hidden'] = f['id'] in hidden
        game_items = [{**f, 'is_new': False, 'hidden': False,
                       'teams': len(p.formation_users(f['id']))} for f in queries.formations(con)]
    return {'items': own + sorted(game_items, key=lambda f: f['id']), 'max': fifa14.MAX_FORMATIONS}


@app.get('/api/formations/{fid}')
def formation_detail(fid: int):
    _ready()
    with db() as con:
        return _detail(con, fid)


class FormationBody(BaseModel):
    name: str = ''
    columns: Optional[dict] = None  # save: the drawing (f14mod.formation.COLUMNS)
    copy_of: Optional[int] = None  # create: a copy of this formation (the game's or the user's)


def _name(name: str) -> str:
    name = formation.fit_name((name or '').strip())
    if not name:
        raise ApiError(400, 'name_required', 'name')
    return name


def _check(name: str, base: int, columns: dict) -> dict:
    try:
        return formation.check({'name': name, 'base': base, 'columns': columns})
    except formation.ShapeError:
        raise ApiError(400, 'bad_formation', 'columns')


@app.post('/api/formations')
def create_formation(body: FormationBody):
    _ready()
    name = _name(body.name)
    if body.copy_of is None:
        raise ApiError(400, 'bad_request', 'copy_of')
    with db() as con:
        source = _detail(con, body.copy_of)
    p = project()
    fid = p.next_formation_id()
    if fid is None:
        raise ApiError(409, 'limit')
    p.create('formation', fid, fields=_check(name, source['base'], source['columns']))
    with db() as con:
        return _detail(con, fid)


def _own(fid: int) -> dict:
    shape = project().formation(fid)
    if shape is None:
        raise ApiError(404 if fid > fifa14.GAME_FORMATIONS else 400, 'not_found' if fid > fifa14.GAME_FORMATIONS
                       else 'game_formation')
    return shape


@app.put('/api/formations/{fid}')
def save_formation(fid: int, body: FormationBody):
    _ready()
    shape = _own(fid)
    columns = body.columns if body.columns is not None else shape['columns']
    project().save('formation', fid, fields=_check(_name(body.name), shape['base'], columns))
    with db() as con:
        return _detail(con, fid)


class HiddenBody(BaseModel):
    hidden: bool


@app.put('/api/formations/{fid}/hidden')
def hide_formation(fid: int, body: HiddenBody):
    _ready()
    _own(fid)
    project().set_hidden('formation', fid, body.hidden)
    with db() as con:
        return _detail(con, fid)


@app.delete('/api/formations/{fid}')
def delete_formation(fid: int):
    """A formation of the user leaves the project; its teams go back to the game's one it was based on."""
    _ready()
    shape = _own(fid)
    p = project()
    for tid in p.formation_users(fid):
        p.save('team', tid, p.names('team', tid), {**p.fields('team', tid), 'formation': shape['base']})
    p.delete('formation', fid)
    return {'deleted': fid, 'base': shape['base']}

