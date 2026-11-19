"""Free countries and leagues: created in the project, written into the patch (fake installation only)."""
import os
import zlib

import fakegame
import pytest

from f14mod import builder, catalog, dbedit, fifa14, flags, images, t3db
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
    assert summary['pictures'] == len(fifa14.LEAGUE_PICTURES) + 4  # the four flag files of country 54 copied
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


def _picture_png(color=(10, 200, 30)):
    from PIL import Image
    img = Image.new('RGBA', (30, 20), color + (255,))
    return flags.normalize_picture(images.png(img))


def test_flag_drawn_from_a_picture_keeps_the_model_files(installed):
    files = catalog.open_game(installed)
    with pytest.raises(flags.FlagError):
        flags.normalize_picture(b'not a picture')
    out = flags.flag_files(files, _picture_png())
    assert set(out) == set(fifa14.FLAG_FILES)
    import tempfile
    from f14mod.big import BigArchive
    for pattern in fifa14.FLAG_FILES[:3]:
        model = files.read(pattern.format(54))
        assert len(out[pattern]) == len(model)  # same texture size and format: only the pixels change
        path = os.path.join(tempfile.mkdtemp(), 'f.big')
        with open(path, 'wb') as f:
            f.write(out[pattern])
        archive = BigArchive(path)
        assert archive.read('0') == b'Apt Data:fake screen' and archive.read('1') == b'Apt constant'
        texture = images.decode_dds(archive.read('2'))
        assert texture.getpixel((8, 8))[:3] != (0, 0, 255) and texture.getpixel((8, 8))[3] == 255
        assert texture.getpixel((8, 1))[3] == 0  # the model's alpha: outside the flag stays clear
    assert flags.preview(files, _picture_png()).size == (16, 16)


def test_build_draws_the_flag_of_a_country_with_a_picture(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('country', 1, {'full': {'*': 'Picture Land'}})
    project.set_picture('country', 1, 'flag', _picture_png())
    project.set_picture('country', 54, 'flag', _picture_png((200, 0, 0)))  # a country of the game too
    assert project.counts() == {'country': 1, 'new_country': 1}
    summary = builder.build(catalog.open_game(installed), project, str(tmp_path / 'patch'))
    for nid in (1, 54):
        for pattern in fifa14.FLAG_FILES:
            assert pattern.format(nid) in summary['loose']
    project.set_picture('country', 54, 'flag', None)
    assert project.counts() == {'new_country': 1}


def test_league_picture_fills_the_eight_league_files(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('league', 400, {'full': {'*': 'Picture League'}}, {'countryid': 54})
    project.set_picture('league', 400, 'logo', _picture_png())
    project.set_picture('league', fakegame.LEAGUE, 'logo', _picture_png((200, 0, 0)))  # a league of the game too
    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    for lid in (400, fakegame.LEAGUE):
        for pattern, (size, _dark) in fifa14.LEAGUE_PICTURES.items():
            assert pattern.format(lid) in summary['loose']
    banner = next(p for p, (size, _d) in fifa14.LEAGUE_PICTURES.items() if size == (512, 128))
    with open(os.path.join(patch_dir, *banner.format(400).split('/')), 'rb') as f:
        img = images.decode_dds(f.read())
    assert img.size == (512, 128)
    assert img.getpixel((256, 64))[3] == 255 and img.getpixel((2, 64))[3] == 0  # fitted in the middle, clear sides
    assert img.getpixel((256, 64))[1] > 150  # the user's green


def test_hide_a_created_league_leaves_it_out_and_an_original_one_hides_it_in_the_game(installed, tmp_path):
    """One Hide button, as in the Street Studio: created = out of the patch; original = hidden in the game."""
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('league', 400, {'full': {'*': 'Hidden League'}}, {'countryid': 54})
    project.set_members(400, [fakegame.TEAM])
    project.set_picture('league', 400, 'logo', _picture_png())
    project.save('league', fakegame.LEAGUE, {'full': {'*': 'Renamed'}}, {'level': 3})
    for lid in (400, fakegame.LEAGUE):
        project.set_hidden('league', lid, True)
    assert project.hidden('league') == {400, fakegame.LEAGUE}
    assert project.hidden_in_game('league') == {fakegame.LEAGUE}
    view = project.visible()
    assert view.created('league') == [] and view.all_members() == {} and view.with_picture('league', 'logo') == []
    assert view.fields('league', fakegame.LEAGUE) == {'level': 3}  # the original keeps its edits
    assert project.created('league') == [400]  # still in the project
    summary, leagues, links = _built_tables(installed, tmp_path, project)
    assert 400 not in {lid for lid, _c in leagues}  # not created
    assert (fakegame.LEAGUE, fifa14.HIDDEN_COUNTRY) in leagues  # hidden in the game
    assert not any('l400.dds' in p for p in summary['loose']) and summary['pictures'] == 0
    project.delete('league', 400)
    assert project.hidden('league') == {fakegame.LEAGUE}


def _built_tables(installed, tmp_path, project):
    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db-meta.xml'), 'rb') as f:
        meta = t3db.load_meta(f.read())
    with open(os.path.join(patch_dir, 'data', 'db', 'fifa_ng_db.db'), 'rb') as f:
        tables = t3db.read_tables(f.read(), meta)
    leagues = sorted((r['leagueid'], r['countryid']) for r in tables['leagues']['rows'])
    links = sorted((r['leagueid'], r['teamid']) for r in tables['leagueteamlinks']['rows'])
    keys = [r['artificialkey'] for r in tables['leagueteamlinks']['rows'] if 'artificialkey' in r]
    assert len(keys) == len(set(keys))  # (the fake game has no key column)
    return summary, leagues, links


def test_league_in_several_countries_is_one_row_per_country(installed, tmp_path):
    from f14mod import fields
    assert fields.clean('league', {'extra_countries': [52, 52, 60]}, {'extra_countries': []}) == \
        {'extra_countries': [52, 60]}
    assert fields.clean('league', {'extra_countries': []}, {'extra_countries': []}) == {}
    with pytest.raises(fields.FieldError):
        fields.clean('league', {'extra_countries': [0]}, {'extra_countries': []})
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save('league', fakegame.LEAGUE, None, {'extra_countries': [52, 54, 60]})  # 54 is its own country
    summary, leagues, links = _built_tables(installed, tmp_path, project)
    assert leagues == sorted([(fakegame.LEAGUE, 54), (fakegame.LEAGUE, 52), (fakegame.LEAGUE, 60),
                              (fakegame.PLAIN_LEAGUE, 52)])
    assert links == sorted([(fakegame.LEAGUE, fakegame.TEAM), (fakegame.PLAIN_LEAGUE, fakegame.SMALL_TEAM)])
    assert summary['database']['visibility']['extra_country_rows'] == 2


def test_league_hidden_in_one_country(installed, tmp_path):
    """hidden_in_countries: the league stays in the country in the project but gets no row there in the patch;
    hidden in all its countries, it is hidden in the game (country 0)."""
    from f14mod import fields
    original = {'countryid': 54, 'extra_countries': []}
    assert fields.clean('league', {'extra_countries': [52], 'hidden_in_countries': [52, 77, 52]}, original) ==         {'extra_countries': [52], 'hidden_in_countries': [52]}  # 77 is not a country of the league
    assert fields.clean('league', {'hidden_in_countries': [77]}, original) == {}
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save('league', fakegame.LEAGUE, None, {'extra_countries': [52, 60], 'hidden_in_countries': [52]})
    _summary, leagues, _links = _built_tables(installed, tmp_path, project)
    assert leagues == sorted([(fakegame.LEAGUE, 54), (fakegame.LEAGUE, 60), (fakegame.PLAIN_LEAGUE, 52)])
    project.save('league', fakegame.LEAGUE, None, {'hidden_in_countries': [54]})  # its only country
    _summary, leagues, _links = _built_tables(installed, tmp_path, project)
    assert leagues == sorted([(fakegame.LEAGUE, 0), (fakegame.PLAIN_LEAGUE, 52)])


def test_hidden_original_country_league_and_team(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save('league', fakegame.LEAGUE, None, {'extra_countries': [60]})
    project.set_hidden('country', 54, True)  # the league stays only in its other country
    project.set_hidden('league', fakegame.PLAIN_LEAGUE, True)
    summary, leagues, links = _built_tables(installed, tmp_path, project)
    assert leagues == sorted([(fakegame.LEAGUE, 60), (fakegame.PLAIN_LEAGUE, fifa14.HIDDEN_COUNTRY)])
    project.set_hidden('country', 60, True)  # every country of the league hidden: country 0
    _summary, leagues, _links = _built_tables(installed, tmp_path, project)
    assert leagues == sorted([(fakegame.LEAGUE, 0), (fakegame.PLAIN_LEAGUE, 0)])

    # a team hidden in the game: its links to visible leagues go; without a hidden league to keep it, it has none
    project = Project(str(tmp_path / 'q.sqlite'))
    project.set_members(fakegame.LEAGUE, [fakegame.TEAM, fakegame.SMALL_TEAM])
    project.set_hidden('team', fakegame.SMALL_TEAM, True)
    summary, leagues, links = _built_tables(installed, tmp_path, project)
    assert links == [(fakegame.LEAGUE, fakegame.TEAM)]
    # the plain league lost its only team, but the user did not change its list: it is left as it is
    assert leagues == sorted([(fakegame.LEAGUE, 54), (fakegame.PLAIN_LEAGUE, 52)])


def test_hidden_team_goes_to_the_hidden_league_and_empty_leagues_hide(installed, tmp_path, monkeypatch):
    monkeypatch.setattr(fifa14, 'HIDDEN_LEAGUE', fakegame.PLAIN_LEAGUE)  # the fake game has no league 111
    project = Project(str(tmp_path / 'p.sqlite'))
    project.set_hidden('league', fakegame.PLAIN_LEAGUE, True)
    project.set_hidden('team', fakegame.TEAM, True)
    project.create('league', 400, {'full': {'*': 'Only Hidden Teams'}}, {'countryid': 54})
    project.set_members(400, [fakegame.TEAM])  # its only team is hidden: the league would show an empty list
    summary, leagues, links = _built_tables(installed, tmp_path, project)
    assert links == sorted([(fakegame.PLAIN_LEAGUE, fakegame.SMALL_TEAM), (fakegame.PLAIN_LEAGUE, fakegame.TEAM)])
    assert (400, 0) in leagues and (fakegame.PLAIN_LEAGUE, 0) in leagues
    assert summary['database']['visibility']['hidden_leagues'] == [400, fakegame.PLAIN_LEAGUE]
    # the created league hidden: out of the patch (not hidden in the game: it does not exist there)
    project.set_hidden('league', 400, True)
    assert 400 not in project.visible().hidden_in_game('league') and 400 not in project.visible().created('league')
