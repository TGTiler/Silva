"""
Servidor web local do Silva para Termux e rede local.
Construído com a biblioteca padrão (http.server.ThreadingHTTPServer)
garantindo zero dependências externas e alta estabilidade no Android.
"""

import base64
import errno
import hmac
import json
import mimetypes
import signal
import threading
import time
import uuid
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict
from urllib.parse import parse_qs, unquote, urlparse

from config import ACCESS_PIN, CAPTURES_DIR, WEB_AUTO_TTS, WEB_HOST, WEB_PORT
from llm_client import SilvaLLMClient
from parser import execute_call
import scheduler
from scheduler import start_events_scheduler
from tools.core import _FILE_LOCK
from tools.media import check_voice_note
from tools.memory_schedule import _get_memory_db

MAX_POST_BODY_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_AUDIO_EXTENSIONS = {"webm", "ogg", "m4a", "wav"}
_PIN_FAIL_LOCK = threading.Lock()
_PIN_FAILURES: Dict[str, int] = {}

STATIC_DIR = Path(__file__).resolve().parent / "static"
llm_client = SilvaLLMClient()


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """
    Servidor HTTP multi-thread com reutilização imediata de socket (SO_REUSEADDR)
    e threads daemon para evitar Address already in use (Errno 98) e garantir
    encerramento limpo sem processos zumbis.
    """
    allow_reuse_address = True
    daemon_threads = True


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

    _AUDIO_MIME_TYPES = {
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
    }

    def _send_file(self, file_path: Path, mime_type: str):
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo não encontrado")
            return
        ext = file_path.suffix.lower()
        effective_mime = self._AUDIO_MIME_TYPES.get(ext, mime_type or "application/octet-stream")
        file_bytes = file_path.read_bytes()
        total_len = len(file_bytes)

        range_header = (self.headers.get("Range") or "").strip() if getattr(self, "headers", None) else ""
        if range_header.startswith("bytes=") and total_len > 0:
            spec = range_header[len("bytes="):].split(",")[0].strip()
            parts = spec.split("-", 1)
            try:
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else total_len - 1
            except ValueError:
                start, end = 0, total_len - 1
            if start < 0 or start >= total_len or end < start:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{total_len}")
                self.end_headers()
                return
            end = min(end, total_len - 1)
            chunk = file_bytes[start:end + 1]
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header("Content-Type", effective_mime)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
            self.send_header("Content-Length", str(len(chunk)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(chunk)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", effective_mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(total_len))
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
            # Validação do ACCESS_PIN se configurado (via query param ?pin= ou header X-Access-Pin)
            if ACCESS_PIN:
                query_params = parse_qs(parsed.query)
                pin_from_query = query_params.get("pin", [""])[0].strip()
                pin_from_header = self.headers.get("X-Access-Pin", "").strip()

                pin_valid = (
                    (pin_from_query and hmac.compare_digest(pin_from_query, ACCESS_PIN)) or
                    (pin_from_header and hmac.compare_digest(pin_from_header, ACCESS_PIN))
                )
                if not pin_valid:
                    return self._send_json(
                        {"status": "error", "message": "PIN de acesso inválido ou ausente para acessar mídia."},
                        status=HTTPStatus.FORBIDDEN
                    )

            filename = unquote(path.replace("/captures/", "")).strip("/")
            # Impede Path Traversal de forma estrita via is_relative_to
            target_path = (CAPTURES_DIR / filename).resolve()
            try:
                if not target_path.is_relative_to(CAPTURES_DIR.resolve()):
                    return self._send_json(
                        {"status": "error", "message": "Acesso negado: tentativa de path traversal."},
                        status=HTTPStatus.FORBIDDEN
                    )
            except AttributeError:
                if not str(target_path).startswith(str(CAPTURES_DIR.resolve())):
                    return self._send_json(
                        {"status": "error", "message": "Acesso negado: tentativa de path traversal."},
                        status=HTTPStatus.FORBIDDEN
                    )

            if not target_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "Arquivo de mídia não encontrado.")
                return

            mime, _ = mimetypes.guess_type(str(target_path))
            return self._send_file(target_path, mime or "application/octet-stream")

        # 3. Health check -> /api/health
        if path == "/api/health":
            llm_health = llm_client.check_health()
            try:
                from .tools.sleep_monitor import get_undelivered_sleep_reports
            except ImportError:
                from tools.sleep_monitor import get_undelivered_sleep_reports
            return self._send_json({
                "status": "ok",
                "agent": "Silva",
                "llm": llm_health,
                "web_auto_tts": WEB_AUTO_TTS,
                "triggered_alerts": scheduler.pop_triggered_alerts(),
                "sleep_reports": get_undelivered_sleep_reports(),
            })

        self.send_error(HTTPStatus.NOT_FOUND, "Rota não encontrada.")

    def _verify_access_pin(self, client_pin: str) -> bool:
        """Valida X-Access-Pin com rate-limit progressivo por IP após 5 falhas consecutivas."""
        if not ACCESS_PIN:
            return True
        client_ip = (self.client_address[0] if self.client_address else "") or "unknown"
        if client_pin and hmac.compare_digest(client_pin, ACCESS_PIN):
            with _PIN_FAIL_LOCK:
                _PIN_FAILURES.pop(client_ip, None)
            return True

        with _PIN_FAIL_LOCK:
            fails = _PIN_FAILURES.get(client_ip, 0) + 1
            _PIN_FAILURES[client_ip] = fails
        if fails >= 5:
            time.sleep(min(3.0, float(fails - 4)))
        self._send_json(
            {"status": "error", "message": "PIN de acesso inválido ou ausente."},
            status=HTTPStatus.FORBIDDEN,
        )
        return False

    def _read_post_body_bytes(self):
        """Valida Content-Length (<= 8 MB) antes de ler do socket, retornando bytes ou None."""
        raw_len = self.headers.get("Content-Length")
        try:
            content_len = int(raw_len) if raw_len is not None else 0
        except (TypeError, ValueError):
            self._send_json(
                {"status": "error", "message": "Content-Length inválido."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return None

        if content_len < 0 or content_len > MAX_POST_BODY_BYTES:
            self._send_json(
                {"status": "error", "message": "Payload excede o limite máximo permitido de 8 MB."},
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return None

        return self.rfile.read(content_len)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/chat":
            if not self._verify_access_pin(self.headers.get("X-Access-Pin", "").strip()):
                return
            try:
                from .tools.sleep_monitor import record_web_activity
            except ImportError:
                from tools.sleep_monitor import record_web_activity
            record_web_activity()

            body_bytes = self._read_post_body_bytes()
            if body_bytes is None:
                return
            try:
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

            session_id = (
                self.headers.get("X-Session-Id")
                or body.get("session_id")
                or (self.client_address[0] if self.client_address else "")
                or "default"
            )
            session_id = str(session_id).strip() or "default"

            # Se o usuário enviou uma chamada direta para testes manuais (ex: <call>get_battery()</call>)
            if user_message.startswith("<call>") and user_message.endswith("</call>"):
                raw_call = user_message
                latency_ms = 0.0
                err_llm = None
            else:
                # Envia ao micro-modelo via llama-server
                raw_call, latency_ms, err_llm = llm_client.generate_call(user_message, session_id=session_id)

            if err_llm:
                if "Não reconheci esse comando no modo rápido" in err_llm:
                    msg = err_llm
                elif any(ref in err_llm for ref in ["111", "Connection refused", "ConnectionRefusedError", "Failed to connect"]):
                    msg = "Não reconheci esse comando no modo rápido (o servidor do modelo local está offline no momento). Tente reformular o pedido ou inicie o llama-server."
                else:
                    msg = f"Silva (LLM Offline): {err_llm}"

                return self._send_json({
                    "status": "error",
                    "message": msg,
                    "raw_call": None,
                    "latency_ms": latency_ms,
                    "image_url": None,
                    "video_url": None,
                    "data": None,
                    "tool_data": None
                })

            # Execução segura através do parser
            result = execute_call(raw_call, session_id=session_id, user_text=user_message)
            result["latency_ms"] = latency_ms

            if "tool_data" not in result:
                primary_tool_data = None
                if result.get("calls"):
                    for c in result["calls"]:
                        if c.get("data") is not None:
                            primary_tool_data = c["data"]
                            break
                if primary_tool_data is None and result.get("data"):
                    if isinstance(result["data"], list) and len(result["data"]) > 0:
                        primary_tool_data = result["data"][0]
                    elif isinstance(result["data"], dict):
                        primary_tool_data = result["data"]
                result["tool_data"] = primary_tool_data

            return self._send_json(result)

        if path == "/api/voice-notes/check":
            if not self._verify_access_pin(self.headers.get("X-Access-Pin", "").strip()):
                return
            body_bytes = self._read_post_body_bytes()
            if body_bytes is None:
                return
            try:
                body = json.loads(body_bytes.decode("utf-8"))
                note_id = int(body.get("id", 0))
            except Exception as e:
                return self._send_json(
                    {"status": "error", "message": f"Requisição inválida: {str(e)}"},
                    status=HTTPStatus.BAD_REQUEST,
                )
            if note_id <= 0:
                return self._send_json(
                    {"status": "error", "message": "ID da nota inválido."},
                    status=HTTPStatus.BAD_REQUEST,
                )
            res = check_voice_note(note_id=note_id)
            return self._send_json(res)

        if path == "/api/voice-notes/upload":
            if not self._verify_access_pin(self.headers.get("X-Access-Pin", "").strip()):
                return
            body_bytes = self._read_post_body_bytes()
            if body_bytes is None:
                return
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                return self._send_json(
                    {"status": "error", "message": f"Corpo inválido: {str(e)}"},
                    status=HTTPStatus.BAD_REQUEST,
                )

            raw_b64 = str(body.get("audio_base64") or "").strip()
            if "," in raw_b64 and raw_b64.startswith("data:"):
                raw_b64 = raw_b64.split(",", 1)[1]
            if not raw_b64:
                return self._send_json(
                    {"status": "error", "message": "Áudio vazio."},
                    status=HTTPStatus.BAD_REQUEST,
                )

            ext = str(body.get("ext") or "webm").strip().lower().lstrip(".")
            if ext not in ALLOWED_AUDIO_EXTENSIONS:
                return self._send_json(
                    {"status": "error", "message": f"Extensão de áudio não permitida: '{ext}'."},
                    status=HTTPStatus.BAD_REQUEST,
                )

            try:
                audio_bytes = base64.b64decode(raw_b64, validate=True)
            except Exception:
                return self._send_json(
                    {"status": "error", "message": "Base64 de áudio inválido."},
                    status=HTTPStatus.BAD_REQUEST,
                )

            CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"voice_note_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.{ext}"
            target_path = (CAPTURES_DIR / filename).resolve()
            if not target_path.is_relative_to(CAPTURES_DIR.resolve()):
                return self._send_json(
                    {"status": "error", "message": "Caminho de destino inválido."},
                    status=HTTPStatus.FORBIDDEN,
                )
            target_path.write_bytes(audio_bytes)
            title = str(body.get("title") or "").strip() or f"Nota de voz ({datetime.now().strftime('%d/%m às %H:%M')})"

            with _FILE_LOCK:
                conn = _get_memory_db()
                try:
                    with conn:
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO voice_notes (title, note_type, filename, is_checked) VALUES (?, 'audio', ?, 0)",
                            (title, filename),
                        )
                        note_id = cur.lastrowid
                finally:
                    conn.close()

            audio_url = f"/captures/{filename}"
            return self._send_json({
                "status": "ok",
                "message": f"Silva: Nota de voz '{title}' salva no checklist.",
                "audio_url": audio_url,
                "media_items": [{"type": "audio", "url": audio_url}],
                "data": {"id": note_id, "title": title, "note_type": "audio", "url": audio_url},
            })

        if path == "/api/sleep/ack":
            if not self._verify_access_pin(self.headers.get("X-Access-Pin", "").strip()):
                return
            raw_bytes = self._read_post_body_bytes()
            if raw_bytes is None:
                return
            try:
                body = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
            except Exception:
                return self._send_json(
                    {"status": "error", "message": "JSON inválido."},
                    status=HTTPStatus.BAD_REQUEST,
                )
            ids_list = []
            if isinstance(body.get("ids"), list):
                ids_list.extend(body["ids"])
            if body.get("id") is not None:
                ids_list.append(body["id"])
            try:
                from .tools.sleep_monitor import ack_sleep_reports
            except ImportError:
                from tools.sleep_monitor import ack_sleep_reports
            acked = ack_sleep_reports(ids_list)
            return self._send_json({"status": "ok", "acked": acked})

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint POST não encontrado.")


def start_server(host: str = WEB_HOST, port: int = WEB_PORT):
    httpd = None
    active_port = port
    max_port = port + 5

    for current_port in range(port, max_port + 1):
        try:
            server_address = (host, current_port)
            httpd = ReusableThreadingHTTPServer(server_address, SilvaHTTPRequestHandler)
            active_port = current_port
            break
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                print(f"[AVISO] Porta {current_port} já está em uso (Errno 98: Address already in use).")
                if current_port < max_port:
                    print(f"[*] Tentando porta alternativa {current_port + 1}...")
                else:
                    print(f"[ERRO] Falha ao iniciar servidor: portas {port} até {max_port} ocupadas.")
                    raise
            else:
                raise

    if active_port != port:
        print(f"[!] ATENÇÃO: Porta original {port} estava em uso. Fallback para http://{host}:{active_port}")

    print(f"[*] Silva Web Server ativo em http://{host}:{active_port}")

    try:
        start_events_scheduler(interval_sec=30)
        print("[*] Agendador de lembretes ativo em background (verificação a cada 30s)")
    except Exception as e:
        print(f"[AVISO] Falha ao iniciar agendador de lembretes: {e}")

    # Registra handlers de sinal para encerramento gracioso (apenas na thread principal)
    orig_sigint = None
    orig_sigterm = None

    def _shutdown_handler(signum, frame):
        print(f"\n[*] Sinal {signum} recebido. Encerrando servidor Silva de forma limpa...")
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    if threading.current_thread() is threading.main_thread():
        try:
            orig_sigint = signal.signal(signal.SIGINT, _shutdown_handler)
            orig_sigterm = signal.signal(signal.SIGTERM, _shutdown_handler)
        except (ValueError, AttributeError):
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Encerrando servidor Silva...")
    finally:
        if orig_sigint is not None:
            try:
                signal.signal(signal.SIGINT, orig_sigint)
            except (ValueError, AttributeError):
                pass
        if orig_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, orig_sigterm)
            except (ValueError, AttributeError):
                pass
        try:
            httpd.server_close()
        except Exception:
            pass
        print("[*] Servidor finalizado e sockets liberados.")


if __name__ == "__main__":
    start_server()
