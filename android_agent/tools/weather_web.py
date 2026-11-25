"""
Módulo Clima e Web do Silva: Localização (GPS), Previsão do Tempo e Busca Web Multi-Fonte.
"""

import email.utils
import html
from html.parser import HTMLParser
import json
import math
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from .core import (
    CAPTURES_DIR,
    LAST_LOCATION_FILE,
    SIMULATE_HARDWARE,
    _run_termux_cmd,
    save_last_location,
    load_last_location,
)
from .adb_bridge import ensure_adb_connected, run_adb_shell

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


UF_TO_STATE = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina",
    "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"
}

STATE_TO_UF = {
    unicodedata.normalize("NFKD", v.lower()).encode("ascii", "ignore").decode("ascii"): k
    for k, v in UF_TO_STATE.items()
}


def _reverse_geocode_label(lat: float, lon: float) -> str:
    """
    Obtém bairro e cidade/UF para as coordenadas dadas via API pública sem chave (timeout 3s).
    Fallback seguro: f'{lat:.4f}, {lon:.4f}'.
    """
    fallback_coord = f"{lat:.4f}, {lon:.4f}"

    # 1. Tenta Nominatim (OpenStreetMap) com zoom de bairro/rua
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SilvaAgent/1.0 (Android Open Source Assistant)"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                d = json.loads(resp.read().decode("utf-8"))
                addr = d.get("address", {})
                neighborhood = (
                    addr.get("suburb")
                    or addr.get("neighbourhood")
                    or addr.get("city_district")
                    or addr.get("quarter")
                    or ""
                )
                city = (
                    addr.get("city")
                    or addr.get("town")
                    or addr.get("municipality")
                    or addr.get("village")
                    or ""
                )
                state = addr.get("state") or ""
                norm_state = unicodedata.normalize("NFKD", state.lower()).encode("ascii", "ignore").decode("ascii") if state else ""
                uf = STATE_TO_UF.get(norm_state, state) if state else ""

                parts = []
                if neighborhood:
                    parts.append(neighborhood)
                if city:
                    city_state = f"{city} - {uf}" if uf else city
                    parts.append(city_state)
                elif uf:
                    parts.append(uf)

                if parts:
                    return ", ".join(parts)
    except Exception:
        pass

    # 2. Tenta BigDataCloud Reverse Geocoding
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=pt"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SilvaAgent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                d = json.loads(resp.read().decode("utf-8"))
                locality = d.get("locality", "")
                city = d.get("city", "")
                subdiv = d.get("principalSubdivisionCode", "")
                uf = subdiv.split("-")[-1] if "-" in subdiv else subdiv

                parts = []
                if locality and locality != city:
                    parts.append(locality)
                if city:
                    city_state = f"{city} - {uf}" if uf else city
                    parts.append(city_state)
                elif uf:
                    parts.append(uf)

                if parts:
                    return ", ".join(parts)
    except Exception:
        pass

    return fallback_coord


_MOCK_LOCATION_ACTIVE: Optional[Any] = None


def _get_current_device_location() -> Optional[tuple]:
    """
    Tenta obter coordenadas atuais do dispositivo em tempo real via termux-location.
    Tenta primeiro 'network' rápido (timeout 5s) e depois 'gps' (timeout 8s).
    Em modo SIMULATE_HARDWARE ou mock, respeita o estado configurado.
    Retorna (latitude, longitude, provider) ou None se desativado/indisponível.
    """
    global _MOCK_LOCATION_ACTIVE
    if _MOCK_LOCATION_ACTIVE is False:
        return None
    if isinstance(_MOCK_LOCATION_ACTIVE, tuple) and len(_MOCK_LOCATION_ACTIVE) >= 2:
        prov = _MOCK_LOCATION_ACTIVE[2] if len(_MOCK_LOCATION_ACTIVE) > 2 else "mock"
        return float(_MOCK_LOCATION_ACTIVE[0]), float(_MOCK_LOCATION_ACTIVE[1]), prov
    if _MOCK_LOCATION_ACTIVE is True:
        return -7.9408, -34.8731, "mock"

    if SIMULATE_HARDWARE:
        return -7.9408, -34.8731, "simulated"

    try:
        # Tenta primeiro via network (rápido, timeout 5s)
        res = _run_termux_cmd(["termux-location", "-p", "network", "-r", "last"], timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout)
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon), data.get("provider", "network")
            except Exception:
                pass

        # Fallback para GPS (timeout 8s)
        res = _run_termux_cmd(["termux-location", "-p", "gps", "-r", "once"], timeout=8)
        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout)
                lat = data.get("latitude")
                lon = data.get("longitude")
                if lat is not None and lon is not None:
                    return float(lat), float(lon), data.get("provider", "gps")
            except Exception:
                pass
    except Exception:
        pass

    return None


def get_location() -> Dict[str, Any]:
    """Obtém coordenadas de localização geográfica com link do Google Maps e pré-visualização de mapa."""
    if SIMULATE_HARDWARE:
        lat, lon = -7.9408, -34.8731
        maps_url = f"https://maps.google.com/?q={lat},{lon}"
        map_img = _generate_map_preview(lat, lon)
        label = "Centro, Paulista - PE"
        loc_data = save_last_location(
            lat, lon,
            label=label,
            maps_url=maps_url,
            image_url=map_img,
            provider="simulated"
        )
        return {
            "status": "ok",
            "message": f"Silva: Localização: {label} (Lat {lat:.5f}, Lon {lon:.5f}). {maps_url} [Simulado]",
            "image_url": map_img,
            "data": loc_data
        }

    try:
        dev_loc = _get_current_device_location()
        if not dev_loc:
            return {"status": "error", "message": "Não foi possível obter sinal de localização."}

        lat_f, lon_f, provider = dev_loc
        maps_url = f"https://maps.google.com/?q={lat_f},{lon_f}"
        map_img = _generate_map_preview(lat_f, lon_f)
        label = _reverse_geocode_label(lat_f, lon_f)
        loc_data = save_last_location(
            lat_f, lon_f,
            label=label,
            maps_url=maps_url,
            image_url=map_img,
            provider=provider
        )

        label_display = f"{label} " if label and label != f"{lat_f:.4f}, {lon_f:.4f}" else ""
        return {
            "status": "ok",
            "message": f"Silva: Localização: {label_display}(Lat {lat_f:.5f}, Lon {lon_f:.5f}). {maps_url}",
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

    # Tentativa 0: ADB Local privilegiado (cmd location set-location-enabled)
    ok_adb, _ = run_adb_shell(
        ["cmd", "location", "set-location-enabled", "true" if st_bool else "false"],
        timeout=5.0,
    )
    if ok_adb:
        return {
            "status": "ok",
            "message": f"Silva: Localização (GPS) {txt} com sucesso.",
            "data": {"state": st_bool, "method": "adb"}
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
    cached = load_last_location()
    if not cached:
        if SIMULATE_HARDWARE:
            lat, lon = -7.9408, -34.8731
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
        lat = float(cached["latitude"])
        lon = float(cached["longitude"])
        maps_url = cached.get("maps_url", f"https://maps.google.com/?q={lat},{lon}")
        img_url = cached.get("image_url")
        label = cached.get("label", "")
        updated_at = cached.get("updated_at") or cached.get("timestamp", "")
        time_label = f" em {updated_at}" if updated_at else ""
        label_str = f"{label} - " if label and label != f"{lat:.4f}, {lon:.4f}" else ""
        return {
            "status": "ok",
            "message": f"Silva: Última localização registrada{time_label}: {label_str}Lat {lat:.5f}, Lon {lon:.5f}. {maps_url}",
            "image_url": img_url,
            "data": cached
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao consultar última localização: {str(e)}"}

WMO_BASE_MAP = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Nevoeiro",
    48: "Nevoeiro com geada",
    51: "Chuvisco leve",
    53: "Chuvisco moderado",
    55: "Chuvisco denso",
    56: "Chuvisco congelante leve",
    57: "Chuvisco congelante denso",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante leve",
    67: "Chuva congelante forte",
    71: "Neve fraca",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas de chuva leves",
    81: "Pancadas de chuva moderadas",
    82: "Chuva forte",
    85: "Pancadas de neve leves",
    86: "Pancadas de neve fortes",
    95: "Trovoadas",
    96: "Trovoadas com granizo leve",
    99: "Trovoadas com granizo forte"
}


def _normalize_geo_text(text: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas para comparações geográficas."""
    nfkd = unicodedata.normalize("NFKD", str(text).lower())
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).strip()


def _resolve_weather_location(location_query: str) -> tuple:
    """
    Resolve coordenadas (latitude, longitude) e nome formatado da localidade.
    Prioriza o Brasil (BR) e desempata por estado/UF se informado.
    """
    loc_clean = str(location_query).strip() if location_query else ""
    lat, lon, city_name = None, None, None

    is_generic = not loc_clean or any(
        loc_clean.lower() == k
        for k in ["aqui", "minha cidade", "minha localizacao", "localizacao atual", "local", "onde estou", "onde eu estou"]
    )

    if not is_generic:
        city_part = loc_clean
        state_hint = ""

        # Separa Cidade e Estado ("Cidade, Estado" ou "Cidade - Estado" ou "Cidade UF")
        if "," in loc_clean:
            parts = loc_clean.split(",", 1)
            city_part, state_hint = parts[0].strip(), parts[1].strip()
        elif " - " in loc_clean:
            parts = loc_clean.split(" - ", 1)
            city_part, state_hint = parts[0].strip(), parts[1].strip()
        else:
            m_uf = re.search(r"\b([A-Za-z]{2})$", loc_clean)
            if m_uf and m_uf.group(1).upper() in UF_TO_STATE:
                state_hint = m_uf.group(1).upper()
                city_part = loc_clean[:m_uf.start()].strip()

        try:
            url_geo = (
                f"https://geocoding-api.open-meteo.com/v1/search?"
                f"name={urllib.parse.quote_plus(city_part)}&count=5&language=pt&format=json"
            )
            req_geo = urllib.request.Request(url_geo, headers={"User-Agent": "SilvaAgent/1.0"})
            with urllib.request.urlopen(req_geo, timeout=4.5) as resp:
                geo_data = json.loads(resp.read().decode())
                results = geo_data.get("results", [])

                if results:
                    chosen = None
                    if state_hint:
                        norm_hint = _normalize_geo_text(state_hint)
                        full_state = UF_TO_STATE.get(state_hint.upper(), "")
                        norm_full = _normalize_geo_text(full_state) if full_state else ""

                        for item in results:
                            admin1 = item.get("admin1", "")
                            norm_admin1 = _normalize_geo_text(admin1)
                            is_br = (
                                item.get("country_code", "").upper() == "BR"
                                or item.get("country", "").lower() == "brasil"
                            )
                            if is_br and (norm_hint in norm_admin1 or (norm_full and norm_full in norm_admin1)):
                                chosen = item
                                break

                    if not chosen:
                        for item in results:
                            if item.get("country_code", "").upper() == "BR" or item.get("country", "").lower() == "brasil":
                                chosen = item
                                break

                    if not chosen:
                        chosen = results[0]

                    lat = float(chosen["latitude"])
                    lon = float(chosen["longitude"])
                    c_name = chosen.get("name", city_part)
                    admin1 = chosen.get("admin1", "")
                    city_name = f"{c_name}, {admin1}" if admin1 else c_name
        except Exception:
            pass

    # Fallback para última localização registrada (cache GPS)
    if lat is None or lon is None:
        if LAST_LOCATION_FILE.is_file():
            try:
                cached = json.loads(LAST_LOCATION_FILE.read_text(encoding="utf-8"))
                lat = float(cached["latitude"])
                lon = float(cached["longitude"])
                city_name = cached.get("city") or "Paulista, PE"
            except Exception:
                pass

    # Fallback padrão seguro (Paulista, PE)
    if lat is None or lon is None:
        lat, lon, city_name = -7.9408, -34.8730, "Paulista, PE"

    return lat, lon, (city_name or loc_clean or "Paulista, PE")


def _interpret_wmo_condition(
    weather_code: int,
    precip_prob: Optional[float] = None,
    precip_mm: Optional[float] = None,
    cloud_cover: Optional[float] = None
) -> str:
    """
    Sanitiza e traduz códigos meteorológicos WMO para descrições precisas em português,
    eliminando falsos positivos de chuva/chuvisco quando probabilidade e volume são baixos.
    """
    code = int(weather_code) if weather_code is not None else 0
    prob = float(precip_prob) if precip_prob is not None else 0.0
    mm = float(precip_mm) if precip_mm is not None else 0.0

    # Faixa de chuvisco, chuva leve e pancadas isoladas sujeitas a falsos positivos
    drizzle_rain_codes = {51, 53, 55, 56, 57, 61, 63, 80, 81}
    if code in drizzle_rain_codes:
        if prob < 35.0 and mm <= 0.5:
            if prob < 15.0:
                return "Céu limpo"
            return "Parcialmente nublado"

    return WMO_BASE_MAP.get(code, "Tempo instável")


def get_weather(day: str = "hoje", time: str = "", location: str = "") -> Dict[str, Any]:
    """Consulta previsão do tempo detalhada por dia, horário e cidade via Open-Meteo com cadeia de 3 níveis."""
    day_raw = str(day).strip().lower() if day else "hoje"
    time_raw = str(time).strip().lower() if time else ""
    loc_raw = str(location).strip() if location else ""

    # Determina se a consulta é relativa à localização atual do usuário (ou vazia)
    is_relative_or_empty = not loc_raw or any(
        loc_raw.lower() == k
        for k in [
            "aqui", "por aqui", "minha cidade", "meu bairro", "minha regiao", "minha região",
            "minha localizacao", "minha localização", "localizacao atual", "localização atual",
            "local atual", "local", "meu local", "onde estou", "onde eu estou",
            "minha area", "minha área", "meu setor", "meu redor", "ao meu redor"
        ]
    )

    location_fallback_notice = ""
    is_cached_fallback = False
    cached_label = ""
    cached_updated_at = ""

    if is_relative_or_empty:
        # CADEIA DE 3 NÍVEIS
        # Nível 1: Localização Ativa do Aparelho (GPS / Network em tempo real)
        dev_loc = _get_current_device_location()
        if not dev_loc:
            auto_gps = os.getenv("AUTO_ENABLE_GPS_VIA_ADB", "true").lower() in ("1", "true", "yes")
            if auto_gps and ensure_adb_connected():
                ok_gps, _ = run_adb_shell(["cmd", "location", "set-location-enabled", "true"], timeout=4.0)
                if ok_gps:
                    time.sleep(0.5)
                    dev_loc = _get_current_device_location()
        if dev_loc:
            lat, lon, provider = dev_loc
            label = _reverse_geocode_label(lat, lon)
            save_last_location(lat, lon, label=label, provider=provider)
            city_name = label
        else:
            # Nível 2: Última Localização Registrada (data/last_location.json)
            cached = load_last_location()
            if cached and cached.get("latitude") is not None and cached.get("longitude") is not None:
                lat = float(cached["latitude"])
                lon = float(cached["longitude"])
                cached_label = cached.get("label") or f"{lat:.4f}, {lon:.4f}"
                cached_updated_at = cached.get("updated_at") or cached.get("timestamp") or "data recente"
                city_name = cached_label
                is_cached_fallback = True
                location_fallback_notice = f"Localização atual desativada — usando última localização registrada ({cached_label} em {cached_updated_at}): "
            else:
                # Nível 3: Nenhuma Localização Disponível
                return {
                    "status": "ok",
                    "message": "Silva: Não foi possível consultar a temperatura porque a localização do aparelho está desligada e ainda não há nenhuma localização anterior registrada. Por favor, ligue a localização (GPS) e tente novamente.",
                    "data": {
                        "error": "location_unavailable",
                        "location_disabled": True,
                        "cached_location_available": False
                    }
                }
    else:
        # Consulta para localidade/cidade informada explicitamente
        lat, lon, city_name = _resolve_weather_location(loc_raw)

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
                if diff == 0:
                    diff = 7
                target_date = today + timedelta(days=diff)
                day_display = wname.capitalize()
                break

    # Consulta real à API Open-Meteo
    try:
        url_forecast = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&timezone=auto&forecast_days=7"
            f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,rain,showers,weather_code,cloud_cover,wind_speed_10m"
            f"&hourly=temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code,cloud_cover"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max"
        )
        req_w = urllib.request.Request(url_forecast, headers={"User-Agent": "SilvaAgent/1.0"})
        with urllib.request.urlopen(req_w, timeout=5.0) as resp:
            data_w = json.loads(resp.read().decode())

        current_block = data_w.get("current", {})
        hourly_block = data_w.get("hourly", {})
        daily_block = data_w.get("daily", {})

        # CASO 2: Horário ou período específico (time != "")
        if time_raw:
            if "noite" in time_raw:
                target_hour = 20
                hora_str = "20:00"
            elif "tarde" in time_raw:
                target_hour = 15
                hora_str = "15:00"
            elif "manha" in time_raw or "manhã" in time_raw:
                target_hour = 9
                hora_str = "09:00"
            elif "madrugada" in time_raw:
                target_hour = 3
                hora_str = "03:00"
            else:
                m_h = re.search(r"(\d{1,2})", time_raw)
                if m_h:
                    target_hour = max(0, min(23, int(m_h.group(1))))
                    hora_str = f"{target_hour:02d}:00"
                else:
                    target_hour = 12
                    hora_str = "12:00"

            target_prefix = f"{target_date.isoformat()}T{target_hour:02d}:"
            hourly_times = hourly_block.get("time", [])
            match_idx = None
            for i, ht in enumerate(hourly_times):
                if ht.startswith(target_prefix):
                    match_idx = i
                    break

            if match_idx is not None:
                temp = hourly_block.get("temperature_2m", [0.0])[match_idx]
                sensacao = hourly_block.get("apparent_temperature", [temp])[match_idx]
                prob = hourly_block.get("precipitation_probability", [0])[match_idx]
                precip_mm = hourly_block.get("precipitation", [0.0])[match_idx]
                clouds = hourly_block.get("cloud_cover", [0.0])[match_idx]
                wcode = hourly_block.get("weather_code", [0])[match_idx]
                cond = _interpret_wmo_condition(wcode, prob, precip_mm, clouds)

                base_msg = f"Previsão para {city_name} ({day_display} às {hora_str}): {cond}, temperatura de {temp:.1f}°C (sensação de {sensacao:.1f}°C) e chance de chuva de {prob}%."
                msg = f"Silva: {location_fallback_notice}{base_msg}" if is_cached_fallback else f"Silva: {base_msg}"
                res_data = {
                    "city": city_name,
                    "latitude": lat,
                    "longitude": lon,
                    "day": day_display,
                    "time": hora_str,
                    "condition": cond,
                    "temperature": temp,
                    "apparent_temperature": sensacao,
                    "precipitation_probability": prob,
                    "precipitation_mm": precip_mm,
                    "source": "open-meteo"
                }
                if is_cached_fallback:
                    res_data["fallback_used"] = "last_location"
                    res_data["cached_label"] = cached_label
                    res_data["cached_updated_at"] = cached_updated_at
                return {
                    "status": "ok",
                    "message": msg,
                    "data": res_data
                }

        # CASO 1: Clima de Hoje sem hora específica (day == "hoje" e time == "")
        if day_raw in ("hoje", "") and not time_raw:
            temp_atual = current_block.get("temperature_2m", 0.0)
            sensacao = current_block.get("apparent_temperature", temp_atual)
            umidade = current_block.get("relative_humidity_2m", 0)
            current_wcode = current_block.get("weather_code", 0)
            current_precip = current_block.get("precipitation", 0.0)
            current_clouds = current_block.get("cloud_cover", 0.0)

            # Busca probabilidade da hora atual no array horário
            current_time_str = current_block.get("time", "")
            current_hour_prob = 0
            if current_time_str:
                prefix = current_time_str[:13]
                for i, ht in enumerate(hourly_block.get("time", [])):
                    if ht.startswith(prefix):
                        current_hour_prob = hourly_block.get("precipitation_probability", [0])[i]
                        break

            condicao_atual = _interpret_wmo_condition(current_wcode, current_hour_prob, current_precip, current_clouds)

            temp_min = daily_block.get("temperature_2m_min", [temp_atual])[0]
            temp_max = daily_block.get("temperature_2m_max", [temp_atual])[0]
            prob_max = daily_block.get("precipitation_probability_max", [0])[0]

            base_msg = (
                f"Agora em {city_name}: {condicao_atual}, {temp_atual:.1f}°C (sensação de {sensacao:.1f}°C). "
                f"Previsão para hoje: mínima de {temp_min:.1f}°C, máxima de {temp_max:.1f}°C e chance de chuva de {prob_max}%."
            )
            msg = f"Silva: {location_fallback_notice}{base_msg}" if is_cached_fallback else f"Silva: {base_msg}"
            res_data = {
                "city": city_name,
                "latitude": lat,
                "longitude": lon,
                "condition": condicao_atual,
                "temperature": temp_atual,
                "apparent_temperature": sensacao,
                "humidity": umidade,
                "temp_min": temp_min,
                "temp_max": temp_max,
                "precipitation_probability": prob_max,
                "precipitation_mm": current_precip,
                "source": "open-meteo"
            }
            if is_cached_fallback:
                res_data["fallback_used"] = "last_location"
                res_data["cached_label"] = cached_label
                res_data["cached_updated_at"] = cached_updated_at
            return {
                "status": "ok",
                "message": msg,
                "data": res_data
            }

        # CASO 3: Dias futuros sem hora específica (day != "hoje" e time == "")
        diff_days = (target_date - today).days
        if diff_days < 0 or diff_days > 6:
            return {
                "status": "ok",
                "message": "Silva: A previsão do tempo está disponível para até 7 dias no futuro.",
                "data": {"location": city_name, "day": day_display}
            }

        daily_times = daily_block.get("time", [])
        day_str = target_date.isoformat()
        day_idx = diff_days
        for i, dt in enumerate(daily_times):
            if dt == day_str:
                day_idx = i
                break

        t_min = daily_block.get("temperature_2m_min", [0.0])[day_idx]
        t_max = daily_block.get("temperature_2m_max", [0.0])[day_idx]
        rain_max = daily_block.get("precipitation_probability_max", [0])[day_idx]
        precip_sum = daily_block.get("precipitation_sum", [0.0])[day_idx]
        wcode = daily_block.get("weather_code", [0])[day_idx]
        cond = _interpret_wmo_condition(wcode, rain_max, precip_sum, None)

        base_msg = f"Previsão para {city_name} ({day_display}): {cond}. Mínima de {t_min:.1f}°C, máxima de {t_max:.1f}°C e probabilidade de chuva de {rain_max}%."
        msg = f"Silva: {location_fallback_notice}{base_msg}" if is_cached_fallback else f"Silva: {base_msg}"
        res_data = {
            "city": city_name,
            "latitude": lat,
            "longitude": lon,
            "day": day_display,
            "condition": cond,
            "temp_min": t_min,
            "temp_max": t_max,
            "precipitation_probability": rain_max,
            "precipitation_sum": precip_sum,
            "source": "open-meteo"
        }
        if is_cached_fallback:
            res_data["fallback_used"] = "last_location"
            res_data["cached_label"] = cached_label
            res_data["cached_updated_at"] = cached_updated_at
        return {
            "status": "ok",
            "message": msg,
            "data": res_data
        }
    except Exception as e:
        if SIMULATE_HARDWARE:
            city_disp = city_name or loc_raw or "Paulista, PE"
            prefix = f"Silva: {location_fallback_notice}" if is_cached_fallback else "Silva: "
            if day_raw in ("hoje", "") and not time_raw:
                res_data = {
                    "city": city_disp, "latitude": lat, "longitude": lon, "condition": "Parcialmente nublado",
                    "temperature": 27.5, "apparent_temperature": 29.8, "humidity": 75,
                    "temp_min": 24.0, "temp_max": 30.5, "precipitation_probability": 20, "precipitation_mm": 0.0,
                    "source": "simulated"
                }
                if is_cached_fallback:
                    res_data["fallback_used"] = "last_location"
                    res_data["cached_label"] = cached_label
                    res_data["cached_updated_at"] = cached_updated_at
                return {
                    "status": "ok",
                    "message": f"{prefix}Agora em {city_disp}: Parcialmente nublado, 27.5°C (sensação de 29.8°C). Previsão para hoje: mínima de 24.0°C, máxima de 30.5°C e chance de chuva de 20%.",
                    "data": res_data
                }
            elif time_raw:
                hora_str = "20:00" if "noite" in time_raw else ("15:00" if "tarde" in time_raw else ("09:00" if any(m in time_raw for m in ["manha", "manhã"]) else "12:00"))
                res_data = {
                    "city": city_disp, "latitude": lat, "longitude": lon, "day": day_display, "time": hora_str,
                    "condition": "Parcialmente nublado", "temperature": 26.0, "apparent_temperature": 28.0,
                    "precipitation_probability": 15, "precipitation_mm": 0.0, "source": "simulated"
                }
                if is_cached_fallback:
                    res_data["fallback_used"] = "last_location"
                    res_data["cached_label"] = cached_label
                    res_data["cached_updated_at"] = cached_updated_at
                return {
                    "status": "ok",
                    "message": f"{prefix}Previsão para {city_disp} ({day_display} às {hora_str}): Parcialmente nublado, temperatura de 26.0°C (sensação de 28.0°C) e chance de chuva de 15%.",
                    "data": res_data
                }
            else:
                res_data = {
                    "city": city_disp, "latitude": lat, "longitude": lon, "day": day_display,
                    "condition": "Parcialmente nublado", "temp_min": 24.5, "temp_max": 31.0,
                    "precipitation_probability": 20, "precipitation_mm": 0.0, "source": "simulated"
                }
                if is_cached_fallback:
                    res_data["fallback_used"] = "last_location"
                    res_data["cached_label"] = cached_label
                    res_data["cached_updated_at"] = cached_updated_at
                return {
                    "status": "ok",
                    "message": f"{prefix}Previsão para {city_disp} ({day_display}): Parcialmente nublado. Mínima de 24.5°C, máxima de 31.0°C e probabilidade de chuva de 20%.",
                    "data": res_data
                }
        return {
            "status": "error",
            "message": "Não foi possível obter a previsão do tempo no momento (verifique a conexão com a internet).",
            "data": {"error": str(e), "location": city_name}
        }


class DuckDuckGoHTMLParser(HTMLParser):
    """Parser leve nativo para extrair os 3 primeiros resultados reais do DuckDuckGo HTML Lite."""
    def __init__(self, max_results: int = 3):
        super().__init__()
        self.max_results = max_results
        self.results = []
        self._in_title = False
        self._in_snippet = False
        self._cur_title = []
        self._cur_snippet = []
        self._cur_url = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()

        if tag == "a" and "result__a" in classes:
            self._in_title = True
            href = attrs_dict.get("href", "")
            if "uddg=" in href:
                m = re.search(r"uddg=([^&]+)", href)
                self._cur_url = urllib.parse.unquote(m.group(1)) if m else href
            else:
                self._cur_url = href
            self._cur_title = []
        elif (tag in ("a", "div", "td", "span")) and ("result__snippet" in classes or "snippet" in classes):
            self._in_snippet = True
            self._cur_snippet = []

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._in_title = False
        elif self._in_snippet and tag in ("a", "div", "td", "span"):
            self._in_snippet = False
            title_text = " ".join("".join(self._cur_title).split())
            snip_text = " ".join("".join(self._cur_snippet).split())
            if title_text and self._cur_url and len(self.results) < self.max_results:
                self.results.append({
                    "title": html.unescape(title_text),
                    "snippet": html.unescape(snip_text),
                    "url": self._cur_url
                })
            self._cur_title = []
            self._cur_snippet = []
            self._cur_url = ""

    def handle_data(self, data):
        if self._in_title:
            self._cur_title.append(data)
        elif self._in_snippet:
            self._cur_snippet.append(data)


SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Accept-Language": "pt-BR,pt;q=0.9"
}


def _fetch_wikipedia_summary(clean_query: str) -> Optional[Dict[str, str]]:
    """
    Fonte 1 — Wikipédia PT-BR (Busca Semântica + Resumo):
    1. Resolve o título oficial via Busca Semântica (ex: 'GTA 6' -> 'Grand Theft Auto VI').
    2. Obtém o resumo na REST API oficial limitado a ~350 caracteres sem truncar palavras.
    """
    if not clean_query:
        return None

    resolved_title = clean_query
    # 1. Busca semântica para resolver o título oficial
    try:
        srsearch = urllib.parse.quote(clean_query)
        search_api_url = f"https://pt.wikipedia.org/w/api.php?action=query&list=search&srsearch={srsearch}&format=json&utf8=1&srlimit=1"
        req_search = urllib.request.Request(search_api_url, headers=SEARCH_HEADERS)
        with urllib.request.urlopen(req_search, timeout=6.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            search_list = data.get("query", {}).get("search", [])
            if search_list and "title" in search_list[0]:
                resolved_title = search_list[0]["title"]
    except Exception:
        resolved_title = clean_query

    # 2. Consulta REST API summary
    try:
        slug = urllib.parse.quote(resolved_title.replace(" ", "_"))
        wiki_url = f"https://pt.wikipedia.org/api/rest_v1/page/summary/{slug}"
        req_sum = urllib.request.Request(wiki_url, headers=SEARCH_HEADERS)
        with urllib.request.urlopen(req_sum, timeout=6.0) as resp:
            sum_data = json.loads(resp.read().decode("utf-8"))
            if sum_data.get("type") == "disambiguation":
                return None
            extract = sum_data.get("extract", "").strip()
            if not extract:
                return None

            # Limita a ~350 caracteres sem cortar palavras
            if len(extract) > 350:
                truncated = extract[:350].rsplit(" ", 1)[0]
                extract = truncated.rstrip(".,;:") + "..."

            title = sum_data.get("title", resolved_title)
            page_url = sum_data.get("content_urls", {}).get("desktop", {}).get("page", f"https://pt.wikipedia.org/wiki/{slug}")

            return {
                "title": title,
                "summary": extract,
                "extract": extract,  # compatibilidade retroativa
                "url": page_url
            }
    except Exception:
        pass

    return None


def _fetch_google_news_rss(clean_query: str) -> list[Dict[str, str]]:
    """
    Fonte 2 — Google News RSS PT-BR:
    Consulta https://news.google.com/rss/search?q=<query>&hl=pt-BR&gl=BR&ceid=BR:pt-419
    Faz parse nativo com xml.etree.ElementTree e extrai até 3 notícias recentes:
    title (limpando o sufixo '- Nome do Veículo' para o campo source), link e pubDate (DD/MM/YYYY).
    """
    results = []
    try:
        encoded_q = urllib.parse.quote_plus(clean_query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        req_rss = urllib.request.Request(rss_url, headers=SEARCH_HEADERS)
        with urllib.request.urlopen(req_rss, timeout=6.0) as resp:
            xml_bytes = resp.read()

        root = ET.fromstring(xml_bytes)
        items = root.findall(".//item")
        for item in items[:3]:
            raw_title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date_raw = (item.findtext("pubDate") or "").strip()

            date_str = ""
            if pub_date_raw:
                try:
                    dt = email.utils.parsedate_to_datetime(pub_date_raw)
                    date_str = dt.strftime("%d/%m/%Y")
                except Exception:
                    date_str = ""

            if " - " in raw_title:
                t_parts = raw_title.rsplit(" - ", 1)
                item_title = t_parts[0].strip()
                source = t_parts[1].strip()
            else:
                item_title = raw_title
                source = "Google News"

            snippet = f"Publicado em {date_str} via {source}" if date_str else f"Fonte: {source}"
            if item_title and link:
                results.append({
                    "title": item_title,
                    "snippet": snippet,
                    "source": source,
                    "url": link,
                    "date": date_str
                })
    except Exception:
        pass

    return results


def _fetch_duckduckgo_lite(clean_query: str) -> list[Dict[str, str]]:
    """
    Fonte 3 — DuckDuckGo Lite (https://lite.duckduckgo.com/lite/):
    Caso Wikipédia e Google News retornem vazios, faz POST e extrai até 3 resultados orgânicos.
    """
    results = []
    try:
        ddg_url = "https://lite.duckduckgo.com/lite/"
        post_data = urllib.parse.urlencode({"q": clean_query}).encode("utf-8")
        post_headers = dict(SEARCH_HEADERS)
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"

        req_ddg = urllib.request.Request(ddg_url, data=post_data, headers=post_headers)
        with urllib.request.urlopen(req_ddg, timeout=6.0) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        matches = re.findall(r'<a[^>]+href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>', content, re.IGNORECASE)
        snippets = re.findall(r'<td[^>]+class=[\"\']result-snippet[\"\'][^>]*>(.*?)</td>', content, re.IGNORECASE | re.DOTALL)

        raw_pairs = []
        for u, t in matches:
            u_clean = u.strip()
            if u_clean.startswith("http") and "duckduckgo.com/y.js" not in u_clean and "duckduckgo.com/lite" not in u_clean:
                title_clean = html.unescape(re.sub(r'<[^>]+>', '', t).strip())
                if title_clean:
                    raw_pairs.append((u_clean, title_clean))

        for idx, (url, title) in enumerate(raw_pairs[:3]):
            snip = ""
            if idx < len(snippets):
                snip = html.unescape(re.sub(r'<[^>]+>', '', snippets[idx]).strip())
            results.append({
                "title": title,
                "snippet": snip or f"Resultado para {clean_query}",
                "source": "DuckDuckGo",
                "url": url,
                "date": ""
            })
    except Exception:
        pass

    return results


def _strip_leading_articles(q: str) -> str:
    """Remove artigos definidos e indefinidos isolados no início da query e pontuações finais."""
    if not q:
        return ""
    cleaned = re.sub(r"(?i)^\s*(?:o|a|os|as|um|uma|uns|umas)\s+", "", q.strip())
    return re.sub(r"[\s\.\?!,;:~—–-]+$", "", cleaned).strip()


def search_google(query: str, open_browser: bool = False) -> Dict[str, Any]:
    """
    Pesquisa multi-fonte na web com cascata real:
    1. Wikipédia PT-BR (Busca Semântica + Resumo)
    2. Google News RSS PT-BR (Notícias recentes via XML nativo)
    3. DuckDuckGo Lite (Fallback orgânico via POST)
    Abre o navegador se open_browser=True ou se solicitado explicitamente no texto.
    """
    clean_query = _strip_leading_articles(str(query))
    if not clean_query:
        return {"status": "error", "message": "Termo de busca não especificado.", "data": None}

    # Verifica se o próprio texto da busca pede para abrir no navegador
    should_open_browser = open_browser or any(
        w in clean_query.lower() for w in ["abre no navegador", "abrir no navegador", "no chrome", "no browser"]
    )

    encoded_query = urllib.parse.quote_plus(clean_query)
    search_url = f"https://www.google.com/search?q={encoded_query}"

    # Simulação realista quando SIMULATE_HARDWARE=True
    if SIMULATE_HARDWARE:
        if "turing" in clean_query.lower():
            wiki_sim = {
                "title": "Alan Turing",
                "summary": (
                    "Alan Mathison Turing (1912 - 1954) foi um matemático, cientista da computação, lógico, "
                    "criptoanalista, filósofo e biólogo teórico britânico. Turing foi altamente influente no "
                    "desenvolvimento da ciência da computação teórica, proporcionando uma formalização dos conceitos "
                    "de algoritmo e computação com a máquina de Turing."
                ),
                "url": "https://pt.wikipedia.org/wiki/Alan_Turing"
            }
        else:
            wiki_sim = {
                "title": clean_query,
                "summary": f"Informações enciclopédicas e contexto temático sobre {clean_query}.",
                "url": f"https://pt.wikipedia.org/wiki/{urllib.parse.quote(clean_query.replace(' ', '_'))}"
            }
        wiki_sim["extract"] = wiki_sim["summary"]

        news_sim = [
            {
                "title": f"Últimas atualizações sobre {clean_query}",
                "snippet": f"Notícia recente e desenvolvimentos sobre {clean_query}.",
                "source": "Portal de Notícias",
                "url": search_url,
                "date": "20/11/2026"
            }
        ]

        sections = [
            f"Silva: Resultados da pesquisa para '{clean_query}':",
            f"[Wikipédia — {wiki_sim['title']}]\n{wiki_sim['summary']}\n[Ler artigo completo na Wikipédia]({wiki_sim['url']})",
            f"Principais Notícias e Artigos:\n1. [{news_sim[0]['title']}]({news_sim[0]['url']}) — {news_sim[0]['source']} ({news_sim[0]['date']})",
            f"[Ver todos os resultados no Google]({search_url})"
        ]

        return {
            "status": "ok",
            "message": "\n\n".join(sections),
            "data": {
                "query": clean_query,
                "google_url": search_url,
                "url": search_url,
                "wiki": wiki_sim,
                "wikipedia": wiki_sim,
                "results": news_sim,
                "opened_browser": False
            }
        }

    # Abre no navegador se solicitado
    if should_open_browser:
        try:
            _run_termux_cmd(["am", "start", "-a", "android.intent.action.VIEW", "-d", search_url], timeout=6)
        except Exception:
            pass

    # Cascata Multi-Fonte Real
    # 1. Wikipédia PT-BR (Busca Semântica + Resumo)
    wiki_res = _fetch_wikipedia_summary(clean_query)

    # 2. Google News RSS PT-BR
    news_res = _fetch_google_news_rss(clean_query)
    results = list(news_res)

    # 3. DuckDuckGo Lite (se Wiki e News estiverem vazios)
    if not wiki_res and not results:
        ddg_results = _fetch_duckduckgo_lite(clean_query)
        if ddg_results:
            results = ddg_results

    # Formatação Limpa da Resposta (zero linhas em branco vazias, links ocultos Markdown)
    sections = [f"Silva: Resultados da pesquisa para '{clean_query}':"]

    if wiki_res:
        wiki_url = wiki_res.get("url", search_url)
        sections.append(
            f"[Wikipédia — {wiki_res['title']}]\n"
            f"{wiki_res['summary']}\n"
            f"[Ler artigo completo na Wikipédia]({wiki_url})"
        )

    if results:
        items_txt = []
        for idx, item in enumerate(results, start=1):
            title = item.get("title", "").strip()
            url = item.get("url", search_url)
            source = item.get("source", "Web").strip()
            date_info = f" ({item['date']})" if item.get("date") else ""
            items_txt.append(f"{idx}. [{title}]({url}) — {source}{date_info}")
        sections.append("Principais Notícias e Artigos:\n" + "\n".join(items_txt))

    sections.append(f"[Ver todos os resultados no Google]({search_url})")

    final_msg = "\n\n".join(sections)

    return {
        "status": "ok",
        "message": final_msg,
        "data": {
            "query": clean_query,
            "google_url": search_url,
            "url": search_url,
            "wiki": wiki_res,
            "wikipedia": wiki_res,
            "results": results,
            "opened_browser": should_open_browser
        }
    }


