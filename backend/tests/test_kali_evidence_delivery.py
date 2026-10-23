"""La vista del estudiante entrega preparación para Kali, sin adjuntos web."""
import ast
import base64
import hashlib
import io
import json
import shlex
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.api import runs
from app.domain.challenges.offline import CATALOG
from app.models import Challenge
from app.services import offline_runtime, dfir_runtime
from test_run_lifecycle import MemorySession


def prepared_files(command):
    # Inspeccionar el contenido sin ejecutar el comando ni escribir en una VM.
    script = ast.parse(shlex.split(command)[2])
    encoded = next(ast.literal_eval(node.args[0]) for node in ast.walk(script)
                   if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'b64decode')
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class KaliEvidenceDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.run = SimpleNamespace(id=31, user_id=7, challenge_id=3)
        self.user = SimpleNamespace(id=7)

    def request(self, session):
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(session_factory=lambda: session)))

    def assert_manifest(self, files):
        for row in files['SHA256SUMS.txt'].decode().splitlines():
            digest, name = row.split('  ', 1)
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)

    async def test_every_analysis_case_keeps_original_evidence_and_hashes_in_kali(self):
        for code in CATALOG:
            challenge = SimpleNamespace(code=code, asset_references=['OFFLINE-CASE', 'LAB-KALI'])
            with patch.object(runs, '_offline_run', new=AsyncMock(return_value=(self.run, challenge))):
                response = await runs.get_offline_case(31, self.request(MemorySession()), self.user)
            view = json.loads(response.body)
            self.assertEqual(set(view), {'title', 'brief', 'kali_command'})
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertNotIn('content-disposition', response.headers)
            files = prepared_files(view['kali_command'])
            original, _ = offline_runtime.case_for(self.run, code)
            for name, data in original['files'].items():
                self.assertEqual(files[name], base64.b64decode(data))
            self.assert_manifest(files)

    async def test_forensic_calibration_and_records_remain_available_inside_kali(self):
        challenge = SimpleNamespace(asset_references=['DFIR-CASE', 'LAB-KALI'])
        session = MemorySession(objects={(Challenge, 3): challenge})
        with patch.object(runs, '_dfir_run', new=AsyncMock(return_value=self.run)):
            response = await runs.get_dfir_case(31, self.request(session), self.user)
        view = json.loads(response.body)
        self.assertEqual(set(view), {'title', 'brief', 'clock_notes', 'kali_command'})
        files = prepared_files(view['kali_command'])
        original, _ = dfir_runtime.case_for(self.run)
        self.assertEqual(json.loads(files['case.json']), original)
        self.assert_manifest(files)

    def test_zip_download_route_is_removed(self):
        self.assertFalse(any(route.path.endswith('/offline/download') for route in runs.router.routes))
