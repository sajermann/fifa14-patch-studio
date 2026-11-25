"""Stadiums: their fields and names, and the stadium a team plays in, written into the patch (fake installation)."""
import os

import fakegame
import pytest

from f14mod import builder, catalog, fields, t3db
from f14mod.big import BigArchive
from f14mod.project import Project


@pytest.fixture
def installed(tmp_path):
    return fakegame.build_installed(str(tmp_path))


def _tables(patch_dir):
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db-meta.xml'), 'rb') as f:
        meta = t3db.load_meta(f.read())
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db.db'), 'rb') as f:
        return t3db.read_tables(f.read(), meta)


def test_stadium_fields_names_and_team_stadium(installed, tmp_path):
    project = Project(str(tmp_path / 'project.sqlite'))
    project.save('stadium', 3, names={'full': {'eng_us': 'A01 Arena'}},
                 fields={'name': 'A01 Ground', 'capacity': 40000, 'timeofday2': 5, 'tod1weather': 2})
    project.set_team_stadium(fakegame.SMALL_TEAM, 3)  # a team without a stadium row gets one
    assert project.counts() == {'stadium': 1, 'team': 1}
    assert project.dates('team', fakegame.SMALL_TEAM)[0] is None and project.dates('team', fakegame.SMALL_TEAM)[1]

    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    assert summary['database']['changed'] == {'stadium': 1} and summary['database']['team_stadiums'] == 1
    tables = _tables(patch_dir)
    row = next(r for r in tables['stadiums']['rows'] if r['stadiumid'] == 3)
    assert (row['name'], row['capacity'], row['timeofday2'], row['tod1weather']) == ('A01 Ground', 40000, 5, 2)
    links = {r['teamid']: r['stadiumid'] for r in tables['teamstadiumlinks']['rows']}
    assert links == {fakegame.TEAM: 3, fakegame.SMALL_TEAM: 3}
    loc = BigArchive(os.path.join(patch_dir, 'data', 'loc', 'locale.big'))
    en = t3db.read_strings(loc.read('data/loc/eng_us.db'), lambda s: True)
    assert en['StadiumName_3'] == 'A01 Arena'


def test_team_stadium_undone_leaves_the_project(tmp_path):
    project = Project(str(tmp_path / 'project.sqlite'))
    project.set_team_stadium(7, 3)
    assert project.team_stadium(7) == 3 and project.counts() == {'team': 1}
    project.reset('team', 7)
    assert project.team_stadium(7) is None and project.counts() == {} and project.dates('team', 7) == (None, None)


def test_stadium_fields_are_checked():
    assert fields.clean('stadium', {'capacity': 1000, 'timeofday1': 1}, {'capacity': 12345, 'timeofday1': 1}) == \
        {'capacity': 1000}
    with pytest.raises(fields.FieldError):
        fields.clean('stadium', {'timeofday1': 2}, {})  # not a time of day the game uses
    with pytest.raises(fields.FieldError):
        fields.clean('stadium', {'yearbuilt': 1700}, {})


# ---- stadiums the user creates -------------------------------------------------------------------------------

NEW = 266


def _stadium_folder(root, sid=158, colour=(200, 0, 0, 255)):
    """A downloaded stadium's folder (any layout): scene, day textures, crowd, glares and a large menu picture."""
    import io

    from PIL import Image
    folder = os.path.join(root, 'A01 Stadium', 'sceneassets')
    for sub, name, data in (('stadium', f'stadium_{sid}.rx3', b'A01 scene'),
                            ('stadium', f'stadium_{sid}_1_textures.rx3', b'A01 day textures'),
                            ('crowdplacement', f'crowd_{sid}_1.dat', b'A01 crowd'),
                            ('fx', f'glares_{sid}_1.lnx', f'<Effect name="glares_{sid}_1"><p index="{sid}"/>'.encode()),
                            ('fx', f'glares_{sid}_1.rx3', b'A01 glares'),
                            ('fx', 'readme.txt', b'not a stadium file')):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
        with open(os.path.join(folder, sub, name), 'wb') as f:
            f.write(data)
    buf = io.BytesIO()
    Image.new('RGBA', (64, 32), colour).save(buf, 'DDS', pixel_format='DXT5')
    os.makedirs(os.path.join(root, 'A01 Stadium', 'ui'), exist_ok=True)
    fakegame.write_big(os.path.join(root, 'A01 Stadium', 'ui', f'st_{sid}_1.big'),
                       {'0': b'Apt Data:fake screen', '2': buf.getvalue()})
    return os.path.join(root, 'A01 Stadium')


def test_stadium_folder_is_read_with_the_id_marked(tmp_path):
    from f14mod import stadium_files
    sid, found = stadium_files.read_folder(_stadium_folder(str(tmp_path)))
    assert sid == 158
    assert sorted(found) == ['data/sceneassets/crowdplacement/crowd_#_1.dat', 'data/sceneassets/fx/glares_#_1.lnx',
                             'data/sceneassets/fx/glares_#_1.rx3', 'data/sceneassets/stadium/stadium_#.rx3',
                             'data/sceneassets/stadium/stadium_#_1_textures.rx3',
                             'data/ui/artassets/stadiumsbig/st_#_1.big']
    # the effect takes the new id; the parameter indices (also 158) stay
    assert found['data/sceneassets/fx/glares_#_1.lnx'] == b'<Effect name="glares_#_1"><p index="158"/>'


def test_stadium_folder_errors(tmp_path):
    from f14mod import stadium_files
    for folder, code in ((str(tmp_path / 'missing'), 'folder_missing'), (str(tmp_path), 'no_stadium')):
        with pytest.raises(stadium_files.StadiumFolderError) as e:
            stadium_files.read_folder(folder)
        assert e.value.code == code
    _stadium_folder(str(tmp_path / 'one'), 158)
    _stadium_folder(str(tmp_path / 'two'), 159)
    with pytest.raises(stadium_files.StadiumFolderError) as e:
        stadium_files.read_folder(str(tmp_path))
    assert e.value.code == 'several_stadiums'
    os.remove(os.path.join(str(tmp_path / 'one'), 'A01 Stadium', 'sceneassets', 'stadium', 'stadium_158_1_textures.rx3'))
    with pytest.raises(stadium_files.StadiumFolderError) as e:
        stadium_files.read_folder(str(tmp_path / 'one'))
    assert e.value.code == 'no_textures'


def _created(tmp_path, with_scene=True):
    from f14mod import stadium_files
    project = Project(str(tmp_path / 'project.sqlite'))
    project.create('stadium', NEW, names={'full': {'*': 'A01 New Stadium'}}, fields={'capacity': 40000})
    project.set_stadium_source(NEW, 3)
    if with_scene:
        project.set_stadium_scene(NEW, stadium_files.read_folder(_stadium_folder(str(tmp_path)))[1])
    project.set_team_stadium(fakegame.TEAM, NEW)
    return project


def test_created_stadium_in_the_patch(installed, tmp_path):
    project = _created(tmp_path)
    assert project.stadium_scene_list(NEW)['data/sceneassets/stadium/stadium_#.rx3'] == len(b'A01 scene')
    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    assert summary['database']['created'] == {'stadium': 1} and summary['stadiums'] == 1
    tables = _tables(patch_dir)
    row = next(r for r in tables['stadiums']['rows'] if r['stadiumid'] == NEW)
    # the template's row (stadium 3) with the new id, name and saved fields; no home team of its own
    assert (row['name'], row['capacity'], row['yearbuilt'], row['hometeamid']) == ('A01 New Stadium', 40000, 1901, 0)
    assert {r['teamid']: r['stadiumid'] for r in tables['teamstadiumlinks']['rows']}[fakegame.TEAM] == NEW
    loc = BigArchive(os.path.join(patch_dir, 'data', 'loc', 'locale.big'))
    assert t3db.read_strings(loc.read('data/loc/eng_us.db'), lambda s: True)[f'StadiumName_{NEW}'] == 'A01 New Stadium'

    def loose(path):
        with open(os.path.join(patch_dir, *path.split('/')), 'rb') as f:
            return f.read()
    assert loose(f'data/sceneassets/stadium/stadium_{NEW}.rx3') == b'A01 scene'
    assert loose(f'data/sceneassets/stadium/stadium_{NEW}_1_textures.rx3') == b'A01 day textures'
    assert loose(f'data/sceneassets/crowdplacement/crowd_{NEW}_1.dat') == b'A01 crowd'
    assert loose(f'data/sceneassets/fx/glares_{NEW}_1.lnx') == f'<Effect name="glares_{NEW}_1"><p index="158"/>'.encode()
    assert not os.path.exists(os.path.join(patch_dir, 'data', 'sceneassets', 'stadium', 'stadium_158.rx3'))


def test_created_stadium_menu_picture(installed, tmp_path):
    import io

    from PIL import Image

    from f14mod import images, stadium_files
    project = _created(tmp_path)
    picture = io.BytesIO()
    Image.new('RGBA', (100, 50), (0, 0, 255, 255)).save(picture, 'PNG')
    project.set_picture('stadium', NEW, 'menu_1', picture.getvalue())
    out = stadium_files.patch_files(catalog.open_game(installed), project, NEW)
    shown = images.apt_picture(out[f'data/ui/artassets/stadiumsbig/st_{NEW}_1.big'])
    assert shown.getpixel((10, 10))[:3] == (0, 0, 255)  # the user's picture, not the folder's red one


def test_created_stadium_without_files_copies_the_template(installed, tmp_path):
    from f14mod import stadium_files

    class Files:  # the game's files with a scene for the template (the fake game has none)
        def __init__(self, files):
            self.files = files

        def read(self, path):
            if path == 'data/sceneassets/fx/glares_3_0.lnx':
                return b'<Effect name="glares_3_0">'
            if path == 'data/sceneassets/stadium/stadium_3.rx3':
                return b'template scene'
            return self.files.read(path)

    project = _created(tmp_path, with_scene=False)
    out = stadium_files.patch_files(Files(catalog.open_game(installed)), project, NEW)
    assert out[f'data/sceneassets/stadium/stadium_{NEW}.rx3'] == b'template scene'
    assert out[f'data/sceneassets/fx/glares_{NEW}_0.lnx'] == f'<Effect name="glares_{NEW}_0">'.encode()


def test_stadium_from_scratch_waits_for_its_folder(installed, tmp_path):
    """Blank (no scene, no pictures, no capacity/year/country): out of the patch until it gets a folder."""
    from f14mod import stadium_files
    project = Project(str(tmp_path / 'project.sqlite'))
    project.create('stadium', NEW, names={'full': {'*': 'A01 Scratch'}})
    project.set_stadium_source(NEW, None)
    project.set_team_stadium(fakegame.TEAM, NEW)
    assert project.incomplete_stadiums() == {NEW}
    patch_dir = str(tmp_path / 'patch')
    builder.build(catalog.open_game(installed), project, patch_dir)
    tables = _tables(patch_dir)
    assert not any(r['stadiumid'] == NEW for r in tables['stadiums']['rows'])
    assert {r['teamid']: r['stadiumid'] for r in tables['teamstadiumlinks']['rows']}[fakegame.TEAM] != NEW
    assert not os.path.exists(os.path.join(patch_dir, 'data', 'sceneassets', 'stadium', f'stadium_{NEW}.rx3'))

    project.set_stadium_scene(NEW, stadium_files.read_folder(_stadium_folder(str(tmp_path)))[1])
    assert project.incomplete_stadiums() == {NEW}  # the 3D, but not the fields the game needs
    values = {f.name: f.options[0] if f.options else max(f.min or 0, 1) for f in fields.STADIUM
              if f.name in fields.STADIUM_REQUIRED}
    project.save('stadium', NEW, project.names('stadium', NEW), {**values, 'capacity': 0, 'yearbuilt': 1999})
    assert project.missing_stadium_fields(NEW) == [] and project.incomplete_stadiums() == set()
    patch_dir = str(tmp_path / 'patch2')
    builder.build(catalog.open_game(installed), project, patch_dir)
    tables = _tables(patch_dir)
    row = next(r for r in tables['stadiums']['rows'] if r['stadiumid'] == NEW)
    assert (row['name'], row['capacity'], row['yearbuilt'], row['countrycode']) == ('A01 Scratch', 0, 1999, 0)
    assert {r['teamid']: r['stadiumid'] for r in tables['teamstadiumlinks']['rows']}[fakegame.TEAM] == NEW


def test_game_stadium_takes_a_folder(installed, tmp_path):
    """A downloaded stadium's folder over one of the game's stadiums: its files under that stadium's id; reset = the
    game's 3D again."""
    from f14mod import stadium_files
    project = Project(str(tmp_path / 'project.sqlite'))
    folder_stadium, scene = stadium_files.read_folder(_stadium_folder(str(tmp_path)))
    project.set_stadium_scene(3, scene)
    project.set_stadium_folder_source(3, folder_stadium)
    assert project.edited('stadium') == [3] and project.stadium_folder_source(3) == folder_stadium
    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    assert summary['stadiums'] == 1

    def loose(path):
        with open(os.path.join(patch_dir, *path.split('/')), 'rb') as f:
            return f.read()
    assert loose('data/sceneassets/stadium/stadium_3.rx3') == b'A01 scene'
    assert loose('data/sceneassets/fx/glares_3_1.lnx') == b'<Effect name="glares_3_1"><p index="158"/>'
    project.reset('stadium', 3)
    assert project.with_stadium_scene() == [] and project.stadium_folder_source(3) is None and not project.edited('stadium')


def test_created_stadium_deleted(tmp_path):
    project = _created(tmp_path)
    assert project.counts() == {'new_stadium': 1, 'team': 1}
    project.delete('stadium', NEW)
    assert project.created('stadium') == [] and project.team_stadium(fakegame.TEAM) is None
    assert project.stadium_scene_list(NEW) == {} and project.stadium_source(NEW) is None


def test_older_project_opens_with_created_stadiums(tmp_path):
    import sqlite3
    path = str(tmp_path / 'p.sqlite')
    Project(path)
    con = sqlite3.connect(path)
    con.execute('DROP TABLE stadium_sources')
    con.execute('DROP TABLE stadium_scene')
    con.execute("UPDATE meta SET value = '13' WHERE key = 'schema'")
    con.commit()
    con.close()
    p = Project(path)
    assert p.stadium_source(NEW) is None and p.stadium_scene_list(NEW) == {}
