#!/usr/bin/env bash
# Script de automação e setup do ambiente Termux para o Silva Agent
set -e

echo "========================================================"
echo "    SILVA AGENT — Setup Automatizado no Termux Android   "
echo "========================================================"

# 1. Atualização dos repositórios do Termux
echo "[1/4] Atualizando repositórios do Termux..."
pkg update -y || apt-get update -y

# 2. Instalação das dependências e do llama-cpp oficial
echo "[2/4] Instalando dependências (python, termux-api, ffmpeg, llama-cpp)..."
pkg install -y python termux-api ffmpeg || apt-get install -y python termux-api ffmpeg

# Tenta instalar pacote oficial do llama-cpp do repositório Termux
if pkg install -y llama-cpp 2>/dev/null || apt-get install -y llama-cpp 2>/dev/null; then
    echo "[OK] Pacote oficial llama-cpp instalado com sucesso!"
else
    echo "[*] Pacote pré-compilado não disponível, compilando via CMake/Clang..."
    pkg install -y clang cmake git libopenblas pkg-config make
    if [ ! -d "llama.cpp" ]; then
        git clone --depth 1 https://github.com/ggml-org/llama.cpp.git
    fi
    cd llama.cpp
    cmake -B build -DGGML_NATIVE=ON -DGGML_OPENBLAS=ON -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target llama-server -j4
    cd ..
    if [ -f "llama.cpp/build/bin/llama-server" ]; then
        cp llama.cpp/build/bin/llama-server ./llama-server
    elif [ -f "llama.cpp/build/llama-server" ]; then
        cp llama.cpp/build/llama-server ./llama-server
    fi
fi

# Bloco Opcional: Instalação do whisper.cpp para comando por voz offline
INSTALL_VOICE=false
for arg in "$@"; do
    if [ "$arg" == "--with-voice" ]; then
        INSTALL_VOICE=true
    fi
done

if [ "$INSTALL_VOICE" != "true" ] && [ -t 0 ]; then
    echo ""
    read -p "Deseja instalar o suporte opcional de comando por voz offline (whisper.cpp)? [s/N]: " choice || true
    if [[ "$choice" =~ ^[sSyY] ]]; then
        INSTALL_VOICE=true
    fi
fi

if [ "$INSTALL_VOICE" == "true" ]; then
    echo "[*] Configurando whisper.cpp para comando por voz offline..."
    pkg install -y clang cmake git make
    WHISPER_DIR="$HOME/whisper.cpp"
    if [ ! -d "$WHISPER_DIR" ]; then
        git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
    fi
    cd "$WHISPER_DIR"
    cmake -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build --target whisper-cli -j4 || cmake --build build --target main -j4 || make -j4
    cd - >/dev/null

    echo "[*] Baixando modelo ggml-base.bin (~142MB)..."
    mkdir -p models
    if [ ! -f "models/ggml-base.bin" ]; then
        if [ -f "$WHISPER_DIR/models/download-ggml-model.sh" ]; then
            bash "$WHISPER_DIR/models/download-ggml-model.sh" base
            cp "$WHISPER_DIR/models/ggml-base.bin" models/ggml-base.bin 2>/dev/null || true
        else
            curl -L -o models/ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
        fi
    fi
    echo "[OK] whisper.cpp e modelo base instalados!"
fi

# 3. Criação de pastas necessárias
echo "[3/4] Configurando pastas de trabalho..."
mkdir -p captures
mkdir -p models

# 4. Permissões de execução
echo "[4/4] Ajustando permissões..."
chmod +x setup_termux.sh start_silva.sh main.py voice_assistant.py 2>/dev/null || true

echo "========================================================"
echo " [OK] Setup do Silva no Termux concluído com sucesso!   "
echo "========================================================"
