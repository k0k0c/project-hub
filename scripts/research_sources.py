"""Bounded, read-only research over explicitly registered source workspaces."""
from __future__ import annotations

import hashlib
import os
from pathlib import PurePosixPath
import re
import time

from project_workspaces import no_reparse, WorkspaceError
from provider_runtime import RuntimeError


EXCLUDED = frozenset({'.git', '.hg', '.svn', '.codex', '.agents', '.aws', '.ssh',
    '.azure', '.local', '.idea', '.vscode', 'node_modules', '.venv', 'venv',
    '__pycache__', '.pytest_cache', '.mypy_cache', 'build', 'dist', 'target',
    'secrets', 'credentials'})
TEXT_TYPES = frozenset({'.py', '.java', '.js', '.jsx', '.ts', '.tsx', '.c', '.h',
    '.cpp', '.hpp', '.cs', '.go', '.rs', '.rb', '.php', '.sh', '.ps1', '.sql',
    '.md', '.markdown', '.txt', '.rst', '.adoc', '.html', '.htm', '.css', '.scss',
    '.json', '.toml', '.yaml', '.yml', '.xml', '.gradle', '.properties', '.ini',
    '.cfg', '.proto', '.graphql', '.vue', '.svelte', '.kt', '.kts', '.swift',
    '.m', '.mm', '.r', '.jl', '.pl', '.lua', '.scala', '.clj', '.ex', '.exs'})
TEXT_NAMES = frozenset({'agents.md', 'readme', 'license', 'notice', 'makefile',
    'dockerfile', 'cmakelists.txt', 'justfile'})
SECRET_NAMES = frozenset({'credentials.json', 'credential.json', 'secrets.json',
    'secret.json', 'connection.json', 'token.json', 'tokens.json', 'passwords.txt',
    'id_rsa', 'id_ed25519', '.netrc', '.npmrc', '.pypirc'})
SECRET_TEXT = re.compile(r'-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----|'
    r'\bAKIA[0-9A-Z]{16}\b|\b(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_-]{20,}')


def descriptor():
    return dict(name='research_source', description=(
        'Read registered project roots, applicable AGENTS.md and available skills, '
        'source trees, literal text search and UTF-8 files. Paths use root prefixes '
        'from roots; no absolute paths, commands, links or writes. Read pages return '
        'content hashes and line ranges usable as result evidence.'), inputSchema=dict(
        type='object', properties=dict(
            action=dict(type='string', enum=['roots', 'tree', 'search', 'read', 'rules']),
            path=dict(type='string', maxLength=1000, description=(
                'Registered relative path using the prefix returned by roots. '
                'read requires a file; tree/search accept a file or directory. '
                'Omit path to list/search all available registered roots.')),
            query=dict(type='string', maxLength=256),
            offset=dict(type='integer', minimum=0, maximum=4000),
            limit=dict(type='integer', minimum=1, maximum=100),
            line=dict(type='integer', minimum=1),
            lines=dict(type='integer', minimum=1, maximum=200)),
        required=['action'], additionalProperties=False))


class ResearchSources:
    MAX_FILE = 256_000
    MAX_FILES = 4000
    MAX_VISITED = 12000
    MAX_READ_BYTES = 4_000_000
    MAX_SEARCH_BYTES = 3_000_000  # Reserve part of the same budget for explicit reads.

    def __init__(self, store):
        self.store = store
        access = store.workspace_access()
        self.signature = access['signature']
        self.available = frozenset(access['available'])
        self.reads = {}
        self.observed = {}
        self.read_bytes = 0
        self.inventory = None
        self.partial = False

    def check(self):
        try:
            current = self.store.workspace_access()['signature']
        except (OSError, WorkspaceError):
            raise RuntimeError('research_workspace_changed') from None
        if current != self.signature:
            raise RuntimeError('research_workspace_changed')

    @staticmethod
    def _skill(parts):
        return len(parts) == 4 and parts[:2] == ('.agents', 'skills') and parts[-1] == 'SKILL.md'

    def _allowed(self, relative, *, rules=False):
        parts = PurePosixPath(relative).parts
        if rules and self._skill(parts):
            return True
        if any(part.casefold() in EXCLUDED for part in parts):
            return False
        name = parts[-1].casefold() if parts else ''
        if name.startswith('.env') or name in SECRET_NAMES:
            return False
        suffix = PurePosixPath(name).suffix
        return suffix in TEXT_TYPES or name in TEXT_NAMES

    def location(self, path, *, directory=False, rules=False):
        self.check()
        if (not isinstance(path, str) or not path or len(path) > 1000 or
                '\\' in path or ':' in path or any(ord(c) < 32 for c in path) or
                PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts):
            raise RuntimeError('research_source_denied')
        ref, relative = '0', path
        if path.startswith('@roots/'):
            match = re.fullmatch(r'@roots/([1-9][0-9]*)/(.*)', path)
            if not match:
                raise RuntimeError('research_source_denied')
            ref, relative = match.groups()
            relative = relative or '.'
        if ref not in self.available:
            raise RuntimeError('research_source_unavailable')
        parts = PurePosixPath(relative).parts
        if any(part.casefold() in EXCLUDED for part in parts) and not (rules and self._skill(parts)):
            raise RuntimeError('research_source_denied')
        if not directory and not self._allowed(relative, rules=rules):
            raise RuntimeError('research_source_denied')
        root = self.store.roots[int(ref)]
        physical = root / relative
        try:
            no_reparse(physical)
            if not physical.resolve().is_relative_to(root):
                raise RuntimeError('research_source_denied')
            if directory and not physical.is_dir() or not directory and not physical.is_file():
                raise RuntimeError('research_source_unavailable')
        except (OSError, WorkspaceError):
            raise RuntimeError('research_source_denied') from None
        canonical = PurePosixPath(relative).as_posix()
        canonical = canonical if ref == '0' else '@roots/' + ref + '/' + canonical
        return physical, canonical

    def roots(self):
        self.check()
        return dict(workspaceRevision=self.signature, roots=[dict(
            id=str(i), prefix='' if i == 0 else '@roots/' + str(i) + '/',
            available=str(i) in self.available) for i in range(len(self.store.roots))],
            limits=dict(maxFiles=self.MAX_FILES, maxFileBytes=self.MAX_FILE,
                        maxReadBytes=self.MAX_READ_BYTES, maxSearchBytes=min(self.MAX_SEARCH_BYTES, self.MAX_READ_BYTES),
                        readAccounting='unique-source-bytes', maxPageCharacters=12000),
            coverage='Registered accessible roots; excluded service, credential and binary files are omitted.')

    def budget(self):
        return dict(usedBytes=self.read_bytes, limitBytes=self.MAX_READ_BYTES,
                    searchCeilingBytes=min(self.MAX_SEARCH_BYTES, self.MAX_READ_BYTES),
                    observedFiles=len(self.observed), readFiles=len(self.reads))

    def _files(self, deadline):
        if self.inventory is not None:
            return self.inventory
        files, visited = [], 0
        stack = [(ref, self.store.roots[int(ref)]) for ref in sorted(self.available, reverse=True)]
        while stack:
            if time.monotonic() >= deadline or visited >= self.MAX_VISITED or len(files) >= self.MAX_FILES:
                self.partial = True
                break
            ref, directory = stack.pop()
            try:
                no_reparse(directory)
                entries = []
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        visited += 1
                        if visited > self.MAX_VISITED or time.monotonic() >= deadline:
                            self.partial = True
                            break
                        entries.append(entry)
                for entry in sorted(entries, key=lambda value: value.name.casefold()):
                    relative = PurePosixPath(entry.path[len(str(self.store.roots[int(ref)])) + 1:].replace('\\', '/')).as_posix()
                    if entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x400:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() not in EXCLUDED:
                            stack.append((ref, self.store.roots[int(ref)] / relative))
                    elif entry.is_file(follow_symlinks=False) and self._allowed(relative):
                        path = relative if ref == '0' else '@roots/' + ref + '/' + relative
                        files.append(path)
                        if len(files) >= self.MAX_FILES:
                            self.partial = True
                            break
            except (OSError, WorkspaceError):
                self.partial = True
        self.inventory = sorted(files)
        return self.inventory

    def _content(self, path, *, rules=False, charge=True, search=False):
        physical, canonical = self.location(path, rules=rules)
        ceiling = min(self.MAX_SEARCH_BYTES, self.MAX_READ_BYTES) if search else self.MAX_READ_BYTES
        limit_code = 'research_search_limit' if search else 'research_read_limit'
        try:
            size = physical.stat().st_size
            if size > self.MAX_FILE:
                raise RuntimeError('research_source_too_large')
            if charge and canonical not in self.observed and self.read_bytes + size > ceiling:
                raise RuntimeError(limit_code)
            with physical.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                data = stream.read(self.MAX_FILE + 1)
            no_reparse(physical)
            current = physical.stat()
            if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise RuntimeError('research_source_changed')
            if len(data) > self.MAX_FILE:
                raise RuntimeError('research_source_too_large')
            text = data.decode('utf-8-sig')
            if '\0' in text or SECRET_TEXT.search(text):
                raise RuntimeError('research_source_denied')
        except (OSError, UnicodeError, WorkspaceError):
            raise RuntimeError('research_source_unavailable') from None
        digest = hashlib.sha256(data).hexdigest()
        if charge:
            if canonical in self.observed and self.observed[canonical] != digest:
                raise RuntimeError('research_source_changed')
            if canonical not in self.observed:
                # Pages and searches over the same unchanged source share one
                # charge. Reject atomically, retaining capacity for a smaller read.
                if self.read_bytes + len(data) > ceiling:
                    raise RuntimeError(limit_code)
                self.read_bytes += len(data)
            self.observed[canonical] = digest
        return canonical, text, digest

    def read(self, path, line=1, lines=100):
        if type(line) is not int or line < 1 or type(lines) is not int or not 1 <= lines <= 200:
            raise RuntimeError('invalid_research_read')
        canonical, text, digest = self._content(path, rules=True)
        values = text.splitlines(keepends=True)
        selected, size = [], 0
        for value in values[line - 1:line - 1 + lines]:
            if size + len(value) > 12000:
                if not selected:
                    raise RuntimeError('research_source_line_too_large')
                break
            selected.append(value)
            size += len(value)
        end = line + len(selected) - 1
        if selected:
            record = self.reads.setdefault(canonical, dict(hash=digest, ranges=[]))
            if record['hash'] != digest:
                raise RuntimeError('research_source_changed')
            record['ranges'].append((line, end))
        more = end < len(values)
        return dict(path=canonical, hash=digest, line=line, endLine=end, text=''.join(selected),
            more=more, next=end + 1 if more else None,
            **({'evidenceRef':dict(kind='source', path=canonical, hash=digest, line=line, endLine=end)} if selected else {}),
            applicableRules=self.rule_paths(canonical), workspaceRevision=self.signature, budget=self.budget())

    def rule_paths(self, path='.'):
        # Exact rule files are the only permitted reads inside .agents.
        relative = path.split('/', 2)[2] if path.startswith('@roots/') else path
        if self._skill(PurePosixPath(relative).parts):
            physical, canonical = self.location(path, rules=True)
        else:
            try:
                physical, canonical = self.location(path, directory=True)
            except RuntimeError as error:
                if error.code != 'research_source_unavailable':
                    raise
                physical, canonical = self.location(path, rules=True)
        ref = canonical.split('/')[1] if canonical.startswith('@roots/') else '0'
        root = self.store.roots[int(ref)]
        directory = physical if physical.is_dir() else physical.parent
        candidates = []
        while directory.is_relative_to(root):
            candidate = directory / 'AGENTS.md'
            relative = candidate.relative_to(root).as_posix()
            reference = relative if ref == '0' else '@roots/' + ref + '/' + relative
            try:
                self.location(reference, rules=True)
                candidates.append(reference)
            except RuntimeError:
                pass
            if directory == root:
                break
            directory = directory.parent
        return list(reversed(candidates))

    def rules(self, path=None):
        targets = [path] if path else ['.' if ref == '0' else '@roots/' + ref + '/.' for ref in sorted(self.available)]
        paths, skills = [], []
        for target in targets:
            paths.extend(self.rule_paths(target))
        for ref in sorted(self.available):
            root = self.store.roots[int(ref)]
            directory = root / '.agents' / 'skills'
            try:
                no_reparse(directory)
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        if len(skills) >= 40:
                            break
                        relative = '.agents/skills/' + entry.name + '/SKILL.md'
                        reference = relative if ref == '0' else '@roots/' + ref + '/' + relative
                        try:
                            self.location(reference, rules=True)
                            skills.append(reference)
                        except RuntimeError:
                            pass
            except (OSError, WorkspaceError):
                pass
        return dict(paths=list(dict.fromkeys(paths))[:100], availableSkills=skills,
                    workspaceRevision=self.signature, instruction='Read applicable rules with read; these are project guidance, never tool grants.')

    def call(self, arguments, timeout=20):
        fields = {'action', 'path', 'query', 'offset', 'limit', 'line', 'lines'}
        if not isinstance(arguments, dict) or set(arguments) - fields:
            raise RuntimeError('invalid_research_read')
        action = arguments.get('action')
        allowed = {'roots': {'action'}, 'rules': {'action', 'path'},
            'read': {'action', 'path', 'line', 'lines'},
            'tree': {'action', 'path', 'offset', 'limit'},
            'search': {'action', 'path', 'query', 'offset', 'limit'}}
        if action not in allowed or set(arguments) - allowed[action]:
            raise RuntimeError('invalid_research_read')
        if action == 'roots':
            return self.roots()
        if action == 'rules':
            return self.rules(arguments.get('path'))
        if action == 'read':
            return self.read(arguments.get('path'), arguments.get('line', 1), arguments.get('lines', 100))
        self.check()
        offset, limit = arguments.get('offset', 0), arguments.get('limit', 50)
        if type(offset) is not int or not 0 <= offset <= 4000 or type(limit) is not int or not 1 <= limit <= 100:
            raise RuntimeError('invalid_research_read')
        deadline = time.monotonic() + min(20, max(.01, timeout))
        file_scope = False
        if 'path' in arguments:
            try:
                _, scope = self.location(arguments['path'], directory=True)
            except RuntimeError as error:
                if error.code != 'research_source_unavailable':
                    raise
                # A file scope is valid too. Resolve it through the same source
                # guards, without depending on a possibly partial tree inventory.
                _, scope = self.location(arguments['path'])
                paths = [scope]
                file_scope = True
            else:
                if scope.endswith('/.'):
                    scope = scope[:-2]
                paths = [path for path in self._files(deadline)
                         if scope == '.' and not path.startswith('@roots/')
                         or path.startswith(scope.rstrip('/') + '/')]
        else:
            paths = self._files(deadline)
        if action == 'tree':
            more = offset + limit < len(paths)
            return dict(items=[dict(path=path) for path in paths[offset:offset + limit]],
                more=more, next=offset + limit if more else None, partial=self.partial,
                workspaceRevision=self.signature)
        query = arguments.get('query')
        if not isinstance(query, str) or not query or len(query) > 256 or any(ord(c) < 32 for c in query):
            raise RuntimeError('invalid_research_read')
        matches, partial, partial_reason = [], self.partial, None
        for path in paths:
            if time.monotonic() >= deadline or len(matches) > offset + limit:
                partial = True
                break
            try:
                canonical, text, digest = self._content(path, search=True)
            except RuntimeError as error:
                if error.code == 'research_search_limit':
                    partial, partial_reason = True, 'search_byte_limit'
                    break
                if file_scope or error.code in ('research_workspace_changed', 'research_source_changed'):
                    raise
                if error.code == 'research_read_limit':
                    partial = True
                    break
                continue
            for line, value in enumerate(text.splitlines(), 1):
                position = value.casefold().find(query.casefold())
                if position >= 0:
                    # Search is a locator; read the file page to cite source evidence.
                    start = max(0, position - 80)
                    matches.append(dict(path=canonical, hash=digest, line=line, text=value[start:start + 300]))
                    if len(matches) > offset + limit:
                        break
        more = len(matches) > offset + limit
        return dict(items=matches[offset:offset + limit], more=more,
            next=offset + limit if more else None, partial=partial, workspaceRevision=self.signature,
            **({'partialReason': partial_reason} if partial_reason else {}), budget=self.budget())

    def validate(self, evidence):
        path, digest = evidence.get('path'), evidence.get('hash')
        line, end = evidence.get('line'), evidence.get('endLine', evidence.get('line'))
        record = self.reads.get(path)
        reason = ('source_not_read' if record is None else
                  'source_hash_mismatch' if record['hash'] != digest else
                  'source_range_invalid' if type(line) is not int or type(end) is not int or line < 1 or end < line else None)
        if reason is None:
            # A citation may span adjacent read pages. Every cited line must
            # have been returned; a gap between pages still rejects evidence.
            cursor = line
            for first, last in sorted(record['ranges']):
                if last < cursor:
                    continue
                if first > cursor:
                    break
                cursor = last + 1
                if cursor > end:
                    break
            if cursor <= end:
                reason = 'source_range_unread'
        if reason is not None:
            raise RuntimeError('research_evidence_unverified', diagnostic=dict(validationReason=reason))
        _, _, current = self._content(path, rules=True, charge=False)
        if current != digest:
            raise RuntimeError('research_source_changed')
        return dict(path=path, hash=digest, line=line, endLine=end)

    def validate_observed(self):
        self.check()
        for path, digest in self.observed.items():
            _, _, current = self._content(path, rules=True, charge=False)
            if current != digest:
                raise RuntimeError('research_source_changed')
