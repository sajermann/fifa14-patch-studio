"""When each entity of the project was created and last changed (schema 8, same rule as the Street Studio)."""
import sqlite3

import pytest

from f14mod.project import Project


@pytest.fixture
def project(tmp_path):
    p = Project(str(tmp_path / 'project.sqlite'))
    p.clock = iter(range(100, 10_000, 100))
    p.now = lambda: next(p.clock)
    return p


def test_a_created_entity_is_created_and_updated_when_it_changes(project):
    project.create('team', 131001, names={'full': {'*': 'A01'}})
    created, updated = project.dates('team', 131001)
    assert created is not None and updated >= created
    project.save('team', 131001, names={'full': {'*': 'A01'}})  # the same form again: nothing changed
    assert project.dates('team', 131001) == (created, updated)
    project.save('team', 131001, names={'full': {'*': 'A02'}})
    assert project.dates('team', 131001)[0] == created and project.dates('team', 131001)[1] > updated


def test_a_game_entity_is_never_created_and_loses_its_dates_when_undone(project):
    assert project.dates('player', 7) == (None, None)
    project.save('player', 7, fields={'height': 180})
    created, updated = project.dates('player', 7)
    assert created is None and updated is not None  # the project changed it, it did not create it
    project.set_picture('player', 7, 'photo', b'png1')
    assert project.dates('player', 7)[1] > updated
    project.reset('player', 7)
    assert project.dates('player', 7) == (None, None)


def test_squads_kits_members_and_hiding_update_their_entity(project):
    project.set_roster(5, [{'player': 1, 'jersey': 9, 'slot': 0}])
    first = project.dates('team', 5)[1]
    project.set_roster(5, [{'player': 1, 'jersey': 9, 'slot': 0}])  # the same squad
    assert project.dates('team', 5)[1] == first
    project.set_kit(5, 0, {'source': 'game'})
    assert project.dates('team', 5)[1] > first
    project.set_members(9, [5, 6])
    assert project.dates('league', 9)[1] is not None
    project.set_hidden('country', 3, True)
    assert project.dates('country', 3)[1] is not None
    project.set_hidden('country', 3, False)  # nothing of the project left: the game's again
    assert project.dates('country', 3) == (None, None)


def test_deleting_a_created_entity_drops_its_dates(project):
    project.create('league', 400, fields={'level': 1})
    project.delete('league', 400)
    assert project.dates('league', 400) == (None, None)


def test_schema_7_projects_get_the_dates_they_had(tmp_path):
    path = str(tmp_path / 'old.sqlite')
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE edited (kind TEXT, id INTEGER, updated_at INTEGER, PRIMARY KEY (kind, id));
        CREATE TABLE created (kind TEXT, id INTEGER, created_at INTEGER, PRIMARY KEY (kind, id));
        INSERT INTO meta VALUES ('schema', '7');
        INSERT INTO created VALUES ('team', 131001, 1000); INSERT INTO edited VALUES ('team', 131001, 2000);
        INSERT INTO edited VALUES ('player', 7, 3000);""")
    con.commit()
    con.close()
    project = Project(path)
    assert project.dates('team', 131001) == (1000, 2000)
    assert project.dates('player', 7) == (None, 3000)  # an original edited before schema 8: no creation date
    project.now = lambda: 4000
    project.save('player', 7, fields={'height': 190})
    assert project.dates('player', 7) == (None, 4000)  # and it never gets one (same rule as the Street Studio)


def test_schema_9_projects_lose_the_creation_date_of_game_entities(tmp_path):
    path = str(tmp_path / 'old.sqlite')
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE created (kind TEXT, id INTEGER, created_at INTEGER, PRIMARY KEY (kind, id));
        CREATE TABLE dates (kind TEXT, id INTEGER, created_at INTEGER, updated_at INTEGER, PRIMARY KEY (kind, id));
        INSERT INTO meta VALUES ('schema', '9');
        INSERT INTO created VALUES ('team', 131001, 1000); INSERT INTO dates VALUES ('team', 131001, 1000, 2000);
        INSERT INTO dates VALUES ('stadium', 1, 3000, 3000);""")
    con.commit()
    con.close()
    project = Project(path)
    assert project.dates('team', 131001) == (1000, 2000)  # created by the user: kept
    assert project.dates('stadium', 1) == (None, 3000)  # a game stadium edited: only the change
