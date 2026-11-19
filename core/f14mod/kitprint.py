"""Crest, name and numbers of a kit, for the 3D preview (the game draws them itself at run time).

Where: the position table of the kit file (rx3.positions: u0, v0, u1, v1 per rectangle; u0 > u1 / v0 > v1 = the
rectangle is mirrored, as the back of the jersey is upside down in the texture): 'team' = the crest (on the jersey,
then on the shorts), 'numberback', 'numberfront', 'name' (+ 'name_arccenter'/'name_arctangent' for the arc) and the
shorts' 'number'.
What: the crest is the kit file's own crest_cm; the numbers are 10 textures per font and color
(sceneassets/kitnumbers/kitnumbers_<font>_<color>.rx3, one image per digit); the name is drawn with a TrueType font
(sceneassets/jerseyfonts/font_<n>.ttf) in the RGB name color, straight (jerseynamelayouttype 0) or in an arc (1). The
arc is an approximation: a circle around name_arccenter whose radius is ARC_RADIUS_FACTOR times its distance to
name_arctangent, each letter kept as wide as when straight.
"""
import io
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from . import rx3
from .teamkits import NAME_FONT, NUMBER_FONT

TRACKING = 0.2  # gap between the letters, in average letter widths
MAX_STRETCH = 1.8  # a short name is widened up to this much to fill the rectangle
ARC_RADIUS_FACTOR = 2.0
CELL = 128  # a digit's cell when two digits are put side by side


def rects(d: bytes) -> dict:
    """{rectangle name: (u0, v0, u1, v1)} of a kit file; the crest is 'team' (jersey) and 'shorts_team'. Empty when
    the file has no table."""
    found = rx3.positions(d)
    if not found:
        return {}
    names = list(rx3.POSITION_NAMES)
    names[6] = 'shorts_team'
    return {n: tuple(r) for n, r in zip(names, found)}


def crest(d: bytes) -> Image.Image | None:
    """The kit file's crest_cm (what the game draws in the 'team' rectangles), or None."""
    try:
        return rx3.to_image(d, rx3.by_name(d, 'crest_cm')).convert('RGBA')
    except (KeyError, IndexError, OSError, ValueError):
        return None


@lru_cache(maxsize=32)
def digits(files, font: int, color: int):
    """The 10 digit images (RGBA) of a number font and palette color, or None when the game has no such file."""
    data = files.read(NUMBER_FONT.format(font, color))
    if data is None:
        return None
    try:
        d = rx3.unpack(data)
        found = rx3.textures(d)[:10]
        return [rx3.to_image(d, t).convert('RGBA') for t in found] if len(found) == 10 else None
    except (KeyError, IndexError, OSError, ValueError):
        return None


@lru_cache(maxsize=16)
def font_bytes(files, font: int) -> bytes | None:
    return files.read(NAME_FONT.format(font))


def _box(rect, size):
    """Pixel box (left, top, right, bottom) and mirroring (flip_x, flip_y) of a UV rectangle on a texture."""
    w, h = size
    u0, v0, u1, v1 = rect
    box = (round(min(u0, u1) * w), round(min(v0, v1) * h), round(max(u0, u1) * w), round(max(v0, v1) * h))
    return box, u0 > u1, v0 > v1


def _paste(img, layer, box, flip_x, flip_y):
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        return
    if flip_x:
        layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
    if flip_y:
        layer = layer.transpose(Image.FLIP_TOP_BOTTOM)
    img.alpha_composite(layer.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS), box[:2])


def draw_crest(img, rect, picture):
    """The crest fitted in its rectangle (kept square, centered)."""
    box, flip_x, flip_y = _box(rect, img.size)
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 2 or h < 2:
        return
    side = min(w, h)
    left, top = box[0] + (w - side) // 2, box[1] + (h - side) // 2
    _paste(img, picture.convert('RGBA'), (left, top, left + side, top + side), flip_x, flip_y)


def draw_number(img, rect, number, glyphs):
    """A 1-2 digit number in a UV rectangle: each digit takes half of its width (one digit is centered)."""
    box, flip_x, flip_y = _box(rect, img.size)
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return
    text = str(number)[-2:]
    layer = Image.new('RGBA', (CELL * 2, CELL), (0, 0, 0, 0))
    x = (2 - len(text)) * CELL // 2
    for ch in text:
        layer.alpha_composite(glyphs[int(ch)].resize((CELL, CELL), Image.LANCZOS), (x, 0))
        x += CELL
    _paste(img, layer, box, flip_x, flip_y)


def draw_name(img, rect, name, font_data, color, arc=None):
    """A name in a UV rectangle, letters as tall as the rectangle, widened to fill its width (up to MAX_STRETCH; a
    long name is narrowed to fit). arc = (name_arccenter, name_arctangent): the name bends around the center."""
    box, flip_x, flip_y = _box(rect, img.size)
    w, h = box[2] - box[0], box[3] - box[1]
    if w < 2 or h < 2 or not name:
        return
    scale = 4  # drawn bigger, then reduced
    font = ImageFont.truetype(io.BytesIO(font_data), h * scale)
    top, bottom = font.getbbox(name)[1], font.getbbox(name)[3]
    widths = [font.getlength(c) for c in name]
    gap = TRACKING * sum(widths) / len(name)
    text_w = max(1, round(sum(widths) + gap * (len(name) - 1)))
    line = Image.new('RGBA', (text_w, max(1, bottom - top)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(line)
    x = 0.0
    spans = []
    for c, cw in zip(name, widths):
        draw.text((x, -top), c, font=font, fill=(*color, 255))
        spans.append((x, x + cw))
        x += cw + gap
    fit_w = min(round(text_w * MAX_STRETCH), w * scale)
    line = line.resize((fit_w, h * scale), Image.LANCZOS)
    radius = _arc_radius(arc, img.size) * scale if arc else 0
    if radius < h * scale:  # straight (or a radius too small to bend around)
        layer = Image.new('RGBA', (w * scale, h * scale), (0, 0, 0, 0))
        layer.alpha_composite(line, ((layer.width - line.width) // 2, 0))
        _paste(img, layer, box, flip_x, flip_y)
        return
    _paste_arc(img, line, [(a * fit_w / text_w, b * fit_w / text_w) for a, b in spans], radius, box, w * scale,
               h * scale, flip_x, flip_y)


def _arc_radius(arc, size):
    center, tangent = arc
    if not any(center) or not any(tangent):
        return 0
    return ARC_RADIUS_FACTOR * math.hypot((tangent[0] - center[0]) * size[0], (tangent[1] - center[1]) * size[1])


def _paste_arc(img, line, spans, radius, box, w, h, flip_x, flip_y):
    """The name bent on a circle (the middle highest, the ends lower and turned outwards); the layer grows down by
    the bend, past the rectangle."""
    mid = line.width / 2
    letters = []
    lowest = 0.0
    for a, b in spans:
        theta = ((a + b) / 2 - mid) / radius
        x = radius * math.sin(theta)
        drop = radius * (1 - math.cos(theta))
        piece = line.crop((max(0, math.floor(a)), 0, min(line.width, math.ceil(b)), line.height))
        piece = piece.rotate(-math.degrees(theta), resample=Image.BICUBIC, expand=True)
        letters.append((piece, x, drop))
        lowest = max(lowest, drop + piece.height / 2)
    extra = max(0, math.ceil(lowest + h / 2 - h))
    layer = Image.new('RGBA', (w, h + extra), (0, 0, 0, 0))
    for piece, x, drop in letters:
        px = round(w / 2 + x - piece.width / 2)
        py = round(h / 2 + drop - piece.height / 2)
        layer.alpha_composite(piece, (max(0, px), max(0, py)), (max(0, -px), max(0, -py)))
    grow = round(extra * (box[3] - box[1]) / h)
    bigger = (box[0], box[1] - grow, box[2], box[3]) if flip_y else (box[0], box[1], box[2], box[3] + grow)
    _paste(img, layer, bigger, flip_x, flip_y)


def decal(files, kit: bytes | None, part: str, size: tuple[int, int], values: dict, *, number=None, name=None,
          crest_picture: Image.Image | None = None) -> Image.Image:
    """Transparent RGBA picture with the same UVs as the kit's jersey ('jersey') or shorts ('shorts') texture, with
    what the game draws over it: the crest, the name and the numbers. kit = the kit file (its position table and
    crest_cm; None = nothing to place); values = the kit's name and numbers (teamkits.PRINT keys); crest_picture
    replaces the file's crest_cm (None = the file's)."""
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    if kit is None:
        return img
    d = rx3.unpack(kit)
    where = rects(d)
    if not where:
        return img
    picture = crest_picture if crest_picture is not None else crest(d)
    if part == 'jersey':
        if picture is not None and 'team' in where:
            draw_crest(img, where['team'], picture)
        glyphs = digits(files, int(values.get('number_font', 0)), int(values.get('number_color', 0))) \
            if number is not None else None
        if glyphs:
            draw_number(img, where['numberback'], number, glyphs)
            if values.get('front_number'):
                draw_number(img, where['numberfront'], number, glyphs)
        if name and values.get('show_name', True):
            data = font_bytes(files, int(values.get('name_font', 0)))
            if data:
                arc = (where['name_arccenter'], where['name_arctangent']) if values.get('name_layout') == 1 else None
                try:
                    draw_name(img, where['name'], name.upper(), data, tuple(values.get('name_color') or (255,) * 3),
                              arc)
                except OSError:  # a font file Pillow cannot read
                    pass
    else:
        if picture is not None and 'shorts_team' in where:
            draw_crest(img, where['shorts_team'], picture)
        if values.get('shorts_number') and number is not None:
            glyphs = digits(files, int(values.get('shorts_number_font', 0)), int(values.get('shorts_number_color', 0)))
            if glyphs:
                draw_number(img, where['number'], number, glyphs)
    return img
