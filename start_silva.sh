#!/usr/bin/env bash
# ==============================================================================
# SILVA AGENT - INICIALIZADOR UNIFICADO (EDGE RUNTIME)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKGROUND_MODE=false
for arg in "$@"; do
    case "$arg" in
        --background|--daemon|-d)
            BACKGROUND_MODE=true
            ;;
    esac
done

ENV_TARGET="$SCRIPT_DIR/android_agent/.env"
ROOT_ENV="$SCRIPT_DIR/.env"

# Cores ANSI
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

# ------------------------------------------------------------------------------
# 1. Verificação de Auto-Setup (.env)
# ------------------------------------------------------------------------------
if [ ! -f "$ENV_TARGET" ] && [ ! -f "$ROOT_ENV" ]; then
    echo -e "${YELLOW}[!] Ambiente não inicializado (.env ausente). Executando ./install-silva.sh...${RESET}"
    if [ -x "$SCRIPT_DIR/install-silva.sh" ]; then
        "$SCRIPT_DIR/install-silva.sh"
    else
        echo -e "${RED}[ERRO] Arquivo install-silva.sh não encontrado.${RESET}"
        exit 1
    fi
fi

# Carrega variáveis de ambiente
if [ -f "$ENV_TARGET" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_TARGET" 2>/dev/null || true
    set +a
elif [ -f "$ROOT_ENV" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ROOT_ENV" 2>/dev/null || true
    set +a
fi

WEB_PORT="${WEB_PORT:-5000}"
LLM_PORT="8080"
if [ -n "$LLAMA_SERVER_URL" ]; then
    PARSED_PORT="$(echo "$LLAMA_SERVER_URL" | grep -oE ':[0-9]+' | tr -d ':' || true)"
    if [ -n "$PARSED_PORT" ]; then
        LLM_PORT="$PARSED_PORT"
    fi
fi

LOG_DIR="$SCRIPT_DIR/android_agent/logs"
DATA_DIR="$SCRIPT_DIR/android_agent/data"
mkdir -p "$LOG_DIR" "$DATA_DIR"

# Impede suspensão de CPU e Wi-Fi no Android
termux-wake-lock 2>/dev/null || true

# ------------------------------------------------------------------------------
# 2. Limpeza de Instâncias e Portas Anteriores
# ------------------------------------------------------------------------------
echo -e "${CYAN}[*] Verificando e liberando portas e processos anteriores...${RESET}"

if [ -x "$SCRIPT_DIR/stop-silva.sh" ]; then
    "$SCRIPT_DIR/stop-silva.sh" --quiet
else
    pkill -f "llama-server" >/dev/null 2>&1 || true
    pkill -f "android_agent/main.py" >/dev/null 2>&1 || true
    pkill -f "python3.*main.py.*--web" >/dev/null 2>&1 || true
fi

sleep 1

# ------------------------------------------------------------------------------
# 3. Gerenciamento de Ciclo de Vida e Sinais (Trap)
# ------------------------------------------------------------------------------
LLAMA_PID=""
WEB_PID=""
PIDS_FILE="$DATA_DIR/runtime.pids"
LLAMA_LOG="$LOG_DIR/llama.log"
WEB_LOG="$LOG_DIR/web.log"

_write_pids_file() {
    {
        echo "llama_pid=${LLAMA_PID}"
        echo "web_pid=${WEB_PID}"
    } > "$PIDS_FILE"
}

_spawn_detached() {
    local logfile="$1"
    shift
    if command -v setsid >/dev/null 2>&1; then
        setsid "$@" </dev/null >> "$logfile" 2>&1 &
    else
        nohup "$@" </dev/null >> "$logfile" 2>&1 &
    fi
}

cleanup() {
    trap - EXIT INT TERM
    echo ""
    echo -e "${YELLOW}[*] Encerrando Silva Agent e serviços acoplados...${RESET}"
    if [ -x "$SCRIPT_DIR/stop-silva.sh" ]; then
        "$SCRIPT_DIR/stop-silva.sh" --quiet
    else
        if [ -n "$LLAMA_PID" ] && kill -0 "$LLAMA_PID" 2>/dev/null; then
            kill "$LLAMA_PID" 2>/dev/null || true
        fi
        if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
            kill "$WEB_PID" 2>/dev/null || true
        fi
        rm -f "$DATA_DIR/llama.pid" "$PIDS_FILE" 2>/dev/null || true
        termux-wake-unlock 2>/dev/null || true
    fi
    echo -e "${GREEN}[OK] Serviços encerrados com segurança. Até logo!${RESET}"
    exit 0
}

if [ "$BACKGROUND_MODE" != "true" ]; then
    trap cleanup INT TERM
fi

# ------------------------------------------------------------------------------
# 4. Inicialização do llama-server (se configurado)
# ------------------------------------------------------------------------------
is_llama_online() {
    if command -v curl >/dev/null 2>&1; then
        curl -s -m 1 "http://127.0.0.1:${LLM_PORT}/health" >/dev/null 2>&1 || curl -s -m 1 "http://127.0.0.1:${LLM_PORT}/" >/dev/null 2>&1
    else
        python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${LLM_PORT}/health', timeout=1)" >/dev/null 2>&1
    fi
}

LLAMA_BIN="${LLAMA_SERVER_BIN:-}"
if [ -z "$LLAMA_BIN" ] || [ ! -x "$LLAMA_BIN" ]; then
    if command -v llama-server >/dev/null 2>&1; then
        LLAMA_BIN="$(command -v llama-server)"
    elif [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/llama-server" ]; then
        LLAMA_BIN="$PREFIX/bin/llama-server"
    elif [ -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
        LLAMA_BIN="$HOME/llama.cpp/build/bin/llama-server"
    elif [ -x "$SCRIPT_DIR/android_agent/llama-server" ]; then
        LLAMA_BIN="$SCRIPT_DIR/android_agent/llama-server"
    fi
fi

TARGET_MODEL="${MODEL_PATH:-${LLAMA_MODEL_PATH:-}}"
if [ -z "$TARGET_MODEL" ] || [ ! -f "$TARGET_MODEL" ]; then
    for sdir in "$SCRIPT_DIR/models" "$SCRIPT_DIR/android_agent/models" "$HOME/models" "$SCRIPT_DIR"; do
        if [ -d "$sdir" ]; then
            found="$(find "$sdir" -maxdepth 2 -type f -name "*.gguf" -size +10M 2>/dev/null | head -n 1)"
            if [ -n "$found" ]; then
                TARGET_MODEL="$found"
                break
            fi
        fi
    done
fi

LLM_STATUS_MSG="${YELLOW}[!] Offline (Fallback Inteligente Ativo - 39 ferramentas funcionais)${RESET}"

if is_llama_online; then
    LLM_STATUS_MSG="${GREEN}[OK] Online (llama-server já em execução na porta ${LLM_PORT})${RESET}"
elif [ -n "$LLAMA_BIN" ] && [ -x "$LLAMA_BIN" ] && [ -n "$TARGET_MODEL" ] && [ -f "$TARGET_MODEL" ]; then
    MODEL_NAME="$(basename "$TARGET_MODEL")"
    echo -e "${CYAN}[*] Iniciando llama-server local com modelo: ${MODEL_NAME}...${RESET}"
    : > "$LLAMA_LOG"
    _spawn_detached "$LLAMA_LOG" "$LLAMA_BIN" -m "$TARGET_MODEL" --host 127.0.0.1 --port "$LLM_PORT" -c 1024 -t 4
    LLAMA_PID=$!
    _write_pids_file
    echo "$LLAMA_PID" > "$DATA_DIR/llama.pid"

    echo -n "    Aguardando inicialização do llama-server"
    LLAMA_READY=false
    for _ in $(seq 1 15); do
        if is_llama_online; then
            LLAMA_READY=true
            break
        fi
        if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
            echo ""
            echo -e "${RED}    [!] Processo llama-server finalizou prematuramente. Verifique logs em $LLAMA_LOG${RESET}"
            break
        fi
        sleep 1
        echo -n "."
    done
    echo ""

    if [ "$LLAMA_READY" = "true" ]; then
        LLM_STATUS_MSG="${GREEN}[OK] Online (llama-server ativo na porta ${LLM_PORT})${RESET}"
    else
        LLM_STATUS_MSG="${YELLOW}[!] Timeout de 15s (Fallback Inteligente ativo)${RESET}"
    fi
else
    LLM_STATUS_MSG="${YELLOW}[!] Não configurado (Fallback Inteligente ativo)${RESET}"
fi

# ------------------------------------------------------------------------------
# 5. Detecção de IP Local e Apresentação do Banner
# ------------------------------------------------------------------------------
LOCAL_IP="$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    print(ip)
except Exception:
    print('127.0.0.1')
" 2>/dev/null || echo "127.0.0.1")"

PIN_DISPLAY="${ACCESS_PIN:-[Nenhum]}"

echo ""
echo -e "${BOLD}========================================================${RESET}"
echo -e "${BOLD}         SILVA AGENT - SISTEMA EM OPERAÇÃO              ${RESET}"
echo -e "${BOLD}========================================================${RESET}"
echo -e "  Motor LLM:         $LLM_STATUS_MSG"
echo -e "  Acesso no Celular: ${CYAN}http://127.0.0.1:${WEB_PORT}${RESET}"
if [ -n "$LOCAL_IP" ] && [ "$LOCAL_IP" != "127.0.0.1" ]; then
    echo -e "  Acesso na Rede:    ${CYAN}http://${LOCAL_IP}:${WEB_PORT}${RESET}"
fi
echo -e "  PIN de Segurança:  ${BOLD}${PIN_DISPLAY}${RESET}"
echo -e "  Logs LLM / Web:    ${LLAMA_LOG} | ${WEB_LOG}"
echo -e "${BOLD}========================================================${RESET}"
echo -e "  Pressione ${RED}Ctrl+C${RESET} a qualquer momento para encerrar."
echo -e "  Para encerrar em segundo plano: ${CYAN}./stop-silva.sh${RESET}"
echo -e "${BOLD}--------------------------------------------------------${RESET}"
echo ""

# ------------------------------------------------------------------------------
# 6. Execução do Servidor Web (Desacoplado)
# ------------------------------------------------------------------------------
cd "$SCRIPT_DIR/android_agent"
: > "$WEB_LOG"
_spawn_detached "$WEB_LOG" python3 main.py --web --port "$WEB_PORT"
WEB_PID=$!
_write_pids_file

if [ "$BACKGROUND_MODE" = "true" ]; then
    echo -e "${GREEN}[OK] Serviços iniciados em background (llama_pid=${LLAMA_PID:-N/A}, web_pid=${WEB_PID}).${RESET}"
    exit 0
fi

wait "$WEB_PID"
