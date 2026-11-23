#!/usr/bin/env bash
# Script de inicialização completa do Silva: llama-server + web_server
set -e

# Navega para o diretório do script
cd "$(dirname "$0")"

# Impede suspensão da CPU e do Wi-Fi pelo Android (Wake Lock)
termux-wake-lock 2>/dev/null || true

echo "========================================================"
echo "         INICIANDO SILVA AGENT (EDGE RUNTIME)          "
echo "========================================================"

mkdir -p data logs

# 1. Carrega variáveis de ambiente do .env antes de checar binários e portas
ENV_PATH=""
if [ -f "./.env" ]; then
    ENV_PATH="./.env"
elif [ -f "../.env" ]; then
    ENV_PATH="../.env"
elif [ -f "./.env.example" ]; then
    ENV_PATH="./.env.example"
elif [ -f "../.env.example" ]; then
    ENV_PATH="../.env.example"
fi

if [ -n "$ENV_PATH" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_PATH" 2>/dev/null || true
    set +a
fi

WEB_PORT="${WEB_PORT:-5000}"
LLM_PORT="8080"
if [ -n "$LLAMA_SERVER_URL" ]; then
    PARSED_LLM_PORT=$(echo "$LLAMA_SERVER_URL" | grep -oE ':[0-9]+' | tr -d ':' || true)
    if [ -n "$PARSED_LLM_PORT" ]; then
        LLM_PORT="$PARSED_LLM_PORT"
    fi
fi

# Verifica se modo de voz foi solicitado via flag --voice ou no .env
VOICE_MODE=false
for arg in "$@"; do
    if [ "$arg" == "--voice" ] || [ "$arg" == "-v" ]; then
        VOICE_MODE=true
    fi
done

if [ "$VOICE_MODE" != "true" ]; then
    if [ "${ENABLE_VOICE_MODE:-false}" == "true" ] || [ "${ENABLE_VOICE_MODE:-false}" == "1" ]; then
        VOICE_MODE=true
    fi
fi

echo "[*] Verificando e limpando eventuais processos órfãos anteriores..."
if [ -f "data/llama.pid" ]; then
    OLD_LLAMA=$(cat data/llama.pid 2>/dev/null || true)
    if [ -n "$OLD_LLAMA" ] && kill -0 "$OLD_LLAMA" 2>/dev/null; then
        echo "[*] Encerrando instância prévia do llama-server (PID: $OLD_LLAMA)..."
        kill "$OLD_LLAMA" 2>/dev/null || true
    fi
    rm -f data/llama.pid
fi

if [ -f "data/web.pid" ]; then
    OLD_WEB=$(cat data/web.pid 2>/dev/null || true)
    if [ -n "$OLD_WEB" ] && kill -0 "$OLD_WEB" 2>/dev/null; then
        echo "[*] Encerrando instância prévia do web_server (PID: $OLD_WEB)..."
        kill "$OLD_WEB" 2>/dev/null || true
    fi
    rm -f data/web.pid
fi

# pkill cirúrgico para instâncias em background
pkill -f "llama-server.*silva-135m" >/dev/null 2>&1 || true
pkill -f "android_agent/main.py" >/dev/null 2>&1 || true
pkill -f "python3.*main.py.*--web" >/dev/null 2>&1 || true

# Libera a porta do Web Server caso tenha ficado presa
if command -v fuser >/dev/null 2>&1; then
    fuser -k "${WEB_PORT}/tcp" >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
    lsof -ti :"${WEB_PORT}" 2>/dev/null | xargs -r kill -9 >/dev/null 2>&1 || true
fi

# Aguarda até 1s para a liberação dos descritores pelo sistema operacional
sleep 1

LLAMA_PID=""
WEB_PID=""

# Função para encerrar subprocessos ao sair
cleanup() {
    trap - EXIT INT TERM
    echo ""
    echo "[*] Encerrando serviços do Silva..."
    if [ -n "$LLAMA_PID" ] && kill -0 "$LLAMA_PID" 2>/dev/null; then
        echo "[*] Finalizando llama-server (PID: $LLAMA_PID)..."
        kill "$LLAMA_PID" 2>/dev/null || true
    fi
    if [ -f "data/llama.pid" ]; then
        PID_FILE_LLAMA=$(cat data/llama.pid 2>/dev/null || true)
        if [ -n "$PID_FILE_LLAMA" ] && kill -0 "$PID_FILE_LLAMA" 2>/dev/null; then
            kill "$PID_FILE_LLAMA" 2>/dev/null || true
        fi
        rm -f data/llama.pid
    fi

    if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
        echo "[*] Finalizando Silva Web Server (PID: $WEB_PID)..."
        kill "$WEB_PID" 2>/dev/null || true
    fi
    if [ -f "data/web.pid" ]; then
        PID_FILE_WEB=$(cat data/web.pid 2>/dev/null || true)
        if [ -n "$PID_FILE_WEB" ] && kill -0 "$PID_FILE_WEB" 2>/dev/null; then
            kill "$PID_FILE_WEB" 2>/dev/null || true
        fi
        rm -f data/web.pid
    fi

    if [ "$VOICE_MODE" == "true" ] || [ -f "data/voice_state.json" ]; then
        echo "[*] Encerrando serviço de voz e removendo notificação persistente..."
        python3 voice_assistant.py --action stop-service >/dev/null 2>&1 || true
    fi
    exit 0
}
trap cleanup EXIT INT TERM

# Localização e auto-detecção do binário llama-server
LLAMA_BIN="${LLAMA_SERVER_BIN:-}"
if [ -z "$LLAMA_BIN" ] || [ ! -x "$LLAMA_BIN" ]; then
    if command -v llama-server >/dev/null 2>&1; then
        LLAMA_BIN=$(command -v llama-server)
    elif [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/llama-server" ]; then
        LLAMA_BIN="$PREFIX/bin/llama-server"
    elif [ -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
        LLAMA_BIN="$HOME/llama.cpp/build/bin/llama-server"
    elif [ -x "./llama-server" ]; then
        LLAMA_BIN="./llama-server"
    elif [ -x "./llama.cpp/build/bin/llama-server" ]; then
        LLAMA_BIN="./llama.cpp/build/bin/llama-server"
    elif [ -x "./llama.cpp/build/llama-server" ]; then
        LLAMA_BIN="./llama.cpp/build/llama-server"
    fi
fi

# Localiza arquivo de modelo GGUF (prioriza silva-135m.gguf)
MODEL_PATH="${LLAMA_MODEL_PATH:-}"
if [ -z "$MODEL_PATH" ] || [ ! -f "$MODEL_PATH" ]; then
    if [ -f "./models/silva-135m.gguf" ]; then
        MODEL_PATH="./models/silva-135m.gguf"
    elif [ -d "./models" ]; then
        MODEL_PATH=$(find ./models -maxdepth 1 -name "*.gguf" 2>/dev/null | head -n 1 || true)
    fi
fi

# Verifica se llama-server já está respondendo
is_llama_online() {
    if command -v curl >/dev/null 2>&1; then
        curl -s -m 1 "http://127.0.0.1:${LLM_PORT}/health" >/dev/null 2>&1 || curl -s -m 1 "http://127.0.0.1:${LLM_PORT}/" >/dev/null 2>&1
    else
        python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${LLM_PORT}/health', timeout=1)" >/dev/null 2>&1
    fi
}

# 1. Inicia o llama-server se disponível e não estiver respondendo
if is_llama_online; then
    echo "[*] llama-server já está ativo e respondendo em 127.0.0.1:${LLM_PORT} (reutilizando serviço existente)."
elif [ -n "$LLAMA_BIN" ] && [ -n "$MODEL_PATH" ] && [ -f "$MODEL_PATH" ]; then
    MODEL_NAME=$(basename "$MODEL_PATH")
    echo "[*] Modelo GGUF detectado e ativo: $MODEL_NAME"
    echo "    -> Caminho completo: $MODEL_PATH"
    echo "[*] Subindo llama-server na porta $LLM_PORT (background)..."
    
    # Flags universais compatíveis com builds recentes do llama.cpp
    $LLAMA_BIN -m "$MODEL_PATH" --host 127.0.0.1 --port "$LLM_PORT" -c 1024 -t 4 > logs/llama_server.log 2>&1 &
    LLAMA_PID=$!
    echo "$LLAMA_PID" > data/llama.pid
    echo "[*] llama-server em inicialização (PID: $LLAMA_PID, Modelo: $MODEL_NAME)"
    
    echo -n "[*] Aguardando llama-server responder em http://127.0.0.1:${LLM_PORT}/health"
    LLAMA_READY=false
    for i in $(seq 1 15); do
        if is_llama_online; then
            LLAMA_READY=true
            break
        fi
        if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
            echo ""
            echo "[!] llama-server encerrou inesperadamente!"
            break
        fi
        sleep 1
        echo -n "."
    done
    echo ""
    
    if [ "$LLAMA_READY" == "true" ]; then
        echo "[OK] llama-server pronto e respondendo em http://127.0.0.1:${LLM_PORT}/health!"
    else
        echo "[AVISO] Falha ao conectar ao llama-server em 15s."
        if [ -f "logs/llama_server.log" ]; then
            echo "--- Conteúdo de logs/llama_server.log ---"
            tail -n 25 logs/llama_server.log
            echo "----------------------------------------"
        fi
    fi
else
    echo "[AVISO] Binário llama-server ou modelo .gguf em ./models/ não encontrado."
    echo "        O Silva Web Server será iniciado no modo simulação/fallback."
fi

# 2. Detecção automática de IP local (Wi-Fi / Hotspot)
LOCAL_IP=$(ip -4 addr show 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '127.0.0.1' | head -n 1 || true)
if [ -z "$LOCAL_IP" ]; then
    LOCAL_IP=$(ifconfig 2>/dev/null | grep -Eo 'inet (addr:)?([0-9]*\.){3}[0-9]*' | grep -Eo '([0-9]*\.){3}[0-9]*' | grep -v '127.0.0.1' | head -n 1 || true)
fi

PORT="$WEB_PORT"
echo ""
echo "========================================================"
echo "    SILVA WEB PRONTO PARA INTERAÇÃO!                    "
echo "========================================================"
echo "  • No navegador do smartphone:"
echo "    http://localhost:$PORT"
if [ -n "$LOCAL_IP" ]; then
    echo "  • No navegador do PC (mesmo Wi-Fi):"
    echo "    http://$LOCAL_IP:$PORT"
fi
echo "========================================================"
echo ""

# 3. Executa o servidor web do Silva
python3 main.py --web --port "$PORT" &
WEB_PID=$!
echo "$WEB_PID" > data/web.pid

# 4. Inicia o Modo de Voz se solicitado
if [ "$VOICE_MODE" == "true" ]; then
    echo "[*] Ativando Modo de Comando por Voz Offline (Notificação Persistente)..."
    python3 voice_assistant.py --action init >/dev/null 2>&1 &
fi

wait "$WEB_PID" || true
echo "    SILVA WEB PRONTO PARA INTERAÇÃO!                    "
echo "========================================================"
echo "  • No navegador do smartphone:"
echo "    http://localhost:$PORT"
if [ -n "$LOCAL_IP" ]; then
    echo "  • No navegador do PC (mesmo Wi-Fi):"
    echo "    http://$LOCAL_IP:$PORT"
fi
echo "========================================================"
echo ""

# 3. Executa o servidor web do Silva
python3 main.py --web --port "$PORT" &
WEB_PID=$!
echo "$WEB_PID" > data/web.pid

# 4. Inicia o Modo de Voz se solicitado
if [ "$VOICE_MODE" == "true" ]; then
    echo "[*] Ativando Modo de Comando por Voz Offline (Notificação Persistente)..."
    python3 voice_assistant.py --action init >/dev/null 2>&1 &
fi

wait "$WEB_PID" || true
