"""The project's problems, shown before building (same rule as the Street Studio's validation).

issues() never raises: it returns problems with a stable `code` and `params` so the interface shows its own text.
Severity 'error' = the build would stop on it (builder.BuildError); 'warning' = the patch is built, but something
differs from what the screen shows. Entities left out of the patch (Hide) are not checked.
"""
import json
import sqlite3

from f14mod import fifa14
from f14mod.builder import STARTERS

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
    _teams(con, out, hidden, created, saved, states)
    _leagues(con, out, hidden, created, saved, states)
    _players(con, out, hidden, created, saved)
    _league_links(con, out)
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
        if tid not in roster_set:  # a created team without its own squad: the copied team's, or none
            if not sources.get(tid):
                out.append(_issue('roster_too_small', 'error', 'team', tid, 'players', count=0, min=STARTERS))
            continue
        rows = [r for r in rosters.get(tid, []) if not r[4] and ('player', r[0]) not in hidden]
        squad = rows[:fifa14.MAX_SQUAD]  # the rest stays out of the patch (builder.lineup)
        if len(rows) < STARTERS:
            out.append(_issue('roster_too_small', 'error', 'team', tid, 'players', count=len(rows), min=STARTERS))
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
        # a face from a pack lives in the project: without its head and face files the build stops
        if isinstance(face, dict) and face.get('source') == 'pack' and \
                not all(k in files.get(pid, ()) for k in fifa14.FACE_REQUIRED):
            out.append(_issue('face_missing', 'error', 'player', pid, 'face'))


def _league_links(con, out):
    """Every team-league link of the game has a 12-bit key (builder.write_members)."""
    changed = {r[0] for r in con.execute('SELECT league_id FROM p.league_members_set')}
    kept = sum(1 for (lid,) in con.execute('SELECT league_id FROM league_teams') if lid not in changed)
    added = con.execute('SELECT COUNT(*) FROM p.league_members WHERE COALESCE(hidden, 0) = 0').fetchone()[0]
    if kept + added > fifa14.MAX_LEAGUE_LINKS:
        out.append(_issue('too_many_league_links', 'error', count=kept + added, max=fifa14.MAX_LEAGUE_LINKS))


def _names(con, out, lang):
    """The shown name of each entity with a problem (the list links to it)."""
    sql = {'team': f'SELECT {queries._team_name("full")} FROM v_teams t WHERE t.id = :id',  # noqa: SLF001
           'league': f'SELECT {queries._league_name()} FROM v_leagues l WHERE l.id = :id',  # noqa: SLF001
           'player': f'SELECT {queries._player_name()} FROM v_players pl WHERE pl.id = :id'}  # noqa: SLF001
    cache = {}
    for i in out:
        if i['kind'] in sql:
            key = (i['kind'], i['id'])
            if key not in cache:
                row = con.execute(sql[i['kind']], {'lang': lang, 'id': i['id']}).fetchone()
                cache[key] = row[0] if row else None
            i['name'] = cache[key]
