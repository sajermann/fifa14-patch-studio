"""Game parts for a real face that lacks some: the generic eyes and the generic hair the game already has.

A face of a pack often comes without its eyes or its hair. The user may fill those in with the game's own generic
parts (the ones the generic heads use): eyes_<code>_1_textures, hair_<code>_1_0 + hair_<code>_1_textures and
hairlod_<code>_1_0. A face with its own hair but not the one seen from afar may take only the generic hairlod. The
project keeps only the codes ({'eyes': 5, 'hair': 12} or {'hairlod': 12}); the files are read from the game
folder of whoever builds the patch and are never kept in the project (they are the game's, not ours).

On a real face the game does not paint the generic hair (its texture is grey), so the hair texture is painted here
with the player's hair color (the game's own table, preview.HAIR_COLORS): the strands' detail is kept and the
picture's average becomes the color. Only the color half of the DXT5 blocks is written; the alpha half is the game's.

The generic hair was made for the generic heads: on a real head some styles float a little or leave the nape open.
The screen says so; the app does not try to fit it.
"""
import hashlib
import io
import re
import struct
import threading
from collections import OrderedDict

from PIL import Image, ImageStat

from . import preview, rx3

EYES_PATH = 'data/sceneassets/heads/eyes_{}_1_textures.rx3'
HAIR_PATHS = {
    'hair': 'data/sceneassets/hair/hair_{}_1_0.rx3',
    'hair_textures': 'data/sceneassets/hair/hair_{}_1_textures.rx3',
    'hairlod': 'data/sceneassets/hairlod/hairlod_{}_1_0.rx3',
}
EYES_KINDS = ('eyes',)
HAIR_KINDS = tuple(HAIR_PATHS)
HAIRLOD_KINDS = ('hairlod',)
GROUPS = {'eyes': EYES_KINDS, 'hair': HAIR_KINDS, 'hairlod': HAIRLOD_KINDS}  # what each fill key covers
MAX_CODE = 4095


class FillError(ValueError):
    pass


def check_fill(value) -> dict:
    """A fill of the screen ({'eyes': code, 'hair': code, 'hairlod': code}, any of them), checked: only whole
    codes; the hair brings its own hairlod, so a fill with both keeps only the hair. Empty = {}."""
    if not isinstance(value, dict):
        raise FillError('fill')
    out = {}
    for key in GROUPS:
        v = value.get(key)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, int) or not 0 < v <= MAX_CODE:
            raise FillError(key)
        out[key] = v
    if 'hair' in out:
        out.pop('hairlod', None)
    return out


def covered(fill) -> set[str]:
    """The kinds of face parts the fill brings."""
    return {kind for key in (fill or {}) for kind in GROUPS.get(key, ())}


def _codes(files, folder: str, pattern: str) -> set[int]:
    rx = re.compile(pattern)
    return {int(m.group(1)) for p in files.list(folder) if (m := rx.search(p))}


def eyes_codes(files) -> list[int]:
    """Generic eyes the game has (every file is a color)."""
    return sorted(_codes(files, 'data/sceneassets/heads/', r'/eyes_(\d+)_1_textures\.rx3$'))


def hair_codes(files) -> list[int]:
    """Generic hair styles the game has all three files of (model, texture, hair seen from afar)."""
    both = _codes(files, 'data/sceneassets/hair/', r'/hair_(\d+)_1_0\.rx3$') & \
        _codes(files, 'data/sceneassets/hair/', r'/hair_(\d+)_1_textures\.rx3$')
    return sorted(both & _codes(files, 'data/sceneassets/hairlod/', r'/hairlod_(\d+)_1_0\.rx3$'))


def hairlod_codes(files) -> list[int]:
    """Generic hair seen from afar the game has."""
    return sorted(_codes(files, 'data/sceneassets/hairlod/', r'/hairlod_(\d+)_1_0\.rx3$'))


_PAINTED: OrderedDict = OrderedDict()  # (sha1 of the game's file, rgb) -> painted file: the preview asks again and again
_PAINTED_MAX = 16
_PAINTED_LOCK = threading.Lock()  # the preview's requests run in several threads


def _painted(texture: bytes, rgb: int) -> bytes:
    """_paint, keeping the last few results (keyed by a digest, so the game's files are not kept as keys)."""
    key = (hashlib.sha1(texture).digest(), rgb)
    with _PAINTED_LOCK:
        if key in _PAINTED:
            _PAINTED.move_to_end(key)
            return _PAINTED[key]
    out = _paint(texture, rgb)
    with _PAINTED_LOCK:
        _PAINTED[key] = out
        while len(_PAINTED) > _PAINTED_MAX:
            _PAINTED.popitem(last=False)
    return out


def _paint(texture: bytes, rgb: int) -> bytes:
    """The hair textures file with hair_cm painted with rgb. The color half of every DXT5 block (every mip) is
    new, the alpha half stays the game's."""
    d = bytearray(texture)
    t = rx3.by_name(bytes(d), 'hair_cm')
    if t['fmt'] != 2:  # DXT5: the only format the game's generic hair uses
        return texture
    img = rx3.to_image(bytes(d), t).convert('RGBA')
    grey = img.convert('L')
    mean = max(ImageStat.Stat(grey).mean[0], 1.0)
    channels = [grey.point(lambda v, c=c: min(255, round(c * v / mean)))
                for c in ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)]
    painted = Image.merge('RGB', channels).convert('RGBA')
    for q, n, w, h in t['levels']:
        buf = io.BytesIO()
        painted.resize((max(4, w), max(4, h)), Image.LANCZOS).save(buf, 'DDS', pixel_format='DXT5')
        new = buf.getvalue()[128:]
        if len(new) < n:
            continue
        for i in range(0, n, 16):  # block = 8 bytes of alpha, then 8 bytes of color
            d[q + i + 8:q + i + 16] = new[i + 8:i + 16]
    return bytes(d)


def paint_hair(texture: bytes, rgb: int) -> bytes:
    """A generic hair textures file painted with rgb (as parts() paints the game's); one that cannot be read stays
    as it is."""
    try:
        return _painted(texture, rgb)
    except (KeyError, ValueError, IndexError, OSError, TypeError, struct.error):
        return texture


def hair_rgb(code) -> int:
    """The color of a haircolorcode (the game's table; an unknown code gets the first)."""
    colors = preview.HAIR_COLORS
    return colors[code] if isinstance(code, int) and 0 <= code < len(colors) else colors[0]


def parts(files, fill, hair_rgb: int) -> dict[str, bytes]:
    """{kind: bytes} of the game's generic parts the fill asks for (hair painted with hair_rgb). {} when the
    fill is empty. FillError: the game has no such file (another game folder than the one the face was filled on)."""
    out: dict[str, bytes] = {}
    for key, code in (fill or {}).items():
        if key == 'eyes':
            paths = {'eyes': EYES_PATH}
        elif key == 'hair':
            paths = HAIR_PATHS
        elif key == 'hairlod' and 'hair' not in fill:
            paths = {'hairlod': HAIR_PATHS['hairlod']}
        else:
            continue
        for kind, path in paths.items():
            data = files.read(path.format(code))
            if data is None:
                raise FillError(f'{key} {code}')
            out[kind] = _painted(data, hair_rgb) if kind == 'hair_textures' else data
    return out


def apply(files, data: dict[str, bytes], fill, hair_rgb: int) -> dict[str, bytes]:
    """The face's files with the fill's parts over them (hair: the three files together, whatever the face had)."""
    return {**data, **parts(files, fill, hair_rgb)}
