"""3D preview of a player wearing a team kit: game meshes as GLB and their textures as PNG.

Files (data/sceneassets/, all RX3l), in the game's reference pose (cm, y up, facing +z):
  head    heads/head_<headtypecode>_1.rx3            meshes 'head' and 'eyes' (generic heads, headclasscode 1)
  face    faces/face_0_1_0_<eyebrowcode>_<sideburnscode>_<facialhaircolorcode>_<facialhairtypecode>_<skintypecode>_
          <skin tone>_textures.rx3: skin of the face, eyebrows and beard baked in (only face type 0 exists; tones 1, 3
          and 7 have no file and use 2, 4 and 8)
  eyes    heads/eyes_<eyecolorcode>_1_textures.rx3
  hair    hair/hair_<hairtypecode>_1_0.rx3 (submeshes alphaA = cap, alphaB = strands) + hair_<code>_1_textures.rx3:
          hair_cm (grey, tinted by the hair color) and hair_coeff (R = cap opacity, B = strands opacity, sampled with
          the 2nd UV set); hairtypecode 0 = bald
  real    a player's own face (headclasscode 0): heads/head_<playerid>_0.rx3, faces/face_<playerid>_0_0_0_0_0_0_0_0_
          textures.rx3, heads/eyes_<playerid>_0_textures.rx3, hair/hair_<playerid>_0_0.rx3 + hair_<playerid>_0_textures
  body    body/jersey_1_<collar>_<sleeve>_0_0_0.rx3 (collar = teamkits.jerseycollargeometrytype 0-15, sleeve 1 =
          long; the last three digits are other cuts of the same jersey), body/arms_1_<sleeve>.rx3 (with long
          sleeves only the hands), body/shorts_1_0.rx3, body/sock_1_<sock length>.rx3 and body/legs_1_<sock length>.rx3,
          shoe/shoe_<shoetypecode>.rx3, gkglove/gkglove_<code>.rx3 (already on the hands)
  skin    body/skin_<tone>_textures.rx3 (arms and legs)
  kit     the kit's jersey_cm and shorts_cm (the socks are mapped on shorts_cm) use the same UVs as the meshes,
          shaded by kit/jersey_<sleeve>_0_textures.rx3 (jersey_am) and kit/shorts_0_0_textures.rx3 (shorts_am).
"""
import io
from functools import lru_cache

from . import gltf, rx3, rx3mesh

ASSETS = 'data/sceneassets/'
CM_TO_M = 0.01
# part -> mesh file (code = the part's appearance code; collar only for the jersey)
MESHES = {
    'head': 'heads/head_{code}_{cls}.rx3',  # cls: 1 generic, 0 a player's own face (code = player id)
    'hair': 'hair/hair_{code}_{cls}_0.rx3',
    'jersey': 'body/jersey_1_{collar}_{code}_0_0_0.rx3',
    'arms': 'body/arms_1_{code}.rx3',
    'shorts': 'body/shorts_1_0.rx3',
    'socks': 'body/sock_1_{code}.rx3',
    'legs': 'body/legs_1_{code}.rx3',
    'shoes': 'shoe/shoe_{code}.rx3',
    'gloves': 'gkglove/gkglove_{code}.rx3',
}
# texture -> (file, texture name or None for the first one, keep alpha)
TEXTURES = {
    'eyes': ('heads/eyes_{code}_{cls}_textures.rx3', None),
    'hair': ('hair/hair_{code}_{cls}_textures.rx3', 'hair_cm'),
    'skin': ('body/skin_{code}_textures.rx3', None),
    'shoe': ('shoe/shoe_{code}_0_textures.rx3', 'shoe_cm'),
    'glove': ('gkglove/gkglove_{code}_textures.rx3', None),
    'jersey-shade': ('kit/jersey_{code}_0_textures.rx3', 'jersey_am'),
    'shorts-shade': ('kit/shorts_0_0_textures.rx3', 'shorts_am'),
}
# hair submesh tag -> hair_coeff channel with its opacity
HAIR_PARTS = {'cap': ('alphaA', 0), 'strands': ('alphaB', 2)}
GENERIC_FACE = 'faces/face_0_1_0_{}_textures.rx3'  # the six codes joined by '_' (face_key)
REAL_FACE = 'faces/face_{}_0_0_0_0_0_0_0_0_textures.rx3'
FACE_CODES = ('eyebrowcode', 'sideburnscode', 'facialhaircolorcode', 'facialhairtypecode', 'skintypecode',
              'skintonecode')
# the hair colors of the game's player script (index = haircolorcode); unknown codes get the first
HAIR_COLORS = (0xEDAC57, 0x0E0E0D, 0xA07741, 0x1F160E, 0xFFD286, 0x6E4D2B, 0x3B2816, 0x683016,
               0xC8C9CF, 0x525355, 0x345A34, 0x263F67)
# the player shown when the squad has nobody to wear the kit
MODEL_LOOK = {'headtypecode': 1, 'hairtypecode': 1, 'haircolorcode': 3, 'eyecolorcode': 1, 'eyebrowcode': 0,
              'sideburnscode': 0, 'facialhaircolorcode': 0, 'facialhairtypecode': 0, 'skintypecode': 0,
              'skintonecode': 4, 'jerseysleevelengthcode': 0, 'socklengthcode': 0, 'shoetypecode': 0,
              'gkglovetypecode': 1, 'headclasscode': 1, 'height': 184}
MODEL_HEIGHT_CM = 183.6  # top of the generic head in the reference pose: the preview scales the player to his height


class PreviewError(LookupError):
    """The game has no such file (or it cannot be read)."""


def _tone(code) -> int:
    return code + 1 if code in (1, 3, 7) else code


def look(files, pid: int | None, raw: dict | None) -> dict:
    """What the 3D preview needs to dress a player (his database row `raw`; None = MODEL_LOOK): head, face and hair
    (his own when the game has his face files: 'real', and head/hair/eyes/face are his id), skin, sleeves, socks,
    boots, gloves (codes the game has no file for become the model's) and the scale of his height."""
    v = {**MODEL_LOOK, **{k: raw[k] for k in MODEL_LOOK if raw and isinstance(raw.get(k), int)}}
    real = (v['headclasscode'] == 0 and pid is not None and files.exists(ASSETS + MESHES['head'].format(code=pid, cls=0))
            and files.exists(ASSETS + REAL_FACE.format(pid)))
    color = HAIR_COLORS[v['haircolorcode']] if 0 <= v['haircolorcode'] < len(HAIR_COLORS) else HAIR_COLORS[0]
    glove = v['gkglovetypecode'] if files.exists(ASSETS + MESHES['gloves'].format(code=v['gkglovetypecode'])) else 1
    return {
        'real': bool(real),
        'head': pid if real else v['headtypecode'],
        # 0 = bald (a real face without hair files too)
        'hair': (pid if files.exists(ASSETS + MESHES['hair'].format(code=pid, cls=0)) else 0) if real else
        v['hairtypecode'],
        'hair_color': '#%06x' % (0x808080 if real else color),  # a real face's hair_cm has its own color
        'eyes': pid if real else v['eyecolorcode'],
        'face': str(pid) if real else face_key(v),
        'skin': v['skintonecode'] if files.exists(ASSETS + TEXTURES['skin'][0].format(code=v['skintonecode'])) else 4,
        'sleeve': 1 if v['jerseysleevelengthcode'] == 1 else 0,
        'socks': v['socklengthcode'] if v['socklengthcode'] in (0, 1, 2) else 0,
        'shoe': v['shoetypecode'] if files.exists(ASSETS + MESHES['shoes'].format(code=v['shoetypecode'])) else 0,
        'glove': glove,
        'scale': round((v['height'] or MODEL_LOOK['height']) / MODEL_HEIGHT_CM, 4),
    }


def face_key(v: dict) -> str:
    return '_'.join(str(_tone(v[k]) if k == 'skintonecode' else v[k]) for k in FACE_CODES)


@lru_cache(maxsize=128)
def face_png(files, key: str) -> bytes:
    """Face texture: a player's own (key = player id) or a generic one (key = face_key); a combination the game does
    not have falls back to the plain face of the same skin tone."""
    parts = key.split('_')
    if not all(p.isdigit() for p in parts) or len(parts) not in (1, 6):
        raise PreviewError(key)
    paths = [REAL_FACE.format(key)] if len(parts) == 1 else \
        [GENERIC_FACE.format(key), GENERIC_FACE.format('_'.join(['0'] * 5 + [parts[5]])), GENERIC_FACE.format('0_0_0_0_0_4')]
    for path in paths:
        if files.exists(ASSETS + path):
            d = _rx3(files, path)
            try:
                return _png(rx3.to_image(d, rx3.textures(d)[0]).convert('RGB'))
            except (KeyError, IndexError, OSError) as e:
                raise PreviewError(f'{path}: {e}')
    raise PreviewError(paths[0])


def _rx3(files, path):
    data = files.read(ASSETS + path)
    if data is None:
        raise PreviewError(path)
    try:
        return rx3.unpack(data)
    except ValueError as e:
        raise PreviewError(f'{path}: {e}')


def _png(img):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _glb_mesh(name, m):
    a = m['attrs']
    out = {'name': name, 'indices': m['indices'],
           'positions': [[c * CM_TO_M for c in p[:3]] for p in a['p0']],
           'uvs': a.get('t0'), 'uvs1': a.get('t1')}
    if 'n0' in a:
        out['normals'] = [[c / n for c in v] if (n := sum(c * c for c in v) ** 0.5) else [0, 1, 0] for v in a['n0']]
    return out


def _node(part, mesh_name):
    """Node name of a submesh: 'eyes' inside a head, 'cap'/'strands' inside hair, else the part."""
    if part == 'head':
        return 'eyes' if 'eyes' in mesh_name else 'head'
    if part == 'hair':
        return next((tag for tag, (sub, _) in HAIR_PARTS.items() if f'_{sub}' in mesh_name), 'cap')
    return part


@lru_cache(maxsize=128)
def mesh_glb(files, part: str, code: int, collar: int = 0, real: bool = False) -> bytes:
    """GLB of one part (nodes named by _node), in meters; real = head/hair of a player's own face (code = his id)."""
    if part not in MESHES:
        raise PreviewError(part)
    d = _rx3(files, MESHES[part].format(code=code, collar=collar, cls=0 if real else 1))
    try:
        meshes = rx3mesh.meshes(d)
    except (ValueError, IndexError, KeyError) as e:  # struct.error is a ValueError
        raise PreviewError(f'{part} {code}: {e}')
    return gltf.write_glb([_glb_mesh(_node(part, m['name']), m) for m in meshes])


@lru_cache(maxsize=128)
def texture_png(files, name: str, code: int, real: bool = False) -> bytes:
    """A texture of the preview as PNG (RGB; 'hair-cap'/'hair-strands' = grey opacity of the hair submesh); real =
    eyes/hair of a player's own face (code = his id)."""
    cls = 0 if real else 1
    if name in ('hair-cap', 'hair-strands'):
        d = _rx3(files, TEXTURES['hair'][0].format(code=code, cls=cls))
        coeff = rx3.to_image(d, rx3.by_name(d, 'hair_coeff')).convert('RGB')
        return _png(coeff.split()[HAIR_PARTS[name[5:]][1]])
    if name not in TEXTURES:
        raise PreviewError(name)
    path, texture = TEXTURES[name]
    d = _rx3(files, path.format(code=code, cls=cls))
    try:
        t = rx3.by_name(d, texture) if texture else rx3.textures(d)[0]
        img = rx3.to_image(d, t)
    except (KeyError, IndexError, OSError) as e:
        raise PreviewError(f'{name} {code}: {e}')
    return _png(img.convert('L' if name.endswith('-shade') else 'RGB'))

