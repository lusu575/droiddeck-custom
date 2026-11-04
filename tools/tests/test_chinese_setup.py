import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'linuxfs/overlay/usr/local/bin/droiddeck-chinese-setup'

class ChineseSetupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        (bin_dir / 'fcitx5').write_text('#!/bin/sh\nexit 0\n')
        (bin_dir / 'fcitx5').chmod(0o755)
        self.config = self.root / 'config'
        self.env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.config), PATH=f'{bin_dir}:' + os.environ['PATH'])

    def run_setup(self): subprocess.run(['bash', str(SCRIPT)], env=self.env, check=True)

    def test_pinyin_and_non_competing_autostart_are_created(self):
        self.run_setup()
        self.assertIn('DefaultIM=pinyin', (self.config / 'fcitx5/profile').read_text())
        self.assertIn('--disable=waylandim', (self.config / 'autostart/droiddeck-fcitx5.desktop').read_text())

    def test_existing_input_preferences_are_preserved(self):
        profile = self.config / 'fcitx5/profile'
        profile.parent.mkdir(parents=True)
        profile.write_text('user preferred input')
        self.run_setup()
        self.assertEqual(profile.read_text(), 'user preferred input')

    def test_default_language_is_chinese_and_system_choice_remains(self):
        app = SCRIPT.parents[6] / 'app/src/main/java/com/droiddeck/launcher/core/AppLanguage.kt'
        text = app.read_text()
        self.assertIn('const val DEFAULT = "zh-CN"', text)
        self.assertIn('const val SYSTEM = ""', text)
        self.assertIn('getString(KEY, DEFAULT)', text)
