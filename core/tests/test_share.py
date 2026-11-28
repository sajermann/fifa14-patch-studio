"""The app's own share zip: export from one project, import into another, ids kept or renumbered, links kept."""
import os

from f14mod import share
from f14mod.project import Project

GAME = {'team': {241, 383}, 'player': {100, 101}, 'league': {13}, 'country': {54, 211}, 'stadium': {1},
        'adboard': {5}, 'boot': {10}, 'glove': {3}, 'ball': {2}}
FIRST = {'team': 131001, 'player': 300001, 'league': 400, 'country': 220, 'stadium': 266, 'adboard': 1001,
         'boot': 100, 'glove': 50, 'ball': 100}


class FakeDest:
    def __init__(self, project: Project):
        self.p = project

    def in_game(self, kind, oid):
        return oid in GAME[kind]

    def used(self, kind, oid):
        return oid in GAME[kind] or self.p.is_created(kind, oid)

    def in_range(self, kind, oid):
        return oid >= FIRST[kind]

    def allocate(self, kind, reserved):
        oid = FIRST[kind]
        while self.used(kind, oid) or oid in reserved:
            oid += 1
        return oid

    def changed(self, kind, oid):
        return oid in self.p.edited(kind)

    def league_members(self, lid):
        return self.p.members(lid) or [241]

    def team_roster(self, tid):
        return self.p.roster(tid) or [{'player': 100, 'jersey': 9, 'slot': 25}]


def _source(tmp_path) -> Project:
    p = Project(os.path.join(tmp_path, 'src.sqlite'))
    p.create('ball', 100, fields={'name': 'B01'})
    p.set_equipment_files('ball', 100, {'mesh': b'mesh', 'texture': b'tex'})
    p.create('boot', 100, fields={'name': 'C01'})
    p.set_equipment_files('boot', 100, {'mesh': b'bm', 'texture': b'bt'})
    p.create('player', 300001, fields={'nationality': 54, 'preferredposition1': 25, 'shoetypecode': 100,
                                      'name.common': 'A01'})
    p.set_player_source(300001, None)
    p.set_player_files(300001, {'head': b'head01'})
    p.set_picture('player', 300001, 'photo', b'png01')
    p.create('player', 300002, fields={'nationality': 54, 'preferredposition1': 0, 'name.common': 'A02'})
    p.set_player_source(300002, None)
    p.create('team', 131001, {'full': {'*': 'T01'}}, {'balltype': 100, 'rivalteam': 241, 'captainid': 300001})
    p.set_team_source(131001, None, False)
    p.set_roster(131001, [{'player': 300001, 'jersey': 10, 'slot': 25}, {'player': 300002, 'jersey': 1, 'slot': 0},
                          {'player': 100, 'jersey': 9, 'slot': 28}])
    p.set_team_stadium(131001, 1)
    p.save('team', 241, {'full': {'*': 'Edited 241'}})
    return p


def _export(p: Project, path, keys, links=None) -> str:
    w = share.Writer()
    for kind, oid in keys:
        w.add(p, kind, oid, (links or {}).get(f'{kind}:{oid}'))
    out = os.path.join(path, 'share.zip')
    w.write(out)
    return out


def test_round_trip_into_an_empty_project_keeps_ids(tmp_path):
    src = _source(tmp_path)
    keys = [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100), ('boot', 100), ('team', 241)]
    zip_path = _export(src, tmp_path, keys, {'team:131001': {'leagues': [13]}})
    bundle = share.read(zip_path)
    assert bundle.origin == 'own' and len(bundle.records) == 6
    tree = share.children(bundle)
    assert set(tree['team:131001']) == {'player:300001', 'player:300002', 'ball:100'}
    assert tree['player:300001'] == ['boot:100']
    assert share.roots(bundle, tree) == ['team:131001', 'team:241']

    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    assert all(v['id'] == int(k.split(':')[1]) and v['reason'] is None for k, v in ids.items())
    share.apply(dst, bundle, ids, set(ids), dest)

    assert dst.is_created('team', 131001) and not dst.is_created('team', 241)
    assert dst.names('team', 241) == {'full': {'*': 'Edited 241'}}
    assert dst.fields('team', 131001) == {'balltype': 100, 'rivalteam': 241, 'captainid': 300001}
    assert [r['player'] for r in dst.roster(131001)] == [300001, 300002, 100]
    assert dst.team_stadium(131001) == 1
    assert dst.player_files(300001) == {'head': b'head01'}
    assert dst.picture('player', 300001, 'photo')[0] == b'png01'
    assert dst.equipment_files('ball', 100) == {'mesh': b'mesh', 'texture': b'tex'}
    assert dst.player_source(300001) is None and dst.blank_players() == {300001, 300002}
    assert dst.members(13) == [241, 131001]  # joined the game league it was in
    assert dst.dates('team', 131001) == src.dates('team', 131001)


def test_taken_ids_are_renumbered_and_every_link_follows(tmp_path):
    src = _source(tmp_path)
    keys = [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100), ('boot', 100)]
    bundle = share.read(_export(src, tmp_path, keys))
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dst.create('team', 131001, {'full': {'*': 'Other'}})
    dst.create('player', 300001, fields={'name.common': 'Other'})
    dst.create('ball', 100, fields={'name': 'Other'})
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    assert ids['team:131001'] == {'id': 131002, 'reason': 'taken', 'default': True}
    assert ids['player:300001']['id'] == 300003 and ids['player:300002']['id'] == 300002
    assert ids['ball:100']['id'] == 101
    share.apply(dst, bundle, ids, set(ids), dest)
    assert dst.names('team', 131001) == {'full': {'*': 'Other'}}  # untouched
    assert dst.fields('team', 131002) == {'balltype': 101, 'rivalteam': 241, 'captainid': 300003}
    assert [r['player'] for r in dst.roster(131002)] == [300003, 300002, 100]
    assert dst.fields('player', 300003)['shoetypecode'] == 100  # boot 100 was free


def test_items_left_out_are_not_pointed_at(tmp_path):
    src = _source(tmp_path)
    keys = [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100), ('boot', 100)]
    bundle = share.read(_export(src, tmp_path, keys))
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    chosen = set(ids) - {'player:300001', 'ball:100'}
    share.apply(dst, bundle, ids, chosen, dest)
    assert [r['player'] for r in dst.roster(131001)] == [300002, 100]
    assert dst.fields('team', 131001) == {'rivalteam': 241}  # ball and captain dropped
    assert not dst.is_created('player', 300001)


def test_leagues_added_to_a_country_are_under_it_and_follow_its_new_id(tmp_path):
    src = Project(os.path.join(tmp_path, 'src.sqlite'))
    src.create('country', 220, {'full': {'*': 'P01'}}, {'nationname': 'P01'})
    src.create('league', 400, {'full': {'*': 'L01'}}, {'countryid': 54, 'extra_countries': [220]})
    src.create('league', 401, {'full': {'*': 'L02'}}, {'countryid': 220})
    src.save('league', 13, {'full': {'*': 'L03'}}, {'extra_countries': [220]})
    bundle = share.read(_export(src, tmp_path, [('country', 220), ('league', 400), ('league', 401), ('league', 13)]))
    tree = share.children(bundle)
    assert set(tree['country:220']) == {'league:400', 'league:401', 'league:13'}
    assert share.roots(bundle, tree) == ['country:220']

    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dst.create('country', 220, {'full': {'*': 'Other'}})
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    assert ids['country:220']['id'] == 221
    share.apply(dst, bundle, ids, set(ids), dest)
    assert dst.fields('league', 400)['extra_countries'] == [221]
    assert dst.fields('league', 13)['extra_countries'] == [221]


def _dump(p: Project) -> dict:
    con = p.connect()
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
        return {t: sorted(map(tuple, con.execute(f'SELECT * FROM {t}')), key=repr) for t in tables
                if t not in ('meta', 'dates', 'edited')}
    finally:
        con.close()


def test_apply_reports_its_steps_and_threads_give_the_same_project(tmp_path):
    src = _source(tmp_path)
    keys = [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100), ('boot', 100), ('team', 241)]
    zip_path = _export(src, tmp_path, keys, {'team:131001': {'leagues': [13]}})
    out = {}
    for workers in (1, 4):
        bundle = share.read(zip_path)
        dst = Project(os.path.join(tmp_path, f'dst{workers}.sqlite'))
        dest = FakeDest(dst)
        ids = share.plan(bundle, dest)
        seen = []
        share.apply(dst, bundle, ids, set(ids), dest, lambda *a: seen.append(a), workers=workers, memory_budget=1)
        steps = list(dict.fromkeys(s[0] for s in seen))
        assert steps == list(share.APPLY_STEPS)
        items = [s[3] for s in seen if s[0] == 'write' and s[3]]
        assert [(i['kind'], i['id']) for i in items] == [(r['kind'], r['id']) for r in bundle.records]
        assert {'kind': 'player', 'name': 'A01', 'id': 300001} in items and items[3]['name'] == 'B01'
        assert ('write', 6, 6, None) in seen
        out[workers] = _dump(dst)
    assert out[1] == out[4]


def test_a_stopped_import_changes_nothing(tmp_path):
    import threading
    src = _source(tmp_path)
    zip_path = _export(src, tmp_path, [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100)])
    bundle = share.read(zip_path)
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dst.create('player', 300009, fields={'name.common': 'A09'})
    before = _dump(dst)
    dest = FakeDest(dst)
    ids = share.plan(bundle, dest)
    cancel = threading.Event()

    def progress(step, done, total, item):
        if step == 'write' and done == 2:
            cancel.set()
    try:
        share.apply(dst, bundle, ids, set(ids), dest, progress, cancel, workers=2)
    except share.ImportCancelled:
        pass
    else:
        raise AssertionError('not stopped')
    assert _dump(dst) == before


def test_a_formation_of_the_project_travels_inside_its_team(tmp_path):
    """Exported, a team with a formation of the project carries its drawing (formation_shape); where it comes in it
    is a formation of that project again (Project.absorb_formation_shapes), the same one for the same drawing."""
    src = _source(tmp_path)
    shape = {'name': 'WM', 'base': 8, 'columns': {f'position{i}': p for i, p in
                                                  enumerate([0, 3, 5, 7, 10, 12, 16, 18, 23, 25, 26])}}
    fid = src.next_formation_id()
    src.create('formation', fid, fields=shape)
    src.save('team', 131001, src.names('team', 131001), {**src.fields('team', 131001), 'formation': fid})
    zip_path = _export(src, tmp_path, [('team', 131001)])
    rec = share.read(zip_path).by_key()['team:131001']
    assert rec['fields']['formation'] == 8 and rec['fields']['formation_shape'] == shape
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    other = dst.next_formation_id()
    dst.create('formation', other, fields={**shape, 'name': 'Other'})  # another drawing: a new one is made
    bundle = share.read(zip_path)
    ids = share.plan(bundle, FakeDest(dst))
    share.apply(dst, bundle, ids, set(ids), FakeDest(dst))
    team = ids['team:131001']['id']
    made = dst.fields('team', team)['formation']
    assert made == other + 1 and dst.formation(made) == shape and 'formation_shape' not in dst.fields('team', team)
