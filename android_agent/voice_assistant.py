#!/usr/bin/env python3
"""
Módulo de Assistente de Voz Offline do Silva Agent.
Integra gravação de áudio via Termux, conversão com FFmpeg, transcrição local via whisper.cpp
e despacho para a API local (/api/chat), gerenciado através de notificação persistente 24/7.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Optional

# Resolução de caminhos e importação de configurações
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

try:
    from .config import (
        ACCESS_PIN,
        ENABLE_VOICE_MODE,
        ENABLE_VOICE_TTS,
        SIMULATE_HARDWARE,
        WEB_HOST,
        WEB_PORT,
        WHISPER_BIN_PATH,
        WHISPER_LANGUAGE,
        WHISPER_MODEL_PATH,
    )
except ImportError:
    try:
        from config import (
            ACCESS_PIN,
            ENABLE_VOICE_MODE,
            ENABLE_VOICE_TTS,
            SIMULATE_HARDWARE,
            WEB_HOST,
            WEB_PORT,
            WHISPER_BIN_PATH,
            WHISPER_LANGUAGE,
            WHISPER_MODEL_PATH,
        )
    except ImportError:
        WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
        WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
        ACCESS_PIN = os.getenv("ACCESS_PIN", "1234").strip()
        SIMULATE_HARDWARE = os.getenv("SIMULATE_HARDWARE", "false").lower() in ("1", "true", "yes")
        ENABLE_VOICE_MODE = os.getenv("ENABLE_VOICE_MODE", "false").lower() in ("1", "true", "yes")
        WHISPER_BIN_PATH = os.getenv("WHISPER_BIN_PATH", "").strip()
        WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", "models/ggml-base.bin").strip()
        WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt").strip()
        ENABLE_VOICE_TTS = os.getenv("ENABLE_VOICE_TTS", "false").lower() in ("1", "true", "yes")

DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = DATA_DIR / "voice_state.json"
RAW_AUDIO_FILE = DATA_DIR / "voice_raw.m4a"
WAV_AUDIO_FILE = DATA_DIR / "voice_input.wav"


def get_voice_state() -> Dict[str, any]:
    """Lê o estado atual da gravação e do serviço de voz."""
    if STATE_FILE.is_file():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"recording": False, "started_at": 0}


def set_voice_state(recording: bool, started_at: float = 0):
    """Atualiza o estado de gravação no arquivo JSON de forma segura."""
    state = {
        "recording": recording,
        "started_at": started_at if started_at else (time.time() if recording else 0)
    }
    tmp_path = STATE_FILE.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        tmp_path.replace(STATE_FILE)
    except Exception:
        pass


def clean_whisper_text(raw_text: str) -> str:
    """Limpa marcações de tempo e ruídos comuns de transcrição do Whisper."""
    if not raw_text:
        return ""
    # Remove marcações de tempo como [00:00:00.000 --> 00:00:05.000]
    t = re.sub(r"\[\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}\]", "", raw_text)
    # Remove marcações de áudio/música/silêncio
    t = re.sub(r"\[(?:m[uú]sica|risos|aplausos|ru[ií]do|som|palmas)[^\]]*\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\((?:sil[eê]ncio|inaud[ií]vel|m[uú]sica|risos)[^\)]*\)", "", t, flags=re.IGNORECASE)
    # Normaliza linhas e espaços
    lines = [line.strip() for line in t.splitlines() if line.strip()]
    cleaned = " ".join(lines).strip()
    return cleaned


def find_whisper_bin() -> str:
    """Localiza o binário de execução do whisper.cpp (whisper-cli ou main)."""
    if WHISPER_BIN_PATH:
        p = Path(WHISPER_BIN_PATH)
        if p.is_file():
            return str(p)

    candidates = [
        shutil.which("whisper-cli"),
        shutil.which("whisper"),
        shutil.which("main"),
        str(Path.home() / "whisper.cpp" / "build" / "bin" / "whisper-cli"),
        str(Path.home() / "whisper.cpp" / "main"),
        str(SCRIPT_DIR / "whisper.cpp" / "build" / "bin" / "whisper-cli"),
        str(SCRIPT_DIR / "whisper.cpp" / "main"),
        str(PROJECT_ROOT / "whisper.cpp" / "build" / "bin" / "whisper-cli"),
        str(PROJECT_ROOT / "whisper.cpp" / "main"),
        "/data/data/com.termux/files/home/whisper.cpp/build/bin/whisper-cli",
        "/data/data/com.termux/files/home/whisper.cpp/main",
        "/data/data/com.termux/files/usr/bin/whisper-cli"
    ]

    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    # Fallback padrão
    return "whisper-cli"


def find_whisper_model() -> str:
    """Localiza o modelo ggml do whisper."""
    candidates = [
        WHISPER_MODEL_PATH,
        str(SCRIPT_DIR / WHISPER_MODEL_PATH),
        str(PROJECT_ROOT / WHISPER_MODEL_PATH),
        str(SCRIPT_DIR / "models" / "ggml-base.bin"),
        str(SCRIPT_DIR / "models" / "ggml-base-q5_1.bin"),
        str(Path.home() / "whisper.cpp" / "models" / "ggml-base.bin"),
        str(Path.home() / "whisper.cpp" / "models" / "ggml-base-q5_1.bin"),
        "/data/data/com.termux/files/home/whisper.cpp/models/ggml-base.bin"
    ]

    for c in candidates:
        if c and os.path.isfile(c):
            return c

    return str(SCRIPT_DIR / "models" / "ggml-base.bin")


def update_voice_notification(title: str, content: str) -> bool:
    """
    Atualiza ou cria a notificação persistente 24/7 na barra de status do Termux
    com botões interativos 'Falar' e 'Parar'.
    """
    abs_script = str(SCRIPT_DIR / "voice_assistant.py")
    py_exec = sys.executable or "python3"

    cmd = [
        "termux-notification",
        "--id", "silva_voice",
        "--ongoing",
        "--priority", "high",
        "--title", title,
        "--content", content,
        "--button1", "Falar",
        "--button1-action", f"{py_exec} {abs_script} --action start",
        "--button2", "Parar",
        "--button2-action", f"{py_exec} {abs_script} --action stop"
    ]

    if SIMULATE_HARDWARE or not shutil.which("termux-notification"):
        print(f"[*] [Notificação Silva Voice Simulação] {title} | {content}")
        return True

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception as e:
        print(f"[!] Erro ao atualizar notificação persistente: {e}")
        return False


def remove_voice_notification() -> bool:
    """Remove a notificação persistente do Silva Voice."""
    if SIMULATE_HARDWARE or not shutil.which("termux-notification-remove"):
        print("[*] [Notificação Silva Voice Simulação] Removida.")
        return True

    try:
        res = subprocess.run(["termux-notification-remove", "silva_voice"], capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception as e:
        print(f"[!] Erro ao remover notificação: {e}")
        return False


def handle_action_init():
    """Inicializa a notificação persistente em estado pronto."""
    set_voice_state(recording=False)
    update_voice_notification("Silva — Pronto", "Toque em Falar para dar um comando de voz.")


def handle_action_start():
    """Ação do botão 'Falar': Inicia gravação de áudio com feedback tátil."""
    state = get_voice_state()
    if state.get("recording"):
        # Encerra gravação anterior órfã se existir
        if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
            subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=3)
        time.sleep(0.1)

    # Feedback háptico curto (80ms) para confirmação imediata
    if shutil.which("termux-vibrate") and not SIMULATE_HARDWARE:
        subprocess.run(["termux-vibrate", "-d", "80"], capture_output=True, timeout=2)

    # Remove gravação antiga
    if RAW_AUDIO_FILE.is_file():
        try:
            RAW_AUDIO_FILE.unlink()
        except Exception:
            pass

    # Inicia captura de áudio com limite de segurança de 60 segundos
    if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
        subprocess.run(
            ["termux-microphone-record", "-f", str(RAW_AUDIO_FILE), "-l", "60"],
            capture_output=True,
            timeout=5
        )

    set_voice_state(recording=True, started_at=time.time())
    update_voice_notification("Silva — Ouvindo...", "Fale seu comando e toque em Parar.")


def handle_action_stop():
    """Ação do botão 'Parar': Finaliza gravação, transcreve com Whisper e despacha para o Silva."""
    # 1. Encerra gravação e aguarda flush do arquivo
    if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
        subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=3)
    time.sleep(0.3)
    set_voice_state(recording=False)

    update_voice_notification("Silva — Processando...", "Transcrevendo áudio com Whisper...")

    # Em modo simulado sem gravação real, cria arquivo dummy se necessário para testes
    if not RAW_AUDIO_FILE.is_file() and SIMULATE_HARDWARE:
        RAW_AUDIO_FILE.write_bytes(b"dummy_audio")

    if not RAW_AUDIO_FILE.is_file():
        update_voice_notification("Silva — Áudio não encontrado", "Toque em Falar para tentar novamente.")
        return

    # 2. Conversão para PCM WAV 16kHz Mono via ffmpeg
    if shutil.which("ffmpeg"):
        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-i", str(RAW_AUDIO_FILE),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(WAV_AUDIO_FILE)
        ]
        subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    elif SIMULATE_HARDWARE:
        WAV_AUDIO_FILE.write_bytes(b"dummy_wav")

    # 3. Transcrição local via whisper.cpp
    whisper_bin = find_whisper_bin()
    model_path = find_whisper_model()
    transcribed_text = ""

    if (shutil.which(whisper_bin) or os.path.isfile(whisper_bin)) and os.path.isfile(model_path) and not SIMULATE_HARDWARE:
        cmd_whisper = [
            whisper_bin,
            "-m", model_path,
            "-l", WHISPER_LANGUAGE,
            "-nt",
            "-t", "4",
            "-f", str(WAV_AUDIO_FILE)
        ]
        try:
            res_w = subprocess.run(cmd_whisper, capture_output=True, text=True, timeout=30)
            transcribed_text = clean_whisper_text(res_w.stdout)
        except Exception as e:
            print(f"[!] Erro na execução do whisper: {e}")
    elif SIMULATE_HARDWARE:
        # Texto simulado caso estejamos em ambiente de teste
        transcribed_text = "qual o nivel da bateria"

    transcribed_text = clean_whisper_text(transcribed_text)

    if not transcribed_text:
        update_voice_notification("Silva — Nenhum comando detectado", "Toque em Falar para tentar novamente.")
        # Limpeza de arquivos temporários
        RAW_AUDIO_FILE.unlink(missing_ok=True)
        WAV_AUDIO_FILE.unlink(missing_ok=True)
        return

    # 4. Envio ao Silva Agent (/api/chat)
    chat_url = f"http://127.0.0.1:{WEB_PORT}/api/chat"
    headers = {"Content-Type": "application/json"}
    if ACCESS_PIN:
        headers["X-Access-Pin"] = ACCESS_PIN

    payload = json.dumps({"message": transcribed_text}).encode("utf-8")
    resposta_curta = "Comando executado."

    try:
        req = urllib.request.Request(chat_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("message", "")
            if msg:
                # Remove quebras de linha e limita tamanho para exibição na notificação
                clean_msg = " ".join(msg.splitlines()).strip()
                if len(clean_msg) > 90:
                    clean_msg = clean_msg[:87].rsplit(" ", 1)[0] + "..."
                resposta_curta = clean_msg
    except Exception as e:
        resposta_curta = f"Silva offline ({str(e)[:30]})"

    # 5. Atualização da notificação e feedback por voz TTS opcional
    content_display = f'"{transcribed_text}" -> {resposta_curta}'
    update_voice_notification("Silva — Pronto", content_display)

    if ENABLE_VOICE_TTS and shutil.which("termux-tts-speak") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(["termux-tts-speak", "-l", "pt-BR", resposta_curta], capture_output=True, timeout=10)
        except Exception:
            pass

    # 6. Limpeza estrita de privacidade
    RAW_AUDIO_FILE.unlink(missing_ok=True)
    WAV_AUDIO_FILE.unlink(missing_ok=True)


def handle_action_stop_service():
    """Encerra qualquer gravação ativa e remove a notificação do sistema."""
    if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
        subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=3)
    set_voice_state(recording=False)
    remove_voice_notification()
    RAW_AUDIO_FILE.unlink(missing_ok=True)
    WAV_AUDIO_FILE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Controlador de Comando por Voz Offline para Silva Agent")
    parser.add_argument(
        "--action",
        choices=["init", "start", "stop", "stop-service", "status"],
        default="status",
        help="Ação a executar no assistente de voz"
    )
    args = parser.parse_args()

    if args.action == "init":
        handle_action_init()
    elif args.action == "start":
        handle_action_start()
    elif args.action == "stop":
        handle_action_stop()
    elif args.action == "stop-service":
        handle_action_stop_service()
    elif args.action == "status":
        state = get_voice_state()
        print(f"Status Silva Voice: recording={state.get('recording')}, whisper={find_whisper_bin()}, model={find_whisper_model()}")


if __name__ == "__main__":
    main()
