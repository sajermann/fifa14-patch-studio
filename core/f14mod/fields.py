"""What the editor can change in each database row (player, team, league) and the limits the game accepts.

A field is a database column of the entity's row, with these exceptions:
  - `name.first`, `name.last`, `name.common`, `name.jersey`: the player's names (texts of the name table);
  - `teamcolorN`: the three columns teamcolorNr/g/b as one [r, g, b] value;
  - `birthdate`: an ISO date (the database keeps days since 1582-10-14);
  - the league's `extra_countries` (list of nation ids), its `hidden_in_countries` (countries of the league where it
    is left out of the patch: it stays in that country in the app) and the country's `flag_from`: no column, the
    builder uses them (one more `leagues` row per extra country, none for a hidden one; the flag files copied).
Values are kept as the screen shows them; `to_columns` turns them into database values.
The overall ratings are not here: the game computes them from the attributes (player) and the players (team).
"""
import datetime
from dataclasses import asdict, dataclass

from . import facefill, fifa14

NAME_FIELDS = {'name.first': 'firstnameid', 'name.last': 'lastnameid', 'name.common': 'commonnameid',
               'name.jersey': 'playerjerseynameid'}
NAME_KEYS = {'name.first': 'first', 'name.last': 'last', 'name.common': 'common', 'name.jersey': 'jersey_name'}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    group: str
    kind: str  # int | select | text | date | color | nation | nations | team | roster | position | code
    #          | traits | face
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


def _codes(columns, group):
    """Appearance/animation codes of the game: the options the screen offers come from the game (the values its
    players use, or its files); min/max = what the database field holds."""
    return [FieldSpec(c, group, 'code', lo, hi) for c, lo, hi in columns]


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
    # the traits the player has (keys of fifa14.TRAITS); written as bits of trait1/trait2, other bits kept
    FieldSpec('traits', 'traits', 'traits'),
    # the ratings in the game's own groups (its attribute screens): pace, shooting, passing, dribbling, defending,
    # physical and goalkeeping
    *_ratings(['acceleration', 'sprintspeed'], 'pace'),
    *_ratings(['finishing', 'shotpower', 'longshots', 'volleys', 'penalties', 'positioning'], 'shooting'),
    *_ratings(['vision', 'crossing', 'freekickaccuracy', 'shortpassing', 'longpassing', 'curve'], 'passing'),
    *_ratings(['agility', 'balance', 'reactions', 'ballcontrol', 'dribbling'], 'dribbling'),
    *_ratings(['interceptions', 'headingaccuracy', 'marking', 'standingtackle', 'slidingtackle'], 'defending'),
    *_ratings(['jumping', 'stamina', 'strength', 'aggression'], 'physical'),
    *_ratings(['gkdiving', 'gkhandling', 'gkkicking', 'gkpositioning', 'gkreflexes'], 'goalkeeping'),
    # generic head (headclasscode 1): the game builds it from these codes
    # (the ranges are the bits of the game's database: hair files above 127, e.g. hair_213, cannot be stored)
    *_codes([('headtypecode', 0, 8191), ('hairtypecode', 0, 127), ('haircolorcode', 0, 15),
             ('facialhairtypecode', 0, 31), ('facialhaircolorcode', 0, 15), ('eyebrowcode', 0, 3),
             ('sideburnscode', 0, 3), ('eyecolorcode', 1, 8), ('skintypecode', 0, 15)], 'look'),
    *_codes([('skintonecode', 1, 16), ('bodytypecode', 1, 32), ('jerseysleevelengthcode', 0, 7),
             ('socklengthcode', 0, 3), ('jerseystylecode', 0, 1), ('jerseyfit', 0, 3), ('shortstyle', 0, 1),
             ('hasseasonaljersey', 0, 7)], 'body'),
    *_codes([(f'{kind}{n}', 0, hi) for n in (1, 2, 3, 4)
             for kind, hi in (('accessorycode', 31), ('accessorycolourcode', 15))], 'accessories'),
    *_codes([('runningcode1', 0, 127), ('runningcode2', 0, 127), ('finishingcode1', 0, 127),
             ('finishingcode2', 0, 127), ('animfreekickstartposcode', 0, 15), ('animpenaltieskickstylecode', 0, 3),
             ('animpenaltiesmotionstylecode', 0, 7), ('animpenaltiesstartposcode', 0, 15), ('gkkickstyle', 0, 3),
             ('gksavetype', 0, 1), ('faceposercode', 0, 3)], 'animations'),
    FieldSpec('contractvaliduntil', 'career', 'int', 2000, 2047),
    FieldSpec('playerjointeamdate', 'career', 'date'),
    FieldSpec('isretiring', 'career', 'select', options=(0, 1)),
    # where the head comes from: {'source': 'generic'} (the look codes), {'source': 'player', 'player': id} (the
    # real face of a player of the game) or {'source': 'pack', ...} (a face of a pack, its files kept in the
    # project); none = the player's own (his real face when the game has one); no column (see builder)
    FieldSpec('face', 'face', 'face'),
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
    # one of the game's 33 formations (formations rows of team -1, relativeformationid): the team's own formation row
    # takes its positions (test TN1); shown on the Squad tab, not with the other fields
    FieldSpec('formation', 'lineup', 'select', options=tuple(range(1, 34))),
]

LEAGUE = [
    FieldSpec('leaguename', 'info', 'text', max_length=60),
    FieldSpec('level', 'info', 'int', 1, 8),
    FieldSpec('countryid', 'info', 'nation', 0, 255, optional=True),
    FieldSpec('extra_countries', 'info', 'nations', 1, 255),  # the league shows in these countries too
    # countries of the league (own or extra) where it is left out of the patch; edited on the country's screen only
    FieldSpec('hidden_in_countries', 'countries', 'nations', 1, 255),
]
NO_COLUMN = {'extra_countries', 'hidden_in_countries', 'flag_from', 'formation', 'traits', 'face'}  # fields the builder uses itself (not written as columns)

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
        elif spec.kind == 'traits':
            out[spec.name] = traits_of(raw)
        elif spec.kind == 'face':
            out[spec.name] = None  # the player's own head
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
            continue  # (an empty trait list is [], not None: taking every trait away is kept)
        out[name] = value
    if kind == 'league' and 'hidden_in_countries' in out:
        countries = league_countries({**original, **out})
        kept = [c for c in out['hidden_in_countries'] if c in countries]  # a country the league left is dropped
        if kept:
            out['hidden_in_countries'] = kept
        else:
            del out['hidden_in_countries']
    return out


def league_countries(values: dict) -> list[int]:
    """Every country a league shows in (its own first, then the extra ones), from its screen values."""
    return [c for c in dict.fromkeys([values.get('countryid') or 0, *(values.get('extra_countries') or [])]) if c]


def _int(spec: FieldSpec, value) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
        raise FieldError('bad_value', spec.name)
    return int(value)


def _check(spec: FieldSpec, value):
    if value is None or value == '' or (spec.kind == 'face' and value == {}):
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
    if spec.kind == 'traits':
        if not isinstance(value, (list, tuple)) or any(v not in fifa14.TRAITS for v in value):
            raise FieldError('bad_value', spec.name)
        return sorted(set(value), key=list(fifa14.TRAITS).index)
    if spec.kind == 'face':
        return check_face(value)
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


# ---- player traits and face --------------------------------------------------------------------------------------

def traits_of(raw: dict) -> list[str]:
    """The trait keys a database row has (its trait1/trait2 bits)."""
    return [key for key, (column, bit) in fifa14.TRAITS.items() if int(raw.get(column) or 0) >> bit & 1]


def trait_columns(raw: dict, traits: list[str]) -> dict:
    """{trait1, trait2} with the known bits set from `traits` and the unknown bits of `raw` kept."""
    out = {}
    for column in ('trait1', 'trait2'):
        value = int(raw.get(column) or 0)
        for key, (c, bit) in fifa14.TRAITS.items():
            if c == column:
                value = value | (1 << bit) if key in traits else value & ~(1 << bit)
        out[column] = value
    return out


FACE_SOURCES = {'generic': (), 'player': ('player',), 'pack': ('pack', 'id')}
FACE_TEXTS = ('pack_name', 'part', 'name', 'credits', 'credits_url')


def check_face(value) -> dict:
    """A face choice of the screen, checked (the backend checks that the player or the pack face exists)."""
    if not isinstance(value, dict) or value.get('source') not in FACE_SOURCES:
        raise FieldError('bad_value', 'face')
    out = {'source': value['source']}
    for key in FACE_SOURCES[value['source']]:
        v = value.get(key)
        if key == 'pack':
            if not isinstance(v, str) or not v.strip():
                raise FieldError('bad_value', 'face')
        elif isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= fifa14.MAX_PLAYER_ID:
            raise FieldError('bad_value', 'face')
        out[key] = v
    if out['source'] == 'pack':
        out.update({k: str(value[k])[:200] for k in FACE_TEXTS if isinstance(value.get(k), str) and value[k]})
        if value.get('fill') is not None:  # the game's generic eyes / hair for the parts the pack lacks
            try:
                fill = facefill.check_fill(value['fill'])
            except facefill.FillError:
                raise FieldError('bad_value', 'face') from None
            if fill:
                out['fill'] = fill
    return out
