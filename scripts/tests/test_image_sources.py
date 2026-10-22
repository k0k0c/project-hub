"""Image sources use temporary project roots and no Hub or production data."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import image_sources as images


def png(width=1, height=1):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\xff\0\0')) + chunk(b'IEND', b''))


def brand(name):
    return struct.pack('>I', 20) + b'ftyp' + name + b'\0' * 4 + name


def jpeg():
    # A complete 2x1 JPEG: usable with either Pillow or the native fallback.
    return base64.b64decode(
        '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
        'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy'
        'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAID'
        'ASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA'
        'AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3'
        'ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm'
        'p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA'
        'AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJB'
        'UQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldY'
        'WVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbH'
        'yMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3E//Z')


class ImageSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SimpleNamespace(root=self.root)

    def put(self, name, data):
        return images.upload(self.store, name, base64.b64encode(data).decode())

    def file(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_content_address_original_and_no_database(self):
        data = png()
        source = self.put('Screenshot.APNG', data)['source']
        self.assertEqual(source, {'label': 'Screenshot.APNG', 'path':
                         'docs/artifacts/images/' + hashlib.sha256(data).hexdigest() + '.png'})
        path = self.root / source['path']
        self.assertEqual(images.read_image(path, 'original'), (data, 'image/png'))
        before = path.stat().st_mtime_ns
        self.assertEqual(self.put('renamed.png', data)['source']['path'], source['path'])
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file()], [path])

    def test_nonimage_info_does_not_open_path(self):
        with patch.object(Path, 'open', side_effect=AssertionError('must not read')):
            self.assertIsNone(images.image_info(self.root / 'missing.md'))
            self.assertIsNone(images.image_info(self.root / 'missing'))

    def test_existing_images_detect_content_without_changing_originals(self):
        cases = [('capture.png', jpeg(), 'jpeg', 'image/jpeg'),
                 ('capture.jpg', png(), 'png', 'image/png'),
                 ('drawing.png', b'<svg width="10" height="10"/>', 'svg', 'image/svg+xml')]
        with patch.object(images, '_decode', return_value=None):
            for name, raw, fmt, mime in cases:
                with self.subTest(name=name):
                    path = self.file(name, raw)
                    self.assertEqual(images.image_info(path),
                                     dict(format=fmt, mime=mime, previewAvailable=True))
                    for mode in ('original', 'thumbnail', 'full'):
                        self.assertEqual(images.read_image(path, mode), (raw, mime))
                        # PreparedSources passes already-read bytes through this path.
                        self.assertEqual(images.read_image(path, mode, content=raw), (raw, mime))
                    self.assertEqual(path.read_bytes(), raw)

    def test_upload_name_correction_uses_bytes_without_io_or_decoding(self):
        cases = [('capture.png', jpeg(), 'capture.jpg'),
                 ('capture.jpg', png(), 'capture.png'),
                 ('capture.JPEG', jpeg(), 'capture.JPEG'),
                 ('capture.APNG', png(), 'capture.APNG'),
                 ('drawing.png', b'<svg width="10" height="10"/>', 'drawing.svg'),
                 ('opaque.png', b'opaque bytes', 'opaque.png'),
                 ('unsafe.png', b'<svg onload="x()"/>', 'unsafe.png'),
                 ('opaque.bin', jpeg(), 'opaque.bin'),
                 ('a' * 251 + '.png', brand(b'avif'), 'a' * 250 + '.avif')]
        with patch.object(Path, 'open', side_effect=AssertionError('no file I/O')),\
                patch.object(images, '_decode', side_effect=AssertionError('no pixel decoding')):
            for name, content, expected in cases:
                with self.subTest(name=name):
                    self.assertEqual(images.normalized_image_name(name, content), expected)

    def test_invalid_name_base64_and_mismatch(self):
        for name in ('../a.png', '..\\a.png', '/a.png', 'C:a.png', 'a/b.png',
                     'a.png\0', 'a.png ', 'a.png.', '', '..', 'a.txt'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.put(name, png())
        for data in ('', '!!!', 'data:image/png;base64,AAAA', 'AAAA\n', '\u00e9'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                images.upload(self.store, 'a.png', data)
        with self.assertRaises(ValueError):
            self.put('a.jpg', png())
        with self.assertRaises(ValueError):
            self.put('a.png', b'not an image')

    def test_limits_before_decode_and_pixels(self):
        with patch.object(images, 'MAX_BYTES', 10):
            with self.assertRaises(ValueError):
                self.put('a.png', png())
            with self.assertRaises(ValueError):
                images.read_image(self.file('a.png', png()), 'original')
        with self.assertRaises(ValueError):
            self.put('bomb.png', png(100_000, 100_000))
        with self.assertRaises(ValueError):
            self.put('zero.png', png(0, 1))

    def test_native_fallback_formats(self):
        gif = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        bmp = b'BM' + struct.pack('<IHHI', 58, 0, 0, 54) + struct.pack('<IiiHHIIiiII', 40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0) + b'\0' * 4
        icon = b'\0\0\1\0\1\0' + b'\1\1\0\0\1\0\x20\0' + struct.pack('<II', len(png()), 22) + png()
        # Header-level fallback fixtures; full decoder validation has separate tests.
        jpeg = b'\xff\xd8\xff\xc0\0\x0b\x08\0\1\0\1\1\1\x11\0\xff\xd9'
        webp = b'RIFF' + struct.pack('<I', 22) + b'WEBPVP8X' + struct.pack('<I', 10) + b'\0' * 10
        values = [('png', png(), 'png'), ('apng', png(), 'png'), ('gif', gif, 'gif'),
                  ('jpg', jpeg, 'jpeg'), ('jpeg', jpeg, 'jpeg'), ('jfif', jpeg, 'jpeg'),
                  ('bmp', bmp, 'bmp'), ('ico', icon, 'ico'), ('webp', webp, 'webp'),
                  ('avif', brand(b'avif'), 'avif')]
        with patch.object(images, '_decode', return_value=None):
            for ext, data, fmt in values:
                with self.subTest(ext=ext):
                    path = self.root / self.put('a.' + ext, data)['source']['path']
                    info = images.image_info(path)
                    self.assertEqual(info['format'], fmt)
                    self.assertTrue(info['previewAvailable'])
                    for mode in ('thumbnail', 'full', 'original'):
                        self.assertEqual(images.read_image(path, mode), (data, info['mime']))

    def test_missing_optional_imports(self):
        with patch.dict(sys.modules, {'PIL': None, 'pillow_heif': None}):
            path = self.root / self.put('a.png', png())['source']['path']
            self.assertEqual(images.read_image(path), (png(), 'image/png'))
            self.assertTrue(images.image_info(path)['previewAvailable'])

    def test_conversion_formats_without_decoder(self):
        with patch.object(images, '_decode', return_value=None):
            for ext, data in [('tiff', b'II*\0\x08\0\0\0'), ('heic', brand(b'heic')),
                              ('heif', brand(b'mif1'))]:
                with self.subTest(ext=ext):
                    path = self.root / self.put('a.' + ext, data)['source']['path']
                    info = images.image_info(path)
                    self.assertFalse(info['previewAvailable'])
                    self.assertEqual(images.read_image(path, 'original')[0], data)
                    for mode in ('full', 'thumbnail'):
                        with self.assertRaisesRegex(ValueError, 'decoder'):
                            images.read_image(path, mode)

    def test_safe_svg_preserved(self):
        data = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><linearGradient id="g"/></defs><rect width="10" height="10" fill="url(#g)"/></svg>'
        path = self.root / self.put('drawing.svg', data)['source']['path']
        self.assertEqual(images.read_image(path, 'full'), (data, 'image/svg+xml'))
        self.assertTrue(images.image_info(path)['previewAvailable'])

    def test_unsafe_svg_rejected_on_upload_and_original_read(self):
        values = [b'<svg><script>alert(1)</script></svg>', b'<svg onload="x()"/>',
                  b'<svg><foreignObject/></svg>', b'<svg><style>rect{fill:red}</style></svg>',
                  b'<svg><use href="https://example.com/a"/></svg>',
                  b'<svg><use href="data:image/svg+xml,x"/></svg>',
                  b'<svg><image href="a.png"/></svg>', b'<svg><animate/></svg>',
                  b'<svg><rect fill="url(https://example.com/a)"/></svg>',
                  b'<svg><rect style="fill:red"/></svg>',
                  b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///a">]><svg>&x;</svg>',
                  b'<?xml-stylesheet href="http://example.com/a"?><svg/>',
                  '<svg/>'.encode('utf-16'), b'<html/>']
        for data in values:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    self.put('a.svg', data)
                for name in ('bad.svg', 'misnamed.png'):
                    with self.assertRaises(ValueError):
                        images.read_image(self.file(name, data), 'original')

    def test_invalid_read_modes_extensions_and_body(self):
        for path, mode in [(self.file('bad.png', b'bad'), 'original'),
                           (self.file('bad.txt', png()), 'original'),
                           (self.root / 'missing.png', 'invalid')]:
            with self.assertRaises(ValueError):
                images.read_image(path, mode)
        with patch.object(images, '_decode', return_value=None):
            for data in (png()[:33], png()[:-1], png() + b'trailing', png()[:40] + b'corrupt' + png()[47:]):
                with self.subTest(data=data), self.assertRaises(ValueError):
                    images.read_image(self.file('truncated.png', data), 'original')

    def test_atomic_failure_cleanup_and_existing_corruption(self):
        with patch.object(images.os, 'link', side_effect=OSError('publication failed')):
            with self.assertRaises(OSError):
                self.put('a.png', png())
        self.assertEqual(list((self.root / 'docs/artifacts/images').iterdir()), [])
        path = self.root / self.put('a.png', png())['source']['path']
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'original'):
            self.put('a.png', png())
        self.assertEqual(path.read_bytes(), b'corrupt')

    def test_concurrent_upload_same_original(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.put('a.png', png()), range(8)))
        self.assertTrue(all(result == results[0] for result in results))
        directory = self.root / 'docs/artifacts/images'
        self.assertEqual(len(list(directory.iterdir())), 1)

    def test_reject_symlink_storage(self):
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            (self.root / 'docs').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation unavailable')
        with self.assertRaises(ValueError):
            self.put('a.png', png())
        self.assertEqual(list(outside.iterdir()), [])

    def test_optional_pillow_conversion_and_orientation(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Optional Pillow is not installed')
        image = Image.new('RGB', (800, 400), 'red')
        exif = Image.Exif()
        exif[274] = 6
        output = io.BytesIO()
        image.save(output, format='JPEG', exif=exif)
        data = output.getvalue()
        path = self.root / self.put('rotated.jpg', data)['source']['path']
        for mode, size in [('thumbnail', (256, 512)), ('full', (400, 800))]:
            body, mime = images.read_image(path, mode)
            self.assertEqual(mime, 'image/png')
            with Image.open(io.BytesIO(body)) as preview:
                self.assertEqual(preview.size, size)
        with patch.object(images, '_decode', wraps=images._decode) as decode:
            images.image_info(path)
            self.assertEqual(decode.call_count, 0, 'native metadata should not decode pixels')
            images.read_image(path, 'thumbnail')
            self.assertEqual(decode.call_count, 0, 'repeat thumbnail should reuse derived bytes')
            replacement = io.BytesIO()
            Image.new('RGB', (200, 100), 'blue').save(replacement, format='JPEG')
            path.write_bytes(replacement.getvalue())
            body, _ = images.read_image(path, 'thumbnail')
            self.assertEqual(decode.call_count, 1, 'changed file must invalidate cached preview')
            with Image.open(io.BytesIO(body)) as preview:
                self.assertEqual(preview.size, (200, 100))
            path.write_bytes(data)
        self.assertEqual(images.read_image(path, 'original')[0], data)
        output = io.BytesIO()
        image.save(output, format='TIFF')
        path = self.root / self.put('a.tiff', output.getvalue())['source']['path']
        self.assertTrue(images.image_info(path)['previewAvailable'])
        self.assertEqual(images.read_image(path)[1], 'image/png')
        with self.assertRaises(ValueError):
            self.put('truncated.png', png()[:33])

    def test_optional_heif_round_trip(self):
        try:
            from PIL import Image
            import pillow_heif
        except ImportError:
            self.skipTest('Optional HEIF decoder is not installed')
        pillow_heif.register_heif_opener()
        output = io.BytesIO()
        with Image.new('RGB', (40, 20), 'green') as image:
            image.save(output, format='HEIF')
        data = output.getvalue()
        path = self.root / self.put('photo.heic', data)['source']['path']
        self.assertTrue(images.image_info(path)['previewAvailable'])
        self.assertEqual(images.read_image(path, 'original')[0], data)
        body, mime = images.read_image(path, 'full')
        self.assertEqual(mime, 'image/png')
        with Image.open(io.BytesIO(body)) as preview:
            self.assertEqual(preview.size, (40, 20))


if __name__ == '__main__':
    unittest.main()
