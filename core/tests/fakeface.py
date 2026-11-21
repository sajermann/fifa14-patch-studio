"""Small synthetic faces for the face converter (f14mod.faceconv): a template in FIFA 14's own mesh format (4 u8
bone influences, 32-byte vertices, a bone palette per mesh) and a pack face in the newer format (2 x 4 u16
influences, 48-byte vertices). Same shapes in both: a head made of rings from the neck base (y = 150) to the top
(y = 182), the eyes in front, and hair (strands + cap) over the top.

Bones (bind positions, cm): 0 torso, 1 neck, 2 head (the eyes hang on it), 3 jaw (the front of the lower face).
"""
import math
import struct

from f14mod import faceconv

BONES = [(0.0, 150.0, 0.0), (0.0, 160.0, 0.0), (0.0, 170.0, 0.0), (0.0, 163.0, 5.0)]
OLD_DECL = 'p0:00:00:0001:3f32 n0:0C:00:0001:3s10n t0:10:00:0001:2f32 i0:18:00:0001:4u8 w0:1C:00:0001:4u8n'
NEW_DECL = ('p0:00:00:0001:3f32 n0:0C:00:0001:3s10n t0:10:00:0001:2f32 i0:18:00:0001:4u16 i1:20:00:0001:4u16 '
            'w0:28:00:0001:4u8n w1:2C:00:0001:4u8n')


def _s10n(n):
    out = 0
    for k, c in enumerate(n):
        out |= (round(c * 511) & 0x3FF) << (10 * k)
    return out


def _skin_weights(p):
    x, y, z = p
    if y < 157:
        return {0: 255}
    if y < 160:
        return {1: 255}
    if z > 2 and y < 168:
        return {3: 200, 2: 55}
    return {2: 255}


def _ring_mesh(radius, ys, segments=12, front=0.0):
    """(vertices [(pos, normal)], triangles) of a tube of rings at these heights."""
    verts, tris = [], []
    for y in ys:
        for s in range(segments):
            a = 2 * math.pi * s / segments
            n = (math.sin(a), 0.0, math.cos(a))
            verts.append(((radius * n[0], y, radius * n[2] + front), n))
    for r in range(len(ys) - 1):
        for s in range(segments):
            a, b = r * segments + s, r * segments + (s + 1) % segments
            c, d = a + segments, b + segments
            tris += [(a, b, c), (b, d, c)]
    return verts, tris


def _vertex(fmt_new, pos, normal, weights):
    head = struct.pack('<3fI2f', *pos, _s10n(normal), 0.5, 0.5)
    items = sorted(weights.items(), key=lambda kv: -kv[1])
    idx = [b for b, _ in items] + [0] * (4 - len(items))
    w = [v for _, v in items] + [0] * (4 - len(items))
    if fmt_new:
        return head + struct.pack('<8H', *idx, 0, 0, 0, 0) + bytes(w) + bytes(4)
    return head + bytes(idx) + bytes(w)


def _pad(b):
    return b + bytes(-len(b) % 16)


def _rx3(meshes, new):
    """RX3l with these meshes [(name, vertices [(pos, normal, weights)], triangles)], in the newer format or FIFA
    14's (then with a bone palette per mesh and the vertex buffers flagged 1, like the game's files)."""
    decl = NEW_DECL if new else OLD_DECL
    stride = 48 if new else 32
    sections = []
    header = struct.pack('<IIII', len(meshes), 0, 0, 0)
    blocks = []
    for name, verts, tris in meshes:
        vb = b''.join(_vertex(new, p, n, w) for p, n, w in verts)
        ib = struct.pack(f'<{3 * len(tris)}H', *[i for t in tris for i in t])
        isize = len(_pad(bytes(16) + ib))
        header += struct.pack('<IIII', isize, 3 * len(tris), 2, 0)
        used = sorted({b for _, _, w in verts for b in w})
        palette = bytearray(256 + 256)
        for slot, bone in enumerate(used):
            palette[bone], palette[256 + slot] = slot, bone
        blocks.append([
            (faceconv.DECL, bytes(16) + decl.encode() + b'\0'),
            (faceconv.INDICES, struct.pack('<II', isize, 3 * len(tris)) + bytes([2]) + bytes(7) + ib),
            (faceconv.VERTICES, struct.pack('<IIII', len(_pad(bytes(16) + vb)), len(verts), stride,
                                            0 if new else 1) + vb),
        ] + ([] if new else [(faceconv.PALETTE, struct.pack('<II', 16 + 512, len(used)) + bytes(8) + palette)]))
    sections.append((faceconv.HEADER, header))
    for block in blocks:
        sections += block
    bones = bytes(16) + b''.join(struct.pack('<16f', 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1)
                                 for x, y, z in BONES)
    sections.append((faceconv.BONES, bones))
    names = b''
    for name, _, _ in meshes:
        label = f'{name}.FxRenderableSimple'.encode() + b'\0'
        names += struct.pack('<II', 0, len(label)) + label
    sections.append((faceconv.NAMES, struct.pack('<IIII', 0, len(meshes), 0, 0) + names))
    off = 16 + 16 * len(sections)
    table, body = b'', b''
    for kind, blob in sections:
        blob = _pad(blob)
        table += struct.pack('<IIII', kind, off + len(body), len(blob), 0)
        body += blob
    data = b'RX3l' + bytes(4) + struct.pack('<II', off + len(body), len(sections)) + table + body
    return data


def _with_weights(mesh, weights):
    verts, tris = mesh
    return [(p, n, weights(p)) for p, n in verts], tris


def head(new, shift=0.0):
    """Head RX3l: skin (mesh 0 in packs) and eyes; FIFA 14's template has the eyes first (its mesh 0)."""
    skin = _with_weights(_ring_mesh(7.0 + shift, [150 + 2 * k for k in range(17)]), _skin_weights)
    eye_verts, eye_tris = _ring_mesh(1.0, [171.0, 172.0, 173.0], segments=6, front=6.5 + shift)
    eyes = [(p, n, {2: 255}) for p, n in eye_verts], eye_tris
    if new:
        return _rx3([('head_', *skin), ('eyes_', *eyes)], True)
    return _rx3([('eyes_', *eyes), ('head_', *skin)], False)


def head_without_eyes():
    """A newer-format head with the skin only (no eyes mesh): a layout the converter does not know."""
    skin = _with_weights(_ring_mesh(7.8, [150 + 2 * k for k in range(17)]), _skin_weights)
    return _rx3([('head_', *skin)], True)


def hair(new, lod=False, shift=0.0):
    """Hair RX3l: strands (alphaB) + cap (alphaA); a hair LOD has the cap only."""
    cap = _with_weights(_ring_mesh(7.5 + shift, [170.0, 174.0, 178.0, 182.0]), lambda p: {2: 255})
    if lod:
        return _rx3([('player_hairlod_alphaA_', *cap)], new)
    strands = _with_weights(_ring_mesh(8.5 + shift, [165.0, 175.0, 183.0], segments=8),
                            lambda p: {2: 255} if p[1] > 166 else {1: 128, 2: 127})
    return _rx3([('player_hair_alphaB_', *strands), ('player_hair_alphaA_', *cap)], new)


def template():
    """{kind: bytes} of the template (faceconv.TEMPLATE in the fake game)."""
    return {'head': head(False), 'hair': hair(False), 'hairlod': hair(False, lod=True)}


def newer_pack_face():
    """{kind: bytes} of a pack face in the newer format, a bit wider than the template (its neck goes through the
    template's), with textures that are just bytes."""
    return {'head': head(True, shift=0.8), 'face': b'RX3l pack face textures', 'hair': hair(True, shift=0.8),
            'hairlod': hair(True, lod=True, shift=0.8), 'hair_textures': b'RX3l pack hair textures'}
