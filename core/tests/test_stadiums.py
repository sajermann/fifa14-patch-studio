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
