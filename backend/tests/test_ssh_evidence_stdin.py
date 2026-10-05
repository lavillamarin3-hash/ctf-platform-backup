"""La flag de ESC viaja por stdin, nunca por argumentos o errores SSH."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


# Prueba el adaptador sin requerir JWT/DB: get_settings se sustituye solo al
# cargar este módulo aislado y no modifica el import normal de la aplicación.
SSH_SOURCE = Path(__file__).resolve().parents[1] / "app" / "infrastructure" / "injection" / "ssh.py"
core_stub = ModuleType("app.core")
core_stub.get_settings = lambda: None
spec = importlib.util.spec_from_file_location("app.infrastructure.injection.ssh_stdin_test", SSH_SOURCE)
ssh_module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"app.core": core_stub}):
    spec.loader.exec_module(ssh_module)
ESC_EVIDENCE_PATH = ssh_module.ESC_EVIDENCE_PATH
FlagInjectionError = ssh_module.FlagInjectionError
SSHFlagInjector = ssh_module.SSHFlagInjector


class SSHEvidenceStdinTests(unittest.TestCase):
    def setUp(self):
        settings = SimpleNamespace(
            flag_injector_enabled=True,
            flag_injector_known_hosts="",
            flag_injector_strict_host_key=True,
            flag_injector_ssh_port=22,
            flag_injector_ssh_user="ctf-injector",
            flag_injector_connect_timeout=2,
            flag_injector_ssh_private_key="/test/key",
            flag_injector_ssh_password="",
            flag_injector_remote_script="/usr/local/sbin/ctf-inject-flag.sh",
            flag_injector_command_timeout=5,
        )
        with patch.object(ssh_module, "get_settings", return_value=settings):
            self.injector = SSHFlagInjector()
        self.stdin = Mock()
        self.stdout = Mock()
        self.stdout.channel.recv_exit_status.return_value = 0
        self.stderr = Mock()
        self.stderr.read.return_value = b""
        self.client = Mock()
        self.client.exec_command.return_value = (self.stdin, self.stdout, self.stderr)
        self.paramiko = SimpleNamespace(
            SSHClient=Mock(return_value=self.client),
            RejectPolicy=Mock(),
            AutoAddPolicy=Mock(),
        )

    def run_with_fake_ssh(self, path, value, *, clear=False):
        with patch.dict("sys.modules", {"paramiko": self.paramiko}):
            self.injector._run_sync("192.168.146.137", path, value, clear=clear)

    def test_esc_command_contains_no_flag_and_delivers_one_line_by_stdin(self):
        secret = "FLAG{esc_only_on_stdin_123}"
        self.run_with_fake_ssh(ESC_EVIDENCE_PATH, secret)
        command = self.client.exec_command.call_args.args[0]
        self.assertIn("--stdin", command)
        self.assertNotIn("--flag", command)
        self.assertNotIn(secret, command)
        self.stdin.write.assert_called_once_with(secret + "\n")
        self.stdin.flush.assert_called_once()
        self.stdin.channel.shutdown_write.assert_called_once()

    def test_esc_remote_failure_does_not_echo_flag_in_error(self):
        secret = "FLAG{must_not_appear_in_errors}"
        self.stdout.channel.recv_exit_status.return_value = 1
        self.stderr.read.return_value = f"remote echoed {secret}".encode()
        with self.assertRaises(FlagInjectionError) as raised:
            self.run_with_fake_ssh(ESC_EVIDENCE_PATH, secret)
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn(secret, self.client.exec_command.call_args.args[0])

    def test_esc_transport_failure_does_not_echo_flag_in_error(self):
        secret = "FLAG{transport_secret}"
        self.client.exec_command.side_effect = RuntimeError(secret)
        with self.assertRaises(FlagInjectionError) as raised:
            self.run_with_fake_ssh(ESC_EVIDENCE_PATH, secret)
        self.assertNotIn(secret, str(raised.exception))

    def test_lab01_keeps_legacy_flag_argument(self):
        self.run_with_fake_ssh("/opt/ctf/flag.txt", "FLAG{lab01_legacy}")
        command = self.client.exec_command.call_args.args[0]
        self.assertIn("--flag", command)
        self.assertIn("FLAG{lab01_legacy}", command)
        self.stdin.write.assert_not_called()

    def test_esc_rejects_multiline_before_ssh(self):
        with self.assertRaises(FlagInjectionError):
            self.injector._run_sync("192.168.146.137", ESC_EVIDENCE_PATH, "x\ny", clear=False)
        self.client.exec_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
