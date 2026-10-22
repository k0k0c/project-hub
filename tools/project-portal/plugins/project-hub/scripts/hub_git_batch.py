"""Native commit entry for an already prepared CAS batch; never a portal writer."""
import argparse
import json
from pathlib import Path

from git_changesets import ChangesetError, digest, hash_value
from git_integration import GitIntegrationError, commit_reviewed_batch


def main(arguments=None):
    parser = argparse.ArgumentParser(description='Commit the exact reviewed candidate with normal Git hooks and native permissions')
    parser.add_argument('--root', required=True)
    parser.add_argument('--cas', required=True, help='Existing knowledge directory containing blobs')
    parser.add_argument('--batch-blob', required=True)
    parser.add_argument('--confirmed', required=True, help='Exact batchId from the reviewed preview')
    parser.add_argument('--title', required=True)
    parser.add_argument('--url')
    args = parser.parse_args(arguments)
    location = Path(args.cas)
    if not location.is_absolute() or not location.is_dir() or not args.title.strip() or len(args.title) > 256:
        parser.error('Use an absolute existing CAS directory and a nonblank title up to 256 characters')

    def read_blob(identifier):
        if not hash_value(identifier):
            raise ChangesetError('content_corrupt', 'Invalid immutable blob reference')
        path = location / 'blobs' / identifier[:2] / identifier
        if any(item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()) for item in (path, *path.parents)):
            raise ChangesetError('content_corrupt', 'CAS evidence cannot traverse links')
        with path.open('rb') as stream:
            data = stream.read(256 * 1024 * 1024 + 1)
        if len(data) > 256 * 1024 * 1024 or digest(data) != identifier:
            raise ChangesetError('content_corrupt', 'CAS bytes failed their integrity/size check')
        return data

    def existing(data):
        identifier = digest(data)
        if read_blob(identifier) != data:
            raise ChangesetError('content_corrupt', 'Prepared candidate evidence changed')
        return identifier

    try:
        batch = json.loads(read_blob(args.batch_blob))
        if not isinstance(batch, dict):
            raise ChangesetError('invalid_batch', 'Expected a reviewed batch object')
        links = batch.get('associations')
        primary = links[0] if isinstance(links, list) and links and isinstance(links[0], dict) else {}
        context = dict(project=primary['project'], url=args.url) if args.url and primary.get('project') else None
        result = commit_reviewed_batch(args.root, batch, read_blob, existing, confirmed=args.confirmed,
                                       title=args.title, check_context=context)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (ChangesetError, GitIntegrationError, OSError, ValueError, KeyError, TypeError) as error:
        result = dict(status='error', reason=str(error), reasonCode=getattr(error, 'reason_code',
                      'filesystem_permission_denied' if isinstance(error, PermissionError) else 'batch_failed'),
                      layer=getattr(error, 'layer', 'native_permissions' if isinstance(error, PermissionError) else 'batch'),
                      operationId=args.confirmed)
        if getattr(error, 'git_outcome', None):
            result['gitOutcome'] = error.git_outcome
        print(json.dumps(result, ensure_ascii=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
