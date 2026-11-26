"""Players the user creates or changes: rows, traits, face (another player's or a pack's), photo, teams and the player
hidden in one team (fake installation only)."""
import io
import json
import os

import fakegame
import pytest
from PIL import Image, ImageStat

from f14mod import builder, catalog, facepack, fields, fifa14, t3db
from f14mod.project import BENCH, Project

NEW = 300001


@pytest.fixture
def installed(tmp_path):
    return fakegame.build_installed(str(tmp_path))


def _png(color, size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new('RGBA', size, color + (255,)).save(buf, 'PNG')
    return buf.getvalue()


def _build(installed, tmp_path, project):
    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db-meta.xml'), 'rb') as f:
        meta = t3db.load_meta(f.read())
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db.db'), 'rb') as f:
        tables = {name: t['rows'] for name, t in t3db.read_tables(f.read(), meta).items()}
    return summary, tables, patch_dir


def _patch_file(patch_dir, game_path):
    path = os.path.join(patch_dir, *game_path.split('/'))
    if not os.path.isfile(path):
        return None
    with open(path, 'rb') as f:
        return f.read()


def _row(tables, pid):
    return next(r for r in tables['players'] if r['playerid'] == pid)


def test_traits_keep_the_bits_the_app_does_not_know():
    raw = {'trait1': 1 << 14 | 1, 'trait2': 1 << 12}
    assert fields.traits_of(raw) == ['inflexible', 'flair']
    out = fields.trait_columns(raw, ['finesse_shot', 'team_player'])
    assert out == {'trait1': 1 << 13, 'trait2': 1 << 12 | 1 << 10}  # bit 12 of trait2 kept
    assert fields.clean('player', {'traits': []}, {'traits': ['flair']}) == {'traits': []}  # taking all away is kept
    with pytest.raises(fields.FieldError):
        fields.clean('player', {'traits': ['flying']}, {'traits': []})


def test_created_player_with_traits_face_photo_and_teams(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('player', NEW, fields={'name.first': 'Novo', 'name.last': 'Craque', 'traits': ['flair', 'diver'],
                                          'height': 190, 'face': {'source': 'player', 'player': fakegame.STAR}})
    project.set_player_source(NEW, fakegame.KEEPER)
    project.set_picture('player', NEW, 'photo', _png((0, 200, 0)))
    # he joins the team on the bench; another player stays in the squad on the screen but is out of the patch
    squad = [{'player': fakegame.STAR, 'jersey': 10, 'slot': 25}, {'player': fakegame.KEEPER, 'jersey': 1, 'slot': 0},
             *({'player': p, 'jersey': i + 2, 'slot': 28} for i, p in enumerate(range(8004, 8014))),
             {'player': 8014, 'jersey': 40, 'slot': 28, 'hidden': True},
             {'player': NEW, 'jersey': 77, 'slot': BENCH}]
    project.set_roster(fakegame.TEAM, squad)
    assert project.roster(fakegame.TEAM)[-2]['hidden'] is True
    summary, tables, patch_dir = _build(installed, tmp_path, project)
    row = _row(tables, NEW)
    keeper = _row(tables, fakegame.KEEPER)
    assert row['preferredposition1'] == keeper['preferredposition1']  # the row of the player he starts from
    assert row['height'] == 190 and row['headclasscode'] == 0
    assert row['trait1'] == 1 << 14 | 1 << 3 and row['trait2'] == 1 << 12
    names = {r['nameid']: r['name'] for r in tables['playernames']}
    assert names[row['firstnameid']] == 'Novo' and names[row['lastnameid']] == 'Craque'
    # the star's face files under the new id
    star_head = catalog.open_game(installed).read(fifa14.PLAYER_FACE_FILES['head'].format(fakegame.STAR))
    assert star_head and _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES['head'].format(NEW)) == star_head
    photo = _patch_file(patch_dir, fifa14.PHOTO.format(NEW))
    assert photo[:4] == b'DDS '
    links = {(r['teamid'], r['playerid']): r for r in tables['teamplayerlinks']}
    assert links[(fakegame.TEAM, NEW)]['jerseynumber'] == 77
    assert (fakegame.TEAM, 8014) not in links  # hidden in this team
    assert summary['database']['created']['player'] == 1


def test_hidden_created_player_is_left_out(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('player', NEW, fields={'name.common': 'Fantasma'})
    project.set_player_source(NEW, fakegame.KEEPER)
    squad = [{'player': p, 'jersey': i + 1, 'slot': 28} for i, p in enumerate(range(8004, 8016))]
    project.set_roster(fakegame.TEAM, squad + [{'player': NEW, 'jersey': 50, 'slot': 28}])
    project.set_hidden('player', NEW, True)
    _summary, tables, _patch = _build(installed, tmp_path, project)
    assert not any(r['playerid'] == NEW for r in tables['players'])
    assert not any(r['playerid'] == NEW for r in tables['teamplayerlinks'])
    project.delete('player', NEW)  # deleting takes him out of every squad
    assert all(r['player'] != NEW for r in project.roster(fakegame.TEAM))


def test_original_player_generic_head_and_pack_face(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save('player', fakegame.STAR, None, {'face': {'source': 'generic'}, 'hairtypecode': 12})
    files = {'head': b'RX3l pack head', 'face': b'RX3l pack face', 'hair': b'RX3l pack hair'}
    project.save('player', fakegame.KEEPER, None, {'face': {'source': 'pack', 'pack': 'x', 'id': 51318}})
    project.set_player_files(fakegame.KEEPER, files)
    _summary, tables, patch_dir = _build(installed, tmp_path, project)
    assert _row(tables, fakegame.STAR)['headclasscode'] == 1 and _row(tables, fakegame.STAR)['hairtypecode'] == 12
    assert _row(tables, fakegame.KEEPER)['headclasscode'] == 0
    for kind, data in files.items():
        assert _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES[kind].format(fakegame.KEEPER)) == data
    project.reset('player', fakegame.KEEPER)
    assert project.player_files(fakegame.KEEPER) == {}


def test_parts_a_face_lacks_are_removed_never_taken_from_the_game(installed, tmp_path):
    """STAR has his whole real face in data1.big. A pack face with only head + face textures goes without the rest:
    the game must not find his own hair, hair LOD and eyes any more (tested in the game: no hair model drawn,
    checkered eyes), so their .bh records are zeroed and no loose file is written for them."""
    from f14mod import bh
    from f14mod.big import BigArchive
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save('player', fakegame.STAR, None, {'face': {'source': 'pack', 'pack': 'x', 'id': 51318}})
    project.set_player_files(fakegame.STAR, {'head': b'RX3l pack head', 'face': b'RX3l pack face'})
    summary, _tables, patch_dir = _build(installed, tmp_path, project)
    gone = {fifa14.PLAYER_FACE_FILES[k].format(fakegame.STAR) for k in ('eyes', 'hair', 'hair_textures')}
    assert gone <= set(summary['removed'])
    for path in gone:
        assert not os.path.exists(os.path.join(patch_dir, *path.split('/')))
    archive = BigArchive(os.path.join(installed, 'data1.big'))
    with open(os.path.join(patch_dir, 'data1.bh'), 'rb') as f:
        zeroed = {archive.order[i] for i in bh.zeroed(f.read())}
    assert gone <= zeroed  # with the head and face textures (written loose)
    assert fifa14.PLAYER_FACE_FILES['head'].format(fakegame.STAR) in zeroed

def test_pack_face_in_a_newer_format_is_converted_on_build(installed, tmp_path):
    """FIFA 14 crashes on the meshes of the newer packs: the build converts them on the game's template
    (f14mod.faceconv); the textures go as they are."""
    import fakeface
    from f14mod import faceconv
    project = Project(str(tmp_path / 'p.sqlite'))
    pack = fakeface.newer_pack_face()
    project.save('player', fakegame.KEEPER, None, {'face': {'source': 'pack', 'pack': 'x', 'id': 51318}})
    project.set_player_files(fakegame.KEEPER, pack)
    _summary, _tables, patch_dir = _build(installed, tmp_path, project)
    template = fakeface.template()
    for kind in faceconv.MESHES:
        made = _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES[kind].format(fakegame.KEEPER))
        assert made != pack[kind] and not faceconv.is_newer(made)
        assert faceconv.check(made, template[kind]) == []
    for kind in ('face', 'hair_textures'):
        assert _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES[kind].format(fakegame.KEEPER)) == pack[kind]


def test_pack_face_the_converter_cannot_handle_stops_the_build(installed, tmp_path):
    import fakeface
    project = Project(str(tmp_path / 'p.sqlite'))
    pack = dict(fakeface.newer_pack_face(), head=fakeface.head_without_eyes())
    project.save('player', fakegame.KEEPER, None, {'face': {'source': 'pack', 'pack': 'x', 'id': 51318}})
    project.set_player_files(fakegame.KEEPER, pack)
    with pytest.raises(builder.BuildError) as e:
        _build(installed, tmp_path, project)
    assert (e.value.code, e.value.detail) == ('player_face_format', str(fakegame.KEEPER))


def test_face_without_files_cannot_be_built(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save('player', fakegame.KEEPER, None, {'face': {'source': 'pack', 'pack': 'x', 'id': 1}})
    with pytest.raises(builder.BuildError) as e:
        _build(installed, tmp_path, project)
    assert e.value.code == 'player_face_missing'


def test_face_pack_reader(tmp_path):
    pack = tmp_path / 'Pack' / 'data' / 'sceneassets'
    for kind in ('head', 'face', 'hair'):
        path = pack / facepack.FILES[kind].format(77)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'RX3l ' + kind.encode())
    (pack / facepack.FILES['head'].format(78)).write_bytes(b'RX3l lonely head')  # no face texture: not listed
    (tmp_path / 'Pack' / 'data' / 'manifest.json').write_text(json.dumps(
        {'type': 'faces', 'credits': 'Maker', 'faces': [{'id': 77, 'name': 'Someone'}]}), encoding='utf-8')
    parts = facepack.find_parts(str(tmp_path))
    assert [label for _p, label in parts] == ['Pack']
    assets = parts[0][0]
    assert [f['id'] for f in facepack.list_faces(assets)] == [77]
    # what the face does not bring is listed (the app never fills it in)
    assert facepack.list_faces(assets)[0]['missing'] == ['eyes', 'hair_textures', 'hairlod']
    manifest, warnings = facepack.read_manifest(assets, str(tmp_path))
    assert manifest == {77: {'name': 'Someone', 'credits': 'Maker'}} and warnings == []
    assert set(facepack.read_face(assets, 77)) == {'head', 'face', 'hair'}


# ---- a face that lacks parts, filled in with the game's generic eyes and hair (facefill)

def _fill_project(tmp_path, fill, color=None):
    project = Project(str(tmp_path / 'p.sqlite'))
    face = {'source': 'pack', 'pack': 'x', 'id': 51318, **({'fill': fill} if fill else {})}
    values = {'face': face, **({'haircolorcode': color} if color is not None else {})}
    project.save('player', fakegame.KEEPER, None, values)
    project.set_player_files(fakegame.KEEPER, {'head': b'RX3l head', 'face': b'RX3l face', 'hair_textures': b'RX3l old'})
    return project


def test_face_fill_is_checked():
    assert fields.check_face({'source': 'pack', 'pack': 'x', 'id': 1, 'fill': {'eyes': 5, 'hair': 12}})['fill'] == {'eyes': 5, 'hair': 12}
    assert 'fill' not in fields.check_face({'source': 'pack', 'pack': 'x', 'id': 1, 'fill': {}})
    assert 'fill' not in fields.check_face({'source': 'generic', 'fill': {'eyes': 5}})  # only a pack face has one
    for bad in ({'eyes': 0}, {'eyes': True}, {'hair': 'a'}, {'hair': 99999}, [5]):
        with pytest.raises(fields.FieldError):
            fields.check_face({'source': 'pack', 'pack': 'x', 'id': 1, 'fill': bad})


def test_face_fill_of_the_hair_from_afar_alone():
    pack = {'source': 'pack', 'pack': 'x', 'id': 1}
    assert fields.check_face({**pack, 'fill': {'hairlod': 12}})['fill'] == {'hairlod': 12}
    # the whole hair brings its own from afar
    assert fields.check_face({**pack, 'fill': {'hair': 3, 'hairlod': 12}})['fill'] == {'hair': 3}
    from f14mod import facefill
    assert facefill.covered({'hairlod': 12}) == {'hairlod'}


def test_fill_only_the_hair_from_afar_keeps_the_pack_hair(installed, tmp_path):
    from f14mod import facefill
    project = _fill_project(tmp_path, {'hairlod': fakegame.GENERIC_HAIR})
    _summary, _tables, patch_dir = _build(installed, tmp_path, project)
    made = lambda kind: _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES[kind].format(fakegame.KEEPER))  # noqa: E731
    files = catalog.open_game(installed)
    assert made('hairlod') == files.read(facefill.HAIR_PATHS['hairlod'].format(fakegame.GENERIC_HAIR))
    assert made('hair_textures') == b'RX3l old'
    assert facefill.hairlod_codes(files) == [fakegame.GENERIC_HAIR]


def test_the_game_has_generic_parts_to_fill_with(installed):
    from f14mod import facefill
    files = catalog.open_game(installed)
    assert facefill.eyes_codes(files) == [fakegame.GENERIC_EYES]
    assert facefill.hair_codes(files) == [fakegame.GENERIC_HAIR]
    assert facefill.covered({'eyes': 1, 'hair': 2}) == {'eyes', 'hair', 'hair_textures', 'hairlod'}


def test_fill_brings_the_games_eyes_and_paints_the_hair(installed, tmp_path):
    from f14mod import facefill, preview, rx3
    project = _fill_project(tmp_path, {'eyes': fakegame.GENERIC_EYES, 'hair': fakegame.GENERIC_HAIR}, color=7)
    _summary, _tables, patch_dir = _build(installed, tmp_path, project)
    files = catalog.open_game(installed)
    made = lambda kind: _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES[kind].format(fakegame.KEEPER))  # noqa: E731
    game = lambda path: files.read(path)  # noqa: E731
    assert made('eyes') == game(facefill.EYES_PATH.format(fakegame.GENERIC_EYES))
    assert made('hair') == game(facefill.HAIR_PATHS['hair'].format(fakegame.GENERIC_HAIR))
    assert made('hairlod') == game(facefill.HAIR_PATHS['hairlod'].format(fakegame.GENERIC_HAIR))
    assert made('head') == b'RX3l head' and made('face') == b'RX3l face'
    # the pack's own hair texture gives way to the game's, painted with his hair color (the game's table)
    original = game(facefill.HAIR_PATHS['hair_textures'].format(fakegame.GENERIC_HAIR))
    painted = made('hair_textures')
    assert painted != original and len(painted) == len(original) and painted != b'RX3l old'
    before, after = (rx3.to_image(d, rx3.by_name(d, 'hair_cm')).convert('RGBA') for d in (original, painted))
    r, g, b, _a = ImageStat.Stat(after).mean
    want = preview.HAIR_COLORS[7]
    assert abs(r - (want >> 16)) < 25 and abs(g - ((want >> 8) & 255)) < 25 and abs(b - (want & 255)) < 25
    assert after.getchannel('A').tobytes() == before.getchannel('A').tobytes()  # the game's alpha is kept


def test_fill_only_the_eyes_keeps_the_pack_hair(installed, tmp_path):
    from f14mod import facefill
    project = _fill_project(tmp_path, {'eyes': fakegame.GENERIC_EYES})
    _summary, _tables, patch_dir = _build(installed, tmp_path, project)
    made = lambda kind: _patch_file(patch_dir, fifa14.PLAYER_FACE_FILES[kind].format(fakegame.KEEPER))  # noqa: E731
    assert made('eyes') == catalog.open_game(installed).read(facefill.EYES_PATH.format(fakegame.GENERIC_EYES))
    assert made('hair_textures') == b'RX3l old'  # the pack's own, as it was
    assert not os.path.exists(os.path.join(patch_dir, *fifa14.PLAYER_FACE_FILES['hair'].format(fakegame.KEEPER).split('/')))


def test_fill_with_a_part_the_game_lacks_stops_the_build(installed, tmp_path):
    project = _fill_project(tmp_path, {'eyes': 6})
    with pytest.raises(builder.BuildError) as e:
        _build(installed, tmp_path, project)
    assert e.value.code == 'player_face_fill'


def test_blank_player_out_until_complete_then_neutral(installed, tmp_path):
    """A player made from scratch (no template) is left out while nationality or position is missing; then his row
    has the neutral values (fields.PLAYER_DEFAULTS), not the model player's."""
    from f14mod import fields
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('player', NEW, fields={'name.common': 'A01 Blank', 'face': {'source': 'generic'}})
    project.set_player_source(NEW, None)
    squad = [{'player': p, 'jersey': i + 1, 'slot': 28} for i, p in enumerate(range(8004, 8016))]
    project.set_roster(fakegame.TEAM, squad + [{'player': NEW, 'jersey': 50, 'slot': 28}])
    assert project.incomplete_players() == {NEW}
    _summary, tables, _patch = _build(installed, tmp_path, project)
    assert not any(r['playerid'] == NEW for r in tables['players'])
    assert not any(r['playerid'] == NEW for r in tables['teamplayerlinks'])

    project.save('player', NEW, fields={'name.common': 'A01 Blank', 'face': {'source': 'generic'},
                                        'nationality': 54, 'preferredposition1': 25})
    assert project.incomplete_players() == set()
    _summary, tables, _patch = _build(installed, tmp_path / 'b', project)
    row = _row(tables, NEW)
    assert (row['nationality'], row['preferredposition1']) == (54, 25)
    for column, value in fields.player_blank_columns().items():
        if value is not None and column in row and column not in ('nationality', 'preferredposition1'):
            assert row[column] == value, column
