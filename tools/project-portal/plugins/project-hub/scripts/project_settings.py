"""Project-only settings with optimistic concurrency and a bounded file journal."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import tempfile
import uuid


DEFAULT_SETTINGS = {
    "git": {"autoCommit": False, "commitOn": "stage-and-task"},
    "tasks": {
        "columns": ["title", "type", "priority", "status", "progress", "estimate",
                    "created", "updated", "actions"],
        "sort": "created", "overviewSort": "created", "showCompleted": True,
        "showEpicsOnOverview": False, "showUpcomingOnOverview": True,
    },
    "viewer": {"wrapLines": True, "showSourceDetails": False},
    "architecture": {"model": "", "depth": 1, "representation": "symbols",
                     "agentSummaries": True, "descriptionDetail": "standard"},
}
SORTS = frozenset(("created", "created-oldest", "updated", "priority", "status", "progress", "title"))
COLUMNS = frozenset(DEFAULT_SETTINGS['tasks']['columns'] + ['summary', 'children'])
HISTORY_LIMIT = 100
MAX_FILE_BYTES = 1024 * 1024
MISSING_REVISION = "unconfigured-v1"


class SettingsError(ValueError):
    """Stable error code and HTTP status for transport adapters."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.status = status
        self.body = {"error": code, "message": message}


def _invalid(message):
    raise SettingsError("invalid_settings", message)


def _fields(value, keys, label, partial=False):
    if not isinstance(value, dict) or not set(value) <= set(keys):
        _invalid(label + " must be an object with known fields")
    if not partial and set(value) != set(keys):
        _invalid(label + " must contain every field")


def _validate(settings, partial=False):
    _fields(settings, DEFAULT_SETTINGS, "settings", partial)
    for section, values in settings.items():
        _fields(values, DEFAULT_SETTINGS[section], section, partial)
        for field, value in values.items():
            label = section + "." + field
            default = DEFAULT_SETTINGS[section][field]
            if section == 'architecture' and field == 'model':
                if not isinstance(value, str) or (value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}', value)):
                    _invalid(label + ' must be a native model ID or empty for Codex defaults')
            elif section == 'architecture' and field == 'depth':
                if value != 'all' and (type(value) is not int or not 1 <= value <= 10000):
                    _invalid(label + ' must be 1..10000 or all')
            elif section == 'architecture' and field in ('representation', 'descriptionDetail'):
                allowed = ('symbols', 'symbols-in-files', 'files') if field == 'representation' else ('brief', 'standard', 'detailed')
                if not isinstance(value, str) or value not in allowed:
                    _invalid(label + ' has an unsupported value')
            elif isinstance(default, bool):
                if type(value) is not bool:
                    _invalid(label + " must be boolean")
            elif field == "columns":
                if (not isinstance(value, list) or not value
                        or any(not isinstance(item, str) or item not in COLUMNS for item in value)
                        or len(value) != len(set(value)) or "title" not in value):
                    _invalid(label + " must contain unique known columns including title")
            else:
                allowed = ("stage", "task", "stage-and-task") if field == "commitOn" else SORTS
                if not isinstance(value, str) or value not in allowed:
                    _invalid(label + " has an unsupported value")


def _actor(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        _invalid("actor must be a nonempty string of at most 200 characters")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid("duplicate JSON field: " + key)
        result[key] = value
    return result


def _upgrade_settings(settings):
    # Older snapshots and audit entries predate the overview preferences.
    if isinstance(settings, dict) and isinstance(settings.get("tasks"), dict):
        settings["tasks"].setdefault("showEpicsOnOverview", False)
        settings["tasks"].setdefault("showUpcomingOnOverview", True)
    if isinstance(settings, dict):
        settings.setdefault('architecture', deepcopy(DEFAULT_SETTINGS['architecture']))
    _validate(settings)


def _read(store):
    path = Path(store.data) / "project-settings.json"
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_FILE_BYTES + 1)
    except FileNotFoundError:
        return {"settings": deepcopy(DEFAULT_SETTINGS), "revision": MISSING_REVISION,
                "history": [], "configured": False}
    try:
        if len(raw) > MAX_FILE_BYTES:
            _invalid("settings file exceeds size limit")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        _fields(value, ("settings", "revision", "history", "configured"), "settings envelope")
        _upgrade_settings(value["settings"])
        revision = value["revision"]
        if (not isinstance(revision, str) or not revision or len(revision) > 128
                or revision == MISSING_REVISION or value["configured"] is not True):
            _invalid("invalid stored revision/configured flag")
        history = value["history"]
        if not isinstance(history, list) or not 1 <= len(history) <= HISTORY_LIMIT:
            _invalid("invalid settings history length")
        previous = None
        for entry in history:
            _fields(entry, ("at", "actor", "sections", "before", "after"), "history entry")
            _actor(entry["actor"])
            if not isinstance(entry["at"], str) or len(entry["at"]) > 40:
                _invalid("invalid history timestamp")
            timestamp = datetime.fromisoformat(entry["at"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                _invalid("history timestamp must include timezone")
            _upgrade_settings(entry["before"])
            _upgrade_settings(entry["after"])
            changed = [key for key in DEFAULT_SETTINGS if entry["before"][key] != entry["after"][key]]
            if not changed or entry["sections"] != changed:
                _invalid("history sections must describe actual changes")
            if previous is not None and previous != entry["before"]:
                _invalid("settings history is discontinuous")
            previous = entry["after"]
        if previous != value["settings"]:
            _invalid("settings do not match history")
        return value
    except (ValueError, TypeError, RecursionError) as exc:
        raise SettingsError("corrupt_settings", "Invalid project-settings.json: " + str(exc), 500) from exc


def read_settings(store):
    """Return a detached envelope; absence yields defaults without creating a file."""
    # Writers fsync a complete sibling and publish with os.replace. A reader
    # opens one completed version; it need not reserve the task journal writer.
    # Parsing/history validation still rejects corrupt external changes.
    return _read(store)


def _write(store, envelope):
    path = Path(store.data) / "project-settings.json"
    payload = json.dumps(envelope, ensure_ascii=True, separators=(",", ":")) + "\n"
    if len(payload.encode("utf-8")) > MAX_FILE_BYTES:
        _invalid("settings file exceeds size limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def update_settings(store, patch, expected, actor="local-user", reset=None):
    """Apply a partial patch or reset one section under the store's writer lock."""
    if not isinstance(expected, str) or not expected or len(expected) > 128:
        _invalid("expected must be a nonempty revision string")
    _actor(actor)
    if reset is not None:
        if not isinstance(reset, str) or reset not in DEFAULT_SETTINGS:
            _invalid("reset must name a known settings section")
        if patch is not None and patch != {}:
            _invalid("reset and patch are mutually exclusive")
    else:
        _validate(patch, partial=True)
    with store.locked():
        current = _read(store)
        if expected != current["revision"]:
            raise SettingsError("settings_conflict", "Settings revision is stale; read settings again", 409)
        settings = deepcopy(current["settings"])
        if reset is not None:
            settings[reset] = deepcopy(DEFAULT_SETTINGS[reset])
        else:
            for section, values in patch.items():
                settings[section].update(deepcopy(values))
        _validate(settings)
        sections = [key for key in DEFAULT_SETTINGS if settings[key] != current["settings"][key]]
        if not sections:
            return current
        entry = {"at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                 "actor": actor, "sections": sections, "before": current["settings"], "after": settings}
        result = {"settings": settings, "revision": uuid.uuid4().hex,
                  "history": (current["history"] + [entry])[-HISTORY_LIMIT:], "configured": True}
        _write(store, result)
        return deepcopy(result)
