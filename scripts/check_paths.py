"""External paths for repository validation receipts and logs."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


def output_home(root):
    root = Path(root).resolve()
    if os.name == 'nt':
        default = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'ProjectHub' / 'checks'
    else:
        default = Path.home() / '.local/share/ProjectHub/checks'
    base = Path(os.environ.get('PROJECT_HUB_CHECK_OUTPUT_HOME', default)).expanduser().resolve()
    if root == base or root.is_relative_to(base) or base.is_relative_to(root):
        raise ValueError('Check output home must be outside the project root')
    namespace = hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()[:16]
    output = base / namespace
    output.mkdir(parents=True, exist_ok=True)
    return output
