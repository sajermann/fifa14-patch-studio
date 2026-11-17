"""A fake FIFA 14 installation for the tests: a small but real T3DB (written here, read by f14mod.t3db), a language
database, crests, photos, league pictures, kits, fonts and face files, loose or inside a BIG archive. Every value is
invented: nothing in it comes from a game."""
import heapq
import io
import itertools
import os
import struct

from PIL import Image

# ---- invented data -------------------------------------------------------------------------------------------------

LEAGUE = 9001         # league with every name and both pictures
PLAIN_LEAGUE = 9002   # league with the database name only, no pictures
TEAM = 7001           # team with names, crest, the three kits and 16 players (2 goalkeepers)
SMALL_TEAM = 7002     # team without names or pictures, 6 players
STAR = 8001           # player with real face and photo, the best of TEAM
KEEPER, BACKUP_KEEPER = 8002, 8003
SHARED = 8016         # player in both teams
SMALL_TEAM_PLAYERS = [SHARED] + list(range(8101, 8106))

COUNTS = {'leagues': 2, 'teams': 2, 'players': 21}

NATIONS = [{'nationid': 54, 'nationname': 'Nowhereland', 'teamid': -1, 'confederation': 1},
           {'nationid': 52, 'nationname': 'Elsewhere', 'teamid': -1, 'confederation': 1}]
LEAGUES = [{'leagueid': LEAGUE, 'leaguename': 'Test League (1)', 'countryid': 54, 'level': 1},
           {'leagueid': PLAIN_LEAGUE, 'leaguename': 'Plain League', 'countryid': 52, 'level': 2}]
TEAMS = [
    {'teamid': TEAM, 'teamname': 'Test Athletic Club', 'teamcolor1r': 200, 'teamcolor1g': 10, 'teamcolor1b': 20,
     'teamcolor2r': 250, 'teamcolor2g': 250, 'teamcolor2b': 250, 'captainid': STAR, 'penaltytakerid': STAR,
     'freekicktakerid': 8004, 'longkicktakerid': 8004, 'leftcornerkicktakerid': 8005,
     'rightcornerkicktakerid': 8005},
    {'teamid': SMALL_TEAM, 'teamname': 'Small Team FC', 'teamcolor1r': 0, 'teamcolor1g': 0, 'teamcolor1b': 200,
     'teamcolor2r': 255, 'teamcolor2g': 255, 'teamcolor2b': 255, 'captainid': 0, 'penaltytakerid': 0,
     'freekicktakerid': 0, 'longkicktakerid': 0, 'leftcornerkicktakerid': 0, 'rightcornerkicktakerid': 0},
]
LEAGUE_TEAM_LINKS = [{'leagueid': LEAGUE, 'teamid': TEAM}, {'leagueid': PLAIN_LEAGUE, 'teamid': SMALL_TEAM}]

# language database: (stringid, text); the _upd database overrides the base one
STRINGS = [
    (f'TeamName_{TEAM}', 'Old Name'),  # replaced by the _upd database
    (f'TeamName_Abbr15_{TEAM}', 'Test Athletic'),
    (f'TeamName_Abbr10_{TEAM}', 'Test Ath.'),
    (f'TeamName_Abbr7_{TEAM}', 'TestAth'),
    (f'TeamName_Abbr3_{TEAM}', 'TAT'),
    (f'CT_TeamName_{TEAM}', 'Athletic'),
    (f'LeagueName_{LEAGUE}', 'Test Premier Division of Nowhere'),
    (f'LeagueName_Abbr15_{LEAGUE}', 'Test Premier Division'),  # some patches put a name longer than 15 here
    (f'Labbr_{LEAGUE}', 'TST 1'),
    (f'TrophyName_{LEAGUE}', 'Test Premier Trophy'),
    (f'TrophyName_Abbr15_{LEAGUE}', 'Test Cup'),
    ('Other_String_1', 'ignored'),
]
STRINGS_UPD = [(f'TeamName_{TEAM}', 'Test Athletic Club')]


def _players():
    """16 players of TEAM (STAR first, 2 goalkeepers) + 5 of SMALL_TEAM. Overall falls by player: the "goalkeeper +
    12 best" pick is the best goalkeeper and the outfield players 8001 and 8004-8014."""
    rows, names, links = [], [], []
    name_id = itertools.count(1)

    def name(text):
        if not text:
            return 0
        nid = next(name_id)
        names.append({'nameid': nid, 'name': text})
        return nid

    def add(pid, first, last, common, overall, position, team, number, birthdate):
        rows.append({
            'playerid': pid, 'firstnameid': name(first), 'lastnameid': name(last), 'commonnameid': name(common),
            'playerjerseynameid': name(last.upper() if last else common.upper()), 'overallrating': overall,
            'preferredposition1': position, 'height': 180, 'weight': 75, 'preferredfoot': 1 + pid % 2,
            'birthdate': birthdate, 'nationality': 54, 'skillmoves': 2,
            # appearance codes outside any short list: they must go exactly as they are
            'headtypecode': 2500 + pid % 7, 'hairtypecode': 300 + pid % 5, 'skintonecode': 1 + pid % 10,
            **{attr: overall for attr in ('acceleration', 'sprintspeed', 'finishing', 'shortpassing', 'dribbling',
                                          'ballcontrol', 'standingtackle', 'interceptions', 'strength',
                                          'stamina', 'gkdiving', 'gkhandling', 'gkpositioning', 'gkreflexes')}})
        for t in team:
            links.append({'teamid': t, 'playerid': pid, 'position': 28 if number > 11 else position,
                          'jerseynumber': number})

    add(STAR, 'Star', 'Plàyer', 'Starman', 95, 25, [TEAM], 10, 140000)
    add(KEEPER, 'First', 'Keeper', '', 80, 0, [TEAM], 1, 140100)
    add(BACKUP_KEEPER, 'Backup', 'Keeper', '', 79, 0, [TEAM], 12, 140200)
    for i, pid in enumerate(range(8004, 8017)):  # 13 outfield players, overall 90 down to 78
        add(pid, f'Player{i}', f'Number{i}', '', 90 - i, 3 + i % 20, [TEAM, SMALL_TEAM] if pid == SHARED else [TEAM],
            i + 2 if i + 2 != 10 else 30, 140300 + 100 * i)
    for i, pid in enumerate(SMALL_TEAM_PLAYERS[1:]):
        # the small team's players share one birth date: a placeholder (more than 20% of the players)
        add(pid, f'Small{i}', f'Guy{i}', '', 60 - i, 0 if i == 0 else 5, [SMALL_TEAM], i + 1, 150000)
    return rows, names, links


def _kits():
    """teamkits: year 0 = the kit in kit_<team>_<kind>_0.rx3; the year 1 row (a classic kit) must not replace it."""
    rows = []
    for kind in (0, 1, 2):
        rows.append({'teamtechid': TEAM, 'teamkittypetechid': kind, 'year': 0, 'jerseynamecolorr': 255,
                     'jerseynamecolorg': 255, 'jerseynamecolorb': kind * 100, 'numbercolor': 1, 'numberfonttype': 1,
                     'shortsnumbercolor': 2, 'shortsnumberfonttype': 1, 'jerseycollargeometrytype': 3,
                     'jerseyfrontnumberplacementcode': 1, 'shortsnumberplacementcode': 0, 'jerseynamelayouttype': 0,
                     'jerseynamefonttype': 2, 'jerseybacknameplacementcode': 1})
    rows.append({**rows[0], 'year': 1, 'jerseycollargeometrytype': 9})
    return rows


# ---- T3DB writer (the layout extractor.fifa_db reads) ------------------------------------------------------------

STRING_SHORT, STRING_LONG, INT = 13, 14, 3  # field types: Huffman string (1 / 2-byte length), integer


def _huffman(texts):
    """(tree bytes, {byte: bit string}) for the texts: node i = two 2-byte entries, (0, byte) = leaf,
    (node, 0) = go to node; node 0 = root."""
    freq = {}
    for t in texts:
        for b in t:
            freq[b] = freq.get(b, 0) + 1
    for filler in (ord('a'), ord('b')):  # a tree needs two leaves
        freq.setdefault(filler, 0)
    order = itertools.count()
    heap = [(f, next(order), b) for b, f in freq.items()]
    heapq.heapify(heap)
    while len(heap) > 1:
        f1, _, a = heapq.heappop(heap)
        f2, _, b = heapq.heappop(heap)
        heapq.heappush(heap, (f1 + f2, next(order), (a, b)))
    root = heap[0][2]
    nodes, codes, queue = [], {}, [(root, '')]
    index = {id(root): 0}
    while queue:  # breadth first: the root gets 0, every child a higher index
        node, code = queue.pop(0)
        entries = []
        for bit, child in enumerate(node):
            if isinstance(child, int):
                codes[child] = code + str(bit)
                entries.append((0, child))
            else:
                index[id(child)] = len(index)
                entries.append((index[id(child)], 0))
                queue.append((child, code + str(bit)))
        nodes.append(bytes(itertools.chain.from_iterable(entries)))
    assert len(nodes) < 256
    return b''.join(nodes), codes


def _encode(text, codes, prefix_len):
    bits = ''.join(codes[b] for b in text)
    bits += '0' * (-len(bits) % 8)
    return len(text).to_bytes(prefix_len, 'big') + bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def _table(rows, types=None):
    """Bytes of one table; fields = the keys of the rows (an int column or a string column)."""
    types = dict(types or {})
    fields = list(dict.fromkeys(k for r in rows for k in r))
    for f in fields:
        if f not in types:
            types[f] = STRING_SHORT if any(isinstance(r.get(f), str) for r in rows) else INT
    texts = [r[f].encode('utf-8') for r in rows for f in fields if types[f] != INT and r.get(f) is not None]
    tree, codes = _huffman(texts)
    area = bytearray(tree)
    lows = {f: min([0] + [r.get(f) or 0 for r in rows]) for f in fields if types[f] == INT}
    records = []
    for r in rows:
        value = 0
        for k, f in enumerate(fields):
            if types[f] == INT:
                v = (r.get(f) or 0) - lows[f]
            elif r.get(f) is None:
                v = 0xFFFFFFFF
            else:
                v = len(area)
                area += _encode(r[f].encode('utf-8'), codes, 2 if types[f] == STRING_LONG else 1)
            value |= v << (32 * k)
        records.append(value.to_bytes(4 * len(fields), 'little'))
    rec_size = 4 * len(fields)
    flags = 0x40 if any(types[f] != INT for f in fields) else 0  # 0x40: the string area is Huffman coded
    head = struct.pack('<IIIIHHIB', flags, rec_size, 0, len(area), 0, len(rows), 0, len(fields)).ljust(0x24, b'\0')
    field_defs = b''.join(struct.pack('<II4sI', types[f], 32 * k, f'f{k:03d}'.encode(), 32)
                          for k, f in enumerate(fields))
    return head + field_defs + b''.join(records) + bytes(area), fields, lows


def write_db(path, tables, meta_path=None, types=None):
    """T3DB with {table name: rows}; meta_path: the XML that names the tables and fields (short names t000/f000)."""
    blobs, meta = [], []
    for i, (name, rows) in enumerate(tables.items()):
        blob, fields, lows = _table(rows, (types or {}).get(name))
        blobs.append((f't{i:03d}'.encode(), blob))
        meta.append(f'<table name="{name}" shortname="t{i:03d}">' + ''.join(
            f'<field name="{f}" shortname="f{k:03d}" rangelow="{lows.get(f, 0)}"/>' for k, f in enumerate(fields))
            + '</table>')
    directory, body = b'', b''
    for short, blob in blobs:
        directory += short + struct.pack('<I', len(body))
        body += blob
    data = b'DB\0\x08'.ljust(16, b'\0') + struct.pack('<II', len(blobs), 0) + directory + b'\0' * 4 + body
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)
    if meta_path:
        with open(meta_path, 'w', encoding='utf-8') as f:
            f.write('<database>' + ''.join(meta) + '</database>')


def write_strings_db(path, strings):
    rows = [{'hashid': n, 'stringid': sid, 'sourcetext': text} for n, (sid, text) in enumerate(strings, 1)]
    write_db(path, {'LanguageStrings': rows},
             types={'LanguageStrings': {'hashid': INT, 'stringid': STRING_SHORT, 'sourcetext': STRING_LONG}})


# ---- pictures, kits, faces -----------------------------------------------------------------------------------------

def _dds(path, size, color):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new('RGBA', size, (255, 255, 255, 255))  # white tile around the picture, as FIFA 14 crests have
    img.paste(Image.new('RGBA', (size[0] // 2, size[1] // 2), color), (size[0] // 4, size[1] // 4))
    img.save(path, 'DDS')


TEXTURE_SECTION, NAMES_SECTION, POSITIONS_SECTION = 0x7A0B60DA, 0x4C9B9EB2, 0xF55B1A1A
KIT_POSITIONS = [[0.1, 0.1, 0.2, 0.2], [0.3, 0.1, 0.5, 0.3], [0.6, 0.1, 0.7, 0.2], [0.3, 0.4, 0.5, 0.45],
                 [0.4, 0.4, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0], [0.1, 0.6, 0.2, 0.7], [0.3, 0.6, 0.4, 0.7]]


def kit_rx3(color):
    """RX3l kit: jersey_cm (64x64) and shorts_cm (32x16) as raw BGRA, their names and the position table."""
    def texture(w, h):
        raw = Image.new('RGBA', (w, h), color + (255,)).tobytes('raw', 'BGRA')
        return struct.pack('<IBBBBHHHH', 0, 0, 7, 0, 0, w, h, 0, 1) + struct.pack('<IIII', 0, 0, len(raw), 0) + raw

    def names(*items):
        out = b''
        for n in items:
            b = n.encode() + b'\0'
            out += struct.pack('<II', 0, len(b)) + b
        return struct.pack('<IIII', 0, len(items), 0, 0) + out

    rects = iter(KIT_POSITIONS)
    pos = b''
    for group, count in (('jersey', 6), ('shorts', 2)):
        pos += group.encode() + b'\0' + bytes([count])
        for n in ('team', 'numberback', 'numberfront', 'name', 'name_arccenter', 'name_arctangent')[:count] \
                if group == 'jersey' else ('team', 'number'):
            pos += n.encode() + b'\0' + struct.pack('<4f', *next(rects))
    positions = b'\0' * 16 + pos
    sections = [(TEXTURE_SECTION, texture(64, 64)), (TEXTURE_SECTION, texture(32, 16)),
                (NAMES_SECTION, names('jersey_cm.Raster', 'shorts_cm.Raster')), (POSITIONS_SECTION, positions)]
    off = 16 + 16 * len(sections)
    table, body = b'', b''
    for kind, blob in sections:
        table += struct.pack('<IIII', kind, off + len(body), len(blob), 0)
        body += blob
    return b'RX3l' + b'\0' * 8 + struct.pack('<I', len(sections)) + table + body


def chunkzip(raw, chunk_size=0x8000):
    """EA's 'chunkzip' container (raw-deflate chunks aligned to 8 bytes), the way some patches ship kits."""
    import zlib
    out = bytearray(b'chunkzip' + struct.pack('>II', 2, len(raw)) + bytes(0x28 - 16))
    for i in range(0, len(raw), chunk_size):
        comp = zlib.compressobj(9, zlib.DEFLATED, -15)
        part = comp.compress(raw[i:i + chunk_size]) + comp.flush()
        out += struct.pack('>II', len(part), 1) + part
        out += bytes(-len(out) % 8)
    return bytes(out)


FACE_FILES = ['heads/head_{}_0.rx3', 'faces/face_{}_0_0_0_0_0_0_0_0_textures.rx3', 'heads/eyes_{}_0_textures.rx3',
              'hair/hair_{}_0_0.rx3']


def build(root):
    """Writes the fake installation under root (root/Game/data, the layout of the patches) and returns root."""
    data = os.path.join(root, 'Game', 'data')
    write_db(os.path.join(data, 'db', 'fifa_ng_db.db'), _tables(), os.path.join(data, 'db', 'fifa_ng_db-meta.xml'))
    write_strings_db(os.path.join(data, 'loc', 'eng_us.db'), STRINGS)
    write_strings_db(os.path.join(data, 'loc', 'eng_us_upd.db'), STRINGS_UPD)

    img = os.path.join(data, 'ui', 'imgAssets')
    _dds(os.path.join(img, 'crest', f'l{TEAM}.dds'), (64, 64), (200, 10, 20, 255))
    _dds(os.path.join(img, 'league', f'l{LEAGUE}.dds'), (64, 64), (0, 100, 0, 255))
    _dds(os.path.join(img, 'league512x128', f'l{LEAGUE}.dds'), (128, 32), (0, 100, 0, 255))
    _dds(os.path.join(img, 'heads', f'p{STAR}.dds'), (32, 32), (180, 140, 100, 255))
    for kind, color in ((0, (200, 10, 20)), (1, (250, 250, 250)), (2, (20, 20, 20))):
        path = os.path.join(data, 'sceneassets', 'kit', f'kit_{TEAM}_{kind}_0.rx3')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(chunkzip(kit_rx3(color)) if kind == 1 else kit_rx3(color))  # the away kit compressed
    # SMALL_TEAM: files that cannot be read (an empty kit, a crest that is not a DDS): left out, never a crash
    with open(os.path.join(data, 'sceneassets', 'kit', f'kit_{SMALL_TEAM}_0_0.rx3'), 'wb') as f:
        pass
    with open(os.path.join(img, 'crest', f'l{SMALL_TEAM}.dds'), 'wb') as f:
        f.write(b'DDS broken file')
    for pattern in FACE_FILES:
        path = os.path.join(data, 'sceneassets', *pattern.format(STAR).split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(f'fake {pattern}'.encode())
    # a player with only the head file has no real face (the face textures are required)
    path = os.path.join(data, 'sceneassets', 'heads', f'head_{KEEPER}_0.rx3')
    with open(path, 'wb') as f:
        f.write(b'fake head')
    for game_path, blob in _fonts().items():
        path = os.path.join(root, 'Game', *game_path.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(blob)
    _dds(os.path.join(img, 'flags512x512', 'f54.dds'), (16, 16), (0, 0, 255, 255))
    _dds(os.path.join(img, 'flags64x64', 'f54.dds'), (8, 8), (0, 0, 255, 255))
    return root


def _tables():
    players, names, links = _players()
    return {'leagues': LEAGUES, 'teams': TEAMS, 'leagueteamlinks': LEAGUE_TEAM_LINKS, 'players': players,
            'playernames': names, 'teamplayerlinks': links, 'nations': NATIONS, 'teamkits': _kits(),
            # a name edited in the database wins over the name table
            'editedplayernames': [{'playerid': KEEPER, 'firstname': 'Edited', 'surname': 'Keeper',
                                   'commonname': '', 'playerjerseyname': 'EDITED'}],
            'teamstadiumlinks': [{'teamid': TEAM, 'stadiumid': 3}]}


def number_font_rx3(color):
    """kitnumbers file: ten digit textures painted in `color` (raw BGRA, 8x8)."""
    def texture():
        raw = Image.new('RGBA', (8, 8), color + (255,)).tobytes('raw', 'BGRA')
        return struct.pack('<IBBBBHHHH', 0, 0, 7, 0, 0, 8, 8, 0, 1) + struct.pack('<IIII', 0, 0, len(raw), 0) + raw
    sections = [(TEXTURE_SECTION, texture()) for _ in range(10)]
    off = 16 + 16 * len(sections)
    table, body = b'', b''
    for kind, blob in sections:
        table += struct.pack('<IIII', kind, off + len(body), len(blob), 0)
        body += blob
    return b'RX3l' + b'\0' * 8 + struct.pack('<I', len(sections)) + table + body


def _fonts():
    """Name font of the kits (not a real font file) and the number files of their two palette colors."""
    return {'data/sceneassets/jerseyfonts/font_2.ttf': b'not a real font',
            'data/sceneassets/kitnumbers/kitnumbers_1_1.rx3': number_font_rx3((250, 250, 250)),
            'data/sceneassets/kitnumbers/kitnumbers_1_2.rx3': chunkzip(number_font_rx3((10, 10, 10)))}


def write_bh(path, names):
    """.bh index for an archive with these entries (made-up, non-zero hash words)."""
    out = bytearray(b'ViV4' + struct.pack('<I', 16 + 20 * len(names)) + struct.pack('>II', len(names), 16 + 20 * len(names)))
    for i, name in enumerate(names):
        out += struct.pack('>III', 0, 0, 0) + struct.pack('>II', 0x1000 + i, 0xABCD0000 + len(name))
    with open(path, 'wb') as f:
        f.write(out)


def write_big(path, files):
    """BIG4 archive with {game path: bytes}."""
    names = list(files)
    header = 16 + sum(8 + len(n.encode()) + 1 for n in names)
    index, body, offset = b'', b'', header
    for n in names:
        index += struct.pack('>II', offset, len(files[n])) + n.encode() + b'\0'
        body += files[n]
        offset += len(files[n])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'BIG4' + struct.pack('<I', header + len(body)) + struct.pack('>II', len(names), header) + index
                + body)


def build_archived(root):
    """The same data the way an installation without loose files keeps it: the database (packed) in patch.big, an
    older database in data0.big (patch.big wins), the language databases in data/loc/locale.big, pictures and kits in
    data1.big; one crest also loose (the loose file wins). Returns root."""
    tmp = os.path.join(root, '_loose')
    build(tmp)
    loose = os.path.join(tmp, 'Game')
    collected = {}
    for folder, _, names in os.walk(loose):
        for n in names:
            full = os.path.join(folder, n)
            with open(full, 'rb') as f:
                collected[os.path.relpath(full, loose).replace(os.sep, '/').lower()] = f.read()
    game = os.path.join(root, 'Game')
    db = {k: chunkzip(v) for k, v in collected.items() if k.startswith('data/db/')}
    write_big(os.path.join(game, 'patch.big'), db)
    old = dict(db)
    old['data/db/fifa_ng_db.db'] = b'not the database the game uses'
    write_big(os.path.join(game, 'data0.big'), old)
    write_big(os.path.join(game, 'data', 'loc', 'locale.big'),
              {k: v for k, v in collected.items() if k.startswith('data/loc/')})
    write_big(os.path.join(game, 'data1.big'),
              {k: chunkzip(v) for k, v in collected.items() if not k.startswith(('data/db/', 'data/loc/'))})
    crest = f'data/ui/imgassets/crest/l{TEAM}.dds'
    os.makedirs(os.path.join(game, 'data', 'ui', 'imgassets', 'crest'), exist_ok=True)
    _dds(os.path.join(game, *crest.split('/')), (32, 32), (0, 0, 0, 255))
    import shutil
    shutil.rmtree(tmp)
    return root


ARCHIVES = ('data0', 'data1', 'data2', 'data3', 'data5', 'data6', 'data7', 'patch')
STRINGS_PT = [(sid, text + ' PT') for sid, text in STRINGS]


def build_installed(root):
    """A clean installation the way the game ships: the executable, every archive with its .bh index, nothing
    loose, and the language archive with two languages. Returns the game folder (root/Game)."""
    build_archived(root)
    game = os.path.join(root, 'Game')
    os.remove(os.path.join(game, 'data', 'ui', 'imgassets', 'crest', f'l{TEAM}.dds'))  # no loose override
    import shutil
    shutil.rmtree(os.path.join(game, 'data', 'ui'))
    loc_dir = os.path.join(root, '_loc')
    write_strings_db(os.path.join(loc_dir, 'eng_us.db'), STRINGS)
    write_strings_db(os.path.join(loc_dir, 'por_br.db'), STRINGS_PT)
    loc = {f'data/loc/{n}': open(os.path.join(loc_dir, n), 'rb').read() for n in ('eng_us.db', 'por_br.db')}
    loc['locale.ini'] = b'[LOCALE]'
    write_big(os.path.join(game, 'data', 'loc', 'locale.big'), loc)
    shutil.rmtree(loc_dir)
    with open(os.path.join(game, 'patch.big'), 'rb'):
        pass
    # the update database of one language goes in patch.big, like the game's
    from f14mod.big import BigArchive
    patch = BigArchive(os.path.join(game, 'patch.big'))
    entries = {k: patch.read(k) for k in patch.order}
    upd = os.path.join(root, '_upd.db')
    write_strings_db(upd, STRINGS_UPD)
    entries['data/loc/eng_us_upd.db'] = open(upd, 'rb').read()
    os.remove(upd)
    write_big(os.path.join(game, 'patch.big'), entries)
    for name in ARCHIVES:
        big = os.path.join(game, name + '.big')
        if not os.path.exists(big):
            write_big(big, {})
        write_bh(os.path.join(game, name + '.bh'), BigArchive(big).order)
    with open(os.path.join(game, 'fifa14.exe'), 'wb') as f:
        f.write(b'not a program')
    return game
