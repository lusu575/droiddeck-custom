import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'linuxfs/overlay/usr/local/bin/droiddeck-assistant'


class AssistantLauncherTest(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(SCRIPT), run_name='test_launcher')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            'XDG_DATA_HOME': str(self.root / 'user'),
            'XDG_DATA_DIRS': str(self.root / 'system'),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def entry(self, name='vendor-assistant.desktop', body=None, location='user'):
        path = self.root / location / 'applications' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body or '[Desktop Entry]\nType=Application\nName=Codex\n'
                        'Exec="/opt/Vendor App/client" --profile "中文 名称" %U\n', encoding='utf-8')
        return path

    def test_codex_keeps_user_arguments_and_approval_defaults(self):
        with patch('shutil.which', return_value='/usr/bin/codex'):
            args, env = self.module['command']('codex', ['--sandbox', 'workspace-write', '你好'])
        self.assertEqual(args, ['/usr/bin/codex', '--sandbox', 'workspace-write', '你好'])
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', args)

    def test_chatgpt_preserves_display_gpu_and_security_defaults(self):
        with patch('shutil.which', return_value='/usr/bin/chatgpt'), patch.dict(
                os.environ, WAYLAND_DISPLAY='wayland-1', XDG_SESSION_TYPE='wayland'):
            args, env = self.module['command']('chatgpt', ['--profile', '中文 名称'])
        self.assertEqual(args, ['/usr/bin/chatgpt', '--profile', '中文 名称'])
        self.assertEqual(env['WAYLAND_DISPLAY'], 'wayland-1')
        self.assertEqual(env['XDG_SESSION_TYPE'], 'wayland')

    def test_explicit_x11_and_software_are_process_scoped(self):
        with patch('shutil.which', return_value='/opt/client'), patch.dict(
                os.environ, DISPLAY=':0', WAYLAND_DISPLAY='wayland-1'):
            args, env = self.module['command']('codex-desktop', [], display='x11', graphics='software')
            self.assertEqual(os.environ['WAYLAND_DISPLAY'], 'wayland-1')
        self.assertEqual(args, ['/opt/client', '--ozone-platform=x11', '--disable-gpu'])
        self.assertNotIn('WAYLAND_DISPLAY', env)
        self.assertEqual(env['XDG_SESSION_TYPE'], 'x11')

    def test_explicit_wayland(self):
        with patch('shutil.which', return_value='/opt/client'), patch.dict(
                os.environ, WAYLAND_DISPLAY='wayland-1'):
            args, env = self.module['command']('chatgpt', [], display='wayland')
        self.assertEqual(args, ['/opt/client', '--ozone-platform=wayland'])
        self.assertEqual(env['WAYLAND_DISPLAY'], 'wayland-1')

    def test_display_must_exist_for_explicit_selection(self):
        with patch('shutil.which', return_value='/opt/client'), patch.dict(os.environ, {}, clear=True):
            for display in ('x11', 'wayland'):
                with self.assertRaises(ValueError):
                    self.module['command']('chatgpt', [], display=display)

    def test_language_fallback_respects_effective_user_locale_and_empty_override(self):
        cases = [({'LANG': 'en_US.UTF-8'}, None),
                 ({'LANG': 'zh_CN.UTF-8'}, 'zh_CN:zh'),
                 ({'LANG': 'zh_CN.UTF-8', 'LANGUAGE': ''}, ''),
                 ({'LANG': 'zh_CN.UTF-8', 'LC_MESSAGES': 'en_US.UTF-8'}, None),
                 ({'LANG': 'zh_CN.UTF-8', 'LC_ALL': 'C'}, None),
                 ({}, 'zh_CN:zh')]
        for original, expected in cases:
            with self.subTest(original=original), patch.dict(os.environ, original, clear=True), patch('shutil.which', return_value='/usr/bin/codex'):
                _, env = self.module['command']('codex', [])
            self.assertEqual(env.get('LANGUAGE'), expected)

    def test_cli_rejects_desktop_options(self):
        for options in ({'display': 'x11'}, {'graphics': 'software'}, {'desktop_file': 'x'}):
            with self.assertRaises(ValueError):
                self.module['command']('codex', [], **options)

    def test_custom_executable_path_with_spaces(self):
        with patch('shutil.which', return_value='/opt/中文 客户端/client') as which:
            args, _ = self.module['command']('codex-desktop', ['a; echo unsafe'],
                                             executable='/opt/中文 客户端/client')
        which.assert_called_once_with('/opt/中文 客户端/client')
        self.assertEqual(args, ['/opt/中文 客户端/client', 'a; echo unsafe'])

    def test_relative_executable_resolved_before_changing_workspace(self):
        with patch('shutil.which', return_value='./client'):
            args, _ = self.module['command']('codex-desktop', [], executable='./client')
        self.assertEqual(args[0], str(Path.cwd() / 'client'))

    def test_missing_client_does_not_attempt_install(self):
        with patch('shutil.which', return_value=None), patch('subprocess.call') as call:
            with self.assertRaises(ValueError):
                self.module['command']('codex', [])
        call.assert_not_called()

    def test_discovers_display_name_not_only_binary_name(self):
        path = self.entry()
        apps = self.module['desktop_apps']()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]['path'], str(path))
        self.assertIn('%U', apps[0]['exec'])

    def test_hidden_override_masks_system_entry(self):
        self.entry(location='system')
        self.entry(body='[Desktop Entry]\nType=Application\nHidden=true\nName=Codex\n')
        self.assertEqual(self.module['desktop_apps'](), [])

    def test_excludes_invalid_unrelated_and_recursive_entries(self):
        self.entry('broken.desktop', 'not a desktop file')
        self.entry('other.desktop', '[Desktop Entry]\nType=Application\nName=Other\nExec=other\n')
        self.entry('Codex.desktop', '[Desktop Entry]\nType=Application\nName=Codex\nExec=droiddeck-assistant codex-desktop\n')
        self.assertEqual(self.module['desktop_apps'](), [])

    def test_desktop_entry_uses_gio_not_shell_or_hand_parsed_exec(self):
        path = self.entry()
        with patch('shutil.which', return_value='/usr/bin/gio'):
            args, _ = self.module['command']('codex-desktop', [], desktop_file=path.name)
        self.assertEqual(args, ['/usr/bin/gio', 'launch', str(path)])
        self.assertNotIn('--no-sandbox', args)

    def test_desktop_entry_rejects_ignored_overrides(self):
        path = self.entry()
        for arguments, options in [(['--profile', 'x'], {}), ([], {'display': 'x11'}),
                                   ([], {'graphics': 'software'})]:
            with self.assertRaises(ValueError):
                self.module['command']('codex-desktop', arguments, desktop_file=str(path), **options)

    def test_unknown_desktop_entry_rejected(self):
        with self.assertRaises(ValueError):
            self.module['command']('chatgpt', [], desktop_file='/tmp/not-installed.desktop')

    def test_missing_gio_has_actionable_error(self):
        path = self.entry()
        with patch('shutil.which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'gio'):
                self.module['command']('codex-desktop', [], desktop_file=str(path))

    def test_main_preserves_unicode_arguments_workspace_and_exit_code(self):
        workspace = self.root / '中文 工作'
        workspace.mkdir()
        with patch('shutil.which', return_value='/usr/bin/codex'), patch('subprocess.call', return_value=7) as call:
            status = self.module['main'](['--workspace', str(workspace), 'codex', '--sandbox', 'workspace-write', '你好'])
        self.assertEqual(status, 7)
        self.assertEqual(call.call_args.args[0], ['/usr/bin/codex', '--sandbox', 'workspace-write', '你好'])
        self.assertEqual(call.call_args.kwargs['cwd'], str(workspace))
        self.assertEqual(call.call_args.kwargs['env']['PWD'], str(workspace))
        self.assertNotIn('shell', call.call_args.kwargs)

    def test_invalid_workspace_fails_before_launch(self):
        with patch('subprocess.call') as call, contextlib.redirect_stderr(io.StringIO()):
            status = self.module['main'](['--workspace', str(self.root / 'absent'), 'codex'])
        self.assertEqual(status, 2)
        call.assert_not_called()

    def test_desktop_path_cannot_silently_override_requested_workspace(self):
        path = self.entry(body=f'[Desktop Entry]\nType=Application\nName=Codex\nExec=client\nPath=/different\n')
        with patch('shutil.which', return_value='/usr/bin/gio'), patch('subprocess.call') as call, contextlib.redirect_stderr(io.StringIO()):
            status = self.module['main'](['--workspace', str(self.root), '--desktop-file', str(path), 'codex-desktop'])
        self.assertEqual(status, 2)
        call.assert_not_called()

    def test_os_launch_error_becomes_clear_failure(self):
        output = io.StringIO()
        with patch('shutil.which', return_value='/usr/bin/codex'), patch('subprocess.call', side_effect=OSError('bad executable')), contextlib.redirect_stderr(output):
            status = self.module['main'](['codex'])
        self.assertEqual(status, 2)
        self.assertIn('bad executable', output.getvalue())

    def test_doctor_is_read_only_and_does_not_claim_functional_support(self):
        output = io.StringIO()
        with patch('subprocess.call') as call, contextlib.redirect_stdout(output):
            status = self.module['main'](['--workspace', str(self.root), 'doctor'])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result['workspace'], str(self.root))
        self.assertEqual(result['codexSandbox'], 'not tested')
        self.assertIn('not tested', result['toolExecution'])
        self.assertIn('rg', result['programs'])
        call.assert_not_called()

    def test_graphics_diagnostics_expose_inherited_software_rendering_without_mutation(self):
        graphics = {'LIBGL_ALWAYS_SOFTWARE': '1', 'GALLIUM_DRIVER': 'llvmpipe',
                    'QT_QUICK_BACKEND': 'software', 'MESA_LOADER_DRIVER_OVERRIDE': 'test-driver',
                    'MESA_VK_WSI_DEBUG': 'sw'}
        output = io.StringIO()
        with patch.dict(os.environ, graphics), patch('shutil.which', return_value='/usr/bin/client'), contextlib.redirect_stdout(output):
            self.module['diagnose']()
            args, env = self.module['command']('chatgpt', [])
            self.assertTrue(all(os.environ[key] == value for key, value in graphics.items()))
        report = json.loads(output.getvalue())
        for key, value in graphics.items():
            self.assertEqual(report['graphicsEnvironment'][key], value)
            self.assertEqual(env[key], value)
        self.assertEqual(args, ['/usr/bin/client'])

    def test_apps_lists_json_without_running_entry(self):
        self.entry()
        output = io.StringIO()
        with patch('subprocess.call') as call, contextlib.redirect_stdout(output):
            self.assertEqual(self.module['main'](['apps']), 0)
        self.assertEqual(len(json.loads(output.getvalue())), 1)
        call.assert_not_called()

    def test_tool_checks_report_missing_failure_and_timeout(self):
        programs = {'bash': '/bin/bash', 'git': '/bin/git', 'node': '/bin/node'}
        with patch('subprocess.run', side_effect=[
                subprocess.CompletedProcess([], 0, 'droiddeck-ok', ''),
                subprocess.CompletedProcess([], 1, '', 'error'),
                subprocess.TimeoutExpired('node', 5)]) as run:
            results = self.module['check_tools'](programs, self.root)
        self.assertEqual(results['bash']['status'], 'passed')
        self.assertEqual(results['git']['status'], 'failed')
        self.assertEqual(results['node']['status'], 'timeout')
        self.assertEqual(results['python3']['status'], 'missing')
        self.assertTrue(all(call.kwargs['timeout'] == 5 for call in run.call_args_list))

    def test_tool_checks_handle_incompatible_architecture(self):
        with patch('subprocess.run', side_effect=OSError('Exec format error')):
            result = self.module['check_tools']({'node': '/opt/node'}, self.root)
        self.assertEqual(result['node']['status'], 'failed')
        self.assertIn('Exec format error', result['node']['error'])

    def test_failed_doctor_checks_return_nonzero(self):
        with patch('shutil.which', return_value=None), contextlib.redirect_stdout(io.StringIO()):
            status = self.module['main'](['--check-tools', 'doctor'])
        self.assertEqual(status, 1)

    def test_check_tools_not_accepted_for_launch(self):
        with patch('subprocess.call') as call, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.module['main'](['--check-tools', 'codex']), 2)
        call.assert_not_called()

    def test_real_launch_round_trip_keeps_arguments_and_cwd(self):
        workspace = self.root / '中文 项目'
        workspace.mkdir()
        result = subprocess.run([sys.executable, str(SCRIPT), '--workspace', str(workspace),
                                 '--executable', sys.executable, 'codex', '-c',
                                 'import os,sys,json; print(json.dumps([os.getcwd(), sys.argv[1:]]))',
                                 '中文 空格', '; echo not-a-shell', '--sandbox', 'workspace-write'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [str(workspace),
                         ['中文 空格', '; echo not-a-shell', '--sandbox', 'workspace-write']])

    def test_doctor_rejects_mistyped_arguments(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.module['main'](['doctor', '--workspace', '/tmp']), 2)


class AssistantMenuTest(unittest.TestCase):
    def setUp(self):
        self.menu = runpy.run_path(str(SCRIPT.with_name('droiddeck-assistant-menu')), run_name='test_menu')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'XDG_DATA_HOME': str(self.root),
                                      'XDG_DATA_DIRS': str(self.root / 'empty')})
        env.start()
        self.addCleanup(env.stop)

    def test_setup_creates_three_entries_and_preserves_all_existing_files(self):
        self.assertEqual(self.menu['setup'](), 0)
        entries = sorted((self.root / 'applications').glob('*.desktop'))
        self.assertEqual(len(entries), 3)
        for path in entries:
            self.assertIn('Terminal=false', path.read_text())
            self.assertIn('X-DroidDeck-Assistant=true', path.read_text())
        entries[0].write_text('user modified entry')
        self.assertEqual(self.menu['setup'](), 0)
        self.assertEqual(entries[0].read_text(), 'user modified entry')

    def test_generated_entries_are_excluded_from_discovery(self):
        self.menu['setup']()
        self.assertEqual(self.menu['LAUNCHER']['desktop_apps'](), [])

    def test_missing_client_is_visible_and_does_not_install(self):
        def which(name):
            return '/usr/bin/kdialog' if name == 'kdialog' else None
        with patch('shutil.which', side_effect=which), patch('subprocess.call', return_value=0) as call, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.menu['main'](['chatgpt']), 2)
        self.assertEqual(call.call_count, 1)
        self.assertIn('--error', call.call_args.args[0])
        self.assertIn('未找到', call.call_args.args[0][-1])

    def test_selection_cancel_does_not_launch(self):
        with patch('shutil.which', return_value='/usr/bin/fake'), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '')), patch('subprocess.call') as call:
            self.assertEqual(self.menu['main'](['codex-desktop']), 0)
        call.assert_not_called()

    def test_menu_launch_preserves_default_sandbox_and_uses_home(self):
        def which(name):
            return name if name.startswith('/') else '/usr/bin/' + name
        with patch('shutil.which', side_effect=which), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '0\n', '')), patch('subprocess.call', return_value=0) as call:
            self.assertEqual(self.menu['main'](['codex-desktop']), 0)
        self.assertEqual(call.call_args.args[0], ['/usr/bin/codex-desktop'])
        self.assertEqual(call.call_args.kwargs['cwd'], str(Path.home()))

    def test_doctor_shows_and_removes_report_file(self):
        files = []
        def display(args):
            path = Path(args[args.index('--textbox') + 1])
            self.assertIn('不代表 Codex 沙箱', path.read_text())
            files.append(path)
            return 0
        with patch.dict(self.menu['LAUNCHER'], {'diagnose': lambda *a, **kw: 0}), patch('shutil.which', return_value='/usr/bin/kdialog'), patch('subprocess.call', side_effect=display):
            self.assertEqual(self.menu['show_doctor'](), 0)
        self.assertEqual(len(files), 1)
        self.assertFalse(files[0].exists())

    def test_invalid_selection_does_not_launch_application(self):
        with patch('shutil.which', return_value='/usr/bin/fake'), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '-1\n', '')), patch('subprocess.call', return_value=0) as call, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.menu['main'](['chatgpt']), 2)
        self.assertIn('--error', call.call_args.args[0])

    def test_failed_app_launch_displays_error_without_unsafe_retry(self):
        with patch('shutil.which', return_value='/usr/bin/fake'), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, '0\n', '')), patch('subprocess.call', side_effect=[3, 0]) as call, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.menu['main'](['chatgpt']), 2)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args_list[0].args[0], ['/usr/bin/fake'])
        self.assertIn('--error', call.call_args_list[1].args[0])

    def test_doctor_falls_back_to_visible_terminal(self):
        with patch('shutil.which', side_effect=lambda name: '/usr/bin/konsole' if name == 'konsole' else None), patch('subprocess.call', return_value=0) as call:
            self.assertEqual(self.menu['show_doctor'](), 0)
        self.assertIn('--hold', call.call_args.args[0])
        self.assertEqual(call.call_args.args[0][-2:], ['--check-tools', 'doctor'])

    def test_missing_kdialog_opens_terminal_selector_without_launching_app(self):
        def which(name):
            return None if name == 'kdialog' else '/usr/bin/' + name
        with patch('shutil.which', side_effect=which), patch('subprocess.call', return_value=0) as call:
            self.assertEqual(self.menu['main'](['codex-desktop']), 0)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[0][0], '/usr/bin/konsole')
        self.assertEqual(call.call_args.args[0][-2:], ['terminal-select', 'codex-desktop'])

    def test_terminal_selector_requires_valid_explicit_choice(self):
        candidates = [('/opt/one', None, 'One'), ('/opt/two', None, 'Two')]
        with patch('builtins.input', return_value='2'), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.menu['terminal_choice'](candidates), 1)
        for answer in ('', '0', '-1', '3', 'not-a-number'):
            with self.subTest(answer=answer), patch('builtins.input', return_value=answer), contextlib.redirect_stdout(io.StringIO()):
                self.assertIsNone(self.menu['terminal_choice'](candidates))

    def test_terminal_selector_cancel_does_not_launch(self):
        with patch('shutil.which', return_value='/usr/bin/client'), patch('builtins.input', return_value=''), patch('subprocess.call') as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.menu['main'](['terminal-select', 'chatgpt']), 0)
        call.assert_not_called()

    def test_terminal_selector_confirm_launches_without_extra_flags(self):
        with patch('shutil.which', return_value='/usr/bin/client'), patch('builtins.input', return_value='1'), patch('subprocess.call', return_value=0) as call, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.menu['main'](['terminal-select', 'chatgpt']), 0)
        self.assertEqual(call.call_args.args[0], ['/usr/bin/client'])

    def test_setup_rejects_relative_xdg_directory(self):
        with patch.dict(os.environ, XDG_DATA_HOME='relative'), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.menu['main'](['setup']), 2)


if __name__ == '__main__':
    unittest.main()
