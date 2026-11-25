"""The files of a stadium the user creates: read from the folder of a downloaded stadium, and written into
the patch under the stadium's own id.

A stadium of the game is (same in the clean game and in the patches):
  data/sceneassets/stadium/stadium_<id>.rx3                    the scene
  data/sceneassets/stadium/stadium_<id>_<tod>_textures.rx3     its textures (1 = day, 3 = night)
  data/sceneassets/crowdplacement/crowd_<id>_<tod>.dat         where the crowd sits
  data/sceneassets/fx/glares_<id>_<n>.lnx / .rx3               the lights' glares (n = 0 1 3 4); the .lnx is text and
                                                               names its effect 'glares_<id>_<n>'
  data/sceneassets/volumefx/volumefx_<id>_<n>.rx3              (only some stadiums)
  data/ui/artassets/stadium/stadium_<id>_<v>.big               menu picture, small (Apt archive, one DDS texture)
  data/ui/artassets/stadiumsbig/st_<id>_<v>.big                menu picture, large (v = 0 1 3 4)
Nothing inside the files names the id but the .lnx effect (the scene's texture names are its own numbering), so a
stadium moves to another id by renaming its files. A downloaded stadium usually replaces one of the game's (its files
carry that id); here it becomes a new stadium.
"""
import io
import os
import re
import struct

from PIL import Image

from . import fifa14, images
from .project import STADIUM_ID_MARK, STADIUM_PICTURE

# {regex of a file name: game path with {id} and the regex groups}
PATTERNS = [
    (re.compile(r'stadium_(\d+)\.rx3$', re.I), 'data/sceneassets/stadium/stadium_{id}.rx3'),
    (re.compile(r'stadium_(\d+)_(\d+)_textures\.rx3$', re.I), 'data/sceneassets/stadium/stadium_{id}_{0}_textures.rx3'),
    (re.compile(r'crowd_(\d+)_(\d+)\.dat$', re.I), 'data/sceneassets/crowdplacement/crowd_{id}_{0}.dat'),
    (re.compile(r'glares_(\d+)_(\d+)\.lnx$', re.I), 'data/sceneassets/fx/glares_{id}_{0}.lnx'),
    (re.compile(r'glares_(\d+)_(\d+)\.rx3$', re.I), 'data/sceneassets/fx/glares_{id}_{0}.rx3'),
    (re.compile(r'volumefx_(\d+)_(\d+)\.rx3$', re.I), 'data/sceneassets/volumefx/volumefx_{id}_{0}.rx3'),
    (re.compile(r'stadium_(\d+)_(\d+)\.big$', re.I), 'data/ui/artassets/stadium/stadium_{id}_{0}.big'),
    (re.compile(r'st_(\d+)_(\d+)\.big$', re.I), 'data/ui/artassets/stadiumsbig/st_{id}_{0}.big'),
]
SCENE = 'data/sceneassets/stadium/stadium_{id}.rx3'
TEXTURES = 'data/sceneassets/stadium/stadium_{id}_{0}_textures.rx3'
TIMES_OF_DAY = (1, 3)
GLARE_VARIANTS = (0, 1, 3, 4)
PICTURE_VARIANTS = (0, 1, 3, 4)
SMALL_PICTURE, LARGE_PICTURE = PATTERNS[6][1], PATTERNS[7][1]
MAX_FOLDER_FILES = 5000  # a folder with more files than this is not a stadium's


class StadiumFolderError(ValueError):
    """The folder is not one stadium: `code` names the message (no_stadium, several_stadiums, no_scene, no_textures,
    folder_missing, too_many_files)."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(f'{code}: {detail}')
        self.code, self.detail = code, detail


def _path(pattern: str, sid, groups) -> str:
    return pattern.format(*groups, id=sid)


def game_paths(sid: int) -> list[str]:
    """Every file a stadium can have (the scene's and the menu pictures)."""
    out = [SCENE.format(id=sid)]
    out += [TEXTURES.format(t, id=sid) for t in TIMES_OF_DAY]
    out += [_path(PATTERNS[2][1], sid, (t,)) for t in TIMES_OF_DAY]
    for n in GLARE_VARIANTS:
        out += [_path(PATTERNS[3][1], sid, (n,)), _path(PATTERNS[4][1], sid, (n,))]
    out += [_path(PATTERNS[5][1], sid, (n,)) for n in (0, 1, 3)]
    for v in PICTURE_VARIANTS:
        out += [_path(SMALL_PICTURE, sid, (v,)), _path(LARGE_PICTURE, sid, (v,))]
    return out


def _glares_renamed(data: bytes, old, new) -> bytes:
    """The .lnx with its effect named after the new id ('glares_<old>_<n>' -> 'glares_<new>_<n>')."""
    return data.replace(f'glares_{old}_'.encode(), f'glares_{new}_'.encode())


def read_folder(folder: str) -> tuple[int, dict[str, bytes]]:
    """(the id the folder's stadium had, {name with STADIUM_ID_MARK: bytes}) of a downloaded stadium's folder (any
    layout: only the file names count). Raises StadiumFolderError."""
    if not folder or not os.path.isdir(folder):
        raise StadiumFolderError('folder_missing', folder or '')
    found: dict[int, dict[str, str]] = {}
    count = 0
    for root, _dirs, names in os.walk(folder):
        for name in names:
            count += 1
            if count > MAX_FOLDER_FILES:
                raise StadiumFolderError('too_many_files', str(MAX_FOLDER_FILES))
            if name.lower().startswith('specificstadium'):
                continue  # a patch's variant per home team: not part of a stadium
            for regex, pattern in PATTERNS:
                m = regex.fullmatch(name)
                if m:
                    sid, groups = int(m.group(1)), m.groups()[1:]
                    found.setdefault(sid, {})[_path(pattern, STADIUM_ID_MARK, groups)] = os.path.join(root, name)
                    break
    stadiums = {sid: files for sid, files in found.items() if SCENE.format(id=STADIUM_ID_MARK) in files}
    if not found:
        raise StadiumFolderError('no_stadium')
    if not stadiums:
        raise StadiumFolderError('no_scene')
    if len(stadiums) > 1:
        raise StadiumFolderError('several_stadiums', ', '.join(str(s) for s in sorted(stadiums)))
    sid, paths = next(iter(stadiums.items()))
    if not any(TEXTURES.format(t, id=STADIUM_ID_MARK) in paths for t in TIMES_OF_DAY):
        raise StadiumFolderError('no_textures')
    out = {}
    for name, path in sorted(paths.items()):
        with open(path, 'rb') as f:
            data = f.read()
        if name.endswith('.lnx'):
            data = _glares_renamed(data, sid, STADIUM_ID_MARK)
        out[name] = data
    return sid, out


# ---- the patch -------------------------------------------------------------------------------------------------

def _shown_size(archive: bytes) -> tuple[tuple[int, int], tuple[int, int], bytes] | None:
    """((texture width, height), (drawn width, height), the texture) of a menu picture archive."""
    try:
        entries = images._big_entries(archive)  # noqa: SLF001
    except images.UNREADABLE:
        return None
    texture = next((d for d in entries.values() if d[:4] == b'DDS '), None)
    data = next((d for d in entries.values() if d.startswith(images.APT_DATA)), b'')
    if texture is None or len(texture) < 128:
        return None
    height, width = struct.unpack('<II', texture[12:20])
    shown = (width, height)
    if len(data) >= images.APT_SHAPE_SIZE + 8:
        w, h = struct.unpack('<ff', data[images.APT_SHAPE_SIZE:images.APT_SHAPE_SIZE + 8])
        if 0 < w <= width and 0 < h <= height:
            shown = (round(w), round(h))
    return (width, height), shown, texture


def picture_archive(archive: bytes, picture: Image.Image) -> bytes | None:
    """The menu picture archive with our picture in its texture (covering the part the screen draws); None when the
    archive cannot take it (then the original stays)."""
    found = _shown_size(archive)
    if found is None:
        return None
    (width, height), shown, texture = found
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 255))
    canvas.paste(images.cover(picture, shown), (0, 0))
    buf = io.BytesIO()
    canvas.save(buf, 'DDS', pixel_format='DXT5')
    ours = buf.getvalue()
    if len(ours) != len(texture):  # a texture with mipmaps or another format: the archive's sizes would change
        return None
    at = archive.index(texture)
    return archive[:at] + ours + archive[at + len(texture):]


def _moved(path: str, old, new) -> str:
    """A stadium's game path under another id (only the file name holds it)."""
    folder, _, name = path.rpartition('/')
    return f'{folder}/' + name.replace(f'_{old}_', f'_{new}_', 1).replace(f'_{old}.', f'_{new}.', 1)


def _marked(path: str, sid: int) -> str:
    return _moved(path, sid, STADIUM_ID_MARK)


def own_name(name: str, sid: int) -> str:
    """The game path of a stadium_scene name under the stadium's id."""
    return _moved(name, STADIUM_ID_MARK, sid)


def _template(project, sid: int) -> int | None:
    """Whose files a stadium uses where it has none of its own: a created stadium's template (None from scratch),
    a game stadium's own."""
    return project.stadium_source(sid) if project.is_created('stadium', sid) else sid


def stadium_file(files, project, sid: int, path: str) -> bytes | None:
    """A file of a stadium (`path` = its game path under `sid`): its own (the folder the user gave), else the one of
    the stadium it starts from (a game stadium: its own in the game; the menu pictures only, once it has a folder)."""
    mark = _marked(path, sid)
    own = project.stadium_scene_file(sid, mark)
    if own is not None:
        return _glares_renamed(own, STADIUM_ID_MARK, sid) if path.endswith('.lnx') else own
    if project.stadium_scene_list(sid) and not mark.startswith('data/ui/'):
        return None  # a stadium of its own takes nothing of the template's scene
    template = _template(project, sid)
    if template is None:
        return None
    data = files.read(_moved(path, sid, template))
    if data is not None and path.endswith('.lnx'):
        data = _glares_renamed(data, template, sid)
    return data


class CreatedStadiumFiles:
    """The game's files with a stadium's own files under its id (the 3D preview reads it like the game): a created
    stadium's, or a game stadium's folder (then nothing of the game's own scene)."""

    def __init__(self, files, project, sid: int):
        self.files, self.project, self.sid = files, project, sid

    def read(self, path: str) -> bytes | None:
        if f'_{self.sid}' in path and ('/stadium/' in path or '/stadiumsbig/' in path):
            return stadium_file(self.files, self.project, self.sid, path)
        return self.files.read(path)

    def exists(self, path: str) -> bool:
        """Without reading the file (a stadium's textures are hundreds of MB)."""
        if f'_{self.sid}' in path and ('/stadium/' in path or '/stadiumsbig/' in path):
            own = self.project.stadium_scene_list(self.sid)
            mark = _marked(path, self.sid)
            if own and not mark.startswith('data/ui/'):
                return mark in own
            template = _template(self.project, self.sid)
            return mark in own or (template is not None and self.files.exists(_moved(path, self.sid, template)))
        return self.files.exists(path)


def picture_slot(variant: int) -> str:
    """The project's picture slot of a stadium's menu picture."""
    return STADIUM_PICTURE.format(variant)


def own_pictures(project, sid: int) -> list[int]:
    """The variants the user gave a picture of their own."""
    return [v for v in PICTURE_VARIANTS if project.picture('stadium', sid, picture_slot(v)) is not None]


def _draw_pictures(project, sid: int, read) -> dict[str, bytes]:
    """{game path: archive} of the menu pictures the user gave the stadium, drawn into its archives (`read(path)` =
    the archive it has; one that cannot take the picture keeps its own)."""
    out = {}
    for v in PICTURE_VARIANTS:
        picture = project.picture('stadium', sid, picture_slot(v))
        if picture is None:
            continue
        img = images.decode_png(picture[0])
        for pattern in (SMALL_PICTURE, LARGE_PICTURE):
            path = pattern.format(v, id=sid)
            archive = read(path)
            made = picture_archive(archive, img) if archive is not None else None
            if made is not None:
                out[path] = made
    return out


def patch_files(files, project, sid: int) -> dict[str, bytes]:
    """{game path: bytes} of a created stadium: its scene (own or the template's) and its menu pictures (with the
    user's pictures drawn into them)."""
    out = {}
    for path in game_paths(sid):
        data = stadium_file(files, project, sid, path)
        if data is not None:
            out[path] = data
    # a stadium without menu archives (made from scratch) draws the user's pictures into the generic stadium's
    out.update(_draw_pictures(project, sid, lambda p: out.get(p) or files.read(_moved(p, sid, fifa14.TEMPLATE_STADIUM))))
    return out


def game_stadium_files(files, project, sid: int) -> dict[str, bytes]:
    """{game path: bytes} of a game stadium the user changed: the files of the folder the user gave it (under its id)
    and the menu pictures the user replaced (drawn into the folder's archives, else the game's)."""
    out = {}
    for name in project.stadium_scene_list(sid):
        data = project.stadium_scene_file(sid, name)
        out[own_name(name, sid)] = _glares_renamed(data, STADIUM_ID_MARK, sid) if name.endswith('.lnx') else data
    out.update(_draw_pictures(project, sid, lambda p: out.get(p) or files.read(p)))
    return out


def has_own_files(project, sid: int) -> bool:
    """The stadium (the game's) reads its files through StadiumFiles: it has a folder of its own."""
    return bool(project.stadium_scene_list(sid))
