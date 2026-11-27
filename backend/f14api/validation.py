"""The project's problems, shown before building (same rule as the Street Studio's validation).

issues() never raises: it returns problems with a stable `code` and `params` so the interface shows its own text.
Severity 'error' = the build would stop on it (builder.BuildError); 'warning' = the patch is built, but something
differs from what the screen shows. Entities left out of the patch (Hide) are not checked.
"""
import json
import sqlite3

from f14mod import facefill, facepack, fields, fifa14
from f14mod.builder import STARTERS
from f14mod.project import ADBOARD_PICTURE, EQUIPMENT_NEEDS, STADIUM_SCENE_NAME

from . import queries

CAPTAIN = 'captainid'
ROLES = (CAPTAIN, *fifa14.TAKERS.values())


def _issue(code: str, severity: str, kind: str | None = None, oid: int | None = None, field: str | None = None,
           **params) -> dict:
    return {'code': code, 'severity': severity, 'kind': kind, 'id': oid,
            'entity': f'{kind}:{oid}' if kind else None, 'field': field, 'params': params, 'name': None}


def issues(con: sqlite3.Connection, lang: str) -> list[dict]:
    out: list[dict] = []
    hidden = {(k, i) for k, i in con.execute('SELECT kind, id FROM p.hidden')}
    created = {(k, i) for k, i in con.execute('SELECT kind, id FROM p.created')}
    saved: dict[tuple[str, int], dict] = {}
    for kind, oid, field, value in con.execute('SELECT kind, id, field, value FROM p.fields'):
        saved.setdefault((kind, oid), {})[field] = json.loads(value)
    states = league_states(con, hidden, created, saved)
    # players made from scratch still missing a required field are out of the patch: their teams count without them
    blank = {r[0] for r in con.execute('SELECT player_id FROM p.player_sources WHERE template IS NULL')}
    incomplete = {('player', pid) for k, pid in created if k == 'player' and pid in blank and
                  any(saved.get(('player', pid), {}).get(f) is None for f in fields.PLAYER_REQUIRED)}
    _teams(con, out, hidden | incomplete, created, saved, states)
    _leagues(con, out, hidden, created, saved, states)
    _players(con, out, hidden, created, saved)
    _stadiums(con, out, hidden, created, saved)
    _boards_and_equipment(con, out, hidden, created)
    _league_links(con, out)
    _formations(con, out, hidden, created, saved, states)
    _names(con, out, lang)
    return out


def league_states(con, hidden, created, saved) -> dict[int, str]:
    """Whether each league enters the game (builder.write_visibility): 'shown'; 'game' = one the game itself does not
    list (country 0 or a country never listed); 'hidden' = the user's Hide; 'countries' = hidden in every country it
    shows in (its countries hidden, or the league hidden in each of them); 'no_country' = a created league in none."""
    countries_hidden = {i for k, i in hidden if k == 'country'}
    out = {}
    for lid, country in con.execute('SELECT id, country_id FROM v_leagues'):
        values = saved.get(('league', lid), {})
        shown_in = {c for c in (country, *(values.get('extra_countries') or []))
                    if c and c not in fifa14.UNLISTED_NATIONS}
        if ('league', lid) in hidden:
            out[lid] = 'hidden'
        elif not shown_in:
            out[lid] = 'no_country' if ('league', lid) in created else 'game'
        elif shown_in <= countries_hidden | set(values.get('hidden_in_countries') or []):
            out[lid] = 'countries'
        else:
            out[lid] = 'shown'
    return out


def _teams(con, out, hidden, created, saved, states):
    rosters: dict[int, list] = {}
    for r in con.execute('SELECT team_id, player_id, ord, jersey, slot, COALESCE(hidden, 0) FROM p.team_rosters '
                         'ORDER BY team_id, ord, player_id'):
        rosters.setdefault(r[0], []).append(r[1:])
    roster_set = {r[0] for r in con.execute('SELECT team_id FROM p.team_rosters_set')}
    sources = {r[0]: bool(r[1]) for r in con.execute('SELECT team_id, copy FROM p.team_sources')}
    # made from scratch: out of the patch (a warning, not an error) until it has what every team of the game has
    blank = {r[0] for r in con.execute('SELECT team_id FROM p.team_sources WHERE template IS NULL AND copy = 0')}
    with_stadium = {r[0] for r in con.execute('SELECT team_id FROM p.team_stadiums')}
    for kind, tid in sorted(created):
        if kind != 'team' or tid not in blank or (kind, tid) in hidden:
            continue
        values = saved.get(('team', tid), {})
        missing = [f for f in fields.TEAM_REQUIRED if values.get(f) is None]
        if missing:
            out.append(_issue('team_missing_fields', 'warning', 'team', tid, 'fields', count=len(missing),
                              fields=missing))
        if tid not in with_stadium:
            out.append(_issue('team_without_stadium', 'warning', 'team', tid, 'stadium'))
    links: dict[int, list[tuple[int, bool]]] = {}
    for lid, tid, out_here in con.execute('SELECT league_id, team_id, hidden FROM v_league_teams'):
        links.setdefault(tid, []).append((lid, bool(out_here)))
    game_teams = {r[0] for r in con.execute('SELECT DISTINCT team_id FROM league_teams')}
    raws = {}
    for tid in roster_set | {i for k, i in created if k == 'team'}:
        row = con.execute('SELECT raw FROM teams WHERE id = ?', (tid,)).fetchone()
        raws[tid] = json.loads(row[0]) if row and row[0] and ('team', tid) not in created else {}
    for tid in sorted(roster_set | {i for k, i in created if k == 'team'}):
        if ('team', tid) in hidden:
            continue
        severity = 'warning' if tid in blank else 'error'  # a blank team without players is left out instead
        if tid not in roster_set:  # a created team without its own squad: the copied team's, or none
            if not sources.get(tid):
                out.append(_issue('roster_too_small', severity, 'team', tid, 'players', count=0, min=STARTERS))
            continue
        rows = [r for r in rosters.get(tid, []) if not r[4] and ('player', r[0]) not in hidden]
        squad = rows[:fifa14.MAX_SQUAD]  # the rest stays out of the patch (builder.lineup)
        if len(rows) < STARTERS:
            out.append(_issue('roster_too_small', severity, 'team', tid, 'players', count=len(rows), min=STARTERS))
        elif len(rows) > fifa14.MAX_SQUAD:
            out.append(_issue('roster_too_large', 'warning', 'team', tid, 'players', count=len(rows),
                              max=fifa14.MAX_SQUAD))
        in_squad = {r[0] for r in squad}
        # a role outside the squad: the build gives it to the last starter (builder.write_rosters)
        everyone = {r[0] for r in rosters.get(tid, [])}
        values = {**raws.get(tid, {}), **saved.get(('team', tid), {})}
        for role in ROLES:
            pid = values.get(role)
            if not pid or pid in in_squad:
                continue
            base = 'captain' if role == CAPTAIN else 'taker'
            out.append(_issue(f'{base}_hidden' if pid in everyone else f'{base}_not_in_roster', 'warning', 'team',
                              tid, role, player=pid))
        numbers: dict[int, int] = {}
        for pid, _ord, jersey, _slot, _hidden in squad:
            if jersey:
                numbers[jersey] = numbers.get(jersey, 0) + 1
        for number in sorted(n for n, c in numbers.items() if c > 1):
            out.append(_issue('duplicate_number', 'warning', 'team', tid, 'players', number=number))
    # a team in no league: a created one, or a game team taken out of every league it was in
    for tid in sorted({i for k, i in created if k == 'team'} | game_teams):
        if ('team', tid) not in hidden and not links.get(tid):
            out.append(_issue('team_without_league', 'warning', 'team', tid, 'leagues'))
    # every league of a team out of the game (test OC1: a team only in hidden leagues leaves the game). One league
    # still shown is enough; teams the game itself keeps out of every list are not the user's doing
    for tid, own in sorted(links.items()):
        if ('team', tid) in hidden or any(not out_here and states.get(lid) == 'shown' for lid, out_here in own):
            continue
        if any(out_here or states.get(lid) in ('hidden', 'countries', 'no_country') for lid, out_here in own):
            out.append(_issue('team_league_hidden', 'warning', 'team', tid, 'leagues'))


def _leagues(con, out, hidden, created, saved, states):
    teams = {r[0]: r[1] for r in con.execute(
        'SELECT league_id, COUNT(*) FROM v_league_teams WHERE hidden = 0 GROUP BY league_id')}
    for kind, lid in sorted(created):
        if kind != 'league' or (kind, lid) in hidden:
            continue
        values = saved.get(('league', lid), {})
        if not values.get('countryid') and not values.get('extra_countries'):
            out.append(_issue('league_without_country', 'warning', 'league', lid, 'countryid'))
        if not teams.get(lid):
            out.append(_issue('league_without_teams', 'warning', 'league', lid, 'teams'))
    # left out of every country it shows in: the league does not enter the game
    for lid, state in sorted(states.items()):
        if state == 'countries':
            out.append(_issue('league_hidden_in_countries', 'warning', 'league', lid, 'countryid'))


def _players(con, out, hidden, created, saved):
    in_team = {r[0] for r in con.execute('SELECT DISTINCT player_id FROM v_team_players WHERE hidden = 0')}
    # made from scratch: out of the patch (a warning) until the required fields are saved
    blank = {r[0] for r in con.execute('SELECT player_id FROM p.player_sources WHERE template IS NULL')}
    for kind, pid in sorted(created):
        if kind == 'player' and pid in blank and (kind, pid) not in hidden:
            missing = [f for f in fields.PLAYER_REQUIRED if saved.get(('player', pid), {}).get(f) is None]
            if missing:
                out.append(_issue('player_missing_fields', 'warning', 'player', pid, 'fields', count=len(missing),
                                  fields=missing))
    files = {}
    for pid, name in con.execute('SELECT player_id, name FROM p.player_files'):
        files.setdefault(pid, set()).add(name)
    for kind, pid in sorted(created):
        if kind == 'player' and (kind, pid) not in hidden and pid not in in_team:
            out.append(_issue('player_without_team', 'warning', 'player', pid, 'teams'))
    for (kind, pid), values in sorted(saved.items()):
        if kind != 'player' or (kind, pid) in hidden:
            continue
        face = values.get('face')
        bald = isinstance(face, dict) and face.get('source') == 'pack' and _hair_code(con, pid, values) == 0
        # a face from a pack lives in the project: without its head and face files the build stops
        if isinstance(face, dict) and face.get('source') == 'pack' and \
                not all(k in files.get(pid, ()) for k in fifa14.FACE_REQUIRED):
            out.append(_issue('face_missing', 'error', 'player', pid, 'face'))
        elif isinstance(face, dict) and face.get('source') == 'pack' and \
                (parts := [k for k in facepack.missing_parts(files.get(pid, ()), bald=bald)
                           if k not in facefill.covered(face.get('fill'))]):
            # a part the pack lacks goes out without it, unless the user filled it with the game's (facefill)
            out.append(_issue('face_incomplete', 'warning', 'player', pid, 'face', parts=parts))


def _hair_code(con, pid: int, values: dict):
    """The player's hair code: the saved one, else the game's (0 = no hair)."""
    if 'hairtypecode' in values:
        return values['hairtypecode']
    row = con.execute('SELECT raw FROM v_players WHERE id = ?', (pid,)).fetchone()
    try:
        return json.loads(row[0]).get('hairtypecode') if row and row[0] else None
    except (ValueError, AttributeError):
        return None


def _stadiums(con, out, hidden, created, saved):
    """A stadium made from scratch enters the patch only with its 3D (a stadium's folder) and every field the game
    needs; without menu pictures the game's menus show it with none."""
    sources = {r[0]: r[1] for r in con.execute('SELECT stadium_id, template FROM p.stadium_sources')}
    scenes = {r[0] for r in con.execute('SELECT stadium_id FROM p.stadium_scene WHERE name = ?', (STADIUM_SCENE_NAME,))}
    pictures = {r[0] for r in con.execute("SELECT id FROM p.pictures WHERE kind = 'stadium'")}
    menus = {r[0] for r in con.execute("SELECT DISTINCT stadium_id FROM p.stadium_scene WHERE name LIKE 'data/ui/%'")}
    for kind, sid in sorted(created):
        if kind != 'stadium' or (kind, sid) in hidden or sources.get(sid) is not None:
            continue
        if sid not in scenes:
            out.append(_issue('stadium_without_scene', 'warning', 'stadium', sid, 'scene'))
        values = saved.get(('stadium', sid), {})
        missing = [f for f in fields.STADIUM_REQUIRED if values.get(f) is None]
        if missing:
            out.append(_issue('stadium_missing_fields', 'warning', 'stadium', sid, 'fields', count=len(missing)))
        if sid not in pictures and sid not in menus:
            out.append(_issue('stadium_without_pictures', 'warning', 'stadium', sid, 'pictures'))


def _boards_and_equipment(con, out, hidden, created):
    """A created board without its picture, or a created boot/glove/ball without the files it needs, is left out of
    the patch (builder.write_adboards, Project.incomplete_equipment)."""
    pictures = {r[0] for r in con.execute(f"SELECT id FROM p.pictures WHERE kind = 'adboard' AND slot = ?",
                                          (ADBOARD_PICTURE,))}
    files: dict[tuple[str, int], set[str]] = {}
    for kind, oid, name in con.execute('SELECT kind, id, name FROM p.equipment_files'):
        files.setdefault((kind, oid), set()).add(name)
    for kind, oid in sorted(created):
        if (kind, oid) in hidden:
            continue
        if kind == 'adboard' and oid not in pictures:
            out.append(_issue('adboard_without_picture', 'warning', 'adboard', oid, 'picture'))
        elif kind in EQUIPMENT_NEEDS:
            missing = [n for n in EQUIPMENT_NEEDS[kind] if n not in files.get((kind, oid), set())]
            if missing:
                out.append(_issue('equipment_without_files', 'warning', kind, oid, 'files', count=len(missing)))


def _league_links(con, out):
    """Every team-league link of the game has a 12-bit key (builder.write_members)."""
    changed = {r[0] for r in con.execute('SELECT league_id FROM p.league_members_set')}
    kept = sum(1 for (lid,) in con.execute('SELECT league_id FROM league_teams') if lid not in changed)
    added = con.execute('SELECT COUNT(*) FROM p.league_members WHERE COALESCE(hidden, 0) = 0').fetchone()[0]
    if kept + added > fifa14.MAX_LEAGUE_LINKS:
        out.append(_issue('too_many_league_links', 'error', count=kept + added, max=fifa14.MAX_LEAGUE_LINKS))


def _formations(con, out, hidden, created, saved, states):
    """Formations 1-899 only (builder.compact_formations): the game's generic ones and the own row of each team of the
    game that can be picked - not hidden and not only in leagues the user hid (the leagues the game itself does not
    list count as shown; a team with no league counts) -, plus one for such a team without a row once the user picks
    its formation. Created teams point at a generic one instead (builder.write_formation_links): they do not count."""
    hidden_teams = {i for k, i in hidden if k == 'team'}
    out_leagues = {lid for lid, state in states.items() if state in ('hidden', 'countries', 'no_country')}
    leagues_of: dict[int, set] = {}
    for lid, tid, out_here in con.execute('SELECT league_id, team_id, hidden FROM v_league_teams'):
        if not out_here:
            leagues_of.setdefault(tid, set()).add(lid)
    own = {r[0] for r in con.execute('SELECT f.team_id FROM formations f JOIN teams t ON t.id = f.team_id '
                                     'WHERE f.generic = 0')}
    made = {i for k, i in created if k == 'team'}
    game_teams = {r[0] for r in con.execute('SELECT id FROM teams')} - made
    playing = {t for t in game_teams if not leagues_of.get(t) or leagues_of[t] - out_leagues} - hidden_teams
    count = con.execute('SELECT COUNT(*) FROM formations WHERE generic = 1').fetchone()[0]
    count += sum(1 for t in playing if t in own or saved.get(('team', t), {}).get('formation') is not None)
    if count > fifa14.MAX_FORMATIONS:
        out.append(_issue('too_many_formations', 'error', count=count, max=fifa14.MAX_FORMATIONS,
                          over=count - fifa14.MAX_FORMATIONS))


def _names(con, out, lang):
    """The shown name of each entity with a problem (the list links to it)."""
    sql = {'team': f'SELECT {queries._team_name("full")} FROM v_teams t WHERE t.id = :id',  # noqa: SLF001
           'league': f'SELECT {queries._league_name()} FROM v_leagues l WHERE l.id = :id',  # noqa: SLF001
           'player': f'SELECT {queries._player_name()} FROM v_players pl WHERE pl.id = :id',  # noqa: SLF001
           'stadium': f'SELECT {queries._stadium_name()} FROM v_stadiums s WHERE s.id = :id'}  # noqa: SLF001
    cache = {}
    for i in out:
        if i['kind'] in ('adboard', 'boot', 'glove', 'ball'):  # their name is a field of the project
            row = con.execute("SELECT json_extract(value, '$') FROM p.fields WHERE kind = ? AND id = ? AND "
                              "field = 'name'", (i['kind'], i['id'])).fetchone()
            i['name'] = row[0] if row else None
        if i['kind'] in sql:
            key = (i['kind'], i['id'])
            if key not in cache:
                row = con.execute(sql[i['kind']], {'lang': lang, 'id': i['id']}).fetchone()
                cache[key] = row[0] if row else None
            i['name'] = cache[key]
