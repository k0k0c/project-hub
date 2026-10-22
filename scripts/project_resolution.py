"""Shared, read-only project selection for session discovery and server execution.

Explicit Codex assignment is authoritative. Paths and Git worktrees are fallbacks
only when no assignment exists. Selection never moves tasks, sessions or claims.
"""
from pathlib import Path
import sys

PLUGIN = Path(__file__).resolve().parents[1]/'tools/project-portal/plugins/project-hub/scripts'
if str(PLUGIN) not in sys.path: sys.path.insert(0,str(PLUGIN))
from hub_core import HubError, resolve_project


def assignment_for(metadata, session):
    if not metadata['available']:
        raise HubError('project_metadata_unavailable','Codex project metadata unavailable; refusing cwd fallback')
    row=metadata.get('assignments',{}).get(session)
    if row is None:return None
    if row['projectKind']!='local':
        raise HubError('project_unregistered','Assigned project is not a local Codex project; refusing cwd fallback')
    return row['projectId']
