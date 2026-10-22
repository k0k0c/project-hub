"""Installation UI preferences, separate from project settings and content."""
import hashlib
import json
import os

from project_portal import atomic_write
from task_transfer import barrier


class PreferenceError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.status = status
        self.body = dict(error=code, message=message)


def read(registry):
    path = registry.home / 'ui-preferences.json'
    if path.is_symlink():
        raise PreferenceError('preferences_invalid', 'UI preference file cannot be a link')
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        language = os.environ.get('PROJECT_HUB_UI_LANGUAGE', 'ru')
        if language not in ('ru','en'):
            language = 'ru'
        raw = b''
        value = dict(schemaVersion=1, language=language)
    else:
        if len(raw)>4096:
            raise PreferenceError('preferences_invalid', 'UI preference file exceeds supported size')
        try:
            value = json.loads(raw)
        except (ValueError,UnicodeError):
            raise PreferenceError('preferences_invalid', 'UI preferences are unreadable; keep the file for recovery') from None
        if not isinstance(value,dict) or set(value)!={'schemaVersion','language'} or value['schemaVersion']!=1 or value['language'] not in ('ru','en'):
            raise PreferenceError('preferences_invalid', 'Unsupported UI preference format')
    return dict(value, revision=hashlib.sha256(raw).hexdigest(), scope='hub', choices=['ru','en'])


def update(registry, body):
    if not isinstance(body,dict) or set(body)!={'language','expected'} or body['language'] not in ('ru','en') or not isinstance(body['expected'],str):
        raise PreferenceError('preferences_request_invalid', 'Use language ru/en and the current preference revision')
    with barrier(registry):
        current = read(registry)
        if body['expected'] != current['revision']:
            if body['language'] == current['language']:
                return current
            raise PreferenceError('preferences_conflict', 'UI preferences changed; refresh before saving',409)
        atomic_write(registry.home / 'ui-preferences.json', json.dumps(dict(schemaVersion=1,language=body['language']),sort_keys=True)+'\n')
        return read(registry)
