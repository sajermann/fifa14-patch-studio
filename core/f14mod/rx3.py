"""Read-only RX3 files (RX3l little-endian, RX3b big-endian): texture list, texture to image, kit print positions."""
import io
import re
import struct

from PIL import Image

from . import chunk

TEXTURE_SECTION, NAMES_SECTION = 0x7A0B60DA, 0x4C9B9EB2
POSITIONS_SECTION = 0xF55B1A1A  # kit files: where the crest, numbers and name go (u0, v0, u1, v1 per rectangle)
DDS_FOURCC = {0: b'DXT1', 1: b'DXT3', 2: b'DXT5'}
# file order of the rectangles of the position table ('team' = the crest: on the jersey, then on the shorts)
POSITION_NAMES = ('team', 'numberback', 'numberfront', 'name', 'name_arccenter', 'name_arctangent', 'team', 'number')


def unpack(d: bytes) -> bytes:
    """The RX3 itself (a chunked container is unpacked); anything else raises ValueError."""
    d = chunk.decode(d)
    if d[:4] not in (b'RX3l', b'RX3b'):
        raise ValueError(f'not an RX3 file ({d[:8]!r})')
    return d


def _swap16(b: bytes) -> bytes:
    a = bytearray(len(b))
    a[0::2] = b[1::2]
    a[1::2] = b[0::2]
    return bytes(a)


def _endian(d: bytes) -> str:
    return '<' if d[:4] == b'RX3l' else '>'


def _sections(d: bytes):
    e = _endian(d)
    n = struct.unpack(e + 'I', d[12:16])[0]
    for i in range(n):
        yield struct.unpack(e + 'IIII', d[16 + 16 * i:32 + 16 * i])


def names(d: bytes) -> list[str]:
    e = _endian(d)
    for type_, off, _, _ in _sections(d):
        if type_ == NAMES_SECTION:
            count = struct.unpack(e + 'I', d[off + 4:off + 8])[0]
            p, out = off + 16, []
            for _ in range(count):
                length = struct.unpack(e + 'I', d[p + 4:p + 8])[0]
                out.append(d[p + 8:p + 8 + length].split(b'\0')[0].decode(errors='replace').replace('.Raster', ''))
                p += 8 + length
            return out
    return []


def textures(d: bytes) -> list[dict]:
    e = _endian(d)
    out = []
    for type_, off, size, _ in _sections(d):
        if type_ != TEXTURE_SECTION:
            continue
        _, _, fmt, _, _, w, h, _, mips = struct.unpack(e + 'IBBBBHHHH', d[off:off + 16])
        levels, q = [], off + 16
        for m in range(mips):
            if q + 16 > off + size:
                break
            _, _, mip_size, _ = struct.unpack(e + 'IIII', d[q:q + 16])
            if q + 16 + mip_size > off + size:
                break
            levels.append((q + 16, mip_size, max(1, w >> m), max(1, h >> m)))
            q += 16 + mip_size
        out.append(dict(off=off, size=size, fmt=fmt, w=w, h=h, mips=len(levels), levels=levels))
    for t, name in zip(out, names(d)):
        t['name'] = name
    return out


def by_name(d: bytes, name: str) -> dict:
    for t in textures(d):
        if t.get('name') == name:
            return t
    raise KeyError(name)


def to_image(d: bytes, t: dict, level: int = 0) -> Image.Image:
    q, n, w, h = t['levels'][level]
    raw = d[q:q + n]
    little = _endian(d) == '<'
    if t['fmt'] in DDS_FOURCC:
        swapped = raw if little else _swap16(raw)
        bw, bh = max(4, w), max(4, h)
        hdr = (b'DDS ' + struct.pack('<7I', 124, 0x1007, bh, bw, len(swapped), 0, 1) + b'\0' * 44 +
               struct.pack('<2I4s5I', 32, 4, DDS_FOURCC[t['fmt']], 0, 0, 0, 0, 0) +
               struct.pack('<5I', 0x1000, 0, 0, 0, 0))
        return Image.open(io.BytesIO(hdr + swapped)).crop((0, 0, w, h))
    return Image.frombytes('RGBA', (w, h), raw[:w * h * 4], 'raw', 'BGRA' if little else 'ARGB')


def positions(d: bytes):
    """The kit's position table as 8 [u0, v0, u1, v1] lists (POSITION_NAMES order), or None when the file has no
    table or one of another shape."""
    e = _endian(d)
    found = next(((off, size) for t, off, size, _ in _sections(d) if t == POSITIONS_SECTION), None)
    if found is None:
        return None
    off, size = found
    p, end, found_names, rects = off + 16, off + size, [], []
    while p < end:
        m = re.match(rb'([a-z_]+)\0', d[p:end])
        if not m:
            break
        name = m.group(1).decode()
        p += len(m.group(0))
        if name in ('jersey', 'shorts'):
            p += 1  # entry count
            continue
        found_names.append(name)
        rects.append([round(v, 6) for v in struct.unpack(e + '4f', d[p:p + 16])])
        p += 16
    return rects if tuple(found_names) == POSITION_NAMES else None
