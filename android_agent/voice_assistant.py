#!/usr/bin/env python3
"""
Módulo de Assistente de Voz Offline Nativo do Silva Agent.
Utiliza o transcritor nativo do Android (termux-speech-to-text) via Termux:API,
simplificando a notificação persistente 24/7 para um fluxo de toque único com
detecção automática de fim de fala pelo SpeechRecognizer do sistema operacional.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

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
        )
    except ImportError:
        WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
        WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
        ACCESS_PIN = os.getenv("ACCESS_PIN", "1234").strip()
        SIMULATE_HARDWARE = os.getenv("SIMULATE_HARDWARE", "false").lower() in ("1", "true", "yes")
        ENABLE_VOICE_MODE = os.getenv("ENABLE_VOICE_MODE", "false").lower() in ("1", "true", "yes")
        ENABLE_VOICE_TTS = os.getenv("ENABLE_VOICE_TTS", "false").lower() in ("1", "true", "yes")


def update_voice_notification(title: str, content: str) -> bool:
    """
    Atualiza ou cria a notificação persistente 24/7 na barra de status do Termux
    com um único botão principal 'Falar' (toque único com auto-detecção de silêncio).
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
        "--button1-action", f"{py_exec} {abs_script} --action listen"
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
    """Inicializa a notificação persistente em estado pronto para toque único."""
    update_voice_notification("Silva — Pronto", "Toque em Falar para dar um comando de voz.")


def handle_action_listen():
    """
    Fluxo Único de Voz:
    1. Feedback tátil curto e notificação 'Ouvindo...'.
    2. Transcrição nativa offline do Android via termux-speech-to-text.
    3. Despacho direto para o endpoint /api/chat.
    4. Atualização da notificação e feedback por voz TTS opcional.
    """
    # 1. Feedback tátil curto (60ms) e atualização visual para escuta ativa
    if shutil.which("termux-vibrate") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(["termux-vibrate", "-d", "60"], capture_output=True, timeout=2)
        except Exception:
            pass

    update_voice_notification("Silva — Ouvindo...", "Fale seu comando agora...")

    # 2. Execução do transcritor nativo do Android com timeout de segurança (20s)
    texto_transcrito = ""
    if not SIMULATE_HARDWARE and shutil.which("termux-speech-to-text"):
        try:
            proc = subprocess.run(
                ["termux-speech-to-text"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if proc.stdout:
                texto_transcrito = proc.stdout.strip()
        except Exception as e:
            print(f"[!] Erro no transcritor de voz termux-speech-to-text: {e}")
            texto_transcrito = ""
    elif SIMULATE_HARDWARE:
        # Fallback de teste local quando simulado
        texto_transcrito = "qual o nivel da bateria"

    # 3. Limpeza e validação do texto transcrito
    texto_transcrito = texto_transcrito.strip() if texto_transcrito else ""
    if not texto_transcrito:
        update_voice_notification(
            "Silva — Pronto",
            "Nenhum comando captado. Toque em Falar para tentar novamente."
        )
        return

    # 4. Envio do texto transcrito diretamente para /api/chat
    chat_url = f"http://127.0.0.1:{WEB_PORT}/api/chat"
    headers = {"Content-Type": "application/json"}
    if ACCESS_PIN:
        headers["X-Access-Pin"] = ACCESS_PIN

    payload = json.dumps({"message": texto_transcrito}).encode("utf-8")
    resposta_curta = "Comando executado."

    try:
        req = urllib.request.Request(chat_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            msg = data.get("message", "")
            if msg:
                # Normaliza quebras de linha e limita tamanho para exibição na notificação
                clean_msg = " ".join(msg.splitlines()).strip()
                if len(clean_msg) > 90:
                    clean_msg = clean_msg[:87].rsplit(" ", 1)[0] + "..."
                resposta_curta = clean_msg
    except Exception as e:
        resposta_curta = f"Silva offline ({str(e)[:30]})"

    # 5. Atualização da notificação persistente com o resultado da execução
    content_display = f'"{texto_transcrito}" -> {resposta_curta}'
    update_voice_notification("Silva — Pronto", content_display)

    # 6. Síntese de voz TTS opcional se ativado
    if ENABLE_VOICE_TTS and shutil.which("termux-tts-speak") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(["termux-tts-speak", "-l", "pt-BR", resposta_curta], capture_output=True, timeout=10)
        except Exception:
            pass


def handle_action_stop_service():
    """Encerra o serviço de voz e remove a notificação do sistema."""
    remove_voice_notification()


def main():
    parser = argparse.ArgumentParser(description="Controlador de Voz Nativo Offline para Silva Agent")
    parser.add_argument(
        "--action",
        choices=["init", "listen", "stop-service", "status"],
        default="status",
        help="Ação a executar no assistente de voz"
    )
    args = parser.parse_args()

    if args.action == "init":
        handle_action_init()
    elif args.action == "listen":
        handle_action_listen()
    elif args.action == "stop-service":
        handle_action_stop_service()
    elif args.action == "status":
        stt_ok = bool(shutil.which("termux-speech-to-text"))
        tts_ok = bool(shutil.which("termux-tts-speak"))
        print(f"Status Silva Voice: native_stt={stt_ok}, tts={tts_ok}, voice_mode={ENABLE_VOICE_MODE}")


if __name__ == "__main__":
    main()
