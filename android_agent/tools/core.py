"""
Módulo Core do Silva: Paths, Locks, Execução de Processos e Utilitários de Contato/App.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from config import CAPTURES_DIR, SIMULATE_HARDWARE
except ImportError:
    from android_agent.config import CAPTURES_DIR, SIMULATE_HARDWARE

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LAST_LOCATION_FILE = DATA_DIR / "last_location.json"
EVENTS_FILE = DATA_DIR / "events.json"

_FILE_LOCK = threading.RLock()


def save_last_location(
    latitude: float,
    longitude: float,
    label: str = "",
    updated_at: str = "",
    maps_url: str = "",
    image_url: Optional[str] = None,
    provider: str = ""
) -> Dict[str, Any]:
    """
    Salva a localização geográfica no arquivo de cache persistente data/last_location.json.
    """
    lat = float(latitude)
    lon = float(longitude)
    from datetime import datetime
    now = datetime.now()
    if not updated_at:
        updated_at = now.strftime("%Y-%m-%d %H:%M")
    if not maps_url:
        maps_url = f"https://maps.google.com/?q={lat},{lon}"
    if not label:
        label = f"{lat:.4f}, {lon:.4f}"

    payload = {
        "latitude": lat,
        "longitude": lon,
        "label": label,
        "updated_at": updated_at,
        "timestamp": now.isoformat(),
        "maps_url": maps_url,
        "image_url": image_url,
        "provider": provider or "termux"
    }
    _atomic_write_json(LAST_LOCATION_FILE, payload)
    return payload


def load_last_location() -> Optional[Dict[str, Any]]:
    """Carrega o último cache de localização registrado em data/last_location.json ou retorna None."""
    if not LAST_LOCATION_FILE.is_file():
        return None
    with _FILE_LOCK:
        try:
            with open(LAST_LOCATION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("latitude") is not None and data.get("longitude") is not None:
                return data
        except Exception:
            pass
    return None

def _atomic_write_json(path: Path, payload: Any) -> None:
    """
    Grava JSON de forma atômica e thread-safe:
    utiliza threading.Lock, grava em arquivo temporário .tmp no mesmo diretório,
    executa flush() e os.fsync() para persistência física no disco, e substitui
    o arquivo original de forma atômica via os.replace().
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with _FILE_LOCK:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)


def _load_events() -> list:
    if not EVENTS_FILE.is_file():
        return []
    with _FILE_LOCK:
        try:
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []


def _save_events(events: list):
    _atomic_write_json(EVENTS_FILE, events)

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
    "outlook": "com.microsoft.office.outlook",
    "uber": "com.ubercab",
    "facebook": "com.facebook.katana",
    "face": "com.facebook.katana",
    "netflix": "com.netflix.mediaclient",
    "play store": "com.android.vending",
    "playstore": "com.android.vending",
    "google play": "com.android.vending"
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
        eff_timeout = float(timeout) if timeout else 5.0
        return subprocess.run(
            exec_cmd,
            capture_output=True,
            text=True,
            timeout=eff_timeout,
            check=False
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args=exec_cmd, returncode=1, stdout="", stderr="TimeoutExpired")
    except OSError:
        # Fallback para invocação via shell do Termux/Android caso ocorra Exec format error
        sh_bin = "/data/data/com.termux/files/usr/bin/sh" if os.path.exists("/data/data/com.termux/files/usr/bin/sh") else "/system/bin/sh"
        try:
            return subprocess.run(
                [sh_bin] + exec_cmd,
                capture_output=True,
                text=True,
                timeout=eff_timeout,
                check=False
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args=exec_cmd, returncode=1, stdout="", stderr="TimeoutExpired")
        except Exception as e2:
            return subprocess.CompletedProcess(args=exec_cmd, returncode=1, stdout="", stderr=str(e2))
    except Exception as e:
        return subprocess.CompletedProcess(args=exec_cmd, returncode=1, stdout="", stderr=str(e))


def _exec_android_intent(cmd_str: str, timeout: int = 5) -> subprocess.CompletedProcess:
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
            timeout=float(timeout) if timeout else 5.0,
            check=False
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="TimeoutExpired")
    except Exception as e:
        return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr=str(e))


def cleanup_orphaned_captures(max_age_days: int = 7) -> Dict[str, int]:
    """
    Coletor de lixo de mídias em CAPTURES_DIR:
    1. Remove capturas temporárias mais antigas que max_age_days dias.
    2. Remove arquivos voice_note_* já concluídos (is_checked=1) ou órfãos (>24h sem registro ativo).
    """
    if not CAPTURES_DIR.is_dir():
        return {"removed_temp": 0, "removed_voice": 0}

    now_ts = time.time()
    temp_cutoff = now_ts - (max(1, int(max_age_days)) * 86400)
    orphan_cutoff = now_ts - 86400

    active_voice: set = set()
    checked_voice: set = set()
    try:
        try:
            from .memory_schedule import _get_memory_db
        except ImportError:
            from tools.memory_schedule import _get_memory_db

        with _FILE_LOCK:
            conn = _get_memory_db()
            try:
                cur = conn.cursor()
                cur.execute("SELECT filename, is_checked FROM voice_notes WHERE filename IS NOT NULL")
                for row in cur.fetchall():
                    fn = str(row["filename"] or "").strip()
                    if not fn:
                        continue
                    if int(row["is_checked"] or 0) == 0:
                        active_voice.add(fn)
                    else:
                        checked_voice.add(fn)
            finally:
                conn.close()
    except Exception:
        pass

    temp_prefixes = ("capture_", "screen_", "vid_", "loc_", "audio_")
    removed_temp = 0
    removed_voice = 0

    for entry in CAPTURES_DIR.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue

        if name.startswith("voice_note_"):
            if name in checked_voice or (name not in active_voice and mtime < orphan_cutoff):
                try:
                    entry.unlink(missing_ok=True)
                    removed_voice += 1
                except OSError:
                    pass
        elif name.startswith(temp_prefixes) and mtime < temp_cutoff:
            try:
                entry.unlink(missing_ok=True)
                removed_temp += 1
            except OSError:
                pass

    return {"removed_temp": removed_temp, "removed_voice": removed_voice}


