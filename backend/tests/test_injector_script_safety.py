"""Comprobaciones no destructivas de los scripts Linux del laboratorio."""

from pathlib import Path
import os
import shutil
import subprocess
import unittest


SCRIPT_DIR = (Path(__file__).resolve().parents[1] / "app" / "infrastructure" /
              "injection" / "scripts" / "linux")
INJECTOR = SCRIPT_DIR / "ctf-inject-flag.sh"
INSTALLER = SCRIPT_DIR / "install-ctf-evidence-service.sh"


def find_bash() -> str | None:
    if os.name == "nt":
        git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
        if git_bash.is_file():
            return str(git_bash)
    return shutil.which("bash")


BASH = find_bash()


@unittest.skipUnless(BASH, "Bash no disponible")
class InjectorScriptSafetyTests(unittest.TestCase):
    def test_scripts_have_valid_bash_syntax(self):
        for script in (INJECTOR, INSTALLER):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [BASH, "-n", str(script)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsafe_paths_are_rejected_before_any_file_operation(self):
        unsafe_paths = (
            "",
            "/etc/passwd",
            "/opt/ctf/../outside.txt",
            "/opt/ctf/dir/../../outside.txt",
            "/opt/ctf//flag.txt",
            "/opt/ctf/./flag.txt",
            "/opt/ctf/flag.txt/",
            "/opt/ctf/flag\nname.txt",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                result = subprocess.run(
                    [BASH, str(INJECTOR), "--path", unsafe_path, "--clear"],
                    capture_output=True, text=True, check=False,
                )
                if os.name == "nt" and "\n" in unsafe_path:
                    # CreateProcess/MSYS puede dividir un argumento con salto
                    # de línea antes de que Bash reciba la ruta original.
                    self.assertIn(result.returncode, (2, 3), result.stderr)
                else:
                    self.assertEqual(result.returncode, 3, result.stderr)
                    self.assertIn("Ruta no permitida", result.stderr)

    def test_esc_rejects_flag_on_command_line(self):
        secret = "FLAG{must_not_be_in_argv}"
        result = subprocess.run(
            [BASH, str(INJECTOR), "--path", "/opt/ctf/ESC-01-RECON/flag.txt",
             "--flag", secret],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("requiere stdin", result.stderr)
        self.assertNotIn(secret, result.stderr)


if __name__ == "__main__":
    unittest.main()
