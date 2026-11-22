"""
Módulo Hardware do Silva: Bateria, Lanterna, DND, Vibração, Volume, Brilho e Wi-Fi Scan.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict

from .core import (
    DATA_DIR,
    SIMULATE_HARDWARE,
    _FILE_LOCK,
    _atomic_write_json,
    _run_termux_cmd,
    _exec_android_intent,
)

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
                _atomic_write_json(backup_file, backup_data)
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



def scan_wifi() -> Dict[str, Any]:
    """
    Escaneia e lista as redes Wi-Fi disponíveis nas proximidades,
    exibindo SSID, nível de sinal (dBm e %), frequência (2.4 GHz ou 5 GHz),
    tipo de segurança (WPA3, WPA2, Aberta) e identificação da rede conectada no momento.
    """
    if SIMULATE_HARDWARE:
        simulated_networks = [
            {
                "ssid": "Silva_5G",
                "bssid": "00:11:22:33:44:55",
                "rssi": -45,
                "quality_pct": 100,
                "band": "5 GHz",
                "security": "WPA2/WPA3",
                "is_connected": True
            },
            {
                "ssid": "Casa_2.4G",
                "bssid": "aa:bb:cc:dd:ee:ff",
                "rssi": -62,
                "quality_pct": 76,
                "band": "2.4 GHz",
                "security": "WPA2",
                "is_connected": False
            },
            {
                "ssid": "Vizinho_Fibra",
                "bssid": "12:34:56:78:9a:bc",
                "rssi": -78,
                "quality_pct": 44,
                "band": "5 GHz",
                "security": "WPA2",
                "is_connected": False
            }
        ]
        lines = [f"Silva: Redes Wi-Fi encontradas nas proximidades ({len(simulated_networks)}):"]
        for idx, net in enumerate(simulated_networks, start=1):
            conn_tag = " [Conectada]" if net["is_connected"] else ""
            lines.append(
                f"{idx}. {net['ssid']}{conn_tag} - Sinal: {net['quality_pct']}% ({net['rssi']} dBm) | {net['band']} | {net['security']}"
            )

        return {
            "status": "ok",
            "message": "\n".join(lines),
            "data": {
                "networks": simulated_networks,
                "total_found": len(simulated_networks),
                "connected_ssid": "Silva_5G"
            }
        }

    # Modo Real Termux
    try:
        # 1. Identificar rede conectada atualmente
        connected_bssid = ""
        connected_ssid = ""
        res_conn = _run_termux_cmd(["termux-wifi-connectioninfo"], timeout=6)
        if res_conn.returncode == 0 and res_conn.stdout.strip():
            try:
                conn_info = json.loads(res_conn.stdout)
                if isinstance(conn_info, dict):
                    connected_bssid = conn_info.get("bssid", "") or ""
                    connected_ssid = (conn_info.get("ssid", "") or "").strip('"')
            except Exception:
                pass

        # 2. Escanear redes disponíveis
        res_scan = _run_termux_cmd(["termux-wifi-scaninfo"], timeout=10)
        if res_scan.returncode != 0:
            return {
                "status": "error",
                "message": f"Silva: Falha ao escanear redes Wi-Fi via Termux: {res_scan.stderr.strip()}",
                "data": {"networks": []}
            }

        raw_scan = res_scan.stdout.strip()
        networks_data = json.loads(raw_scan) if raw_scan else []

        if not networks_data:
            return {
                "status": "ok",
                "message": (
                    "Silva: Nenhuma rede Wi-Fi encontrada nas proximidades.\n\n"
                    "Aviso: No Android 10+, o escaneamento de Wi-Fi exige que a Localização (GPS) "
                    "do smartphone esteja ativada nas configurações do sistema."
                ),
                "data": {"networks": [], "total_found": 0, "warning": "gps_required"}
            }

        cleaned_networks = []
        for net in networks_data:
            ssid = str(net.get("ssid", "")).strip().strip('"')
            if not ssid:
                continue
            bssid = str(net.get("bssid", "")).strip()
            rssi = int(net.get("rssi", -100))
            quality_pct = max(0, min(100, 2 * (rssi + 100)))

            freq = int(net.get("frequency", 0))
            band = "5 GHz" if freq >= 4900 else "2.4 GHz"

            capabilities = str(net.get("capabilities", "")).upper()
            if "WPA3" in capabilities or "SAE" in capabilities:
                security = "WPA3"
            elif "WPA2" in capabilities or "PSK" in capabilities:
                security = "WPA2"
            elif "WEP" in capabilities:
                security = "WEP"
            elif not capabilities or ("ESS" in capabilities and "WPA" not in capabilities):
                security = "Aberta"
            else:
                security = "Protegida"

            is_connected = False
            if (connected_bssid and bssid and bssid.lower() == connected_bssid.lower()) or (connected_ssid and ssid == connected_ssid):
                is_connected = True

            cleaned_networks.append({
                "ssid": ssid,
                "bssid": bssid,
                "rssi": rssi,
                "quality_pct": quality_pct,
                "band": band,
                "security": security,
                "is_connected": is_connected
            })

        if not cleaned_networks:
            return {
                "status": "ok",
                "message": "Silva: Nenhuma rede Wi-Fi com identificador (SSID) público foi encontrada.",
                "data": {"networks": [], "total_found": 0}
            }

        # Ordenar: conectada primeiro (se houver), depois por melhor sinal (rssi decrescente)
        cleaned_networks.sort(key=lambda x: (not x["is_connected"], -x["rssi"]))

        lines = [f"Silva: Redes Wi-Fi encontradas nas proximidades ({len(cleaned_networks)}):"]
        for idx, net in enumerate(cleaned_networks, start=1):
            conn_tag = " [Conectada]" if net["is_connected"] else ""
            lines.append(
                f"{idx}. {net['ssid']}{conn_tag} - Sinal: {net['quality_pct']}% ({net['rssi']} dBm) | {net['band']} | {net['security']}"
            )

        return {
            "status": "ok",
            "message": "\n".join(lines),
            "data": {
                "networks": cleaned_networks,
                "total_found": len(cleaned_networks),
                "connected_ssid": connected_ssid
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Silva: Erro ao escanear Wi-Fi: {str(e)}",
            "data": {"networks": []}
        }


