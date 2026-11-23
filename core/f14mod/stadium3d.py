"""A stadium of the game as one binary glTF (GLB) for the 3D preview: its meshes with their textures.

stadium_<id>.rx3 (sections: u32 type, offset, size, 0):
  0xC28193F0 / 0x005878F4 / 0x00587AA1  declaration, indices and vertices of each mesh (rx3mesh); positions in cm, y up;
                                        t0 = UV of the diffuse texture, t1 = UV of the baked light
  0x075BD958  materials: u32 size, u32 slot count, 8 bytes, shader name\\0, then per slot: slot name\\0 + u32 index into
              the scene's texture names (the 0x7A0B60DA entries of the names section). Slots: diffuseTexture,
              ambientTexture (the baked light, 2nd UV), normalMap, coeffMap, alphamask...
  0x7E2480EC  scene nodes: u32 size, 1, -1, 0, 4x4 matrix, bounding box (8 floats), u32 count, -1, then per
              renderable: bounding box (8 floats), u32 mesh index, u32 material index
stadium_<id>_<tod>_textures.rx3 (1 = day, 3 = night): the same texture names as the scene, in another order (found by
name).

The GLB has one node per renderable; each material carries the diffuse texture (baseColorTexture) and the baked light
(occlusionTexture on TEXCOORD_1), which the viewer applies as a light map (so no normals: nothing is lit). Not in it: the sky dome, the crowd and the
pitch's grass (the game makes them at run time; the pitch is a flat green).
"""
import io
import json
import struct

import numpy as np
from PIL import Image

from . import rx3, rx3mesh

SCENE = 'data/sceneassets/stadium/stadium_{}.rx3'
TEXTURES = 'data/sceneassets/stadium/stadium_{}_{}_textures.rx3'  # stadium, time of day
TIMES = (1, 3)  # day, night
MATERIAL, NODE, TEXTURE_NAME = 0x075BD958, 0x7E2480EC, 0x7A0B60DA
CM_TO_M = 0.01
MAX_TEXTURE = 512  # the preview's textures are scaled down to this side (a stadium has 150-300 textures)
MAX_LIGHT = 256  # the baked light is soft: smaller still
SKIPPED_SHADERS = ('sky',)
PITCH_COLOR = [0.25, 0.45, 0.18, 1]


class StadiumError(LookupError):
    """The game has no such stadium file (or it cannot be read)."""


def _sections(d):
    return rx3mesh._sections(d)  # noqa: SLF001 - the same section table


def materials(d) -> list[dict]:
    """[{'shader', 'slots': {slot: index into texture_names}}] in file order."""
    out = []
    for kind, off, size, _ in _sections(d):
        if kind != MATERIAL:
            continue
        b = d[off:off + size]
        count = struct.unpack('<I', b[4:8])[0]
        end = b.index(b'\0', 16)
        shader, p, slots = b[16:end].decode('ascii', 'replace'), end + 1, {}
        for _ in range(count):
            end = b.index(b'\0', p)
            slots[b[p:end].decode('ascii', 'replace')] = struct.unpack('<I', b[end + 1:end + 5])[0]
            p = end + 5
        out.append({'shader': shader, 'slots': slots})
    return out


def renderables(d) -> list[tuple[int, int]]:
    """[(mesh index, material index)] of every scene node."""
    out = []
    for kind, off, _, _ in _sections(d):
        if kind != NODE:
            continue
        p = off + 16 + 64 + 32
        count = struct.unpack('<I', d[p:p + 4])[0]
        p += 8
        for _ in range(count):
            out.append(struct.unpack('<II', d[p + 32:p + 40]))
            p += 40
    return out


def texture_names(d) -> list[str]:
    """The scene's texture names (what the material slots index)."""
    for kind, off, _, _ in _sections(d):
        if kind == rx3mesh.NAMES:
            count = struct.unpack('<I', d[off + 4:off + 8])[0]
            p, out = off + 16, []
            for _ in range(count):
                entry, length = struct.unpack('<II', d[p:p + 8])
                if entry == TEXTURE_NAME:
                    out.append(d[p + 8:p + 8 + length].split(b'\0')[0].decode('ascii', 'replace'))
                p += 8 + length
            return out
    return []


def _encode(img: Image.Image, side: int) -> tuple[bytes, str]:
    """(bytes, mime) of a texture at most `side` pixels wide: JPEG when opaque, PNG when its alpha matters."""
    img.thumbnail((side, side))
    buf = io.BytesIO()
    if img.mode == 'RGBA' and img.getextrema()[3][0] < 250:
        img.save(buf, 'PNG', optimize=True)
        return buf.getvalue(), 'image/png'
    img.convert('RGB').save(buf, 'JPEG', quality=80)
    return buf.getvalue(), 'image/jpeg'


class _Glb:
    def __init__(self):
        self.buf = bytearray()
        self.views, self.accessors = [], []

    def view(self, data: bytes, target=None) -> int:
        self.buf.extend(b'\0' * (-len(self.buf) % 4))
        v = {'buffer': 0, 'byteOffset': len(self.buf), 'byteLength': len(data)}
        if target:
            v['target'] = target
        self.views.append(v)
        self.buf.extend(data)
        return len(self.views) - 1

    def accessor(self, arr: np.ndarray, comp: int, type_: str, target: int, minmax=False) -> int:
        a = {'bufferView': self.view(arr.tobytes(), target), 'componentType': comp, 'count': len(arr), 'type': type_}
        if minmax:
            a['min'], a['max'] = arr.min(axis=0).tolist(), arr.max(axis=0).tolist()
        self.accessors.append(a)
        return len(self.accessors) - 1

    def write(self, doc: dict) -> bytes:
        doc.update({'accessors': self.accessors, 'bufferViews': self.views,
                    'buffers': [{'byteLength': len(self.buf)}]})
        js = json.dumps(doc, separators=(',', ':')).encode()
        js += b' ' * (-len(js) % 4)
        self.buf.extend(b'\0' * (-len(self.buf) % 4))
        total = 12 + 8 + len(js) + 8 + len(self.buf)
        return (struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(js), b'JSON') + js +
                struct.pack('<I4s', len(self.buf), b'BIN\0') + bytes(self.buf))


def available(files, sid: int) -> list[int]:
    """The times of day (TIMES) the stadium can be shown at: its scene and that time's textures exist."""
    if not files.exists(SCENE.format(sid)):
        return []
    return [t for t in TIMES if files.exists(TEXTURES.format(sid, t))]


def glb(files, sid: int, tod: int = 1) -> bytes:
    """The stadium as a GLB (meters, y up); raises StadiumError."""
    scene, textures = files.read(SCENE.format(sid)), files.read(TEXTURES.format(sid, tod))
    if scene is None or textures is None:
        raise StadiumError(f'stadium {sid} ({tod})')
    try:
        d, t = rx3.unpack(scene), rx3.unpack(textures)
        meshes, mats, links, names = rx3mesh.meshes(d), materials(d), renderables(d), texture_names(d)
        by_name = {x.get('name'): x for x in rx3.textures(t)}
    except (ValueError, IndexError, KeyError) as e:  # struct.error is a ValueError
        raise StadiumError(f'stadium {sid}: {e}') from e
    out = _Glb()
    images, gl_textures, gl_materials, gl_meshes, nodes = [], [], [], [], []
    texture_of: dict[int, int | None] = {}

    def texture(i: int, side: int = MAX_TEXTURE) -> int | None:
        if i not in texture_of:
            found = by_name.get(names[i]) if i < len(names) else None
            texture_of[i] = None
            if found is not None:
                try:
                    data, mime = _encode(rx3.to_image(t, found).convert('RGBA'), side)
                except (OSError, ValueError, KeyError, IndexError):
                    return None
                images.append({'bufferView': out.view(data), 'mimeType': mime})
                gl_textures.append({'source': len(images) - 1, 'sampler': 0})
                texture_of[i] = len(gl_textures) - 1
        return texture_of[i]

    material_of: dict[int, int] = {}

    def material(k: int) -> int:
        if k not in material_of:
            m = mats[k] if k < len(mats) else {'shader': '', 'slots': {}}
            slots, pbr = m['slots'], {'metallicFactor': 0, 'roughnessFactor': 1}
            g = {'name': m['shader'], 'doubleSided': True, 'pbrMetallicRoughness': pbr}
            if m['shader'].startswith('pitch'):
                pbr['baseColorFactor'] = PITCH_COLOR  # the grass is drawn by the game
            elif 'diffuseTexture' in slots and (tex := texture(slots['diffuseTexture'])) is not None:
                pbr['baseColorTexture'] = {'index': tex}
            if 'ambientTexture' in slots and (tex := texture(slots['ambientTexture'], MAX_LIGHT)) is not None:
                g['occlusionTexture'] = {'index': tex, 'texCoord': 1}
            if 'alpha' in m['shader'] or 'glass' in m['shader']:
                g['alphaMode'], g['alphaCutoff'] = 'MASK', 0.4
            gl_materials.append(g)
            material_of[k] = len(gl_materials) - 1
        return material_of[k]

    for mesh_i, mat_i in links:
        if mesh_i >= len(meshes) or (mat_i < len(mats) and mats[mat_i]['shader'] in SKIPPED_SHADERS):
            continue
        a = meshes[mesh_i]['attrs']
        if 'p0' not in a or not meshes[mesh_i]['indices']:
            continue
        pos = np.asarray([p[:3] for p in a['p0']], dtype='<f4') * CM_TO_M
        attrs = {'POSITION': out.accessor(pos, 5126, 'VEC3', 34962, minmax=True)}
        for key, attr in (('t0', 'TEXCOORD_0'), ('t1', 'TEXCOORD_1')):
            if key in a:
                attrs[attr] = out.accessor(np.asarray([v[:2] for v in a[key]], dtype='<f4'), 5126, 'VEC2', 34962)
        idx = np.asarray(meshes[mesh_i]['indices'], dtype='<u4')
        small = idx.max() <= 0xFFFF
        ind = out.accessor(idx.astype('<u2') if small else idx, 5123 if small else 5125, 'SCALAR', 34963)
        gl_meshes.append({'primitives': [{'attributes': attrs, 'indices': ind, 'mode': 4,
                                          'material': material(mat_i)}]})
        nodes.append({'mesh': len(gl_meshes) - 1, 'name': meshes[mesh_i]['name']})
    if not nodes:
        raise StadiumError(f'stadium {sid}: no meshes')
    doc = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes,
           'meshes': gl_meshes, 'materials': gl_materials, 'textures': gl_textures, 'images': images,
           'samplers': [{'wrapS': 10497, 'wrapT': 10497}]}
    return out.write(doc)
