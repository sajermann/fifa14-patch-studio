"""A FIFA patch package (`*.fifapkg.zip`, format `fifa-patch-package`, made by an extractor that knows nothing of this
app) read as the records of f14mod.share: every item comes in as a created entity (origin 'package'), its values
taken from the source database rows the package carries, its pictures and game files kept in the project.

What is converted:
  - country: its names (full, abbr3) and flag;
  - league: names, database name, level, country, logo, teams, the first board picture;
  - team: names, every editable column of its row (fields.TEAM), crest, kits (the jersey and shorts pictures with
    the colors, placements and collar of their name and numbers; the fonts stay the game's), squad (number and
    position), formation, stadium, ball, the first board picture and the leagues it is in;
  - player: names, every editable column of his row (fields.PLAYER), photo, his own face files and the teams he is in;
  - stadium: names, columns, menu pictures and scene files;
  - board picked on its own: its picture;
  - boot, glove, ball: name, pack files (and the ball's picture).
The source's values are the same game's (FIFA 14 PC), so nothing is scaled; a value out of the editor's range is
left out (the entity keeps the model's). A reference to something the package does not have is dropped (its ids
belong to another database), except a stadium, boot, glove or ball the clean game has under that id (f14mod.share
resolver).
"""
import json
import re
import zipfile

from . import facefill, fields as fieldspecs
from . import fifa14
from .share import Bundle, ShareError

FORMAT = 'fifa-patch-package'
FORMAT_VERSION = 1
MANIFEST = 'package.json'
MAX_MANIFEST = 512 * 1024 * 1024

KIT_TYPES = (0, 1, 2, 3, 4, 5, 7, 8)
PLAYER_NAME_KEYS = {'first': 'first', 'last': 'last', 'common': 'common', 'jersey': 'jersey_name'}
EQUIPMENT_LISTS = {'boots': 'boot', 'gloves': 'glove', 'balls': 'ball'}
EQUIPMENT_FILE_NAMES = {
    'boot': (('mesh', re.compile(r'/shoe_\d+\.rx3$')), ('texture', re.compile(r'/shoe_\d+_0_textures\.rx3$')),
             ('texture', re.compile(r'/shoe_\d+_\d+_textures\.rx3$'))),
    'glove': (('texture', re.compile(r'/gkglove_\d+_textures\.rx3$')),),
    'ball': (('mesh', re.compile(r'/ball_\d+\.rx3$')), ('texture', re.compile(r'/ball_\d+_textures\.rx3$'))),
}
GAME_PREFIX = 'game/'


def is_package(z: zipfile.ZipFile) -> bool:
    return MANIFEST in z.namelist()


def read_manifest(z: zipfile.ZipFile) -> dict:
    if z.getinfo(MANIFEST).file_size > MAX_MANIFEST:
        raise ShareError('invalid_package', 'manifest too big')
    try:
        manifest = json.loads(z.read(MANIFEST))
    except (ValueError, UnicodeDecodeError) as e:
        raise ShareError('invalid_package', str(e)) from None
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
        raise ShareError('invalid_package', 'format')
    version = manifest.get('format_version')
    if not isinstance(version, int) or version < 1:
        raise ShareError('invalid_package', 'format_version')
    if version > FORMAT_VERSION:
        raise ShareError('package_too_new', str(version))
    if (manifest.get('source') or {}).get('game') not in (None, 'fifa14'):
        raise ShareError('package_other_game', str(manifest['source'].get('game')))
    return manifest


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _list(manifest: dict, key: str) -> list[dict]:
    value = manifest.get(key)
    return [i for i in value if isinstance(i, dict) and _int(i.get('source_id'))] if isinstance(value, list) else []


def _first_row(item: dict, table: str) -> dict:
    rows = (item.get('raw') or {}).get(table) or []
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def _values(kind: str, row: dict, names: dict | None = None) -> dict:
    """The editor's values of a source row, each one checked alone (an out-of-range one is left out)."""
    out = {}
    for name, value in fieldspecs.original_values(kind, row, names).items():
        if value is None or value == '' or value == []:
            continue
        try:
            out.update(fieldspecs.clean(kind, {name: value}, {}))
        except fieldspecs.FieldError:
            pass
    return out


def _names(names: dict, keys) -> dict:
    """{key: {'*': text}}: the package has one language (manifest source.language), kept for every language."""
    return {key: {'*': text.strip()} for key in keys
            if isinstance((text := (names or {}).get(key)), str) and text.strip()}


def _formation_of(roster: list[dict], formations: dict[int, list[int]]) -> int | None:
    """The game's formation whose 11 positions are the starters' (a team with no formation of its own in its
    database: many patches leave them out, and the lineup still says where each starter plays), or None."""
    starters = sorted(r['position'] for r in roster if _int(r.get('position')) and 0 <= r['position'] <= 27)
    if len(starters) != 11:
        return None
    found = [fid for fid, positions in formations.items() if sorted(positions) == starters]
    return min(found) if found else None


class _Converter:
    def __init__(self, z: zipfile.ZipFile, manifest: dict, formations: dict[int, list[int]] | None = None):
        self.z, self.m = z, manifest
        self.formations = formations or {}
        self.names = set(z.namelist())
        self.records: list[dict] = []
        self.warnings: list[str] = []
        self._board = 0
        self.ids = {kind: {i['source_id'] for i in _list(manifest, key)} for kind, key in (
            ('team', 'teams'), ('player', 'players'), ('league', 'leagues'), ('country', 'nations'),
            ('stadium', 'stadiums'))}
        self.ids.update({kind: {i['source_id'] for i in _list(manifest, key)} for key, kind in EQUIPMENT_LISTS.items()})

    def file(self, name) -> str | None:
        """A file of the package (its name), or None when it is missing."""
        if not isinstance(name, str) or name not in self.names:
            return None
        return name  # read when it is written into the project (Bundle.read_file)

    def image(self, picture) -> str | None:
        return self.file(picture.get('image')) if isinstance(picture, dict) else None

    def record(self, kind: str, oid: int, names=None, values=None, pictures=None, tables=None, links=None,
               label=None) -> dict:
        rec = {'kind': kind, 'id': oid, 'created': True, 'names': names or {}, 'fields': values or {},
               'hidden': False, 'dates': {'created_at': None, 'updated_at': None},
               'pictures': {k: v for k, v in (pictures or {}).items() if v}, 'tables': tables or {},
               'links': links or {}}
        if label:
            rec['label'] = label
        self.records.append(rec)
        return rec

    def board(self, picture: dict, name: str) -> int | None:
        """A board picture of a team or league as a board of its own (a negative id: plan() gives it a new one)."""
        img = self.image(picture)
        if img is None:
            return None
        self._board -= 1
        self.record('adboard', self._board, values={'name': name[:60]}, pictures={'board': img})
        return self._board

    # ---- kinds
    def country(self, n: dict) -> None:
        names = _names(n.get('names') or {}, fifa14.COUNTRY_NAME_STRINGS)
        if 'full' not in names and isinstance(n.get('name'), str):
            names['full'] = {'*': n['name']}
        self.record('country', n['source_id'], names, pictures={'flag': self.image(n.get('flag'))})

    def league(self, lg: dict) -> None:
        names = lg.get('names') or {}
        values = _values('league', _first_row(lg, 'leagues'))
        values.pop('countryid', None)
        if isinstance(names.get('database'), str) and names['database'].strip():
            values['leaguename'] = names['database'].strip()[:60]
        if _int(lg.get('level')) and 1 <= lg['level'] <= 8:
            values['level'] = lg['level']
        if _int(lg.get('country_nation_id')):
            values['countryid'] = lg['country_nation_id']
        tables = {'league_members': [{'team_id': t, 'ord': i, 'hidden': 0}
                                     for i, t in enumerate(x for x in lg.get('team_ids') or [] if _int(x))]}
        boards = [b for b in lg.get('adboards') or [] if isinstance(b, dict)]
        board = self.board(boards[0], (names.get('full') or str(lg['source_id']))) if boards else None
        if board is not None:
            tables['league_adboards'] = [{'adboard_id': board}]
        images = lg.get('images') or {}
        self.record('league', lg['source_id'], _names(names, fifa14.LEAGUE_NAME_STRINGS), values,
                    {'logo': self.image(images.get('logo'))}, tables)

    def team(self, t: dict) -> None:
        tid = t['source_id']
        values = _values('team', _first_row(t, 'teams'))
        formation = (t.get('formation') or {}).get('base')
        if _int(formation) and formation in fieldspecs.BY_NAME['team']['formation'].options:
            values['formation'] = formation
        if values.get('rivalteam') not in self.ids['team']:  # a rival outside the package: another team of it
            others = sorted(self.ids['team'] - {tid})
            values['rivalteam'] = others[0] if others else tid
        roster = [r for r in t.get('roster') or [] if isinstance(r, dict) and _int(r.get('player_id'))]
        if 'formation' not in values and (found := _formation_of(roster, self.formations)) is not None:
            values['formation'] = found
        tables = {
            'team_sources': [{'template': None, 'copy': 0}],
            'team_rosters_set': [{}],
            'team_rosters': [{'player_id': r['player_id'], 'ord': i,
                              'jersey': r.get('jersey_number') if _int(r.get('jersey_number')) else None,
                              'slot': r['position'] if _int(r.get('position')) and 0 <= r['position'] <= 29 else 29,
                              'hidden': 0} for i, r in enumerate(roster)],
        }
        stadiums = [s for s in t.get('stadium_ids') or [] if _int(s)]
        if stadiums:
            tables['team_stadiums'] = [{'stadium_id': stadiums[0]}]
        boards = [b for b in t.get('adboards') or [] if isinstance(b, dict)]
        name = (t.get('names') or {}).get('full') or str(tid)
        board = self.board(boards[0], name) if boards else None
        if board is not None:
            tables['team_adboards'] = [{'adboard_id': board}]
        crest = t.get('crest') or {}
        pictures = {'crest': self.file(crest.get('image_no_background')) if crest.get('preferred') == 'no_background'
                    else None}
        pictures['crest'] = pictures['crest'] or self.image(crest)
        kits = []
        for k in t.get('kits') or []:
            if not isinstance(k, dict) or k.get('type') not in KIT_TYPES:
                continue
            jersey, shorts = self.file(k.get('jersey')), self.file(k.get('shorts'))
            if not jersey:
                continue
            pictures[f"kit{k['type']}_jersey"] = jersey
            if shorts:
                pictures[f"kit{k['type']}_shorts"] = shorts
            config = {'source': 'upload', 'print': _kit_print(k)}
            if _int(k.get('collar')) and 0 <= k['collar'] <= 15:
                config['collar'] = k['collar']
            kits.append({'kind': k['type'], 'config': json.dumps(config, ensure_ascii=False)})
        if kits:
            tables['team_kits'] = kits
        links = {'leagues': [x for x in t.get('league_ids') or [] if _int(x)]}
        self.record('team', tid, _names(t.get('names') or {}, fifa14.TEAM_NAME_STRINGS), values, pictures, tables,
                    links)

    def player(self, pl: dict) -> None:
        pid = pl['source_id']
        names = {PLAYER_NAME_KEYS[k]: v for k, v in (pl.get('names') or {}).items() if k in PLAYER_NAME_KEYS}
        values = _values('player', _first_row(pl, 'players'), names)
        if _int(pl.get('nationality_id')):
            values['nationality'] = pl['nationality_id']
        tables = {'player_sources': [{'template': None}]}
        face = {}
        for path, part in ((pl.get('face') or {}).get('files') or {}).items():
            game_path = path.lower()
            zip_name = part.get('file') if isinstance(part, dict) else None
            for kind, pattern in fifa14.PLAYER_FACE_FILES.items():
                if game_path == pattern.format(pid) and self.file(zip_name):
                    face[kind] = zip_name
        fill = None
        if all(k in face for k in fifa14.FACE_REQUIRED):
            tables['player_files'] = [{'name': k, 'data': v} for k, v in face.items()]
            values['face'] = {'source': 'pack', 'pack': 'package', 'id': pid}
            fill = self.fill(face, _first_row(pl, 'players'))
        teams = [{'team': x['team_id'], 'jersey': x.get('jersey_number') if _int(x.get('jersey_number')) else None,
                  'slot': x['position'] if _int(x.get('position')) and 0 <= x['position'] <= 29 else 29}
                 for x in pl.get('teams') or [] if isinstance(x, dict) and _int(x.get('team_id'))]
        rec = self.record('player', pid, values=values, pictures={'photo': self.image(pl.get('photo'))},
                          tables=tables, links={'teams': teams})
        if fill:
            rec['fill'] = fill

    def fill(self, face: dict, row: dict) -> dict | None:
        """What a real face of the package lacks and the source game shows in its place (the generic eyes / hair of
        the player's codes): {'eyes': {code, files?}, 'hair': {code, files?, hair_color}, 'hairlod': {code, files?}},
        files = the generic files the package brings (generic_parts); share.apply puts them in when the user wants
        (else nothing changes). 'hairlod': a face with its own hair but not the one seen from afar. Hair code 0 is no
        hair (the game has no generic of it): nothing to fill."""
        generic = self.m.get('generic_parts') if isinstance(self.m.get('generic_parts'), dict) else {}
        out = {}
        eye = row.get('eyecolorcode')
        if 'eyes' not in face and _int(eye) and eye > 0:
            given = (generic.get('eyes') or {}).get(str(eye)) or {}
            files = {'eyes': self.file(given.get('file'))} if isinstance(given, dict) else {}
            out['eyes'] = {'code': eye, **({'files': files} if all(files.values()) and files else {})}
        hair = row.get('hairtypecode')
        if not ('hair' in face and 'hair_textures' in face) and _int(hair) and hair > 0:
            given = ((generic.get('hair') or {}).get(str(hair)) or {}).get('files') or {}
            files = {k: self.file(given.get(k)) for k in facefill.HAIR_KINDS if isinstance(given, dict) and given.get(k)}
            files = {k: v for k, v in files.items() if v}
            whole = 'hair' in files and 'hair_textures' in files
            out['hair'] = {'code': hair, 'hair_color': row.get('haircolorcode'), **({'files': files} if whole else {})}
        elif 'hairlod' not in face and _int(hair) and hair > 0:
            given = (generic.get('hairlod') or {}).get(str(hair))
            name = given.get('file') if isinstance(given, dict) else None
            if not name:  # the whole generic hair of the same code, taken for another player
                whole = ((generic.get('hair') or {}).get(str(hair)) or {}).get('files')
                name = whole.get('hairlod') if isinstance(whole, dict) else None
            lod = self.file(name) if name else None
            out['hairlod'] = {'code': hair, **({'files': {'hairlod': lod}} if lod else {})}
        return out or None

    def stadium(self, s: dict) -> None:
        sid = s['source_id']
        names = s.get('names') or {}
        values = _values('stadium', _first_row(s, 'stadiums'))
        values.pop('hometeamid', None)
        if isinstance(names.get('database'), str) and names['database'].strip():
            values['name'] = names['database'].strip()[:60]
        pictures = {f"menu_{p['variant']}": self.image(p) for p in s.get('pictures') or []
                    if isinstance(p, dict) and _int(p.get('variant'))}
        scene = []
        mark = re.compile(rf'((?:specific)?stadium_|crowd_){sid}(?=[._])')
        for game_path, zip_name in (s.get('files') or {}).items():
            if self.file(zip_name):
                scene.append({'name': mark.sub(r'\g<1>#', game_path.lower()), 'data': zip_name})
        tables = {'stadium_sources': [{'template': None, 'folder_stadium': None}]}
        if scene:
            tables['stadium_scene'] = scene
        self.record('stadium', sid, _names(names, fifa14.STADIUM_NAME_STRINGS), values, pictures, tables)

    def adboard(self, a: dict) -> None:
        img = self.image(a)
        if img is None:
            return
        self._board -= 1
        self.record('adboard', self._board, values={'name': str(a.get('name') or 'board')[:60]},
                    pictures={'board': img})

    def equipment(self, kind: str, e: dict) -> None:
        files = {}
        for game_path, zip_name in (e.get('files') or {}).items():
            for name, pattern in EQUIPMENT_FILE_NAMES[kind]:
                if name not in files and pattern.search(game_path.lower()) and self.file(zip_name):
                    files[name] = zip_name
        values = {'name': e['name'].strip()[:60]} if isinstance(e.get('name'), str) and e['name'].strip() else {}
        credits = (self.m.get('credits') or {}).get('text')
        if isinstance(credits, str) and credits.strip():
            values['credits'] = credits.strip()[:200]
        self.record(kind, e['source_id'], values=values, pictures={'thumbnail': self.image(e.get('picture'))},
                    tables={'equipment_files': [{'name': k, 'data': v} for k, v in files.items()]})

    def convert(self) -> list[dict]:
        for n in _list(self.m, 'nations'):
            self.country(n)
        for lg in _list(self.m, 'leagues'):
            self.league(lg)
        for s in _list(self.m, 'stadiums'):
            self.stadium(s)
        for t in _list(self.m, 'teams'):
            self.team(t)
        for p in _list(self.m, 'players'):
            self.player(p)
        for a in self.m.get('adboards') or []:
            if isinstance(a, dict):
                self.adboard(a)
        for key, kind in EQUIPMENT_LISTS.items():
            for e in _list(self.m, key):
                self.equipment(kind, e)
        return self.records


def _kit_print(k: dict) -> dict:
    """The name and numbers of a package kit as config['print'] (f14mod.teamkits.PRINT); the fonts are left to the
    game's (the package's font ids are another database's)."""
    out = {}
    color = k.get('name_color')
    if isinstance(color, list) and len(color) == 3 and all(_int(c) and 0 <= c <= 255 for c in color):
        out['name_color'] = color
    if k.get('name_layout') in (0, 1):
        out['name_layout'] = k['name_layout']
    for key, source in (('show_name', 'back_name_placement'), ('front_number', 'front_number_placement'),
                        ('shorts_number', 'shorts_number_placement')):
        if _int(k.get(source)):
            out[key] = bool(k[source])
    for key, source in (('number_color', 'number_font'), ('shorts_number_color', 'shorts_number_font')):
        color = (k.get(source) or {}).get('color') if isinstance(k.get(source), dict) else None
        if _int(color) and 0 <= color <= 19:
            out[key] = color
    return out


def convert(z: zipfile.ZipFile, formations: dict[int, list[int]] | None = None) -> Bundle:
    """The package as share records (origin 'package'). formations: the game's generic formations {id: 11
    positions}, to find the formation of a team that has none of its own (from its starters)."""
    manifest = read_manifest(z)
    c = _Converter(z, manifest, formations)
    records = c.convert()
    source = manifest.get('source') or {}
    meta = {'tool': manifest.get('tool'), 'created_at': manifest.get('created_at'),
            'patch_name': source.get('patch_name'), 'credits': manifest.get('credits')}
    return Bundle(records, 'package', meta, warnings=c.warnings)
