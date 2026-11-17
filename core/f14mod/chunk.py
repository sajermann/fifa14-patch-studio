"""EA chunked containers: 'chunkzip' (raw deflate chunks) and 'chunkref' (RefPack chunks).

Layout: 8-byte magic, big-endian header with the total unpacked size at 12, chunks from 0x28 on, each one
`size (u32 BE), kind (u32 BE), data`, aligned to 8 bytes. kind 0 = stored, 1 = deflate, 2 = RefPack.
"""
import struct
import zlib

MAGICS = (b'chunkzip', b'chunkref')
HEADER = 0x28


class ChunkError(ValueError):
    """A damaged or unknown container."""


def is_chunked(data: bytes) -> bool:
    return data[:8] in MAGICS


def refpack(src: bytes) -> bytes:
    """Decodes one RefPack (QFS) stream."""
    if len(src) < 5 or src[1] != 0xFB:
        raise ChunkError('not a RefPack stream')
    flags = src[0]
    width = 4 if flags & 0x80 else 3
    pos = 2 + (width if flags & 0x01 else 0)
    size = int.from_bytes(src[pos:pos + width], 'big')
    pos += width
    out = bytearray()
    n = len(src)
    while pos < n and len(out) < size:
        b0 = src[pos]
        if b0 < 0x80:
            b1 = src[pos + 1]
            plain, length, offset = b0 & 3, ((b0 & 0x1C) >> 2) + 3, ((b0 & 0x60) << 3) + b1 + 1
            pos += 2
        elif b0 < 0xC0:
            b1, b2 = src[pos + 1], src[pos + 2]
            plain, length, offset = b1 >> 6, (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1
            pos += 3
        elif b0 < 0xE0:
            b1, b2, b3 = src[pos + 1], src[pos + 2], src[pos + 3]
            plain = b0 & 3
            length = ((b0 & 0x0C) << 6) + b3 + 5
            offset = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            pos += 4
        elif b0 < 0xFC:
            plain, length, offset = ((b0 & 0x1F) << 2) + 4, 0, 0
            pos += 1
        else:
            plain, length, offset = b0 & 3, 0, 0
            pos += 1
            out += src[pos:pos + plain]
            break
        out += src[pos:pos + plain]
        pos += plain
        if length:
            start = len(out) - offset
            if start < 0:
                raise ChunkError('RefPack offset before the start')
            for i in range(length):
                out.append(out[start + i])
    return bytes(out[:size])


def decode(data: bytes) -> bytes:
    """The unpacked file of a chunked container (anything else is returned as is)."""
    if not is_chunked(data):
        return data
    try:
        total = struct.unpack('>I', data[12:16])[0]
        pos, out = HEADER, bytearray()
        while len(out) < total:
            size, kind = struct.unpack('>II', data[pos:pos + 8])
            chunk = data[pos + 8:pos + 8 + size]
            if len(chunk) < size:
                raise ChunkError('truncated chunk')
            if kind == 0:
                out += chunk
            elif kind == 1:
                out += zlib.decompress(chunk, -15)
            elif kind == 2:
                out += refpack(chunk)
            else:
                raise ChunkError(f'unknown chunk kind {kind}')
            pos = (pos + 8 + size + 7) // 8 * 8
        return bytes(out[:total])
    except (struct.error, zlib.error, IndexError) as e:
        raise ChunkError(f'damaged container ({e})') from e
