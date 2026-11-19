"""Pictures of the look codes for the Visual card (the same pickers as the Street Studio's).

The game's own Create Player pictures where it has them (data/ui/artassets/createplayer/<folder>/<name>_<n>.big: an
Apt archive with one DDS texture whose top left swatch is the picture), else a front view of the generic head drawn with
the code (facepack.thumbnail):
  haircolorcode        haircolor/color_hair_<code>
  skintonecode         skintone/complexion_<code> (1-10; 0 is an empty silhouette)
  eyecolorcode         eyecolor/eye_<code - 1>
  facialhaircolorcode  facialhaircolor/facial_hair_<code>
  headtypecode         drawn: generic head <code>
  hairtypecode         drawn: model head + hair <code>, in the hair color `variant`
  facialhairtypecode   drawn: model head with beard <code>, in the beard color `variant`
  eyebrowcode          drawn: model head with eyebrows <code>, in the beard color `variant`
"""
import struct

from PIL import Image

from . import facepack, images, preview

READY = {'haircolorcode': ('haircolor/color_hair_{}', 0), 'skintonecode': ('skintone/complexion_{}', 0),
         'eyecolorcode': ('eyecolor/eye_{}', -1), 'facialhaircolorcode': ('facialhaircolor/facial_hair_{}', 0)}
DRAWN = ('headtypecode', 'hairtypecode', 'facialhairtypecode', 'eyebrowcode')
FIELDS = (*DRAWN[:2], 'haircolorcode', *DRAWN[2:], 'facialhaircolorcode', 'eyecolorcode', 'skintonecode')
CREATE_PLAYER = 'data/ui/artassets/createplayer/{}.big'
SIZE = 128
SWATCH = {(256, 128): (18, 3, 117, 102), (512, 256): (40, 0, 280, 240)}  # texture size -> square of the swatch


class ThumbError(LookupError):
    pass


def _big_texture(blob: bytes) -> Image.Image:
    """The DDS texture inside a small Apt archive (BIGF/BIG4, big-endian index)."""
    count = struct.unpack('>I', blob[8:12])[0]
    p = 16
    for _ in range(count):
        offset, size = struct.unpack('>II', blob[p:p + 8])
        p = blob.index(b'\0', p + 8) + 1
        data = blob[offset:offset + size]
        if data[:4] == b'DDS ':
            return images.decode_dds(data)
    raise ThumbError('no texture')


def _ready(files, field: str, code: int) -> Image.Image:
    name, shift = READY[field]
    blob = files.read(CREATE_PLAYER.format(name.format(code + shift)))
    if blob is None:
        raise ThumbError(f'{field} {code}')
    img = _big_texture(blob)
    # the picture is the swatch at the top left of the texture (the rest is the menu's frame); a square of it
    box = SWATCH.get(img.size, (0, 0, img.height, img.height))
    return img.crop(box).convert('RGBA').resize((SIZE, SIZE), Image.LANCZOS)


def _face_texture(files, codes: dict) -> bytes:
    """The generic face texture file of these codes (a combination the game lacks: the plain face of the tone)."""
    look = {**preview.MODEL_LOOK, **codes}
    key = preview.face_key(look)
    for k in (key, '_'.join(['0'] * 5 + [key.split('_')[-1]]), '0_0_0_0_0_4'):
        data = files.read(preview.ASSETS + preview.GENERIC_FACE.format(k))
        if data is not None:
            return data
    raise ThumbError('no generic face')


def _drawn(files, field: str, code: int, variant: int) -> Image.Image:
    a, look = preview.ASSETS, dict(preview.MODEL_LOOK)
    head, hair, color = look['headtypecode'], None, look['haircolorcode']
    codes = {}
    if field == 'headtypecode':
        head = code
    elif field == 'hairtypecode':
        hair, color = code, variant
    elif field == 'facialhairtypecode':
        codes = {'facialhairtypecode': code, 'facialhaircolorcode': variant}
    elif field == 'eyebrowcode':
        codes = {'eyebrowcode': code, 'facialhaircolorcode': variant}
    data = {'head': files.read(a + preview.MESHES['head'].format(code=head, cls=1)),
            'face': _face_texture(files, codes),
            'eyes': files.read(a + preview.TEXTURES['eyes'][0].format(code=1, cls=1))}
    if hair:
        data['hair'] = files.read(a + preview.MESHES['hair'].format(code=hair, cls=1))
        data['hair_textures'] = files.read(a + preview.TEXTURES['hair'][0].format(code=hair, cls=1))
    if data['head'] is None:
        raise ThumbError(f'{field} {code}')
    rgb = preview.HAIR_COLORS[color] if 0 <= color < len(preview.HAIR_COLORS) else preview.HAIR_COLORS[0]
    png = facepack.thumbnail({k: v for k, v in data.items() if v is not None}, SIZE,
                             hair_rgb=((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255))
    return images.decode_png(png)


def thumbnail(files, field: str, code: int, variant: int = 0) -> Image.Image:
    """The picture of one value of a look code (RGBA, SIZE pixels); raises ThumbError when there is none."""
    if field in READY:
        return _ready(files, field, code)
    if field in DRAWN:
        try:
            return _drawn(files, field, code, variant)
        except images.UNREADABLE as e:
            raise ThumbError(f'{field} {code}: {e}') from e
    raise ThumbError(field)
