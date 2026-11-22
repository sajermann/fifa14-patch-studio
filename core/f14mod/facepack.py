"""FIFA 14 face packs on the user's disk: listing, reading and gallery thumbnails (same reader as the Street
Studio's, without any conversion: the pack files are the game's own format).

A pack folder holds heads/, faces/, hair/, hairlod/ (the files of fifa14.PLAYER_FACE_FILES, named after the face
id), often inside screenassets/ or data/sceneassets/, and sometimes ui/imgAssets/heads/p<id>.dds (player photos).
The user may point at the pack root, at its asset folder or at a folder with several packs inside: find_parts
looks deeper, and packs that bring several versions of the same face side by side (03/, 08/, 'FIFA 14 PC'/...) give
one part each. Packs are read in place and never written; the app never ships packs. An optional manifest.json at
the pack's root (read_manifest) tells the player's name and who made each face; a face outside it shows its id.
"""
import io
import json
import os
import re

from PIL import Image

import struct
import zlib

from . import chunk, fifa14, rx3, rx3mesh, weblink

ASSETS_PREFIX = 'data/sceneassets/'
FILES = {kind: path[len(ASSETS_PREFIX):] for kind, path in fifa14.PLAYER_FACE_FILES.items()}
REQUIRED = fifa14.FACE_REQUIRED


class FaceFormatError(ValueError):
    """A face file the game cannot read (a console file in a PC pack, a damaged download)."""


def read_files(folder, face_id):
    """{kind: bytes} of the FILES of a face found under folder (a pack's asset folder). EA-compressed files
    (chunkzip) come back decoded; an optional part that is not a PC RX3 file is left out."""
    out = {}
    for kind, f in FILES.items():
        path = os.path.join(folder, *f.format(face_id).split('/'))
        if not os.path.isfile(path):
            continue
        with open(path, 'rb') as fh:
            data = fh.read()
        if data[:4] == b'chun':
            try:
                data = chunk.decode(data)
            except (zlib.error, ValueError, struct.error, chunk.ChunkError) as e:
                raise FaceFormatError(f'{os.path.basename(path)}: damaged compressed file ({e})') from e
        if data[:4] != b'RX3l':
            if kind in REQUIRED:
                raise FaceFormatError(f'{os.path.basename(path)}: not a PC RX3 file ({data[:4]!r})')
            continue
        out[kind] = data
    return out

SCREENASSETS = 'screenassets'
PHOTOS = os.path.join('ui', 'imgAssets', 'heads')
FACE_RE = re.compile(r'face_(\d+)_0_0_0_0_0_0_0_0_textures\.rx3$')


def assets_dir(folder):
    """screenassets folder of a pack (the folder itself, its child, or the child of its only subfolder), or None."""
    if not folder or not os.path.isdir(folder):
        return None
    candidates = [folder, os.path.join(folder, SCREENASSETS)]
    try:
        subs = [e.path for e in os.scandir(folder) if e.is_dir()]
    except OSError:  # no permission
        return None
    if len(subs) == 1:
        candidates.append(os.path.join(subs[0], SCREENASSETS))
    for c in candidates:
        if os.path.isdir(os.path.join(c, 'heads')) and os.path.isdir(os.path.join(c, 'faces')):
            return c
    return None


ASSET_FOLDERS = ('screenassets', 'sceneassets')  # names packs give the folder that holds heads/, faces/...
WRAPPER_FOLDERS = ASSET_FOLDERS + ('data',)  # left out of a part's name (data/sceneassets = the pack itself)
FIND_DEPTH = 4  # how deep find_parts looks under the folder the user set
FIND_MAX_FOLDERS = 5000  # folders looked at, at most (a folder pointed at by mistake, like a whole disk)


def _is_assets(folder):
    return os.path.isdir(os.path.join(folder, 'heads')) and os.path.isdir(os.path.join(folder, 'faces'))


def find_parts(folder):
    """Every folder with faces (heads/ + faces/) under the folder the user set, itself included, looking FIND_DEPTH
    levels down and never inside a folder with faces: [(assets folder, label)], by label. label = the path from the
    folder set, without wrapper folders ('' = the folder itself; 'data/sceneassets' -> ''; '08' or 'FIFA 14 PC' for
    packs that bring several versions of a face side by side, '2010_11/screenassets' -> '2010_11')."""
    if not folder or not os.path.isdir(folder):
        return []
    found, seen = [], 0
    pending = [(folder, 0)]
    while pending:
        current, depth = pending.pop()
        if _is_assets(current):
            found.append(current)
            continue
        if depth >= FIND_DEPTH or seen >= FIND_MAX_FOLDERS:
            continue
        try:
            subs = sorted((e.path for e in os.scandir(current) if e.is_dir() and not e.name.startswith('.')),
                          reverse=True)
        except OSError:  # no permission
            continue
        seen += len(subs)
        pending.extend((s, depth + 1) for s in subs)
    out = []
    for assets in found:
        parts = os.path.relpath(assets, folder).replace('\\', '/').split('/')
        parts = [p for p in parts if p not in ('.', '') and p.lower() not in WRAPPER_FOLDERS]
        out.append((assets, '/'.join(parts)))
    return sorted(out, key=lambda p: [s.lower() for s in p[1].split('/')])


def pack_root(assets):
    """The pack's own folder: the parent of screenassets/, or assets itself when the pack has no screenassets/."""
    return os.path.dirname(assets) if os.path.basename(os.path.normpath(assets)).lower() in ASSET_FOLDERS else assets


def pack_name(assets):
    """Name of the pack (its folder name), whichever the layout."""
    return os.path.basename(os.path.normpath(pack_root(assets)))


def _photo_path(assets, face_id):
    return os.path.join(pack_root(assets), PHOTOS, f'p{face_id}.dds')


def missing_parts(kinds):
    """The OPTIONAL parts a face does not bring (kinds of FILES, in their order). Only the user fills them in, with
    the game's generic eyes or hair (facefill); the app never does it on its own."""
    return [k for k in FILES if k not in REQUIRED and k not in kinds]


def list_faces(assets):
    """[{'id', 'hair', 'hairlod', 'photo', 'missing'}] of the faces with a head mesh and a face texture, by id
    (missing = missing_parts)."""
    names = {kind: set(os.listdir(os.path.join(assets, os.path.dirname(f))))
             for kind, f in FILES.items() if os.path.isdir(os.path.join(assets, os.path.dirname(f)))}
    out = []
    for n in names.get('face', ()):
        m = FACE_RE.match(n)
        if not m:
            continue
        fid = int(m[1])
        has = {kind: os.path.basename(f.format(fid)) in names.get(kind, ()) for kind, f in FILES.items()}
        if all(has[k] for k in REQUIRED):
            out.append({'id': fid, 'hair': has['hair'] and has['hair_textures'], 'hairlod': has['hairlod'],
                        'photo': os.path.isfile(_photo_path(assets, fid)),
                        'missing': missing_parts({k for k, v in has.items() if v})})
    return sorted(out, key=lambda f: f['id'])


# ------------------------------------------------------------------ manifest.json (who each face is, credits)

MANIFEST = 'manifest.json'
MANIFEST_TYPE = 'faces'  # "type" of a face manifest
MANIFEST_VERSION = 1  # highest version this app reads; a newer manifest is ignored (with a warning)
MANIFEST_MAX_BYTES = 32 * 1024 * 1024
FACE_TEXT_FIELDS = ('name', 'credits')


def manifest_path(assets):
    """Where a pack's manifest.json is: its root (the folder that holds faces/, heads/... or screenassets/)."""
    return os.path.join(pack_root(assets), MANIFEST)


def manifest_for(folder, assets):
    """The manifest.json that applies to a part of the folder the user set: the part's own (next to its faces/ or
    screenassets/) when it has one, else the one at the folder set (for all its parts). None = no manifest."""
    for path in dict.fromkeys((manifest_path(assets), os.path.join(folder, MANIFEST))):
        if os.path.isfile(path):
            return path
    return None


def _text(value):
    return value.strip() or None if isinstance(value, str) else None


def _face_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def read_manifest(assets, folder=None):
    """(faces, warnings) of the pack's manifest.json (manifest_for: the part's own, else the one at `folder`, the
    folder the user set), written by whoever made or gathered the pack (the app only reads it). faces = {face id: {'name', 'credits', 'credits_url'}} (keys only when known) of the faces it lists;
    a face without credits of its own (neither `credits` nor `credits_url`) gets the pack's (top-level) ones, a face
    with any of them keeps only its own. warnings = [{'code', 'count'?, 'detail'?}]:
      manifest_unreadable / manifest_invalid_json / manifest_wrong_type / manifest_newer_version: the whole file is
        ignored (the pack works as if it had none);
      manifest_bad_entries: entries skipped (not an object, missing/invalid id, repeated id), the rest is used;
      manifest_bad_links: credits_url that are not http(s) addresses, dropped.
    No manifest.json = ({}, [])."""
    path = manifest_for(folder or pack_root(assets), assets)
    if path is None:
        return {}, []
    try:
        if os.path.getsize(path) > MANIFEST_MAX_BYTES:
            return {}, [{'code': 'manifest_unreadable', 'detail': 'file too large'}]
        with open(path, 'rb') as f:
            text = f.read().decode('utf-8-sig')
    except (OSError, UnicodeError) as e:
        return {}, [{'code': 'manifest_unreadable', 'detail': str(e)}]
    try:
        data = json.loads(text)
    except ValueError as e:
        return {}, [{'code': 'manifest_invalid_json', 'detail': str(e)}]
    if not isinstance(data, dict) or data.get('type') != MANIFEST_TYPE or not isinstance(data.get('faces', []), list):
        return {}, [{'code': 'manifest_wrong_type'}]
    version = data.get('version', 1)
    if isinstance(version, int) and not isinstance(version, bool) and version > MANIFEST_VERSION:
        return {}, [{'code': 'manifest_newer_version', 'detail': str(version)}]

    bad_links = 0

    def link(value):
        nonlocal bad_links
        url = weblink.normalize(value)
        if url is None and _text(value):
            bad_links += 1
        return url

    pack_credits = {'credits': _text(data.get('credits')), 'credits_url': link(data.get('credits_url'))}
    faces, bad = {}, 0
    for entry in data.get('faces', []):
        fid = _face_id(entry.get('id')) if isinstance(entry, dict) else None
        if fid is None or fid in faces:
            bad += 1
            continue
        own = {'credits': _text(entry.get('credits')), 'credits_url': link(entry.get('credits_url'))}
        face = {'name': _text(entry.get('name')), **(own if any(own.values()) else pack_credits)}
        faces[fid] = {k: v for k, v in face.items() if v}
    warnings = []
    if bad:
        warnings.append({'code': 'manifest_bad_entries', 'count': bad})
    if bad_links:
        warnings.append({'code': 'manifest_bad_links', 'count': bad_links})
    return faces, warnings


def read_face(assets, face_id):
    """{kind: RX3l bytes} of the files a face has in the pack."""
    return read_files(assets, face_id)


def photo(assets, face_id):
    """Player photo shipped with the pack (PIL image) or None."""
    path = _photo_path(assets, face_id)
    if not os.path.isfile(path):
        return None
    try:
        return Image.open(path).convert('RGBA')
    except OSError:
        return None


# ------------------------------------------------------------------ thumbnail (front view, PIL only)

FRAME = (-15.0, 150.5, 15.0, 186.5)  # cm (x0, y0, x1, y1) around the head in the reference pose
LIGHT = (0.35, 0.45, 0.82)  # towards the viewer, from the upper left
BACKGROUND = (0, 0, 0, 0)
# blue and green checkers, as the game draws a missing texture (8x8 cells, repeated over the eyeball's UVs)
MISSING_TEXTURE = Image.new('RGBA', (32, 32))
MISSING_TEXTURE.putdata([(40, 90, 220, 255) if ((x // 4) + (y // 4)) % 2 else (40, 200, 70, 255)
                         for y in range(32) for x in range(32)])


def _texture(d, index):
    d = rx3.unpack(d)
    return rx3.to_image(d, rx3.textures(d)[index]).convert('RGBA')


def _shade(n):
    ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1
    return 0.45 + 0.65 * max(0.0, (n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]) / ln)


def _draw(out, zbuf, size, mesh, tex, alpha=None, uv_alpha='t0', tint=(1.0, 1.0, 1.0)):
    """Rasterizes mesh (orthographic, front) with z-buffer, per-vertex light and optional alpha test (alpha =
    (grey image, threshold) sampled with the uv_alpha set)."""
    x0, y0, x1, y1 = FRAME
    sx, sy = size / (x1 - x0), size / (y1 - y0)
    a = mesh['attrs']
    pts = [((p[0] - x0) * sx, (y1 - p[1]) * sy, p[2]) for p in a['p0']]
    uv, uva = a['t0'], a.get(uv_alpha, a['t0'])
    light = [_shade(n) for n in a['n0']] if 'n0' in a else [1.0] * len(pts)
    px, (tw, th) = tex.load(), tex.size
    if alpha:
        apx, (aw, ah), cut = alpha[0].load(), alpha[0].size, alpha[1]
    idx = mesh['indices']
    for t in range(0, len(idx) - 2, 3):
        i0, i1, i2 = idx[t:t + 3]
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[i0], pts[i1], pts[i2]
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area == 0:
            continue
        inv = 1.0 / area
        for y in range(max(0, int(min(ay, by, cy))), min(size - 1, int(max(ay, by, cy))) + 1):
            fy = y + 0.5
            for x in range(max(0, int(min(ax, bx, cx))), min(size - 1, int(max(ax, bx, cx))) + 1):
                fx = x + 0.5
                w0 = ((bx - fx) * (cy - fy) - (cx - fx) * (by - fy)) * inv
                w1 = ((cx - fx) * (ay - fy) - (ax - fx) * (cy - fy)) * inv
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * az + w1 * bz + w2 * cz
                k = y * size + x
                if z <= zbuf[k]:
                    continue
                if alpha:
                    u = w0 * uva[i0][0] + w1 * uva[i1][0] + w2 * uva[i2][0]
                    v = w0 * uva[i0][1] + w1 * uva[i1][1] + w2 * uva[i2][1]
                    if apx[int(u % 1 * aw), int(v % 1 * ah)] < cut:
                        continue
                u = w0 * uv[i0][0] + w1 * uv[i1][0] + w2 * uv[i2][0]
                v = w0 * uv[i0][1] + w1 * uv[i1][1] + w2 * uv[i2][1]
                c = px[int(u % 1 * tw), int(v % 1 * th)]
                s = w0 * light[i0] + w1 * light[i1] + w2 * light[i2]
                zbuf[k] = z
                out[x, y] = (min(255, int(c[0] * s * tint[0])), min(255, int(c[1] * s * tint[1])),
                             min(255, int(c[2] * s * tint[2])), 255)


def thumbnail(files, size=160, hair_tint=0.9, hair_rgb=None):
    """PNG of a face seen from the front: head with its face texture, eyes, hair (cap + strands, alpha tested).
    files: {kind: RX3 bytes} (pack or converted). hair_tint: the game draws scanned hair with hairColor 0x808080
    (the viewer's gain makes it ~0.9)."""
    img = Image.new('RGBA', (size, size), BACKGROUND)
    out, zbuf = img.load(), [-1e9] * (size * size)
    face = _texture(files['face'], 0)
    # a face without its eyes texture: the game's checkered missing texture (nothing is filled in)
    eyes = _texture(files['eyes'], 0) if files.get('eyes') else MISSING_TEXTURE
    for m in rx3mesh.meshes(rx3.unpack(files['head'])):
        _draw(out, zbuf, size, m, eyes if 'eyes' in m['name'] else face)
    if files.get('hair') and files.get('hair_textures'):
        coeff, cm = _texture(files['hair_textures'], 0), _texture(files['hair_textures'], 1)
        cap_alpha, strands_alpha = coeff.getchannel('R'), coeff.getchannel('B')
        # a generic hair is grey: the game tints it with the hair color (hair_rgb, brightened like the preview)
        tint = tuple(min(2.0, c / 255 * 1.8) for c in hair_rgb) if hair_rgb else (hair_tint,) * 3
        for m in rx3mesh.meshes(rx3.unpack(files['hair'])):
            if 'alphaA' in m['name']:  # the coeff is read with the second UV set, like the game (preview.HAIR_PARTS)
                _draw(out, zbuf, size, m, cm, (cap_alpha, 110), 't1', tint)
            else:
                _draw(out, zbuf, size, m, cm, (strands_alpha, 110), 't1', tint)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
