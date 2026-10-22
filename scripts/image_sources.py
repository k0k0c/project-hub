"""Immutable local image sources; no portal, database, or mandatory dependencies.

upload accepts a store with a project ``root`` and a basename plus strict base64.
It returns a project-relative source path. Callers must resolve/authorize paths
before image_info/read_image (these functions also support external local files).
All reads/uploads are limited to 20 MiB. Reads detect the actual format from
validated content within supported image paths, including older artifacts whose
suffix names a different image format. Image-only uploads additionally require
the suffix to match. Without Pillow, raster validation is header-level, not
a guarantee that a browser can decode a complete image. No raster is decoded by
the standard-library fallback. Native JPG/JPEG/JFIF, PNG/APNG, GIF, WebP, AVIF,
BMP, ICO and safe SVG bytes can be served unchanged in that configuration.

Pillow is imported lazily. Installed decoders validate and bound decoded images
to MAX_PIXELS, normalize first-frame EXIF orientation, and produce PNG previews
(thumbnail <= 512px, full <= 4096px). Animated originals remain untouched;
previews may be still images. Unsupported native decoders fall back to original
bytes. TIFF/HEIC/HEIF require a working optional decoder for previews; pillow-heif
is registered lazily when present. Missing/broken decoders never advertise those
formats as previewable. Original reads always preserve exact validated bytes.

SVG uses a conservative static-element/attribute policy: no DTD/entities, scripts,
events, CSS, animation, embedded images, foreign content or external references.
Serve SVG only as an image response with the parent's sandbox/CSP headers, never
insert it into inline DOM. ValueError denotes invalid/unsafe/oversized input;
OSError denotes filesystem failures. No output file is overwritten on upload.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
from collections import OrderedDict
from pathlib import Path
import re
import struct
import tempfile
import threading
import warnings
import xml.etree.ElementTree as ET
import zlib

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
_TYPES = {
    'jpeg': ('image/jpeg', {'jpg', 'jpeg', 'jfif'}),
    'png': ('image/png', {'png', 'apng'}),
    'gif': ('image/gif', {'gif'}),
    'webp': ('image/webp', {'webp'}),
    'avif': ('image/avif', {'avif'}),
    'bmp': ('image/bmp', {'bmp'}),
    'ico': ('image/x-icon', {'ico'}),
    'svg': ('image/svg+xml', {'svg'}),
    'tiff': ('image/tiff', {'tif', 'tiff'}),
    'heic': ('image/heic', {'heic'}),
    'heif': ('image/heif', {'heif'}),
}
_EXTENSIONS = {ext: fmt for fmt, (_, exts) in _TYPES.items() for ext in exts}
_CONVERT = {'tiff', 'heic', 'heif'}
# Image listings are requested once per source and the browser then requests a
# preview.  Keep the small, immutable derived responses so those two requests
# do not repeatedly invoke Pillow.  The byte cap keeps a large image from
# turning an otherwise bounded process into an unbounded image cache.
_CACHE_LIMIT = 64 * 1024 * 1024
_CACHE_ENTRY_LIMIT = 8 * 1024 * 1024
_cache_lock = threading.RLock()
_info_cache = OrderedDict()
_preview_cache = OrderedDict()
_preview_cache_bytes = 0
_SVG_ELEMENTS = set('svg g defs title desc path rect circle ellipse line polyline polygon '
                    'text tspan textPath use symbol clipPath mask linearGradient '
                    'radialGradient stop pattern marker'.split())
_SVG_ATTRIBUTES = set('id version width height viewBox preserveAspectRatio x y x1 y1 x2 y2 '
                      'cx cy r rx ry d points transform fill fill-rule fill-opacity stroke '
                      'stroke-width stroke-linecap stroke-linejoin stroke-miterlimit '
                      'stroke-dasharray stroke-dashoffset stroke-opacity opacity '
                      'clip-path clip-rule mask color offset stop-color stop-opacity '
                      'gradientUnits gradientTransform spreadMethod fx fy fr '
                      'patternUnits patternContentUnits patternTransform '
                      'markerWidth markerHeight markerUnits orient refX refY '
                      'marker-start marker-mid marker-end font-family font-size '
                      'font-weight font-style text-anchor dominant-baseline dx dy '
                      'rotate textLength lengthAdjust href startOffset overflow'.split())


def _pixels(width, height):
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise ValueError('Image dimensions exceed the pixel limit or are invalid')


def _svg(data):
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError as error:
        raise ValueError('SVG must be UTF-8') from error
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml\s)', text, re.I):
        raise ValueError('SVG declarations and processing instructions are unsafe')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError('Invalid SVG') from error
    if root.tag not in ('svg', '{http://www.w3.org/2000/svg}svg'):
        raise ValueError('Not an SVG image')
    for element in root.iter():
        tag = element.tag.removeprefix('{http://www.w3.org/2000/svg}')
        if tag not in _SVG_ELEMENTS:
            raise ValueError('Unsafe SVG element')
        for key, value in element.attrib.items():
            key = key.removeprefix('{http://www.w3.org/1999/xlink}')
            if key not in _SVG_ATTRIBUTES:
                raise ValueError('Unsafe SVG attribute')
            if key == 'href' and not re.fullmatch(r'#[A-Za-z_][\w.:-]*', value):
                raise ValueError('SVG references must be local fragments')
            # No CSS escapes/comments or URL syntax except simple local paint refs.
            if any(char in value for char in ('\\', '<', '>')) or '/*' in value:
                raise ValueError('Unsafe SVG attribute value')
            cleaned = re.sub(r'url\(#[A-Za-z_][\w.:-]*\)', '', value)
            if re.search(r'url\s*\(|(?:javascript|data|https?|file):', cleaned, re.I):
                raise ValueError('Unsafe SVG URL')


def _signature(data, expected=None):
    """Detect validated content; an upload may also require a filename match."""
    fmt = None
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 33 and data[12:16] == b'IHDR':
        if data[8:12] != b'\0\0\0\r':
            raise ValueError('Invalid PNG header')
        _pixels(*struct.unpack('>II', data[16:24]))
        position = 8
        has_data = False
        while position + 12 <= len(data):
            size = int.from_bytes(data[position:position + 4], 'big')
            end = position + 12 + size
            if end > len(data):
                raise ValueError('Truncated PNG chunk')
            tag = data[position + 4:position + 8]
            checksum = int.from_bytes(data[end - 4:end], 'big')
            if zlib.crc32(data[position + 4:end - 4]) != checksum:
                raise ValueError('Invalid PNG checksum')
            has_data |= tag == b'IDAT'
            position = end
            if tag == b'IEND':
                if size or position != len(data) or not has_data:
                    raise ValueError('Invalid PNG end')
                break
        else:
            raise ValueError('Missing PNG end')
        fmt = 'png'
    elif data[:6] in (b'GIF87a', b'GIF89a') and len(data) >= 13:
        _pixels(*struct.unpack('<HH', data[6:10]))
        fmt = 'gif'
    elif data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'):
        fmt = 'jpeg'
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in (0xD9, 0xDA):
                break
            size = int.from_bytes(data[pos:pos + 2], 'big')
            if size < 2 or pos + size > len(data):
                raise ValueError('Invalid JPEG segment')
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if size < 8:
                    raise ValueError('Invalid JPEG dimensions')
                _pixels(*struct.unpack('>HH', data[pos + 3:pos + 7]))
            pos += size
    elif data.startswith(b'RIFF') and len(data) >= 20 and data[8:12] == b'WEBP':
        if int.from_bytes(data[4:8], 'little') + 8 != len(data) or data[12:16] not in (b'VP8 ', b'VP8L', b'VP8X'):
            raise ValueError('Invalid WebP container')
        if data[12:16] == b'VP8X' and len(data) >= 30:
            _pixels(1 + int.from_bytes(data[24:27], 'little'), 1 + int.from_bytes(data[27:30], 'little'))
        fmt = 'webp'
    elif data.startswith(b'BM') and len(data) >= 26:
        dib = int.from_bytes(data[14:18], 'little')
        if dib == 12:
            _pixels(*struct.unpack('<HH', data[18:22]))
        elif dib >= 40 and len(data) >= 54:
            width, height = struct.unpack('<ii', data[18:26])
            _pixels(width, abs(height))
        else:
            raise ValueError('Invalid BMP header')
        fmt = 'bmp'
    elif data.startswith(b'\0\0\1\0') and len(data) >= 22:
        count = int.from_bytes(data[4:6], 'little')
        if not count or 6 + count * 16 > len(data):
            raise ValueError('Invalid ICO directory')
        for pos in range(6, 6 + count * 16, 16):
            size, offset = struct.unpack('<II', data[pos + 8:pos + 16])
            if not size or offset < 6 + count * 16 or offset + size > len(data):
                raise ValueError('Invalid ICO entry')
        fmt = 'ico'
    elif data[:4] in (b'II*\0', b'MM\0*', b'II+\0', b'MM\0+') and len(data) >= 8:
        fmt = 'tiff'
    elif len(data) >= 16 and data[4:8] == b'ftyp':
        size = int.from_bytes(data[:4], 'big')
        if size < 16 or size > len(data) or size % 4:
            raise ValueError('Invalid image brand box')
        brands = {data[8:12]} | {data[i:i + 4] for i in range(16, size, 4)}
        if brands & {b'avif', b'avis'}:
            fmt = 'avif'
        elif brands & {b'heic', b'heix', b'hevc', b'hevx'}:
            fmt = 'heic'
        elif brands & {b'mif1', b'msf1'}:
            fmt = 'heif'
    elif expected in (None, 'svg'):
        _svg(data)
        fmt = 'svg'
    if fmt is None or (expected is not None and fmt != expected and {fmt, expected} != {'heic', 'heif'}):
        raise ValueError('Image content does not match a supported filename type')
    return fmt


def normalized_image_name(name, content):
    """Correct an image suffix using bounded upload bytes, without decoding.

    Callers validate the basename and byte limit. Opaque/invalid artifacts keep
    their names; this helper does not make them eligible for image previews.
    """
    path = Path(name)
    expected = _EXTENSIONS.get(path.suffix.lower().lstrip('.'))
    if expected is None:
        return name
    try:
        fmt = _signature(content)
    except ValueError:
        return name
    if fmt == expected or {fmt, expected} == {'heic', 'heif'}:
        return name
    suffix = '.' + {'jpeg': 'jpg', 'tiff': 'tif'}.get(fmt, fmt)
    return path.stem[:255 - len(suffix)] + suffix


def _decode(data, fmt):
    """Return a loaded first frame, or None if its optional decoder is absent."""
    if fmt == 'svg':
        return None
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    if fmt in ('heic', 'heif'):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
    Image.init()
    decoder = {'heic': 'HEIF', 'heif': 'HEIF'}.get(fmt, fmt.upper())
    if decoder not in Image.OPEN:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                _pixels(*image.size)
                image.load()
                result = ImageOps.exif_transpose(image)
                return result.convert('RGBA' if 'A' in result.getbands() or 'transparency' in result.info else 'RGB')
    except Exception as error:
        raise ValueError('Image decoder rejected the image') from error


def _read(path):
    path = Path(path)
    expected = _EXTENSIONS.get(path.suffix.lower().lstrip('.'))
    if expected is None:
        return None
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Image must contain 1 byte to 20 MiB')
    return data, _signature(data)


def _file_key(path):
    """Return a change-sensitive cache key without retaining file handles."""
    path = Path(path)
    stat = path.stat()
    with path.open('rb') as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError('Image must contain 1 byte to 20 MiB')
    return (str(path), hashlib.sha256(content).digest())


def _cache_get(cache, key):
    with _cache_lock:
        value = cache.pop(key, None)
        if value is not None:
            cache[key] = value
        return value


def _cache_put_preview(key, value):
    global _preview_cache_bytes
    if len(value[0]) > _CACHE_ENTRY_LIMIT:
        return
    with _cache_lock:
        old = _preview_cache.pop(key, None)
        if old is not None:
            _preview_cache_bytes -= len(old[0])
        _preview_cache[key] = value
        _preview_cache_bytes += len(value[0])
        while _preview_cache and _preview_cache_bytes > _CACHE_LIMIT:
            _, removed = _preview_cache.popitem(last=False)
            _preview_cache_bytes -= len(removed[0])


def image_info(path):
    """Return format/mime/previewAvailable; None only for non-image suffixes."""
    if _EXTENSIONS.get(Path(path).suffix.lower().lstrip('.')) is None:
        return None
    item = _read(path)
    if item is None:
        return None
    data, fmt = item
    key = (str(path), hashlib.sha256(data).digest())
    cached = _cache_get(_info_cache, key)
    if cached is not None:
        return dict(cached)
    # Signature validation already guarantees that native browser formats can
    # be served unchanged.  Avoid a full Pillow decode during state listing;
    # conversion formats still need the optional decoder check.
    decoded = None
    if fmt in _CONVERT:
        try:
            decoded = _decode(data, fmt)
        except ValueError:
            decoded = None
    available = fmt not in _CONVERT or decoded is not None
    if decoded is not None:
        decoded.close()
    result = {'format': fmt, 'mime': _TYPES[fmt][0], 'previewAvailable': available}
    with _cache_lock:
        _info_cache[key] = result
        while len(_info_cache) > 512:
            _info_cache.popitem(last=False)
    return dict(result)


def read_image(path, preview='thumbnail', *, content=None):
    """Return (bytes, mime); original is byte-exact, other modes may convert."""
    if preview not in ('thumbnail', 'full', 'original'):
        raise ValueError('Unknown image preview mode')
    if _EXTENSIONS.get(Path(path).suffix.lower().lstrip('.')) is None:
        raise ValueError('Not a supported image extension')
    item = _read(path) if content is None else (content, _signature(content))
    data, fmt = item
    key = (str(path), hashlib.sha256(data).digest(), preview)
    if preview != 'original':
        cached = _cache_get(_preview_cache, key)
        if cached is not None:
            return cached
    if preview == 'original':
        decoded = _decode(data, fmt)
        if decoded is not None:
            decoded.close()
        return data, _TYPES[fmt][0]
    decoded = _decode(data, fmt)
    if decoded is None:
        if fmt in _CONVERT:
            raise ValueError('Image preview requires an optional working decoder')
        return data, _TYPES[fmt][0]
    try:
        edge = 512 if preview == 'thumbnail' else 4096
        decoded.thumbnail((edge, edge))
        output = io.BytesIO()
        decoded.save(output, format='PNG')
        result = (output.getvalue(), 'image/png')
        _cache_put_preview(key, result)
        return result
    finally:
        decoded.close()


def upload(store, name, contentBase64):
    """Validate and atomically publish an immutable SHA-256-addressed original."""
    if (not isinstance(name, str) or not name or len(name) > 255
            or name in ('.', '..') or any(c in name for c in '/\\:')
            or any(ord(c) < 32 for c in name) or name.rstrip(' .') != name):
        raise ValueError('Image name must be a safe basename')
    expected = _EXTENSIONS.get(Path(name).suffix.lower().lstrip('.'))
    if expected is None:
        raise ValueError('Unsupported image extension')
    if not isinstance(contentBase64, str) or len(contentBase64) > 4 * ((MAX_BYTES + 2) // 3):
        raise ValueError('Invalid or oversized base64 image')
    try:
        data = base64.b64decode(contentBase64, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Invalid base64 image') from error
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Image must contain 1 byte to 20 MiB')
    fmt = _signature(data, expected)
    decoded = _decode(data, fmt)
    if decoded is not None:
        decoded.close()
    if hasattr(store, 'registry') and hasattr(store, 'project_id'):
        from artifact_store import publish
        return publish(store, name, data, provenance='image-upload')
    root = Path(store.root).resolve(strict=True)
    directory = root
    for part in ('docs', 'artifacts', 'images'):
        directory = directory / part
        if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
            raise ValueError('Image storage must not traverse links')
        directory.mkdir(exist_ok=True)
        if not directory.resolve().is_relative_to(root):
            raise ValueError('Image storage escapes the project root')
    extension = {'jpeg': 'jpg', 'tiff': 'tif'}.get(fmt, fmt)
    target = directory / (hashlib.sha256(data).hexdigest() + '.' + extension)
    descriptor, temporary = tempfile.mkstemp(prefix='.upload-', dir=directory)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Hard-link publication is atomic and cannot replace an existing name.
            os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or target.stat().st_size != len(data):
                raise ValueError('Existing content-addressed image is not the original')
            with target.open('rb') as stream:
                if stream.read(MAX_BYTES + 1) != data:
                    raise ValueError('Existing content-addressed image is not the original')
    finally:
        os.unlink(temporary)
    return {'source': {'label': name, 'path': target.relative_to(root).as_posix()}}
