"""3D preview of a kit: game meshes as GLB, textures as PNG and the crest/name/numbers layer (fake installation
only)."""
import io
import json
import struct

import fakegame
import pytest
from PIL import Image

from f14mod import catalog, kitprint, preview, teamkits


@pytest.fixture
def files(game):
    return catalog.open_game(game)


def _glb_json(data: bytes) -> dict:
    assert data[:4] == b'glTF'
    length = struct.unpack('<I', data[12:16])[0]
    return json.loads(data[20:20 + length])


def test_mesh_glb_names_the_part_and_converts_to_meters(files):
    doc = _glb_json(preview.mesh_glb(files, 'shorts', 0))
    assert [n['name'] for n in doc['nodes']] == ['shorts']
    position = doc['accessors'][doc['meshes'][0]['primitives'][0]['attributes']['POSITION']]
    assert position['count'] == 3 and position['max'][1] == pytest.approx(1.1)
    assert 'TEXCOORD_0' in doc['meshes'][0]['primitives'][0]['attributes']


def test_texture_png_is_the_first_texture(files):
    img = Image.open(io.BytesIO(preview.texture_png(files, 'skin', 4)))
    assert img.mode == 'RGB' and img.getpixel((0, 0)) == (180, 120, 90)


def test_missing_parts_raise_preview_error(files):
    with pytest.raises(preview.PreviewError):
        preview.mesh_glb(files, 'jersey', 0, 3)
    with pytest.raises(preview.PreviewError):
        preview.mesh_glb(files, 'cape', 0)
    with pytest.raises(preview.PreviewError):
        preview.face_png(files, '12345')  # a real face the game does not have
    with pytest.raises(preview.PreviewError):
        preview.face_png(files, '../x')
    with pytest.raises(preview.PreviewError):
        preview.texture_png(files, 'tattoo', 1)


def _kit(files, team=None, kind=0):
    return files.read(teamkits.KIT_FILE.format(team or fakegame.TEAM, kind))


def test_decal_draws_number_and_crest_in_the_kit_rectangles(files):
    crest = Image.new('RGBA', (16, 16), (0, 0, 255, 255))
    values = {'number_font': 1, 'number_color': 1, 'shorts_number': True, 'shorts_number_font': 1,
              'shorts_number_color': 2, 'name_font': 2, 'show_name': True}
    # name_font 2 is not a real font: the name is left out, never a crash
    jersey = kitprint.decal(files, _kit(files), 'jersey', (100, 100), values, number=7, name='Test',
                            crest_picture=crest)
    assert jersey.getpixel((15, 15)) == (0, 0, 255, 255)  # crest: 'team' 0.1-0.2
    assert jersey.getpixel((40, 20))[:3] == (250, 250, 250)  # one digit centered in 'numberback' 0.3-0.5
    assert jersey.getpixel((90, 90))[3] == 0  # the rest stays transparent
    shorts = kitprint.decal(files, _kit(files, kind=1), 'shorts', (100, 50), values, number=7, crest_picture=crest)
    assert shorts.getpixel((35, 32))[:3] == (10, 10, 10)  # shorts number: color 2, chunked font file
    assert shorts.getpixel((15, 32)) == (0, 0, 255, 255)  # shorts crest


def test_decal_without_a_table_or_number_is_empty(files):
    blank = kitprint.decal(files, None, 'jersey', (32, 32), {})
    assert blank.getbbox() is None
    no_number = kitprint.decal(files, _kit(files), 'shorts', (32, 16), {'shorts_number': False}, number=9,
                               crest_picture=Image.new('RGBA', (4, 4), (0, 0, 0, 0)))
    assert no_number.getbbox() is None


def test_look_of_a_generic_player_a_real_face_and_the_model(files):
    raw = {'headclasscode': 1, 'headtypecode': 22, 'hairtypecode': 31, 'haircolorcode': 1, 'eyecolorcode': 3,
           'eyebrowcode': 1, 'sideburnscode': 0, 'facialhaircolorcode': 2, 'facialhairtypecode': 6,
           'skintypecode': 0, 'skintonecode': 3, 'jerseysleevelengthcode': 1, 'socklengthcode': 2,
           'shoetypecode': 99, 'gkglovetypecode': 0, 'height': 200}
    generic = preview.look(files, 8004, raw)
    assert generic['real'] is False and (generic['head'], generic['hair'], generic['eyes']) == (22, 31, 3)
    assert generic['face'] == '1_0_2_6_0_4'  # tone 3 has no face file: 4
    assert generic['hair_color'] == '#0e0e0d' and generic['sleeve'] == 1 and generic['socks'] == 2
    assert generic['shoe'] == 0 and generic['glove'] == 1 and generic['skin'] == 4  # no such files: the model's
    assert generic['scale'] == pytest.approx(200 / preview.MODEL_HEIGHT_CM, abs=1e-3)
    real = preview.look(files, fakegame.STAR, {**raw, 'headclasscode': 0})
    assert real['real'] is True and real['head'] == real['hair'] == real['eyes'] == fakegame.STAR
    assert real['face'] == str(fakegame.STAR)
    # a real face class without the files: the generic head
    assert preview.look(files, fakegame.KEEPER, {**raw, 'headclasscode': 0})['real'] is False
    model = preview.look(files, None, None)
    assert model['head'] == preview.MODEL_LOOK['headtypecode'] and model['face'] == '0_0_0_0_0_4'


def test_face_falls_back_to_the_plain_face_of_the_tone(files):
    img = Image.open(io.BytesIO(preview.face_png(files, '2_1_4_7_2_4')))
    assert img.getpixel((0, 0)) == (200, 150, 120)
