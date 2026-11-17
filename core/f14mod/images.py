"""Pictures: DDS decoding, kit textures, crest background removal and PNG encoding."""
import io
import struct
import zlib
from collections import deque

import numpy as np
from PIL import Image

from . import chunk, rx3

# what reading a broken or unknown game file raises (Pillow's own errors are OSError / ValueError subclasses)
UNREADABLE = (OSError, ValueError, KeyError, IndexError, struct.error, zlib.error, chunk.ChunkError,
              Image.DecompressionBombError)
KIT_TEXTURES = {'jersey': 'jersey_cm', 'shorts': 'shorts_cm'}


def decode_dds(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as img:
        return img.convert('RGBA')


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def thumbnail(img: Image.Image, size: int) -> Image.Image:
    img = img.copy()
    img.thumbnail((size, size))
    return img


def kit_textures(data: bytes) -> dict[str, Image.Image]:
    """{'jersey': image, 'shorts': image} of a kit RX3 file. A file it cannot read raises one of UNREADABLE."""
    d = rx3.unpack(data)
    return {part: rx3.to_image(d, rx3.by_name(d, name)).convert('RGB') for part, name in KIT_TEXTURES.items()}


def _is_background(px) -> bool:
    r, g, b, a = px
    return a < 16 or (r >= 235 and g >= 235 and b >= 235)


def remove_background(img: Image.Image) -> Image.Image:
    """Makes transparent the light tile drawn around some crests: a flood fill from the borders over near-white or
    transparent pixels; light pixels left touching the cleared area get half their alpha (soft edge)."""
    arr = np.array(img.convert('RGBA'))
    h, w = arr.shape[:2]
    visited = np.zeros((h, w), dtype=bool)
    queue = deque([(0, x) for x in range(w)] + [(h - 1, x) for x in range(w)] +
                  [(y, 0) for y in range(1, h - 1)] + [(y, w - 1) for y in range(1, h - 1)])
    while queue:
        y, x = queue.popleft()
        if visited[y, x]:
            continue
        visited[y, x] = True
        if not _is_background(arr[y, x]):
            continue
        arr[y, x, 3] = 0
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx] and _is_background(arr[ny, nx]):
                queue.append((ny, nx))
    clear = arr[..., 3] == 0
    near = np.zeros_like(clear)
    near[1:, :] |= clear[:-1, :]
    near[:-1, :] |= clear[1:, :]
    near[:, 1:] |= clear[:, :-1]
    near[:, :-1] |= clear[:, 1:]
    light = (arr[..., 0] >= 200) & (arr[..., 1] >= 200) & (arr[..., 2] >= 200)
    edge = near & light & ~clear
    arr[..., 3] = np.where(edge, arr[..., 3] // 2, arr[..., 3])
    return Image.fromarray(arr, 'RGBA')
