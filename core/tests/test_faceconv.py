"""Pack faces in a newer FIFA format converted into FIFA 14's (f14mod.faceconv), on the synthetic faces of
tests/fakeface.py."""
import struct

import pytest

import fakeface
from f14mod import faceconv, rx3mesh


def _skin(d, slot):
    return faceconv.vertex_bones(d, '<', slot, faceconv.decl(d, '<', slot))


def test_a_face_in_fifa14s_format_is_kept_as_it_is():
    tpl = fakeface.template()
    own = dict(tpl, face=b'RX3l textures')
    assert not any(faceconv.needs_conversion(tpl[k]) for k in faceconv.MESHES)
    assert faceconv.convert(tpl, own) == own


def _quirky(d: bytes) -> bytes:
    """d with bytes past its header's file size and the palette of mesh 0 cut to one bone."""
    out = bytearray(d) + bytes(80)
    po, _ = faceconv.of_type(d, '<', faceconv.PALETTE)[0]
    struct.pack_into('<I', out, po + 4, 1)
    return bytes(out)


def test_a_head_with_the_quirks_the_game_takes_is_kept_as_it_is():
    tpl = fakeface.template()
    head = _quirky(tpl['head'])
    assert faceconv.check(head, head)  # the problems are there...
    assert faceconv.needs_conversion(head)  # ...and alone (no kind) they still count
    assert not faceconv.needs_conversion(head, 'head')
    assert not faceconv.face_needs_conversion(dict(tpl, head=head))
    # on hair they still do (a pack hair with its bones outside the palette)
    assert faceconv.face_needs_conversion(dict(tpl, hair=_quirky(tpl['hair'])))


def test_rx3b_with_little_endian_vertices():
    """Some RX3b files of PC patches have only the container big-endian: the vertex buffer's flag (and its
    vertices) are little-endian."""
    assert rx3mesh.vertex_endian(b'RX3b' + bytes(12) + struct.pack('<I', 1), 4) == '<'
    assert rx3mesh.vertex_endian(b'RX3b' + bytes(12) + struct.pack('>I', 1), 4) == '>'
    assert rx3mesh.vertex_endian(b'RX3l' + bytes(12) + struct.pack('<I', 1), 4) == '<'


def test_a_file_that_is_not_a_mesh_is_not_converted():
    assert not faceconv.needs_conversion(b'RX3l pack head')


def test_newer_meshes_come_out_in_the_templates_format():
    tpl, pack = fakeface.template(), fakeface.newer_pack_face()
    assert all(faceconv.needs_conversion(pack[k]) for k in faceconv.MESHES)
    out = faceconv.convert(tpl, pack)
    for kind in faceconv.MESHES:
        assert faceconv.check(out[kind], tpl[kind]) == [], kind
        assert not faceconv.needs_conversion(out[kind])
    # same vertices as the pack: skin (pack mesh 0) -> template slot 1, eyes -> slot 0
    assert len(_skin(out['head'], 1)) == len(_skin(pack['head'], 0))
    assert len(_skin(out['head'], 0)) == len(_skin(pack['head'], 1))
    # textures as they are
    assert out['face'] == pack['face'] and out['hair_textures'] == pack['hair_textures']


def test_the_neck_base_takes_the_templates_shape_and_weights():
    """The pack's head is wider than the template's: below the chin it is laid onto the template's neck (and hangs
    on its torso/neck bones), above the chin it keeps its own shape."""
    tpl, pack = fakeface.template(), fakeface.newer_pack_face()
    skin = _skin(faceconv.convert(tpl, pack)['head'], 1)

    def width(y):
        return max(abs(p[0]) for p, _ in skin if abs(p[1] - y) < 0.01)
    assert 6.7 < width(150) <= 7.0  # on the template's neck (radius 7, flat between its 12 vertices)
    assert width(180) == pytest.approx(7.8, abs=0.05)  # the pack's own
    assert all(set(bw) <= {0, 1} for p, bw in skin if p[1] < 157)


def test_the_jaw_goes_to_the_templates_jaw():
    tpl, pack = fakeface.template(), fakeface.newer_pack_face()
    skin = _skin(faceconv.convert(tpl, pack)['head'], 1)
    front = [bw for p, bw in skin if 160 < p[1] < 168 and p[2] > 3]
    assert front and all(3 in bw for bw in front)


def test_a_face_in_an_unknown_layout_raises_face_format_error():
    tpl, pack = fakeface.template(), fakeface.newer_pack_face()
    pack['head'] = fakeface.head_without_eyes()
    with pytest.raises(faceconv.FaceFormatError):
        faceconv.convert(tpl, pack)
