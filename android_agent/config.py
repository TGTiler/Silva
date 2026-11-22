"""
Configurações centrais do micro-agente Silva.
Carrega variáveis de ambiente, define caminhos e o System Prompt mínimo.
"""

import os
import shutil
from pathlib import Path


def load_env(env_path: Path):
    """Carregador simples de .env sem dependência de bibliotecas externas."""
    if not env_path.is_file():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k not in os.environ:
                os.environ[k] = v


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"
if not ENV_FILE.is_file():
    ENV_FILE = PROJECT_ROOT / ".env.example"

load_env(ENV_FILE)

# Servidor Web
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
ACCESS_PIN = os.getenv("ACCESS_PIN", "1234").strip()

# Conexão com o LLM (llama-server)
LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8080").rstrip("/")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "15"))

# Armazenamento de capturas
CAPTURES_DIR = BASE_DIR / "captures"
CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

# Detecção automática de ambiente Termux
HAS_TERMUX = bool(shutil.which("termux-battery-status"))
SIMULATE_HARDWARE = os.getenv("SIMULATE_HARDWARE", "false").lower() in ("1", "true", "yes") or not HAS_TERMUX

# System Prompt estrito do Silva para Function Calling
SILVA_SYSTEM_PROMPT = (
    "Você é o Silva, um micro-agente offline para controle de smartphone Android.\n"
    "Sua única função é traduzir o pedido do usuário para chamadas de função estritas.\n"
    "Ferramentas disponíveis: get_battery(), get_last_sms(limit), send_sms(number, message), "
    "take_photo(camera_id), record_video(duration, camera_id), take_screenshot(), open_app(app_name), make_call(number), get_location(), "
    "get_last_location(), set_location_state(state=bool), get_weather(day, time, location), "
    "set_torch(state), set_dnd(state=bool), vibrate(duration_ms), get_clipboard(), set_clipboard(text), "
    "tell_joke(), set_alarm(time, label, days), cancel_alarm(time, day, label), schedule_event(title, date, time), "
    "remember_note(key, value), recall_note(query), get_notifications(app), set_volume(stream, level), "
    "set_brightness(level), set_timer(minutes, label), calculate(expression), search_google(query, open_browser), "
    "request_ride(destination, app), order_food(query, app), install_app(app_name), media_control(action), "
    "scan_wifi(), connect_wifi(ssid, password), get_wifi_info(), set_wifi_state(state), list_capabilities(), none().\n"
    "Responda EXCLUSIVAMENTE com chamadas no formato: <call>get_battery()</call> ou <call>set_torch(state=True)</call>.\n"
    "Quando o usuário solicitar mais de uma ação na mesma frase, emita múltiplas tags em sequência (ex: <call>get_battery()</call><call>set_torch(state=True)</call>).\n"
    "Caso o comando não corresponda a nenhuma ferramenta ou seja uma conversa geral, responda apenas:\n"
    "<call>none()</call>\n"
    "NUNCA adicione saudações, introduções ou explicações fora da tag."
)
