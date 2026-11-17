import os
import struct
import zlib

import pytest

import fakegame
from f14mod import chunk, fifa14, gamefs, images, kitfonts, rx3, t3db
from f14mod.fifa14 import Fifa14Source


def test_source_reads_the_database(game):
    src = Fifa14Source(game)
    assert len(src.leagues) == 2 and len(src.teams) == 2 and len(src.players) == 21
    assert src.team_display_name(fakegame.TEAM) == 'Test Athletic Club'  # the _upd language database wins
    assert src.team_all_names(fakegame.TEAM)['abbr3'] == 'TAT'
    assert src.league_display_name(fakegame.LEAGUE) == 'Test Premier Division of Nowhere'
    assert src.league_display_name(fakegame.PLAIN_LEAGUE) == 'Plain League'
    assert src.player_names(fakegame.STAR)['last'] == 'Plàyer'  # accents kept
    assert src.player_names(fakegame.KEEPER)['first'] == 'Edited'  # edited names win
    assert src.league_teams[fakegame.LEAGUE] == [fakegame.TEAM]


def test_archives_order(archived_game):
    src = Fifa14Source(archived_game)
    assert src.database_source == 'patch.big'  # not the broken one of data0.big
    assert src.files.where(fifa14.CREST.format(fakegame.TEAM)) == 'loose'
    assert src.files.where(fifa14.PHOTO.format(fakegame.STAR)) == 'data1.big'
    assert src.files.where('data/loc/eng_us.db') == 'locale.big'


def test_find_game_dir(loose_game):
    assert gamefs.find_game_dir(loose_game).endswith('Game')
    assert gamefs.find_game_dir(os.path.join(loose_game, 'Game')).endswith('Game')
    with pytest.raises(FileNotFoundError):
        gamefs.find_game_dir(os.path.join(loose_game, 'Game', 'data', 'db'))


def test_assets(game):
    src = Fifa14Source(game)
    assert src.crest_path(fakegame.TEAM) == f'data/ui/imgassets/crest/l{fakegame.TEAM}.dds'
    assert src.photo_path(fakegame.STAR) and src.photo_path(fakegame.KEEPER) is None
    assert set(src.league_image_paths(fakegame.LEAGUE)) == {'logo', 'banner'}
    assert src.league_image_paths(fakegame.PLAIN_LEAGUE) == {}
    assert list(src.kit_paths(fakegame.TEAM)) == [0, 1, 2]
    assert set(src.current_kits(fakegame.TEAM)) == {0, 1, 2}
    assert src.current_kits(fakegame.TEAM)[0]['jerseycollargeometrytype'] == 3  # year 0, not the classic kit
    assert src.has_face(fakegame.STAR) and not src.has_face(fakegame.KEEPER)
    assert set(src.face_paths(fakegame.STAR).values()) == {'head', 'face', 'eyes', 'hair'}
    assert src.flag_path(54) == 'data/ui/imgassets/flags512x512/f_54.dds' or src.flag_path(54) is None


def test_suspect_birthdates(loose_game):
    src = Fifa14Source(loose_game)
    assert src.suspect_birthdates == {150000}
    assert fifa14.to_date(0) == '1582-10-14'


def test_kit_textures_and_positions(loose_game):
    src = Fifa14Source(loose_game)
    for kit_type in (0, 1):  # 1 is packed in a chunkzip container
        data = src.files.read(src.kit_paths(fakegame.TEAM)[kit_type])
        tex = images.kit_textures(data)
        assert tex['jersey'].size == (64, 64) and tex['shorts'].size == (32, 16)
        assert rx3.positions(rx3.unpack(data)) == fakegame.KIT_POSITIONS


def test_unreadable_files_raise_known_errors(loose_game):
    src = Fifa14Source(loose_game)
    with pytest.raises(images.UNREADABLE):
        images.kit_textures(src.files.read(src.kit_paths(fakegame.SMALL_TEAM)[0]))
    with pytest.raises(images.UNREADABLE):
        images.decode_dds(src.files.read(src.crest_path(fakegame.SMALL_TEAM)))


def test_ink_color():
    assert kitfonts.ink_color(fakegame.number_font_rx3((250, 10, 10))) == [250, 10, 10]
    assert kitfonts.ink_color(b'nothing') is None
    assert kitfonts.family_name(b'not a font') is None


def test_remove_background(loose_game):
    src = Fifa14Source(loose_game)
    img = images.decode_dds(src.files.read(src.crest_path(fakegame.TEAM)))
    out = images.remove_background(img)
    assert out.getpixel((0, 0))[3] == 0  # the white tile is gone
    assert out.getpixel((32, 32))[3] == 255  # the crest stays


def test_refpack_and_chunks():
    # literal-only RefPack stream: header 10 FB + size, one 4-byte literal block (0xE0), then the end code with 1 byte
    stream = bytes([0x10, 0xFB, 0, 0, 5, 0xE0]) + b'abcd' + bytes([0xFD]) + b'e'
    assert chunk.refpack(stream) == b'abcde'
    # back reference: 'ab' then copy 4 bytes from 2 back -> 'ababab'
    stream = bytes([0x10, 0xFB, 0, 0, 6, (2 & 3) | ((4 - 3) << 2), 1]) + b'ab' + bytes([0xFC])
    assert chunk.refpack(stream) == b'ababab'
    packed = fakegame.chunkzip(b'hello' * 1000)
    assert chunk.decode(packed) == b'hello' * 1000
    assert chunk.decode(b'plain') == b'plain'
    with pytest.raises(chunk.ChunkError):
        chunk.decode(packed[:60])


def test_t3db_rejects_other_files():
    with pytest.raises(t3db.DatabaseError):
        t3db.read_tables(b'XX' + bytes(40), {})
    with pytest.raises(t3db.DatabaseError):
        t3db.load_meta(b'<nothing/>')


def test_not_a_game_folder(tmp_path):
    with pytest.raises(fifa14.SourceError):
        Fifa14Source(str(tmp_path))
    (tmp_path / 'data.big').write_bytes(b'BIG4' + struct.pack('<I', 16) + struct.pack('>II', 0, 16))
    with pytest.raises(fifa14.SourceError):  # an archive, but no database
        Fifa14Source(str(tmp_path))


def test_zlib_is_raw_deflate():
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    assert zlib.decompress(comp.compress(b'x') + comp.flush(), -15) == b'x'
