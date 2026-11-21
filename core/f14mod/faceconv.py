"""Pack faces in a newer FIFA format converted into FIFA 14's own (validated in game).

FIFA 14 crashes on the meshes of most face packs of the newer games (8 bone influences with u16 indices into a
400-bone skeleton, 48/52-byte head vertices, 19 sections); FIFA 14's have 4 influences with u8 indices into its
255-bone skeleton and 32-byte head vertices. The textures load as they are.

A head of the game is the template (TEMPLATE): its files keep their skeleton (bone matrices), bone palette (one per
mesh) and materials; only the vertex and index buffers are replaced, in the template's vertex layout:
  - the pack's head is moved so its eyes sit on the template's (align_offset);
  - each pack bone goes to the nearest bone the template's mesh already uses (bind positions), the face's bones by
    vote (vote_map: the template vertex under each pack vertex), so the mouth and eyelids move like the pack's;
  - the neck base takes the template's shape and bone weights (neck_fitter, neck_weights): every head of the game
    shares it, and a converted neck went through the shirt collars; the hair that comes down the nape moves with it;
  - the hair follows the skin's head and jaw bones (skin_follow).
A face whose meshes FIFA 14 takes as they are (needs_conversion) is kept as it is.

Template meshes: head 0 = eyes, 1 = skin; hair 0 = strands (alphaB), 1 = cap (alphaA); hairlod 0 = cap. Their names
carry no player id. Pack files: RX3l (little-endian), skin first after head_mesh_first.
"""
import math
import struct

from . import fifa14, rx3, rx3mesh

TEMPLATE = 158023  # Messi: the game head whose skeleton, palettes and materials every converted face gets
T = '<'  # FIFA 14 PC: the template and the output are little-endian
HEADER, DECL, NAMES, INDICES, VERTICES, BONES = 0x22B2BE36, 0xC28193F0, 0x4C9B9EB2, 0x005878F4, 0x00587AA1, 0xDF9AEC1E
PALETTE = 0x0F3861A2  # per mesh: u32 size, u32 count, 8 bytes, then bone -> slot (256 u8) and slot -> bone (256 u8)
MESH_SECTIONS = (DECL, INDICES, PALETTE, VERTICES, BONES, 0xD48D7880)  # section types with one entry per mesh
HEAD_SLOTS = {'skin': 1, 'eyes': 0}  # template head meshes
MESHES = ('head', 'hair', 'hairlod')  # the kinds of fifa14.PLAYER_FACE_FILES that are meshes
# Back of the neck: the converted one is laid onto the template's and takes its bone weights; both fade out towards
# the front, from z=NAPE_FRONT on
NAPE_FRONT, NAPE_FADE = 2.0, 3.0  # cm
NAPE_FIT_TOP, NAPE_FIT_FULL = 167.0, 164.0  # cm: laid onto the template's neck (only ever pulled in), whole below full
NAPE_WEIGHTS_TOP, NAPE_WEIGHTS_FADE = 168.0, 2.0  # cm: takes the template's bone weights


class FaceFormatError(ValueError):
    """A face the converter cannot handle: packs are made with many tools and some bring files in a layout it has
    never met."""


def sections(d, e):
    n = struct.unpack(e + 'I', d[12:16])[0]
    return [struct.unpack(e + 'IIII', d[16 + 16 * i:32 + 16 * i]) for i in range(n)]


def of_type(d, e, type_):
    return [(o, s) for t, o, s, _ in sections(d, e) if t == type_]


def decl(d, e, k):
    o, s = of_type(d, e, DECL)[k]
    out = {}
    for tok in d[o + 16:o + s].split(b'\0')[0].decode().split():
        name, off, _, _, fmt = tok.split(':')
        out[name] = (int(off, 16), int(fmt[0]), fmt[1:])
    return out


def bone_positions(d, e):
    """Bind position of every bone (inverse of the rigid inverse-bind matrices)."""
    o, s = of_type(d, e, BONES)[0]
    out = []
    for i in range((s - 16) // 64):
        m = struct.unpack_from(e + '16f', d, o + 16 + 64 * i)
        rot, t = (m[0:3], m[4:7], m[8:11]), m[12:15]
        out.append(tuple(-sum(t[k] * rot[j][k] for k in range(3)) for j in range(3)))
    return out


def used_bones(d, e, k, dc):
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    ioff, n, typ = dc['i0']
    woff = dc['w0'][0]
    used = set()
    for i in range(count):
        b = o + 16 + i * stride
        idx = struct.unpack_from(e + ('4B' if typ == 'u8' else '4H'), d, b + ioff)
        used.update(x for x, w in zip(idx, d[b + woff:b + woff + 4]) if w)
    return used


def nearest_map(src_pos, dst_pos, allowed):
    def dist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))
    return {i: min(allowed, key=lambda j: dist(p, dst_pos[j])) for i, p in enumerate(src_pos)}


def positions(d, e, k):
    """[(x, y, z)] of mesh k (heads: 3 x f32; hair: 4 x f16)."""
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    off, n, typ = decl(d, e, k)['p0']
    fmt = e + ('3f' if typ == 'f32' else '3e')
    return [struct.unpack_from(fmt, d, o + 16 + i * stride + off) for i in range(count)]


def check_positions(src):
    """ValueError when a mesh of the pack has vertex positions that are not numbers (NaN/inf): they would be
    copied as they are into the game's files (seen in the eyes of a pack's head)."""
    for kind in ('head', 'hair', 'hairlod'):
        d = src.get(kind)
        if not d:
            continue
        for k in range(len(of_type(d, '<', VERTICES))):
            if not all(math.isfinite(v) for p in positions(d, '<', k) for v in p):
                raise ValueError(f'{kind}: mesh {k} has vertex positions that are not numbers (NaN)')


def _closest_on_triangle(p, a, b, c):
    """Closest point to p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    def sub(u, v): return (u[0] - v[0], u[1] - v[1], u[2] - v[2])
    def dot(u, v): return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    def lin(u, v, s): return (u[0] + v[0] * s, u[1] + v[1] * s, u[2] + v[2] * s)
    ab, ac, ap = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a
    bp = sub(p, b)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return lin(a, ab, d1 / (d1 - d3))
    cp = sub(p, c)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return lin(a, ac, d2 / (d2 - d6))
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        return lin(b, sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6)))
    den = 1 / (va + vb + vc)
    return lin(lin(a, ab, vb * den), ac, vc * den)


def s10n(v):
    out = []
    for k in range(3):
        x = (v >> (10 * k)) & 0x3FF
        out.append((x - 0x400 if x & 0x200 else x) / 511.0)
    return out


def vertex_bones(d, e, k, dd):
    """[(position, {bone: weight})] of mesh k (both influence sets)."""
    o, _ = of_type(d, e, VERTICES)[k]
    _, count, stride, _ = struct.unpack(e + 'IIII', d[o:o + 16])
    out = []
    for i in range(count):
        b = o + 16 + i * stride
        bw = {}
        for iname, wname in (('i0', 'w0'), ('i1', 'w1')):
            if iname in dd:
                fmt = e + ('4B' if dd[iname][2] == 'u8' else '4H')
                for x, w in zip(struct.unpack_from(fmt, d, b + dd[iname][0]), d[b + dd[wname][0]:b + dd[wname][0] + 4]):
                    if w:
                        bw[x] = bw.get(x, 0) + w
        out.append((struct.unpack_from(e + '3f', d, b), bw))
    return out


def head_bone(d, e):
    """Bone that carries the head: the one the eyes (mesh 1) use. Some packs hang the eyes on a bone the skin (mesh 0)
    does not use at all; there it is the most weighted bone of the skin."""
    eyes = used_bones(d, e, 1, decl(d, e, 1))
    skin = {}
    for _, bw in vertex_bones(d, e, 0, decl(d, e, 0)):
        for x, w in bw.items():
            skin[x] = skin.get(x, 0) + w
    return min(eyes) if any(b in skin for b in eyes) else max(skin, key=skin.get)


def jaw_family(verts, head_bone, threshold=0.25):
    """Bones that move with the jaw: the jaw is the most weighted bone of the face (y >= 160) after the head bone;
    a bone belongs to its family when at least `threshold` of its vertices also hang on the jaw (lower lip and chin
    bones are the jaw's children, so they share its vertices: newer packs' lower lip 46/96/97 29-38%, chin 29 100%,
    upper lip 72/73/98 0%)."""
    total = {}
    for p, bw in verts:
        if p[1] >= 160:
            for x, w in bw.items():
                total[x] = total.get(x, 0) + w
    jaw = max((x for x in total if x != head_bone), key=total.get)
    count, shared = {}, {}
    for _, bw in verts:
        for x in bw:
            count[x] = count.get(x, 0) + 1
            shared[x] = shared.get(x, 0) + (jaw in bw)
    return jaw, {x for x in count if shared[x] >= threshold * count[x]}


def mirrors(bones, tol=0.8):
    """{bone: its left/right twin} by bind position (x mirrored); central bones (|x| < 0.3) map to themselves."""
    out = {}
    for i, (x, y, z) in enumerate(bones):
        if abs(x) < 0.3:
            out[i] = i
            continue
        j = min(range(len(bones)), key=lambda j: (bones[j][0] + x) ** 2 + (bones[j][1] - y) ** 2 + (bones[j][2] - z) ** 2)
        if (bones[j][0] + x) ** 2 + (bones[j][1] - y) ** 2 + (bones[j][2] - z) ** 2 < tol * tol:
            out[i] = j
    return out


def _index_format(attr):
    """struct format of a pack's bone index attribute: most packs use 2 x 4 u16 influences, faces made with other
    tools 4 u8; both index the same 400-bone skeleton."""
    return '<4B' if attr[2] == 'u8' else '<4H'


def hair_skeleton(hair, head):
    """Bind positions of a pack's hair bones. Some hair files bring the matrices of another skeleton under the bone
    ids of the head's (the main bone of a mesh shows up far from it, e.g. at the leg, and the hair moves apart from
    the head in game): those use the head's skeleton."""
    own = bone_positions(hair, '<')
    for k in range(len(of_type(hair, '<', VERTICES))):
        weights = {}
        for _, bw in vertex_bones(hair, '<', k, decl(hair, '<', k)):
            for x, w in bw.items():
                weights[x] = weights.get(x, 0) + w
        if not weights:
            continue
        main = max(weights, key=weights.get)
        ys = [p[1] for p in positions(hair, '<', k)]
        if main >= len(own) or abs(own[main][1] - sum(ys) / len(ys)) > 40:
            return bone_positions(head, '<')
    return own


def head_mesh_first(head):
    """RX3l head with the skin as mesh 0 and the eyes as mesh 1. A head whose names are right but stored eyes first
    has the same meshes in another order: section table, header and names are put in the usual order. A head whose
    names do not match the meshes (eyes named head_) is hand-made and comes out with torn ears and eyes:
    FaceFormatError."""
    secs = sections(head, '<')
    skin, eyes = (struct.unpack('<IIII', head[o:o + 16])[1] for o, _ in of_type(head, '<', VERTICES)[:2])
    if skin >= eyes:
        return head
    # packs name the meshes 'head_'/'eyes_' or 'head'/'eyes'
    labels = [n.split('.')[0].rstrip('_') for n in rx3mesh.names(head) if n.endswith('.FxRenderableSimple')]
    if labels != ['eyes', 'head']:
        raise FaceFormatError(f'head meshes swapped: {skin} skin vertices, {eyes} eye vertices')
    out = bytearray(head)
    for type_ in MESH_SECTIONS:
        a, b = (i for i, s in enumerate(secs) if s[0] == type_)
        ta, tb = 16 + 16 * a, 16 + 16 * b
        out[ta:ta + 16], out[tb:tb + 16] = head[tb:tb + 16], head[ta:ta + 16]
    h = of_type(head, '<', HEADER)[0][0]
    out[h + 16:h + 32], out[h + 32:h + 48] = head[h + 32:h + 48], head[h + 16:h + 32]
    first = of_type(head, '<', NAMES)[0][0] + 16
    second = first + 8 + struct.unpack_from('<I', head, first + 4)[0]
    end = second + 8 + struct.unpack_from('<I', head, second + 4)[0]
    out[first:end] = head[second:end] + head[first:second]
    return bytes(out)


def hair_parts(d):
    """{'cap': mesh index, 'strands': mesh index} of a hair RX3 by submesh name (alphaA = cap, alphaB = strands);
    packs differ in order and some hair has a cap only. Hair with strands only: they act as the cap."""
    out = {}
    for k, m in enumerate(rx3mesh.meshes(d)):
        part = 'cap' if 'alphaA' in m['name'] else 'strands' if 'alphaB' in m['name'] else None
        if part and part not in out:
            out[part] = k
    return {'cap': out['strands']} if 'strands' in out and 'cap' not in out else out


def is_newer(d: bytes) -> bool:
    """A mesh in the newer format: some vertex declaration has a second influence set or u16 bone indices."""
    for k in range(len(of_type(d, '<', DECL))):
        dd = decl(d, '<', k)
        if 'i1' in dd or dd.get('i0', (0, 0, 'u8'))[2] != 'u8':
            return True
    return False


def align_offset(template_head, src_head):
    """Offset (cm) putting the pack's eyes on the template's (bbox centers; x stays 0)."""
    def center(pts):
        return [(min(p[k] for p in pts) + max(p[k] for p in pts)) / 2 for k in range(3)]
    a = center(positions(template_head, T, HEAD_SLOTS['eyes']))
    b = center(positions(src_head, '<', 1))
    return (0.0, a[1] - b[1], a[2] - b[2])


def template_head_bone(template_head):
    return min(used_bones(template_head, T, HEAD_SLOTS['eyes'], decl(template_head, T, HEAD_SLOTS['eyes'])))


def template_jaw(template_head):
    slot = HEAD_SLOTS['skin']
    return jaw_family(vertex_bones(template_head, T, slot, decl(template_head, T, slot)),
                      template_head_bone(template_head))


def vote_map(src, k, template, slot, offset, fallback):
    """{pack bone: template bone} of the skin by vote: each pack vertex finds the nearest template vertex facing the
    same way and votes, with its weights, for that vertex's bones. Jaw bones (jaw_family) only vote for the
    template's jaw family, so the mouth opens like the pack's. Left/right twins share their votes (a face is
    symmetric); only bones of the template mesh's palette win. Bones that got no vote keep `fallback` (the nearest
    bone), never one of the template's jaw family."""
    sd, td = decl(src, '<', k), decl(template, T, slot)
    src_head = head_bone(src, '<')
    tpl_head = template_head_bone(template)
    src_jaw, src_family = jaw_family(vertex_bones(src, '<', k, sd), src_head)
    tpl_jaw, tpl_family = template_jaw(template)
    o, _ = of_type(template, T, VERTICES)[slot]
    _, count, stride, _ = struct.unpack(T + 'IIII', template[o:o + 16])
    cells, reach = {}, 2.0
    for i in range(count):
        b = o + 16 + i * stride
        p = struct.unpack_from(T + '3f', template, b)
        n = s10n(struct.unpack_from(T + 'I', template, b + td['n0'][0])[0])
        bones = [(x, w) for x, w in zip(template[b + td['i0'][0]:b + td['i0'][0] + 4],
                                        template[b + td['w0'][0]:b + td['w0'][0] + 4]) if w]
        cells.setdefault(tuple(int(c // reach) for c in p), []).append((p, n, bones))
    o, _ = of_type(src, '<', VERTICES)[k]
    _, count, stride, _ = struct.unpack('<IIII', src[o:o + 16])
    votes = {}
    for i in range(count):
        b = o + 16 + i * stride
        p = [c + d for c, d in zip(struct.unpack_from('<3f', src, b), offset)]
        n = s10n(struct.unpack_from('<I', src, b + sd['n0'][0])[0])
        best, hit = None, None
        for r in (1, 2, 3):
            c0 = [int(c // reach) for c in p]
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        for q in cells.get((c0[0] + dx, c0[1] + dy, c0[2] + dz), ()):
                            if sum(a * c for a, c in zip(n, q[1])) < 0.3:
                                continue
                            d = sum((a - c) ** 2 for a, c in zip(p, q[0]))
                            if best is None or d < best:
                                best, hit = d, q
            if hit:
                break
        if not hit:
            continue
        for iname, wname in (('i0', 'w0'), ('i1', 'w1')):
            if iname not in sd:
                continue
            for x, w in zip(struct.unpack_from(_index_format(sd[iname]), src, b + sd[iname][0]),
                            src[b + sd[wname][0]:b + sd[wname][0] + 4]):
                if w:
                    for tb, tw in hit[2]:
                        if x in src_family and tb not in tpl_family:
                            continue
                        votes.setdefault(x, {}).setdefault(tb, 0)
                        votes[x][tb] += w * tw
    src_twin, tpl_twin = mirrors(bone_positions(src, '<')), mirrors(bone_positions(template, T))
    merged = {}
    for b, tally in votes.items():
        m = dict(tally)
        t = src_twin.get(b)
        if t is not None and t != b:
            for tb, w in votes.get(t, {}).items():
                if tb in tpl_twin:
                    m[tpl_twin[tb]] = m.get(tpl_twin[tb], 0) + w
        merged[b] = m
    # only bones of the mesh's palette (a mirrored twin may be one this template mesh does not use)
    allowed = used_bones(template, T, slot, td)
    merged = {b: {tb: w for tb, w in m.items() if tb in allowed} for b, m in merged.items()}
    merged = {b: m for b, m in merged.items() if m}
    out = {}
    for b in fallback:
        if b in merged:
            out[b] = max(merged[b], key=merged[b].get)
        elif b in src_family:
            out[b] = tpl_jaw
        else:
            out[b] = fallback[b] if fallback[b] not in tpl_family else tpl_head
    out[src_head], out[src_jaw] = tpl_head, tpl_jaw
    return out


def palette_first(template, slot):
    """Bone in slot 0 of the template mesh's palette: what the template's files write in the unused influences."""
    o, _ = of_type(template, T, PALETTE)[slot]
    return template[o + 16 + 256]


def padded(n):
    return n + (-n % 16)


def _neck_surface(template, slot, top, full):
    """Function that lays a point onto the template's neck surface (closest point on its triangles): whole below
    `full`, fading out up to `top`."""
    pos = positions(template, T, slot)
    o, _ = of_type(template, T, INDICES)[slot]
    n = struct.unpack(T + 'I', template[o + 4:o + 8])[0]
    idx = struct.unpack_from(f'{T}{n}H', template, o + 16)
    tris = [tuple(pos[i] for i in idx[t:t + 3]) for t in range(0, n - 2, 3)
            if min(pos[i][1] for i in idx[t:t + 3]) < top + 2]

    def fit(p):
        if p[1] >= top:
            return p
        best = min((_closest_on_triangle(p, *tri) for tri in tris),
                   key=lambda q: (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 + (q[2] - p[2]) ** 2)
        t = min(1.0, (top - p[1]) / (top - full))
        return tuple(a + (b - a) * t for a, b in zip(p, best))
    return fit


def neck_fitter(template, slot, top=160.5, full=158.0):
    """Function that lays the pack's neck base onto the template's (the chin is at ~160 cm). Every FIFA 14 head
    shares the template's neck base (same vertices up to the nape); the packs' necks are wider and their napes 1-2 cm
    further back, so they went through the shirt collars. Whole below `full`, fading out up to `top`; the back of the
    neck goes higher (NAPE_FIT_*), but only inwards: napes slimmer than the template's stay as they are."""
    base = _neck_surface(template, slot, top, full)
    high = _neck_surface(template, slot, NAPE_FIT_TOP, NAPE_FIT_FULL)

    def fit(p):
        q = base(p)
        back = max(0.0, min(1.0, (NAPE_FRONT - p[2]) / NAPE_FADE))
        if back == 0 or p[1] >= NAPE_FIT_TOP:
            return q
        r = high(p)
        if r[2] <= q[2]:
            return q
        return tuple(a + (b - a) * back for a, b in zip(q, r))
    return fit


def neck_weights(template, slot, below=160.0):
    """Function (pos, normal, voted indices, voted weights) -> (indices, weights): below the chin a vertex takes the
    bone weights of the nearest template vertex facing the same way (FIFA 14's neck base hangs on the torso and both
    clavicles: 60, 61, 103, so it follows the shirt); the back of the neck fades into the template's weights higher
    up (its middle neck bone, 146, that the vote never picks). None above that: the voted weights stay."""
    dd = decl(template, T, slot)
    o, _ = of_type(template, T, VERTICES)[slot]
    _, count, stride, _ = struct.unpack(T + 'IIII', template[o:o + 16])
    ioff, woff, noff = dd['i0'][0], dd['w0'][0], dd['n0'][0]
    high = []
    for i in range(count):
        b = o + 16 + i * stride
        p = struct.unpack_from(T + '3f', template, b + dd['p0'][0])
        if p[1] < NAPE_WEIGHTS_TOP + 3:
            n = s10n(struct.unpack_from(T + 'I', template, b + noff)[0])
            high.append((p, n, template[b + ioff:b + ioff + 4], template[b + woff:b + woff + 4]))
    low = [q for q in high if q[0][1] < below + 3]
    fill = palette_first(template, slot)

    def nearest(pts, p, n):
        def cost(q):
            d = sum((a - c) ** 2 for a, c in zip(p, q[0]))
            facing = sum(a * c for a, c in zip(n, q[1]))
            return d + (100.0 if facing < 0.3 else 0.0)  # same side of the surface
        return min(pts, key=cost)

    def lookup(p, n, voted_idx, voted_weights):
        if p[1] < below:
            q = nearest(low, p, n)
            return list(q[2]), list(q[3])
        mix = (max(0.0, min(1.0, (NAPE_FRONT - p[2]) / NAPE_FADE))
               * max(0.0, min(1.0, (NAPE_WEIGHTS_TOP - p[1]) / NAPE_WEIGHTS_FADE)))
        if mix == 0:
            return None
        q = nearest(high, p, n)
        weights = {}
        for x, w in zip(voted_idx, voted_weights):
            if w:
                weights[x] = weights.get(x, 0) + w * (1 - mix)
        for x, w in zip(q[2], q[3]):
            if w:
                weights[x] = weights.get(x, 0) + w * mix
        top = sorted(weights.items(), key=lambda kv: -kv[1])[:4]
        total = sum(w for _, w in top)
        scaled = [round(w * 255 / total) for _, w in top]
        scaled[0] += 255 - sum(scaled)
        return [x for x, _ in top] + [fill] * (4 - len(top)), scaled + [0] * (4 - len(top))
    return lookup


def convert_vertices(src, k, template, slot, bone_map, offset, fit=None, weights_of=None):
    """Pack vertex buffer k -> the template slot's vertex layout (its declaration and stride), little-endian. fit /
    weights_of: neck_fitter / neck_weights (the skin)."""
    sd, dd = decl(src, '<', k), decl(template, T, slot)
    to, _ = of_type(template, T, VERTICES)[slot]
    out_stride = struct.unpack(T + 'IIII', template[to:to + 16])[2]
    o, _ = of_type(src, '<', VERTICES)[k]
    _, count, stride, _ = struct.unpack('<IIII', src[o:o + 16])
    floats = ('f32', 'f16')
    out = bytearray()
    for i in range(count):
        b = o + 16 + i * stride
        v = bytearray(out_stride)
        p = nrm = None
        for name, (doff, n, typ) in dd.items():
            if name in ('i0', 'w0'):
                continue
            if name not in sd:
                raise ValueError(f'vertex attribute {name} missing in the pack (mesh {k})')
            soff, sn, styp = sd[name]
            if typ in floats:
                if styp not in floats:
                    raise ValueError(f'vertex attribute {name}: {sn}{styp} in the pack, {n}{typ} in the game')
                vals = struct.unpack_from(f'<{sn}{"f" if styp == "f32" else "e"}', src, b + soff)
                vals = (vals + (1.0,) * n)[:n]  # 3 -> 4 (w = 1) or 4 -> 3
                if name == 'p0':
                    vals = tuple(c + d for c, d in zip(vals[:3], offset)) + vals[3:]
                    if fit:
                        vals = tuple(fit(vals[:3])) + vals[3:]
                    p = vals[:3]
                v[doff:doff + (4 if typ == 'f32' else 2) * n] = struct.pack(f'<{n}{"f" if typ == "f32" else "e"}', *vals)
            elif typ == 's10n' and styp == 's10n':
                v[doff:doff + 4] = src[b + soff:b + soff + 4]
                if name == 'n0':
                    nrm = s10n(struct.unpack_from('<I', src, b + soff)[0])
            else:
                raise ValueError(f'vertex attribute {name}: {sn}{styp} in the pack, {n}{typ} in the game')
        weights = {}
        for iname, wname in (('i0', 'w0'), ('i1', 'w1')):
            if iname not in sd:
                continue
            idx = struct.unpack_from(_index_format(sd[iname]), src, b + sd[iname][0])
            for x, w in zip(idx, src[b + sd[wname][0]:b + sd[wname][0] + 4]):
                if w:
                    weights[bone_map[x]] = weights.get(bone_map[x], 0) + w
        top = sorted(weights.items(), key=lambda kv: -kv[1])[:4]
        total = sum(w for _, w in top) or 1
        scaled = [round(w * 255 / total) for _, w in top]
        if scaled:
            scaled[0] += 255 - sum(scaled)
        # unused (zero weight) influences: the game's own files fill them in different ways (0, the last bone...);
        # the template's way (the palette's first bone)
        idx = [bone for bone, _ in top] + [palette_first(template, slot)] * (4 - len(top))
        scaled += [0] * (4 - len(scaled))
        copied = weights_of(p, nrm, idx, scaled) if weights_of else None
        if copied:
            idx, scaled = copied
        v[dd['i0'][0]:dd['i0'][0] + 4] = bytes(idx)
        v[dd['w0'][0]:dd['w0'][0] + 4] = bytes(scaled)
        out += v
    return count, out_stride, bytes(out)


def vertex_flag(template, slot):
    """4th word of the template's vertex buffer header (1 in FIFA 14's files)."""
    o, _ = of_type(template, T, VERTICES)[slot]
    return struct.unpack(T + 'I', template[o + 12:o + 16])[0]


def convert_indices(src, k):
    o, _ = of_type(src, '<', INDICES)[k]
    _, count = struct.unpack('<II', src[o:o + 8])
    if src[o + 8] != 2:
        raise ValueError('32-bit indices are not supported')
    return count, src[o + 16:o + 16 + 2 * count]


def rebuild(template, replace):
    """New RX3l from the template with these sections' contents replaced ({section index: bytes})."""
    secs = sections(template, T)
    head_size = 16 + 16 * len(secs)
    first = min(o for _, o, _, _ in secs)
    body, table, pos = bytearray(), [], first
    for i, (t, o, s, z) in enumerate(secs):
        data = replace.get(i, template[o:o + s])
        data = data + b'\0' * (-len(data) % 16)
        table.append(struct.pack(T + 'IIII', t, pos, len(data), z))
        body += data
        pos += len(data)
    out = template[:12] + struct.pack(T + 'I', len(secs)) + b''.join(table) + template[head_size:first] + body
    return bytearray(out[:8] + struct.pack(T + 'I', len(out)) + out[12:])


def convert_mesh(template, src, slot_of, offset, vote_slot=None, empty=(), skeleton=None, follow=None,
                 fit_neck=False, fit=None):
    """slot_of[k] = template mesh that receives pack mesh k; vote_slot = the pack mesh whose bones go by vote (the
    skin); empty = template slots the pack has nothing for (one zero-area triangle, none of the template's geometry
    left); skeleton = bind positions of the pack's bones when not its own (hair_skeleton); follow = {pack
    bone: template bone} that wins over the nearest bone (the hair follows the skin's head/jaw); fit_neck: the
    vote_slot mesh (the skin) gets the template's neck base shape and weights (neck_fitter, neck_weights); fit: function moving the
    positions of every mesh (the hair's nape: nape_follower)."""
    secs = sections(template, T)
    idx_of = {t: [i for i, s in enumerate(secs) if s[0] == t] for t in (HEADER, VERTICES, INDICES)}
    src_bones = [tuple(c + d for c, d in zip(b, offset)) for b in (skeleton or bone_positions(src, '<'))]
    dst_bones = bone_positions(template, T)
    header = bytearray(template[secs[idx_of[HEADER][0]][1]:][:secs[idx_of[HEADER][0]][2]])
    replace = {}
    for k, slot in enumerate(slot_of):
        allowed = sorted(used_bones(template, T, slot, decl(template, T, slot)))
        bone_map = nearest_map(src_bones, dst_bones, allowed)
        for b, t in (follow or {}).items():
            if b in bone_map and t in allowed:
                bone_map[b] = t
        if vote_slot == k:
            bone_map = vote_map(src, k, template, slot, offset, bone_map)
        neck = fit_neck and vote_slot == k
        count, stride, vb = convert_vertices(src, k, template, slot, bone_map, offset,
                                             neck_fitter(template, slot) if neck else fit,
                                             neck_weights(template, slot) if neck else None)
        replace[idx_of[VERTICES][slot]] = struct.pack(T + 'IIII', padded(16 + len(vb)), count, stride,
                                                         vertex_flag(template, slot)) + vb
        n_idx, ib = convert_indices(src, k)
        to = secs[idx_of[INDICES][slot]][1]
        size = padded(16 + len(ib))  # FIFA 14 keeps the padded size, in the section and in the header
        replace[idx_of[INDICES][slot]] = struct.pack(T + 'II', size, n_idx) + template[to + 8:to + 16] + ib
        struct.pack_into(T + 'II', header, 16 + 16 * slot, size, n_idx)
    for slot in empty:
        vo = secs[idx_of[VERTICES][slot]][1]
        _, _, stride, _ = struct.unpack(T + 'IIII', template[vo:vo + 16])
        vb = template[vo + 16:vo + 16 + stride] * 3
        replace[idx_of[VERTICES][slot]] = struct.pack(T + 'IIII', padded(16 + len(vb)), 3, stride,
                                                         vertex_flag(template, slot)) + vb
        ib = struct.pack(T + '3H', 0, 0, 0)  # degenerate: nothing drawn (validated in game)
        to = secs[idx_of[INDICES][slot]][1]
        size = padded(16 + len(ib))
        replace[idx_of[INDICES][slot]] = struct.pack(T + 'II', size, 3) + template[to + 8:to + 16] + ib
        struct.pack_into(T + 'II', header, 16 + 16 * slot, size, 3)
    replace[idx_of[HEADER][0]] = bytes(header)
    return bytes(rebuild(template, replace))


def nape_follower(template_head, head, offset, reach=3.0):
    """Function moving a hair point at the back of the neck by the shift neck_fitter gave the nearest skin vertex
    (fading out over `reach` cm away from the skin): hair that comes down the nape (some strands go down to
    161 cm) lay on the pack's nape, which the skin no longer has, and would float behind the neck."""
    fit = neck_fitter(template_head, HEAD_SLOTS['skin'])
    moved = []
    for p in positions(head, '<', 0):
        a = tuple(c + d for c, d in zip(p, offset))
        if a[1] < NAPE_FIT_TOP + 2:
            b = fit(a)
            if b != a:
                moved.append((a, tuple(y - x for x, y in zip(a, b))))

    def follow(p):
        if not moved or p[1] >= NAPE_FIT_TOP + 2:
            return p
        a, delta = min(moved, key=lambda m: sum((x - y) ** 2 for x, y in zip(p, m[0])))
        t = max(0.0, 1 - sum((x - y) ** 2 for x, y in zip(p, a)) ** 0.5 / reach)
        return tuple(c + d * t for c, d in zip(p, delta)) if t else p
    return follow


def skin_follow(template_head, head, offset):
    """{pack bone: template head or jaw bone} of the bones the skin's vote sends there: the hair hangs on them too,
    so it moves with the skin and not with a nearby facial bone."""
    slot = HEAD_SLOTS['skin']
    allowed = sorted(used_bones(template_head, T, slot, decl(template_head, T, slot)))
    src_bones = [tuple(c + d for c, d in zip(b, offset)) for b in bone_positions(head, '<')]
    voted = vote_map(head, 0, template_head, slot, offset,
                     nearest_map(src_bones, bone_positions(template_head, T), allowed))
    top, (jaw, _family) = template_head_bone(template_head), template_jaw(template_head)
    skin = set()
    for _, bw in vertex_bones(head, '<', 0, decl(head, '<', 0)):
        skin.update(bw)
    return {b: t for b, t in voted.items() if b in skin and t in (top, jaw)}


def needs_conversion(d: bytes) -> bool:
    """A mesh FIFA 14 cannot take as it is: the newer format, or FIFA 14's layout with broken data (sections not
    padded, bones outside the mesh's palette: a pack hair seen with every vertex on bone 9). A file that cannot be
    read as a mesh at all cannot be converted either: False (it goes as it is)."""
    try:
        return is_newer(d) or bool(check(d, d))
    except (ValueError, IndexError, KeyError, UnicodeDecodeError, struct.error):
        return False


def convert(tpl: dict, src: dict) -> dict:
    """{kind: RX3l bytes} of a pack face with its meshes in FIFA 14's format. tpl: the template's head, hair and
    hairlod (the game's files); src: the pack's files (kinds of fifa14.PLAYER_FACE_FILES). When any of its meshes
    needs it (needs_conversion), every mesh goes through the template (one skeleton for all); a face whose meshes
    are all fine is kept as it is. Textures are kept as they are; a part the pack does not bring stays missing.
    FaceFormatError: a face in a layout the converter does not know."""
    meshes = [k for k in MESHES if src.get(k)]
    if not any(needs_conversion(src[k]) for k in meshes):
        return dict(src)
    try:
        check_positions(src)
        return _convert(tpl, src)
    except FaceFormatError:
        raise
    except (ValueError, IndexError, KeyError, struct.error) as e:
        raise FaceFormatError(str(e)) from e


def _convert(tpl: dict, src: dict) -> dict:
    out = dict(src)
    head = head_mesh_first(src['head'])
    offset = align_offset(tpl['head'], head)
    out['head'] = convert_mesh(tpl['head'], head, [HEAD_SLOTS['skin'], HEAD_SLOTS['eyes']], offset, vote_slot=0,
                               fit_neck=True)
    follow = skin_follow(tpl['head'], head, offset)
    nape = nape_follower(tpl['head'], head, offset)
    hair = src.get('hair')
    if hair:
        tpl_parts, src_parts = hair_parts(tpl['hair']), hair_parts(hair)
        slot_of = [tpl_parts.get(next((p for p, i in src_parts.items() if i == k), None)) for k in
                   range(len(of_type(hair, '<', VERTICES)))]
        if None in slot_of:
            raise ValueError('hair submesh that is neither cap nor strands')
        empty = [tpl_parts[p] for p in tpl_parts if p not in src_parts]
        out['hair'] = convert_mesh(tpl['hair'], hair, slot_of, offset, empty=empty,
                                   skeleton=hair_skeleton(hair, head), follow=follow, fit=nape)
    lod = src.get('hairlod')
    if lod:
        out['hairlod'] = convert_mesh(tpl['hairlod'], lod, [0], offset,
                                      skeleton=hair_skeleton(lod, head), follow=follow, fit=nape)
    return out


def check(d: bytes, template: bytes) -> list[str]:
    """Problems of a converted RX3 against its template: same section types in the same order, sections aligned
    and padded to 16, the header's index sizes and counts equal to the index sections', vertex buffers that fit
    their sections, the template's vertex layout and flag, indices inside their vertex buffer, bones inside the
    mesh's palette."""
    out = []
    secs, tsecs = sections(d, T), sections(template, T)
    if [s[0] for s in secs] != [s[0] for s in tsecs]:
        out.append('section types differ from the template')
    if struct.unpack(T + 'I', d[8:12])[0] != len(d):
        out.append('file size in the header')
    for t, o, s, _ in secs:
        if o % 16 or s % 16 or o + s > len(d):
            out.append(f'section {t:08X} at {o} size {s}: not aligned or past the end')
    hdr = of_type(d, T, HEADER)[0][0]
    for k, (io, isz) in enumerate(of_type(d, T, INDICES)):
        size, count = struct.unpack(T + 'II', d[io:io + 8])
        if (size, count) != struct.unpack_from(T + 'II', d, hdr + 16 + 16 * k) or size != isz:
            out.append(f'mesh {k}: index sizes do not match the header')
        vo, vsz = of_type(d, T, VERTICES)[k]
        vsize, vcount, stride, flag = struct.unpack(T + 'IIII', d[vo:vo + 16])
        tvo = of_type(template, T, VERTICES)[k][0]
        _, _, tstride, tflag = struct.unpack(T + 'IIII', template[tvo:tvo + 16])
        if (stride, flag) != (tstride, tflag) or vsize != vsz or 16 + vcount * stride > vsz:
            out.append(f'mesh {k}: vertex buffer header')
        if decl(d, T, k) != decl(template, T, k):
            out.append(f'mesh {k}: vertex layout')
        idx = struct.unpack_from(T + '%dH' % count, d, io + 16)
        if idx and max(idx) >= vcount:
            out.append(f'mesh {k}: index past the vertex buffer')
        po, _ = of_type(d, T, PALETTE)[k]
        palette = set(d[po + 16 + 256:po + 16 + 256 + struct.unpack(T + 'I', d[po + 4:po + 8])[0]])
        dd = decl(d, T, k)
        for i in range(vcount):
            b = vo + 16 + i * stride
            for x, w in zip(d[b + dd['i0'][0]:b + dd['i0'][0] + 4], d[b + dd['w0'][0]:b + dd['w0'][0] + 4]):
                if w and x not in palette:
                    out.append(f'mesh {k}: bone {x} outside the palette')
                    break
            else:
                continue
            break
    return out


def game_template(files) -> dict | None:
    """{kind: RX3l bytes} of the game's TEMPLATE meshes (files: anything with read(game path)); None when the game
    lacks one of them."""
    out = {}
    for kind in MESHES:
        data = files.read(fifa14.PLAYER_FACE_FILES[kind].format(TEMPLATE))
        if data is None:
            return None
        out[kind] = rx3.unpack(data)
    return out


def face_needs_conversion(own: dict) -> bool:
    """A face ({kind of fifa14.PLAYER_FACE_FILES: bytes}, meshes packed or not) with a mesh FIFA 14 cannot take as
    it is (needs_conversion)."""
    for kind in MESHES:
        if own.get(kind):
            try:
                d = rx3.unpack(own[kind])
            except ValueError:
                continue
            if needs_conversion(d):
                return True
    return False


def convert_face(template: dict, own: dict) -> dict:
    """The face `own` with its meshes in FIFA 14's format (convert); the other files as they are."""
    meshes = {kind: rx3.unpack(own[kind]) for kind in MESHES if own.get(kind)}
    return {**own, **{kind: bytes(v) for kind, v in convert(template, meshes).items()}}
