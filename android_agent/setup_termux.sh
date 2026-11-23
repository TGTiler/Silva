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

# Instalação opcional/recomendada do Vosk e modelo offline PT-BR
echo "[*] Verificando Vosk e modelo de voz offline PT-BR..."
pkg install -y python-pip unzip curl || apt-get install -y python3-pip unzip curl || true
pip install --upgrade vosk 2>/dev/null || true

mkdir -p models
if [ ! -d "models/vosk-model-small-pt-0.3" ]; then
    echo "[*] Baixando modelo vosk-model-small-pt-0.3 (~31MB)..."
    curl -L -o models/vosk-model-small-pt-0.3.zip https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip
    unzip -q models/vosk-model-small-pt-0.3.zip -d models/
    rm -f models/vosk-model-small-pt-0.3.zip
    echo "[OK] Modelo Vosk instalado com sucesso!"
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
