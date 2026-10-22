"""Compatibility launcher; the HTTP entry point belongs to the canonical plugin."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] /
        'tools/project-portal/plugins/project-hub/scripts/client_entry.py'), run_name='__main__')
