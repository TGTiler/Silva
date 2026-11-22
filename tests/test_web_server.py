"""
Testes de Integração do Servidor Web, Autenticação PIN e Proteção de Mídia.
"""

import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

import android_agent.web_server as ws
from android_agent.config import ACCESS_PIN, CAPTURES_DIR


class TestWebServer(unittest.TestCase):
    """Testa endpoints HTTP, autorização por PIN e proteção contra Path Traversal."""

    @classmethod
    def setUpClass(cls):
        # Garante diretório de capturas e cria arquivo dummy
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        cls.dummy_file = CAPTURES_DIR / "test_capture_unit.jpg"
        with open(cls.dummy_file, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb")

        # Inicia servidor efêmero na porta 0 (livre)
        cls.server = ws.ReusableThreadingHTTPServer(("127.0.0.1", 0), ws.SilvaHTTPRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"

        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        # Encerra o servidor de forma limpa
        cls.server.shutdown()
        cls.server.server_close()
        if cls.dummy_file.is_file():
            cls.dummy_file.unlink()

    def test_health_endpoint(self):
        """Verifica se GET /api/health retorna 200 OK e JSON válido."""
        url = f"{self.base_url}/api/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("agent"), "Silva")

    def test_chat_pin_protection(self):
        """Verifica se POST /api/chat bloqueia PIN inválido/ausente e aceita PIN correto."""
        url = f"{self.base_url}/api/chat"
        payload = json.dumps({"message": "qual o nivel da bateria?"}).encode("utf-8")

        # 1. Sem PIN -> 403 Forbidden
        req_no_pin = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_no_pin)
        self.assertEqual(ctx.exception.code, 403)

        # 2. PIN errado -> 403 Forbidden
        req_wrong_pin = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "X-Access-Pin": "wrong_pin_9999"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_wrong_pin)
        self.assertEqual(ctx.exception.code, 403)

        # 3. PIN correto -> 200 OK
        req_ok = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "X-Access-Pin": ACCESS_PIN}
        )
        with urllib.request.urlopen(req_ok) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(res_data.get("status"), "ok")
            self.assertIn("calls", res_data)

    def test_captures_pin_and_path_traversal(self):
        """Testa restrição de PIN e bloqueio de path traversal na rota /captures/*."""
        filename = self.dummy_file.name

        # 1. Acesso sem PIN -> 403 Forbidden
        url_no_pin = f"{self.base_url}/captures/{filename}"
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(url_no_pin)
        self.assertEqual(ctx.exception.code, 403)

        # 2. Acesso com PIN correto via query param ?pin= -> 200 OK
        url_with_pin = f"{self.base_url}/captures/{filename}?pin={ACCESS_PIN}"
        with urllib.request.urlopen(url_with_pin) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read()
            self.assertGreater(len(content), 0)

        # 3. Acesso com PIN correto via header X-Access-Pin -> 200 OK
        req_header = urllib.request.Request(
            f"{self.base_url}/captures/{filename}",
            headers={"X-Access-Pin": ACCESS_PIN}
        )
        with urllib.request.urlopen(req_header) as resp:
            self.assertEqual(resp.status, 200)

        # 4. Tentativa de Path Traversal -> 403 Forbidden
        traversal_url = f"{self.base_url}/captures/../../../../etc/passwd?pin={ACCESS_PIN}"
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(traversal_url)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
