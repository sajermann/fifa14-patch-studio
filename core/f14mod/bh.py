"""The .bh index next to each .big archive ('ViV4'): a 16-byte header and one 20-byte record per entry of the .big,
in the same order. The game looks entries up through the two hash words at the end of each record; with them zeroed
it no longer finds the entry in the archive and opens the loose file of the same name under the game folder.
"""
import struct

MAGIC = b'ViV4'
HEADER = 16
RECORD = 20
HASHES = slice(12, 20)  # the two hash words inside a record


class BhError(ValueError):
    """Not a .bh file this reader knows."""


def records(data: bytes) -> int:
    if data[:4] != MAGIC or (len(data) - HEADER) % RECORD:
        raise BhError('not a .bh index')
    return (len(data) - HEADER) // RECORD


def zeroed(data: bytes) -> list[int]:
    """Indexes of the records whose hash words are zero (entries redirected to loose files)."""
    n = records(data)
    empty = bytes(8)
    return [i for i in range(n) if data[HEADER + i * RECORD:HEADER + (i + 1) * RECORD][HASHES] == empty]


def zero(data: bytes, indexes) -> bytes:
    """A copy with the hash words of these records zeroed (offset and size kept)."""
    out = bytearray(data)
    n = records(data)
    for i in indexes:
        if not 0 <= i < n:
            raise IndexError(i)
        start = HEADER + i * RECORD
        out[start + 12:start + 20] = bytes(8)
    return bytes(out)


def entry_count_matches(data: bytes, big_entries: int) -> bool:
    try:
        return records(data) == big_entries
    except BhError:
        return False


def header_count(data: bytes) -> int:
    """The entry count written in the header (big-endian at 8)."""
    return struct.unpack('>I', data[8:12])[0]
