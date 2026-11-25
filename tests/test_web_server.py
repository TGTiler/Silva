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

    def test_llm_offline_clean_error_message(self):
        """Testa se erro de llama-server offline retorna mensagem limpa sem stack trace ou Errno 111."""
        from unittest.mock import patch
        url = f"{self.base_url}/api/chat"
        payload = json.dumps({"message": "uma pergunta complexa que nao tem regra no fallback deterministico"}).encode("utf-8")

        with patch.object(ws.llm_client, "generate_call") as mock_gen:
            mock_gen.return_value = (
                "<call>none()</call>",
                5.0,
                "Não reconheci esse comando no modo rápido (o servidor do modelo local está offline no momento). Tente reformular o pedido ou inicie o llama-server."
            )
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "X-Access-Pin": ACCESS_PIN}
            )
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200)
                res_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(res_data.get("status"), "error")
                self.assertEqual(
                    res_data.get("message"),
                    "Não reconheci esse comando no modo rápido (o servidor do modelo local está offline no momento). Tente reformular o pedido ou inicie o llama-server."
                )

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

    def test_voice_notes_upload_and_check_endpoints(self):
        """Testa POST /api/voice-notes/upload e POST /api/voice-notes/check com validação de PIN."""
        import base64
        from unittest.mock import patch
        import tempfile
        from android_agent.tools import media as tools_media

        b64_audio = base64.b64encode(b"WEBM_TEST_AUDIO").decode("ascii")
        upload_payload = json.dumps({"audio_base64": b64_audio, "ext": "webm", "title": "Teste Web UI"}).encode("utf-8")

        # 1. Sem PIN -> 403
        req_no_pin = urllib.request.Request(
            f"{self.base_url}/api/voice-notes/upload",
            data=upload_payload,
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req_no_pin)
        self.assertEqual(ctx.exception.code, 403)

        # 2. Upload + Check com PIN válido em diretório temporário
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            tmp_cap = tmp_dir / "captures"
            tmp_cap.mkdir(parents=True, exist_ok=True)
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_dir), \
                 patch("android_agent.web_server.CAPTURES_DIR", tmp_cap), \
                 patch.object(tools_media, "CAPTURES_DIR", tmp_cap):
                req_up = urllib.request.Request(
                    f"{self.base_url}/api/voice-notes/upload",
                    data=upload_payload,
                    headers={"Content-Type": "application/json", "X-Access-Pin": ACCESS_PIN},
                )
                with urllib.request.urlopen(req_up) as resp:
                    self.assertEqual(resp.status, 200)
                    up_data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(up_data["status"], "ok")
                    note_id = up_data["data"]["id"]

                chk_payload = json.dumps({"id": note_id}).encode("utf-8")
                req_chk = urllib.request.Request(
                    f"{self.base_url}/api/voice-notes/check",
                    data=chk_payload,
                    headers={"Content-Type": "application/json", "X-Access-Pin": ACCESS_PIN},
                )
                with urllib.request.urlopen(req_chk) as resp:
                    self.assertEqual(resp.status, 200)
                    chk_data = json.loads(resp.read().decode("utf-8"))
                    self.assertEqual(chk_data["status"], "ok")
                    self.assertTrue(chk_data["data"]["checked"])

                # 3. Extensão não permitida (.php / .sh) -> 400 Bad Request
                bad_ext_payload = json.dumps({"audio_base64": b64_audio, "ext": "php", "title": "Evil"}).encode("utf-8")
                req_bad_ext = urllib.request.Request(
                    f"{self.base_url}/api/voice-notes/upload",
                    data=bad_ext_payload,
                    headers={"Content-Type": "application/json", "X-Access-Pin": ACCESS_PIN},
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx_ext:
                    urllib.request.urlopen(req_bad_ext)
                self.assertEqual(ctx_ext.exception.code, 400)

    def test_http_413_payload_limit_and_pin_rate_limit(self):
        """Testa rejeição HTTP 413 (> 8 MB) e rate-limit progressivo por IP no PIN inválido."""
        import http.client
        from unittest.mock import patch
        from android_agent import web_server

        # 1. HTTP 413 via Content-Length > 8 MB sem enviar 8 MB reais
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/api/chat")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("X-Access-Pin", ACCESS_PIN)
        conn.putheader("Content-Length", str(9 * 1024 * 1024))
        conn.endheaders()
        resp = conn.getresponse()
        self.assertEqual(resp.status, 413)
        conn.close()

        # 2. Rate-limit progressivo após 5 falhas consecutivas de PIN
        web_server._PIN_FAILURES.clear()
        with patch("android_agent.web_server.time.sleep") as mock_sleep:
            for _ in range(5):
                req_bad = urllib.request.Request(
                    f"{self.base_url}/api/chat",
                    data=b"{}",
                    headers={"Content-Type": "application/json", "X-Access-Pin": "0000"},
                )
                with self.assertRaises(urllib.error.HTTPError) as ctx_pin:
                    urllib.request.urlopen(req_bad)
                self.assertEqual(ctx_pin.exception.code, 403)
            mock_sleep.assert_called_once_with(1.0)

            # PIN válido zera o contador
            req_ok = urllib.request.Request(
                f"{self.base_url}/api/chat",
                data=json.dumps({"message": "<call>get_battery()</call>"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Access-Pin": ACCESS_PIN},
            )
            with urllib.request.urlopen(req_ok) as resp_ok:
                self.assertEqual(resp_ok.status, 200)
            self.assertEqual(web_server._PIN_FAILURES, {})


if __name__ == "__main__":
    unittest.main()
