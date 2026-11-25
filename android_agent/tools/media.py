"""
Módulo Mídia do Silva: Foto, Screenshot, Vídeo e Controle de Mídia.
"""

import shlex
import shutil
import subprocess
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .core import (
    CAPTURES_DIR,
    SIMULATE_HARDWARE,
    _FILE_LOCK,
    _run_termux_cmd,
    _exec_android_intent,
)
from .adb_bridge import ensure_adb_connected, pull_adb_file, run_adb_shell
from .memory_schedule import _get_memory_db

def take_photo(camera_id: int = 0) -> Dict[str, Any]:
    """Captura uma foto e salva no diretório de capturas."""
    cam_id = 0 if camera_id not in (0, 1) else camera_id
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"capture_{timestamp}.jpg"
    file_path = CAPTURES_DIR / filename
    rel_url = f"/captures/{filename}"

    if SIMULATE_HARDWARE:
        # Gera uma imagem JPEG mínima válida (1x1 ou header JPEG básico) para visualização offline
        # Assinatura binária simples de JPEG 1x1 pixel
        jpeg_1x1 = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06"
            b"\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14"
            b"\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00"
            b"\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01"
            b"\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda"
            b"\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        )
        file_path.write_bytes(jpeg_1x1)
        return {
            "status": "ok",
            "message": f"Silva: Foto capturada pela câmera {cam_id}. [Simulado]",
            "image_url": rel_url,
            "data": {"file_path": str(file_path), "camera_id": cam_id}
        }

    try:
        res = _run_termux_cmd(["termux-camera-photo", "-c", str(cam_id), str(file_path)], timeout=15)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao acionar câmera: {res.stderr.strip()}"}

        cam_label = "frontal (selfie)" if cam_id == 1 else "traseira"
        return {
            "status": "ok",
            "message": f"Silva: Foto capturada com a câmera {cam_label}.",
            "image_url": rel_url,
            "data": {"file_path": str(file_path), "camera_id": cam_id}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro na captura de imagem: {str(e)}"}


def _is_valid_png(path: Path) -> bool:
    """Verifica se o arquivo existe, tem tamanho superior a 10 KB e inicia com cabeçalho PNG válido."""
    try:
        if path.is_file() and path.stat().st_size > 10 * 1024:
            with open(path, "rb") as f:
                header = f.read(4)
                return header == b"\x89PNG"
    except Exception:
        pass
    return False


def take_screenshot() -> Dict[str, Any]:
    """Captura um print da tela do smartphone e salva no dispositivo."""
    ts = int(time.time())
    filename = f"screen_{ts}.png"
    output_path = CAPTURES_DIR / filename
    rel_url = f"/captures/{filename}"

    if SIMULATE_HARDWARE:
        # Gera uma imagem representativa de screenshot no modo simulado
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (360, 640), color=(18, 16, 28))
            draw = ImageDraw.Draw(img)
            draw.rectangle([(20, 40), (340, 100)], fill=(37, 32, 56), outline=(123, 31, 162), width=2)
            draw.text((40, 60), "Silva — Print Simulado", fill=(241, 241, 245))
            draw.rectangle([(20, 120), (340, 580)], fill=(24, 21, 36))
            draw.text((40, 200), f"Capturado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", fill=(155, 152, 171))
            img.save(output_path, "PNG")
        except Exception:
            png_minimal = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            output_path.write_bytes(png_minimal)

        return {
            "status": "ok",
            "message": "Silva: Print da tela capturado.",
            "image_url": rel_url,
            "data": {"file_path": str(output_path), "method": "simulated"}
        }

    try:
        # Método 0 — Ponte ADB Local privilegiada (screencap -> pull -> validação PNG)
        if ensure_adb_connected():
            remote_tmp = f"/data/local/tmp/{filename}"
            ok_cap, _ = run_adb_shell(["screencap", "-p", remote_tmp], timeout=8.0)
            if ok_cap and pull_adb_file(remote_tmp, output_path, timeout=8.0):
                run_adb_shell(["rm", "-f", remote_tmp], timeout=3.0)
                if _is_valid_png(output_path):
                    return {
                        "status": "ok",
                        "message": "Silva: Print da tela capturado.",
                        "image_url": rel_url,
                        "data": {"file_path": str(output_path), "method": "adb"}
                    }

        # Método 1 — ADB Local (adb exec-out screencap -p)
        adb_bin = shutil.which("adb")
        if adb_bin:
            try:
                proc_devices = subprocess.run([adb_bin, "devices"], capture_output=True, text=True, timeout=3)
                device_lines = [l.strip() for l in proc_devices.stdout.splitlines() if "\tdevice" in l]
                if device_lines:
                    proc_cap = subprocess.run([adb_bin, "exec-out", "screencap", "-p"], capture_output=True, timeout=8)
                    if proc_cap.stdout and len(proc_cap.stdout) > 10 * 1024 and proc_cap.stdout[:4] == b"\x89PNG":
                        output_path.write_bytes(proc_cap.stdout)
                        if _is_valid_png(output_path):
                            return {
                                "status": "ok",
                                "message": "Silva: Print da tela capturado.",
                                "image_url": rel_url,
                                "data": {"file_path": str(output_path), "method": "adb_local"}
                            }
            except Exception:
                pass

        # Método 2 — Shizuku (rish -c "screencap -p")
        rish_bin = shutil.which("rish")
        if rish_bin:
            try:
                proc_rish = subprocess.run([rish_bin, "-c", "screencap -p"], capture_output=True, timeout=8)
                if proc_rish.stdout and len(proc_rish.stdout) > 10 * 1024 and proc_rish.stdout[:4] == b"\x89PNG":
                    output_path.write_bytes(proc_rish.stdout)
                    if _is_valid_png(output_path):
                        return {
                            "status": "ok",
                            "message": "Silva: Print da tela capturado.",
                            "image_url": rel_url,
                            "data": {"file_path": str(output_path), "method": "rish"}
                        }
            except Exception:
                pass

        # Método 3 — Fallback direto (screencap -p e input keyevent 120)
        try:
            temp_sdcard = Path("/sdcard/Download") / f"temp_{filename}"
            _run_termux_cmd(["screencap", "-p", str(output_path)], timeout=8)
            if not _is_valid_png(output_path):
                _run_termux_cmd(["screencap", "-p", str(temp_sdcard)], timeout=8)
                if _is_valid_png(temp_sdcard):
                    shutil.move(str(temp_sdcard), str(output_path))

            if _is_valid_png(output_path):
                return {
                    "status": "ok",
                    "message": "Silva: Print da tela capturado.",
                    "image_url": rel_url,
                    "data": {"file_path": str(output_path), "method": "screencap"}
                }
        except Exception:
            pass

        try:
            _run_termux_cmd(["input", "keyevent", "120"], timeout=4)
            time.sleep(1.8)

            screenshot_dirs = [
                Path("/sdcard/DCIM/Screenshots"),
                Path("/sdcard/Pictures/Screenshots"),
                Path("/storage/emulated/0/DCIM/Screenshots"),
                Path("/storage/emulated/0/Pictures/Screenshots"),
                Path("/sdcard/DCIM"),
                Path("/sdcard/Pictures")
            ]

            now = time.time()
            newest_file = None
            newest_mtime = 0

            for d in screenshot_dirs:
                if d.is_dir():
                    try:
                        for f in d.iterdir():
                            if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                                mtime = f.stat().st_mtime
                                if (now - mtime) < 20 and mtime > newest_mtime:
                                    newest_mtime = mtime
                                    newest_file = f
                    except Exception:
                        pass

            if newest_file and newest_file.is_file():
                shutil.copy2(newest_file, output_path)
                if _is_valid_png(output_path):
                    return {
                        "status": "ok",
                        "message": "Silva: Print da tela capturado.",
                        "image_url": rel_url,
                        "data": {"file_path": str(output_path), "method": "keyevent_120", "source": str(newest_file)}
                    }
        except Exception:
            pass

        # 4. Mensagem de erro orientativa se todos falharem
        return {
            "status": "error",
            "message": "Não foi possível capturar a tela sem permissão de shell. Para liberar prints no Android sem root, instale 'pkg install android-tools' no Termux e conecte a Depuração por Wi-Fi local (adb connect 127.0.0.1:PORTA)."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": "Não foi possível capturar a tela sem permissão de shell. Para liberar prints no Android sem root, instale 'pkg install android-tools' no Termux e conecte a Depuração por Wi-Fi local (adb connect 127.0.0.1:PORTA)."
        }


def record_video(duration: int = 10, camera_id: int = 0) -> Dict[str, Any]:
    """Grava um vídeo por X segundos usando a câmera traseira (0) ou frontal (1)."""
    dur = max(3, min(int(duration), 120))
    cam = 1 if int(camera_id) == 1 else 0
    cam_label = "frontal (selfie)" if cam == 1 else "traseira"
    ts = int(time.time())
    filename = f"vid_{ts}.mp4"
    output_path = CAPTURES_DIR / filename
    rel_url = f"/captures/{filename}"

    if SIMULATE_HARDWARE:
        # Assinatura binária mínima de contêiner MP4 (ftypisom)
        dummy_mp4 = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"
        output_path.write_bytes(dummy_mp4)
        return {
            "status": "ok",
            "message": f"Silva: Vídeo gravado com sucesso ({dur}s, câmera {cam_label}). [Simulado]",
            "video_url": rel_url,
            "data": {"file_path": str(output_path), "duration": dur, "camera_id": cam}
        }

    try:
        start_ts = time.time()
        # Dispara Intent nativa de captura de vídeo do Android
        _run_termux_cmd([
            "am", "start",
            "-a", "android.media.action.VIDEO_CAPTURE",
            "--ei", "android.intent.extra.durationLimit", str(dur),
            "--ei", "android.intent.extras.CAMERA_FACING", str(cam),
            "--ez", "android.intent.extra.quickCapture", "true"
        ], timeout=6)

        # Aguarda a gravação com margem de segurança de 3s
        time.sleep(dur + 3)

        # Procura o arquivo .mp4 mais recente criado após o início da chamada
        video_dirs = [
            Path("/sdcard/DCIM/Camera"),
            Path("/sdcard/Movies"),
            Path("/sdcard/DCIM"),
            Path("/storage/emulated/0/DCIM/Camera"),
            Path("/storage/emulated/0/Movies")
        ]
        newest_file = None
        newest_mtime = 0
        for vd in video_dirs:
            if vd.is_dir():
                try:
                    for f in vd.iterdir():
                        if f.is_file() and f.suffix.lower() in (".mp4", ".3gp", ".mkv"):
                            mtime = f.stat().st_mtime
                            if mtime >= (start_ts - 5) and mtime > newest_mtime:
                                newest_mtime = mtime
                                newest_file = f
                except Exception:
                    pass

        if newest_file and newest_file.is_file():
            shutil.copy2(newest_file, output_path)
            return {
                "status": "ok",
                "message": f"Silva: Vídeo gravado com sucesso ({dur}s, câmera {cam_label}).",
                "video_url": rel_url,
                "data": {"file_path": str(output_path), "duration": dur, "camera_id": cam, "source": str(newest_file)}
            }

        return {
            "status": "ok",
            "message": f"Silva: Gravação de vídeo iniciada ({dur}s, câmera {cam_label}).",
            "data": {"duration": dur, "camera_id": cam}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro na gravação de vídeo: {str(e)}"}



MEDIA_ACTION_SYNONYMS = {
    # pause
    "pause": "pause",
    "pausa": "pause",
    "pausar": "pause",
    "parar": "pause",
    "para": "pause",
    "pare": "pause",
    "interromper": "pause",
    "stop": "pause",
    # play
    "play": "play",
    "tocar": "play",
    "toca": "play",
    "toque": "play",
    "reproduzir": "play",
    "reproduz": "play",
    "continuar": "play",
    "continua": "play",
    "retomar": "play",
    "retoma": "play",
    "despausar": "play",
    "despausa": "play",
    # next
    "next": "next",
    "proxima": "next",
    "próxima": "next",
    "proximo": "next",
    "próximo": "next",
    "avancar": "next",
    "avançar": "next",
    "avanca": "next",
    "avança": "next",
    "pular": "next",
    "pula": "next",
    "pule": "next",
    "passar": "next",
    "passa": "next",
    "passe": "next",
    # previous
    "previous": "previous",
    "anterior": "previous",
    "voltar": "previous",
    "volta": "previous",
    "retroceder": "previous",
    "retrocede": "previous",
}

MEDIA_KEYEVENTS = {
    "play": 126,
    "pause": 127,
    "next": 87,
    "previous": 88,
}

MEDIA_CONFIRMATIONS = {
    "pause": "Mídia pausada.",
    "play": "Reprodução retomada.",
    "next": "Avançando para a próxima faixa.",
    "previous": "Voltando para a mídia anterior.",
}


def media_control(action: str) -> Dict[str, Any]:
    """Controla a reprodução global de música ou vídeo no Android (play, pause, next, previous)."""
    raw_action = str(action or "").strip().lower()
    normalized_action = MEDIA_ACTION_SYNONYMS.get(raw_action)
    if not normalized_action:
        for syn, target in MEDIA_ACTION_SYNONYMS.items():
            if syn in raw_action:
                normalized_action = target
                break

    if not normalized_action or normalized_action not in MEDIA_KEYEVENTS:
        return {
            "status": "error",
            "message": f"Ação de mídia '{action}' inválida. Use 'pause', 'play', 'next' ou 'previous'."
        }

    msg = MEDIA_CONFIRMATIONS[normalized_action]

    if not SIMULATE_HARDWARE:
        key_code = MEDIA_KEYEVENTS[normalized_action]
        # Tentativa 0 (ADB Local privilegiado): input keyevent {code}
        ok_adb, _ = run_adb_shell(["input", "keyevent", str(key_code)], timeout=4.0)
        if ok_adb:
            return {
                "status": "ok",
                "message": msg,
                "data": {"action": normalized_action, "method": "adb"}
            }

        # Tentativa 1 (Nativo Android 10+): cmd media_session dispatch {normalized_action}
        res1 = _exec_android_intent(f"cmd media_session dispatch {normalized_action}")
        # Tentativa 2 (Fallback via KeyEvent caso cmd media_session falhe)
        if res1.returncode != 0 or "Error" in res1.stderr:
            _exec_android_intent(f"input keyevent {key_code}")

    return {
        "status": "ok",
        "message": msg,
        "data": {"action": normalized_action}
    }


def record_audio(duration: int = 10) -> Dict[str, Any]:
    """Grava um áudio/nota de voz usando o microfone via termux-microphone-record (1 a 120s)."""
    try:
        dur = int(duration)
    except (TypeError, ValueError):
        dur = 10
    dur = max(1, min(120, dur))

    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"audio_{int(time.time())}.m4a"
    out_path = CAPTURES_DIR / filename
    audio_url = f"/captures/{filename}"

    if SIMULATE_HARDWARE:
        out_path.write_bytes(b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom\x00\x00\x00\x08free")
        return {
            "status": "ok",
            "message": f"Silva: Áudio de {dur}s gravado com sucesso. [Simulado]",
            "audio_url": audio_url,
            "media_items": [{"type": "audio", "url": audio_url}],
            "data": {"filename": filename, "duration": dur, "simulated": True},
        }

    try:
        _run_termux_cmd(["termux-microphone-record", "-q"], timeout=3)
    except Exception:
        pass

    try:
        res = _run_termux_cmd(
            ["termux-microphone-record", "-f", str(out_path), "-l", str(dur), "-e", "aac"],
            timeout=dur + 8,
        )
        time.sleep(0.4)
        if res.returncode != 0 and not out_path.is_file():
            return {
                "status": "error",
                "message": (
                    f"Falha ao gravar áudio ({res.stderr.strip() or 'erro desconhecido'}). "
                    "Verifique se a permissão de Microfone foi concedida ao aplicativo Termux:API nas Configurações do Android."
                ),
            }
    except Exception as e:
        return {
            "status": "error",
            "message": (
                f"Erro ao gravar áudio: {str(e)}. "
                "Conceda permissão de Microfone ao Termux:API nas Configurações do Android."
            ),
        }
    finally:
        try:
            _run_termux_cmd(["termux-microphone-record", "-q"], timeout=3)
        except Exception:
            pass

    if not out_path.is_file() or out_path.stat().st_size <= 0:
        return {
            "status": "error",
            "message": (
                "A gravação de áudio não gerou um arquivo válido (0 bytes). "
                "Conceda a permissão de Microfone ao aplicativo Termux:API nas Configurações do Android."
            ),
        }

    return {
        "status": "ok",
        "message": f"Silva: Áudio de {dur}s gravado com sucesso ({filename}).",
        "audio_url": audio_url,
        "media_items": [{"type": "audio", "url": audio_url}],
        "data": {"filename": filename, "duration": dur, "size_bytes": out_path.stat().st_size},
    }


_MEDIA_APP_PACKAGES = {
    "spotify": ("com.spotify.music", "Spotify"),
    "youtube": ("com.google.android.youtube", "YouTube"),
    "youtube music": ("com.google.android.apps.youtube.music", "YouTube Music"),
}


def _dispatch_media_intent(args: list, adb_serial: Optional[str]) -> bool:
    if adb_serial:
        ok, out = run_adb_shell(args, timeout=6.0)
        if ok and "Error:" not in (out or ""):
            return True
    res = _exec_android_intent(shlex.join(args))
    return res.returncode == 0 and "Error:" not in (res.stderr or "")


def play_media(query: str, app: str = "") -> Dict[str, Any]:
    """Busca e inicia a reprodução de música, artista, playlist ou vídeo no Spotify, YouTube ou player padrão."""
    clean_query = str(query or "").strip()
    if not clean_query:
        return {"status": "error", "message": "Informe o nome da música, artista ou vídeo para reproduzir."}

    raw_app = str(app or "").strip().lower()
    if raw_app in ("yt", "youtube"):
        norm_app = "youtube"
    elif raw_app in ("yt music", "youtube music", "youtubemusic"):
        norm_app = "youtube music"
    elif "spotify" in raw_app:
        norm_app = "spotify"
    else:
        norm_app = ""

    pkg, app_label = _MEDIA_APP_PACKAGES.get(norm_app, ("", "Player padrão"))
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Reproduzindo '{clean_query}' no {app_label}. [Simulado]",
            "data": {"query": clean_query, "app": norm_app or "default", "simulated": True},
        }
    adb_serial = ensure_adb_connected()

    search_cmd = [
        "am", "start",
        "-a", "android.media.action.MEDIA_PLAY_FROM_SEARCH",
        "-e", "query", clean_query,
    ]
    if pkg:
        search_cmd.extend(["-p", pkg])

    launched = _dispatch_media_intent(search_cmd, adb_serial)
    if not launched:
        enc_q = urllib.parse.quote(clean_query)
        if norm_app in ("youtube", "youtube music"):
            launched = _dispatch_media_intent(
                ["am", "start", "-a", "android.intent.action.VIEW", "-d", f"https://www.youtube.com/results?search_query={enc_q}"],
                adb_serial,
            )
        elif norm_app == "spotify":
            launched = _dispatch_media_intent(
                ["am", "start", "-a", "android.intent.action.VIEW", "-d", f"spotify:search:{enc_q}", "-p", "com.spotify.music"],
                adb_serial,
            )

    if not launched:
        return {
            "status": "error",
            "message": f"Não foi possível iniciar a reprodução de '{clean_query}' no {app_label}.",
            "data": {"query": clean_query, "app": norm_app or "default"},
        }

    return {
        "status": "ok",
        "message": f"Silva: Reproduzindo '{clean_query}' no {app_label}.",
        "data": {"query": clean_query, "app": norm_app or "default", "package": pkg},
    }


def save_voice_note(title: str = "", duration: int = 15, text_only: bool = False) -> Dict[str, Any]:
    """
    Salva um lembrete multimodal na tabela voice_notes (memory.db):
    - text_only=True: registra lembrete digitado diretamente (sem gravação).
    - text_only=False: grava áudio real via microfone e registra na lista ativa.
    """
    clean_title = str(title or "").strip()
    is_text_only = (
        text_only if isinstance(text_only, bool)
        else str(text_only).strip().lower() in ("true", "1", "yes", "sim")
    )

    if is_text_only:
        if not clean_title:
            return {"status": "error", "message": "Informe o texto do lembrete para adicionar ao checklist."}
        with _FILE_LOCK:
            conn = _get_memory_db()
            try:
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO voice_notes (title, note_type, filename, is_checked) VALUES (?, 'text', NULL, 0)",
                        (clean_title,),
                    )
                    note_id = cur.lastrowid
            finally:
                conn.close()
        return {
            "status": "ok",
            "message": f"Silva: Lembrete '{clean_title}' adicionado à lista interativa.",
            "data": {"id": note_id, "title": clean_title, "note_type": "text"},
        }

    # Modo voz (text_only=False)
    try:
        dur = int(duration)
    except (TypeError, ValueError):
        dur = 15
    dur = max(1, min(120, dur))

    note_title = clean_title or f"Nota de voz ({datetime.now().strftime('%d/%m às %H:%M')})"
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"voice_note_{int(time.time() * 1000)}.m4a"
    out_path = CAPTURES_DIR / filename
    audio_url = f"/captures/{filename}"

    if SIMULATE_HARDWARE:
        out_path.write_bytes(b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom\x00\x00\x00\x08free")
    else:
        try:
            _run_termux_cmd(["termux-microphone-record", "-q"], timeout=3)
        except Exception:
            pass
        try:
            res = _run_termux_cmd(
                ["termux-microphone-record", "-f", str(out_path), "-l", str(dur), "-e", "aac"],
                timeout=dur + 8,
            )
            time.sleep(0.4)
            if res.returncode != 0 and not out_path.is_file():
                return {
                    "status": "error",
                    "message": (
                        f"Falha ao gravar nota de voz ({res.stderr.strip() or 'erro desconhecido'}). "
                        "Conceda permissão de Microfone ao Termux:API nas Configurações do Android."
                    ),
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erro ao gravar nota de voz: {str(e)}",
            }
        finally:
            try:
                _run_termux_cmd(["termux-microphone-record", "-q"], timeout=3)
            except Exception:
                pass

        if not out_path.is_file() or out_path.stat().st_size <= 0:
            return {
                "status": "error",
                "message": "A gravação da nota de voz não gerou um arquivo válido (0 bytes).",
            }

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO voice_notes (title, note_type, filename, is_checked) VALUES (?, 'audio', ?, 0)",
                    (note_title, filename),
                )
                note_id = cur.lastrowid
        finally:
            conn.close()

    return {
        "status": "ok",
        "message": f"Silva: Nota de voz '{note_title}' gravada ({dur}s) e salva no checklist.",
        "audio_url": audio_url,
        "media_items": [{"type": "audio", "url": audio_url}],
        "data": {
            "id": note_id,
            "title": note_title,
            "note_type": "audio",
            "filename": filename,
            "url": audio_url,
            "duration": dur,
        },
    }


def get_voice_notes(query: str = "") -> Dict[str, Any]:
    """Lista ou busca lembretes e notas de voz pendentes (is_checked = 0) para o checklist interativo."""
    clean_q = str(query or "").strip()
    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            cur = conn.cursor()
            if clean_q:
                cur.execute(
                    "SELECT id, title, note_type, filename, created_at "
                    "FROM voice_notes WHERE is_checked = 0 AND lower(title) LIKE ? "
                    "ORDER BY id DESC",
                    (f"%{clean_q.lower()}%",),
                )
            else:
                cur.execute(
                    "SELECT id, title, note_type, filename, created_at "
                    "FROM voice_notes WHERE is_checked = 0 ORDER BY id DESC"
                )
            rows = cur.fetchall()
        finally:
            conn.close()

    if not rows:
        msg = (
            f"Silva: Nenhum lembrete pendente encontrado para '{clean_q}'."
            if clean_q
            else "Silva: Sua lista de lembretes e notas de voz está limpa (nenhum item pendente)."
        )
        return {
            "status": "ok",
            "message": msg,
            "data": {"voice_notes": [], "total": 0},
        }

    items = []
    media_items = []
    for r in rows:
        fn = r["filename"]
        url = f"/captures/{fn}" if fn else None
        items.append({
            "id": r["id"],
            "title": r["title"],
            "note_type": r["note_type"],
            "url": url,
            "created_at": r["created_at"],
        })
        if url:
            media_items.append({"type": "audio", "url": url})

    lines = [f"- {it['title']} ({'Áudio' if it['url'] else 'Texto'})" for it in items]
    resp: Dict[str, Any] = {
        "status": "ok",
        "message": f"Silva: Você tem {len(items)} item(ns) no checklist:\n" + "\n".join(lines),
        "data": {"voice_notes": items, "total": len(items)},
    }
    if media_items:
        resp["media_items"] = media_items
    return resp


def check_voice_note(query: str = "", note_id: int = 0) -> Dict[str, Any]:
    """Marca um lembrete/nota de voz como concluído (check), removendo da lista ativa e do disco."""
    clean_q = str(query or "").strip()
    try:
        nid = int(note_id or 0)
    except (TypeError, ValueError):
        nid = 0

    if nid <= 0 and not clean_q:
        return {"status": "error", "message": "Informe o ID ou o título do lembrete para concluir."}

    target_row = None
    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            cur = conn.cursor()
            if nid > 0:
                cur.execute(
                    "SELECT id, title, filename FROM voice_notes WHERE id = ? AND is_checked = 0",
                    (nid,),
                )
                target_row = cur.fetchone()
            elif any(k in clean_q.lower() for k in ("última", "ultima", "último", "ultimo", "recente")):
                cur.execute(
                    "SELECT id, title, filename FROM voice_notes WHERE is_checked = 0 ORDER BY id DESC LIMIT 1"
                )
                target_row = cur.fetchone()
            else:
                cur.execute(
                    "SELECT id, title, filename FROM voice_notes "
                    "WHERE is_checked = 0 AND lower(title) LIKE ? ORDER BY id DESC LIMIT 1",
                    (f"%{clean_q.lower()}%",),
                )
                target_row = cur.fetchone()

            if not target_row:
                return {
                    "status": "ok",
                    "message": "Silva: Nenhum lembrete pendente correspondente foi encontrado.",
                    "data": {"checked": False},
                }

            with conn:
                conn.execute(
                    "UPDATE voice_notes SET is_checked = 1, checked_at = datetime('now', 'localtime') WHERE id = ?",
                    (target_row["id"],),
                )
        finally:
            conn.close()

    deleted_audio = False
    fn = target_row["filename"]
    if fn:
        audio_path = (CAPTURES_DIR / fn).resolve()
        try:
            if audio_path.is_relative_to(CAPTURES_DIR.resolve()) and audio_path.is_file():
                audio_path.unlink(missing_ok=True)
                deleted_audio = True
        except Exception:
            pass

    return {
        "status": "ok",
        "message": f"Silva: '{target_row['title']}' concluído e removido do checklist.",
        "data": {
            "id": target_row["id"],
            "title": target_row["title"],
            "checked": True,
            "deleted_audio": deleted_audio,
        },
    }


