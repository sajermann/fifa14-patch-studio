"""Teams the user creates or changes: rows, formation, squad and lineup, crest and kits (fake installation only;
the rules were proven in game by test TN1)."""
import io
import os

import fakegame
import pytest
from PIL import Image

from f14mod import builder, catalog, images, rx3, t3db, teamkits
from f14mod.project import Project

NEW = 131001
P433 = [0, 3, 4, 6, 7, 13, 14, 15, 23, 25, 27]


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


def _file(patch_dir, path):
    with open(os.path.join(patch_dir, *path.split('/')), 'rb') as f:
        return f.read()


def _squad(tables, team):
    return [r['playerid'] for r in tables['teamplayerlinks'] if r['teamid'] == team]


def test_lineup_puts_one_starter_in_each_slot():
    rows = [{'player': i, 'slot': s} for i, s in enumerate([0, 3, 99, 28, 4, 29, 29, 29, 29, 29, 29, 29, 29])]
    rows[2]['slot'] = 5  # a starter in a slot the formation does not have takes a free one
    out = builder.lineup(rows, [0, 3, 4, 6, 7, 13, 14, 15, 23, 25, 27])
    starters = sorted(r['slot'] for r in out if r['slot'] < 28)
    assert starters == [0, 3, 4, 6, 7, 13, 14, 15, 23, 25, 27]
    assert out[2]['slot'] == 6 and out[3]['slot'] == 7  # the starter first, then the bench steps up
    assert len(builder.lineup([{'player': i} for i in range(50)], P433)) == 41  # the rest stays out of the patch


def test_team_made_from_scratch(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('team', NEW, {'full': {'*': 'Free Team United'}},
                   {'teamcolor1': [0, 0, 200], 'teamcolor2': [255, 255, 255], 'formation': 8})
    project.set_team_source(NEW, fakegame.TEAM, False)
    files = catalog.open_game(installed)
    source = __import__('f14mod.fifa14', fromlist=['Fifa14Source']).Fifa14Source(installed, files=files)
    squad = [link['playerid'] for link in source.team_links[fakegame.TEAM]][:14]
    project.set_roster(NEW, [{'player': pid, 'jersey': i + 1, 'slot': 29} for i, pid in enumerate(squad)])
    summary, tables, patch_dir = _build(installed, tmp_path, project)

    team = next(r for r in tables['teams'] if r['teamid'] == NEW)
    assert team['teamname'] == 'Free Team United' and (team['teamcolor1r'], team['teamcolor1b']) == (0, 200)
    assert team['captainid'] in squad
    # no formation of its own (the game takes 899 at most): it points at the generic one chosen (test FM4)
    assert NEW not in {r['teamid'] for r in tables['formations']}
    link = next(r for r in tables['teamformationteamstylelinks'] if r['teamid'] == NEW)
    generic = next(r for r in tables['formations'] if r['formationid'] == link['formationid'])
    assert (generic['teamid'], generic['relativeformationid'], link['teamstyleid']) == (-1, 8, 0)
    assert [generic[f'position{i}'] for i in range(11)] == P433
    links = [r for r in tables['teamplayerlinks'] if r['teamid'] == NEW]
    assert len(links) == 14 and sorted(r['position'] for r in links if r['position'] < 28) == P433
    assert [r['jerseynumber'] for r in links] == list(range(1, 15))
    assert _squad(tables, fakegame.TEAM) == [link['playerid'] for link in source.team_links[fakegame.TEAM]]
    assert {r['teamkittypetechid'] for r in tables['teamkits'] if r['teamtechid'] == NEW} == {0, 1, 2}
    assert summary['database']['created']['team'] == 1

    # generic kits: the mask painted with the team colors (home: color 1 where the mask is red)
    home = rx3.unpack(_file(patch_dir, teamkits.KIT_FILE.format(NEW, 0)))
    px = rx3.to_image(home, rx3.by_name(home, 'jersey_cm')).convert('RGB').getpixel((5, 5))
    assert px == (0, 0, 200)
    away = rx3.unpack(_file(patch_dir, teamkits.KIT_FILE.format(NEW, 1)))
    assert rx3.to_image(away, rx3.by_name(away, 'jersey_cm')).convert('RGB').getpixel((5, 5)) == (255, 255, 255)
    keeper = _file(patch_dir, teamkits.KIT_FILE.format(NEW, 2))
    assert keeper == fakegame.kit_rx3((0, 200, 0))  # the game's plain goalkeeper kit
    crest = images.decode_dds(_file(patch_dir, teamkits.CREST_FILE.format('crest', NEW)))
    assert crest.size == (64, 64)  # the model's size
    assert os.path.exists(os.path.join(patch_dir, *teamkits.MINIKIT.format(0, NEW).split('/')))


def test_team_from_scratch_needs_players(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('team', NEW, {'full': {'*': 'Empty'}})
    with pytest.raises(builder.BuildError) as e:
        builder.build(catalog.open_game(installed), project, str(tmp_path / 'patch'))
    assert e.value.code == 'team_too_few_players'


def test_copied_team_keeps_the_models_squad_crest_and_kits(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('team', NEW, {'full': {'*': 'Copy FC'}})
    project.set_team_source(NEW, fakegame.TEAM, True)
    summary, tables, patch_dir = _build(installed, tmp_path, project)
    assert _squad(tables, NEW) == _squad(tables, fakegame.TEAM)
    files = catalog.open_game(installed)
    assert _file(patch_dir, teamkits.KIT_FILE.format(NEW, 0)) == files.read(teamkits.KIT_FILE.format(fakegame.TEAM, 0))
    assert _file(patch_dir, teamkits.CREST_FILE.format('crest', NEW)) == \
        files.read(teamkits.CREST_FILE.format('crest', fakegame.TEAM))


def test_game_team_squad_crest_and_uploaded_kit(installed, tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    files = catalog.open_game(installed)
    source = __import__('f14mod.fifa14', fromlist=['Fifa14Source']).Fifa14Source(installed, files=files)
    squad = [link['playerid'] for link in source.team_links[fakegame.TEAM]]
    small = [link['playerid'] for link in source.team_links[fakegame.SMALL_TEAM]]
    new_squad = squad[:10] + small[:2]
    project.set_roster(fakegame.TEAM, [{'player': pid, 'jersey': 30 + i, 'slot': 28} for i, pid in enumerate(new_squad)])
    project.save('team', fakegame.TEAM, None, {'formation': 8})
    project.set_picture('team', fakegame.TEAM, 'crest', _png((0, 150, 0)))
    project.set_kit(fakegame.TEAM, 0, {'source': 'upload', 'collar': 5})
    project.set_picture('team', fakegame.TEAM, 'kit0_jersey', _png((10, 20, 30)))
    summary, tables, patch_dir = _build(installed, tmp_path, project)

    links = [r for r in tables['teamplayerlinks'] if r['teamid'] == fakegame.TEAM]
    assert [r['playerid'] for r in links] == new_squad
    assert sorted(r['position'] for r in links if r['position'] < 28) == P433
    team = next(r for r in tables['teams'] if r['teamid'] == fakegame.TEAM)
    assert team['captainid'] in new_squad
    kit = rx3.unpack(_file(patch_dir, teamkits.KIT_FILE.format(fakegame.TEAM, 0)))
    assert rx3.to_image(kit, rx3.by_name(kit, 'jersey_cm')).convert('RGB').getpixel((3, 3)) == (10, 20, 30)
    row = next(r for r in tables['teamkits'] if r['teamtechid'] == fakegame.TEAM and r['teamkittypetechid'] == 0
               and r['year'] == 0)
    assert row['jerseycollargeometrytype'] == 5
    crest = images.decode_dds(_file(patch_dir, teamkits.CREST_FILE.format('crest', fakegame.TEAM))).convert('RGB')
    assert crest.getpixel((32, 32)) == (0, 150, 0)
    assert summary['database']['rosters'] == 1 and summary['database']['formations'] == 1


def test_paint_mask_keeps_what_is_not_red_or_green():
    img = Image.new('RGB', (3, 1))
    img.putdata([(255, 0, 0), (0, 255, 0), (40, 40, 200)])
    out = teamkits.paint_mask(img, (10, 20, 30), (200, 100, 0))
    assert [out.getpixel((x, 0)) for x in range(3)] == [(10, 20, 30), (200, 100, 0), (40, 40, 200)]


def test_extra_outfield_kit(installed, tmp_path):
    """Types 3 and up are more outfield kits (tests GK1/GK2): a new type gets its file, minikit and teamkits row,
    with the team's home kit file as the model of an uploaded one."""
    project = Project(str(tmp_path / 'p.sqlite'))
    project.set_kit(fakegame.TEAM, 5, {'source': 'generic', 'model': 7500, 'colors': [[255, 0, 200], [255, 255, 255]]})
    project.set_kit(fakegame.TEAM, 7, {'source': 'upload'})
    project.set_picture('team', fakegame.TEAM, 'kit7_jersey', _png((1, 2, 3)))
    summary, tables, patch_dir = _build(installed, tmp_path, project)
    kinds = {r['teamkittypetechid'] for r in tables['teamkits'] if r['teamtechid'] == fakegame.TEAM and r['year'] == 0}
    assert kinds == {0, 1, 2, 5, 7}
    kit = rx3.unpack(_file(patch_dir, teamkits.KIT_FILE.format(fakegame.TEAM, 5)))
    assert rx3.to_image(kit, rx3.by_name(kit, 'jersey_cm')).convert('RGB').getpixel((3, 3)) == (255, 0, 200)
    assert os.path.exists(os.path.join(patch_dir, *teamkits.MINIKIT.format(7, fakegame.TEAM).split('/')))


def test_kit_print_keeps_the_kit_file(installed, tmp_path):
    """'keep': only the name and numbers of the kit change (teamkits); the kit file is not written."""
    project = Project(str(tmp_path / 'p.sqlite'))
    project.set_kit(fakegame.TEAM, 0, {'source': 'keep', 'collar': 9, 'print': {
        'name_color': [10, 20, 30], 'number_color': 5, 'front_number': True, 'shorts_number': False,
        'show_name': False, 'name_layout': 1}})
    summary, tables, patch_dir = _build(installed, tmp_path, project)
    row = next(r for r in tables['teamkits'] if r['teamtechid'] == fakegame.TEAM and r['teamkittypetechid'] == 0
               and r['year'] == 0)
    assert (row['jerseynamecolorr'], row['jerseynamecolorg'], row['jerseynamecolorb']) == (10, 20, 30)
    assert (row['numbercolor'], row['jerseyfrontnumberplacementcode'], row['jerseycollargeometrytype']) == (5, 1, 9)
    assert (row['shortsnumberplacementcode'], row['jerseynamelayouttype']) == (0, 1)
    assert row.get('jerseybacknameplacementcode', 0) == 0
    assert not os.path.exists(os.path.join(patch_dir, *teamkits.KIT_FILE.format(fakegame.TEAM, 0).split('/')))


def test_blank_team_stays_out_until_complete(installed, tmp_path):
    """A team made from scratch (no template) starts blank: out of the patch until it has every required field, a
    stadium and a lineup; then its row has the neutral tactics, not the model team's values."""
    from f14mod import fields
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('team', NEW, {'full': {'*': 'A01 Blank'}})
    project.set_team_source(NEW, None, False)
    project.set_roster(NEW, [])
    project.set_members(fakegame.PLAIN_LEAGUE, [fakegame.SMALL_TEAM, NEW])
    assert project.missing_team_parts(NEW) == {'fields': list(fields.TEAM_REQUIRED), 'stadium': True, 'players': 0}
    assert project.incomplete_teams() == {NEW}
    summary, tables, _ = _build(installed, tmp_path, project)
    assert not any(r['teamid'] == NEW for r in tables['teams'])
    assert not any(r['teamid'] == NEW for r in tables['leagueteamlinks'])

    files = catalog.open_game(installed)
    source = __import__('f14mod.fifa14', fromlist=['Fifa14Source']).Fifa14Source(installed, files=files)
    squad = [link['playerid'] for link in source.team_links[fakegame.TEAM]][:14]
    project.set_roster(NEW, [{'player': pid, 'jersey': i + 1, 'slot': 29} for i, pid in enumerate(squad)])
    project.set_team_stadium(NEW, 3)
    project.save('team', NEW, fields={'teamcolor1': [1, 2, 3], 'teamcolor2': [4, 5, 6], 'teamcolor3': [7, 8, 9],
                                      'domesticprestige': 3, 'internationalprestige': 2,
                                      'rivalteam': fakegame.SMALL_TEAM, 'transferbudget': 1000,
                                      'balltype': fakegame.GAME_BALL, 'formation': 8, 'busbuildupspeed': 70})
    assert project.missing_team_parts(NEW) == {} and project.incomplete_teams() == set()
    summary, tables, _ = _build(installed, tmp_path / 'b', project)
    team = next(r for r in tables['teams'] if r['teamid'] == NEW)
    assert (team['teamcolor1r'], team['teamcolor2b'], team['balltype']) == (1, 6, fakegame.GAME_BALL)
    assert team['captainid'] in squad  # blank: the last starter (builder.write_rosters), not the model's captain
    assert next(r for r in tables['teamstadiumlinks'] if r['teamid'] == NEW)['stadiumid'] == 3
    assert summary['database']['created']['team'] == 1


def test_copy_with_plain_crest(installed, tmp_path):
    """A copy whose copied crest was removed (plain_crest) gets the plain crest, not the copied team's files."""
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('team', NEW, {'full': {'*': 'A01 Copy'}, 'abbr3': {'*': 'ACP'}},
                   {'plain_crest': 1, 'teamcolor1': [0, 0, 200], 'teamcolor2': [255, 255, 255]})
    project.set_team_source(NEW, fakegame.TEAM, True)
    _, _, patch_dir = _build(installed, tmp_path, project)
    files = catalog.open_game(installed)
    copied = files.read(teamkits.CREST_FILE.format('crest', fakegame.TEAM))
    crest = _file(patch_dir, teamkits.CREST_FILE.format('crest', NEW))
    assert crest != copied
    r, g, b = images.decode_dds(crest).convert('RGB').getpixel((32, 20))
    assert r < 10 and g < 10 and b > 180  # color 1 (DXT rounds it)


def _crowd_files(installed):
    """The model team's crowd flags and banner, and its warm-up kit (loose files of the game)."""
    out = {}
    for path in (f'data/sceneassets/flag/flag_{fakegame.TEAM}.rx3', f'data/sceneassets/banner/banner_{fakegame.TEAM}.rx3',
                 f'data/sceneassets/warmup/warmup_{fakegame.TEAM}_0.rx3'):
        full = os.path.join(installed, *path.split('/'))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(path.encode())
        out[path.rsplit('/', 1)[0]] = path
    return out


def _made_from(installed, tmp_path, copy):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.create('team', NEW, {'full': {'*': 'A01'}})
    project.set_team_source(NEW, fakegame.TEAM, copy)
    if not copy:
        source = __import__('f14mod.fifa14', fromlist=['Fifa14Source']).Fifa14Source(
            installed, files=catalog.open_game(installed))
        squad = [link['playerid'] for link in source.team_links[fakegame.TEAM]][:14]
        project.set_roster(NEW, [{'player': pid, 'jersey': i + 1, 'slot': 29} for i, pid in enumerate(squad)])
    return project


def test_created_team_does_not_take_the_models_crowd_flags_or_board(installed, tmp_path):
    _crowd_files(installed)
    summary, tables, patch_dir = _build(installed, tmp_path, _made_from(installed, tmp_path, copy=False))
    exists = lambda folder, name: os.path.exists(os.path.join(patch_dir, *folder.split('/'), name))
    assert not exists('data/sceneassets/flag', f'flag_{NEW}.rx3')  # the model's flags show the model's crest
    assert not exists('data/sceneassets/banner', f'banner_{NEW}.rx3')
    assert exists('data/sceneassets/warmup', f'warmup_{NEW}_0.rx3')  # the warm-up kit still comes from the model
    team = next(r for r in tables['teams'] if r['teamid'] == NEW)
    assert team['adboardid'] == builder.adboards.DEFAULT_BOARD  # not the model's 7: its league is not in the game's table


def test_copied_team_keeps_the_models_crowd_flags_and_board(installed, tmp_path):
    _crowd_files(installed)
    summary, tables, patch_dir = _build(installed, tmp_path, _made_from(installed, tmp_path, copy=True))
    assert _file(patch_dir, f'data/sceneassets/flag/flag_{NEW}.rx3') ==         f'data/sceneassets/flag/flag_{fakegame.TEAM}.rx3'.encode()
    assert os.path.exists(os.path.join(patch_dir, 'data', 'sceneassets', 'banner', f'banner_{NEW}.rx3'))
    assert next(r for r in tables['teams'] if r['teamid'] == NEW)['adboardid'] == 7


def test_formations_get_ids_in_sequence_and_a_hidden_game_team_frees_its_own(installed, tmp_path):
    """The game takes formations 1-899 only (tests FM1-FM4): the rows get ids 1-N, a hidden game team's row leaves,
    a created team points at the generic formation its model's row was a copy of."""
    project = _made_from(installed, tmp_path, copy=False)
    project.set_hidden('team', fakegame.TEAM, True)
    _, tables, _ = _build(installed, tmp_path, project)
    rows = tables['formations']
    assert [r['formationid'] for r in rows] == list(range(1, len(rows) + 1))
    assert {r['teamid'] for r in rows} == {-1}  # the generic ones stay; the model's row went with its team
    link = next(r for r in tables['teamformationteamstylelinks'] if r['teamid'] == NEW)
    generic = next(r for r in rows if r['formationid'] == link['formationid'])
    assert generic['relativeformationid'] == 13  # the model team's own row is a copy of 13 (4-2-2-2)
    starters = sorted(r['position'] for r in tables['teamplayerlinks'] if r['teamid'] == NEW and r['position'] < 28)
    assert starters == sorted(generic[f'position{i}'] for i in range(11))


def test_more_formations_than_the_game_takes_stop_the_build(installed, tmp_path, monkeypatch):
    """Only the game's own rows count: a created team points at a generic formation."""
    monkeypatch.setattr(builder.fifa14, 'MAX_FORMATIONS', 3)  # the fake game: 2 generic + its team
    project = _made_from(installed, tmp_path, copy=False)
    _build(installed, tmp_path, project)  # the created team takes no row
    monkeypatch.setattr(builder.fifa14, 'MAX_FORMATIONS', 2)
    with pytest.raises(builder.BuildError) as error:
        _build(installed, tmp_path, project)
    assert (error.value.code, error.value.detail) == ('too_many_formations', '1')


def test_a_team_only_in_hidden_leagues_frees_its_formation(installed, tmp_path):
    """Nobody can pick a team whose leagues are all hidden: its formation leaves (the generic ones stay)."""
    project = Project(str(tmp_path / 'p.sqlite'))
    project.set_hidden('league', fakegame.LEAGUE, True)  # the fake game's TEAM is only in it
    _, tables, _ = _build(installed, tmp_path, project)
    rows = tables['formations']
    assert fakegame.TEAM not in {r['teamid'] for r in rows}
    assert [r['formationid'] for r in rows] == list(range(1, len(rows) + 1))


def test_a_created_team_only_in_hidden_leagues_stays_out_of_the_patch(installed, tmp_path):
    """Nobody can pick it: left out like a hidden team (a faster build with leagues put aside), and so is a created
    player who only plays for it; one league still shown is enough to keep both."""
    project = _made_from(installed, tmp_path, copy=False)
    pid = builder.fifa14.FIRST_FREE_PLAYER
    project.create('player', pid, fields={'name.common': 'P01'})
    project.set_roster(NEW, project.roster(NEW) + [{'player': pid, 'jersey': 99, 'slot': 29}])
    project.set_members(fakegame.LEAGUE, [fakegame.TEAM, NEW])
    project.set_hidden('league', fakegame.LEAGUE, True)
    assert project.out_by_hidden_leagues() == ({NEW}, {pid})
    _, tables, _ = _build(installed, tmp_path, project)
    for table, column in (('teams', 'teamid'), ('leagueteamlinks', 'teamid'), ('teamplayerlinks', 'teamid'),
                          ('teamformationteamstylelinks', 'teamid'), ('players', 'playerid')):
        assert not {NEW, pid} & {r[column] for r in tables[table]}, table
    project.set_members(fakegame.PLAIN_LEAGUE, [fakegame.SMALL_TEAM, NEW])
    assert project.out_by_hidden_leagues() == (set(), set())
