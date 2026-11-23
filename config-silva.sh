#!/usr/bin/env bash
# ==============================================================================
# SILVA AGENT - ASSISTENTE INTERATIVO DE CONFIGURAÇÃO (CLI)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_TARGET="$SCRIPT_DIR/android_agent/.env"
ROOT_ENV="$SCRIPT_DIR/.env"

# Cores ANSI para interface limpa no terminal
BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
CYAN="\033[36m"
RED="\033[31m"
RESET="\033[0m"

# Garante que ao menos um .env existe; caso contrário, chama install-silva.sh ou cria
if [ ! -f "$ENV_TARGET" ] && [ ! -f "$ROOT_ENV" ]; then
    echo -e "${YELLOW}[!] Arquivo .env não encontrado. Executando instalador...${RESET}"
    if [ -x "$SCRIPT_DIR/install-silva.sh" ]; then
        "$SCRIPT_DIR/install-silva.sh"
    else
        echo -e "${RED}[ERRO] install-silva.sh não encontrado.${RESET}"
        exit 1
    fi
fi

# Se um existir e o outro não, sincroniza
if [ -f "$ENV_TARGET" ] && [ ! -f "$ROOT_ENV" ]; then
    cp "$ENV_TARGET" "$ROOT_ENV"
elif [ -f "$ROOT_ENV" ] && [ ! -f "$ENV_TARGET" ]; then
    cp "$ROOT_ENV" "$ENV_TARGET"
fi

# Funções auxiliares para ler e escrever no .env
get_env_val() {
    local key="$1"
    local default_val="$2"
    python3 - << PYEOF
import os

key = "$key"
default_val = """$default_val"""
val = ""
for p in ["$ENV_TARGET", "$ROOT_ENV"]:
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                k, v = raw.split("=", 1)
                if k.strip() == key:
                    val = v.strip().strip("'\"")
                    break
    if val:
        break
print(val if val != "" else default_val)
PYEOF
}

set_env_val() {
    local key="$1"
    local val="$2"
    python3 - << PYEOF
import os

key = "$key"
val = """$val"""
files = ["$ENV_TARGET", "$ROOT_ENV"]

for p in files:
    lines = []
    found = False
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
    new_lines = []
    for line in lines:
        raw = line.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            k, _ = raw.split("=", 1)
            if k.strip() == key:
                new_lines.append(f'{key}="{val}"\n')
                found = True
                continue
        new_lines.append(line)
    if not found:
        new_lines.append(f'{key}="{val}"\n')
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
PYEOF
}

detect_llama_server() {
    local bin=""
    if command -v llama-server >/dev/null 2>&1; then
        bin="$(command -v llama-server)"
    elif [ -n "$PREFIX" ] && [ -x "$PREFIX/bin/llama-server" ]; then
        bin="$PREFIX/bin/llama-server"
    elif [ -x "$HOME/llama.cpp/build/bin/llama-server" ]; then
        bin="$HOME/llama.cpp/build/bin/llama-server"
    elif [ -x "$SCRIPT_DIR/android_agent/llama-server" ]; then
        bin="$SCRIPT_DIR/android_agent/llama-server"
    fi
    echo "$bin"
}

detect_model() {
    local search_dirs=("$SCRIPT_DIR/models" "$SCRIPT_DIR/android_agent/models" "$HOME/models" "$SCRIPT_DIR")
    for sdir in "${search_dirs[@]}"; do
        if [ -d "$sdir" ]; then
            local found
            found="$(find "$sdir" -maxdepth 2 -type f -name "*.gguf" -size +10M 2>/dev/null | head -n 1)"
            if [ -n "$found" ]; then
                echo "$found"
                return
            fi
        fi
    done
}

print_menu() {
    clear
    local current_pin
    current_pin="$(get_env_val ACCESS_PIN "1234")"
    local current_port
    current_port="$(get_env_val WEB_PORT "5000")"
    local current_tts
    current_tts="$(get_env_val ENABLE_VOICE_TTS "false")"
    local current_sim
    current_sim="$(get_env_val SIMULATE_HARDWARE "false")"
    local current_llama
    current_llama="$(get_env_val LLAMA_SERVER_BIN "auto")"
    local current_model
    current_model="$(get_env_val MODEL_PATH "nenhum")"
    local current_city
    current_city="$(get_env_val DEFAULT_CITY "Recife")"

    echo -e "${BOLD}========================================================${RESET}"
    echo -e "${BOLD}      SILVA AGENT - ASSISTENTE DE CONFIGURAÇÃO          ${RESET}"
    echo -e "${BOLD}========================================================${RESET}"
    echo ""
    echo -e "  [1] Alterar PIN de Acesso         ${CYAN}(Atual: ${current_pin:-[desativado]})${RESET}"
    echo -e "  [2] Alterar Porta Web (HTTP)      ${CYAN}(Atual: ${current_port})${RESET}"
    echo -e "  [3] Alternar TTS (Voz Falada)     ${CYAN}(Atual: ${current_tts})${RESET}"
    echo -e "  [4] Alternar Simulação Hardware   ${CYAN}(Atual: ${current_sim})${RESET}"
    echo -e "  [5] Auto-detectar llama.cpp / LLM ${CYAN}(Motor: ${current_llama##*/})${RESET}"
    echo -e "  [6] Alterar Cidade Padrão (Clima) ${CYAN}(Atual: ${current_city})${RESET}"
    echo -e "  [7] Restaurar Configurações Padrão"
    echo ""
    echo -e "  [0] Salvar e Sair"
    echo -e "${BOLD}--------------------------------------------------------${RESET}"
    echo -n "Escolha uma opção [0-7]: "
}

while true; do
    print_menu
    read -r opt
    case "$opt" in
        1)
            echo ""
            echo -e "${BOLD}--- [1] Alterar PIN de Acesso ---${RESET}"
            echo "Digite o novo PIN numérico (mínimo 4 dígitos) ou aperte ENTER para manter:"
            read -r new_pin
            if [ -n "$new_pin" ]; then
                if [[ "$new_pin" =~ ^[0-9]{4,10}$ ]]; then
                    set_env_val "ACCESS_PIN" "$new_pin"
                    echo -e "${GREEN}[OK] PIN atualizado para: $new_pin${RESET}"
                else
                    echo -e "${RED}[ERRO] O PIN deve conter entre 4 e 10 dígitos numéricos.${RESET}"
                fi
            else
                echo -e "${YELLOW}[INFO] PIN mantido inalterado.${RESET}"
            fi
            sleep 1.5
            ;;
        2)
            echo ""
            echo -e "${BOLD}--- [2] Alterar Porta do Servidor Web ---${RESET}"
            echo "Digite a nova porta HTTP (ex: 5000, 8000, 8080) [1024-65535]:"
            read -r new_port
            if [ -n "$new_port" ]; then
                if [[ "$new_port" =~ ^[0-9]+$ ]] && [ "$new_port" -ge 1024 ] && [ "$new_port" -le 65535 ]; then
                    set_env_val "WEB_PORT" "$new_port"
                    echo -e "${GREEN}[OK] Porta web atualizada para: $new_port${RESET}"
                else
                    echo -e "${RED}[ERRO] Porta inválida. Deve ser um número entre 1024 e 65535.${RESET}"
                fi
            else
                echo -e "${YELLOW}[INFO] Porta mantida inalterada.${RESET}"
            fi
            sleep 1.5
            ;;
        3)
            current_tts="$(get_env_val ENABLE_VOICE_TTS "false")"
            if [ "$current_tts" = "true" ]; then
                set_env_val "ENABLE_VOICE_TTS" "false"
                echo -e "${YELLOW}[OK] TTS (Síntese por Voz) DESATIVADO.${RESET}"
            else
                set_env_val "ENABLE_VOICE_TTS" "true"
                echo -e "${GREEN}[OK] TTS (Síntese por Voz) ATIVADO.${RESET}"
            fi
            sleep 1.2
            ;;
        4)
            current_sim="$(get_env_val SIMULATE_HARDWARE "false")"
            if [ "$current_sim" = "true" ]; then
                set_env_val "SIMULATE_HARDWARE" "false"
                echo -e "${GREEN}[OK] Modo Simulação de Hardware DESATIVADO (Usa chamadas nativas Termux:API).${RESET}"
            else
                set_env_val "SIMULATE_HARDWARE" "true"
                echo -e "${YELLOW}[OK] Modo Simulação de Hardware ATIVADO (Mock para PC/Testes).${RESET}"
            fi
            sleep 1.2
            ;;
        5)
            echo ""
            echo -e "${BOLD}--- [5] Auto-detecção de llama.cpp e Modelo GGUF ---${RESET}"
            echo "Buscando llama-server no sistema..."
            found_llama="$(detect_llama_server)"
            if [ -n "$found_llama" ]; then
                set_env_val "LLAMA_SERVER_BIN" "$found_llama"
                echo -e "  ${GREEN}[OK] llama-server encontrado:${RESET} $found_llama"
            else
                echo -e "  ${RED}[!] llama-server não localizado no PATH nem em pastas conhecidas.${RESET}"
            fi

            echo "Buscando modelos .gguf (>10MB)..."
            found_model="$(detect_model)"
            if [ -n "$found_model" ]; then
                set_env_val "MODEL_PATH" "$found_model"
                set_env_val "LLAMA_MODEL_PATH" "$found_model"
                echo -e "  ${GREEN}[OK] Modelo GGUF encontrado:${RESET} $found_model"
            else
                echo -e "  ${YELLOW}[!] Nenhum modelo .gguf encontrado nas pastas padrão (models/).${RESET}"
                echo "      Você pode colocar seu modelo .gguf na pasta 'models/' a qualquer momento."
            fi
            echo ""
            echo "Pressione ENTER para continuar..."
            read -r
            ;;
        6)
            echo ""
            echo -e "${BOLD}--- [6] Alterar Cidade Padrão para Clima ---${RESET}"
            current_city="$(get_env_val DEFAULT_CITY "Recife")"
            echo "Cidade atual: $current_city"
            echo -n "Digite o novo nome da cidade padrão: "
            read -r new_city
            if [ -n "$new_city" ]; then
                set_env_val "DEFAULT_CITY" "$new_city"
                echo -e "${GREEN}[OK] Cidade padrão definida como: $new_city${RESET}"
            else
                echo -e "${YELLOW}[INFO] Cidade padrão mantida.${RESET}"
            fi
            sleep 1.5
            ;;
        7)
            echo ""
            echo -e "${BOLD}--- [7] Restaurar Configurações Padrão ---${RESET}"
            echo -n "Tem certeza que deseja restaurar as configurações padrão? [s/N]: "
            read -r confirm
            if [[ "$confirm" =~ ^[sSyY]$ ]]; then
                set_env_val "WEB_HOST" "0.0.0.0"
                set_env_val "WEB_PORT" "5000"
                set_env_val "ENABLE_VOICE_TTS" "false"
                set_env_val "DEFAULT_CITY" "Recife"
                # Detecta Termux vs Desktop para SIMULATE_HARDWARE
                if [ -n "$PREFIX" ] && [[ "$PREFIX" == *"com.termux"* ]]; then
                    set_env_val "SIMULATE_HARDWARE" "false"
                else
                    set_env_val "SIMULATE_HARDWARE" "true"
                fi
                echo -e "${GREEN}[OK] Configurações padrão restauradas.${RESET}"
            else
                echo -e "${YELLOW}[INFO] Operação cancelada.${RESET}"
            fi
            sleep 1.5
            ;;
        0)
            echo ""
            echo -e "${GREEN}[OK] Configurações salvas em .env com sucesso!${RESET}"
            echo -e "Para iniciar o Silva, execute: ${BOLD}./start_silva.sh${RESET}"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}[!] Opção inválida. Digite um número de 0 a 7.${RESET}"
            sleep 1.2
            ;;
    esac
done
