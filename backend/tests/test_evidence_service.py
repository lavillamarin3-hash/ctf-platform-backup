"""Pruebas locales del servicio didáctico; no toca VMs ni flags reales."""

from http.server import ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen


SERVICE = (Path(__file__).resolve().parents[1] / "app" / "infrastructure" /
           "injection" / "scripts" / "linux" / "ctf-evidence-service.py")
spec = importlib.util.spec_from_file_location("ctf_evidence_service", SERVICE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceServiceTests(unittest.TestCase):
    def test_default_path_is_separate_from_lab01(self):
        self.assertEqual(module.EvidenceHandler.flag_path, Path("/opt/ctf/ESC-01-RECON/flag.txt"))
        self.assertNotEqual(module.EvidenceHandler.flag_path, Path("/opt/ctf/flag.txt"))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        flag_path = Path(self.temp.name) / "flag.txt"

        class TestHandler(module.EvidenceHandler):
            allowed_client_ip = "127.0.0.1"

        TestHandler.flag_path = flag_path
        self.handler = TestHandler
        self.flag_path = flag_path
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), TestHandler)
        self.server.daemon_threads = True
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop_server)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(timeout=2)

    def request(self, path):
        try:
            with urlopen(self.base_url + path, timeout=2) as response:
                return response.status, response.read(), response.headers
        except HTTPError as error:
            return error.code, error.read(), error.headers

    def test_serves_only_injected_file_and_returns_404_after_cleanup(self):
        status, _, _ = self.request("/evidence")
        self.assertEqual(status, 404)
        self.flag_path.write_bytes(b"FLAG{esc-01_fixture_run_abcdef}\n")
        status, content, headers = self.request("/evidence")
        self.assertEqual(status, 200)
        self.assertEqual(content, b"FLAG{esc-01_fixture_run_abcdef}\n")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("/evidencia")[1], content)
        self.flag_path.unlink()
        status, content, _ = self.request("/evidence")
        self.assertEqual(status, 404)
        self.assertNotIn(b"FLAG{", content)

    def test_only_documented_routes_and_source_are_allowed(self):
        self.flag_path.write_bytes(b"FLAG{fixture}\n")
        self.assertEqual(self.request("/")[0], 200)
        self.assertEqual(self.request("/flag.txt")[0], 404)
        self.assertEqual(self.request("/../flag.txt")[0], 404)
        self.handler.allowed_client_ip = "192.168.146.134"
        status, content, _ = self.request("/evidence")
        self.assertEqual(status, 403)
        self.assertNotIn(b"FLAG{", content)

    def test_symlink_cannot_redirect_evidence_to_other_file(self):
        secret = Path(self.temp.name) / "private.txt"
        secret.write_text("not a flag", encoding="utf-8")
        try:
            self.flag_path.symlink_to(secret)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks no disponibles en este host")
        status, content, _ = self.request("/evidence")
        self.assertEqual(status, 404)
        self.assertNotIn(b"not a flag", content)


if __name__ == "__main__":
    unittest.main()
