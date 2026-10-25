"""Durable, installation-wide setup wizard progress."""
import json
import re
import sqlite3
import time


STATE_LIMIT = 64 * 1024
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REQUEST_ID = re.compile(r"^[0-9a-fA-F]{32}$")
STEPS = {"welcome", "app", "invite", "verify", "chatgpt", "api", "api-key", "control", "projects", "finish"}
APPLICATIONS = {"codex", "other"}
PROVIDERS = {"responses", "anthropic", "gemini", "chat"}
NETWORK_MODES = {"direct", "system"}
PATCH_FIELDS = {
    "step", "application", "completed", "invitationId", "connectionId", "projectId", "accountId",
    "providerId", "authAttemptId", "probeRequestId", "standalone", "manualProject", "additional",
    "model", "manualProjectName", "manualProjectRoot", "providerKind", "networkMode",
}
IDENTIFIER_FIELDS = {"invitationId", "connectionId", "projectId", "accountId", "providerId", "authAttemptId", "probeRequestId"}
BOOLEAN_FIELDS = {"completed", "standalone", "manualProject", "additional"}
STRING_FIELDS = {"model", "manualProjectName"}


class SetupWizardError(ValueError):
    def __init__(self, message, status=400, code="invalid_request"):
        super().__init__(message)
        self.status, self.code = status, code


def _path(registry):
    return registry.home / "setup-wizard.json"


def _lock(registry):
    from project_portal import Store
    return Store.lock_probe(registry.home / "setup-wizard.lock")


def _default():
    return {"schemaVersion": 1, "revision": 0, "progress": {
        "started": False, "completed": False, "step": "welcome", "application": "codex"
    }}


def _read(path):
    if path.is_symlink():
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_unavailable")
    if not path.exists():
        return _default()
    if not path.is_file():
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_unavailable")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_unavailable") from error
    if len(raw) > STATE_LIMIT:
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError) as error:
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt") from error
    if not isinstance(value, dict) or set(value) - {"schemaVersion", "revision", "progress", "claimRequestId"} \
            or value.get("schemaVersion") != 1 or type(value.get("revision")) is not int \
            or value["revision"] < 0 or not isinstance(value.get("progress"), dict):
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt")
    if "claimRequestId" in value and (not isinstance(value["claimRequestId"], str) or
                                      not REQUEST_ID.fullmatch(value["claimRequestId"])):
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt")
    progress = value["progress"]
    if not {"started", "completed", "step", "application"} <= set(progress):
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt")
    if set(progress) - ({"started", "completed"} | PATCH_FIELDS) or \
            type(progress.get("started", False)) is not bool or type(progress.get("completed", False)) is not bool:
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt")
    try:
        _validate_patch({key: value for key, value in progress.items() if key not in {"started", "completed"}})
    except SetupWizardError as error:
        raise SetupWizardError("Setup wizard state is unavailable", 500, "state_corrupt") from error
    return value


def _validate_patch(patch):
    if not isinstance(patch, dict) or set(patch) - PATCH_FIELDS:
        raise SetupWizardError("Use only supported setup wizard fields")
    for key in IDENTIFIER_FIELDS:
        if key in patch and (not isinstance(patch[key], str) or
                             (patch[key] != "" and not IDENTIFIER.fullmatch(patch[key]))):
            raise SetupWizardError("Invalid setup wizard identifier")
    for key in BOOLEAN_FIELDS:
        if key in patch and type(patch[key]) is not bool:
            raise SetupWizardError("Setup wizard flags must be boolean")
    if "step" in patch and (not isinstance(patch["step"], str) or patch["step"] not in STEPS):
        raise SetupWizardError("Invalid setup wizard step")
    if "application" in patch and (not isinstance(patch["application"], str) or patch["application"] not in APPLICATIONS):
        raise SetupWizardError("Invalid setup wizard application")
    if "providerKind" in patch and (not isinstance(patch["providerKind"], str) or patch["providerKind"] not in PROVIDERS):
        raise SetupWizardError("Invalid setup wizard provider")
    if "networkMode" in patch and (not isinstance(patch["networkMode"], str) or patch["networkMode"] not in NETWORK_MODES):
        raise SetupWizardError("Invalid setup wizard network mode")
    for key in STRING_FIELDS:
        if key in patch and (not isinstance(patch[key], str) or len(patch[key]) > 160 or "\x00" in patch[key]):
            raise SetupWizardError("Invalid setup wizard text")
    if "manualProjectRoot" in patch and (not isinstance(patch["manualProjectRoot"], str) or
                                        len(patch["manualProjectRoot"]) > 4096 or "\x00" in patch["manualProjectRoot"]):
        raise SetupWizardError("Invalid setup wizard folder")


def _invitation(registry, invitation_id):
    if not invitation_id:
        return None
    try:
        with registry.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "agent_invitations" not in tables:
                return {"id": invitation_id, "state": "missing", "connectionId": None}
            row = db.execute("SELECT id,expires,revoked,response FROM agent_invitations WHERE id=?", (invitation_id,)).fetchone()
    except (sqlite3.Error, OSError):
        return {"id": invitation_id, "state": "missing", "connectionId": None}
    if row is None:
        return {"id": invitation_id, "state": "missing", "connectionId": None}
    if row[2]:
        state = "revoked"
    elif row[3] is not None:
        state = "used"
    elif row[1] < time.time():
        state = "expired"
    else:
        state = "pending"
    binding = None
    if row[3] is not None:
        try:
            response = json.loads(row[3])
            candidate = response.get("binding") if isinstance(response, dict) else None
            binding = candidate if isinstance(candidate, str) and IDENTIFIER.fullmatch(candidate) else None
        except (ValueError, TypeError):
            binding = None
    return {"id": invitation_id, "state": state, "connectionId": binding}


def _project(registry, state):
    progress = dict(state["progress"])
    invitation = _invitation(registry, progress.get("invitationId"))
    return {"schemaVersion": 1, "revision": state["revision"], "progress": progress,
            "autoEligible": not progress.get("started", False), "invitation": invitation}


def read(registry):
    with _lock(registry).locked():
        return _project(registry, _read(_path(registry)))


def change(registry, body):
    if not isinstance(body, dict) or set(body) - {"action", "expected", "requestId", "patch"}:
        raise SetupWizardError("Use action, expected, requestId and optional patch")
    if not isinstance(body.get("action"), str) or body["action"] not in {"claim", "save"} or type(body.get("expected")) is not int \
            or not isinstance(body.get("requestId"), str) or not REQUEST_ID.fullmatch(body["requestId"]):
        raise SetupWizardError("Use a valid action, revision and 32-character requestId")
    if body["action"] == "claim" and set(body) != {"action", "expected", "requestId"}:
        raise SetupWizardError("Claim does not accept a patch")
    if body["action"] == "save" and set(body) != {"action", "expected", "requestId", "patch"}:
        raise SetupWizardError("Save requires patch")
    patch = body.get("patch", {})
    if body["action"] == "save":
        _validate_patch(patch)
    from task_transfer import barrier
    with barrier(registry), _lock(registry).locked():
        path = _path(registry)
        state = _read(path)
        if body["action"] == "claim" and state.get("claimRequestId") == body["requestId"]:
            result = _project(registry, state)
            result["claimed"] = True
            return result
        if body["expected"] != state["revision"]:
            raise SetupWizardError("Setup wizard progress changed", 409, "revision_conflict")
        if body["action"] == "claim":
            claimed = False
            if not state["progress"].get("started", False):
                state["progress"]["started"] = True
                state["revision"] += 1
                state["claimRequestId"] = body["requestId"]
                claimed = True
                _write(path, state)
            result = _project(registry, state)
            result["claimed"] = claimed
            return result
        state["progress"].update(patch)
        state["progress"]["started"] = True
        state["revision"] += 1
        _write(path, state)
        return _project(registry, state)


def _write(path, value):
    from project_portal import atomic_write
    atomic_write(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")))
