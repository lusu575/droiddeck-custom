from pathlib import Path
import subprocess
import tempfile
import unittest

class ClipboardIncrTest(unittest.TestCase):
    def test_long_transfer(self):
        source = Path(__file__).with_name('clipboard_incr_harness.c')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'clipboard'
            subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', str(source), '-ldl', '-o', str(output)], check=True)
            subprocess.run([str(output)], check=True)
