import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'linuxfs/overlay/usr/local/bin/droiddeck-assistant'

class AssistantLauncherTest(unittest.TestCase):
    def setUp(self): self.module = runpy.run_path(str(SCRIPT), run_name='test_launcher')

    def test_codex_keeps_user_arguments_and_approval_defaults(self):
        with patch('shutil.which', return_value='/usr/bin/codex'):
            args, env = self.module['command']('codex', ['--sandbox', 'workspace-write', '你好'])
        self.assertEqual(args, ['/usr/bin/codex', '--sandbox', 'workspace-write', '你好'])
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)

    def test_chatgpt_applies_process_scoped_compatibility_flags(self):
        with patch('shutil.which', return_value='/usr/bin/chatgpt'), patch.dict(os.environ, WAYLAND_DISPLAY='wayland-1'):
            args, env = self.module['command']('chatgpt', ['--profile', '中文 名称'])
        self.assertEqual(args[-2:], ['--profile', '中文 名称'])
        self.assertIn('--no-sandbox', args)
        self.assertNotIn('WAYLAND_DISPLAY', env)

    def test_missing_client_does_not_attempt_install(self):
        with patch('shutil.which', return_value=None):
            with self.assertRaises(ValueError): self.module['command']('codex', [])
