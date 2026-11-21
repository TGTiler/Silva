"""
Implementação das ferramentas nativas do Android via Termux:API para o Silva.
Controle de hardware, chamadas de sistema, sanitização e retornos padronizados.
"""

import ast
import html
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from config import CAPTURES_DIR, SIMULATE_HARDWARE

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LAST_LOCATION_FILE = DATA_DIR / "last_location.json"
EVENTS_FILE = DATA_DIR / "events.json"


def _load_events() -> list:
    if not EVENTS_FILE.is_file():
        return []
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_events(events: list):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

# Mapeamento de nomes amigáveis para pacotes Android conhecidos
APP_PACKAGES = {
    "hltv": "org.hltv.android",
    "bitget wallet": "com.bgwapp.official",
    "bitget": "com.bgwapp.official",
    "yt studio": "com.google.android.apps.youtube.creator",
    "youtube studio": "com.google.android.apps.youtube.creator",
    "duckduckgo": "com.duckduckgo.mobile.android",
    "duckduck": "com.duckduckgo.mobile.android",
    "instagram": "com.instagram.android",
    "insta": "com.instagram.android",
    "vlc": "org.videolan.vlc",
    "99": "com.taxis99",
    "99pop": "com.taxis99",
    "caixa tem": "br.gov.caixa.tem",
    "caixatem": "br.gov.caixa.tem",
    "termux": "com.termux",
    "metamask": "io.metamask",
    "zarchiver": "ru.zdevs.zarchiver",
    "carteira do google": "com.google.android.apps.walletnfcrel",
    "google wallet": "com.google.android.apps.walletnfcrel",
    "carteira": "com.google.android.apps.walletnfcrel",
    "em 3": "com.oxiwyle.modernage3",
    "simulador do presidente": "com.oxiwyle.modernage3",
    "aqua": "io.aquawallet.android",
    "aqua wallet": "io.aquawallet.android",
    "mercado bitcoin": "br.com.mercadobitcoin.android",
    "x": "com.twitter.android",
    "twitter": "com.twitter.android",
    "jornada do estudante": "br.gov.mec.jornada.estudante",
    "sideshift": "ai.sideshift.app",
    "github": "com.github.android",
    "shein": "com.zzkko",
    "gemini": "com.google.android.apps.bard",
    "lobstr": "com.lobstr.client",
    "trust wallet": "com.wallet.crypto.trustapp",
    "chatgpt": "com.openai.chatgpt",
    "yoosee": "com.yoosee",
    "calculadora": "com.sec.android.app.popupcalculator",
    "discord": "com.discord",
    "tradingview": "com.tradingview.tradingviewapp",
    "bomber friends": "com.hyperkani.bomberfriends",
    "sideswap": "io.sideswap",
    "userland": "tech.ula",
    "cittamobi": "br.com.cittabus",
    "gamemarket": "br.com.gamemarket.app",
    "tiktok": "com.zhiliaoapp.musically",
    "pichau": "com.pichaumobile",
    "shopee": "com.shopee.br",
    "pinterest": "com.pinterest",
    "nubank": "com.nu.production",
    "telegram": "org.telegram.messenger",
    "ifood": "br.com.brainweb.ifood",
    "whatsapp": "com.whatsapp",
    "duolingo": "com.duolingo",
    "proton mail": "ch.protonmail.android",
    "protonmail": "ch.protonmail.android",
    "twitch": "tv.twitch.android.app",
    "adguard": "com.adguard.android",
    "snaptube": "com.snaptube.premium",
    "steam": "com.valvesoftware.android.steam.community",
    "amazon shopping": "com.amazon.mShop.android.shopping",
    "amazon": "com.amazon.mShop.android.shopping",
    "calendario": "com.samsung.android.calendar",
    "calendário": "com.samsung.android.calendar",
    "chat maritaca": "com.maritaca.app",
    "maritaca": "com.maritaca.app",
    "bluewallet": "io.bluewallet.bluewallet",
    "celular seguro": "com.celularlegal",
    "wallet of satoshi": "com.livingroomofsatoshi.wallet",
    "minecraft": "com.mojang.minecraftpe",
    "kick": "com.kick.mobile",
    "authenticator": "com.google.android.apps.authenticator2",
    "cartao vem": "vem.posto.virtual",
    "cartão vem": "vem.posto.virtual",
    "vem": "vem.posto.virtual",
    "deepseek": "com.deepseek.chat",
    # Aplicativos essenciais do sistema
    "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome",
    "camera": "com.sec.android.app.camera",
    "câmera": "com.sec.android.app.camera",
    "configuracoes": "com.android.settings",
    "configurações": "com.android.settings",
    "settings": "com.android.settings",
    "spotify": "com.spotify.music",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "galeria": "com.sec.android.gallery3d",
    "fotos": "com.sec.android.gallery3d",
    "relogio": "com.sec.android.app.clockpackage",
    "relógio": "com.sec.android.app.clockpackage",
    "alarme": "com.sec.android.app.clockpackage",
    "gov.br": "br.gov.meugovbr",
    "govbr": "br.gov.meugovbr",
    "meu gov": "br.gov.meugovbr",
    "roblox": "com.roblox.client",
    "outlook": "com.microsoft.office.outlook"
}

RESOLVED_APP_ACTIVITIES = {   'ai.sideshift.app': 'ai.sideshift.app/.MainActivity',
    'br.com.brainweb.ifood': 'br.com.brainweb.ifood/.AppIcon',
    'br.com.cittabus': 'br.com.cittabus/br.com.cittati.cittamobi_flutter.MainActivity',
    'br.com.gamemarket.app': 'br.com.gamemarket.app/.LauncherActivity',
    'br.com.mercadobitcoin.android': 'br.com.mercadobitcoin.android/br.com.mercadobitcoin.welcome.view.WelcomeActivity',
    'br.gov.caixa.tem': 'br.gov.caixa.tem/.ui.activities.SplashScreenAnimation',
    'br.gov.mec.jornada.estudante': 'br.gov.mec.jornada.estudante/.MainActivity',
    'br.gov.meugovbr': 'br.gov.meugovbr/.MainActivity',
    'ch.protonmail.android': 'ch.protonmail.android/.RoutingActivity',
    'com.adguard.android': 'com.adguard.android/.ui.activity.SplashActivity',
    'com.amazon.mShop.android.shopping': 'com.amazon.mShop.android.shopping/com.amazon.mShop.home.HomeActivity',
    'com.android.chrome': 'com.android.chrome/com.google.android.apps.chrome.Main',
    'com.android.settings': 'com.android.settings/.Settings',
    'com.bgwapp.official': 'com.bgwapp.official/.MainActivity',
    'com.celularlegal': 'com.celularlegal/.MainActivity',
    'com.deepseek.chat': 'com.deepseek.chat/.MainActivity',
    'com.discord': 'com.discord/.main.MainDefault',
    'com.duckduckgo.mobile.android': 'com.duckduckgo.mobile.android/com.duckduckgo.app.launch.Launcher',
    'com.duolingo': 'com.duolingo/.app.LoginActivity',
    'com.github.android': 'com.github.android/.main.MainActivity',
    'com.google.android.apps.authenticator2': 'com.google.android.apps.authenticator2/.main.MainActivity',
    'com.google.android.apps.bard': 'com.google.android.apps.bard/.shellapp.BardEntryPointActivity',
    'com.google.android.apps.maps': 'com.google.android.apps.maps/com.google.android.maps.MapsActivity',
    'com.google.android.apps.walletnfcrel': 'com.google.android.apps.walletnfcrel/com.google.commerce.tapandpay.android.wallet.WalletActivity',
    'com.google.android.apps.youtube.creator': 'com.google.android.apps.youtube.creator/.main.MainActivity',
    'com.google.android.gm': 'com.google.android.gm/.ConversationListActivityGmail',
    'com.google.android.youtube': 'com.google.android.youtube/.app.honeycomb.Shell$HomeActivity',
    'com.hyperkani.bomberfriends': 'com.hyperkani.bomberfriends/.BomberFriends',
    'com.instagram.android': 'com.instagram.android/.activity.MainTabActivity',
    'com.kick.mobile': 'com.kick.mobile/.MainActivity',
    'com.livingroomofsatoshi.wallet': 'com.livingroomofsatoshi.wallet/.MainActivity',
    'com.lobstr.client': 'com.lobstr.client/app_icon_alias.InitialAlias',
    'com.maritaca.app': 'com.maritaca.app/.MainActivity',
    'com.microsoft.office.outlook': 'com.microsoft.office.outlook/.MainActivity',
    'com.mojang.minecraftpe': 'com.mojang.minecraftpe/.MainActivity',
    'com.nu.production': 'com.nu.production/br.com.nubank.app.LegacySplashActivity',
    'com.openai.chatgpt': 'com.openai.chatgpt/.MainActivity',
    'com.oxiwyle.modernage3': 'com.oxiwyle.modernage3/com.oxiwyle.modernage2.activities.StartActivity',
    'com.pichaumobile': 'com.pichaumobile/.MainActivity',
    'com.pinterest': 'com.pinterest/.activity.PinterestActivity',
    'com.roblox.client': 'com.roblox.client/.startup.LauncherAliasMain',
    'com.samsung.android.calendar': 'com.samsung.android.calendar/com.samsung.android.app.calendar.activity.MainActivity',
    'com.sec.android.app.camera': 'com.sec.android.app.camera/.Camera',
    'com.sec.android.app.clockpackage': 'com.sec.android.app.clockpackage/.ClockPackage',
    'com.sec.android.app.popupcalculator': 'com.sec.android.app.popupcalculator/.Calculator',
    'com.sec.android.gallery3d': 'com.sec.android.gallery3d/com.samsung.android.gallery.app.activity.GalleryActivity',
    'com.shopee.br': 'com.shopee.br/com.shopee.app.ui.home.HomeActivity_',
    'com.snaptube.premium': 'com.snaptube.premium/.activity.ExploreActivity',
    'com.spotify.music': None,
    'com.taxis99': 'com.taxis99/com.didi.sdk.splash.SplashActivity',
    'com.termux': 'com.termux/.app.TermuxActivity',
    'com.tradingview.tradingviewapp': 'com.tradingview.tradingviewapp/.root.view.RootActivity',
    'com.twitter.android': 'com.twitter.android/com.x.android.main.MainActivity',
    'com.valvesoftware.android.steam.community': 'com.valvesoftware.android.steam.community/.MainActivity',
    'com.wallet.crypto.trustapp': 'com.wallet.crypto.trustapp/.ui.app.AppActivity.default',
    'com.whatsapp': 'com.whatsapp/.Main',
    'com.yoosee': 'com.yoosee/com.jwkj.activity.LogoActivity',
    'com.zhiliaoapp.musically': 'com.zhiliaoapp.musically/com.ss.android.ugc.aweme.splash.SplashActivity',
    'com.zzkko': 'com.zzkko/com.shein.welcome.WelcomeActivity',
    'io.aquawallet.android': 'io.aquawallet.android/io.aquawallet.MainActivity',
    'io.bluewallet.bluewallet': 'io.bluewallet.bluewallet/.MainActivity',
    'io.metamask': 'io.metamask/.MainActivity',
    'io.sideswap': 'io.sideswap/.MainActivity',
    'org.hltv.android': 'org.hltv.android/org.hltv.mobileapp.MainActivity',
    'org.telegram.messenger': 'org.telegram.messenger/.DefaultIcon',
    'org.videolan.vlc': 'org.videolan.vlc/.StartActivity',
    'ru.zdevs.zarchiver': 'ru.zdevs.zarchiver/.ZArchiver',
    'tech.ula': 'tech.ula/.MainActivity',
    'tv.twitch.android.app': 'tv.twitch.android.app/.core.LandingActivity',
    'vem.posto.virtual': 'vem.posto.virtual/.MainActivity'}


def sanitize_phone_number(number: str) -> str:
    """Sanitiza número de telefone mantendo dígitos e prefixo +."""
    raw = str(number).strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    return ("+" + digits) if has_plus else digits


def resolve_contact_or_number(target: str) -> str:
    """
    Resolve um número ou nome de contato.
    Se o alvo contiver letras (ex: 'Mãe', 'Aline'), tenta localizar o número na agenda do celular via Termux:API.
    Caso contrário ou em simulação, preserva a identificação do contato ou sanitiza o número.
    """
    raw = str(target).strip()
    if not raw:
        return ""

    # Se contém letras, trata como nome de contato
    if re.search(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", raw):
        if not SIMULATE_HARDWARE:
            try:
                res = _run_termux_cmd(["termux-contact-list"], timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    contacts = json.loads(res.stdout)
                    norm_target = raw.lower()
                    for c in contacts:
                        c_name = c.get("name", "").lower()
                        if norm_target in c_name or c_name in norm_target:
                            num = c.get("number")
                            if num:
                                return sanitize_phone_number(num)
            except Exception:
                pass
        return raw

    return sanitize_phone_number(raw)


def _run_termux_cmd(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    """Executa comando de forma segura sem shell injection, resolvendo binários do sistema Android se necessário."""
    if not cmd:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="Comando vazio")

    exec_cmd = list(cmd)
    binary = exec_cmd[0]

    # Prioriza o wrapper nativo do Termux para o comando 'am' evitando o SecurityException no Android 14
    if binary == "am" and os.path.exists("/data/data/com.termux/files/usr/bin/am"):
        exec_cmd[0] = "/data/data/com.termux/files/usr/bin/am"
    elif not shutil.which(binary):
        # Se o binário não estiver no PATH, procura nos caminhos conhecidos do Android/Termux
        for candidate in [f"/data/data/com.termux/files/usr/bin/{binary}", f"/system/bin/{binary}", f"/system/xbin/{binary}"]:
            if os.path.exists(candidate):
                exec_cmd[0] = candidate
                break

    try:
        return subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
    except OSError:
        # Fallback para invocação via shell do Termux/Android caso ocorra Exec format error
        sh_bin = "/data/data/com.termux/files/usr/bin/sh" if os.path.exists("/data/data/com.termux/files/usr/bin/sh") else "/system/bin/sh"
        try:
            return subprocess.run(
                [sh_bin] + exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
        except Exception as e2:
            return subprocess.CompletedProcess(args=exec_cmd, returncode=1, stdout="", stderr=str(e2))
    except Exception as e:
        return subprocess.CompletedProcess(args=exec_cmd, returncode=1, stdout="", stderr=str(e))


def _exec_android_intent(cmd_str: str, timeout: int = 6) -> subprocess.CompletedProcess:
    """Executa comando de intent/app priorizando o am do Termux ou shell Android para máxima compatibilidade."""
    termux_bin = "/data/data/com.termux/files/usr/bin"
    sh_bin = f"{termux_bin}/sh" if os.path.exists(f"{termux_bin}/sh") else "/system/bin/sh"

    # Se o comando chama 'am', preferir o binário wrapper do Termux se existir (evita Permission Denial no Android 14)
    am_bin = f"{termux_bin}/am" if os.path.exists(f"{termux_bin}/am") else "am"
    if cmd_str.startswith("am "):
        exec_str = f"{am_bin} {cmd_str[3:]}"
    else:
        exec_str = cmd_str

    full_cmd = f"export PATH={termux_bin}:$PATH:/system/bin:/system/xbin; {exec_str}"
    try:
        return subprocess.run(
            [sh_bin, "-c", full_cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
    except Exception as e:
        return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr=str(e))


def get_battery() -> Dict[str, Any]:
    """Obtém status da bateria: porcentagem, status e temperatura."""
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": "Silva: Bateria em 82% (descarregando, temperatura 31.4°C). [Simulado]",
            "data": {
                "percentage": 82,
                "status": "DISCHARGING",
                "temperature": 31.4,
                "health": "GOOD"
            }
        }

    try:
        res = _run_termux_cmd(["termux-battery-status"], timeout=5)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao ler bateria: {res.stderr.strip()}"}
        
        data = json.loads(res.stdout)
        pct = data.get("percentage", 0)
        status = data.get("status", "UNKNOWN")
        temp = data.get("temperature", 0)
        plugged = data.get("plugged", "UNPLUGGED")

        status_pt = "carregando" if plugged != "UNPLUGGED" else "descarregando"
        msg = f"Silva: Bateria em {pct}% ({status_pt}, temperatura {temp:.1f}°C)."
        return {"status": "ok", "message": msg, "data": data}
    except Exception as e:
        return {"status": "error", "message": f"Erro ao acessar status da bateria: {str(e)}"}


def get_last_sms(limit: int = 5) -> Dict[str, Any]:
    """Lê as últimas mensagens SMS recebidas."""
    limit = max(1, min(int(limit), 20))
    if SIMULATE_HARDWARE:
        simulated_messages = [
            {"number": "11987654321", "received": "2026-11-20 20:30", "body": "Chegando em 10 minutos!"},
            {"number": "Nubank", "received": "2026-11-20 18:45", "body": "Compra de R$ 45,00 aprovada."},
        ][:limit]
        return {
            "status": "ok",
            "message": f"Silva: Encontrei {len(simulated_messages)} mensagens recentes. [Simulado]",
            "data": simulated_messages
        }

    try:
        res = _run_termux_cmd(["termux-sms-list", "-l", str(limit)], timeout=8)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao obter SMS: {res.stderr.strip()}"}

        messages = json.loads(res.stdout)
        formatted = []
        for sms in messages:
            formatted.append({
                "number": sms.get("number", "Desconhecido"),
                "received": sms.get("received", ""),
                "body": sms.get("body", "")
            })

        summary = f"Silva: {len(formatted)} SMS encontrados."
        return {"status": "ok", "message": summary, "data": formatted}
    except Exception as e:
        return {"status": "error", "message": f"Erro ao listar SMS: {str(e)}"}


def send_sms(number: str, message: str) -> Dict[str, Any]:
    """Envia SMS para o número ou contato especificado."""
    clean_target = resolve_contact_or_number(number)
    if not clean_target:
        return {"status": "error", "message": "Destinatário do SMS inválido."}

    clean_text = str(message).strip()
    if not clean_text:
        return {"status": "error", "message": "Mensagem SMS vazia."}

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: SMS enviado com sucesso para {clean_target}: '{clean_text}'. [Simulado]",
            "data": {"number": clean_target, "message": clean_text}
        }

    try:
        res = _run_termux_cmd(["termux-sms-send", "-n", clean_target, clean_text], timeout=10)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao enviar SMS: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: SMS enviado com sucesso para {clean_target}.",
            "data": {"number": clean_target, "message": clean_text}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao disparar SMS: {str(e)}"}


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


def open_app(app_name: str) -> Dict[str, Any]:
    """Abre um aplicativo pelo nome ou pacote Android."""
    key = str(app_name).strip().lower()
    # Normaliza removendo acentos para casar 'calendário' com 'calendario', etc.
    key_unaccent = unicodedata.normalize("NFKD", key).encode("ASCII", "ignore").decode("utf-8")
    package = APP_PACKAGES.get(key) or APP_PACKAGES.get(key_unaccent) or key

    packages_to_try = [package]
    if key == "tiktok" or package in ("com.zhiliaoapp.musically", "com.ss.android.ugc.trill"):
        packages_to_try = ["com.zhiliaoapp.musically", "com.ss.android.ugc.trill"]

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Abrindo aplicativo '{key}' ({packages_to_try[0]}). [Simulado]",
            "data": {"app": key, "package": packages_to_try[0]}
        }

    try:
        opened_pkg = None
        for pkg in packages_to_try:
            # 1. Componente explícito se fornecido (ex: pkg/activity)
            if "/" in pkg:
                res_c = _exec_android_intent(f"am start -n {pkg}")
                if res_c.returncode == 0 and "Error:" not in res_c.stdout:
                    opened_pkg = pkg
                    break

            # 2. Resolução exata via mapa de Activities verificadas no dispositivo
            if pkg in RESOLVED_APP_ACTIVITIES and RESOLVED_APP_ACTIVITIES[pkg]:
                act_comp = RESOLVED_APP_ACTIVITIES[pkg]
                res_act = _exec_android_intent(f"am start -n {act_comp}")
                if res_act.returncode == 0 and "Error:" not in res_act.stdout:
                    opened_pkg = pkg
                    break

            # 3. Fallback am start com categoria LAUNCHER
            res_am = _exec_android_intent(f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {pkg}")
            if res_am.returncode == 0 and "Error:" not in res_am.stdout:
                opened_pkg = pkg
                break

            # 4. Fallback am start direto em Activities comuns
            for act in [".MainActivity", ".Main", ".Calculator", ".HomeActivity", ".SplashActivity"]:
                res_act = _exec_android_intent(f"am start -n {pkg}/{act}")
                if res_act.returncode == 0 and "Error:" not in res_act.stdout:
                    opened_pkg = pkg
                    break
            if opened_pkg:
                break

        if not opened_pkg:
            return {
                "status": "error",
                "message": f"Não foi possível abrir o app '{key}'. Verifique se o pacote '{packages_to_try[0]}' está instalado."
            }

        return {
            "status": "ok",
            "message": f"Silva: Abrindo {key}.",
            "data": {"app": key, "package": opened_pkg}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao abrir aplicativo: {str(e)}"}


def make_call(number: str) -> Dict[str, Any]:
    """Disca para um número ou contato telefônico."""
    clean_target = resolve_contact_or_number(number)
    if not clean_target:
        return {"status": "error", "message": "Destinatário de discagem inválido."}

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Discando para {clean_target}... [Simulado]",
            "data": {"number": clean_target}
        }

    try:
        res = _run_termux_cmd(["termux-telephony-call", clean_target], timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao discar: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: Discando para {clean_target}.",
            "data": {"number": clean_target}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao efetuar ligação: {str(e)}"}


def _generate_map_preview(lat: float, lon: float) -> Optional[str]:
    """
    Tenta baixar o tile OpenStreetMap centrado na coordenada (zoom 16)
    e desenha um marcador vermelho no ponto exato.
    Retorna o caminho relativo da imagem (/captures/loc_*.png) ou None se offline/falha.
    """
    ts = int(time.time())
    filename = f"loc_{ts}.png"
    output_path = CAPTURES_DIR / filename
    rel_url = f"/captures/{filename}"

    zoom = 16
    n = 1 << zoom
    x_exact = (lon + 180.0) / 360.0 * n
    x_tile = int(x_exact)
    lat_rad = math.radians(lat)
    y_exact = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    y_tile = int(y_exact)

    tile_url = f"https://tile.openstreetmap.org/{zoom}/{x_tile}/{y_tile}.png"
    tile_bytes = None

    try:
        req = urllib.request.Request(
            tile_url,
            headers={"User-Agent": "SilvaAgent/1.0 (Android Open Source Assistant)"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                tile_bytes = resp.read()
    except Exception:
        pass

    # Se o dispositivo estiver offline e não conseguir baixar o tile
    if not tile_bytes:
        if SIMULATE_HARDWARE:
            try:
                from PIL import Image, ImageDraw
                img = Image.new("RGB", (256, 256), color=(235, 237, 240))
                draw = ImageDraw.Draw(img)
                for x in range(0, 256, 32):
                    draw.line([(x, 0), (x, 256)], fill=(215, 220, 225), width=1)
                for y in range(0, 256, 32):
                    draw.line([(0, y), (256, y)], fill=(215, 220, 225), width=1)
                draw.line([(0, 120), (256, 140)], fill=(255, 255, 255), width=8)
                draw.line([(110, 0), (140, 256)], fill=(255, 255, 255), width=8)
                px, py = 128, 128
                draw.ellipse((px - 9, py - 20, px + 9, py - 2), fill=(235, 50, 50), outline=(120, 0, 0), width=2)
                draw.polygon([(px - 7, py - 9), (px + 7, py - 9), (px, py)], fill=(235, 50, 50))
                draw.ellipse((px - 3, py - 14, px + 3, py - 8), fill=(255, 255, 255))
                img.save(output_path, "PNG")
                return rel_url
            except Exception:
                return None
        return None

    # Desenha o pino vermelho sobre o tile baixado
    px = int((x_exact - x_tile) * 256)
    py = int((y_exact - y_tile) * 256)
    px = max(10, min(245, px))
    py = max(20, min(250, py))

    try:
        from io import BytesIO
        from PIL import Image, ImageDraw
        img = Image.open(BytesIO(tile_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Sombra sob o pino
        draw.ellipse((px - 6, py - 3, px + 6, py + 3), fill=(100, 100, 100))

        # Cabeça do pino
        r = 9
        draw.ellipse((px - r, py - r - 10, px + r, py + r - 10), fill=(235, 45, 45), outline=(130, 0, 0), width=2)
        # Bico do pino
        draw.polygon([(px - 7, py - 9), (px + 7, py - 9), (px, py)], fill=(235, 45, 45))
        # Centro branco
        draw.ellipse((px - 3, py - 14, px + 3, py - 8), fill=(255, 255, 255))

        img.save(output_path, "PNG")
        return rel_url
    except Exception:
        try:
            output_path.write_bytes(tile_bytes)
            return rel_url
        except Exception:
            return None


def get_location() -> Dict[str, Any]:
    """Obtém coordenadas de localização geográfica com link do Google Maps e pré-visualização de mapa."""
    if SIMULATE_HARDWARE:
        lat, lon = -23.550520, -46.633308
        maps_url = f"https://maps.google.com/?q={lat},{lon}"
        map_img = _generate_map_preview(lat, lon)
        loc_data = {
            "latitude": lat,
            "longitude": lon,
            "timestamp": datetime.now().isoformat(),
            "maps_url": maps_url,
            "image_url": map_img,
            "provider": "simulated"
        }
        try:
            LAST_LOCATION_FILE.write_text(json.dumps(loc_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return {
            "status": "ok",
            "message": f"Silva: Localização: Lat {lat:.5f}, Lon {lon:.5f}. {maps_url} [Simulado]",
            "image_url": map_img,
            "data": loc_data
        }

    try:
        # Tenta primeiro via network (rápido)
        res = _run_termux_cmd(["termux-location", "-p", "network", "-r", "last"], timeout=10)
        if res.returncode != 0 or not res.stdout.strip():
            # Fallback para GPS
            res = _run_termux_cmd(["termux-location", "-p", "gps", "-r", "once"], timeout=15)

        if res.returncode != 0 or not res.stdout.strip():
            return {"status": "error", "message": "Não foi possível obter sinal de localização."}

        data = json.loads(res.stdout)
        lat = data.get("latitude")
        lon = data.get("longitude")
        if lat is None or lon is None:
            return {"status": "error", "message": "Coordenadas não disponíveis."}

        maps_url = f"https://maps.google.com/?q={lat},{lon}"
        map_img = _generate_map_preview(float(lat), float(lon))
        loc_data = {
            "latitude": float(lat),
            "longitude": float(lon),
            "timestamp": datetime.now().isoformat(),
            "maps_url": maps_url,
            "image_url": map_img,
            "provider": data.get("provider", "termux")
        }
        try:
            LAST_LOCATION_FILE.write_text(json.dumps(loc_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return {
            "status": "ok",
            "message": f"Silva: Localização: Lat {lat:.5f}, Lon {lon:.5f}. {maps_url}",
            "image_url": map_img,
            "data": loc_data
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao consultar GPS: {str(e)}"}


def set_location_state(state: bool) -> Dict[str, Any]:
    """Ativa ou desativa o serviço de localização/GPS do dispositivo."""
    st_bool = bool(state)
    val = "3" if st_bool else "0"
    txt = "ativada" if st_bool else "desativada"

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Localização (GPS) {txt} com sucesso. [Simulado]",
            "data": {"state": st_bool}
        }

    try:
        res = _run_termux_cmd(["settings", "put", "secure", "location_mode", val], timeout=5)
        err_output = ((res.stderr or "") + (res.stdout or "")).lower()
        if res.returncode == 0 and not any(k in err_output for k in ["securityexception", "permission", "error"]):
            return {
                "status": "ok",
                "message": f"Silva: Localização (GPS) {txt} com sucesso.",
                "data": {"state": st_bool}
            }

        # Fallback sem permissão WRITE_SECURE_SETTINGS: abre configurações de localização nativas
        _run_termux_cmd(["am", "start", "-a", "android.settings.LOCATION_SOURCE_SETTINGS"], timeout=5)
        return {
            "status": "ok",
            "message": f"Silva: Abrindo configurações de localização para você {'ativar' if st_bool else 'desativar'}.",
            "data": {"state": st_bool, "fallback": "location_settings"}
        }
    except Exception as e:
        try:
            _run_termux_cmd(["am", "start", "-a", "android.settings.LOCATION_SOURCE_SETTINGS"], timeout=5)
        except Exception:
            pass
        return {
            "status": "ok",
            "message": f"Silva: Abrindo configurações de localização para você {'ativar' if st_bool else 'desativar'}.",
            "data": {"state": st_bool, "error": str(e)}
        }


def get_last_location() -> Dict[str, Any]:
    """Consulta a última localização geográfica registrada offline com card de mapa."""
    if not LAST_LOCATION_FILE.is_file():
        if SIMULATE_HARDWARE:
            lat, lon = -23.550520, -46.633308
            maps_url = f"https://maps.google.com/?q={lat},{lon}"
            map_img = _generate_map_preview(lat, lon)
            dt_fmt = datetime.now().strftime("%d/%m/%Y às %H:%M")
            return {
                "status": "ok",
                "message": f"Silva: Última localização registrada ({dt_fmt}): Lat {lat:.5f}, Lon {lon:.5f}. {maps_url} [Simulado]",
                "image_url": map_img,
                "data": {"latitude": lat, "longitude": lon, "timestamp": datetime.now().isoformat(), "maps_url": maps_url}
            }
        return {
            "status": "ok",
            "message": "Silva: Nenhuma localização registrada anteriormente no dispositivo.",
            "data": {}
        }

    try:
        data = json.loads(LAST_LOCATION_FILE.read_text(encoding="utf-8"))
        lat = data.get("latitude")
        lon = data.get("longitude")
        maps_url = data.get("maps_url", f"https://maps.google.com/?q={lat},{lon}")
        img_url = data.get("image_url")
        ts_str = data.get("timestamp", "")
        dt_fmt = ""
        if ts_str:
            try:
                dt_obj = datetime.fromisoformat(ts_str)
                dt_fmt = dt_obj.strftime("%d/%m/%Y às %H:%M")
            except Exception:
                dt_fmt = ts_str

        time_label = f" em {dt_fmt}" if dt_fmt else ""
        return {
            "status": "ok",
            "message": f"Silva: Última localização registrada{time_label}: Lat {float(lat):.5f}, Lon {float(lon):.5f}. {maps_url}",
            "image_url": img_url,
            "data": data
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao consultar última localização: {str(e)}"}


WMO_WEATHER_CODES = {
    0: "Céu limpo ☀️",
    1: "Predomínio de sol 🌤️",
    2: "Parcialmente nublado ⛅",
    3: "Nublado / Encoberto ☁️",
    45: "Nevoeiro 🌫️",
    48: "Nevoeiro com geada 🌫️",
    51: "Chuvisco leve 🌦️",
    53: "Chuvisco moderado 🌧️",
    55: "Chuvisco intenso 🌧️",
    61: "Chuva fraca 🌧️",
    63: "Chuva moderada 🌧️",
    65: "Chuva forte ⛈️",
    80: "Pancadas de chuva leves 🌦️",
    81: "Pancadas de chuva moderadas 🌧️",
    82: "Pancadas de chuva violentas ⛈️",
    95: "Tempestade com trovoadas ⛈️",
    96: "Tempestade com granizo leve ⛈️",
    99: "Tempestade com granizo pesado ⛈️"
}


def get_weather(day: str = "hoje", time: str = "", location: str = "") -> Dict[str, Any]:
    """Consulta previsão do tempo detalhada por dia, horário e cidade via Open-Meteo."""
    day_raw = str(day).strip().lower() if day else "hoje"
    time_raw = str(time).strip().lower() if time else ""
    loc_raw = str(location).strip() if location else ""

    if SIMULATE_HARDWARE:
        city_disp = loc_raw or "sua localização"
        t_label = f" às {time_raw}" if time_raw else ""
        return {
            "status": "ok",
            "message": f"Silva: Previsão do tempo para {city_disp} ({day_raw}{t_label}): Parcialmente nublado ⛅. Temperatura 28.5°C, chance de chuva de 25%. [Simulado]",
            "data": {"day": day_raw, "time": time_raw, "location": city_disp, "condition": "Parcialmente nublado", "temperature": 28.5, "rain_probability": 25}
        }

    # 1. Determina Coordenadas e Nome do Local
    lat, lon, city_name = None, None, None
    if loc_raw and not any(loc_raw.lower() == k for k in ["aqui", "minha cidade", "minha localizacao", "localizacao atual", "local"]):
        try:
            url_geo = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote_plus(loc_raw)}&count=1&language=pt"
            req_geo = urllib.request.Request(url_geo, headers={"User-Agent": "SilvaAgent/1.0"})
            with urllib.request.urlopen(req_geo, timeout=4.0) as resp:
                geo_data = json.loads(resp.read().decode())
                if geo_data.get("results"):
                    first = geo_data["results"][0]
                    lat = float(first["latitude"])
                    lon = float(first["longitude"])
                    city_name = first.get("name", loc_raw)
        except Exception:
            pass

    if lat is None or lon is None:
        if LAST_LOCATION_FILE.is_file():
            try:
                cached = json.loads(LAST_LOCATION_FILE.read_text(encoding="utf-8"))
                lat = float(cached["latitude"])
                lon = float(cached["longitude"])
                city_name = "sua localização"
            except Exception:
                pass

    if lat is None or lon is None:
        lat, lon, city_name = -7.9408, -34.8730, "Paulista"

    city_name = city_name or loc_raw or "sua localização"

    # 2. Resolução da Data Alvo
    today = date.today()
    target_date = today
    day_display = "hoje"

    weekdays_map = {
        "segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3,
        "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6
    }

    if "amanha" in day_raw or "amanhã" in day_raw:
        if "depois" in day_raw:
            target_date = today + timedelta(days=2)
            day_display = "depois de amanhã"
        else:
            target_date = today + timedelta(days=1)
            day_display = "amanhã"
    else:
        for wname, wday in weekdays_map.items():
            if wname in day_raw:
                diff = (wday - today.weekday()) % 7
                if diff == 0 and ("proxim" in day_raw or "que vem" in day_raw):
                    diff = 7
                elif diff == 0:
                    diff = 7
                target_date = today + timedelta(days=diff)
                day_display = wname.capitalize()
                break

    # 3. Resolução do Horário Alvo (se fornecido)
    target_hour = None
    if time_raw:
        if "noite" in time_raw:
            target_hour = 20
        elif "tarde" in time_raw:
            target_hour = 15
        elif "manha" in time_raw or "manhã" in time_raw:
            target_hour = 9
        elif "madrugada" in time_raw:
            target_hour = 3
        else:
            m_h = re.search(r"(\d{1,2})", time_raw)
            if m_h:
                h_val = int(m_h.group(1))
                if 0 <= h_val <= 23:
                    target_hour = h_val

    # 4. Consulta API Open-Meteo
    try:
        url_forecast = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,precipitation_probability,weathercode"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode"
            f"&timezone=auto"
        )
        req_w = urllib.request.Request(url_forecast, headers={"User-Agent": "SilvaAgent/1.0"})
        with urllib.request.urlopen(req_w, timeout=5.0) as resp:
            data_w = json.loads(resp.read().decode())

        if target_hour is not None:
            target_prefix = f"{target_date.isoformat()}T{target_hour:02d}:"
            hourly_times = data_w.get("hourly", {}).get("time", [])
            match_idx = None
            for i, ht in enumerate(hourly_times):
                if ht.startswith(target_prefix):
                    match_idx = i
                    break

            if match_idx is not None:
                temp = data_w["hourly"]["temperature_2m"][match_idx]
                rain_prob = data_w["hourly"]["precipitation_probability"][match_idx]
                wcode = data_w["hourly"]["weathercode"][match_idx]
                cond = WMO_WEATHER_CODES.get(wcode, "Tempo instável")

                msg = f"Silva: Previsão para {city_name} em {day_display} às {target_hour:02d}:00: {cond}. Temperatura de {temp:.1f}°C e chance de chuva de {rain_prob}%."
                return {
                    "status": "ok",
                    "message": msg,
                    "data": {
                        "location": city_name,
                        "day": day_display,
                        "time": f"{target_hour:02d}:00",
                        "condition": cond,
                        "temperature": temp,
                        "precipitation_probability": rain_prob
                    }
                }

        # Previsão diária geral
        daily_times = data_w.get("daily", {}).get("time", [])
        day_str = target_date.isoformat()
        day_idx = 0
        for i, dt in enumerate(daily_times):
            if dt == day_str:
                day_idx = i
                break

        t_max = data_w["daily"]["temperature_2m_max"][day_idx]
        t_min = data_w["daily"]["temperature_2m_min"][day_idx]
        rain_max = data_w["daily"]["precipitation_probability_max"][day_idx]
        wcode = data_w["daily"]["weathercode"][day_idx]
        cond = WMO_WEATHER_CODES.get(wcode, "Tempo instável")

        msg = f"Silva: Previsão do tempo para {city_name} ({day_display}): {cond}. Mínima de {t_min:.1f}°C, máxima de {t_max:.1f}°C e probabilidade máxima de chuva de {rain_max}%."
        return {
            "status": "ok",
            "message": msg,
            "data": {
                "location": city_name,
                "day": day_display,
                "condition": cond,
                "temp_min": t_min,
                "temp_max": t_max,
                "precipitation_probability_max": rain_max
            }
        }
    except Exception as e:
        return {
            "status": "ok",
            "message": f"Silva: Não foi possível obter previsão online no momento ({str(e)}). Verifique a conexão com a internet.",
            "data": {"day": day_raw, "time": time_raw, "location": city_name, "error": str(e)}
        }


def set_torch(state: bool) -> Dict[str, Any]:
    """Liga ou desliga a lanterna."""
    state_bool = bool(state)
    param = "on" if state_bool else "off"

    if SIMULATE_HARDWARE:
        txt = "acesa" if state_bool else "apagada"
        return {
            "status": "ok",
            "message": f"Silva: Lanterna {txt}. [Simulado]",
            "data": {"state": state_bool}
        }

    try:
        res = _run_termux_cmd(["termux-torch", param], timeout=5)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao acionar lanterna: {res.stderr.strip()}"}
        txt = "ligada" if state_bool else "desligada"
        return {
            "status": "ok",
            "message": f"Silva: Lanterna {txt}.",
            "data": {"state": state_bool}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro na lanterna: {str(e)}"}


def set_dnd(state: bool) -> Dict[str, Any]:
    """
    Ativa ou desativa o modo Não Perturbe (DND) / Silencioso.
    Tenta primeiro via comando de sistema Android ('cmd notification set_dnd').
    Fallback sem root / sem ADB: ajusta e restaura volumes com termux-volume.
    """
    state_bool = bool(state)
    dnd_state_str = "on" if state_bool else "off"
    action_pt = "ativado" if state_bool else "desativado"

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Modo Não Perturbe {action_pt}. [Simulado]",
            "data": {"state": state_bool}
        }

    # Arquivo de backup dos volumes para restauração quando DND for desativado
    backup_file = DATA_DIR / "dnd_backup.json"

    # Tentativa 1: cmd notification set_dnd on|off (nativo Android)
    try:
        res_cmd = _run_termux_cmd(["cmd", "notification", "set_dnd", dnd_state_str], timeout=4)
        out_err = (res_cmd.stderr or "") + (res_cmd.stdout or "")
        if res_cmd.returncode == 0 and "SecurityException" not in out_err and "Permission" not in out_err:
            return {
                "status": "ok",
                "message": f"Silva: Modo Não Perturbe {action_pt}.",
                "data": {"state": state_bool, "method": "cmd_notification"}
            }
    except Exception:
        pass

    # Fallback garantido: controle de canais via termux-volume
    target_streams = ["ring", "notification", "system"]
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if state_bool:
            # Salva volumes atuais antes de silenciar
            res_vol = _run_termux_cmd(["termux-volume"], timeout=5)
            backup_data = {}
            if res_vol.returncode == 0 and res_vol.stdout.strip():
                try:
                    streams = json.loads(res_vol.stdout)
                    for item in streams:
                        s_name = item.get("stream")
                        if s_name in target_streams:
                            backup_data[s_name] = item.get("volume", 5)
                except Exception:
                    pass

            # Caso não tenha lido os volumes, define padrão seguro para restauração futura
            for s in target_streams:
                if s not in backup_data:
                    backup_data[s] = 5

            try:
                backup_file.write_text(json.dumps(backup_data), encoding="utf-8")
            except Exception:
                pass

            # Silencia os canais de alerta
            for s in target_streams:
                _run_termux_cmd(["termux-volume", s, "0"], timeout=3)

            return {
                "status": "ok",
                "message": "Silva: Modo Não Perturbe ativado (volumes de toque e notificações silenciados).",
                "data": {"state": True, "method": "termux_volume"}
            }
        else:
            # Restaura os volumes anteriores
            restored_data = {}
            if backup_file.is_file():
                try:
                    restored_data = json.loads(backup_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            for s in target_streams:
                vol_to_set = restored_data.get(s, 5)
                _run_termux_cmd(["termux-volume", s, str(vol_to_set)], timeout=3)

            # Remove arquivo temporário após restauração
            if backup_file.is_file():
                try:
                    backup_file.unlink()
                except Exception:
                    pass

            return {
                "status": "ok",
                "message": "Silva: Modo Não Perturbe desativado (volumes restaurados).",
                "data": {"state": False, "method": "termux_volume"}
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro ao configurar Modo Não Perturbe: {str(e)}",
            "data": {"state": state_bool}
        }


def vibrate(duration_ms: int = 500) -> Dict[str, Any]:
    """Faz o telefone vibrar pelo tempo determinado."""
    dur = max(50, min(int(duration_ms), 5000))

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Vibração acionada por {dur}ms. [Simulado]",
            "data": {"duration_ms": dur}
        }

    try:
        res = _run_termux_cmd(["termux-vibrate", "-d", str(dur)], timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao vibrar: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: Dispositivo vibrou ({dur}ms).",
            "data": {"duration_ms": dur}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao acionar vibração: {str(e)}"}


def get_clipboard() -> Dict[str, Any]:
    """Lê o conteúdo da área de transferência."""
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": "Silva: Conteúdo da área de transferência lido com sucesso. [Simulado]",
            "data": {"clipboard": "https://github.com/silva-agent"}
        }

    try:
        res = _run_termux_cmd(["termux-clipboard-get"], timeout=5)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao ler clipboard: {res.stderr.strip()}"}
        content = res.stdout
        preview = (content[:80] + "...") if len(content) > 80 else content
        return {
            "status": "ok",
            "message": f"Silva: Área de transferência: '{preview}'" if preview else "Silva: Área de transferência vazia.",
            "data": {"clipboard": content}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao ler clipboard: {str(e)}"}


def set_clipboard(text: str) -> Dict[str, Any]:
    """Escreve um texto na área de transferência."""
    txt = str(text)
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": "Silva: Texto copiado para a área de transferência. [Simulado]",
            "data": {"clipboard": txt}
        }

    try:
        # Usa input via stdin para evitar problemas de escaping
        proc = subprocess.run(
            ["termux-clipboard-set"],
            input=txt,
            text=True,
            capture_output=True,
            timeout=5
        )
        if proc.returncode != 0:
            return {"status": "error", "message": f"Falha ao gravar no clipboard: {proc.stderr.strip()}"}
        return {
            "status": "ok",
            "message": "Silva: Texto copiado para a área de transferência.",
            "data": {"clipboard": txt}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao copiar para clipboard: {str(e)}"}


JOKES_PTBR = [
    "Por que o computador foi ao médico? Porque ele estava com um vírus!",
    "Existem 10 tipos de pessoas no mundo: as que entendem binário e as que não entendem.",
    "O que o botão zero disse para o botão um? 'Você está no meu espaço!'.",
    "Por que os programadores preferem o modo escuro? Porque a luz atrai bugs!",
    "Qual é o café favorito do desenvolvedor? O Java.",
    "O que a chave de fenda foi fazer no baile? Foi desenroscar os passos.",
    "Por que o livro de matemática ficou triste? Porque tinha problemas demais.",
    "O que uma impressora disse para a outra? 'Essa folha é sua ou é impressão minha?'.",
    "Qual é o cúmulo da paciência? Jogar xadrez contra o espelho e esperar a jogada do adversário.",
    "Por que o JavaScript foi ao psicólogo? Porque ele tinha problemas de escopo e não se sentia definido.",
    "O que o pato disse para a pata? 'Vem quá!'.",
    "Qual é o peixe que caiu do décimo andar? Aaaaatum!",
    "O que o zero disse para o oito? 'Belo cinto!'",
    "Por que o esqueleto não brigou com ninguém? Porque ele não tinha estômago para isso.",
    "Qual é o animal que não vale mais nada? O javali.",
    "Por que o desenvolvedor não gosta de florestas? Tem muitos bugs e pouca memória ram.",
    "O que o tomate foi fazer no banco? Foi tirar o extrato.",
    "Como as estrelas lavam o cabelo? Com Milky Way.",
    "Por que o alarme do celular tocou feliz hoje? Porque acordou com disposição!",
    "O que o Wi-Fi disse para o smartphone? 'Sinto uma forte conexão entre nós'.",
    "Qual a fórmula da água benta? H Deus O.",
    "Por que a aranha é o animal mais conectado do mundo? Porque vive na web.",
    "O que o ponto de exclamação falou pro de interrogação? 'Nossa, que cara curioso você é!'.",
    "Como se chama uma cobra que resolve equações? Uma píton (Python) matemática.",
    "Por que o banco de dados terminou o namoro? Porque não aguentava mais queries e relacionamentos complicados.",
    "O que um algoritmo disse para o outro? 'Siga meus passos!'.",
    "Qual é a cidade que não tem táxi? Uberlândia."
]

_LAST_JOKE: Optional[str] = None


def tell_joke() -> Dict[str, Any]:
    """Retorna uma piada curta aleatória em Português do Brasil sem repetir consecutivamente."""
    global _LAST_JOKE
    candidates = [j for j in JOKES_PTBR if j != _LAST_JOKE] if len(JOKES_PTBR) > 1 else JOKES_PTBR
    chosen = random.choice(candidates)
    _LAST_JOKE = chosen
    return {
        "status": "ok",
        "message": f"Silva: {chosen}",
        "data": {"joke": chosen}
    }


MONTHS_PTBR = {
    "janeiro": 1, "jan": 1,
    "fevereiro": 2, "fev": 2,
    "março": 3, "marco": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "maio": 5, "mai": 5,
    "junho": 6, "jun": 6,
    "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9,
    "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}


def parse_ptbr_date(date_str: str) -> date:
    """
    Converte expressões de data em Português do Brasil para um objeto datetime.date real.
    Suporta: 'hoje', 'amanhã', 'depois de amanhã', dias da semana ('segunda', 'sexta-feira', etc.),
    datas por extenso ('29 de novembro', 'dia 29 de novembro deste ano', '15 de janeiro de 2027')
    e formatos 'DD/MM', 'DD/MM/AAAA' e 'AAAA-MM-DD'.
    """
    raw = (date_str or "").strip().lower()
    today = date.today()

    if not raw or raw in ("hoje", "today"):
        return today
    if raw in ("amanhã", "amanha", "tomorrow"):
        return today + timedelta(days=1)
    if raw in ("depois de amanhã", "depois de amanha"):
        return today + timedelta(days=2)

    # Dias da semana
    weekdays = {
        "segunda": 0, "segunda-feira": 0,
        "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1,
        "quarta": 2, "quarta-feira": 2,
        "quinta": 3, "quinta-feira": 3,
        "sexta": 4, "sexta-feira": 4,
        "sábado": 5, "sabado": 5,
        "domingo": 6,
    }
    for w_name, w_idx in weekdays.items():
        if raw == w_name or raw.startswith(f"próxima {w_name}") or raw.startswith(f"proxima {w_name}"):
            days_ahead = (w_idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    # Data por extenso em português: "29 de novembro", "dia 29 de novembro deste ano", "15 de janeiro de 2027"
    m_ext = re.search(r"(?:dia\s+)?(\d{1,2})\s+de\s+([a-zç]+)(?:\s+de\s+(\d{2,4})|\s+deste\s+ano)?", raw)
    if m_ext:
        day = int(m_ext.group(1))
        month_name = m_ext.group(2)
        month = MONTHS_PTBR.get(month_name)
        if month:
            year_str = m_ext.group(3)
            year = int(year_str) if year_str else today.year
            if year < 100:
                year += 2000
            try:
                target_date = date(year, month, day)
                # Se o ano não foi informado e nem veio "deste ano", caso a data já tenha passado usa o próximo ano
                if not year_str and "deste ano" not in raw and target_date < today:
                    target_date = date(year + 1, month, day)
                return target_date
            except ValueError:
                return today

    # Padrão DD/MM ou DD/MM/AAAA
    match_br = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", raw)
    if match_br:
        day = int(match_br.group(1))
        month = int(match_br.group(2))
        year_str = match_br.group(3)
        year = int(year_str) if year_str else today.year
        if year < 100:
            year += 2000
        try:
            target_date = date(year, month, day)
            if not year_str and target_date < today:
                target_date = date(year + 1, month, day)
            return target_date
        except ValueError:
            return today

    # Padrão ISO YYYY-MM-DD
    match_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", raw)
    if match_iso:
        try:
            return date(int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3)))
        except ValueError:
            return today

    return today


def parse_time_str(time_str: str) -> tuple[int, int]:
    """Extrai (hora, minuto) de strings como '07:30', '7:30', '7h', '7h30' ou '14:00'."""
    raw = (time_str or "").strip().lower()
    if not raw:
        return (9, 0)

    # Formato HH:MM
    match_colon = re.search(r"(\d{1,2}):(\d{2})", raw)
    if match_colon:
        h, m = int(match_colon.group(1)), int(match_colon.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    # Formato 7h, 7h30, 14h00
    match_h = re.search(r"(\d{1,2})h(?:(\d{2}))?", raw)
    if match_h:
        h = int(match_h.group(1))
        m = int(match_h.group(2)) if match_h.group(2) else 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    # Apenas dígitos de hora (ex: '7')
    match_num = re.search(r"^\d{1,2}$", raw)
    if match_num:
        h = int(raw)
        if 0 <= h <= 23:
            return (h, 0)

    return (9, 0)


def set_alarm(time: str, label: str = "", days: str = "") -> Dict[str, Any]:
    """Define um alarme no relógio nativo do Android via Intent."""
    hour, minute = parse_time_str(time)
    formatted_time = f"{hour:02d}:{minute:02d}"
    label_clean = str(label).strip()
    days_clean = str(days).strip()

    if SIMULATE_HARDWARE:
        lbl_msg = f" com o rótulo '{label_clean}'" if label_clean else ""
        return {
            "status": "ok",
            "message": f"Silva: Alarme definido para {formatted_time}{lbl_msg}. [Simulado]",
            "data": {"hour": hour, "minute": minute, "time": formatted_time, "label": label_clean, "days": days_clean}
        }

    cmd = [
        "am", "start",
        "-a", "android.intent.action.SET_ALARM",
        "--ei", "android.intent.extra.alarm.HOUR", str(hour),
        "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    if label_clean:
        cmd.extend(["--es", "android.intent.extra.alarm.MESSAGE", label_clean])

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao definir alarme: {res.stderr.strip()}"}
        lbl_msg = f" com o rótulo '{label_clean}'" if label_clean else ""
        return {
            "status": "ok",
            "message": f"Silva: Alarme definido para {formatted_time}{lbl_msg}.",
            "data": {"hour": hour, "minute": minute, "time": formatted_time, "label": label_clean, "days": days_clean}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao definir alarme: {str(e)}"}


def cancel_alarm(time: str = "", day: str = "", label: str = "") -> Dict[str, Any]:
    """Cancela ou descarta um alarme no Android via Intent."""
    time_clean = str(time).strip()
    label_clean = str(label).strip()
    day_clean = str(day).strip()

    target_desc = []
    if time_clean:
        target_desc.append(f"das {time_clean}")
    if day_clean:
        target_desc.append(f"de {day_clean}")
    if label_clean:
        target_desc.append(f"'{label_clean}'")
    desc_str = " ".join(target_desc) if target_desc else "ativo"

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Alarme {desc_str} cancelado com sucesso. [Simulado]",
            "data": {"time": time_clean, "day": day_clean, "label": label_clean}
        }

    cmd = [
        "am", "start",
        "-a", "android.intent.action.DISMISS_ALARM",
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    if time_clean:
        h, m = parse_time_str(time_clean)
        cmd.extend([
            "--ei", "android.intent.extra.alarm.HOUR", str(h),
            "--ei", "android.intent.extra.alarm.MINUTES", str(m)
        ])
    if label_clean:
        cmd.extend(["--es", "android.intent.extra.alarm.MESSAGE", label_clean])

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao cancelar alarme: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: Alarme {desc_str} cancelado com sucesso.",
            "data": {"time": time_clean, "day": day_clean, "label": label_clean}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao cancelar alarme: {str(e)}"}


def schedule_event(title: str, date: str = "", time: str = "") -> Dict[str, Any]:
    """Cria um compromisso na agenda local do Silva e abre diretamente no Calendário Samsung sem diálogo de escolha."""
    title_clean = str(title).strip()
    if not title_clean:
        return {"status": "error", "message": "Título do compromisso não informado."}

    target_date = parse_ptbr_date(date)
    hour, minute = parse_time_str(time)
    dt_event = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
    begin_ms = int(dt_event.timestamp() * 1000)
    end_ms = begin_ms + (3600 * 1000)  # +1 hora
    event_ts = int(dt_event.timestamp())

    formatted_date = target_date.strftime("%d/%m/%Y")
    formatted_time = f"{hour:02d}:{minute:02d}"
    event_id = str(uuid.uuid4())[:8]

    # 1. Persistência real na Agenda Local (android_agent/data/events.json)
    event_record = {
        "id": event_id,
        "title": title_clean,
        "date": target_date.strftime("%Y-%m-%d"),
        "time": formatted_time,
        "timestamp": event_ts,
        "notified": False
    }
    events = _load_events()
    events.append(event_record)
    _save_events(events)

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Compromisso '{title_clean}' salvo na agenda do Silva para {formatted_date} às {formatted_time} (e aberto no Calendário Samsung para confirmar, se desejar). [Simulado]",
            "data": {
                "id": event_id,
                "title": title_clean,
                "date": target_date.strftime("%Y-%m-%d"),
                "time": formatted_time,
                "begin_ms": begin_ms,
                "end_ms": end_ms
            }
        }

    # 2. Intent direta para o Calendário Samsung (evitando pop-up do Outlook)
    cmd = [
        "am", "start",
        "-a", "android.intent.action.INSERT",
        "-t", "vnd.android.cursor.item/event",
        "-d", "content://com.android.calendar/events",
        "-p", "com.samsung.android.calendar",
        "--es", "title", title_clean,
        "--el", "beginTime", str(begin_ms),
        "--el", "endTime", str(end_ms)
    ]

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            # Fallback sem a flag -p caso o Calendário Samsung não esteja presente
            fallback_cmd = [
                "am", "start",
                "-a", "android.intent.action.INSERT",
                "-t", "vnd.android.cursor.item/event",
                "-d", "content://com.android.calendar/events",
                "--es", "title", title_clean,
                "--el", "beginTime", str(begin_ms),
                "--el", "endTime", str(end_ms)
            ]
            _run_termux_cmd(fallback_cmd, timeout=6)
    except Exception:
        pass

    return {
        "status": "ok",
        "message": f"Silva: Compromisso '{title_clean}' salvo na agenda do Silva para {formatted_date} às {formatted_time} (e aberto no Calendário Samsung para confirmar, se desejar).",
        "data": {
            "id": event_id,
            "title": title_clean,
            "date": target_date.strftime("%Y-%m-%d"),
            "time": formatted_time,
            "begin_ms": begin_ms,
            "end_ms": end_ms
        }
    }


DATA_DIR = Path(__file__).resolve().parent / "data"
MEMORY_FILE = DATA_DIR / "memory.json"


def _load_memory() -> dict:
    if not MEMORY_FILE.is_file():
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_memory(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def remember_note(key: str, value: str) -> Dict[str, Any]:
    """Salva/atualiza uma anotação persistente na memória local do Silva."""
    clean_key = str(key).strip()
    clean_val = str(value).strip()
    if not clean_key or not clean_val:
        return {"status": "error", "message": "Chave ou valor da anotação não informados."}

    mem = _load_memory()
    mem[clean_key] = {
        "value": clean_val,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    _save_memory(mem)
    return {
        "status": "ok",
        "message": f"Silva: Anotado: {clean_key} = {clean_val}.",
        "data": {"key": clean_key, "value": clean_val}
    }


def recall_note(query: str) -> Dict[str, Any]:
    """Busca anotações e compromissos salvos na memória/agenda local por similaridade semântica e palavras-chave."""
    clean_query = str(query).strip()
    if not clean_query:
        return {"status": "error", "message": "Termo de busca não informado."}

    norm_query = _normalize_text(clean_query)
    query_tokens = set(norm_query.split())

    # 1. Busca em memória (memory.json)
    mem = _load_memory()
    matches = []
    if mem:
        for k, v_data in mem.items():
            val = v_data.get("value", "") if isinstance(v_data, dict) else str(v_data)
            norm_k = _normalize_text(k)
            norm_v = _normalize_text(val)

            score = 0
            if norm_query == norm_k:
                score += 10
            elif norm_query in norm_k:
                score += 6
            elif norm_k in norm_query:
                score += 5

            # Intersecção de palavras-chave
            k_tokens = set(norm_k.split())
            common = query_tokens.intersection(k_tokens)
            if common:
                score += len(common) * 2

            if norm_query in norm_v:
                score += 3

            if score > 0:
                matches.append((score, k, val))

    # 2. Busca em compromissos da agenda (events.json)
    events = _load_events()
    event_matches = []
    if events:
        is_agenda_query = any(w in norm_query for w in ["agenda", "compromisso", "compromissos", "evento", "eventos", "reuniao", "lembrete", "lembretes"])
        for ev in events:
            ev_title = ev.get("title", "")
            ev_date = ev.get("date", "")
            ev_time = ev.get("time", "")
            norm_title = _normalize_text(ev_title)
            if is_agenda_query or norm_query in norm_title or norm_title in norm_query or query_tokens.intersection(set(norm_title.split())):
                event_matches.append(f"'{ev_title}' em {ev_date} às {ev_time}")

    if not matches and not event_matches:
        return {
            "status": "ok",
            "message": f"Silva: Nenhuma anotação ou compromisso encontrado sobre '{clean_query}'.",
            "data": {"found": False, "query": clean_query}
        }

    parts = []
    if matches:
        matches.sort(key=lambda x: x[0], reverse=True)
        best_matches = matches[:3]
        notes_str = "; ".join(f"{k}: {val}" for _, k, val in best_matches)
        parts.append(f"Memória: {notes_str}")
    if event_matches:
        ev_str = "; ".join(event_matches[:4])
        parts.append(f"Agenda: {ev_str}")

    msg = "Silva: " + " | ".join(parts) + "."

    return {
        "status": "ok",
        "message": msg,
        "data": {
            "found": True,
            "notes": [{"key": k, "value": v} for _, k, v in matches[:3]] if matches else [],
            "events": event_matches
        }
    }


def get_notifications(app: str = "") -> Dict[str, Any]:
    """Lê as notificações recentes do Android filtrando opcionalmente por app."""
    app_filter = str(app).strip().lower()

    if SIMULATE_HARDWARE:
        sim_notifs = [
            {"app": "WhatsApp", "title": "Mariana", "content": "Não esquece do documento amanhã!"},
            {"app": "Nubank", "title": "Transferência Recebida", "content": "Você recebeu R$ 150,00 de Carlos."},
            {"app": "Gmail", "title": "Alerta de Segurança", "content": "Novo login detectado."},
            {"app": "Instagram", "title": "Novo seguidor", "content": "lucas_dev começou a seguir você."}
        ]
        if app_filter:
            sim_notifs = [n for n in sim_notifs if app_filter in n["app"].lower() or app_filter in n["title"].lower()]

        if not sim_notifs:
            msg = f"Silva: Nenhuma notificação recente{f' do app {app_filter}' if app_filter else ''}. [Simulado]"
            return {"status": "ok", "message": msg, "data": []}

        formatted = [f"[{n['app']}] {n['title']}: {n['content']}" for n in sim_notifs[:5]]
        msg = "Silva: Notificações recentes:\n" + "\n".join(formatted) + " [Simulado]"
        return {"status": "ok", "message": msg, "data": sim_notifs[:5]}

    try:
        res = _run_termux_cmd(["termux-notification-list"], timeout=8)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao ler notificações: {res.stderr.strip()}"}

        notifs = json.loads(res.stdout) if res.stdout.strip() else []
        filtered = []
        for n in notifs:
            pkg = n.get("packageName", "").lower()
            appName = n.get("appName", "").lower()
            title = n.get("title", "")
            content = n.get("content", "")
            display_app = n.get("appName") or n.get("packageName", "App")

            if app_filter:
                if app_filter not in pkg and app_filter not in appName and app_filter not in title.lower():
                    continue

            filtered.append({
                "app": display_app,
                "title": title,
                "content": content
            })

        if not filtered:
            msg = f"Silva: Nenhuma notificação encontrada{f' para o aplicativo {app_filter}' if app_filter else ''}."
            return {"status": "ok", "message": msg, "data": []}

        formatted = [f"[{item['app']}] {item['title']}: {item['content']}" for item in filtered[:5]]
        msg = f"Silva: {len(filtered[:5])} notificação(ões) recente(s):\n" + "\n".join(formatted)
        return {"status": "ok", "message": msg, "data": filtered[:5]}
    except Exception as e:
        return {"status": "error", "message": f"Erro ao acessar notificações: {str(e)}"}


def set_volume(stream: str = "media", level: int = 50) -> Dict[str, Any]:
    """Ajusta o volume do stream especificado em porcentagem (0 a 100%)."""
    raw_stream = str(stream).strip().lower()
    stream_map = {
        "media": "music", "mídia": "music", "midia": "music", "musica": "music", "música": "music",
        "ring": "ring", "toque": "ring", "chamada": "ring",
        "notification": "notification", "notificacao": "notification", "notificação": "notification",
        "alarm": "alarm", "alarme": "alarm",
        "system": "system", "sistema": "system",
        "call": "call", "voz": "call"
    }
    target_stream = stream_map.get(raw_stream, "music")
    level_pct = max(0, min(int(level), 100))

    if SIMULATE_HARDWARE:
        max_vol = 15
        calc_vol = round((level_pct / 100.0) * max_vol)
        return {
            "status": "ok",
            "message": f"Silva: Volume de '{raw_stream}' ajustado para {level_pct}% ({calc_vol}/{max_vol}). [Simulado]",
            "data": {"stream": target_stream, "level_pct": level_pct, "volume": calc_vol, "max_volume": max_vol}
        }

    try:
        max_vol = 15
        res_info = _run_termux_cmd(["termux-volume"], timeout=5)
        if res_info.returncode == 0 and res_info.stdout.strip():
            try:
                streams_info = json.loads(res_info.stdout)
                for s in streams_info:
                    if s.get("stream") == target_stream:
                        max_vol = s.get("max_volume", 15)
                        break
            except Exception:
                pass

        calc_vol = round((level_pct / 100.0) * max_vol)
        res_set = _run_termux_cmd(["termux-volume", target_stream, str(calc_vol)], timeout=5)
        if res_set.returncode != 0:
            return {"status": "error", "message": f"Falha ao definir volume: {res_set.stderr.strip()}"}

        return {
            "status": "ok",
            "message": f"Silva: Volume de '{raw_stream}' ajustado para {level_pct}% ({calc_vol}/{max_vol}).",
            "data": {"stream": target_stream, "level_pct": level_pct, "volume": calc_vol, "max_volume": max_vol}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao ajustar volume: {str(e)}"}


def set_brightness(level: int) -> Dict[str, Any]:
    """Ajusta o brilho da tela do smartphone de 0 a 100%."""
    level_pct = max(0, min(int(level), 100))
    val_255 = round((level_pct / 100.0) * 255)

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Brilho da tela ajustado para {level_pct}% ({val_255}/255). [Simulado]",
            "data": {"level_pct": level_pct, "brightness_255": val_255}
        }

    try:
        res = _run_termux_cmd(["termux-brightness", str(val_255)], timeout=5)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao ajustar brilho: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: Brilho da tela ajustado para {level_pct}%.",
            "data": {"level_pct": level_pct, "brightness_255": val_255}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao ajustar brilho: {str(e)}"}


def set_timer(minutes: int, label: str = "") -> Dict[str, Any]:
    """Inicia um cronômetro/timer no relógio nativo do Android."""
    mins = max(1, int(minutes))
    seconds = mins * 60
    clean_label = str(label).strip()

    if SIMULATE_HARDWARE:
        lbl_msg = f" ({clean_label})" if clean_label else ""
        return {
            "status": "ok",
            "message": f"Silva: Timer de {mins} minuto(s){lbl_msg} iniciado. [Simulado]",
            "data": {"minutes": mins, "seconds": seconds, "label": clean_label}
        }

    cmd = [
        "am", "start",
        "-a", "android.intent.action.SET_TIMER",
        "--ei", "android.intent.extra.alarm.LENGTH", str(seconds),
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    if clean_label:
        cmd.extend(["--es", "android.intent.extra.alarm.MESSAGE", clean_label])

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao iniciar timer: {res.stderr.strip()}"}
        lbl_msg = f" para '{clean_label}'" if clean_label else ""
        return {
            "status": "ok",
            "message": f"Silva: Timer de {mins} minuto(s){lbl_msg} iniciado.",
            "data": {"minutes": mins, "seconds": seconds, "label": clean_label}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao iniciar timer: {str(e)}"}


class SafeMathEvaluator(ast.NodeVisitor):
    ALLOWED_OPERATORS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    def visit(self, node):
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        raise ValueError(f"Operação não permitida na calculadora: {node.__class__.__name__}")

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Apenas valores numéricos são permitidos.")

    def visit_UnaryOp(self, node):
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Operador unário não suportado: {op_type.__name__}")
        operand = self.visit(node.operand)
        return self.ALLOWED_OPERATORS[op_type](operand)

    def visit_BinOp(self, node):
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Operador binário não suportado: {op_type.__name__}")
        left = self.visit(node.left)
        right = self.visit(node.right)

        if op_type is ast.Pow:
            if abs(right) > 1000:
                raise ValueError("Expoente muito grande (limite: 1000).")

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Divisão por zero não é permitida.")

        return self.ALLOWED_OPERATORS[op_type](left, right)


def calculate(expression: str) -> Dict[str, Any]:
    """Calculadora matemática offline segura baseada em AST (sem eval)."""
    expr_clean = str(expression).strip()
    if not expr_clean:
        return {"status": "error", "message": "Expressão matemática vazia."}

    normalized = expr_clean.replace("x", "*").replace("X", "*").replace("÷", "/").replace(",", ".")

    try:
        tree = ast.parse(normalized, mode="eval")
        evaluator = SafeMathEvaluator()
        result = evaluator.visit(tree)

        if isinstance(result, float) and result.is_integer():
            result_fmt = str(int(result))
        elif isinstance(result, float):
            result_fmt = f"{result:.4f}".rstrip("0").rstrip(".")
        else:
            result_fmt = str(result)

        return {
            "status": "ok",
            "message": f"Silva: O resultado de {expr_clean} é {result_fmt}.",
            "data": {"expression": expr_clean, "result": result, "result_formatted": result_fmt}
        }
    except ZeroDivisionError:
        return {"status": "error", "message": "Erro de cálculo: Divisão por zero."}
    except Exception as e:
        return {"status": "error", "message": f"Não foi possível calcular '{expr_clean}': {str(e)}"}


def search_google(query: str) -> Dict[str, Any]:
    """
    Pesquisa um termo no Google, abrindo no navegador do celular
    e retornando um resumo rápido do primeiro resultado se disponível.
    """
    clean_query = str(query).strip()
    if not clean_query:
        return {"status": "error", "message": "Termo de busca não especificado."}

    encoded_query = urllib.parse.quote_plus(clean_query)
    search_url = f"https://www.google.com/search?q={encoded_query}"

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Pesquisando '{clean_query}' no Google: {search_url} [Simulado]",
            "data": {
                "query": clean_query,
                "url": search_url,
                "snippet": None
            }
        }

    try:
        # Dispara Intent nativa para abrir no navegador padrão do Android
        _run_termux_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", search_url], timeout=6)
    except Exception:
        pass

    # Resumo rápido para o chat web via DuckDuckGo HTML lite (best-effort, timeout 3s)
    snippet = None
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        req = urllib.request.Request(
            ddg_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
            }
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        snippets = re.findall(r'class=[\"\'][^\"\']*result__snippet[^\"\']*[\"\'][^>]*>(.*?)</a>', content, re.DOTALL)
        if not snippets:
            snippets = re.findall(r'class=[\"\'][^\"\']*snippet[^\"\']*[\"\'][^>]*>(.*?)</(?:td|div|span|a)>', content, re.DOTALL)

        if snippets:
            clean_snip = html.unescape(re.sub(r'<[^>]+>', '', snippets[0])).strip()
            if clean_snip:
                snippet = clean_snip[:280]
    except Exception:
        snippet = None

    if snippet:
        msg = f"Silva: Pesquisando '{clean_query}' no Google.\n\n💡 Resumo: {snippet}\n\n{search_url}"
    else:
        msg = f"Silva: Pesquisando '{clean_query}' no Google: {search_url}"

    return {
        "status": "ok",
        "message": msg,
        "data": {
            "query": clean_query,
            "url": search_url,
            "snippet": snippet
        }
    }


def none() -> Dict[str, Any]:
    """Chamada quando o comando não aciona nenhuma ferramenta do smartphone."""
    return {
        "status": "ok",
        "message": (
            "Silva: Sou um micro-agente focado no controle do seu celular (bateria, lanterna, fotos, SMS, apps). "
            "Não encontrei uma ferramenta específica para essa solicitação."
        ),
        "data": {}
    }


def _clean_ride_destination(raw_dest: str) -> str:
    """
    Remove prefixos conversacionais e sufixos de cortesia de um destino de corrida.
    Exemplos:
      "mim ir ao Shopping Recife" -> "Shopping Recife"
      "eu ir pro aeroporto pfv" -> "aeroporto"
      "ir na casa da minha tia" -> "casa da minha tia"
    """
    if not raw_dest:
        return ""
    text = str(raw_dest).strip()

    # 1. Sufixos de cortesia e ruídos no final
    suffix_pat = r"(?i)\s+(?:por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|de\s+uber|de\s+99|no\s+uber|na\s+99|pelo\s+uber|pela\s+99|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos conversacionais no início (repetidos até limpar completamente)
    prefix_patterns = [
        r"(?i)^(?:me\s+levar|me\s+leva|me\s+leve|levar|leva|leve|chegar|voltar|ir)\b\s*",
        r"(?i)^(?:para|pra|pro|pras|pros)\b\s*",
        r"(?i)^p/\s*",
        r"(?i)^(?:mim|eu|gente|nós|nos)\b\s*",
        r"(?i)^(?:ao|aos|à|às|no|na|nos|nas|em|até|ate)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
    ]

    for _ in range(10):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    text = re.sub(suffix_pat, "", text).strip()
    text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
    return text.strip()


def request_ride(destination: str, app: str = "uber") -> Dict[str, Any]:
    """Abre o aplicativo de transporte (Uber ou 99) com o destino configurado a partir da localização atual."""
    clean_dest = _clean_ride_destination(destination)
    if not clean_dest:
        return {"status": "error", "message": "Destino da corrida não informado."}

    # 1. Integração com Memória Local: consulta se o destino corresponde a um local salvo
    resolved_destination = clean_dest
    mem = _load_memory()
    if mem:
        norm_dest = _normalize_text(clean_dest)
        query_tokens = set(norm_dest.split())
        best_match = None
        best_score = 0
        for k, v_data in mem.items():
            val = v_data.get("value", "") if isinstance(v_data, dict) else str(v_data)
            norm_k = _normalize_text(k)
            score = 0
            if norm_dest == norm_k:
                score += 10
            elif norm_dest in norm_k:
                score += 6
            elif norm_k in norm_dest:
                score += 5

            common = query_tokens.intersection(set(norm_k.split()))
            if common:
                score += len(common) * 2

            if score > best_score and score >= 4:
                best_score = score
                best_match = val

        if best_match:
            resolved_destination = best_match

    app_target = str(app).strip().lower() if app else "uber"

    if app_target == "uber":
        encoded_dest = urllib.parse.quote(resolved_destination)
        url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}"
        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Abrindo UBER com destino para '{resolved_destination}'. Basta confirmar a corrida na tela. [Simulado]",
                "data": {"destination": resolved_destination, "app": "uber", "url": url}
            }
        _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Abrindo UBER com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
            "data": {"destination": resolved_destination, "app": "uber", "url": url}
        }

    elif app_target in ("99", "99pop"):
        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Abrindo 99 com destino para '{resolved_destination}'. Basta confirmar a corrida na tela. [Simulado]",
                "data": {"destination": resolved_destination, "app": "99"}
            }
        set_clipboard(resolved_destination)
        open_app("99")
        return {
            "status": "ok",
            "message": f"Abrindo 99 com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
            "data": {"destination": resolved_destination, "app": "99"}
        }
    else:
        encoded_dest = urllib.parse.quote(resolved_destination)
        url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}"
        if not SIMULATE_HARDWARE:
            _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Abrindo {app_target.upper()} com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
            "data": {"destination": resolved_destination, "app": app_target, "url": url}
        }


def order_food(query: str, app: str = "ifood") -> Dict[str, Any]:
    """Abre o aplicativo de delivery (iFood ou 99) buscando o prato, restaurante ou item pedido."""
    clean_query = str(query).strip()
    if not clean_query:
        return {"status": "error", "message": "Item ou prato para busca de comida não informado."}

    app_target = str(app).strip().lower() if app else "ifood"
    encoded_query = urllib.parse.quote_plus(clean_query)

    if app_target == "ifood":
        url = f"https://www.ifood.com.br/busca?q={encoded_query}"
        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no Ifood. [Simulado]",
                "data": {"query": clean_query, "app": "ifood", "url": url}
            }
        _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no Ifood.",
            "data": {"query": clean_query, "app": "ifood", "url": url}
        }

    elif app_target in ("99", "99food", "99 food"):
        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no 99. [Simulado]",
                "data": {"query": clean_query, "app": "99"}
            }
        set_clipboard(clean_query)
        open_app("99")
        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no 99.",
            "data": {"query": clean_query, "app": "99"}
        }
    else:
        url = f"https://www.ifood.com.br/busca?q={encoded_query}"
        if not SIMULATE_HARDWARE:
            _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no {app_target.capitalize()}.",
            "data": {"query": clean_query, "app": app_target, "url": url}
        }


# Dicionário de registro de funções disponíveis para o parser
AVAILABLE_TOOLS = {
    "get_battery": get_battery,
    "get_last_sms": get_last_sms,
    "send_sms": send_sms,
    "take_photo": take_photo,
    "record_video": record_video,
    "take_screenshot": take_screenshot,
    "search_google": search_google,
    "open_app": open_app,
    "make_call": make_call,
    "get_location": get_location,
    "get_last_location": get_last_location,
    "set_location_state": set_location_state,
    "get_weather": get_weather,
    "set_torch": set_torch,
    "set_dnd": set_dnd,
    "vibrate": vibrate,
    "get_clipboard": get_clipboard,
    "set_clipboard": set_clipboard,
    "tell_joke": tell_joke,
    "set_alarm": set_alarm,
    "cancel_alarm": cancel_alarm,
    "schedule_event": schedule_event,
    "remember_note": remember_note,
    "recall_note": recall_note,
    "get_notifications": get_notifications,
    "set_volume": set_volume,
    "set_brightness": set_brightness,
    "set_timer": set_timer,
    "calculate": calculate,
    "request_ride": request_ride,
    "order_food": order_food,
    "none": none,
}
