"""Writing the game's files, building a patch, installing it and taking it out (fake installation only)."""
import hashlib
import os
import shutil

import fakegame
import pytest

from f14mod import bh, builder, catalog, dbedit, install_check, installer, t3db
from f14mod.big import BigArchive, rebuild
from f14mod.project import Project


@pytest.fixture
def installed(tmp_path):
    return fakegame.build_installed(str(tmp_path))


def tree_hashes(folder):
    out = {}
    for base, _, names in os.walk(folder):
        for n in names:
            full = os.path.join(base, n)
            with open(full, 'rb') as f:
                out[os.path.relpath(full, folder)] = hashlib.sha1(f.read()).hexdigest()
    return out


def test_database_written_again_reads_the_same(installed):
    files = catalog.open_game(installed)
    raw = files.read('data/db/fifa_ng_db.db')
    once = dbedit.Database(raw).build()
    assert dbedit.Database(once).build() == once  # stable after the first write (CRCs filled in)
    meta = t3db.load_meta(files.read('data/db/fifa_ng_db-meta.xml'))
    assert t3db.read_tables(once, meta)['teams']['rows'] == t3db.read_tables(raw, meta)['teams']['rows']


def test_language_strings_new_characters_and_rows(installed):
    files = catalog.open_game(installed)
    strings = dbedit.LanguageStrings(files.read('data/loc/eng_us.db'))
    strings.set(f'TeamName_Abbr15_{fakegame.TEAM}', 'Ωmega ç €')  # characters the tree does not have
    strings.set('Brand_New_1', 'new row')
    out = t3db.read_strings(strings.build(), lambda s: True)
    assert out[f'TeamName_Abbr15_{fakegame.TEAM}'] == 'Ωmega ç €'
    assert out['Brand_New_1'] == 'new row'
    assert out[f'LeagueName_{fakegame.LEAGUE}'] == 'Test Premier Division of Nowhere'


def test_big_rebuild(installed):
    path = os.path.join(installed, 'data', 'loc', 'locale.big')
    with open(path, 'rb') as f:
        original = f.read()
    assert rebuild(path, {}) == original
    out = os.path.join(installed, '..', 'new.big')
    with open(out, 'wb') as f:
        f.write(rebuild(path, {'data/loc/eng_us.db': b'changed'}))
    assert BigArchive(out).read('data/loc/eng_us.db') == b'changed'
    assert BigArchive(out).read('data/loc/por_br.db') == BigArchive(path).read('data/loc/por_br.db')
    with pytest.raises(KeyError):
        rebuild(path, {'data/loc/missing.db': b''})


def test_bh_zero():
    data = b'ViV4' + bytes(12) + bytes(range(1, 21)) * 3
    out = bh.zero(data, [1])
    assert bh.zeroed(out) == [1]
    assert out[16 + 20:16 + 32] == data[16 + 20:16 + 32]  # offset and size kept


def test_build_install_uninstall(installed, tmp_path):
    before = tree_hashes(installed)
    project = Project(str(tmp_path / 'project.sqlite'))
    team = fakegame.TEAM
    project.save_team(team, {'abbr15': {'*': 'Everywhere', 'por_br': 'Só Aqui'}, 'full': {'eng_us': 'Full EN'}})
    assert project.counts() == {'team': 1}

    patch_dir = str(tmp_path / 'patch')
    summary = builder.build(catalog.open_game(installed), project, patch_dir)
    # the full name lives in the update database (patch.big): loose file + zeroed record in patch.bh
    assert summary['loose'] == ['data/loc/eng_us_upd.db']
    assert summary['indexes'] == {'patch.bh': 1}
    assert summary['locale'] == ['data/loc/eng_us.db', 'data/loc/por_br.db']
    loc = BigArchive(os.path.join(patch_dir, 'data', 'loc', 'locale.big'))
    pt = t3db.read_strings(loc.read('data/loc/por_br.db'), lambda s: True)
    en = t3db.read_strings(loc.read('data/loc/eng_us.db'), lambda s: True)
    assert pt[f'TeamName_Abbr15_{team}'] == 'Só Aqui'
    assert en[f'TeamName_Abbr15_{team}'] == 'Everywhere'

    installer.install(patch_dir, installed, 'test')
    assert install_check.check(installed)['state'] == 'patched'
    files = catalog.open_game(installed)  # the originals, read through the backups
    original = t3db.read_strings(files.read('data/loc/eng_us_upd.db'), lambda s: True)
    assert original[f'TeamName_{team}'] == 'Test Athletic Club'
    with open(os.path.join(installed, 'patch.bh'), 'rb') as f:
        assert len(bh.zeroed(f.read())) == 1

    # building again while installed gives the same patch
    again = str(tmp_path / 'patch2')
    builder.build(files, project, again)
    assert tree_hashes(again) == tree_hashes(patch_dir)

    installer.uninstall(installed)
    assert tree_hashes(installed) == before
    assert install_check.check(installed)['state'] == 'clean'


def test_install_replaces_the_previous_patch(installed, tmp_path):
    before = tree_hashes(installed)
    project = Project(str(tmp_path / 'project.sqlite'))
    project.save_team(fakegame.TEAM, {'full': {'*': 'One'}})
    patch_dir = str(tmp_path / 'patch')
    builder.build(catalog.open_game(installed), project, patch_dir)
    installer.install(patch_dir, installed)
    project.save_team(fakegame.TEAM, {'abbr3': {'*': 'TWO'}})
    builder.build(catalog.open_game(installed), project, patch_dir)
    installer.install(patch_dir, installed)
    assert installer.read_manifest(installed)['added'] == []  # only locale.big now (replaced)
    installer.uninstall(installed)
    assert tree_hashes(installed) == before


def test_check_finds_other_changes(installed):
    assert install_check.check(installed)['state'] == 'clean'
    loose = os.path.join(installed, 'data', 'db')
    os.makedirs(loose)
    shutil.copy(os.path.join(installed, 'patch.bh'), os.path.join(loose, 'fifa_ng_db.db'))
    result = install_check.check(installed)
    assert result['state'] == 'modified'
    assert [i['code'] for i in result['issues']] == ['loose_overrides']
    shutil.rmtree(loose)
    with open(os.path.join(installed, 'data1.bh'), 'rb') as f:
        data = f.read()
    with open(os.path.join(installed, 'data1.bh'), 'wb') as f:
        f.write(bh.zero(data, [0]))
    assert [i['code'] for i in install_check.check(installed)['issues']] == ['redirected_entries']
    os.remove(os.path.join(installed, 'data2.bh'))
    assert install_check.check(installed)['state'] == 'invalid'
    assert install_check.check(os.path.dirname(installed) + '/nowhere')['state'] == 'not_found'


def test_project_keeps_one_entity_at_a_time(tmp_path):
    project = Project(str(tmp_path / 'p.sqlite'))
    project.save_team(1, {'full': {'*': 'A', 'eng_us': ''}})
    project.save_team(2, {'abbr3': {'*': 'BBB'}})
    assert project.team_names(1) == {'full': {'*': 'A'}}
    project.reset_team(1)
    assert project.team_names(1) == {}
    assert project.counts() == {'team': 1}
