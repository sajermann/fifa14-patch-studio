"""Editable T3DB database of FIFA PC (little-endian): read every table, change rows, write it back with every CRC.

Layout:
  0x18-byte header + catalog (8 bytes per table: short name, offset) + catalog CRC + tables.
  Table: 0x24-byte header | N field descriptors (16 bytes) | records | string area | padding | CRC.
  Records: little-endian integers, fields LSB-first from the descriptor's bit offset.
  Field types: 0 = fixed string (depth bits), 3 = integer (raw value; real value = raw + the meta's range low),
               4 = float32, 13/14 = string in the string area (the field holds a 32-bit offset, 0xFFFFFFFF = empty;
               13 = 1-byte length prefix, 14 = 2-byte length prefix, both big-endian).
  Huffman string area (table flag 0x40): tree (4-byte nodes, two 2-byte children: (index, 0) = inner node,
  (0, byte) = leaf) followed by the strings, [length][bits MSB-first, padded to a byte].
  CRCs (CRC-32/MPEG-2): database header db[0:0x14] at 0x14; the catalog right after it; per table its header
  table[0:0x20] at 0x20 and its body table[0x24:end-4] in the last 4 bytes.

Reading and writing an unchanged database gives the same bytes. A string with a character the table's Huffman tree
cannot encode makes the table get a new tree built from all of its strings.
"""
import heapq
import itertools
import struct
import zlib

STRING_TYPES = (13, 14)

# ---- CRC-32/MPEG-2: zlib's CRC-32 with mirrored bits (fast) ----------------------------------------------------

_MIRROR = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))


def _mirror32(value):
    return int.from_bytes(value.to_bytes(4, 'big').translate(_MIRROR)[::-1], 'big')


def crc32_mpeg2(data, crc=0xFFFFFFFF):
    register = zlib.crc32(bytes(data).translate(_MIRROR), _mirror32(crc) ^ 0xFFFFFFFF)
    return _mirror32(register ^ 0xFFFFFFFF)


# ---- bits -------------------------------------------------------------------------------------------------------

def get_bits(buf, bitpos, n):
    start, end = bitpos >> 3, (bitpos + n + 7) >> 3
    if end > len(buf):
        raise IndexError(f'bits {bitpos}+{n} are outside the buffer')
    return (int.from_bytes(buf[start:end], 'little') >> (bitpos & 7)) & ((1 << n) - 1)


def set_bits(buf, bitpos, n, v):
    start, end = bitpos >> 3, (bitpos + n + 7) >> 3
    if end > len(buf):
        raise IndexError(f'bits {bitpos}+{n} are outside the buffer')
    shift = bitpos & 7
    mask = ((1 << n) - 1) << shift
    current = int.from_bytes(buf[start:end], 'little')
    buf[start:end] = ((current & ~mask) | ((v << shift) & mask)).to_bytes(end - start, 'little')


# ---- strings ------------------------------------------------------------------------------------------------------

class Huffman:
    def __init__(self, tree: bytes):
        self.tree = tree
        self.exact_padding = False  # some tools pad a string that fills whole bytes without the extra byte
        self.nodes = [(tree[4 * i:4 * i + 2], tree[4 * i + 2:4 * i + 4]) for i in range(len(tree) // 4)]
        self.codes: dict[int, str] = {}
        self._walk(0, '')
        self._code_sizes = {c: len(code) for c, code in self.codes.items()}
        self._byte_steps: dict = {}

    @classmethod
    def from_texts(cls, texts) -> 'Huffman':
        """A tree for these strings (breadth-first node order: the root is node 0)."""
        freq: dict[int, int] = {}
        for t in texts:
            for b in t:
                freq[b] = freq.get(b, 0) + 1
        for filler in (ord('a'), ord('b')):  # a tree needs at least two leaves
            freq.setdefault(filler, 0)
        order = itertools.count()
        heap = [(f, next(order), b) for b, f in freq.items()]
        heapq.heapify(heap)
        while len(heap) > 1:
            f1, _, a = heapq.heappop(heap)
            f2, _, b = heapq.heappop(heap)
            heapq.heappush(heap, (f1 + f2, next(order), (a, b)))
        nodes, queue, index = [], [heap[0][2]], {}
        index[id(heap[0][2])] = 0
        while queue:
            node = queue.pop(0)
            entries = []
            for child in node:
                if isinstance(child, int):
                    entries.append(bytes((0, child)))
                else:
                    index[id(child)] = len(index)
                    entries.append(bytes((index[id(child)], 0)))
                    queue.append(child)
            nodes.append(b''.join(entries))
        assert len(index) < 256  # at most 256 leaves: node indexes fit the entry's first byte
        return cls(b''.join(nodes))

    def _child(self, entry: bytes):
        """(leaf byte, None) or (None, node index)."""
        if entry[1] != 0 or entry[0] == 0:
            return entry[1], None
        return None, entry[0]

    def _walk(self, idx, prefix):
        for bit, e in (('0', self.nodes[idx][0]), ('1', self.nodes[idx][1])):
            leaf, node = self._child(e)
            if node is None:
                self.codes[leaf] = prefix + bit
            else:
                self._walk(node, prefix + bit)

    @staticmethod
    def tree_size(area: bytes):
        """Tree length in bytes = (highest referenced node index + 1) * 4."""
        seen, stack, highest = set(), [0], 0
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            highest = max(highest, i)
            for e in (area[4 * i:4 * i + 2], area[4 * i + 2:4 * i + 4]):
                if e[1] == 0 and e[0] != 0:
                    stack.append(e[0])
        return (highest + 1) * 4

    def _byte_step(self, key):
        cur, byte = key >> 8, key & 0xFF
        out = bytearray()
        for shift in range(7, -1, -1):
            leaf, node = self._child(self.nodes[cur][(byte >> shift) & 1])
            if node is None:
                out.append(leaf)
                cur = 0
            else:
                cur = node
        step = self._byte_steps[key] = (bytes(out), cur)
        return step

    def decode(self, area, off, prefix_len=1):
        """(string, bytes used)."""
        n = int.from_bytes(area[off:off + prefix_len], 'big')
        pos, cur, have, parts = off + prefix_len, 0, 0, []
        steps = self._byte_steps
        while have < n:
            key = cur << 8 | area[pos]
            pos += 1
            chars, cur = steps.get(key) or self._byte_step(key)
            parts.append(chars)
            have += len(chars)
        return b''.join(parts)[:n], pos - off

    def missing_chars(self, s: bytes):
        return sorted({c for c in s if c not in self.codes})

    def nbits(self, s: bytes):
        return sum(map(self._code_sizes.__getitem__, s))

    def encode(self, s: bytes, prefix_len=1):
        bits = ''.join(map(self.codes.__getitem__, s))
        # EA's encoder writes nbits // 8 + 1 bytes (always at least one padding bit)
        bits += '0' * (-len(bits) % 8 if self.exact_padding else 8 - len(bits) % 8)
        return len(s).to_bytes(prefix_len, 'big') + (int(bits, 2).to_bytes(len(bits) // 8, 'big') if bits else b'')


class PlainStrings:
    """Uncompressed string area: [length][bytes]."""
    tree = b''

    @staticmethod
    def decode(area, off, prefix_len=1):
        n = int.from_bytes(area[off:off + prefix_len], 'big')
        return bytes(area[off + prefix_len:off + prefix_len + n]), n + prefix_len

    @staticmethod
    def missing_chars(s: bytes):
        return []

    @staticmethod
    def encode(s: bytes, prefix_len=1):
        return len(s).to_bytes(prefix_len, 'big') + s


# ---- tables -----------------------------------------------------------------------------------------------------

class Field:
    __slots__ = ('type', 'bitoff', 'short', 'depth', 'name', 'rangelow')

    def __init__(self, type_, bitoff, short, depth):
        self.type, self.bitoff, self.short, self.depth = type_, bitoff, short, depth
        self.name, self.rangelow = short, 0


class Table:
    def __init__(self, short: str, raw: bytes, meta: dict | None = None):
        """meta: the reader's {table short: (table name, {field short: (field name, range low)})}."""
        self.short = short
        (self.flags, self.rec_size, self.rec_bits, strsz, nvalid, nrec, self.unk14,
         nfields) = struct.unpack('<IIIIHHIB', raw[:0x19])
        self.hdr_rest = raw[0x19:0x20]
        self.name = short
        self.fields: list[Field] = []
        for k in range(nfields):
            t, bo, sn, dp = struct.unpack('<II4sI', raw[0x24 + 16 * k:0x34 + 16 * k])
            self.fields.append(Field(t, bo, sn.decode('latin1'), dp))
        if meta and short in meta:
            self.name, meta_fields = meta[short]
            for f in self.fields:
                if f.short in meta_fields:
                    f.name, f.rangelow = meta_fields[f.short]
        self.nvalid = nvalid
        p = 0x24 + 16 * nfields
        recs = raw[p:p + self.rec_size * nrec]
        area = raw[p + self.rec_size * nrec:p + self.rec_size * nrec + strsz]
        self.huff = None
        if any(f.type in STRING_TYPES for f in self.fields):
            self.huff = Huffman(area[:Huffman.tree_size(area)]) if self.flags & 0x40 else PlainStrings()
        self.records: list[list] = []
        self.raw_records: list[bytes] = []  # original bytes (keeps the bits outside every field)
        self.nrec_orig = nrec
        seen_offsets: dict = {}
        decoded: dict = {}
        self.shared_strings = False  # rows pointing at the same string (some tools write them so)
        for r in range(nrec):
            rb = recs[r * self.rec_size:(r + 1) * self.rec_size]
            self.raw_records.append(rb)
            row = []
            for f in self.fields:
                if f.type in STRING_TYPES:
                    off = get_bits(rb, f.bitoff, 32)
                    if off == 0xFFFFFFFF:
                        row.append(None)
                        continue
                    self.shared_strings |= seen_offsets.setdefault(off, (r, f.short)) != (r, f.short)
                    key = (off, 2 if f.type == 14 else 1)
                    if key not in decoded:
                        decoded[key] = self.huff.decode(area, *key)
                    row.append(decoded[key][0])
                elif f.type == 0:
                    row.append(rb[f.bitoff // 8:(f.bitoff + f.depth) // 8])
                else:
                    row.append(get_bits(rb, f.bitoff, 32 if f.type == 4 else f.depth))
            self.records.append(row)
        if isinstance(self.huff, Huffman):
            self.huff.exact_padding = self._detect_exact_padding(decoded)

    def _detect_exact_padding(self, decoded):
        starts = sorted(decoded)
        for (off, prefix_len), (nxt, _) in zip(starts, starts[1:]):
            s, used = decoded[off, prefix_len]
            if self.huff.nbits(s) % 8 == 0 and nxt - off == used:
                return True
        return False

    # ---- values ---------------------------------------------------------------------------------------------

    def field(self, name: str) -> Field:
        for f in self.fields:
            if f.name == name or f.short == name:
                return f
        raise KeyError(f'{self.name}.{name}')

    def column(self, name: str) -> int:
        return self.fields.index(self.field(name))

    def get(self, row: list, name: str):
        """Real value of a field (range low added, strings decoded)."""
        f = self.field(name)
        v = row[self.fields.index(f)]
        if f.type == 3:
            return v + f.rangelow
        if f.type == 4:
            return struct.unpack('<f', struct.pack('<I', v))[0]
        if f.type == 0:
            return v.split(b'\0')[0].decode('utf-8', 'replace')
        if f.type in STRING_TYPES:
            return None if v is None else v.decode('utf-8', 'replace')
        return v

    def set(self, row: list, name: str, value) -> None:
        f = self.field(name)
        i = self.fields.index(f)
        if f.type == 3:
            raw = int(value) - f.rangelow
            if not 0 <= raw < (1 << f.depth):
                raise ValueError(f'{self.name}.{f.name}: {value} is out of range')
            row[i] = raw
        elif f.type == 4:
            row[i] = struct.unpack('<I', struct.pack('<f', float(value)))[0]
        elif f.type == 0:
            data = str(value).encode('utf-8')
            size = f.depth // 8
            if len(data) >= size:
                raise ValueError(f'{self.name}.{f.name}: text longer than {size - 1} bytes')
            row[i] = data.ljust(size, b'\0')
        elif f.type in STRING_TYPES:
            row[i] = None if value is None else str(value).encode('utf-8')
        else:
            row[i] = value

    def find(self, **where) -> list[list]:
        """Rows whose fields have these real values."""
        return [row for row in self.records if all(self.get(row, k) == v for k, v in where.items())]

    # ---- writing --------------------------------------------------------------------------------------------

    def _ensure_codes(self) -> None:
        """A new tree when some string has a character the current tree cannot encode."""
        if not isinstance(self.huff, Huffman):
            return
        texts = [v for row in self.records for f, v in zip(self.fields, row) if f.type in STRING_TYPES and v]
        if any(self.huff.missing_chars(t) for t in texts):
            self.huff = Huffman.from_texts(texts)

    def build(self) -> bytes:
        self._ensure_codes()
        nfields = len(self.fields)
        area = bytearray()
        offsets = []
        if self.huff:
            area += self.huff.tree
            written: dict = {}
            for row in self.records:
                offs = []
                for f, v in zip(self.fields, row):
                    if f.type not in STRING_TYPES:
                        continue
                    if v is None:
                        offs.append(0xFFFFFFFF)
                    elif self.shared_strings and (f.type, v) in written:
                        offs.append(written[f.type, v])
                    else:
                        offs.append(len(area))
                        written[f.type, v] = len(area)
                        area += self.huff.encode(v, 2 if f.type == 14 else 1)
                offsets.append(offs)
        recs = bytearray(self.rec_size * len(self.records))
        for r, raw_r in enumerate(self.raw_records[:len(self.records)]):
            recs[r * self.rec_size:(r + 1) * self.rec_size] = raw_r
        for r, row in enumerate(self.records):
            base = r * self.rec_size * 8
            si = 0
            for f, v in zip(self.fields, row):
                if f.type in STRING_TYPES:
                    set_bits(recs, base + f.bitoff, 32, offsets[r][si])
                    si += 1
                elif f.type == 0:
                    o = r * self.rec_size + f.bitoff // 8
                    recs[o:o + len(v)] = v
                else:
                    set_bits(recs, base + f.bitoff, 32 if f.type == 4 else f.depth, v)
        n = len(self.records)
        hdr = struct.pack('<IIIIHHIB', self.flags, self.rec_size, self.rec_bits, len(area),
                          self.nvalid if n == self.nrec_orig else n, n, self.unk14, nfields) + self.hdr_rest
        hdr += struct.pack('<I', crc32_mpeg2(hdr))
        body = bytearray()
        for f in self.fields:
            body += struct.pack('<II4sI', f.type, f.bitoff, f.short.encode('latin1'), f.depth)
        body += recs + area
        if area:  # tables with a string area end on 8 bytes (CRC included)
            body += b'\0' * (-(len(hdr) + len(body) + 4) % 8)
        return bytes(hdr + body) + struct.pack('<I', crc32_mpeg2(bytes(body)))


class Database:
    def __init__(self, data: bytes, meta: dict | None = None):
        if data[:2] != b'DB' or data[4] != 0:
            raise ValueError('not a T3DB database in PC (little-endian) layout')
        self.header = data[:0x18]
        n = struct.unpack('<I', data[16:20])[0]
        self.catalog = [(data[0x18 + 8 * i:0x1C + 8 * i].decode('latin1'),
                         struct.unpack('<I', data[0x1C + 8 * i:0x20 + 8 * i])[0]) for i in range(n)]
        base = 0x18 + 8 * n + 4
        order = sorted(range(n), key=lambda i: self.catalog[i][1])
        self.order = [self.catalog[i][0] for i in order]  # physical order
        self.tables: dict[str, Table] = {}
        for k, i in enumerate(order):
            start = base + self.catalog[i][1]
            end = base + self.catalog[order[k + 1]][1] if k + 1 < n else len(data)
            self.tables[self.catalog[i][0]] = Table(self.catalog[i][0], data[start:end], meta)

    def table(self, name: str) -> Table:
        for t in self.tables.values():
            if t.name == name or t.short == name:
                return t
        raise KeyError(name)

    def first(self) -> Table:
        return self.tables[self.order[0]]

    def build(self) -> bytes:
        blobs, offs, cur = {}, {}, 0
        for sn in self.order:
            blobs[sn] = self.tables[sn].build()
            offs[sn] = cur
            cur += len(blobs[sn])
        cat = b''.join(sn.encode('latin1') + struct.pack('<I', offs[sn]) for sn, _ in self.catalog)
        out = bytearray(self.header) + cat + struct.pack('<I', crc32_mpeg2(cat))
        for sn in self.order:
            out += blobs[sn]
        struct.pack_into('<I', out, 8, len(out))
        struct.pack_into('<I', out, 0x14, crc32_mpeg2(bytes(out[:0x14])))  # covers the total size
        return bytes(out)


# ---- language databases -----------------------------------------------------------------------------------------

_CRC_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_TABLE.append(_c)


def string_hash(sid: str) -> int:
    """The hashid of a language string: CRC-32 (reflected, starting at 0, no final xor) of the stringid's bytes, each
    byte & 0xDF (case does not matter). The rows of a language database are kept in hashid order."""
    c = 0
    for b in sid.encode('utf-8'):
        c = (c >> 8) ^ _CRC_TABLE[(c ^ (b & 0xDF)) & 0xFF]
    return c


class LanguageStrings:
    """The one table of a language database (stringid -> text), editable. A new string gets its hashid and the rows
    are written back in hashid order, as the game keeps them."""

    def __init__(self, data: bytes):
        self.db = Database(data)
        self.table = self.db.first()
        self._sid = next(i for i, f in enumerate(self.table.fields) if f.type == 13)
        self._text = next(i for i, f in enumerate(self.table.fields) if f.type == 14)
        self._hash = next((i for i, f in enumerate(self.table.fields) if f.type == 3), None)
        self._rows = {row[self._sid]: row for row in self.table.records if row[self._sid] is not None}
        self._added = False

    def get(self, sid: str) -> str | None:
        row = self._rows.get(sid.encode('utf-8'))
        if row is None or row[self._text] is None:
            return None
        return row[self._text].decode('utf-8', 'replace')

    def set(self, sid: str, text: str) -> None:
        """Changes a string; a stringid the database does not have yet gets a new row."""
        key = sid.encode('utf-8')
        row = self._rows.get(key)
        if row is None:
            if not self.table.records:
                raise ValueError('empty language database')
            row = list(self.table.records[-1])
            row[self._sid] = key
            for i, f in enumerate(self.table.fields):
                if f.type == 3:
                    row[i] = 0
            if self._hash is not None:
                row[self._hash] = string_hash(sid)
            self.table.records.append(row)
            self.table.raw_records.append(bytes(self.table.rec_size))
            self._rows[key] = row
            self._added = True
        row[self._text] = text.encode('utf-8')

    def build(self) -> bytes:
        if self._added and self._hash is not None:
            t = self.table
            raws = t.raw_records + [bytes(t.rec_size)] * (len(t.records) - len(t.raw_records))
            pairs = sorted(zip(t.records, raws), key=lambda p: p[0][self._hash])  # stable: old order kept on ties
            t.records, t.raw_records = [p[0] for p in pairs], [p[1] for p in pairs]
            self._added = False
        return self.db.build()
