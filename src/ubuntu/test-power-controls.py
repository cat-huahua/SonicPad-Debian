#!/usr/bin/env python3
"""Check power commands and mount cleanup without controlling hardware."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('menu', BASE / 'sonicpad-menu.py')
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class PowerControls(unittest.TestCase):
    def test_orderly_shutdown_and_restart(self):
        for action, command in [('shutdown', 'poweroff'), ('reboot', 'reboot')]:
            runner = Mock()
            menu.request_power(action, runner)
            runner.assert_called_once_with(['systemctl', command], check=True)

    def test_unsupported_action_does_not_run_a_command(self):
        runner = Mock()
        with self.assertRaises(ValueError):
            menu.request_power('force', runner)
        runner.assert_not_called()

    def test_shutdown_remains_available_after_startup(self):
        for width, height in [(1024, 600), (800, 480)]:
            for screen in ('startup', 'runtime', 'info'):
                _, buttons = menu.render(width, height, 10, settings=screen == 'info', runtime=screen == 'runtime')
                self.assertIn('shutdown', [action for _, action in buttons])
                for (x0, y0, x1, y1), _ in buttons:
                    self.assertTrue(0 <= x0 < x1 <= width)
                    self.assertTrue(0 <= y0 < y1 <= height)

    def test_failed_unmount_never_removes_mounted_root(self):
        template = (BASE / 'usb-power-patch.sh.in').read_text()
        cleanup = template[template.index('cleanup() {'):template.index('\ntrap cleanup EXIT')]
        # All external commands are stubs. This test performs no real mount,
        # deletion, or boot environment operation.
        harness = '''set -eu
temporary=/nonexistent-test-mount
mounted=1
sync() { :; }
umount() { return 1; }
rm() { echo UNSAFE_DELETE; }
fw_setenv() { :; }
''' + cleanup + '\ncleanup\n'
        result = subprocess.run(['sh', '-c', harness], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('UNSAFE_DELETE', result.stdout)
        self.assertIn('leaving it in place', result.stderr)


if __name__ == '__main__':
    unittest.main()
