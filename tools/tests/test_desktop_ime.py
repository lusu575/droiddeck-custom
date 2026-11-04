import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import runpy

IME = Path(__file__).resolve().parents[1] / 'linuxfs/overlay/usr/local/bin/droiddeck-ime'


def message(obj, opcode, payload=b''):
    return struct.pack('<II', obj, ((8 + len(payload)) << 16) | opcode) + payload


def wl_string(value):
    data = value.encode() + b'\0'
    return struct.pack('<I', len(data)) + data + b'\0' * (-len(data) % 4)


class DesktopImeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Path(self.temp.name)
        self.server, client = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(self.server.close)
        env = dict(os.environ, BL_LAUNCH_DIR=str(self.session), WAYLAND_SOCKET=str(client.fileno()))
        self.proc = subprocess.Popen(['python3', str(IME)], env=env, pass_fds=[client.fileno()],
                                     stderr=subprocess.PIPE, text=True)
        client.close()
        self.addCleanup(self.stop)
        self.server.settimeout(5)
        self.assertEqual(self.read(12), message(1, 1, struct.pack('<I', 2)))
        self.server.sendall(message(2, 0, struct.pack('<I', 7) + wl_string('zwp_input_method_v1') + struct.pack('<I', 1)))
        bind = self.read(8 + 4 + len(wl_string('zwp_input_method_v1')) + 8)
        self.assertEqual(bind, message(2, 0, struct.pack('<I', 7) + wl_string('zwp_input_method_v1') + struct.pack('<II', 1, 3)))

    def stop(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(5)
        self.proc.stderr.close()

    def read(self, size):
        data = b''
        while len(data) < size:
            chunk = self.server.recv(size - len(data))
            if not chunk:
                break
            data += chunk
        return data

    def state(self, seq, timeout=5):
        path = self.session / 'agent/ime.json'
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                snapshot = json.loads(path.read_text())
            except (OSError, ValueError):
                snapshot = None
            if snapshot and snapshot['seq'] >= seq:
                return snapshot
            time.sleep(0.02)
        self.fail('ime.json never reached seq %d' % seq)

    def test_focus_and_blur_are_reported(self):
        self.server.sendall(message(3, 0, struct.pack('<I', 100)))
        self.assertTrue(self.state(1)['textField'])
        self.server.sendall(message(100, 2, struct.pack('<II', 0, 9)))
        snapshot = self.state(2)
        self.assertEqual((snapshot['textField'], snapshot['purpose']), (True, 9))
        self.server.sendall(message(3, 1, struct.pack('<I', 100)))
        self.assertEqual(self.read(8), message(100, 0))
        self.assertFalse(self.state(3)['textField'])
        self.assertEqual(oct((self.session / 'agent/ime.json').stat().st_mode & 0o777), '0o600')

    def test_switching_fields_does_not_flicker(self):
        self.server.sendall(message(3, 0, struct.pack('<I', 100)))
        self.assertTrue(self.state(1)['textField'])
        self.server.sendall(message(3, 1, struct.pack('<I', 100)) + message(3, 0, struct.pack('<I', 101)))
        self.assertEqual(self.read(8), message(100, 0))
        time.sleep(0.4)
        self.assertTrue(self.state(1)['textField'])

    def test_compositor_exit_clears_the_field(self):
        self.server.sendall(message(3, 0, struct.pack('<I', 100)))
        self.assertTrue(self.state(1)['textField'])
        self.server.close()
        self.assertEqual(self.proc.wait(5), 0)
        self.assertFalse(self.state(2)['textField'])


    def test_a_protocol_error_clears_the_field(self):
        self.server.sendall(message(3, 0, struct.pack('<I', 100)))
        self.assertTrue(self.state(1)['textField'])
        self.server.sendall(message(1, 0, struct.pack('<II', 3, 1) + wl_string('bad request')))
        self.assertEqual(self.proc.wait(5), 1)
        self.assertFalse(self.state(2)['textField'])



class ImeUnicodeBridgeTest(unittest.TestCase):
    def setUp(self):
        self.scope = runpy.run_path(str(IME), run_name="droiddeck_ime_test")

    def deliver(self, commands, current=100, token="focused", directory=""):
        class Receiver:
            def recv(self, size):
                if not commands:
                    raise BlockingIOError()
                return commands.pop(0)
        class Connection:
            def __init__(self): self.sent = []
            def send(self, *args): self.sent.append(args)
        bridge = self.scope["InputBridge"]("")
        bridge.sock = Receiver()
        bridge.directory = directory
        conn = Connection()
        bridge.receive(conn, current, 42, token)
        return conn.sent

    def command(self, operation, text, token="focused"):
        return json.dumps(dict(operation=operation, text=text, token=token)).encode()

    def test_chinese_commit_preserves_unicode_and_serial(self):
        text = "中文测试，𠮷😊\n第二行"
        sent = self.deliver([self.command("commit", text)])
        self.assertEqual(sent[-1], (100, 1, struct.pack("<I", 42) + wl_string(text)))
        self.assertEqual(sent[0][1], 2)

    def test_preedit_reports_utf8_cursor_offset(self):
        sent = self.deliver([self.command("preedit", "拼音")])
        self.assertEqual(sent[0], (100, 4, struct.pack("<i", 6)))
        self.assertEqual(sent[1][1], 2)

    def test_stale_field_and_malformed_or_oversized_input_are_rejected(self):
        commands = [self.command("commit", "旧字段", "old"), b"bad json", b"[]",
                    self.command("commit", "中" * 350000), self.command("commit", "a\0b")]
        self.assertEqual(self.deliver(commands), [])
        self.assertEqual(self.deliver([self.command("commit", "中文")], current=None), [])

    def test_long_chinese_is_split_without_losing_characters(self):
        text = "中文𠮷😊\n" * 4000
        sent = self.deliver([self.command("commit", text)])
        commits = [payload[4:] for _, operation, payload in sent if operation == 1]
        rebuilt = ""
        for payload in commits:
            size = struct.unpack_from("<I", payload)[0]
            rebuilt += payload[4:4 + size - 1].decode()
        self.assertEqual(rebuilt, text)

    def test_large_preedit_is_one_preview_not_replacing_chunks(self):
        sent = self.deliver([self.command("preedit", "中" * 1000)])
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[1][1], 2)

    def test_file_commit_is_read_once_and_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("input-" + "a" * 32 + ".json")
            path.write_text("长文测试𠮷😊" * 1000)
            command = json.dumps(dict(operation="commit", token="focused", file=path.name)).encode()
            sent = self.deliver([command], directory=directory)
            self.assertFalse(path.exists())
            self.assertGreater(len(sent), 2)

    def test_stale_file_input_is_discarded_and_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("input-" + "a" * 32 + ".json")
            path.write_text("old field input")
            command = json.dumps(dict(operation="commit", token="old", file=path.name)).encode()
            self.assertEqual(self.deliver([command], directory=directory), [])
            self.assertFalse(path.exists())

    def test_cancel_preedit_clears_without_committing(self):
        sent = self.deliver([self.command("preedit", "")])
        self.assertEqual(sent, [(100, 4, struct.pack("<i", 0)),
                                (100, 2, struct.pack("<I", 42) + wl_string("") + wl_string(""))])

    def test_file_at_byte_limit_preserves_all_unicode(self):
        text = "😊" * (1024 * 1024 // 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("input-" + "b" * 32 + ".json")
            path.write_text(text)
            command = json.dumps(dict(operation="commit", token="focused", file=path.name)).encode()
            sent = self.deliver([command], directory=directory)
            rebuilt = "".join(self.scope["read_string"](payload, 4)[0]
                              for _, opcode, payload in sent if opcode == 1)
            self.assertEqual(rebuilt, text)
            self.assertFalse(path.exists())

    def test_oversized_file_is_removed_without_committing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("input-" + "c" * 32 + ".json")
            path.write_bytes(b"x" * (1024 * 1024 + 1))
            command = json.dumps(dict(operation="commit", token="focused", file=path.name)).encode()
            self.assertEqual(self.deliver([command], directory=directory), [])
            self.assertFalse(path.exists())

    def test_symlink_and_hardlink_do_not_expose_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "private.txt"
            target.write_text("not input")
            path = Path(directory) / ("input-" + "d" * 32 + ".json")
            command = json.dumps(dict(operation="commit", token="focused", file=path.name)).encode()
            for link in (lambda: path.symlink_to(target), lambda: os.link(target, path)):
                link()
                self.assertEqual(self.deliver([command], directory=directory), [])
                self.assertFalse(path.exists())
                self.assertEqual(target.read_text(), "not input")

    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("input-" + "e" * 32 + ".json")
            os.mkfifo(path)
            command = json.dumps(dict(operation="commit", token="focused", file=path.name)).encode()
            self.assertEqual(self.deliver([command], directory=directory), [])
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
