"""Read-only reader of the little-endian (PC) T3DB databases of FIFA: the main database (fifa_ng_db.db + its
-meta.xml with the table and field names) and the language databases (data/loc/<language>.db)."""
import re
import struct

from . import chunk

STRING_FIXED, FLOAT = 0, 4
STRING_SHORT, STRING_LONG = 13, 14  # Huffman strings with a 1- or 2-byte length


class DatabaseError(ValueError):
    """A file this reader does not understand."""


def load_meta(raw: bytes) -> dict:
    """{table short name: (table name, {field short name: (field name, range low)})} of a -meta.xml file."""
    raw = chunk.decode(raw)
    try:
        txt = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        txt = raw.decode('latin1')
    out = {}
    for tm in re.finditer(r'<table name="([^"]+)" shortname="([^"]+)"[^>]*>(.*?)</table>', txt, re.S):
        fields = {}
        for fm in re.finditer(r'<field ([^>]*)/>', tm.group(3)):
            a = dict(re.findall(r'(\w+)="([^"]*)"', fm.group(1)))
            if 'shortname' in a and 'name' in a:
                fields[a['shortname']] = (a['name'], int(a.get('rangelow', 0) or 0))
        out[tm.group(2)] = (tm.group(1), fields)
    if not out:
        raise DatabaseError('no tables in the meta file')
    return out


def huff_decode(area: bytes, off: int, prefix_len: int) -> bytes:
    """A Huffman string of a table's string area. The length prefix is big-endian even in the PC database."""
    n = int.from_bytes(area[off:off + prefix_len], 'big')
    pos, cur, out = off + prefix_len, 0, bytearray()
    while len(out) < n:
        byte = area[pos]
        pos += 1
        for shift in range(7, -1, -1):
            j = 4 * cur + 2 * ((byte >> shift) & 1)
            first, second = area[j], area[j + 1]
            if second != 0 or first == 0:
                out.append(second)
                cur = 0
                if len(out) == n:
                    break
            else:
                cur = first
    return bytes(out)


def text_of(raw: bytes) -> str:
    """Database strings: UTF-8 when valid, else Latin-1."""
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin1')


def _table_offsets(data: bytes):
    if data[:2] != b'DB':
        raise DatabaseError('not a T3DB database')
    count = struct.unpack('<I', data[16:20])[0]
    base = 0x18 + 8 * count + 4
    for i in range(count):
        short = data[0x18 + 8 * i:0x1C + 8 * i].decode('latin1')
        yield short, base + struct.unpack('<I', data[0x1C + 8 * i:0x20 + 8 * i])[0]


def _fields(data: bytes, t: int):
    _, rec_size, _, strsz, _, nrec, _, nfields = struct.unpack('<IIIIHHIB', data[t:t + 0x19])
    fields = []
    for k in range(nfields):
        ftype, bitoff, fshort, depth = struct.unpack('<II4sI', data[t + 0x24 + 16 * k:t + 0x34 + 16 * k])
        fields.append((fshort.decode('latin1'), ftype, bitoff, depth))
    p = t + 0x24 + 16 * nfields
    area = data[p + rec_size * nrec:p + rec_size * nrec + strsz]
    return rec_size, nrec, fields, p, area


def read_tables(raw: bytes, meta: dict) -> dict[str, dict]:
    """{table name: {'fields': [field names in file order], 'rows': [{field: value}]}}.
    Integers get the field's range low added (the value the game uses); missing strings are None."""
    data = chunk.decode(raw)
    tables = {}
    try:
        for short, t in _table_offsets(data):
            name, meta_fields = meta.get(short, (short, {}))
            rec_size, nrec, fields, p, area = _fields(data, t)
            named = []
            for fshort, ftype, bitoff, depth in fields:
                fname, low = meta_fields.get(fshort, (fshort, 0))
                named.append((fname, ftype, bitoff, depth, low))
            rows = []
            for r in range(nrec):
                rb = data[p + r * rec_size:p + (r + 1) * rec_size]
                as_int = int.from_bytes(rb, 'little')
                row = {}
                for fname, ftype, bitoff, depth, low in named:
                    if ftype == STRING_FIXED:
                        row[fname] = text_of(rb[bitoff // 8:(bitoff + depth) // 8].split(b'\0')[0])
                    elif ftype in (STRING_SHORT, STRING_LONG):
                        off = (as_int >> bitoff) & 0xFFFFFFFF
                        row[fname] = None if off == 0xFFFFFFFF else text_of(
                            huff_decode(area, off, 2 if ftype == STRING_LONG else 1))
                    elif ftype == FLOAT:
                        row[fname] = struct.unpack('<f', struct.pack('<I', (as_int >> bitoff) & 0xFFFFFFFF))[0]
                    else:
                        row[fname] = ((as_int >> bitoff) & ((1 << depth) - 1)) + low
                rows.append(row)
            tables[name] = {'fields': [f[0] for f in named], 'rows': rows}
    except (struct.error, IndexError) as e:
        raise DatabaseError(f'damaged database ({e})') from e
    return tables


def read_strings(raw: bytes, wanted) -> dict[str, str]:
    """{stringid: text} of a language database (one table: stringid, sourcetext...) for the stringids where
    wanted(stringid) is true; only those texts are decoded (the table holds tens of thousands)."""
    data = chunk.decode(raw)
    try:
        _, t = next(iter(_table_offsets(data)))
        rec_size, nrec, fields, p, area = _fields(data, t)
        offsets = {ftype: bitoff for _, ftype, bitoff, _ in fields}  # 13 = stringid, 14 = sourcetext
        sid_bit, text_bit = offsets[STRING_SHORT], offsets[STRING_LONG]
        out = {}
        for r in range(nrec):
            as_int = int.from_bytes(data[p + r * rec_size:p + (r + 1) * rec_size], 'little')
            off = (as_int >> sid_bit) & 0xFFFFFFFF
            if off == 0xFFFFFFFF:
                continue
            sid = text_of(huff_decode(area, off, 1))
            if wanted(sid):
                off = (as_int >> text_bit) & 0xFFFFFFFF
                out[sid] = '' if off == 0xFFFFFFFF else text_of(huff_decode(area, off, 2))
        return out
    except (StopIteration, KeyError, struct.error, IndexError) as e:
        raise DatabaseError(f'damaged language database ({e})') from e
