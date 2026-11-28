"""A formation drawing the game's 33 generic formations do not have (one brought by a package from another patch).

A team stands in one of the game's 33 formations when its 11 positions are one of theirs (field `formation`); a
drawing with other positions (e.g. a 2-3-5 of an old-times patch) is kept whole on the team (field
`formation_shape`): {name, base, columns}. The builder writes one shared generic formation (team -1) per different
drawing and the teams point at it (teamformationteamstylelinks), so a drawing costs one of the 899 formations the game
takes, not one per team. `base`: the game's formation nearest to it (its columns fill what the drawing leaves out).
"""
import hashlib
import json
import math

STARTERS = 11
GOALKEEPER = 0
MAX_POSITION = 27  # starters' positions 0-27 (28 = bench, 29 = reserve)
NAME_BYTES = 24  # formations.formationname: 25 bytes with the terminator
# the columns of a formations row a drawing carries (no team, id, relative id or full name id: the builder's)
INT_COLUMNS = {
    **{f'position{i}': (0, MAX_POSITION) for i in range(STARTERS)},
    **{f'{side}role_{i}': (0, 3) for side in ('attacking', 'defensive') for i in range(STARTERS)},
    **{f'{side}direction_{i}': (0, 7) for side in ('attacking', 'defensive') for i in range(STARTERS)},
    'offensiverating': (0, 7),
    'issweeper': (0, 1),
}
FLOAT_COLUMNS = {*(f'offset{i}{axis}' for i in range(STARTERS) for axis in 'xy'), 'defenders', 'midfielders',
                 'attackers'}
COLUMNS = (*INT_COLUMNS, *sorted(FLOAT_COLUMNS))


class ShapeError(ValueError):
    pass


def positions_of(columns: dict) -> list[int]:
    return [columns[f'position{i}'] for i in range(STARTERS)]


def check(value) -> dict:
    """A drawing as it is kept on a team, checked; raises ShapeError."""
    if not isinstance(value, dict) or not isinstance(value.get('columns'), dict):
        raise ShapeError('bad_value')
    base = value.get('base')
    if isinstance(base, bool) or not isinstance(base, int) or not 1 <= base <= 33:
        raise ShapeError('bad_value')
    given = value['columns']
    columns = {}
    for column, (low, high) in INT_COLUMNS.items():
        v = given.get(column)
        if column.startswith('position') or v is not None:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not low <= v <= high:
                raise ShapeError('bad_value')
            columns[column] = int(v)
    for column in FLOAT_COLUMNS:
        v = given.get(column)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not -10 <= v <= 10:
            raise ShapeError('bad_value')
        columns[column] = round(float(v), 4)
    positions = positions_of(columns)
    if positions[0] != GOALKEEPER or GOALKEEPER in positions[1:] or len(set(positions)) != STARTERS:
        raise ShapeError('bad_value')
    name = value.get('name')
    name = name.strip() if isinstance(name, str) else ''
    return {'name': fit_name(name) or 'Custom', 'base': base, 'columns': columns}


def fit_name(name: str) -> str:
    """The name as the database takes it (NAME_BYTES of UTF-8, not cutting a character)."""
    data = name.encode('utf-8')[:NAME_BYTES]
    return data.decode('utf-8', 'ignore').strip()


def key(shape: dict) -> str:
    """The same drawing gives the same key (teams with it share one formation)."""
    text = json.dumps({'name': shape['name'], 'columns': shape['columns']}, sort_keys=True)
    return 'shape-' + hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]


def has_settings(columns: dict) -> bool:
    """Whether a formation row has a work rate other than the default (3: 0 medium, 1 low, 2 high) or a run arrow
    (tests FD1-FD3): what the
    game's 33 do not have (some teams' own rows and some patches' formations do)."""
    return any(columns.get(f'{side}role_{i}', 3) != 3 or columns.get(f'{side}direction_{i}', 0)
               for side in ('attacking', 'defensive') for i in range(STARTERS))


def game_match(positions, game: dict[int, list[int]]) -> int | None:
    """The game's formation with these 11 positions (in any order), or None."""
    wanted = sorted(positions)
    found = [fid for fid, p in game.items() if sorted(p) == wanted]
    return min(found) if found else None


def nearest(positions, game: dict[int, list[int]]) -> int | None:
    """The game's formation sharing most positions with these (ties: the lowest id)."""
    if not game:
        return None
    wanted = set(positions)
    return min(game, key=lambda fid: (-len(wanted & set(game[fid])), fid))
