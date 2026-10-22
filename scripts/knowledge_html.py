"""Immutable, bounded HTML document bundles. No project code is executed."""
import hashlib
import json
import mimetypes
import os
import posixpath
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

MAX_FILE = 4_000_000
MAX_BUNDLE = 32_000_000
MAX_FILES = 400
TEXT_SUFFIXES = {'.html', '.htm', '.css', '.js', '.mjs', '.json', '.md', '.txt', '.svg'}
FORBIDDEN = {'.git', '.codex', '.agents', '.aws', '.ssh', 'node_modules', '.env'}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.references = []
        self.text = []
        self.title = []
        self.in_title = False
        self.hidden = 0
        self.in_style = False
        self.in_script = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title': self.in_title = True
        if tag in ('script', 'style'): self.hidden += 1
        if tag == 'style': self.in_style = True
        if tag == 'script': self.in_script = True
        for key in ('src', 'href', 'poster', 'data'):
            if attrs.get(key): self.references.append((attrs[key], tag not in ('a', 'area')))
        if attrs.get('srcset'):
            for part in attrs['srcset'].split(','):
                if part.strip(): self.references.append((part.strip().split()[0], True))
        if attrs.get('style'): self.references.extend(css_references(attrs['style']))

    def handle_endtag(self, tag):
        if tag == 'title': self.in_title = False
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if tag == 'style': self.in_style = False
        if tag == 'script': self.in_script = False

    def handle_data(self, data):
        if self.in_title: self.title.append(data)
        if self.in_style: self.references.extend(css_references(data))
        if self.in_script: self.references.extend(script_references(data))
        if not self.hidden and data.strip(): self.text.append(data.strip())


def css_references(text):
    refs = re.findall(r'url\(\s*[\"\']?([^\s\)\"\']+)', text, re.I)
    refs += re.findall(r'@import\s+[\"\']([^\"\']+)', text, re.I)
    return [(ref, True) for ref in refs]


def script_references(text):
    refs = re.findall(r'(?:\bfrom\s*|\bimport\s*\(?\s*|\bfetch\s*\(\s*|\bnew\s+URL\s*\(\s*)[\"\'](\.{1,2}/[^\"\']+)', text)
    return [(ref, True) for ref in refs]


def safe_path(value):
    return (isinstance(value, str) and 0 < len(value) <= 1000 and '\\' not in value
            and not value.startswith('/') and all(part not in ('', '.', '..') for part in value.split('/'))
            and not any(part in FORBIDDEN or part.startswith('.env') for part in value.split('/'))
            and ':' not in value and '\x00' not in value)


def snapshot(store, root, entry_path):
    from knowledge_store import KnowledgeError
    try: entry = entry_path.absolute().relative_to(root).as_posix()
    except ValueError as error: raise KnowledgeError('unsafe_source', 'HTML entry is outside the project', 400) from error
    pending = [entry]
    files = {}
    missing = set()
    external = set()
    total = 0
    first = None
    while pending:
        relative = pending.pop()
        if relative in files: continue
        if not safe_path(relative):
            missing.add(relative); continue
        original = root / relative
        chain = [original] + list(original.parents[:len(original.parts)-len(root.parts)])
        if any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in chain):
            missing.add(relative); continue
        target = original.resolve()
        if not target.is_relative_to(root) or not target.is_file():
            missing.add(relative); continue
        if any(part in FORBIDDEN or part.startswith('.env') for part in target.relative_to(root).parts):
            missing.add(relative); continue
        size = target.stat().st_size
        if size > MAX_FILE or total + size > MAX_BUNDLE or len(files) >= MAX_FILES:
            raise KnowledgeError('html_bundle_too_large', 'HTML bundle exceeds bounded file/count/size limits', 400)
        with target.open('rb') as stream:
            before=os.fstat(stream.fileno())
            data=stream.read(MAX_FILE+1)
            after=os.fstat(stream.fileno())
        if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns) or original.resolve()!=target or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in chain):
            raise KnowledgeError('source_changed','HTML dependency changed during snapshot; retry preview',409)
        total += len(data)
        if len(data) > MAX_FILE or total > MAX_BUNDLE:
            raise KnowledgeError('html_bundle_too_large', 'HTML bundle changed beyond its size limit', 400)
        digest = store.blob(data)
        files[relative] = dict(path=relative, hash=digest, size=len(data))
        suffix = target.suffix.lower()
        if suffix not in TEXT_SUFFIXES: continue
        try: text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            if relative == entry: raise KnowledgeError('source_encoding', 'HTML import requires UTF-8', 400)
            missing.add(relative+' (non-UTF-8 dependency)'); continue
        refs = []
        if suffix in ('.html', '.htm'):
            page = Page(); page.feed(text)
            refs = page.references
            if re.search(r'<base\b|type\s*=\s*[\"\']module|http-equiv\s*=\s*[\"\']refresh',text,re.I):
                missing.add(relative+' (base/module/refresh requires explicit browser compatibility review)')
            if relative == entry: first = page
        elif suffix == '.css': refs = css_references(text)
        elif suffix in ('.js', '.mjs'): refs = script_references(text)
        for raw, resource in refs:
            url = urlsplit(raw)
            if url.scheme or url.netloc:
                if resource and (url.scheme in ('http', 'https') or url.netloc): external.add(raw)
                elif resource and url.scheme not in ('data', 'blob'): missing.add(raw)
                continue
            if not url.path: continue
            decoded = unquote(url.path)
            # Absolute URLs address a web server, not the user's filesystem.
            if decoded.startswith('/') or '\\' in decoded:
                missing.add(raw); continue
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(relative), decoded))
            if not safe_path(resolved): missing.add(raw); continue
            pending.append(resolved)
    if entry not in files or first is None:
        raise KnowledgeError('unsafe_source', 'HTML entry must be a readable project file', 400)
    ordered = [files[key] for key in sorted(files)]
    basis = [{'path': '__entry__' if f['path'] == entry else posixpath.relpath(f['path'], posixpath.dirname(entry) or '.'), 'hash': f['hash']} for f in ordered]
    fingerprint = hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()
    return dict(entry=entry, files=ordered), fingerprint, ''.join(first.title).strip()[:300] or entry_path.stem, ' '.join(first.text)[:1100], sorted(missing), sorted(external)


def validate_bundle(item):
    from knowledge_store import KnowledgeError
    if item.get('format', 'markdown') not in ('markdown', 'html'):
        raise KnowledgeError('invalid_item', 'Document format must be markdown or html', 400)
    if item.get('format') != 'html': return
    bundle = item.get('htmlBundle')
    if not isinstance(bundle, dict) or not safe_path(bundle.get('entry')) or PurePosixPath(bundle['entry']).suffix.lower() not in ('.html','.htm') or not isinstance(bundle.get('files'), list) or not 1 <= len(bundle['files']) <= MAX_FILES:
        raise KnowledgeError('invalid_html_bundle', 'HTML document needs a bounded entry/file manifest', 400)
    preserved = {s.get('hash') for s in item.get('sources', [])} | {a['hash'] for s in item.get('sources', []) for a in s.get('assets', [])}
    paths = set()
    total = 0
    for file in bundle['files']:
        if not isinstance(file, dict) or not safe_path(file.get('path')) or not re.fullmatch('[a-f0-9]{64}', str(file.get('hash', ''))) or file['hash'] not in preserved or file['path'] in paths:
            raise KnowledgeError('invalid_html_bundle', 'Manifest files must be unique safe paths backed by preserved blobs', 400)
        paths.add(file['path'])
        size=file.get('size')
        if not isinstance(size,int) or isinstance(size,bool) or not 0<=size<=MAX_FILE:
            raise KnowledgeError('invalid_html_bundle','Manifest file size exceeds limits',400)
        total+=size
    if total>MAX_BUNDLE: raise KnowledgeError('invalid_html_bundle','Manifest bundle size exceeds limits',400)
    if bundle['entry'] not in paths:
        raise KnowledgeError('invalid_html_bundle', 'HTML entry is absent from manifest', 400)


def content(store, item, path=None):
    from knowledge_store import KnowledgeError
    if item.get('format') != 'html': raise KnowledgeError('not_html', 'Select an HTML document', 400)
    validate_bundle(item)
    path = item['htmlBundle']['entry'] if path is None else path
    if not safe_path(path): raise KnowledgeError('unsafe_source', 'Unsafe bundle path', 400)
    file = next((f for f in item['htmlBundle']['files'] if f['path'] == path), None)
    if file is None: raise KnowledgeError('html_asset_missing', 'File is not in this document snapshot', 404)
    try:
        data=store.read_blob(file['hash'])
        if len(data)!=file['size']: raise KnowledgeError('invalid_html_bundle','Manifest file size differs from blob',400)
        return data
    except FileNotFoundError as error: raise KnowledgeError('html_asset_missing', 'Preserved file is unavailable', 404) from error


def mime(path):
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in ('.html', '.htm'): return 'text/html; charset=utf-8'
    if suffix in ('.js', '.mjs'): return 'text/javascript; charset=utf-8'
    if suffix == '.css': return 'text/css; charset=utf-8'
    if suffix in ('.md', '.txt', '.java', '.py'): return 'text/plain; charset=utf-8'
    guessed = mimetypes.guess_type(path)[0]
    return guessed if guessed and (guessed.startswith(('image/', 'font/')) or guessed == 'application/json') else 'application/octet-stream'


def embedded_theme(data):
    """Choose the browser's dark canvas default without changing authored CSS."""
    text = data.decode('utf-8-sig')
    # HTMLParser counts LF characters, rather than Python's wider splitlines set.
    offsets = [0] + [match.end() for match in re.finditer('\n', text)]

    class Head(HTMLParser):
        position = None
        fallback = 0
        has_scheme = False

        def source_offset(self):
            line, column = self.getpos()
            return offsets[line - 1] + column

        def handle_decl(self, decl):
            if decl.lower().startswith('doctype'):
                self.fallback = self.source_offset() + len(decl) + 3

        def handle_starttag(self, tag, attrs):
            if tag == 'head' and self.position is None:
                self.position = self.source_offset() + len(self.get_starttag_text())
            if tag == 'meta' and str(dict(attrs).get('name', '')).lower() == 'color-scheme':
                self.has_scheme = True

    head = Head()
    head.feed(text)
    if head.has_scheme: return data
    offset = head.position if head.position is not None else head.fallback
    # Native metadata supplies a UA default. Explicit HTML/CSS backgrounds and
    # a document's authored color-scheme continue to take precedence.
    metadata = '<meta name="color-scheme" content="dark" data-hub-theme>'
    signature = b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b''
    return signature + (text[:offset] + metadata + text[offset:]).encode('utf-8')
