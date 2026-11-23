#!/usr/bin/env bash
# ==============================================================================
# SILVA AGENT - ENCERRAMENTO SEGURO DE PROCESSOS (STOP SCRIPT)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Flags de execução
QUIET=false
for arg in "$@"; do
    case "$arg" in
        -q|--quiet)
            QUIET=true
            ;;
    esac
done

# Cores ANSI
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

log_info() {
    if [ "$QUIET" = "false" ]; then
        echo -e "$1"
    fi
}

# ------------------------------------------------------------------------------
# 1. Carregamento de Configurações
# ------------------------------------------------------------------------------
ENV_TARGET="$SCRIPT_DIR/android_agent/.env"
ROOT_ENV="$SCRIPT_DIR/.env"

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

DATA_DIR="$SCRIPT_DIR/android_agent/data"
PIDS_FILE="$DATA_DIR/runtime.pids"
LLAMA_PID_FILE="$DATA_DIR/llama.pid"

# ------------------------------------------------------------------------------
# 2. [1/3] Encerramento por PIDs e Varredura de Processos
# ------------------------------------------------------------------------------
log_info "${CYAN}[1/3] Encerrando processos do Silva (PIDs e instâncias ativas)...${RESET}"

PIDS_TO_KILL=()

if [ -f "$PIDS_FILE" ]; then
    while IFS= read -r pid; do
        pid_clean="$(echo "$pid" | tr -d '[:space:]')"
        if [ -n "$pid_clean" ] && [ "$pid_clean" -eq "$pid_clean" ] 2>/dev/null; then
            PIDS_TO_KILL+=("$pid_clean")
        fi
    done < "$PIDS_FILE"
fi

if [ -f "$LLAMA_PID_FILE" ]; then
    lpid="$(cat "$LLAMA_PID_FILE" 2>/dev/null | tr -d '[:space:]' || true)"
    if [ -n "$lpid" ] && [ "$lpid" -eq "$lpid" ] 2>/dev/null; then
        PIDS_TO_KILL+=("$lpid")
    fi
fi

# Envia SIGTERM para os PIDs identificados
for pid in "${PIDS_TO_KILL[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
    fi
done

# Aguarda até 2s para encerramento gracioso
for _ in 1 2; do
    still_alive=false
    for pid in "${PIDS_TO_KILL[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            still_alive=true
            break
        fi
    done
    if [ "$still_alive" = "false" ]; then
        break
    fi
    sleep 1
done

# Envia SIGKILL se algum processo dos PIDs ainda persistir
for pid in "${PIDS_TO_KILL[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
    fi
done

# Limpeza dos arquivos de controle
rm -f "$PIDS_FILE" "$LLAMA_PID_FILE" 2>/dev/null || true

# Varredura residual de segurança
pkill -f "llama-server.*${LLM_PORT}" 2>/dev/null || true
pkill -f "llama-server" 2>/dev/null || true
pkill -f "android_agent/main.py" 2>/dev/null || true
pkill -f "python3.*main.py.*--web" 2>/dev/null || true

# ------------------------------------------------------------------------------
# 3. [2/3] Liberação Garantida de Portas de Rede
# ------------------------------------------------------------------------------
log_info "${CYAN}[2/3] Liberando portas de rede (WEB: ${WEB_PORT}, LLM: ${LLM_PORT})...${RESET}"

if command -v fuser >/dev/null 2>&1; then
    fuser -k "${WEB_PORT}/tcp" >/dev/null 2>&1 || true
    fuser -k "${LLM_PORT}/tcp" >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
    lsof -ti :"${WEB_PORT}" 2>/dev/null | xargs -r kill -9 >/dev/null 2>&1 || true
    lsof -ti :"${LLM_PORT}" 2>/dev/null | xargs -r kill -9 >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------------------------
# 4. [3/3] Liberação de Wake-Lock e Notificações Android
# ------------------------------------------------------------------------------
log_info "${CYAN}[3/3] Liberando wake-lock do sistema e notificações Android...${RESET}"

termux-wake-unlock 2>/dev/null || true
termux-notification-remove --id silva_voice 2>/dev/null || true
termux-notification-remove --id silva_status 2>/dev/null || true

log_info "${GREEN}[OK] Silva Agent encerrado com sucesso.${RESET}"
exit 0
