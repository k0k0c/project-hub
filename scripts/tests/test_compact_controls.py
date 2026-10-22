"""Guard the shared control contract and the reported responsive regressions."""
from pathlib import Path
import re
import unittest


WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'


class CompactControlsTest(unittest.TestCase):
    def test_one_shared_height_and_wrapping_stage_actions(self):
        css = (WEB / 'style.css').read_text(encoding='utf-8')
        self.assertIn('--control-height: 25px;', css)
        button = re.search(r'\nbutton \{([^}]+)\}', css).group(1)
        self.assertIn('height: var(--control-height)', button)
        self.assertIn('font-size: var(--control-font-size)', button)
        for selector, body in re.findall(r'([^{}]+)\{([^{}]*)\}', css):
            if selector.strip() == '.stage-detail-actions':
                self.assertNotIn('nowrap', body)
            if selector.strip() == '.task-status-pair':
                self.assertNotIn('nowrap', body)
        viewer = (WEB / 'viewer.css').read_text(encoding='utf-8')
        self.assertNotRegex(viewer, r'\.artifact-viewer button[^{}]*\{[^{}]*(?:height|padding):')

    def test_title_fills_column_instead_of_fixed_text_width(self):
        css = (WEB / 'task-table.css').read_text(encoding='utf-8')
        rule = re.search(r'\.task-table-title a \{([^}]+)\}', css).group(1)
        self.assertIn('flex:1', rule)
        self.assertIn('min-width:0', rule)
        self.assertNotRegex(rule, r'(?:max-)?width:\s*\d+px')
        self.assertIn('[data-task-cell="title"]', css)

    def test_icon_actions_have_names_and_tooltips(self):
        for name in ('app.js', 'task-editor.js', 'task-table.js', 'viewer.js'):
            source = (WEB / name).read_text(encoding='utf-8')
            for attributes in re.findall(r'<(?:button|summary)\s+([^>]+)>', source):
                if 'icon-button' not in attributes:
                    continue
                self.assertIn('aria-label=', attributes, (name, attributes))
                self.assertIn('title=', attributes, (name, attributes))
        index = (WEB / 'index.html').read_text(encoding='utf-8')
        self.assertLess(index.index('/vendor/lucide.js'), index.index('/app.js'))
        self.assertTrue((WEB / 'vendor/lucide.LICENSE').is_file())
