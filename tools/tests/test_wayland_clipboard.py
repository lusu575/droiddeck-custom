from pathlib import Path
import subprocess
import tempfile
import unittest


class WaylandClipboardTest(unittest.TestCase):
    def test_utf8_and_inclusive_size_limit(self):
        root = Path(__file__).resolve().parents[2]
        native = root / 'app/src/main/cpp/waylandcomp'
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'clipboard'
            subprocess.run([
                'cc', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                '-ffunction-sections', '-fdata-sections', '-Wl,--gc-sections',
                '-I' + str(native / 'prebuilt/include'), '-I' + str(native / 'generated'),
                str(Path(__file__).with_name('wayland_clipboard_harness.c')), '-o', str(binary),
            ], check=True)
            subprocess.run([str(binary)], check=True)
