"""Free countries and leagues: created in the project, written into the patch (fake installation only)."""
import os
import zlib

import fakegame
import pytest

from f14mod import builder, catalog, dbedit, fifa14, t3db
from f14mod.big import BigArchive
from f14mod.project import Project


@pytest.fixture
def installed(tmp_path):
    return fakegame.build_installed(str(tmp_path))


def test_string_hash_is_crc32_of_the_folded_id():
    sid = 'LeagueName_Abbr15_400'
    folded = bytes(b & 0xDF for b in sid.encode())
    assert dbedit.string_hash(sid) == zlib.crc32(folded, 0xFFFFFFFF) ^ 0xFFFFFFFF
    assert dbedit.string_hash('teamname_1') == dbedit.string_hash('TEAMNAME_1')  # case does not matter


def test_new_strings_get_their_hash_and_the_rows_stay_in_order(installed):
    files = catalog.open_game(installed)
    strings = dbedit.LanguageStrings(files.read('data/loc/eng_us.db'))
    for sid in ('NationName_1', 'LeagueName_400', 'Labbr_400'):
        strings.set(sid, sid.lower())
    db = dbedit.Database(strings.build())
    table = db.first()
    hash_column = next(i for i, f in enumerate(table.fields) if f.type == 3)
    hashes = [r[hash_column] for r in table.records]
    assert hashes == sorted(hashes)
    out = t3db.read_strings(db.build(), lambda s: True)
    assert out['LeagueName_400'] == 'leaguename_400'
    assert out[f'TeamName_Abbr15_{fakegame.TEAM}'] == 'Test Athletic'


def test_project_created_entities_and_league_members(tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('country', 1, {'full': {'*': 'Free Land'}}, {'flag_from': 54})
    project.create('league', 400, {'full': {'*': 'Free League'}}, {'countryid': 1, 'level': 1})
    with pytest.raises(ValueError):
        project.create('league', 400)
    project.set_members(400, [7002, 7001, 7002])
    assert project.members(400) == [7002, 7001]
    assert project.members(9001) is None
    assert project.counts()['new_league'] == 1 and project.counts()['new_country'] == 1
    project.delete('league', 400)
    assert project.created('league') == [] and project.members(400) is None
    assert project.fields('league', 400) == {} and project.names('league', 400) == {}


def test_build_writes_country_league_links_strings_and_pictures(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('country', 1, {'full': {'*': 'Free Land', 'eng_us': 'Free Land EN'}, 'abbr3': {'*': 'FRL'}},
                   {'flag_from': 54})
    project.create('league', 400, {'full': {'*': 'Free League'}, 'abbr': {'*': 'FL1'}},
                   {'countryid': 1, 'level': 2, 'leaguename': 'Free League'})
    project.set_members(400, [fakegame.SMALL_TEAM, fakegame.TEAM])
    project.set_members(fakegame.LEAGUE, [fakegame.TEAM, fakegame.SMALL_TEAM])  # a team in several leagues

    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    assert summary['database']['created'] == {'country': 1, 'league': 1}
    assert summary['database']['league_links'] == 4
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db-meta.xml'), 'rb') as f:
        meta = t3db.load_meta(f.read())
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db.db'), 'rb') as f:
        tables = t3db.read_tables(f.read(), meta)
    nation = next(r for r in tables['nations']['rows'] if r['nationid'] == 1)
    assert nation['nationname'] == 'Free Land' and nation['teamid'] == -1
    league = next(r for r in tables['leagues']['rows'] if r['leagueid'] == 400)
    assert (league['countryid'], league['level'], league['leaguename']) == (1, 2, 'Free League')
    links = sorted((r['leagueid'], r['teamid']) for r in tables['leagueteamlinks']['rows'])
    assert links == sorted([(400, fakegame.SMALL_TEAM), (400, fakegame.TEAM), (fakegame.LEAGUE, fakegame.TEAM),
                            (fakegame.LEAGUE, fakegame.SMALL_TEAM), (fakegame.PLAIN_LEAGUE, fakegame.SMALL_TEAM)])

    loc = BigArchive(os.path.join(patch_dir, 'data', 'loc', 'locale.big'))
    en = t3db.read_strings(loc.read('data/loc/eng_us.db'), lambda s: True)
    assert en['NationName_1'] == 'Free Land EN' and en['nationname_abbr3_1'] == 'FRL'
    assert en['LeagueName_400'] == 'Free League' and en['Labbr_400'] == 'FL1'
    # names left empty come from the full name: the short name is the one the team selection shows
    assert en['LeagueName_Abbr15_400'] == 'Free League' and en['TrophyName_400'] == 'Free League'
    assert en['TrophyName_Abbr15_400'] == 'Free League'
    assert summary['missing_strings'] == []
    for pattern in fifa14.LEAGUE_PICTURES:
        assert pattern.format(400) in summary['loose']
    assert summary['pictures'] == len(fifa14.LEAGUE_PICTURES) + 1  # the fake game has one flag file of country 54
    assert fifa14.FLAG_PICTURE.format(1) in summary['loose']


def test_derived_names_of_created_entities():
    names = builder.with_derived_names('league', {'full': {'*': 'Campeonato Livre de Teste', 'por_br': 'Liga Livre'},
                                                  'abbr': {'*': 'CLT'}})
    assert names['abbr15'] == {'*': 'Campeonato Livr', 'por_br': 'Liga Livre'}
    assert names['abbr'] == {'*': 'CLT'}  # written by the user for every language
    assert builder.with_derived_names('country', {'full': {'*': 'Ligas Livres'}})['abbr3'] == {'*': 'LIG'}


def test_too_many_league_links_stop_the_build(installed, tmp_path, monkeypatch):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.set_members(fakegame.LEAGUE, [fakegame.TEAM, fakegame.SMALL_TEAM])
    monkeypatch.setattr(fifa14, 'MAX_LEAGUE_LINKS', 2)
    with pytest.raises(builder.BuildError) as e:
        builder.build(catalog.open_game(installed), project, str(tmp_path / 'patch'))
    assert e.value.code == 'too_many_league_links'
