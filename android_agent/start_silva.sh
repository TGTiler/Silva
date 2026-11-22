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

# Carrega WEB_PORT do .env (com fallback para 5000)
WEB_PORT="5000"
ENV_PATH=""
if [ -f "../.env" ]; then
    ENV_PATH="../.env"
elif [ -f "./.env" ]; then
    ENV_PATH="./.env"
elif [ -f "../.env.example" ]; then
    ENV_PATH="../.env.example"
elif [ -f "./.env.example" ]; then
    ENV_PATH="./.env.example"
fi

if [ -n "$ENV_PATH" ]; then
    PARSED_PORT=$(grep -E '^\s*WEB_PORT\s*=' "$ENV_PATH" | head -n 1 | cut -d'=' -f2 | tr -d ' "\r\n' || true)
    if [ -n "$PARSED_PORT" ]; then
        WEB_PORT="$PARSED_PORT"
    fi
fi

mkdir -p data

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
    exit 0
}
trap cleanup EXIT INT TERM

LLAMA_BIN=""
if [ -x "./llama-server" ]; then
    LLAMA_BIN="./llama-server"
elif [ -x "./llama.cpp/build/bin/llama-server" ]; then
    LLAMA_BIN="./llama.cpp/build/bin/llama-server"
elif [ -x "./llama.cpp/build/llama-server" ]; then
    LLAMA_BIN="./llama.cpp/build/llama-server"
elif command -v llama-server >/dev/null 2>&1; then
    LLAMA_BIN=$(command -v llama-server)
fi

# Localiza arquivo de modelo GGUF (prioriza silva-135m.gguf)
MODEL_PATH=""
if [ -f "./models/silva-135m.gguf" ]; then
    MODEL_PATH="./models/silva-135m.gguf"
elif [ -d "./models" ]; then
    MODEL_PATH=$(find ./models -maxdepth 1 -name "*.gguf" 2>/dev/null | head -n 1 || true)
fi

# Verifica se 127.0.0.1:8080 já está respondendo
is_llama_online() {
    if command -v curl >/dev/null 2>&1; then
        curl -s -m 1 http://127.0.0.1:8080/health >/dev/null 2>&1 || curl -s -m 1 http://127.0.0.1:8080/ >/dev/null 2>&1
    else
        python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=1)" >/dev/null 2>&1
    fi
}

# 1. Inicia o llama-server se disponível e não estiver respondendo
if is_llama_online; then
    echo "[*] llama-server já está ativo e respondendo em 127.0.0.1:8080 (reutilizando serviço existente)."
elif [ -n "$LLAMA_BIN" ] && [ -n "$MODEL_PATH" ] && [ -f "$MODEL_PATH" ]; then
    MODEL_NAME=$(basename "$MODEL_PATH")
    echo "[*] Modelo GGUF detectado e ativo: $MODEL_NAME"
    echo "    -> Caminho completo: $MODEL_PATH"
    echo "[*] Subindo llama-server na porta 8080 (background)..."
    $LLAMA_BIN -m "$MODEL_PATH" --host 127.0.0.1 --port 8080 -c 2048 -t 4 --log-disable > /dev/null 2>&1 &
    LLAMA_PID=$!
    echo "$LLAMA_PID" > data/llama.pid
    echo "[*] llama-server em execução (PID: $LLAMA_PID, Modelo: $MODEL_NAME)"
    sleep 1
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
wait "$WEB_PID" || true
