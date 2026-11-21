"""
Servidor web local do Silva para Termux e rede local.
Construído com a biblioteca padrão (http.server.ThreadingHTTPServer)
garantindo zero dependências externas e alta estabilidade no Android.
"""

import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from config import ACCESS_PIN, CAPTURES_DIR, WEB_HOST, WEB_PORT
from llm_client import SilvaLLMClient
from parser import execute_call

STATIC_DIR = Path(__file__).resolve().parent / "static"
llm_client = SilvaLLMClient()


class SilvaHTTPRequestHandler(SimpleHTTPRequestHandler):
    server_version = "SilvaAgent/1.0"

    def _send_json(self, data: dict, status: int = HTTPStatus.OK):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Pin")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, file_path: Path, mime_type: str):
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo não encontrado")
            return
        file_bytes = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(file_bytes)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(file_bytes)

    def do_OPTIONS(self):
        """Suporte a CORS pre-flight."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Pin")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. Rota raiz -> index.html
        if path in ("/", "/index.html"):
            index_path = STATIC_DIR / "index.html"
            return self._send_file(index_path, "text/html; charset=utf-8")

        # 2. Rota de capturas -> /captures/<filename>
        if path.startswith("/captures/"):
            filename = unquote(path.replace("/captures/", "")).strip("/")
            # Impede Path Traversal
            safe_path = (CAPTURES_DIR / filename).resolve()
            if not str(safe_path).startswith(str(CAPTURES_DIR.resolve())):
                self.send_error(HTTPStatus.FORBIDDEN, "Acesso negado.")
                return
            mime, _ = mimetypes.guess_type(str(safe_path))
            return self._send_file(safe_path, mime or "image/jpeg")

        # 3. Health check -> /api/health
        if path == "/api/health":
            llm_health = llm_client.check_health()
            return self._send_json({
                "status": "ok",
                "agent": "Silva",
                "llm": llm_health
            })

        self.send_error(HTTPStatus.NOT_FOUND, "Rota não encontrada.")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/chat":
            # Validação de segurança via X-Access-Pin (se configurado)
            if ACCESS_PIN:
                client_pin = self.headers.get("X-Access-Pin", "").strip()
                if client_pin != ACCESS_PIN:
                    return self._send_json(
                        {"status": "error", "message": "PIN de acesso inválido ou ausente."},
                        status=HTTPStatus.FORBIDDEN
                    )

            # Leitura do corpo JSON
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                body_bytes = self.rfile.read(content_len)
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                return self._send_json(
                    {"status": "error", "message": f"Corpo de requisição inválido: {str(e)}"},
                    status=HTTPStatus.BAD_REQUEST
                )

            user_message = body.get("message", "").strip()
            if not user_message:
                return self._send_json(
                    {"status": "error", "message": "Mensagem vazia."},
                    status=HTTPStatus.BAD_REQUEST
                )

            # Se o usuário enviou uma chamada direta para testes manuais (ex: <call>get_battery()</call>)
            if user_message.startswith("<call>") and user_message.endswith("</call>"):
                raw_call = user_message
                latency_ms = 0.0
                err_llm = None
            else:
                # Envia ao micro-modelo via llama-server
                raw_call, latency_ms, err_llm = llm_client.generate_call(user_message)

            if err_llm:
                return self._send_json({
                    "status": "error",
                    "message": f"Silva (LLM Offline): {err_llm}",
                    "raw_call": None,
                    "latency_ms": latency_ms,
                    "image_url": None,
                    "video_url": None,
                    "data": None
                })

            # Execução segura através do parser
            result = execute_call(raw_call)
            result["latency_ms"] = latency_ms

            return self._send_json(result)

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint POST não encontrado.")


def start_server(host: str = WEB_HOST, port: int = WEB_PORT):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, SilvaHTTPRequestHandler)
    print(f"[*] Silva Web Server ativo em http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Encerrando servidor Silva...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    start_server()
