"""Recoverable append protocol for authoritative journals in registry mode.

SQLite durably records the exact suffix before touching the journal. A restart
finishes that suffix once. It repairs only a provably matching partial append;
unrelated/corrupt replacement data is never truncated or overwritten.
"""
import hashlib
import json
import os
import tempfile
from request_metrics import timed


def checkpoint(point):
    """Fault injection boundary; production needs no action."""


def setup(registry):
    with registry.connect() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS journal_append_intents(
            project TEXT PRIMARY KEY, event TEXT NOT NULL, seed_hash BLOB NOT NULL,
            before_hash BLOB, before_size INTEGER NOT NULL,
            after_hash BLOB NOT NULL, suffix BLOB NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS journal_append_proofs(
            project TEXT PRIMARY KEY,event TEXT NOT NULL,after_hash BLOB NOT NULL,
            journal_token TEXT)''')


def digest(data):
    return hashlib.sha256(data).digest() if data is not None else None


def hash_stream(stream, hasher, remaining=None):
    """Verify bytes with one reusable buffer instead of one allocation per chunk."""
    buffer = bytearray(1024 * 1024)
    view = memoryview(buffer)
    while remaining is None or remaining:
        target = view if remaining is None else view[:min(len(view), remaining)]
        count = stream.readinto(target)
        if not count:
            break
        hasher.update(view[:count])
        if remaining is not None:
            remaining -= count
    return remaining


@timed('append_durability')
def finish(store, row, *, input_token=None, retain_intent=False):
    models = getattr(store.registry, 'read_models', None)
    seed = (models.file_digests.digest(store.data / 'project.json') if models is not None else
            hashlib.sha256((store.data / 'project.json').read_bytes()).digest())
    if seed != row['seed_hash']:
        raise ValueError('Seed conflicts with pending journal append; history was not changed')
    if input_token is not None:
        from file_freshness import token
        appended = False
        try:
            with store.journal.open('r+b') as output:
                if token(output) == input_token:
                    output.seek(row['before_size'])
                    output.write(row['suffix'])
                    output.flush()
                    os.fsync(output.fileno())
                    appended = True
        except FileNotFoundError:
            pass  # Recovery below rejects a missing previous journal.
        if appended:
            # Windows may finalize change metadata when the writing handle
            # closes. Capture the reusable final proof only after that close.
            return verify_finish(store,row,retain_intent=retain_intent)
    try:
        current = store.journal.read_bytes()
    except FileNotFoundError:
        current = None
    current_hash = digest(current)
    if current_hash != row['after_hash']:
        # Missing and empty journals are different identities even though both
        # have a zero-length prefix.
        if row['before_hash'] is not None and current is None:
            raise ValueError('Journal is missing during append recovery')
        if row['before_hash'] is None and current == b'':
            raise ValueError('Empty journal replacement conflicts with pending append; history was not changed')
        raw = current or b''
        prefix, partial = raw[:row['before_size']], raw[row['before_size']:]
        # The ordinary append has the exact complete prior journal, so its
        # digest also proves the prefix. Partial recovery still hashes it.
        before = current_hash if len(raw) == row['before_size'] else digest(prefix if row['before_hash'] is not None else None)
        if (len(prefix) != row['before_size'] or before != row['before_hash'] or
                not bytes(row['suffix']).startswith(partial) or len(partial) > len(row['suffix'])):
            raise ValueError('Journal conflicts with pending append; history was not changed')
        if partial == bytes(row['suffix']):
            return verify_finish(store,row,retain_intent=retain_intent)
        store.journal.parent.mkdir(parents=True, exist_ok=True)
        if current is None:
            # Publish a complete first journal atomically without overwriting a
            # concurrently created target. A crash never leaves an ambiguous
            # empty target between creation and the first write.
            descriptor, temporary = tempfile.mkstemp(prefix='.journal-', dir=store.journal.parent)
            try:
                with os.fdopen(descriptor, 'wb') as output:
                    output.write(row['suffix'])
                    output.flush()
                    os.fsync(output.fileno())
                checkpoint('before_initial_publish')
                os.link(temporary, store.journal)
            finally:
                os.unlink(temporary)
        else:
            with store.journal.open('r+b') as output:
                output.seek(row['before_size'])
                output.truncate()
                output.write(row['suffix'])
                output.flush()
                os.fsync(output.fileno())
    return verify_finish(store,row,retain_intent=retain_intent)


@timed('append_verify')
def verify_finish(store,row, *, retain_intent=False):
    checkpoint('after_append')
    from file_freshness import token
    with store.journal.open('rb') as stream:
        before = token(stream)
        hasher = hashlib.sha256()
        if row['after_hash']:
            hash_stream(stream, hasher)
            actual = hasher.digest()
        else:
            remaining = hash_stream(stream, hasher, row['before_size'])
            prior_hash = hasher.digest() if row['before_hash'] is not None else None
            # One extra byte detects an unrelated tail without copying the
            # whole journal (or its prefix) into another large allocation.
            suffix = stream.read(len(row['suffix']) + 1)
            if (remaining or prior_hash != row['before_hash'] or
                    suffix != bytes(row['suffix'])):
                raise ValueError('Journal changed during append; retry recovery')
            hasher.update(suffix)
            actual = hasher.digest()
        after = token(stream)
    with store.journal.open('rb') as current:
        identity = token(current)
    if (row['after_hash'] and actual != row['after_hash']) or (before is not None and before != after) or (after is not None and after != identity):
        raise ValueError('Journal changed during append; retry recovery')
    models = getattr(store.registry,'read_models',None)
    if models is not None:
        # Reuse only the post-write proof. Opening permission and the complete
        # content digest were checked immediately above.
        if before is not None and before == after == identity:
            with models.file_digests.lock:
                models.file_digests.entries[store.journal] = identity,actual
                models.file_digests.entries.move_to_end(store.journal)
                while len(models.file_digests.entries) > 256:
                    models.file_digests.entries.popitem(last=False)
    with store.registry.connect() as c:
        if retain_intent and models is not None:
            # A reader may lend the previous completed head only while the
            # origin writer is active and these fully verified bytes remain
            # unchanged. The proof is tied to this exact durable intent.
            c.execute('INSERT OR REPLACE INTO journal_append_proofs '
                      'SELECT project,event,?,? FROM journal_append_intents '
                      'WHERE project=? AND event=?',
                      (actual,json.dumps(identity) if identity is not None else None,
                       store.project_id,row['event']))
        elif not retain_intent:
            c.execute('DELETE FROM journal_append_intents WHERE project=? AND event=?', (store.project_id, row['event']))
            c.execute('DELETE FROM journal_append_proofs WHERE project=? AND event=?', (store.project_id,row['event']))
    return actual


def prepare(store, event):
    prior = store._loaded_journal_bytes
    size = getattr(store,'_loaded_journal_size',len(prior or b''))
    last = getattr(store,'_loaded_journal_last',prior[-1:] if prior else b'')
    suffix = (b'\n' if size and last != b'\n' else b'') + json.dumps(event, ensure_ascii=False).encode() + b'\n'
    row = dict(project=store.project_id, event=event['id'], seed_hash=store._loaded_signature[0],
               before_hash=store._loaded_signature[1], before_size=size,
               after_hash=b'', suffix=suffix)
    return row


def append(store, event, *, prepared=None, retain_intent=False):
    row = prepare(store,event) if prepared is None else prepared
    with store.registry.connect() as c:
        c.execute('INSERT INTO journal_append_intents VALUES(?,?,?,?,?,?,?)', tuple(row.values()))
    checkpoint('after_intent')
    return finish(store,row,input_token=getattr(store,'_loaded_journal_token',None),retain_intent=retain_intent)


def recover(registry):
    models = getattr(registry,'read_models',None)
    if models is not None and not getattr(registry.transfer_local,'depth',0):
        from task_transfer import barrier
        with barrier(registry):
            return  # The barrier calls recovery once with its depth recorded.
    with registry.connect() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM journal_append_intents ORDER BY project')]
    for row in rows:
        store = registry.base_store(row['project'])
        with store.locked():
            actual = finish(store,row,retain_intent=models is not None)
            if models is not None:
                # Project exactly these verified bytes before any legacy
                # migration is allowed to append its deterministic audit event.
                seed,events = store._load()
                signature = store._loaded_signature
                tasks = store.project(seed,events,hierarchy=False)
        if models is not None:
            # Keep the marker visible across restart reconciliation too. Release
            # the journal handle lock before the index reader takes it again.
            from task_transfer import _origin_signature
            if signature != (row['seed_hash'],actual) or _origin_signature(store) != signature:
                raise ValueError('Journal changed during index recovery')
            getattr(registry,'_inventory_cache',{}).pop(row['project'],None)
            # Version zero preserves the remaining migration obligation if the
            # process exits after consuming the intent but before migration.
            models.publish(row['project'],seed,tasks,events,signature,
                           consume_intent=row['event'],require_migrations=True)
            checkpoint('after_recovery_publish')
            models.ensure_origin(row['project'])
