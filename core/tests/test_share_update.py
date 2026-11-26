"""Importing from the same origin again: the items that came in before are updated instead of coming in as copies."""
import json
import os
import sqlite3
import zipfile

from f14mod import share
from f14mod.project import Project
from test_share import FakeDest, _export, _source
from test_share_package import _package


class OriginDest(FakeDest):
    """FakeDest that knows where the project's entities came from (as the backend's GameDestination)."""

    def match(self, kind, source, source_id):
        found = self.p.find_origin(kind, source, source_id)
        uid = self.p.uid(create=False)
        if found is None and uid and source == share.project_source(uid) and self.p.is_created(kind, source_id):
            found = source_id
        return found

    def changed_since_import(self, kind, oid):
        return self.p.changed_since_import(kind, oid)


def _repack(tmp_path, name, patch_name='P01', change=None) -> str:
    """The test package with another patch name and, optionally, its manifest changed (change(manifest))."""
    src = _package(tmp_path)
    out = os.path.join(tmp_path, name)
    with zipfile.ZipFile(src) as z, zipfile.ZipFile(out, 'w') as w:
        for info in z.infolist():
            data = z.read(info.filename)
            if info.filename == 'package.json':
                manifest = json.loads(data)
                manifest['source']['patch_name'] = patch_name
                if change:
                    change(manifest)
                data = json.dumps(manifest).encode()
            w.writestr(info.filename, data)
    return out


def _import(dst: Project, path: str, as_new=()) -> dict:
    bundle = share.read(path)
    dest = OriginDest(dst)
    ids = share.as_new(share.plan(bundle, dest), as_new)
    chosen = {k for k, v in ids.items() if v['default']}
    share.apply(dst, bundle, ids, chosen, dest)
    return ids


def _v2(manifest):
    manifest['teams'][0]['names']['full'] = 'T01 v2'
    manifest['players'][0]['raw']['players'][0]['finishing'] = 95


def _counts(p: Project) -> dict:
    return {k: len(p.created(k)) for k in ('league', 'team', 'player', 'boot')}


def test_the_same_package_again_updates_what_came_in_and_adds_nothing(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    first = _import(dst, _repack(tmp_path, 'v1.zip'))
    before = _counts(dst)
    created_at = dst.dates('team', 131001)[0]
    assert dst.origin('team', 131001) == ('pkg:p01', 1043)

    bundle = share.read(_repack(tmp_path, 'v2.zip', change=_v2))
    ids = share.plan(bundle, OriginDest(dst))
    for key in ('league:7', 'team:1043', 'player:9001', 'player:9002', 'player:9003', 'boot:30'):
        assert ids[key]['reason'] == 'updates' and ids[key]['id'] == first[key]['id'], key
        assert ids[key]['changed'] is False and ids[key]['alt'] is not None
    share.apply(dst, bundle, ids, {k for k, v in ids.items() if v['default']}, OriginDest(dst))

    assert _counts(dst) == before  # no copies
    assert dst.names('team', 131001)['full'] == {'*': 'T01 v2'}
    assert dst.fields('player', first['player:9001']['id'])['finishing'] == 95
    assert dst.dates('team', 131001)[0] == created_at  # still created when it first came in


def test_an_item_renumbered_the_first_time_is_found_by_its_id_in_the_package(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dst.create('team', 131001, {'full': {'*': 'T99'}})
    first = _import(dst, _repack(tmp_path, 'v1.zip'))
    assert first['team:1043']['id'] == 131002
    again = share.plan(share.read(_repack(tmp_path, 'v2.zip')), OriginDest(dst))
    assert again['team:1043']['id'] == 131002 and again['team:1043']['reason'] == 'updates'
    assert dst.names('team', 131001) == {'full': {'*': 'T99'}}  # never touched


def test_the_patch_name_is_compared_without_case_accents_or_extra_spaces(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    _import(dst, _repack(tmp_path, 'v1.zip', 'Pacote Ação'))
    same = share.plan(share.read(_repack(tmp_path, 'same.zip', '  pacote   acao ')), OriginDest(dst))
    assert same['team:1043']['reason'] == 'updates'
    other = share.plan(share.read(_repack(tmp_path, 'other.zip', 'P02')), OriginDest(dst))
    assert other['team:1043']['reason'] == 'range'
    unnamed = share.read(_repack(tmp_path, 'unnamed.zip', None))
    assert all(r['origin'] is None for r in unnamed.records)
    assert share.plan(unnamed, OriginDest(dst))['team:1043']['reason'] == 'range'


def test_an_update_can_come_in_as_a_new_item_and_is_then_a_copy_of_its_own(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    _import(dst, _repack(tmp_path, 'v1.zip'))
    ids = _import(dst, _repack(tmp_path, 'v2.zip', change=_v2), as_new={'team:1043'})
    new = ids['team:1043']['id']
    assert new == 131002 and ids['team:1043']['reason'] == 'range'
    assert dst.names('team', 131001)['full'] == {'*': 'T01'} and dst.names('team', 131002)['full'] == {'*': 'T01 v2'}
    # its squad: the players, updated in place
    assert [r['player'] for r in dst.roster(new)] == [ids['player:9001']['id'], ids['player:9002']['id']]
    assert dst.origin('team', new) is None
    assert share.plan(share.read(_repack(tmp_path, 'v3.zip')), OriginDest(dst))['team:1043']['id'] == 131001


def test_an_item_changed_after_the_import_is_flagged(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    _import(dst, _repack(tmp_path, 'v1.zip'))
    dst.now = lambda: 4_000_000_000  # later than the import
    dst.save('team', 131001, {'full': {'*': 'T01 mine'}}, dst.fields('team', 131001))
    ids = share.plan(share.read(_repack(tmp_path, 'v2.zip')), OriginDest(dst))
    assert ids['team:1043']['changed'] is True and ids['player:9001']['changed'] is False


def test_a_deleted_item_comes_in_as_new_again(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    _import(dst, _repack(tmp_path, 'v1.zip'))
    dst.delete('team', 131001)
    assert dst.origin('team', 131001) is None
    ids = share.plan(share.read(_repack(tmp_path, 'v2.zip')), OriginDest(dst))
    assert ids['team:1043'] == {'id': 131001, 'reason': 'range', 'default': True}


def test_an_update_keeps_the_leagues_the_user_put_the_team_in(tmp_path):
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    _import(dst, _repack(tmp_path, 'v1.zip'))
    dst.set_members(13, [241, 131001])
    _import(dst, _repack(tmp_path, 'v2.zip', change=_v2))
    assert dst.members(13) == [241, 131001]


def test_a_zip_of_the_app_imported_twice_updates_and_its_origin_travels(tmp_path):
    keys = [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100), ('boot', 100)]
    os.makedirs(os.path.join(tmp_path, 'a'))
    src = _source(os.path.join(tmp_path, 'a'))
    zip_path = _export(src, os.path.join(tmp_path, 'a'), keys)
    with zipfile.ZipFile(zip_path) as z:
        manifest = json.loads(z.read(share.MANIFEST))
    assert manifest['project'] == {'uid': src.uid()}
    assert manifest['items'][0]['origin'] == {'source': share.project_source(src.uid()), 'id': 131001}

    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    dst.create('team', 131001, {'full': {'*': 'T99'}})
    first = _import(dst, zip_path)
    assert first['team:131001']['id'] == 131002
    again = share.plan(share.read(zip_path), OriginDest(dst))
    assert {k: v['reason'] for k, v in again.items()} == {k: 'updates' for k in again}
    assert again['team:131001']['id'] == 131002

    # the project's own zip coming back to it: its own entities
    own = share.plan(share.read(zip_path), OriginDest(src))
    assert own['team:131001']['reason'] == 'updates' and own['team:131001']['id'] == 131001


def test_an_item_that_came_from_a_package_keeps_that_origin_when_it_is_exported(tmp_path):
    os.makedirs(os.path.join(tmp_path, 'a'))
    a = Project(os.path.join(tmp_path, 'a', 'a.sqlite'))
    b = Project(os.path.join(tmp_path, 'b.sqlite'))
    b.create('team', 131001, {'full': {'*': 'T99'}})  # so the two give the package's team different ids
    in_a = _import(a, _repack(tmp_path, 'v1.zip'))
    in_b = _import(b, _repack(tmp_path, 'v1.zip'))
    assert in_a['team:1043']['id'] == 131001 and in_b['team:1043']['id'] == 131002
    zip_path = _export(a, os.path.join(tmp_path, 'a'), [('team', 131001)])
    ids = share.plan(share.read(zip_path), OriginDest(b))
    assert ids['team:131001']['reason'] == 'updates' and ids['team:131001']['id'] == 131002


def test_a_project_of_the_previous_schema_opens_with_no_origins(tmp_path):
    path = os.path.join(tmp_path, 'old.sqlite')
    Project(path).create('team', 131001, {'full': {'*': 'T01'}})
    con = sqlite3.connect(path)
    con.execute('DROP TABLE origins')
    con.execute("UPDATE meta SET value = '15' WHERE key = 'schema'")
    con.commit()
    con.close()
    p = Project(path)
    assert p.origin('team', 131001) is None and p.uid(create=False) is None
    assert p.names('team', 131001) == {'full': {'*': 'T01'}}
    ids = _import(p, _repack(tmp_path, 'v1.zip'))
    assert ids['team:1043']['id'] == 131002 and p.origin('team', 131002) == ('pkg:p01', 1043)


def test_a_zip_without_origins_comes_in_as_before(tmp_path):
    src = _source(tmp_path)
    zip_path = _export(src, tmp_path, [('team', 131001), ('player', 300001), ('player', 300002), ('ball', 100),
                                       ('boot', 100)])
    old = os.path.join(tmp_path, 'old.zip')
    with zipfile.ZipFile(zip_path) as z, zipfile.ZipFile(old, 'w') as w:
        for info in z.infolist():
            data = z.read(info.filename)
            if info.filename == share.MANIFEST:  # as a version before origins wrote it
                manifest = json.loads(data)
                manifest.pop('project')
                for item in manifest['items']:
                    item.pop('origin')
                data = json.dumps(manifest).encode()
            w.writestr(info.filename, data)
    dst = Project(os.path.join(tmp_path, 'dst.sqlite'))
    _import(dst, old)
    ids = share.plan(share.read(old), OriginDest(dst))
    assert ids['team:131001']['reason'] == 'taken'
