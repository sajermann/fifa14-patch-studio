"""BIG4/BIGF archives: a header with the file count, then one `offset, size (u32 BE), name\\0` per file.

Reading is on demand. `rebuild` writes the same archive with some entries replaced, keeping the order of the
entries, the bytes between the index and the first file and the data alignment of the original."""
import os
import struct

MAGICS = (b'BIG4', b'BIGF')


class BigError(ValueError):
    """Not an archive this reader knows."""


class BigArchive:
    """Index of one archive; entries are read on demand (names normalized: lower case, '/' separators)."""

    def __init__(self, path: str):
        self.path = path
        self.name = os.path.basename(path)
        self.entries: dict[str, tuple[int, int]] = {}
        self.order: list[str] = []  # normalized names in index order (the order of the .bh records)
        self.raw_names: list[str] = []  # names as written in the index
        with open(path, 'rb') as f:
            head = f.read(16)
            if len(head) < 16 or head[:4] not in MAGICS:
                raise BigError(f'{self.name}: not a BIG archive')
            count, header_size = struct.unpack('>II', head[8:16])
            data = f.read(max(0, header_size - 16) + 512)
        self.header_size = header_size
        p = 0
        try:
            for _ in range(count):
                offset, size = struct.unpack('>II', data[p:p + 8])
                end = data.index(b'\0', p + 8)
                name = data[p + 8:end].decode('latin1')
                p = end + 1
                key = normalize(name)
                self.entries[key] = (offset, size)
                self.order.append(key)
                self.raw_names.append(name)
        except (struct.error, ValueError) as e:
            raise BigError(f'{self.name}: damaged index ({e})') from e

    def read(self, name: str) -> bytes | None:
        """Raw bytes of an entry (still packed when the archive keeps it packed), or None."""
        found = self.entries.get(normalize(name))
        if found is None:
            return None
        offset, size = found
        with open(self.path, 'rb') as f:
            f.seek(offset)
            return f.read(size)

    def alignment(self) -> int:
        """Data alignment of the archive (64 when every entry starts on 64 bytes, else 1)."""
        offsets = [o for o, s in self.entries.values() if s]
        return 64 if offsets and all(o % 64 == 0 for o in offsets) else 1


def rebuild(path: str, replace: dict[str, bytes]) -> bytes:
    """The archive at `path` with the entries in `replace` ({game path: bytes}) swapped; the rest is copied."""
    big = BigArchive(path)
    replace = {normalize(k): v for k, v in replace.items()}
    unknown = set(replace) - set(big.entries)
    if unknown:
        raise KeyError(f'{big.name}: entries not in the archive: {sorted(unknown)}')
    align = big.alignment()
    with open(path, 'rb') as f:
        raw = f.read()
    first = min((o for o, _ in big.entries.values()), default=len(raw))
    out = bytearray(raw[:first])
    p = 16
    for key, name in zip(big.order, big.raw_names):
        data = replace.get(key)
        if data is None:
            o, s = big.entries[key]
            data = raw[o:o + s]
        out += b'\0' * (-len(out) % align)
        struct.pack_into('>II', out, p, len(out), len(data))
        p += 8 + len(name.encode('latin1')) + 1
        out += data
    out += b'\0' * (-len(out) % align)
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out)


def normalize(path: str) -> str:
    return path.replace('\\', '/').lstrip('/').lower()
