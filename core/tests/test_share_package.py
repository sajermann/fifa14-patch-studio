"""A package of the extractor imported: every item a new entity, linked together, ids of the game left alone."""
import json
import os
import zipfile

from f14mod import share
from f14mod.project import Project
from test_share import FakeDest


def _package(path) -> str:
    """A small package as the extractor writes it: country 54 (the game has it), league 7, team 1043 with players 9001
    (boot 30 of the package) and 9002, ball 2 (the game has it), player 9003 of another team (team 555, not exported)."""
    face = {'data/sceneassets/heads/head_9001_0.rx3': {'kind': 'head', 'file': 'game/h'},
            'data/sceneassets/faces/face_9001_0_0_0_0_0_0_0_0_textures.rx3': {'kind': 'face', 'file': 'game/f'}}
    manifest = {
        'format': 'fifa-patch-package', 'format_version': 1, 'source': {'game': 'fifa14', 'patch_name': 'P01'},
        'nations': [{'source_id': 54, 'name': 'Brazil', 'names': {'full': 'Brazil', 'abbr3': 'BRA'},
                     'flag': {'image': 'nations/54/flag.png'}}],
        'leagues': [{'source_id': 7, 'names': {'database': 'L01 DB', 'full': 'L01'}, 'level': 1,
                     'country_nation_id': 54, 'team_ids': [1043, 1044], 'images': {}, 'adboards': [],
                     'raw': {'leagues': [{'leagueid': 7, 'level': 1}]}}],
        'teams': [{'source_id': 1043, 'names': {'full': 'T01', 'abbr3': 'T01'}, 'league_ids': [7],
                   'crest': {'image': 'teams/1043/crest.png'}, 'stadium_ids': [1], 'formation': {'base': 5},
                   'kits': [{'type': 0, 'jersey': 'teams/1043/kits/0/jersey.png', 'collar': 3,
                             'number_font': {'id': 77, 'color': 4}, 'front_number_placement': 1}],
                   'roster': [{'player_id': 9001, 'jersey_number': 10, 'position': 25},
                              {'player_id': 9002, 'jersey_number': 1, 'position': 0}],
                   'raw': {'teams': [{'teamid': 1043, 'teamcolor1r': 1, 'teamcolor1g': 2, 'teamcolor1b': 3,
                                      'balltype': 2, 'rivalteam': 999, 'captainid': 9001, 'domesticprestige': 7}]}}],
        'players': [{'source_id': 9001, 'names': {'common': 'A01'}, 'nationality_id': 54,
                     'photo': {'image': 'players/9001/photo.png'}, 'face': {'files': face},
                     'teams': [{'team_id': 1043, 'jersey_number': 10, 'position': 25}],
                     'raw': {'players': [{'playerid': 9001, 'preferredposition1': 25, 'shoetypecode': 30,
                                          'height': 180, 'finishing': 90}]}},
                    {'source_id': 9002, 'names': {'common': 'A02'}, 'nationality_id': 54,
                     'teams': [{'team_id': 1043, 'jersey_number': 1, 'position': 0}],
                     'raw': {'players': [{'playerid': 9002, 'preferredposition1': 0}]}},
                    {'source_id': 9003, 'names': {'common': 'A03'}, 'nationality_id': 54,
                     'teams': [{'team_id': 555, 'jersey_number': 5, 'position': 28}],
                     'raw': {'players': [{'playerid': 9003, 'preferredposition1': 5}]}}],
        'boots': [{'source_id': 30, 'name': 'C30',
                   'files': {'data/sceneassets/shoe/shoe_30.rx3': 'game/s',
                             'data/sceneassets/shoe/shoe_30_0_textures.rx3': 'game/st'}}],
    }
    out = os.path.join(path, 'p.fifapkg.zip')
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('package.json', json.dumps(manifest))
        for name in ('nations/54/flag.png', 'teams/1043/crest.png', 'teams/1043/kits/0/jersey.png',
                     'players/9001/photo.png', 'game/h', 'game/f', 'game/s', 'game/st'):
            z.writestr(name, name.encode())
    return out


def test_package_comes_in_as_new_entities_linked_together(tmp_path):
    bundle = share.read(_package(tmp_path))
    assert bundle.origin == 'package'
    tree = share.children(bundle)
    assert tree['country:54'] == ['league:7'] and tree['league:7'] == ['team:1043']
    assert set(tree['team:1043']) == {'player:9001', 'player:9002'} and tree['player:9001'] == ['boot:30']
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    assert ids['country:54']['default'] is False  # the game has it: whoever uses it keeps the game's
    assert ids['country:54']['game_has'] is True and 'game_has' not in ids['team:1043']
    assert ids['team:1043'] == {'id': 131001, 'reason': 'range', 'default': True}
    chosen = {k for k, v in ids.items() if v['default']}
    share.apply(dst, bundle, ids, chosen, dest)

    p1, p2, p3 = ids['player:9001']['id'], ids['player:9002']['id'], ids['player:9003']['id']
    assert (p1, p2, p3) == (300001, 300002, 300003)
    team = dst.fields('team', 131001)
    assert team['teamcolor1'] == [1, 2, 3] and team['balltype'] == 2 and team['captainid'] == p1
    assert team['rivalteam'] == 131001 and team['formation'] == 5 and team['domesticprestige'] == 7
    assert [(r['player'], r['jersey'], r['slot']) for r in dst.roster(131001)] == [(p1, 10, 25), (p2, 1, 0)]
    assert dst.team_stadium(131001) == 1  # the game's stadium 1
    assert dst.members(ids['league:7']['id']) == [131001]  # team 1044 is not in the package
    assert dst.fields('league', 400)['countryid'] == 54 and not dst.is_created('country', 54)
    kit = dst.kits(131001)[0]
    assert kit == {'source': 'upload', 'collar': 3, 'print': {'front_number': True, 'number_color': 4}}
    assert dst.picture('team', 131001, 'kit0_jersey')[0] == b'teams/1043/kits/0/jersey.png'
    player = dst.fields('player', p1)
    assert player['nationality'] == 54 and player['name.common'] == 'A01' and player['finishing'] == 90
    assert player['shoetypecode'] == ids['boot:30']['id'] == 100  # 30 is outside the created range of the fake
    assert player['face'] == {'source': 'pack', 'pack': 'package', 'id': 9001}
    assert dst.player_files(p1) == {'head': b'game/h', 'face': b'game/f'}
    assert dst.equipment_files('boot', 100) == {'mesh': b'game/s', 'texture': b'game/st'}
    assert dst.roster(555) is None and not dst.edited('team')  # team 555 is not the game's: no link written
    assert dst.names('team', 131001)['abbr3'] == {'*': 'T01'}


def test_a_country_the_game_has_with_no_id_left_is_not_an_error(tmp_path):
    bundle = share.read(_package(tmp_path))
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))

    class Full(FakeDest):
        def allocate(self, kind, reserved):
            return None if kind == 'country' else super().allocate(kind, reserved)
    ids = share.plan(bundle, Full(dst))
    # left out, the league keeps the game's country: no new id is needed for that
    assert ids['country:54'] == {'id': None, 'reason': None, 'default': False, 'game_has': True}


def test_a_team_without_its_own_formation_gets_the_one_of_its_starters():
    from f14mod import package
    formations = {3: [0, 3, 5, 7, 12, 14, 16, 23, 25, 27, 4], 9: [0, 3, 4, 5, 7, 10, 14, 18, 21, 25, 26]}
    starters = [{'player_id': 9000 + i, 'position': p} for i, p in enumerate([0, 3, 4, 5, 7, 10, 14, 18, 21, 25, 26])]
    bench = [{'player_id': 9100, 'position': 28}, {'player_id': 9101, 'position': 29}]
    assert package._formation_of(starters + bench, formations) == 9
    assert package._formation_of(starters[:10] + bench, formations) is None  # not 11 starters
    other = starters[:10] + [{'player_id': 9050, 'position': 2}]
    assert package._formation_of(other, formations) is None  # no formation of the game has these positions


def test_the_package_formation_wins_and_a_missing_one_comes_from_the_starters(tmp_path):
    path = _package(tmp_path)
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read('package.json'))
    team = manifest['teams'][0]
    assert share.read(path, {5: [0] * 11}).by_key()['team:1043']['fields']['formation'] == 5
    team['formation'] = None
    team['roster'] = [{'player_id': 9001 + i, 'position': p} for i, p in enumerate(range(0, 22, 2))]
    with zipfile.ZipFile(path) as z:
        others = {n: z.read(n) for n in z.namelist() if n != 'package.json'}
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('package.json', json.dumps(manifest))
        for name, data in others.items():
            z.writestr(name, data)
    formations = {12: list(range(20, -1, -2)), 13: list(range(11))}
    assert share.read(path, formations).by_key()['team:1043']['fields']['formation'] == 12
    assert 'formation' not in share.read(path).by_key()['team:1043']['fields']


def _rewrite(path, change):
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read('package.json'))
        others = {n: z.read(n) for n in z.namelist() if n != 'package.json'}
    change(manifest, others)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('package.json', json.dumps(manifest))
        for name, data in others.items():
            z.writestr(name, data)


def _without_eyes_and_hair(manifest, files, generic=True):
    player = manifest['players'][0]  # 9001: head and face only
    player['raw']['players'][0].update(eyecolorcode=9, hairtypecode=17, haircolorcode=2)
    if generic:
        manifest['generic_parts'] = {'eyes': {'9': {'file': 'game/eyes9'}},
                                     'hair': {'17': {'files': {'hair': 'game/h17', 'hair_textures': 'game/t17',
                                                               'hairlod': 'game/l17'}}}}
        files.update({'game/eyes9': b'E9', 'game/h17': b'H17', 'game/t17': b'T17', 'game/l17': b'L17'})


def _imported(tmp_path, path, fill_missing, generic=None):
    bundle = share.read(path)
    dst = Project(os.path.join(tmp_path, f'dst{fill_missing}{bool(generic)}.sqlite'))
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    chosen = {k for k, v in ids.items() if v['default']}
    share.apply(dst, bundle, ids, chosen, dest, fill_missing=fill_missing, generic=generic)
    pid = ids['player:9001']['id']
    return dst.player_files(pid), dst.fields('player', pid)['face']


def test_a_face_without_eyes_and_hair_is_completed_with_the_generic_parts_of_the_package(tmp_path):
    path = _package(tmp_path)
    _rewrite(path, _without_eyes_and_hair)
    files, face = _imported(tmp_path, path, True)
    # the package's generic parts became his own (the hair textures would be painted: these fake bytes cannot be)
    assert files == {'head': b'game/h', 'face': b'game/f', 'eyes': b'E9', 'hair': b'H17', 'hair_textures': b'T17',
                     'hairlod': b'L17'}
    assert 'fill' not in face
    files, face = _imported(tmp_path, path, False)  # not wanted: as the package has it
    assert files == {'head': b'game/h', 'face': b'game/f'} and 'fill' not in face


def test_without_generic_parts_in_the_package_the_game_ones_of_the_same_codes(tmp_path):
    path = _package(tmp_path)
    _rewrite(path, lambda m, f: _without_eyes_and_hair(m, f, generic=False))
    files, face = _imported(tmp_path, path, True, {'eyes': {1, 9}, 'hair': {5}})
    assert files == {'head': b'game/h', 'face': b'game/f'}
    assert face['fill'] == {'eyes': 9}  # the game has eyes 9, not hair 17: that part stays missing


def _own_hair_but_not_from_afar(manifest, files, code=17, generic=True):
    player = manifest['players'][0]
    player['raw']['players'][0].update(eyecolorcode=0, hairtypecode=code, haircolorcode=2)
    player['face']['files'].update({
        'data/sceneassets/hair/hair_9001_0_0.rx3': {'kind': 'hair', 'file': 'game/oh'},
        'data/sceneassets/hair/hair_9001_0_textures.rx3': {'kind': 'hair', 'file': 'game/ot'}})
    files.update({'game/oh': b'OWN H', 'game/ot': b'OWN T'})
    if generic:
        manifest['generic_parts'] = {'eyes': {}, 'hair': {}, 'hairlod': {str(code): {'file': 'game/l17'}}}
        files['game/l17'] = b'L17'


def test_a_face_with_its_hair_but_not_the_one_from_afar_takes_only_the_generic_one_from_afar(tmp_path):
    path = _package(tmp_path)
    _rewrite(path, _own_hair_but_not_from_afar)
    files, face = _imported(tmp_path, path, True)
    assert files == {'head': b'game/h', 'face': b'game/f', 'hair': b'OWN H', 'hair_textures': b'OWN T',
                     'hairlod': b'L17'}  # his own hair up close stays
    assert 'fill' not in face


def test_from_afar_without_the_package_part_the_game_one_of_the_same_code(tmp_path):
    path = _package(tmp_path)
    _rewrite(path, lambda m, f: _own_hair_but_not_from_afar(m, f, generic=False))
    files, face = _imported(tmp_path, path, True, {'eyes': set(), 'hair': set(), 'hairlod': {17}})
    assert 'hairlod' not in files and face['fill'] == {'hairlod': 17}


def test_a_bald_player_needs_no_hair(tmp_path):
    path = _package(tmp_path)
    _rewrite(path, lambda m, f: _without_eyes_and_hair(m, f) or m['players'][0]['raw']['players'][0].update(
        hairtypecode=0))
    files, face = _imported(tmp_path, path, True, {'eyes': set(), 'hair': {0}, 'hairlod': {0}})
    assert files == {'head': b'game/h', 'face': b'game/f', 'eyes': b'E9'} and 'fill' not in face
