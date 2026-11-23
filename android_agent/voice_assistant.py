#!/usr/bin/env python3
"""
Módulo de Assistente de Voz Offline do Silva Agent utilizando Vosk (vosk-model-small-pt-0.3).
Executa gravação com cancelamento manual de ruído (Falar / Parar) através de notificação
persistente 24/7 no Termux, conversão de áudio via FFmpeg, reconhecimento local com
gramática prioritária das 39 ferramentas do Silva e despacho direto para a API local (/api/chat).
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
import wave
from pathlib import Path
from typing import Dict, List, Optional

# Resolução de caminhos e importação de configurações
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

try:
    from .config import (
        ACCESS_PIN,
        ENABLE_VOICE_MODE,
        ENABLE_VOICE_TTS,
        SIMULATE_HARDWARE,
        VOSK_MODEL_PATH,
        VOSK_USE_GRAMMAR,
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
            VOSK_MODEL_PATH,
            VOSK_USE_GRAMMAR,
            WEB_HOST,
            WEB_PORT,
        )
    except ImportError:
        WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
        WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
        ACCESS_PIN = os.getenv("ACCESS_PIN", "1234").strip()
        SIMULATE_HARDWARE = os.getenv("SIMULATE_HARDWARE", "false").lower() in ("1", "true", "yes")
        ENABLE_VOICE_MODE = os.getenv("ENABLE_VOICE_MODE", "false").lower() in ("1", "true", "yes")
        VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-pt-0.3").strip()
        VOSK_USE_GRAMMAR = os.getenv("VOSK_USE_GRAMMAR", "false").lower() in ("1", "true", "yes")
        ENABLE_VOICE_TTS = os.getenv("ENABLE_VOICE_TTS", "false").lower() in ("1", "true", "yes")

# Fallback seguro para vosk em ambientes desktop sem o pacote instalado
try:
    import vosk
    from vosk import KaldiRecognizer, Model, SetLogLevel
    HAS_VOSK = True
    try:
        SetLogLevel(-1)
    except Exception:
        pass
except ImportError:
    vosk = None
    KaldiRecognizer = None
    Model = None
    SetLogLevel = None
    HAS_VOSK = False

DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = DATA_DIR / "voice_state.json"
RAW_AUDIO_FILE = DATA_DIR / "voice_raw.m4a"
WAV_AUDIO_FILE = DATA_DIR / "voice_input.wav"

# ==============================================================================
# Vocabulário / Gramática Inteligente do Silva (39 Tools + Apps + Numerais)
# ==============================================================================
SILVA_VOSK_GRAMMAR: List[str] = [
    # Artigos, contrações, preposições e conectivos do português
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
    "em", "num", "numa", "por", "para", "pro", "pra",
    "com", "sem", "e", "ou", "que", "me", "se", "te",
    "ao", "aos", "à", "às",

    # Ativação e cortesia
    "silva", "ei silva", "por favor", "agora", "hoje", "amanha", "depois de amanha",
    
    # Verbos de ação
    "abra", "abrir", "abre", "liga", "ligar", "desliga", "desligar",
    "ativa", "ativar", "desativa", "desativar", "tira", "tirar", "grava", "gravar",
    "manda", "mandar", "envia", "enviar", "calcula", "calcular",
    "pesquisa", "pesquisar", "busca", "buscar", "conecta", "conectar", "conecte-se",
    "escaneia", "escanear", "lista", "listar", "mostra", "mostrar",
    "lembra", "lembrar", "anota", "anotar", "qual", "quais", "quanto",
    "pausa", "pausar", "continua", "tocar", "proxima", "anterior",
    "aumenta", "aumente", "diminui", "baixa", "instala", "chama", "pede",
    "agenda", "cancela", "vibra",
    
    # Hardware, sensores e utilitários (39 tools)
    "bateria", "sms", "mensagem", "foto", "selfie", "camera", "frontal", "traseira",
    "print", "tela", "video", "localizacao", "gps", "mapa", "clima", "tempo",
    "previsao", "google", "lanterna", "nao perturbe", "silencioso", "vibrar",
    "area de transferencia", "copiar", "colar", "piada", "alarme", "despertador",
    "evento", "compromisso", "nota", "memoria", "senha", "notificacoes", "volume",
    "brilho", "total", "maximo", "minimo", "timer", "cronometro", "minutos", "horas",
    "meia hora", "raiz quadrada", "seno", "cosseno", "fatorial", "uber",
    "noventa e nove", "ifood", "play store", "musica", "midia", "wifi", "wi-fi",
    "rede", "redes", "ip", "funcoes", "comandos", "ajuda",
    
    # Apps populares
    "youtube", "whatsapp", "instagram", "telegram", "spotify", "tiktok", "chrome",
    "calculadora", "configuracoes", "relógio", "galeria",
    
    # Numerais PT-BR
    "zero", "um", "uma", "dois", "duas", "tres", "quatro", "cinco", "seis", "meia",
    "sete", "oito", "nove", "dez", "onze", "doze", "quinze", "vinte", "trinta",
    "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa", "cem",
    "cento", "duzentos", "trezentos", "quinhentos", "mil",
    
    # Token aberto para nomes de contatos, termos de busca e destinos abertos
    "[unk]"
]


def _clean_vosk_text(raw_text: str) -> str:
    """Limpa marcações de palavras desconhecidas como [unk] e normaliza espaços."""
    if not raw_text:
        return ""
    t = re.sub(r"\[unk\]|<unk>", " ", raw_text, flags=re.IGNORECASE)
    cleaned = " ".join(t.split()).strip()
    return cleaned


def _postprocess_transcript(text: str) -> str:
    """Corrige confusões fonéticas comuns do Vosk PT-BR em nomes de apps e termos frequentes."""
    if not text:
        return ""
    t = text.lower()
    replacements = [
        (r"\b(you\s*tube|io\s*tube|iutube)\b", "youtube"),
        (r"\b(whats\s*app|uatisapi|what\s*zap|uatsap|uats\s*app)\b", "whatsapp"),
        (r"\b(instagran|insta\s*gram)\b", "instagram"),
        (r"\b(uai\s*fai|wi\s*fi|way\s*fay)\b", "wifi"),
        (r"\b(tik\s*tok)\b", "tiktok"),
        (r"\b(i\s*food)\b", "ifood"),
        (r"\b(play\s*store)\b", "play store"),
    ]
    for pattern, rep in replacements:
        t = re.sub(pattern, rep, t, flags=re.IGNORECASE)
    return " ".join(t.split()).strip()


def get_voice_state() -> Dict[str, any]:
    """Lê o estado atual do assistente de voz a partir de arquivo JSON."""
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


def find_vosk_model() -> str:
    """Localiza o diretório do modelo Vosk em caminhos relativos ou no Termux."""
    candidates = [
        VOSK_MODEL_PATH,
        str(SCRIPT_DIR / VOSK_MODEL_PATH),
        str(PROJECT_ROOT / VOSK_MODEL_PATH),
        str(SCRIPT_DIR / "models" / "vosk-model-small-pt-0.3"),
        str(PROJECT_ROOT / "models" / "vosk-model-small-pt-0.3"),
        str(Path.home() / "silva-agent" / "android_agent" / "models" / "vosk-model-small-pt-0.3"),
        "/data/data/com.termux/files/home/silva-agent/android_agent/models/vosk-model-small-pt-0.3",
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return str(SCRIPT_DIR / "models" / "vosk-model-small-pt-0.3")


def update_voice_notification(title: str, content: str) -> bool:
    """
    Atualiza ou cria a notificação persistente 24/7 na barra de status do Termux
    com botões interativos 'Falar' (--action start) e 'Parar' (--action stop).
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
    """
    Ação do botão 'Falar':
    - Encerra gravação anterior órfã se existir.
    - Vibração háptica curta de 70ms.
    - Inicia gravação com limite de 60s via termux-microphone-record.
    - Atualiza notificação para 'Silva — Ouvindo...'.
    """
    state = get_voice_state()
    if state.get("recording"):
        if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
            try:
                subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=3)
            except Exception:
                pass
        time.sleep(0.1)

    # Feedback háptico de 70ms
    if shutil.which("termux-vibrate") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(["termux-vibrate", "-d", "70"], capture_output=True, timeout=2)
        except Exception:
            pass

    # Remove gravação antiga se houver
    RAW_AUDIO_FILE.unlink(missing_ok=True)
    WAV_AUDIO_FILE.unlink(missing_ok=True)

    if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(
                ["termux-microphone-record", "-f", str(RAW_AUDIO_FILE), "-e", "aac", "-r", "16000", "-b", "64000", "-l", "60"],
                capture_output=True,
                timeout=5
            )
        except Exception as e:
            print(f"[!] Erro ao iniciar termux-microphone-record: {e}")

    set_voice_state(recording=True, started_at=time.time())
    update_voice_notification("Silva — Ouvindo...", "Fale seu comando e toque em Parar.")


def handle_action_stop():
    """
    Ação do botão 'Parar':
    - Encerra gravação.
    - Converte m4a para WAV 16kHz mono via ffmpeg.
    - Transcreve áudio com Vosk e gramática prioritária das 39 tools.
    - Envia para /api/chat e atualiza notificação.
    - Limpa arquivos temporários no bloco finally.
    """
    # 1. Encerra gravação e aguarda flush de disco
    if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=3)
        except Exception:
            pass
    time.sleep(0.25)
    set_voice_state(recording=False)

    update_voice_notification("Silva — Transcrevendo...", "Processando áudio com Vosk...")

    try:
        # Em modo simulado sem gravação real, cria arquivo dummy se necessário para testes
        if not RAW_AUDIO_FILE.is_file() and SIMULATE_HARDWARE:
            RAW_AUDIO_FILE.write_bytes(b"dummy_raw_audio")

        if not RAW_AUDIO_FILE.is_file():
            update_voice_notification("Silva — Pronto", "Nenhum áudio gravado. Toque em Falar.")
            return

        # 2. Converte para PCM WAV 16kHz Mono via FFmpeg com filtro dynaudnorm/highpass
        if shutil.which("ffmpeg"):
            cmd_ffmpeg = [
                "ffmpeg", "-y",
                "-i", str(RAW_AUDIO_FILE),
                "-ar", "16000",
                "-ac", "1",
                "-af", "highpass=f=80,dynaudnorm",
                "-c:a", "pcm_s16le",
                str(WAV_AUDIO_FILE)
            ]
            subprocess.run(cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        elif SIMULATE_HARDWARE:
            WAV_AUDIO_FILE.write_bytes(b"dummy_wav_audio")

        # 3. Transcrição com Vosk
        transcribed_text = ""
        model_dir = find_vosk_model()

        if HAS_VOSK and (os.path.isdir(model_dir) or SIMULATE_HARDWARE):
            try:
                model = Model(model_dir)
                if WAV_AUDIO_FILE.is_file():
                    with wave.open(str(WAV_AUDIO_FILE), "rb") as wf:
                        if VOSK_USE_GRAMMAR:
                            grammar_json = json.dumps(SILVA_VOSK_GRAMMAR, ensure_ascii=False)
                            rec = KaldiRecognizer(model, wf.getframerate(), grammar_json)
                        else:
                            rec = KaldiRecognizer(model, wf.getframerate())
                        while True:
                            data = wf.readframes(4000)
                            if len(data) == 0:
                                break
                            rec.AcceptWaveform(data)
                        res = json.loads(rec.FinalResult())
                        transcribed_text = res.get("text", "")
            except Exception as e:
                print(f"[!] Erro no reconhecimento Vosk: {e}")
        elif SIMULATE_HARDWARE:
            transcribed_text = "abra o youtube"

        transcribed_text = _clean_vosk_text(transcribed_text)
        transcribed_text = _postprocess_transcript(transcribed_text)

        if not transcribed_text:
            update_voice_notification("Silva — Pronto", "Nenhuma fala reconhecida. Toque em Falar.")
            return

        # 4. Envio ao endpoint /api/chat do Silva
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

    finally:
        # 6. Limpeza garantida de arquivos temporários e atualização de estado
        set_voice_state(recording=False)
        RAW_AUDIO_FILE.unlink(missing_ok=True)
        WAV_AUDIO_FILE.unlink(missing_ok=True)


def handle_action_stop_service():
    """Encerra qualquer gravação ativa e remove a notificação do sistema."""
    if shutil.which("termux-microphone-record") and not SIMULATE_HARDWARE:
        try:
            subprocess.run(["termux-microphone-record", "-q"], capture_output=True, timeout=3)
        except Exception:
            pass
    set_voice_state(recording=False)
    remove_voice_notification()
    RAW_AUDIO_FILE.unlink(missing_ok=True)
    WAV_AUDIO_FILE.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Assistente de Voz Offline Vosk para Silva Agent")
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
        model_path = find_vosk_model()
        model_exists = os.path.isdir(model_path)
        print(f"Status Silva Voice Vosk: recording={state.get('recording')}, has_vosk={HAS_VOSK}, model={model_path} (exists={model_exists})")


if __name__ == "__main__":
    main()
