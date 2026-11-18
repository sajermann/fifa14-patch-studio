"""What the editor can change in each database row (player, team, league) and the limits the game accepts.

A field is a database column of the entity's row, with these exceptions:
  - `name.first`, `name.last`, `name.common`, `name.jersey`: the player's names (texts of the name table);
  - `teamcolorN`: the three columns teamcolorNr/g/b as one [r, g, b] value;
  - `birthdate`: an ISO date (the database keeps days since 1582-10-14);
  - the league's `extra_countries` (list of nation ids) and the country's `flag_from`: no column, the builder uses
    them (one more `leagues` row per extra country; the flag files copied).
Values are kept as the screen shows them; `to_columns` turns them into database values.
The overall ratings are not here: the game computes them from the attributes (player) and the players (team).
"""
import datetime
from dataclasses import asdict, dataclass

from . import fifa14

NAME_FIELDS = {'name.first': 'firstnameid', 'name.last': 'lastnameid', 'name.common': 'commonnameid',
               'name.jersey': 'playerjerseynameid'}
NAME_KEYS = {'name.first': 'first', 'name.last': 'last', 'name.common': 'common', 'name.jersey': 'jersey_name'}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    group: str
    kind: str  # int | select | text | date | color | nation | nations | team | roster | position
    min: int | None = None
    max: int | None = None
    options: tuple = ()
    max_length: int | None = None
    optional: bool = False  # select/position/roster: the "none" value is allowed

    def as_dict(self) -> dict:
        out = asdict(self)
        out['options'] = list(self.options)
        return out


class FieldError(ValueError):
    def __init__(self, code: str, field: str):
        super().__init__(f'{code}: {field}')
        self.code, self.field = code, field


def _ratings(columns, group):
    return [FieldSpec(c, group, 'int', 1, 99) for c in columns]


PLAYER = [
    *(FieldSpec(n, 'names', 'text', max_length=30 if n == 'name.jersey' else 40) for n in NAME_FIELDS),
    FieldSpec('birthdate', 'info', 'date'),
    FieldSpec('height', 'info', 'int', 150, 220),
    FieldSpec('weight', 'info', 'int', 50, 130),
    FieldSpec('preferredfoot', 'info', 'select', options=(1, 2)),
    FieldSpec('nationality', 'info', 'nation', 1, 4095),
    FieldSpec('preferredposition1', 'positions', 'position', 0, 27),
    *(FieldSpec(f'preferredposition{i}', 'positions', 'position', -1, 27, optional=True) for i in (2, 3, 4)),
    FieldSpec('potential', 'style', 'int', 1, 99),
    FieldSpec('skillmoves', 'style', 'select', options=(0, 1, 2, 3, 4)),
    FieldSpec('weakfootabilitytypecode', 'style', 'select', options=(1, 2, 3, 4, 5)),
    FieldSpec('internationalrep', 'style', 'select', options=(1, 2, 3, 4, 5)),
    FieldSpec('attackingworkrate', 'style', 'select', options=(0, 1, 2)),
    FieldSpec('defensiveworkrate', 'style', 'select', options=(0, 1, 2)),
    *_ratings(['acceleration', 'sprintspeed', 'agility', 'balance', 'jumping', 'stamina', 'strength',
               'reactions'], 'physical'),
    *_ratings(['aggression', 'interceptions', 'positioning', 'vision'], 'mental'),
    *_ratings(['ballcontrol', 'crossing', 'curve', 'dribbling', 'finishing', 'freekickaccuracy', 'headingaccuracy',
               'longpassing', 'longshots', 'marking', 'penalties', 'shortpassing', 'shotpower', 'slidingtackle',
               'standingtackle', 'volleys'], 'skill'),
    *_ratings(['gkdiving', 'gkhandling', 'gkkicking', 'gkpositioning', 'gkreflexes'], 'goalkeeper'),
]

TEAM = [
    *(FieldSpec(f'teamcolor{i}', 'colors', 'color') for i in (1, 2, 3)),
    FieldSpec('domesticprestige', 'club', 'int', 0, 20),
    FieldSpec('internationalprestige', 'club', 'int', 0, 20),
    FieldSpec('rivalteam', 'club', 'team', 1, 262143),
    FieldSpec('transferbudget', 'club', 'int', 0, 500_000_000),
    *(FieldSpec(column, 'takers', 'roster', 1, 524287) for column in
      ('captainid', *fifa14.TAKERS.values())),
    *(FieldSpec(c, 'tactics', 'int', 1, 99) for c in ('busbuildupspeed', 'buspassing', 'busdribbling')),
    FieldSpec('buspositioning', 'tactics', 'select', options=(1, 2)),
    *(FieldSpec(c, 'tactics', 'int', 1, 99) for c in ('cccrossing', 'ccpassing', 'ccshooting')),
    FieldSpec('ccpositioning', 'tactics', 'select', options=(1, 2)),
    *(FieldSpec(c, 'tactics', 'int', 1, 99) for c in ('defmentality', 'defaggression', 'defteamwidth')),
    FieldSpec('defdefenderline', 'tactics', 'select', options=(1, 2)),
]

LEAGUE = [
    FieldSpec('leaguename', 'info', 'text', max_length=60),
    FieldSpec('level', 'info', 'int', 1, 8),
    FieldSpec('countryid', 'info', 'nation', 0, 255, optional=True),
    FieldSpec('extra_countries', 'info', 'nations', 1, 255),  # the league shows in these countries too
]
NO_COLUMN = {'extra_countries', 'flag_from'}  # fields the builder uses itself (not written as columns)

COUNTRY = [
    FieldSpec('flag_from', 'info', 'nation', 1, fifa14.MAX_NATION_ID, optional=True),  # whose flag is copied
]

SPECS = {'player': PLAYER, 'team': TEAM, 'league': LEAGUE, 'country': COUNTRY}
BY_NAME = {kind: {s.name: s for s in specs} for kind, specs in SPECS.items()}


def specs(kind: str) -> list[dict]:
    return [s.as_dict() for s in SPECS[kind]]


# ---- values ---------------------------------------------------------------------------------------------------------

def _to_iso(days) -> str | None:
    return fifa14.to_date(days)


def _to_days(iso: str) -> int:
    return (datetime.date.fromisoformat(iso) - fifa14.DATE_ZERO).days


def original_values(kind: str, raw: dict, names: dict | None = None) -> dict:
    """The screen values of a database row (`names`: the player's texts first/last/common/jersey_name)."""
    out = {}
    for spec in SPECS[kind]:
        if spec.name in NAME_FIELDS:
            out[spec.name] = (names or {}).get(NAME_KEYS[spec.name]) or ''
        elif spec.kind == 'color':
            out[spec.name] = [raw.get(f'{spec.name}{c}') for c in 'rgb']
        elif spec.kind == 'date':
            out[spec.name] = _to_iso(raw.get(spec.name))
        elif spec.kind == 'nations':
            out[spec.name] = []  # the game's leagues are in one country
        else:
            out[spec.name] = raw.get(spec.name)
    return out


def clean(kind: str, values: dict, original: dict) -> dict:
    """The values that differ from the original, checked; raises FieldError."""
    out = {}
    for name, value in values.items():
        spec = BY_NAME[kind].get(name)
        if spec is None:
            raise FieldError('unknown_field', name)
        value = _check(spec, value)
        if value is None or value == original.get(name):
            continue
        out[name] = value
    return out


def _int(spec: FieldSpec, value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise FieldError('bad_value', spec.name)
    return int(value)


def _check(spec: FieldSpec, value):
    if value is None or value == '':
        return None  # empty = the original
    if spec.kind == 'text':
        text = str(value).strip()
        if spec.max_length and len(text) > spec.max_length:
            raise FieldError('too_long', spec.name)
        return text or None
    if spec.kind == 'date':
        try:
            day = datetime.date.fromisoformat(str(value))
        except ValueError:
            raise FieldError('bad_value', spec.name) from None
        if not 1900 <= day.year <= 2100:
            raise FieldError('out_of_range', spec.name)
        return day.isoformat()
    if spec.kind == 'nations':
        if not isinstance(value, (list, tuple)):
            raise FieldError('bad_value', spec.name)
        ids = list(dict.fromkeys(_int(spec, v) for v in value))
        if any(not spec.min <= v <= spec.max for v in ids):
            raise FieldError('out_of_range', spec.name)
        return ids or None
    if spec.kind == 'color':
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise FieldError('bad_value', spec.name)
        rgb = [_int(spec, c) for c in value]
        if any(not 0 <= c <= 255 for c in rgb):
            raise FieldError('out_of_range', spec.name)
        return rgb
    number = _int(spec, value)
    if spec.options:
        if number not in spec.options:
            raise FieldError('out_of_range', spec.name)
        return number
    if not spec.min <= number <= spec.max:
        raise FieldError('out_of_range', spec.name)
    return number


def to_columns(kind: str, values: dict) -> dict:
    """{database column: database value} of saved values (the player's names are not here: see NAME_FIELDS)."""
    out = {}
    for name, value in values.items():
        spec = BY_NAME[kind].get(name)
        if spec is None or name in NAME_FIELDS or name in NO_COLUMN:
            continue
        if spec.kind == 'color':
            out.update({f'{name}{c}': v for c, v in zip('rgb', value)})
        elif spec.kind == 'date':
            out[name] = _to_days(value)
        else:
            out[name] = value
    return out
