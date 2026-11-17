"""Kit fonts: the real ink color of a number font file and the family name of a name font.

teamkits.numbercolor / shortsnumbercolor are palette indexes; the digits come from
data/sceneassets/kitnumbers/kitnumbers_<font>_<color>.rx3 with the color painted in. Some club fonts do not follow the
palette, so the color the file really shows is read from the file itself.
"""
import io

import numpy as np
from PIL import ImageFont

from . import images, rx3

INK_DIGIT = 8  # the digit with the most ink


def ink_color(data: bytes) -> list[int] | None:
    """Main color [r, g, b] of the digits of a kitnumbers file (the most common opaque color, so an outline does not
    count), or None when the file cannot be read."""
    try:
        d = rx3.unpack(data)
        found = rx3.textures(d)
        img = rx3.to_image(d, found[min(INK_DIGIT, len(found) - 1)]).convert('RGBA')
    except images.UNREADABLE:
        return None
    a = np.asarray(img, dtype=np.int32)
    ink = a[..., :3][a[..., 3] > 200]
    if not len(ink):
        return None
    bins = ink // 32
    keys = bins[:, 0] * 64 + bins[:, 1] * 8 + bins[:, 2]
    top = np.bincount(keys).argmax()
    return [int(v) for v in ink[keys == top].mean(axis=0)]


def family_name(data: bytes) -> str | None:
    """The .ttf's own name (family and style), or None."""
    try:
        family, style = ImageFont.truetype(io.BytesIO(data), 12).getname()
    except Exception:  # noqa: BLE001 - any broken font file
        return None
    return ' '.join(p for p in ((family or '').strip(), (style or '').strip()) if p and p != 'Regular') or None
