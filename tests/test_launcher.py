"""启动器复用、端口冲突和后台启动约束。"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from scripts import launch_local as launcher


class LauncherTests(unittest.TestCase):
    def test_reuses_running_service_without_spawning(self):
        with patch.object(launcher,'healthy',return_value=True), \
                patch.object(launcher.subprocess,'Popen') as start:
            self.assertEqual(launcher.ensure_service(8002),'reused')
            start.assert_not_called()

    def test_conflicting_port_is_not_replaced(self):
        with patch.object(launcher,'healthy',return_value=False), \
                patch.object(launcher,'port_in_use',return_value=True), \
                patch.object(launcher.subprocess,'Popen') as start:
            with self.assertRaisesRegex(RuntimeError,'8002'):
                launcher.ensure_service(8002)
            start.assert_not_called()

    def test_starts_only_loopback_and_records_own_pid(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(launcher,'LOGS',Path(folder)), \
                patch.object(launcher,'healthy',side_effect=[False,True]), \
                patch.object(launcher,'port_in_use',return_value=False), \
                patch.object(launcher,'find_python',return_value='python.exe'), \
                patch.object(launcher.subprocess,'Popen',return_value=Mock(pid=12345)) as start:
            self.assertEqual(launcher.ensure_service(18002),'started')
            command=start.call_args.args[0]
            self.assertEqual(command[command.index('--host')+1],'127.0.0.1')
            self.assertEqual(command[command.index('--port')+1],'18002')
            self.assertEqual(start.call_args.kwargs['creationflags'],launcher.HIDDEN)
            self.assertEqual((Path(folder)/'service-18002.pid').read_text(),'12345')

    def test_startup_failure_has_diagnostic_instead_of_opening_browser(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(launcher,'LOGS',Path(folder)), \
                patch.object(launcher,'healthy',return_value=False), \
                patch.object(launcher,'port_in_use',return_value=False), \
                patch.object(launcher,'find_python',return_value='python.exe'), \
                patch.object(launcher.subprocess,'Popen',return_value=Mock(pid=12345,poll=lambda:1)):
            with self.assertRaisesRegex(RuntimeError,'logs'):
                launcher.ensure_service(18002)
