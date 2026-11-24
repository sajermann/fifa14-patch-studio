"""Advertising boards: the user's boards and the stadium script that shows them.

The game picks the boards around the pitch from a fixed table in its executable (competition -> board file), so a new
league or team cannot get its own boards from the database. The stadium script (data/fifarna/lua/assets/stadium.lua)
builds the path of the board texture, and a path may list several files separated by ';' (the game loads the first
that exists). The patch installs the game's script with three additions:
  - the competition of the match is read from the match's wipe table (wvWipe<n>.leagueID: -1 in a friendly between
    teams of different leagues, the league of both teams in a friendly between teams of the same league);
  - two tables, team id -> board and league id -> board, and a function that gives the board file of the home team,
    else the one of the league of the match, else nothing;
  - that function in front of the game's board path, so without a board the game's own one is used.
Each board the user created is written once (studioadboard_<id>.rx3, a copy of the game's board file with the user's
picture). A board of the game can be linked too (its own file, adboard_<n>_0.rx3), and edited: its new picture goes
into its own file, so it changes in every competition the game shows it in (GAME_TABLE). A board is one texture of
512x1024 with 16 bands of 512x64: the stadium decides where each band is shown and whether the bands scroll.
"""
import io
import re

from PIL import Image

from . import rx3, teamkits

MODEL = 'data/sceneassets/adboard/adboard_1_0.rx3'  # the game's board file the user's boards are written into
GAME_FILE = 'data/sceneassets/adboard/adboard_{}_0.rx3'  # a board of the game (its number)
GAME_FILE_NAME = re.compile(r'data/sceneassets/adboard/adboard_(\d+)_0\.rx3$')
DEFAULT_BOARD = 1  # the board of every competition the game's table does not list (friendlies, cups, new leagues)
# the game's table of boards (in its executable, FIFA 14 PC): competition id -> board number; every other
# competition shows DEFAULT_BOARD. Read from the executable once (study of 23/11/2026); the competitions above 2000
# and 223/224/970-999 are tournaments of the game, not leagues of its database.
GAME_TABLE = {
    353: 1, 351: 35, 80: 16, 4: 11, 7: 32, 335: 41, 336: 42, 1: 12, 13: 2, 14: 3, 60: 3, 61: 3, 16: 7, 17: 7, 19: 18,
    20: 18, 10: 14, 78: 1, 65: 34, 31: 9, 32: 9, 83: 1, 341: 24, 41: 13, 66: 26, 308: 25, 67: 38, 76: 1, 350: 39,
    50: 3, 53: 5, 54: 5, 56: 15, 189: 17, 39: 40, 2028: 1, 223: 100, 224: 101, 970: 102, 980: 103, 990: 104, 999: 105,
    2029: 106,
}
MODEL_FALLBACK = 'data/sceneassets/adboard/'  # else the first board file of the game
SCRIPT = 'data/fifarna/lua/assets/stadium.lua'
SIZE = (512, 1024)
BANDS = 16
FILE = 'data/sceneassets/adboard/studioadboard_{}.rx3'  # a board the user created (its id)

# the lines of the game's script the additions go next to (same text in the clean game and the known patches' copies
# made from it)
READ_ANCHOR = 'db.stadium[idx].adboardGroup = as:GetInt(stadium, "adboardGroup" )'
BIND_ANCHOR = 'function StadiumAssetBind(stadium)'
TEXTURE_PATH = '"data/sceneassets/adboard/adboard_${db.stadium[?].adboardID}_${db.stadium[?].adboardGroup}.rx3"'
MARK = 'StudioAdboardSrc'  # a script that already has it was made by this app


class AdboardError(ValueError):
    """The game's stadium script is not one the boards can be added to (e.g. replaced by another patch)."""


def picture(png: bytes) -> Image.Image:
    """The board as it goes to the game: the user's picture stretched to 512x1024."""
    img = Image.open(io.BytesIO(png)).convert('RGBA')
    return img if img.size == SIZE else img.resize(SIZE, Image.LANCZOS)


def model_file(files) -> bytes:
    data = files.read(MODEL)
    if data is None:
        for path in files.list(MODEL_FALLBACK):
            if path.endswith('.rx3'):
                data = files.read(path)
                if data is not None and rx3.textures(data):
                    break
        else:
            data = None
    if data is None:
        raise FileNotFoundError(MODEL)
    return data


def board_file(model: bytes, png: bytes) -> bytes:
    """The game's board file with the user's picture in every mip of its texture."""
    out = bytearray(model)
    teamkits.set_texture(out, rx3.textures(model)[0]['name'], picture(png))
    return bytes(out)


def _lua_table(name: str, links: dict[int, str]) -> str:
    return f'{name} = {{ ' + ', '.join(f'[{k}] = "{v}"' for k, v in sorted(links.items())) + ' }'


def game_boards(files) -> list[int]:
    """The numbers of the game's board files (adboard_<n>_0.rx3)."""
    return sorted(int(m.group(1)) for p in files.list('data/sceneassets/adboard/') if (m := GAME_FILE_NAME.match(p)))


def competitions_of(board: int) -> list[int]:
    """The competitions the game shows this board in (its table; DEFAULT_BOARD: also every competition it lacks)."""
    return sorted(c for c, b in GAME_TABLE.items() if b == board)


def file_name(board: int) -> str:
    """The name the stadium script loads a board by: a board of the game, or one the user created."""
    from .project import GAME_ADBOARD_MAX
    return f'adboard_{board}_0' if board <= GAME_ADBOARD_MAX else f'studioadboard_{board}'


def script(game_script: bytes, teams: dict[int, int], leagues: dict[int, int]) -> bytes:
    """The game's stadium script with the boards of `teams` / `leagues` ({id: board}: a game board number or the id
    of a board the user created)."""
    text = game_script.decode('latin-1')
    if MARK in text:
        raise AdboardError('the stadium script already has boards of a patch made by this app')
    if text.count(READ_ANCHOR) != 1 or text.count(BIND_ANCHOR) != 1 or text.count(TEXTURE_PATH) != 1:
        raise AdboardError('the stadium script is not the game\'s')
    nl = '\r\n' if '\r\n' in text else '\n'
    read = (f'{READ_ANCHOR}{nl}'
            f'\t-- competition of the match: the league of the boards (see StudioAdboardSrc){nl}'
            f'\tlocal wipe = as:GetTable("wvWipe", idx){nl}'
            f'\tdb.stadium[idx].matchLeagueID = as:GetInt(wipe, "leagueID")')
    block = nl.join([
        '-- Advertising boards of the patch: the home team\'s board, else the board of the league of the match,',
        '-- else the game\'s own (the empty string leaves the game\'s path alone)',
        _lua_table('StudioTeamAdboards', {k: file_name(v) for k, v in teams.items()}),
        _lua_table('StudioLeagueAdboards', {k: file_name(v) for k, v in leagues.items()}),
        '',
        f'function {MARK}(idx)',
        '\tlocal board = StudioTeamAdboards[db.stadium[idx].homeKitTeamID]',
        '\tif ( board == nil ) then',
        '\t\tboard = StudioLeagueAdboards[db.stadium[idx].matchLeagueID]',
        '\tend',
        '\tif ( board == nil ) then',
        '\t\treturn ""',
        '\tend',
        '\treturn "data/sceneassets/adboard/" .. board .. ".rx3;"',
        'end',
        '', '',
    ])
    text = text.replace(READ_ANCHOR, read).replace(BIND_ANCHOR, block + BIND_ANCHOR)
    text = text.replace(TEXTURE_PATH, '"${' + MARK + '(?)}' + TEXTURE_PATH[1:])
    return text.encode('latin-1')
