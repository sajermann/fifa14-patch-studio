"""Country flags made from a picture of the user.

The game draws a country with four files (fifa14.FLAG_FILES): three small Apt screens (BIG archives with the Apt data,
the texture's description and one DDS texture) and a plain DDS. A new flag keeps every file of a model country as it
is and swaps only the texture: the picture is drawn where the model's flag is (the area of its opaque pixels), keeping
the model's alpha, so the shape, the shadow and the size the screens expect stay the same.
"""
import io
import os
import struct
import tempfile

from PIL import Image

from . import big, fifa14, images

MODEL_NATIONS = (54, fifa14.TEMPLATE_NATION)  # the first one with all four files is the model
MAX_PICTURE = images.MAX_PICTURE


class FlagError(ValueError):
    """The picture or the model files cannot be used."""


def normalize_picture(data: bytes) -> bytes:
    """The uploaded picture as a PNG (RGBA, at most MAX_PICTURE pixels a side); raises FlagError."""
    try:
        return images.normalize_picture(data)
    except images.PictureError as e:
        raise FlagError(str(e)) from e


def draw(model: Image.Image, picture: Image.Image) -> Image.Image:
    """The model texture with `picture` in place of its flag (cover fit in the opaque area; the model's alpha)."""
    model = model.convert('RGBA')
    alpha = model.split()[3]
    box = alpha.point(lambda v: 255 if v > 200 else 0).getbbox() or (0, 0, *model.size)
    w, h = box[2] - box[0], box[3] - box[1]
    pic = picture.convert('RGBA')
    scale = max(w / pic.width, h / pic.height)  # cover: the flag fills the whole area, the excess is cut
    size = (max(1, round(pic.width * scale)), max(1, round(pic.height * scale)))
    pic = pic.resize(size, Image.LANCZOS)
    left, top = (size[0] - w) // 2, (size[1] - h) // 2
    pic = pic.crop((left, top, left + w, top + h))
    out = model.copy()
    flat = Image.new('RGBA', pic.size, (255, 255, 255, 255))
    flat.alpha_composite(pic)  # a transparent picture shows white, as a flag would
    out.paste(flat.convert('RGB'), box[:2])
    out.putalpha(alpha)
    return out


def _dds_data(blob: bytes) -> tuple[int, int] | None:
    """(offset, size) of the pixels of a one-level DXT5 DDS, or None for any other kind."""
    if blob[:4] != b'DDS ' or blob[84:88] not in (b'DXT5', b'DX10'):
        return None
    height, width = struct.unpack('<II', blob[12:20])
    mipmaps = struct.unpack('<I', blob[28:32])[0]
    if mipmaps > 1:
        return None
    offset = 148 if blob[84:88] == b'DX10' else 128
    size = width * height  # DXT5: 16 bytes per 4x4 block
    return (offset, size) if offset + size <= len(blob) else None


def _like_model(model: bytes, new: bytes) -> bytes:
    """The new texture with the model's own DDS header and trailing bytes (same size and format: only the pixels
    change); a texture of another kind is used as it is."""
    a, b = _dds_data(model), _dds_data(new)
    if a and b and a[1] == b[1]:
        return model[:a[0]] + new[b[0]:b[0] + b[1]] + model[a[0] + a[1]:]
    return new


def _texture_entry(archive: big.BigArchive) -> str:
    for name in archive.order:
        data = archive.read(name)
        if data and data[:4] == b'DDS ':
            return name
    raise FlagError(f'{archive.name}: no texture inside')


def _swap_texture(blob: bytes, picture: Image.Image) -> bytes:
    """An Apt flag archive with its texture drawn again."""
    fd, path = tempfile.mkstemp(suffix='.big')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(blob)
        archive = big.BigArchive(path)
        name = _texture_entry(archive)
        model = archive.read(name)
        return big.rebuild(path, {name: _like_model(model, images.dds(draw(images.decode_dds(model), picture)))})
    finally:
        os.remove(path)


def model_files(files) -> dict[str, bytes]:
    """{flag file pattern: bytes} of the first model country that has all four files."""
    for nid in MODEL_NATIONS:
        found = {pattern: files.read(pattern.format(nid)) for pattern in fifa14.FLAG_FILES}
        if all(found.values()):
            return found
    raise FlagError('no model flag in the game')


def flag_files(files, png: bytes) -> dict[str, bytes]:
    """{flag file pattern ('{}' = the country id): bytes} of a flag drawn from the picture."""
    with Image.open(io.BytesIO(png)) as img:
        picture = img.convert('RGBA')
    out = {}
    for pattern, blob in model_files(files).items():
        if blob[:4] == b'DDS ':
            out[pattern] = _like_model(blob, images.dds(draw(images.decode_dds(blob), picture)))
        else:
            out[pattern] = _swap_texture(blob, picture)
    return out


def preview(files, png: bytes) -> Image.Image:
    """The big flag as the screens show it (the flags512x512 texture)."""
    with Image.open(io.BytesIO(png)) as img:
        picture = img.convert('RGBA')
    model = model_files(files)[fifa14.FLAG_PICTURE]
    return draw(images.decode_dds(model), picture)
