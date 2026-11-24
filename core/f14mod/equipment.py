"""Boots, goalkeeper gloves and balls: the game's own and the ones the user adds from PC packs (FIFA 14 to 16).

How the game uses them (validated in game):
  boot   players.shoetypecode (0-255) -> data/sceneassets/shoe/shoe_<code>.rx3 (mesh) +
         shoe_<code>_<design>_textures.rx3 (shoe_cm, shoe_nm, shoe_coeff). Code 0 is the generic boot, painted with
         shoecolorcode1/2 and shoedesigncode; a licensed boot is worn with colors 30/31 and design 0. The game's edit
         player screen lists a boot when it has a `playerboots` row like the game's store boots (isavailableinstore 1,
         powid -1, islicensed 1, islocked 0) and a name CreatePlayerBoot_<code>; any code works, also above the game's.
  glove  players.gkglovetypecode (0-127) -> data/sceneassets/gkglove/gkglove_<code>.rx3 (mesh: the game's glove 1 mesh
         fits every glove) + gkglove_<code>_textures.rx3 (gkglove_cm, gkglove_nm, gkglove_coeff). Only a player whose
         preferred position (preferredposition1) is goalkeeper wears his own glove; anyone else in goal wears the
         default one. The edit player screen only lists the game's own glove codes (a fixed list): a new code works
         in matches but is not listed (the screen shows another glove's name, and once changed there it cannot be
         picked again); the name GkGlovePattern_<code> only shows for the game's codes.
  ball   teams.balltype (0-255) = the ball of the home team's matches (friendlies and leagues; the league's ball is
         not used) -> data/sceneassets/ball/ball_<id>.rx3 + ball_<id>_textures.rx3 (ball_cm, ball_nm). The match
         settings list is the `teamballs` table, named BallName_<id>, with the picture
         data/ui/artassets/settingsimg/ball_<id>.big (a BIG archive with one DDS; the menu shows its top-left area).
New files go loose under Game/data/... (new codes work there).

Pack files of the newer games:
  - textures: their normal maps are BC5 (x, y only: z is rebuilt) and a boot's coeff map means something else (the
    game's average boot coeff is used): such files are written again in the game's own layout, all DXT1 without
    alpha (a coeff with alpha 0 written as DXT1 with alpha comes out black). Files already in the game's formats are
    kept as they are.
  - boot meshes: skinned to the 400-bone skeleton with u16 bone indices; they load but crash the game when the camera
    comes close. The bones are renumbered to FIFA 14's (always the same 8, 4 per leg), the indices become u8 and the
    game's own skeleton section is used (the result matches other tools' converted boots byte for byte).
"""
import io
import re
import struct

import numpy as np
from PIL import Image, ImageDraw

from . import chunk, images, rx3, rx3mesh

SHOE_DIR, GLOVE_DIR, BALL_DIR = 'data/sceneassets/shoe/', 'data/sceneassets/gkglove/', 'data/sceneassets/ball/'
MENU_DIR = 'data/ui/artassets/settingsimg/'
KINDS = ('boot', 'glove', 'ball')
FIELDS = {'boot': ('players', 'shoetypecode'), 'glove': ('players', 'gkglovetypecode'), 'ball': ('teams', 'balltype')}
CODES = {'boot': range(1, 256), 'glove': range(1, 128), 'ball': range(1, 256)}  # what the database fields hold
FILE_NAME = {'boot': re.compile(r'shoe_(\d+)\.rx3$'), 'glove': re.compile(r'gkglove_(\d+)\.rx3$'),
             'ball': re.compile(r'ball_(\d+)\.rx3$')}
DIRS = {'boot': SHOE_DIR, 'glove': GLOVE_DIR, 'ball': BALL_DIR}
TEXTURES = {'boot': ('shoe_cm', 'shoe_nm', 'shoe_coeff'), 'glove': ('gkglove_cm', 'gkglove_nm', 'gkglove_coeff'),
            'ball': ('ball_cm', 'ball_nm')}
NAME_STRING = {'boot': 'CreatePlayerBoot_{}', 'glove': 'GkGlovePattern_{}', 'ball': 'BallName_{}'}
# the other spellings of a glove's name in the game's texts (the same list, written by other tools)
GLOVE_NAME_SPELLINGS = ('GKGlovePattern_{}', 'gkglovepattern_{}')
BOOT_OTHER_NAME = 'Boot_{}'  # another list of boot names the game has (kept the same)
GLOVE_MESH = GLOVE_DIR + 'gkglove_1.rx3'  # every glove wears this mesh
BOOT_TEMPLATE = SHOE_DIR + 'shoe_200.rx3'  # the game's skeleton section of a boot
BOOT_COEFF = SHOE_DIR + 'shoe_200_0_textures.rx3'  # the coeff map a converted pack boot gets
BALL_MENU_MODEL = MENU_DIR + 'ball_1.big'
STORE_BOOT_ROW = {'isavailableinstore': 1, 'powid': -1, 'islicensed': 1, 'islocked': 0, 'isembargoed': 0,
                  'shoedesign': 0, 'shoecolor1': 30, 'shoecolor2': 31}
LICENSED_COLORS = (30, 31)  # shoecolorcode1/2 of a player wearing a licensed boot (shoedesigncode 0)
GOALKEEPER = 0  # preferredposition1 of a goalkeeper
MAX_UPLOAD = 64 * 1024 * 1024
MAX_SIZE = 2048  # texture side (a pack's own size is kept up to this)
BC5 = 7
TEXTURE_HEADERS, TEXTURE, NAMES = 0x6BD085DC, 0x7A0B60DA, 0x4C9B9EB2
# boot meshes of the newer packs: their bone ids -> FIFA 14's (one leg, the other leg)
BOOT_BONES = {315: 31, 316: 32, 317: 33, 330: 35, 348: 4, 349: 5, 350: 6, 363: 8}
SKELETON, PALETTE = 0xDF9AEC1E, 0x0F3861A2
DECL_WIDE = b'i0:18:00:0001:4u16 w0:20:00:0001:4u8n'
DECL_GAME = b'i0:18:00:0001:4u8 w0:1C:00:0001:4u8n'
BALL_RADIUS = (5.0, 20.0)  # cm: a mesh outside this is not a ball (the game's are ~11)


class EquipmentError(ValueError):
    """A file that is not a usable boot, glove or ball; `code` names the reason (texts in the interface)."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code, self.detail = code, detail


# ---------------------------------------------------------------- the game's items
def mesh_path(kind: str, code: int) -> str:
    return DIRS[kind] + {'boot': 'shoe_{}.rx3', 'glove': 'gkglove_{}.rx3', 'ball': 'ball_{}.rx3'}[kind].format(code)


def texture_path(kind: str, code: int) -> str:
    return DIRS[kind] + {'boot': 'shoe_{}_0_textures.rx3', 'glove': 'gkglove_{}_textures.rx3',
                         'ball': 'ball_{}_textures.rx3'}[kind].format(code)


def menu_path(ball: int) -> str:
    return MENU_DIR + f'ball_{ball}.big'


def game_codes(files, kind: str) -> list[int]:
    """The codes the game has a mesh for (boots: also a texture file of design 0)."""
    found = set()
    for path in files.list(DIRS[kind]):
        m = FILE_NAME[kind].search(path)
        if m and path == mesh_path(kind, int(m.group(1))) and int(m.group(1)) in CODES[kind]:
            found.add(int(m.group(1)))
    if kind == 'boot':
        found = {c for c in found if files.exists(texture_path('boot', c))}
    return sorted(found)


def free_codes(files, kind: str, taken=()) -> list[int]:
    used = set(game_codes(files, kind)) | set(taken)
    return [c for c in CODES[kind] if c not in used]


def listed_gloves(files) -> set[int]:
    """The glove codes the game's edit player screen lists (its own, with a name)."""
    return set(game_codes(files, 'glove'))


# ---------------------------------------------------------------- the user's files
def plain(data: bytes) -> bytes:
    if len(data) > MAX_UPLOAD:
        raise EquipmentError('equipment_file_too_big')
    return bytes(chunk.decode(data)) if data[:4] == b'chun' else data


def check_texture(kind: str, data: bytes) -> bytes:
    """The pack's texture file (bytes, chunk-compressed or not), checked; raises EquipmentError."""
    d = plain(data)
    if d[:4] != b'RX3l':
        raise EquipmentError('equipment_not_pc', d[:4].hex())
    try:
        found = {t.get('name') for t in rx3.textures(d)}
    except Exception as e:  # noqa: BLE001 (any parse error: not a texture file)
        raise EquipmentError('equipment_texture_invalid', f'{type(e).__name__}: {e}') from e
    missing = [n for n in TEXTURES[kind] if n not in found]
    if missing:
        raise EquipmentError('equipment_texture_missing', ', '.join(missing))
    return d


def _wide_decl(d: bytes) -> bool:
    return any(t == rx3mesh.DECL and DECL_WIDE in d[o:o + s] for t, o, s, _ in rx3mesh._sections(d))  # noqa: SLF001


def check_mesh(kind: str, data: bytes) -> bytes:
    """The pack's mesh file (boot or ball), checked; raises EquipmentError."""
    d = plain(data)
    if d[:4] != b'RX3l':
        raise EquipmentError('equipment_not_pc', d[:4].hex())
    try:
        meshes = rx3mesh.meshes(d)
    except Exception as e:  # noqa: BLE001
        raise EquipmentError('equipment_mesh_invalid', f'{type(e).__name__}: {e}') from e
    if not meshes or not {'p0', 'n0', 't0'} <= set(meshes[0]['attrs']):
        raise EquipmentError('equipment_mesh_invalid', 'no mesh')
    p = np.array(meshes[0]['attrs']['p0'])[:, :3]
    if kind == 'ball':
        radius = float(np.abs(p).max())
        if not BALL_RADIUS[0] <= radius <= BALL_RADIUS[1]:
            raise EquipmentError('ball_mesh_not_ball', f'{radius:.1f}')
    elif kind == 'boot':
        if not {'i0', 'w0'} <= set(meshes[0]['attrs']):
            raise EquipmentError('boot_mesh_not_boot', 'not skinned')
        bones = _boot_bones(d)
        if _wide_decl(d):
            unknown = sorted(bones - set(BOOT_BONES))
        else:
            unknown = sorted(bones - set(BOOT_BONES.values()))
        if unknown:
            raise EquipmentError('boot_mesh_not_boot', 'bones ' + ', '.join(map(str, unknown[:8])))
    return d


def _sections(d: bytes):
    return [(t, d[o:o + s]) for t, o, s, _ in rx3mesh._sections(d)]  # noqa: SLF001


def _boot_bones(d: bytes) -> set[int]:
    """The bone ids a boot mesh's vertices use (weight > 0; the vertices keep the ids themselves)."""
    secs = dict(_sections(d))
    wide = _wide_decl(d)
    vb = secs[rx3mesh.VERTICES]
    _, count, stride, _ = struct.unpack('<IIII', vb[:16])
    used = set()
    for i in range(count):
        v = vb[16 + i * stride:16 + (i + 1) * stride]
        idx = struct.unpack('<4H', v[24:32]) if wide else tuple(v[24:28])
        w = v[32:36] if wide else v[28:32]
        used.update(b for k, b in enumerate(idx) if w[k])
    return used


def _rx3(head: bytes, parts: list[tuple[int, bytes]]) -> bytes:
    """An RX3l file: its 16-byte header, the section table, the sections (each 16-aligned)."""
    table_end = 16 + 16 * len(parts)
    start = (table_end + 15) // 16 * 16
    body, offsets, p = b'', [], start
    for _, data in parts:
        offsets.append(p)
        padded = data.ljust((len(data) + 15) // 16 * 16, b'\0')
        body += padded
        p += len(padded)
    table = b''.join(struct.pack('<IIII', t, off, len(data), 0) for (t, data), off in zip(parts, offsets))
    out = head[:8] + struct.pack('<II', start + len(body), len(parts)) + table
    return out.ljust(start, b'\0') + body


def boot_mesh(pack: bytes, game_boot: bytes) -> bytes:
    """A boot mesh for the game: a newer pack's one with FIFA 14's bones (see the module), one already in the game's
    layout as it is. game_boot: any boot mesh of the game (its skeleton section)."""
    if not _wide_decl(pack):
        return pack
    game = dict(_sections(game_boot))
    parts = []
    for t, data in _sections(pack):
        if t == rx3mesh.DECL:
            text = data[16:].split(b'\0')[0].replace(DECL_WIDE, DECL_GAME)
            data = data[:4] + struct.pack('<I', len(text) + 1) + data[8:16] + text + b'\0'
            if len(data) < len(game[rx3mesh.DECL]):
                data = data.ljust(len(game[rx3mesh.DECL]), b'\0')
        elif t == rx3mesh.VERTICES:
            _, count, stride, flag = struct.unpack('<IIII', data[:16])
            if stride != 36:
                raise EquipmentError('boot_mesh_not_boot', f'stride {stride}')
            out = bytearray()
            for i in range(count):
                v = data[16 + i * 36:16 + (i + 1) * 36]
                out += v[:24] + bytes(BOOT_BONES.get(b, 0) for b in struct.unpack('<4H', v[24:32])) + v[32:36]
            data = struct.pack('<IIII', 16 + len(out), count, 32, flag) + bytes(out)
        elif t == SKELETON:
            data = game[SKELETON]
        elif t == PALETTE:
            count = data[4]
            full = {b & 0xFF: b for b in BOOT_BONES}
            bones = [BOOT_BONES[full[b]] for b in data[16 + 256:16 + 256 + count] if b in full]
            to_slot, to_bone = bytearray(256), bytearray(256)
            for s, b in enumerate(bones):
                to_slot[b] = s
            to_bone[:len(bones)] = bytes(bones)
            data = data[:4] + struct.pack('<I', len(bones)) + data[8:16] + bytes(to_slot) + bytes(to_bone)
        parts.append((t, data))
    return _rx3(pack[:16], parts)


# ---------------------------------------------------------------- textures
def decode(d: bytes, t: dict) -> Image.Image:
    if t['fmt'] != BC5:
        return rx3.to_image(d, t)
    q, n, w, h = t['levels'][0]
    hdr = (b'DDS ' + struct.pack('<7I', 124, 0x1007, h, w, n, 0, 1) + b'\0' * 44 +
           struct.pack('<2I4s5I', 32, 4, b'ATI2', 0, 0, 0, 0, 0) + struct.pack('<5I', 0x1000, 0, 0, 0, 0))
    return Image.open(io.BytesIO(hdr + d[q:q + n]))


def full_normal(img: Image.Image) -> Image.Image:
    """x, y (+ empty blue) -> x, y, z; a map that already has z is kept."""
    a = np.asarray(img.convert('RGB'), dtype=np.float32).copy()
    if a[..., 2].mean() > 64:
        return img.convert('RGB')
    x, y = a[..., 0] / 127.5 - 1, a[..., 1] / 127.5 - 1
    a[..., 2] = (np.sqrt(np.clip(1 - x * x - y * y, 0, 1)) + 1) * 127.5
    return Image.fromarray(a.clip(0, 255).astype(np.uint8), 'RGB')


def _dxt1(img: Image.Image) -> bytes:
    w, h = img.size
    pic = img.convert('RGB').convert('RGBA')  # opaque: no 1-bit alpha black blocks
    if w < 4 or h < 4:
        pic = pic.resize((max(4, w), max(4, h)), Image.LANCZOS)
    buf = io.BytesIO()
    pic.save(buf, 'DDS', pixel_format='DXT1')
    return buf.getvalue()[128:]


def _texture_section(img: Image.Image) -> tuple[bytes, bytes]:
    """(16-byte header, whole section) of one DXT1 texture with its full mip chain."""
    w, h = img.size
    mips, body = 0, b''
    cw, ch = w, h
    while True:
        level = img if (cw, ch) == (w, h) else img.resize((cw, ch), Image.LANCZOS)
        bw, bh = max(1, (cw + 3) // 4), max(1, (ch + 3) // 4)
        size = bw * bh * 8
        body += struct.pack('<IIII', bw * 8, bh, size, 0) + _dxt1(level)[:size]
        mips += 1
        if cw == 1 and ch == 1:
            break
        cw, ch = max(1, cw // 2), max(1, ch // 2)
    size = (16 + len(body) + 15) // 16 * 16  # the game counts the section's padding in its size
    header = struct.pack('<IBBBBHHHH', size, 1, 0, 1, 0, w, h, 1, mips)
    return header, (header + body).ljust(size, b'\0')


def textures_file(textures: list[tuple[str, Image.Image]]) -> bytes:
    """A texture file in the game's layout with these (name, picture) textures, in this order, DXT1."""
    headers, sections = [], []
    for _, img in textures:
        hdr, sec = _texture_section(img)
        headers.append(hdr)
        sections.append(sec)
    table = struct.pack('<I12x', len(textures)) + b''.join(headers)
    names = b''.join(struct.pack('<II', TEXTURE, len(n) + 8) + n.encode() + b'.Raster\0' for n, _ in textures)
    names = struct.pack('<II8x', 0, len(textures)) + names
    names = names.ljust((len(names) + 15) // 16 * 16, b'\0')
    names = struct.pack('<I', len(names)) + names[4:]
    return _rx3(b'RX3l' + struct.pack('<I', 4), [(TEXTURE_HEADERS, table)] + [(TEXTURE, s) for s in sections]
                + [(NAMES, names)])


def game_textures(kind: str, pack: bytes, replace: dict[str, Image.Image] | None = None) -> bytes:
    """The pack's texture file for the game: kept as it is when the game reads all its formats, else written again
    (see the module). replace: textures taken from elsewhere when it is written again."""
    found = {t['name']: t for t in rx3.textures(pack)}
    if all(found[n]['fmt'] in rx3.DDS_FOURCC for n in TEXTURES[kind]):
        return pack
    out = []
    for name in TEXTURES[kind]:
        img = (replace or {}).get(name) or decode(pack, found[name])
        if name.endswith('_nm'):
            img = full_normal(img)
        img = img.convert('RGB')
        if max(img.size) > MAX_SIZE:
            f = MAX_SIZE / max(img.size)
            img = img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)
        out.append((name, img))
    return textures_file(out)


def needs_coeff(pack: bytes) -> bool:
    """A newer pack's boot (BC5 normal map): its coeff map means something else."""
    return any(t['fmt'] == BC5 for t in rx3.textures(pack))


# ---------------------------------------------------------------- the patch's files of one item
def boot_files(files, code: int, mesh: bytes | None, texture: bytes | None) -> dict[str, bytes]:
    out = {}
    if mesh is not None:
        out[mesh_path('boot', code)] = boot_mesh(mesh, files.read(BOOT_TEMPLATE))
    if texture is not None:
        replace = None
        if needs_coeff(texture):
            base = files.read(BOOT_COEFF)
            replace = {'shoe_coeff': rx3.to_image(base, rx3.by_name(base, 'shoe_coeff'))}
        out[texture_path('boot', code)] = game_textures('boot', texture, replace)
    return out


def glove_files(files, code: int, texture: bytes | None, own_mesh: bool) -> dict[str, bytes]:
    out = {}
    if own_mesh:  # a new code: the game's glove mesh
        out[mesh_path('glove', code)] = files.read(GLOVE_MESH)
    if texture is not None:
        out[texture_path('glove', code)] = game_textures('glove', texture)
    return out


def ball_files(files, code: int, mesh: bytes | None, texture: bytes | None,
               picture: Image.Image | None) -> dict[str, bytes]:
    out = {}
    if mesh is not None:
        out[mesh_path('ball', code)] = mesh
    if texture is not None:
        out[texture_path('ball', code)] = game_textures('ball', texture)
    if picture is not None:
        model = files.read(menu_path(code)) or files.read(BALL_MENU_MODEL)
        if model is not None:
            out[menu_path(code)] = menu_picture(model, picture)
    return out


def menu_picture(blob: bytes, picture: Image.Image) -> bytes:
    """The game's ball picture archive with the user's picture drawn in the area the menu shows."""
    entries = images._big_entries(blob)  # noqa: SLF001
    apt = next((v for v in entries.values() if v.startswith(images.APT_DATA)), None)
    start = blob.index(b'DDS ')
    height, width = struct.unpack('<II', blob[start + 12:start + 20])
    four = blob[start + 84:start + 88].decode()
    if apt is not None and len(apt) >= images.APT_SHAPE_SIZE + 8:
        shown = struct.unpack('<ff', apt[images.APT_SHAPE_SIZE:images.APT_SHAPE_SIZE + 8])
        w, h = min(width, round(shown[0])), min(height, round(shown[1]))
    else:
        w, h = width, height
    pic = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    src = picture.convert('RGBA')
    f = min(w / src.width, h / src.height)
    src = src.resize((max(1, round(src.width * f)), max(1, round(src.height * f))), Image.LANCZOS)
    pic.alpha_composite(src, ((w - src.width) // 2, (h - src.height) // 2))
    buf = io.BytesIO()
    pic.save(buf, 'DDS', pixel_format=four if four in ('DXT1', 'DXT3', 'DXT5') else 'DXT5')
    new = buf.getvalue()
    count = struct.unpack('>I', blob[8:12])[0]
    p = 16
    for _ in range(count):
        offset, size = struct.unpack('>II', blob[p:p + 8])
        end = blob.index(b'\0', p + 8)
        if offset == start and size:
            if len(new) > size:
                raise EquipmentError('ball_picture_too_big')
            out = bytearray(blob)
            out[start:start + size] = new.ljust(size, b'\0')
            return bytes(out)
        p = end + 1
    raise EquipmentError('ball_picture_model')


# ---------------------------------------------------------------- the database and the texts
def add_store_boots(table, codes) -> int:
    """`playerboots` rows (like the game's store boots) for the boot codes it lacks; returns how many."""
    have = {table.get(r, 'shoetype') for r in table.records}
    columns = {f.name for f in table.fields}
    model = next((r for r in table.records if table.get(r, 'isavailableinstore') == 1 and table.get(r, 'powid') == -1
                  and table.get(r, 'islicensed') == 1), table.records[-1])
    added = 0
    for code in sorted(set(codes) - have):
        row = list(model)
        table.set(row, 'shoetype', code)
        for column, value in STORE_BOOT_ROW.items():
            if column in columns:
                table.set(row, column, value)
        if 'isadidas' in columns:
            table.set(row, 'isadidas', 0)
        table.records.append(row)
        added += 1
    return added


def list_boots(table, codes) -> int:
    """The game's boots the user named: their rows become store boots (listed by the edit player screen)."""
    changed = 0
    columns = {f.name for f in table.fields}
    for row in table.records:
        if table.get(row, 'shoetype') in codes:
            for column in ('isavailableinstore', 'powid', 'islocked', 'isembargoed'):
                if column in columns and table.get(row, column) != STORE_BOOT_ROW[column]:
                    table.set(row, column, STORE_BOOT_ROW[column])
                    changed += 1
    return changed


def add_menu_balls(table, codes) -> int:
    """`teamballs` rows (the match settings list) for the balls it lacks."""
    have = {table.get(r, 'ballid') for r in table.records}
    added = 0
    for code in sorted(set(codes) - have):
        row = list(table.records[-1])
        table.set(row, 'ballid', code)
        table.records.append(row)
        added += 1
    return added


def name_strings(kind: str, code: int, name: str) -> dict[str, str]:
    """The texts of an item's name (every spelling the game reads)."""
    out = {NAME_STRING[kind].format(code): name}
    if kind == 'boot':
        out[BOOT_OTHER_NAME.format(code)] = name
    return out


def player_columns(values: dict) -> dict:
    """The colors and design a player wearing a boot needs: a licensed one (code > 0) is worn with 30/31, design 0."""
    code = values.get('shoetypecode')
    if not code:
        return {}
    return {'shoecolorcode1': LICENSED_COLORS[0], 'shoecolorcode2': LICENSED_COLORS[1], 'shoedesigncode': 0}


# ---------------------------------------------------------------- pictures
def triangles(indices: list[int]) -> np.ndarray:
    """Triangles of a mesh's indices: a list (boots, gloves), or a strip (the balls: repeated indices mark its joins).
    A list never repeats an index inside one triangle (it may across two, so that alone does not mark a strip)."""
    if len(indices) % 3 == 0:
        tris = np.array(indices).reshape(-1, 3)
        if not ((tris[:, 0] == tris[:, 1]) | (tris[:, 1] == tris[:, 2]) | (tris[:, 0] == tris[:, 2])).any():
            return tris
    out = []
    for k in range(len(indices) - 2):
        a, b, c = indices[k:k + 3]
        if a == b or b == c or a == c:
            continue
        out.append((a, b, c) if k % 2 == 0 else (b, a, c))
    return np.array(out).reshape(-1, 3)


def rasterize(X, Y, depth, uv, shade_v, tris, tex, width, height):
    """(rgb float32 HxWx3, alpha uint8 HxW) of textured triangles drawn per pixel with a z-buffer (larger depth =
    nearer). X, Y = image positions of the vertices, uv = their texture coordinates, shade_v = their light factor."""
    size, h = width, height
    th, tw = tex.shape[:2]
    rgb = np.zeros((h, size, 3), np.float32)
    alpha = np.zeros((h, size), np.uint8)
    zb = np.full((h, size), -np.inf)
    for t in tris:
        x, y, z = X[t], Y[t], depth[t]
        x0, x1 = max(0, int(np.floor(x.min()))), min(size - 1, int(np.ceil(x.max())))
        y0, y1 = max(0, int(np.floor(y.min()))), min(h - 1, int(np.ceil(y.max())))
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if x1 < x0 or y1 < y0 or abs(den) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / den
        w1 = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        w0, w1, w2 = w0[inside], w1[inside], w2[inside]
        px, py = (gx[inside] - 0.5).astype(int), (gy[inside] - 0.5).astype(int)
        zz = w0 * z[0] + w1 * z[1] + w2 * z[2]
        front = zz > zb[py, px]
        if not front.any():
            continue
        px, py, w0, w1, w2, zz = px[front], py[front], w0[front], w1[front], w2[front], zz[front]
        u = w0 * uv[t[0], 0] + w1 * uv[t[1], 0] + w2 * uv[t[2], 0]
        v = w0 * uv[t[0], 1] + w1 * uv[t[1], 1] + w2 * uv[t[2], 1]
        shade = w0 * shade_v[t[0]] + w1 * shade_v[t[1]] + w2 * shade_v[t[2]]
        texel = tex[np.clip((v * th).astype(int) % th, 0, th - 1), np.clip((u * tw).astype(int) % tw, 0, tw - 1)]
        zb[py, px] = zz
        rgb[py, px] = texel * shade[:, None]
        alpha[py, px] = 255
    return rgb, alpha


def _color(texture: bytes, kind: str) -> np.ndarray:
    t = rx3.by_name(texture, TEXTURES[kind][0])
    img = decode(texture, t).convert('RGB')
    if max(img.size) > 512:
        img = img.resize((max(1, img.width * 512 // max(img.size)), max(1, img.height * 512 // max(img.size))))
    return np.asarray(img)


def thumbnail(kind: str, mesh: bytes, texture: bytes, width: int = 256, supersample: int = 2) -> Image.Image:
    """The item's picture drawn from its files: the boot's outer side (right foot), the back of the right glove, the
    ball from the front."""
    m = rx3mesh.meshes(mesh)[0]
    p = np.array(m['attrs']['p0'])[:, :3]
    uv = np.array(m['attrs']['t0'])[:, :2]
    nrm = np.array(m['attrs']['n0'])[:, :3] if 'n0' in m['attrs'] else np.tile([0.0, 0.0, 1.0], (len(p), 1))
    tris = triangles(m['indices'])
    tex = _color(texture, kind)
    if kind == 'boot':
        tris = tris[(p[tris][:, :, 0] > 0).all(1)]
        sx, sy, depth, light = p[:, 2], -p[:, 1], p[:, 0], (0.6, 0.6, 0.5)
    elif kind == 'glove':
        tris = tris[(p[tris][:, :, 0] > 0).all(1)]
        sx, sy, depth, light = p[:, 0], p[:, 2], p[:, 1], (0.3, 0.9, 0.4)
    else:
        sx, sy, depth, light = p[:, 0], -p[:, 1], p[:, 2], (-0.4, 0.6, 0.7)
    if not len(tris):
        tris = triangles(m['indices'])
    used = np.unique(tris)
    lo = np.array([sx[used].min(), sy[used].min()])
    hi = np.array([sx[used].max(), sy[used].max()])
    size = width * supersample
    pad = size // 16
    scale = (size - 2 * pad) / max(float(max(hi - lo)), 1e-6)
    h = int((hi[1] - lo[1]) * scale) + 2 * pad
    X = (size - (hi[0] - lo[0]) * scale) / 2 + (sx - lo[0]) * scale
    Y = pad + (sy - lo[1]) * scale
    lv = np.array(light) / np.linalg.norm(light)
    shade_v = 0.5 + 0.5 * np.clip(nrm @ lv, 0, 1)
    rgb, alpha = rasterize(X, Y, depth, uv, shade_v, tris, tex, size, h)
    img = Image.fromarray(np.dstack([rgb.clip(0, 255).astype(np.uint8), alpha]), 'RGBA')
    return img.resize((width, max(1, h // supersample)), Image.LANCZOS)


def placeholder(width: int = 256) -> Image.Image:
    """A plain picture for an item without files yet."""
    img = Image.new('RGBA', (width, width), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((width * 0.2, width * 0.2, width * 0.8, width * 0.8), outline=(150, 150, 150, 255),
                                width=max(2, width // 40))
    return img
