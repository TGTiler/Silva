#!/usr/bin/env bash
# ==============================================================================
# SILVA AGENT - INSTALADOR COMPLETO E IDEMPOTENTE (PLUG & PLAY)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================"
echo "         SILVA AGENT - INSTALAÇÃO PLUG & PLAY           "
echo "========================================================"
echo ""

# ------------------------------------------------------------------------------
# [1/5] Detecção de Ambiente e Pacotes Base
# ------------------------------------------------------------------------------
echo "[1/5] Verificando ambiente e instalando pacotes base..."

IS_TERMUX=false
if [ -n "$PREFIX" ] && [[ "$PREFIX" == *"com.termux"* ]]; then
    IS_TERMUX=true
elif [ -d "/data/data/com.termux" ]; then
    IS_TERMUX=true
elif command -v termux-info >/dev/null 2>&1; then
    IS_TERMUX=true
fi

if [ "$IS_TERMUX" = "true" ]; then
    echo "      -> Ambiente Android Termux detectado."
    echo "      -> Atualizando repositórios e instalando dependências essenciais..."
    pkg update -y
    pkg install -y python termux-api curl git cmake clang android-tools
    echo "      [OK] Pacotes base instalados com sucesso no Termux."
else
    echo "      -> Ambiente Linux Desktop/Servidor detectado."
    for cmd in python3 curl git; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            echo "      [!] Aviso: '$cmd' não encontrado no PATH do sistema."
            echo "          Instale via: sudo apt install -y python3 curl git (ou equivalente)."
        fi
    done
    echo "      [OK] Verificação de ambiente concluída."
fi

# ------------------------------------------------------------------------------
# [2/5] Detecção ou Instalação do Motor llama.cpp (llama-server)
# ------------------------------------------------------------------------------
echo ""
echo "[2/5] Configurando motor de inferência local (llama-server)..."

LLAMA_SERVER_BIN=""

# Verifica se já existe no PATH ou em locais padrão
if command -v llama-server >/dev/null 2>&1; then
    LLAMA_SERVER_BIN="$(command -v llama-server)"
elif [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/llama-server" ]; then
    LLAMA_SERVER_BIN="$PREFIX/bin/llama-server"
elif [ -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
    LLAMA_SERVER_BIN="$HOME/llama.cpp/build/bin/llama-server"
elif [ -x "$SCRIPT_DIR/android_agent/llama-server" ]; then
    LLAMA_SERVER_BIN="$SCRIPT_DIR/android_agent/llama-server"
fi

# No Termux, tenta instalar o pacote pré-compilado oficial se não existir
if [ -z "$LLAMA_SERVER_BIN" ] && [ "$IS_TERMUX" = "true" ]; then
    echo "      -> Tentando instalar pacote pré-compilado llama-cpp no Termux..."
    pkg install -y llama-cpp >/dev/null 2>&1 || true
    if command -v llama-server >/dev/null 2>&1; then
        LLAMA_SERVER_BIN="$(command -v llama-server)"
    elif [ -x "$PREFIX/bin/llama-server" ]; then
        LLAMA_SERVER_BIN="$PREFIX/bin/llama-server"
    fi
fi

# Fallback: Se não encontrou binário pré-compilado, compila apenas o llama-server
if [ -z "$LLAMA_SERVER_BIN" ]; then
    echo "      -> Binário pré-compilado não disponível. Compilando llama-server..."
    LLAMA_REPO_DIR="$HOME/llama.cpp"
    if [ ! -d "$LLAMA_REPO_DIR" ]; then
        echo "      -> Clonando repositório oficial do llama.cpp em $LLAMA_REPO_DIR..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_REPO_DIR"
    fi
    echo "      -> Gerando build com CMake..."
    cmake -B "$LLAMA_REPO_DIR/build" -S "$LLAMA_REPO_DIR" -DGGML_OPENMP=OFF -DLLAMA_CURL=OFF
    echo "      -> Compilando alvo llama-server (4 threads)..."
    cmake --build "$LLAMA_REPO_DIR/build" --target llama-server -j4
    if [ -x "$LLAMA_REPO_DIR/build/bin/llama-server" ]; then
        LLAMA_SERVER_BIN="$LLAMA_REPO_DIR/build/bin/llama-server"
    fi
fi

if [ -n "$LLAMA_SERVER_BIN" ]; then
    # Converte para caminho absoluto
    LLAMA_SERVER_BIN="$(readlink -f "$LLAMA_SERVER_BIN" 2>/dev/null || echo "$LLAMA_SERVER_BIN")"
    echo "      [OK] llama-server pronto: $LLAMA_SERVER_BIN"
else
    echo "      [AVISO] llama-server não pôde ser instalado automaticamente."
    echo "              O Silva Agent rodará no modo Fallback Inteligente (sem perda de ferramentas)."
fi

# ------------------------------------------------------------------------------
# [3/5] Estrutura de Diretórios e Modelo GGUF
# ------------------------------------------------------------------------------
echo ""
echo "[3/5] Organizando diretórios de dados e modelo GGUF..."

mkdir -p "$SCRIPT_DIR/android_agent/models"
mkdir -p "$SCRIPT_DIR/android_agent/data"
mkdir -p "$SCRIPT_DIR/android_agent/logs"
mkdir -p "$SCRIPT_DIR/android_agent/captures"

MODEL_PATH=""
# Busca modelo GGUF existente (> 10 MB)
for candidate in \
    "$SCRIPT_DIR/android_agent/models"/*.gguf \
    "$SCRIPT_DIR/models"/*.gguf \
    "$HOME/silva-agent/android_agent/models"/*.gguf; do
    if [ -f "$candidate" ]; then
        SIZE_BYTES=$(wc -c < "$candidate" 2>/dev/null || stat -c%s "$candidate" 2>/dev/null || echo 0)
        if [ "$SIZE_BYTES" -gt 10000000 ]; then
            MODEL_PATH="$(readlink -f "$candidate" 2>/dev/null || echo "$candidate")"
            break
        fi
    fi
done

if [ -n "$MODEL_PATH" ]; then
    echo "      [OK] Modelo GGUF detectado: $(basename "$MODEL_PATH")"
    echo "           Caminho: $MODEL_PATH"
elif [ -n "$MODEL_DOWNLOAD_URL" ]; then
    echo "      -> Baixando modelo GGUF a partir de \$MODEL_DOWNLOAD_URL..."
    TARGET_MODEL="$SCRIPT_DIR/android_agent/models/silva-135m.gguf"
    curl -L -o "$TARGET_MODEL" "$MODEL_DOWNLOAD_URL"
    MODEL_PATH="$(readlink -f "$TARGET_MODEL" 2>/dev/null || echo "$TARGET_MODEL")"
    echo "      [OK] Modelo baixado com sucesso: $MODEL_PATH"
else
    echo "      [AVISO] Nenhum modelo .gguf (> 10MB) encontrado em android_agent/models/."
    echo "              Para ativar o LLM neural offline, coloque 'silva-135m.gguf' em:"
    echo "              $SCRIPT_DIR/android_agent/models/silva-135m.gguf"
fi

# ------------------------------------------------------------------------------
# [4/5] Geração Segura do Arquivo de Configuração (.env)
# ------------------------------------------------------------------------------
echo ""
echo "[4/5] Configurando variáveis de ambiente (android_agent/.env)..."

ENV_TARGET="$SCRIPT_DIR/android_agent/.env"
ROOT_ENV="$SCRIPT_DIR/.env"
ENV_TEMPLATE="$SCRIPT_DIR/android_agent/.env.example"
[ ! -f "$ENV_TEMPLATE" ] && ENV_TEMPLATE="$SCRIPT_DIR/.env.example"

# Gera PIN numérico seguro de 6 dígitos
GEN_PIN=$(python3 -c "import secrets; print(f'{secrets.randbelow(900000) + 100000}')" 2>/dev/null || shuf -i 100000-999999 -n 1 2>/dev/null || echo "123456")

if [ ! -f "$ENV_TARGET" ]; then
    if [ -f "$ENV_TEMPLATE" ]; then
        cp "$ENV_TEMPLATE" "$ENV_TARGET"
    else
        cat << 'EOF' > "$ENV_TARGET"
# Configurações do Silva Agent
WEB_HOST=0.0.0.0
WEB_PORT=5000
ACCESS_PIN=123456

# Conexão Local com llama-server
LLAMA_SERVER_URL=http://127.0.0.1:8080
LLM_TIMEOUT_SECONDS=15
LLAMA_SERVER_BIN=""
MODEL_PATH=""

# Simulação e Recursos
SIMULATE_HARDWARE=false
ENABLE_VOICE_TTS=false
DEFAULT_CITY="Recife"
EOF
    fi

    # Aplica valores detectados de forma segura
    python3 - << PYEOF
import os

env_path = "$ENV_TARGET"
pin = "$GEN_PIN"
llama_bin = "$LLAMA_SERVER_BIN"
model_path = "$MODEL_PATH"
is_termux = "$IS_TERMUX" == "true"

with open(env_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
keys_seen = set()

for line in lines:
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        new_lines.append(line)
        continue
    k, v = raw.split("=", 1)
    k = k.strip()
    keys_seen.add(k)
    if k == "ACCESS_PIN":
        new_lines.append(f'ACCESS_PIN="{pin}"\n')
    elif k == "LLAMA_SERVER_BIN" and llama_bin:
        new_lines.append(f'LLAMA_SERVER_BIN="{llama_bin}"\n')
    elif k in ("MODEL_PATH", "LLAMA_MODEL_PATH") and model_path:
        new_lines.append(f'{k}="{model_path}"\n')
    elif k == "SIMULATE_HARDWARE":
        val = "false" if is_termux else "true"
        new_lines.append(f'SIMULATE_HARDWARE={val}\n')
    else:
        new_lines.append(line)

with open(env_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
PYEOF
    echo "      [OK] Novo arquivo de ambiente gerado com PIN seguro: $GEN_PIN"
else
    echo "      -> Arquivo android_agent/.env já existe (mantendo configurações existentes)."
fi

# Sincroniza .env da raiz com android_agent/.env
cp "$ENV_TARGET" "$ROOT_ENV" 2>/dev/null || true

# ------------------------------------------------------------------------------
# [5/5] Permissões e Finalização
# ------------------------------------------------------------------------------
echo ""
echo "[5/5] Ajustando permissões de execução dos scripts principais..."

chmod +x "$SCRIPT_DIR/install-silva.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/config-silva.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/start_silva.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/android_agent/start_silva.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/android_agent/main.py" 2>/dev/null || true

echo "      [OK] Permissões concedidas com sucesso."
echo ""
echo "========================================================"
echo "         INSTALAÇÃO CONCLUÍDA COM SUCESSO!              "
echo "========================================================"
echo "  Próximos passos disponíveis na raiz do projeto:"
echo ""
echo "  1. Iniciar o Silva agora:"
echo "     ./start_silva.sh"
echo ""
echo "  2. Ajustar configurações (PIN, porta, cidade, etc.):"
echo "     ./config-silva.sh"
echo "========================================================"
