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
LLAMA_PID=""

# Função para encerrar subprocessos ao sair
cleanup() {
    echo ""
    echo "[*] Encerrando serviços do Silva..."
    if [ -n "$LLAMA_PID" ] && kill -0 "$LLAMA_PID" 2>/dev/null; then
        echo "[*] Finalizando llama-server (PID: $LLAMA_PID)..."
        kill "$LLAMA_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Inicia o llama-server se disponível
if [ -n "$LLAMA_BIN" ] && [ -n "$MODEL_PATH" ] && [ -f "$MODEL_PATH" ]; then
    MODEL_NAME=$(basename "$MODEL_PATH")
    echo "[*] Modelo GGUF detectado e ativo: $MODEL_NAME"
    echo "    -> Caminho completo: $MODEL_PATH"
    echo "[*] Subindo llama-server na porta 8080 (background)..."
    $LLAMA_BIN -m "$MODEL_PATH" --host 127.0.0.1 --port 8080 -c 2048 -t 4 --log-disable > /dev/null 2>&1 &
    LLAMA_PID=$!
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

PORT=5000
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
python3 main.py --web --port $PORT
