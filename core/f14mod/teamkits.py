"""A team's crest and kits as game files (test TN1, validated in game on 19/11/2026).

Crest: `ui/imgassets/<folder>/l<team>.dds` in 8 folders (crest 256 DXT5, crest50x50 64 DXT5, crest16x16/crest32x32
plain 32-bit, each with a dark/ twin); every file keeps the size and pixel format of the game's own.

Kits: `sceneassets/kit/kit_<team>_<type>_0.rx3` (RX3l, not compressed): crest_cm 128 DXT5, jersey_cm 1024 DXT1,
jersey_coeff, shorts_cm 1024x512 DXT1, shorts_coeff; the minikit `ui/imgassets/kits/j<type>_<team>_0.dds` 256 DXT5.
A kit comes from one of (`config['source']`):
  - 'game'    a kit of a game team, as it is ({'team', 'kind'});
  - 'upload'  the user's jersey and shorts pictures (FIFA 14-16 layout, any size: scaled into the model kit file) and
              optionally a minikit picture; crest_cm is left empty (the picture already has the crest: TN1 A);
  - 'keep'    the kit file stays (the game's, or the default of a created team): only `print`/`collar` change;
  - 'generic' one of the game's mask kits (ids 7500-7799: red = color 1, green = color 2) painted with two colors
              ({'model', 'colors': [[r, g, b], [r, g, b]]}) + the team's crest on crest_cm (TN1 B/C: the game does
              not paint the masks itself).
"""
import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import rx3

KIT_FILE = 'data/sceneassets/kit/kit_{}_{}_0.rx3'  # team, type
MINIKIT = 'data/ui/imgassets/kits/j{}_{}_0.dds'  # type, team
CREST_FOLDERS = ('crest', 'crest/dark', 'crest16x16', 'crest16x16/dark', 'crest32x32', 'crest32x32/dark',
                 'crest50x50', 'crest50x50/dark')
CREST_FILE = 'data/ui/imgassets/{}/l{}.dds'  # folder, team
# 0 home, 1 away, 2 goalkeeper (the only one: the keeper wears it with any kit), 3 third; 4, 5, 7, 8 = more outfield
# kits, all named "Alternate" in the kit selection (tests GK1/GK2); 6 is listed as "undefined" (no name in the game)
KIT_TYPES = (0, 1, 2, 3, 4, 5, 7, 8)
MASKS = range(7500, 7800)  # the game's generic mask kits (kit type 0 files)
DEFAULT_MASKS = {0: 7500, 1: 7600, 3: 7700}  # a team made from scratch: generic kits until the user picks
GENERIC_GOALKEEPER = 5000  # kit_5000_2_0: a plain goalkeeper kit of the game
MODEL_TEAM = 383  # a team whose files exist in every game: model of sizes and formats when the team has none
NAME_FONT = 'data/sceneassets/jerseyfonts/font_{}.ttf'  # name on the back
NUMBER_FONT = 'data/sceneassets/kitnumbers/kitnumbers_{}_{}.rx3'  # font, color (the digits painted in)

# name and numbers of a kit: teamkits columns (every value below is used by the clean game itself, and the Street
# Studio validated the same columns in game). `config['print']` sets them; a value left out keeps the row's.
PRINT = {
    'name_color': ('jerseynamecolorr', 'jerseynamecolorg', 'jerseynamecolorb'),  # [r, g, b]
    'number_color': 'numbercolor',  # palette 0-19 (the kitnumbers_<font>_<color> file)
    'shorts_number_color': 'shortsnumbercolor',
    'front_number': 'jerseyfrontnumberplacementcode',  # 1 = number on the front of the jersey
    'shorts_number': 'shortsnumberplacementcode',  # 1 = number on the shorts
    'show_name': 'jerseybacknameplacementcode',  # 1 = name on the back, 0 = none
    'name_layout': 'jerseynamelayouttype',  # 0 straight, 1 arc
    'name_font': 'jerseynamefonttype',  # jerseyfonts/font_<n>.ttf
    'number_font': 'numberfonttype',  # kitnumbers_<font>_<number_color>.rx3
    'shorts_number_font': 'shortsnumberfonttype',
}
BOOL_PRINT = ('front_number', 'shorts_number', 'show_name')
COLLARS = range(16)  # jerseycollargeometrytype values of the clean game (0-15)


def print_of(row: dict) -> dict:
    """The name-and-numbers values of a teamkits row (as `config['print']` keeps them)."""
    out = {}
    for key, column in PRINT.items():
        if isinstance(column, tuple):
            if all(c in row for c in column):
                out[key] = [row[c] for c in column]
        elif column in row:
            out[key] = bool(row[column]) if key in BOOL_PRINT else row[column]
    if 'jerseycollargeometrytype' in row:
        out['collar'] = row['jerseycollargeometrytype']
    return out


def apply_print(table, row: list, values: dict) -> None:
    """Writes `config['print']` into a teamkits row (a column the table lacks is skipped)."""
    names = {f.name for f in table.fields}
    for key, value in values.items():
        column = PRINT.get(key)
        if column is None or value is None:
            continue
        pairs = zip(column, value) if isinstance(column, tuple) else [(column, int(value))]
        for c, v in pairs:
            if c in names:
                table.set(row, c, int(v))


def _model(files, path_for, team: int, kind: int | None = None) -> bytes:
    """The file of `team` (else of MODEL_TEAM) to copy the layout of; a kit type the team lacks uses its home kit."""
    kinds = [None] if kind is None else list(dict.fromkeys([kind, 0]))
    for t in (team, MODEL_TEAM):
        for k in kinds:
            data = files.read(path_for(t) if k is None else path_for(t, k))
            if data is not None:
                return data
    raise FileNotFoundError(path_for(team) if kind is None else path_for(team, kind))


def dds_like(model: bytes, img: Image.Image) -> bytes:
    """A DDS of img with the model's size and pixel format (DXT1/3/5 or plain 32-bit), no mipmaps."""
    w, h = int.from_bytes(model[16:20], 'little'), int.from_bytes(model[12:16], 'little')
    fmt = {b'DXT1': 'DXT1', b'DXT3': 'DXT3', b'DXT5': 'DXT5'}.get(model[84:88])
    buf = io.BytesIO()
    pic = img.convert('RGBA').resize((w, h), Image.LANCZOS)
    if fmt:
        pic.save(buf, 'DDS', pixel_format=fmt)
    else:
        pic.save(buf, 'DDS')
    return buf.getvalue()


def _encode(img: Image.Image, fmt: int, w: int, h: int) -> bytes:
    """One mip of an RX3l texture (PC: plain DXT data, no byte swap)."""
    if fmt not in rx3.DDS_FOURCC:  # plain 32-bit
        return img.convert('RGBA').resize((w, h), Image.LANCZOS).tobytes('raw', 'BGRA')
    pic = img.convert('RGBA').resize((max(4, w), max(4, h)), Image.LANCZOS)
    buf = io.BytesIO()
    pic.save(buf, 'DDS', pixel_format=rx3.DDS_FOURCC[fmt].decode())
    return buf.getvalue()[128:]


def set_texture(d: bytearray, name: str, img: Image.Image) -> None:
    """Writes img into every mip of the named texture of an RX3l file (same size and format as the file's); a
    texture the file does not have is skipped."""
    try:
        t = rx3.by_name(bytes(d), name)
    except KeyError:
        return
    for q, n, w, h in t['levels']:
        b = _encode(img, t['fmt'], w, h)
        d[q:q + n] = b[:n].ljust(n, b'\0')


MASK_LEVEL = 230.0  # the masks' full red/green (230, 0, 0): a darker one is a shadow of the same color


def paint_mask(img: Image.Image, c1, c2) -> Image.Image:
    """A mask kit picture painted with two RGB colors: each pixel is split into its gray part (white highlights,
    kept), its red part (color 1, as dark as the red), its green part (color 2, likewise) and its blue part (maker
    logos, kept)."""
    a = np.asarray(img.convert('RGB')).astype(np.float32)
    gray = a.min(axis=2, keepdims=True)
    red, green, blue = (np.clip((a[..., i:i + 1] - gray) / MASK_LEVEL, 0, 1) for i in range(3))
    out = gray + red * np.array(c1, dtype=np.float32) + green * np.array(c2, dtype=np.float32)
    out[..., 2:3] += blue * MASK_LEVEL
    return Image.fromarray(np.clip(out, 0, 255).astype('uint8'))


def textures(data: bytes) -> dict[str, Image.Image]:
    d = rx3.unpack(data)
    return {name: rx3.to_image(d, rx3.by_name(d, f'{name}_cm')).convert('RGB') for name in ('jersey', 'shorts')}


EMPTY = Image.new('RGBA', (8, 8), (0, 0, 0, 0))


def kit_file(files, config: dict, kind: int, template: int, crest: Image.Image | None,
             pictures: dict[str, Image.Image]) -> bytes:
    """The kit file of one kit of a team (see the module docstring); `template` = the team whose kit file is the
    model of an uploaded kit; `pictures` = the user's {'jersey', 'shorts'} pictures of this kit."""
    source = config.get('source')
    if source == 'game':
        data = files.read(KIT_FILE.format(config['team'], config.get('kind', kind)))
        if data is None:
            raise FileNotFoundError(KIT_FILE.format(config['team'], config.get('kind', kind)))
        return bytes(rx3.unpack(data))
    if source == 'upload':
        d = bytearray(rx3.unpack(_model(files, KIT_FILE.format, template, kind)))
        for name in ('jersey', 'shorts'):
            if name in pictures:
                set_texture(d, f'{name}_cm', pictures[name])
        set_texture(d, 'crest_cm', EMPTY)
        return bytes(d)
    if source == 'generic':
        model = int(config.get('model', DEFAULT_MASKS.get(kind, 7500)))
        d = bytearray(rx3.unpack(_model(files, KIT_FILE.format, model, 0)))
        c1, c2 = (config.get('colors') or [[255, 255, 255], [0, 0, 0]])[:2]
        for name in ('jersey_cm', 'shorts_cm'):
            t = rx3.by_name(bytes(d), name)
            set_texture(d, name, paint_mask(rx3.to_image(bytes(d), t), c1, c2))
        set_texture(d, 'crest_cm', crest if crest is not None else EMPTY)
        return bytes(d)
    raise ValueError(f'unknown kit source {source!r}')


def minikit(files, config: dict, kind: int, template: int, picture: Image.Image | None) -> bytes:
    """The minikit (kit picture of the menus): the user's picture, the game kit's own, or the model's shirt shape
    tinted with the kit's first color."""
    model = None
    for team in (template, MODEL_TEAM):
        for k in dict.fromkeys([kind, 0]):  # a kit type the team lacks: its home minikit as the model
            model = model or files.read(MINIKIT.format(k, team))
    if picture is not None:
        return dds_like(model, picture)
    from .images import decode_dds
    if config.get('source') == 'game':
        own = files.read(MINIKIT.format(config.get('kind', kind), config['team']))
        if own is not None:
            return own
    if config.get('source') == 'generic':  # the mask has a minikit of its own (red/green too): painted the same way
        mask = files.read(MINIKIT.format(0, int(config.get('model', DEFAULT_MASKS.get(kind, 7500)))))
        if mask is not None:
            c1, c2 = (config.get('colors') or [[255, 255, 255], [0, 0, 0]])[:2]
            pic = decode_dds(mask).convert('RGBA')
            painted = paint_mask(pic.convert('RGB'), c1, c2).convert('RGBA')
            painted.putalpha(pic.getchannel('A'))
            return dds_like(model or mask, painted)
    if model is None:
        model = dds_like(b'DDS ' + bytes(8) + (256).to_bytes(4, 'little') * 2 + bytes(64) + b'DXT5' + bytes(40),
                         Image.new('RGBA', (256, 256), (255, 255, 255, 255)))
    shape = decode_dds(model).convert('RGBA')
    color = (config.get('colors') or [[200, 200, 200]])[0]
    from PIL import ImageFilter
    # the model's shading, blurred so its logos and sponsors do not show through
    gray = np.asarray(shape.convert('L').filter(ImageFilter.GaussianBlur(8))).astype(np.float32)[..., None] / 255.0
    shade = 0.55 + 0.45 * gray  # keep the folds of the model's shirt
    rgb = np.clip(shade * np.array(color, dtype=np.float32), 0, 255).astype('uint8')
    tinted = Image.fromarray(rgb, 'RGB')
    tinted.putalpha(shape.getchannel('A'))
    return dds_like(model, tinted)


def plain_crest(text: str, c1, c2) -> Image.Image:
    """The crest of a team made from scratch without a picture: a shield in its colors with its short name."""
    img = Image.new('RGBA', (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    shield = [(56, 40), (456, 40), (456, 260), (256, 480), (56, 260)]
    d.polygon(shield, fill=tuple(c1) + (255,))
    d.line(shield + [shield[0]], fill=tuple(c2) + (255,), width=18)
    text = (text or '?')[:3]
    try:
        font = ImageFont.truetype('arialbd.ttf', 200 if len(text) <= 2 else 150)
    except OSError:
        font = ImageFont.load_default()
    d.text((256, 230), text, fill=tuple(c2) + (255,), font=font, anchor='mm')
    return img


def crest_files(files, picture: Image.Image, team: int, template: int) -> dict[str, bytes]:
    """{game path: bytes} of the 8 crest files of a team from one picture."""
    out = {}
    for folder in CREST_FOLDERS:
        try:
            model = _model(files, lambda t, f=folder: CREST_FILE.format(f, t), template)
        except FileNotFoundError:
            continue  # a size this game has no model of
        out[CREST_FILE.format(folder, team)] = dds_like(model, picture)
    return out
