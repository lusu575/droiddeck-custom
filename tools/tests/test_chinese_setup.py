import os
import pty
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
        self.bin_dir = bin_dir
        self.config = self.root / 'config'
        self.env = dict(os.environ, HOME=str(self.root), XDG_CONFIG_HOME=str(self.config), XDG_DATA_HOME=str(self.root / "data"), PATH=f'{bin_dir}:' + os.environ['PATH'])

    def run_setup(self, *args):
        return subprocess.run(['bash', str(SCRIPT), *args], env=self.env, check=True, capture_output=True, text=True)

    def stub(self, name, body):
        path = self.bin_dir / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)

    def locale_stub(self):
        self.stub('kwriteconfig6', 'printf "%s\\n" "$*" >> "$HOME/locale-calls"')
        self.env.update(LANG='zh_CN.UTF-8', LANGUAGE='zh_CN:zh')

    def test_disabled_autostart_is_preserved(self):
        entry = self.config / 'autostart/droiddeck-fcitx5.desktop'
        entry.parent.mkdir(parents=True)
        entry.write_text('[Desktop Entry]\nHidden=true\n')
        self.run_setup()
        self.assertIn('Hidden=true', entry.read_text())

    def test_session_only_syncs_a_changed_app_language(self):
        self.locale_stub()
        self.run_setup('--session')
        calls = self.root / 'locale-calls'
        self.assertIn('zh_CN.UTF-8', calls.read_text())
        before = calls.read_text()
        self.run_setup('--session')
        self.assertEqual(before, calls.read_text())
        self.env.update(LANG='de_DE.UTF-8', LANGUAGE='de_DE:de')
        self.run_setup('--session')
        self.assertIn('de_DE.UTF-8', calls.read_text())

    def test_preexisting_kde_language_is_preserved_on_migration(self):
        self.locale_stub()
        self.config.mkdir()
        (self.config / 'plasma-localerc').write_text('[Formats]\nLANG=fr_FR.UTF-8\n')
        self.run_setup('--session')
        self.assertFalse((self.root / 'locale-calls').exists())

    def test_matching_distribution_language_defaults_are_not_user_choices(self):
        self.locale_stub()
        self.config.mkdir()
        stock = self.root / 'stock-localerc'
        stock.write_text('[Formats]\nLANG=en_US.UTF-8\n')
        (self.config / 'plasma-localerc').write_text(stock.read_text())
        script = self.root / 'setup'
        script.write_text(SCRIPT.read_text().replace('/etc/skel/.config/plasma-localerc', str(stock)))
        subprocess.run(['bash', str(script), '--session'], env=self.env, check=True)
        self.assertIn('zh_CN.UTF-8', (self.root / 'locale-calls').read_text())

    def test_stock_input_profile_is_initialized_only_once(self):
        profile = self.config / 'fcitx5/profile'
        profile.parent.mkdir(parents=True)
        stock = self.root / 'stock-profile'
        stock.write_text('DefaultIM=keyboard-us\n')
        profile.write_text(stock.read_text())
        script = self.root / 'setup'
        script.write_text(SCRIPT.read_text().replace('/etc/skel/.config/fcitx5/profile', str(stock)))
        subprocess.run(['bash', str(script)], env=self.env, check=True)
        self.assertIn('DefaultIM=pinyin', profile.read_text())
        profile.write_text(stock.read_text())
        subprocess.run(['bash', str(script)], env=self.env, check=True)
        self.assertEqual(stock.read_text(), profile.read_text())

    def test_explicit_app_language_action_restores_saved_choice(self):
        self.locale_stub()
        self.run_setup('--session')
        self.env.update(LANG='en_US.UTF-8', LANGUAGE='en_US')
        self.run_setup('--use-app-language')
        calls = (self.root / 'locale-calls').read_text()
        self.assertEqual(2, calls.count('--key LANG zh_CN.UTF-8'))
        self.assertNotIn('en_US', calls)

    def test_startup_never_calls_package_manager(self):
        for name in ('apt-get', 'pacman'):
            self.stub(name, 'touch "$HOME/unexpected-install"; exit 99')
        self.run_setup('--session')
        self.assertFalse((self.root / 'unexpected-install').exists())
        entry = self.root / 'data/applications/droiddeck-chinese-support.desktop'
        self.assertIn('--interactive', entry.read_text())

    def test_install_requires_interactive_terminal(self):
        self.stub('apt-get', 'touch "$HOME/unexpected-install"; exit 99')
        result = subprocess.run(['bash', str(SCRIPT), '--interactive'], env=self.env,
                                input='INSTALL\n', capture_output=True, text=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('non-interactive installation is disabled', result.stdout)
        self.assertFalse((self.root / 'unexpected-install').exists())

    def interactive_setup(self, answer):
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(['bash', str(SCRIPT), '--interactive'],
                                       env=self.env, stdin=slave, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
            os.write(master, (answer + '\n').encode())
            out, err = process.communicate(timeout=10)
            return process.returncode, out, err
        finally:
            os.close(master)
            os.close(slave)

    def test_interactive_cancellation_never_installs(self):
        self.stub('apt-get', 'touch "$HOME/unexpected-install"; exit 99')
        code, out, _ = self.interactive_setup('cancel')
        self.assertEqual(0, code)
        self.assertIn('Cancelled', out)
        self.assertFalse((self.root / 'unexpected-install').exists())

    def test_confirmed_install_stops_on_repository_failure(self):
        self.stub('id', 'echo 0')
        self.stub('apt-get', 'printf "%s\\n" "$*" >> "$HOME/package-calls"; exit 7')
        code, out, _ = self.interactive_setup('INSTALL')
        self.assertNotEqual(0, code)
        self.assertEqual('update\n', (self.root / 'package-calls').read_text())
        self.assertNotIn('请退出并重新进入桌面', out)

    def test_install_only_requests_translation_packages_with_candidates(self):
        self.stub('id', 'echo 0')
        self.stub('apt-get', 'printf "%s\\n" "$*" >> "$HOME/package-calls"; [ "$1" = update ]')
        self.stub('apt-cache', 'case "$2" in language-pack-zh-hans|fcitx5-frontend-qt6|firefox-esr-l10n-zh-cn) echo "  Candidate: 1.0";; *) echo "  Candidate: (none)";; esac')
        self.stub('dpkg-query', 'echo "install ok installed"')
        code, _, _ = self.interactive_setup('INSTALL')
        self.assertNotEqual(0, code)
        calls = (self.root / 'package-calls').read_text()
        self.assertIn('language-pack-zh-hans', calls)
        self.assertIn('firefox-esr-l10n-zh-cn', calls)
        self.assertNotIn('language-pack-kde', calls)
        self.assertNotIn('kde-l10n-zhcn', calls)
        self.assertNotIn('libreoffice-l10n', calls)

    def test_debian_install_does_not_require_ubuntu_translation_packages(self):
        self.stub('id', 'echo 0')
        self.stub('apt-get', 'printf "%s\\n" "$*" >> "$HOME/package-calls"; [ "$1" = update ]')
        self.stub('apt-cache', 'echo "  Candidate: (none)"')
        self.stub('dpkg-query', 'exit 1')
        self.interactive_setup('INSTALL')
        calls = (self.root / 'package-calls').read_text()
        self.assertIn('install locales fonts-noto-cjk', calls)
        self.assertNotIn('language-pack', calls)

    def test_check_does_not_write_configuration(self):
        self.stub('fc-list', 'echo "Noto Sans CJK SC"')
        result = subprocess.run(['bash', str(SCRIPT), '--check'], env=self.env,
                                capture_output=True, text=True)
        self.assertIn('Noto Sans CJK SC', result.stdout)
        self.assertFalse(self.config.exists())


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
