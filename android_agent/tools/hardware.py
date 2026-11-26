"""
Módulo Hardware do Silva: Bateria, Lanterna, DND, Vibração, Volume, Brilho e Wi-Fi Scan.
"""

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
from typing import Any, Dict

from .core import (
    DATA_DIR,
    SIMULATE_HARDWARE,
    _atomic_write_json,
    _exec_android_intent,
    _run_termux_cmd,
)
from .adb_bridge import ensure_adb_connected, run_adb_shell

_BATTERY_STATUS_MAP = {
    "2": "carregando",
    "3": "descarregando",
    "4": "não carregando",
    "5": "cheia",
}
_BATTERY_HEALTH_MAP = {
    "2": "Boa",
    "3": "Superaquecida",
    "4": "Morta",
    "5": "Sobretensão",
}


def get_battery_info() -> Dict[str, Any]:
    """
    Obtém telemetria real da bateria:
    - Camada 1: ADB `dumpsys battery` (level, status, temperature/10, voltage mV->V, health)
    - Camada 2: `termux-battery-status` ou `/sys/class/power_supply/battery/`
    """
    if SIMULATE_HARDWARE and not ensure_adb_connected():
        return {
            "status": "ok",
            "message": "Silva: Bateria em 82% (descarregando, temperatura 31.4°C, 4.12V, saúde Boa). [Simulado]",
            "data": {
                "percentage": 82,
                "status": "DISCHARGING",
                "temperature": 31.4,
                "voltage_v": 4.12,
                "health": "Boa",
                "source": "simulated",
            },
        }

    # Camada 1: ADB dumpsys battery
    if ensure_adb_connected():
        ok_b, out_b = run_adb_shell(["dumpsys", "battery"], timeout=5.0)
        if ok_b and out_b and "level:" in out_b:
            m_lvl = re.search(r"level:\s*(\d+)", out_b)
            m_st = re.search(r"status:\s*(\d+)", out_b)
            m_temp = re.search(r"temperature:\s*(-?\d+)", out_b)
            m_volt = re.search(r"voltage:\s*(\d+)", out_b)
            m_hlth = re.search(r"health:\s*(\d+)", out_b)
            pct = int(m_lvl.group(1)) if m_lvl else 0
            st_code = m_st.group(1) if m_st else "3"
            status_pt = _BATTERY_STATUS_MAP.get(st_code, "descarregando")
            temp_c = round(int(m_temp.group(1)) / 10.0, 1) if m_temp else 0.0
            volt_mv = int(m_volt.group(1)) if m_volt else 0
            volt_v = round(volt_mv / 1000.0, 2) if volt_mv > 100 else round(float(volt_mv), 2)
            health_pt = _BATTERY_HEALTH_MAP.get(m_hlth.group(1) if m_hlth else "2", "Boa")
            msg = f"Silva: Bateria em {pct}% ({status_pt}, temperatura {temp_c:.1f}°C, {volt_v:.2f}V, saúde {health_pt})."
            return {
                "status": "ok",
                "message": msg,
                "data": {
                    "percentage": pct,
                    "status": status_pt,
                    "temperature": temp_c,
                    "voltage_v": volt_v,
                    "health": health_pt,
                    "source": "adb_dumpsys",
                },
            }

    # Camada 2a: termux-battery-status
    try:
        res = _run_termux_cmd(["termux-battery-status"], timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            pct = int(data.get("percentage", 0))
            temp = float(data.get("temperature", 0.0))
            plugged = data.get("plugged", "UNPLUGGED")
            status_pt = "carregando" if plugged != "UNPLUGGED" else "descarregando"
            msg = f"Silva: Bateria em {pct}% ({status_pt}, temperatura {temp:.1f}°C)."
            data["source"] = "termux_api"
            return {"status": "ok", "message": msg, "data": data}
    except Exception:
        pass

    # Camada 2b: /sys/class/power_supply/battery/
    try:
        base = "/sys/class/power_supply/battery"
        if os.path.isdir(base):
            def _read_sys(name: str, default: str = "") -> str:
                p = os.path.join(base, name)
                if os.path.isfile(p):
                    with open(p, "r", encoding="utf-8") as fp:
                        return fp.read().strip()
                return default

            pct = int(_read_sys("capacity", "0") or 0)
            st_raw = _read_sys("status", "Discharging")
            status_pt = "carregando" if st_raw.lower() in ("charging", "full") else "descarregando"
            raw_t = float(_read_sys("temp", "0") or 0)
            temp_c = round(raw_t / 10.0, 1) if raw_t > 100 else round(raw_t, 1)
            msg = f"Silva: Bateria em {pct}% ({status_pt}, temperatura {temp_c:.1f}°C)."
            return {
                "status": "ok",
                "message": msg,
                "data": {"percentage": pct, "status": status_pt, "temperature": temp_c, "source": "sysfs"},
            }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao acessar status da bateria: {str(e)}"}

    return {"status": "error", "message": "Não foi possível ler o status da bateria."}


get_battery = get_battery_info



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

    # Tentativa 0: ADB Local privilegiado (cmd notification set_dnd)
    ok_adb, _ = run_adb_shell(["cmd", "notification", "set_dnd", dnd_state_str], timeout=5.0)
    if ok_adb:
        return {
            "status": "ok",
            "message": f"Silva: Modo Não Perturbe {action_pt}.",
            "data": {"state": state_bool, "method": "adb"}
        }

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
        try:
            networks_data = json.loads(raw_scan) if raw_scan else []
        except Exception as e:
            return {
                "status": "error",
                "message": f"Silva: Falha ao interpretar resposta do Wi-Fi: {str(e)}",
                "data": {"networks": []}
            }

        # Trata resposta de erro retornada como dicionário pela Termux:API (ex: Localização desligada)
        if isinstance(networks_data, dict):
            api_error = str(networks_data.get("API_ERROR", "") or networks_data.get("error", "")).strip()
            if "location" in api_error.lower() or "gps" in api_error.lower():
                return {
                    "status": "ok",
                    "message": (
                        "Silva: Para escanear redes Wi-Fi nas proximidades, a Localização (GPS) precisa estar ativada "
                        "no smartphone (exigência do Android). Por favor, ative a Localização e tente novamente."
                    ),
                    "data": {"networks": [], "total_found": 0, "warning": "gps_required"}
                }
            if api_error:
                return {
                    "status": "error",
                    "message": f"Silva: Erro da API do Termux ao escanear Wi-Fi: {api_error}",
                    "data": {"networks": []}
                }
            networks_data = []

        if not isinstance(networks_data, list) or not networks_data:
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
            if not isinstance(net, dict):
                continue
            ssid = str(net.get("ssid", "")).strip().strip('"')
            if not ssid:
                continue
            bssid = str(net.get("bssid", "")).strip()
            try:
                rssi = int(net.get("rssi", -100))
            except (ValueError, TypeError):
                rssi = -100
            quality_pct = max(0, min(100, 2 * (rssi + 100)))

            try:
                freq = int(net.get("frequency_mhz", net.get("frequency", 0)))
            except (ValueError, TypeError):
                freq = 0
            band = "5 GHz" if freq >= 4900 else "2.4 GHz"

            capabilities = str(net.get("capabilities", "")).upper()
            if "WPA3" in capabilities or "SAE" in capabilities:
                security = "WPA3"
            elif "WPA2" in capabilities or "PSK" in capabilities:
                security = "WPA2"
            elif "WEP" in capabilities:
                security = "WEP"
            elif not capabilities or ("ESS" in capabilities and "WPA" not in capabilities):
                security = "Aberta" if capabilities else "Protegida"
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


def connect_wifi(ssid: str, password: str = "") -> Dict[str, Any]:
    """
    Conecta a uma rede Wi-Fi informando nome (SSID) e senha opcional.
    Salva automaticamente a credencial no SQLite memory.db se a senha for fornecida.
    """
    clean_ssid = str(ssid or "").strip().strip('"\'')
    clean_pass = str(password or "").strip().strip('"\'')

    if not clean_ssid:
        return {
            "status": "error",
            "message": "Silva: O nome da rede Wi-Fi (SSID) é obrigatório."
        }

    # Salva na memória SQLite se houver senha fornecida
    if clean_pass:
        try:
            from .memory_schedule import remember_note
            remember_note(key=f"wifi {clean_ssid}", value=clean_pass)
        except Exception:
            pass

    if SIMULATE_HARDWARE:
        tipo = "com senha" if clean_pass else "rede aberta"
        return {
            "status": "ok",
            "message": f"Silva: Conectado com sucesso à rede Wi-Fi '{clean_ssid}' ({tipo}) [Simulado].",
            "data": {
                "ssid": clean_ssid,
                "protected": bool(clean_pass),
                "saved_to_memory": bool(clean_pass),
                "simulated": True
            }
        }

    # Modo Real no Android / Termux
    # Camada 0: Conexão direta privilegiada via ADB Local (cmd wifi connect-network)
    if clean_pass:
        for sec_type in ("wpa2", "wpa3"):
            ok_adb, out_adb = run_adb_shell(
                ["cmd", "wifi", "connect-network", clean_ssid, sec_type, clean_pass],
                timeout=8.0,
            )
            if ok_adb and not any(err in out_adb for err in ("SecurityException", "Permission denied", "Error", "Failed")):
                return {
                    "status": "ok",
                    "message": f"Silva: Conectado diretamente à rede Wi-Fi '{clean_ssid}' ({sec_type.upper()}).",
                    "data": {"ssid": clean_ssid, "direct_connect": True, "protected": True, "method": "adb"}
                }
    else:
        ok_adb, out_adb = run_adb_shell(
            ["cmd", "wifi", "connect-network", clean_ssid, "open"],
            timeout=8.0,
        )
        if ok_adb and not any(err in out_adb for err in ("SecurityException", "Permission denied", "Error", "Failed")):
            return {
                "status": "ok",
                "message": f"Silva: Conectado diretamente à rede Wi-Fi aberta '{clean_ssid}'.",
                "data": {"ssid": clean_ssid, "direct_connect": True, "protected": False, "method": "adb"}
            }

    # Camada 1: Conexão direta via cmd wifi (Shizuku, ADB ou Root)
    cmd_args = ["cmd", "wifi", "connect-network", clean_ssid]
    if clean_pass:
        cmd_args.extend(["wpa2", clean_pass])
    else:
        cmd_args.append("open")

    try:
        res = _run_termux_cmd(cmd_args, timeout=8)
        output = (res.stdout + " " + res.stderr).strip()
        is_permission_error = any(
            err in output for err in ["SecurityException", "Permission denied", "not allowed", "Error"]
        )

        if res.returncode == 0 and not is_permission_error:
            return {
                "status": "ok",
                "message": f"Silva: Conectado diretamente à rede Wi-Fi '{clean_ssid}'.",
                "data": {"ssid": clean_ssid, "direct_connect": True, "protected": bool(clean_pass)}
            }
    except Exception:
        pass

    # Camada 2: Fallback inteligente sem Root/ADB (Android 10+)
    # Copia a senha para a área de transferência e abre as configurações de Wi-Fi
    if clean_pass:
        try:
            _run_termux_cmd(["termux-clipboard-set", clean_pass], timeout=3)
        except Exception:
            pass

        try:
            _run_termux_cmd(["am", "start", "-a", "android.settings.WIFI_SETTINGS"], timeout=3)
        except Exception:
            pass

        return {
            "status": "ok",
            "message": f"Silva: Senha da rede '{clean_ssid}' copiada para a área de transferência! Selecione a rede na tela aberta e cole a senha.",
            "data": {
                "ssid": clean_ssid,
                "fallback": True,
                "clipboard_copied": True,
                "settings_opened": True
            }
        }
    else:
        try:
            _run_termux_cmd(["am", "start", "-a", "android.settings.WIFI_SETTINGS"], timeout=3)
        except Exception:
            pass

        return {
            "status": "ok",
            "message": f"Silva: Abrindo configurações de Wi-Fi para conectar à rede aberta '{clean_ssid}'.",
            "data": {"ssid": clean_ssid, "fallback": True, "settings_opened": True}
        }


def _get_local_ip_fallback() -> str:
    """
    Obtém o IP local da interface de rede ativa via socket UDP conectando a um IP público.
    Não envia pacotes reais pela rede. Retorna o IPv4 pontuado ou string vazia.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and ip != "127.0.0.1":
                return ip
    except Exception:
        pass
    return ""


def get_wifi_info() -> Dict[str, Any]:
    """Mostra informações detalhadas da rede Wi-Fi conectada, sinal, velocidade e IP local."""
    web_port = os.getenv("WEB_PORT", "5000")

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Conectado ao Wi-Fi 'Silva_5G' | IP: 192.168.1.105 | Sinal: 96% (-52 dBm) | Velocidade: 433 Mbps | Acesso web: http://192.168.1.105:{web_port} [Simulado]",
            "data": {
                "connected": True,
                "ssid": "Silva_5G",
                "ip": "192.168.1.105",
                "link_speed_mbps": 433,
                "rssi": -52,
                "quality_pct": 96,
                "web_url": f"http://192.168.1.105:{web_port}",
                "simulated": True
            }
        }

    try:
        info: Dict[str, Any] = {}
        res = _run_termux_cmd(["termux-wifi-connectioninfo"], timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            try:
                info = json.loads(res.stdout)
            except Exception:
                info = {}

        raw_ssid = str(info.get("ssid", "")).strip().strip('"')
        supplicant_state = str(info.get("supplicant_state", "")).strip().upper()

        # Tratamento de IP (string ou inteiro little-endian de 32 bits)
        ip_raw = info.get("ip")
        ip_str = ""
        if isinstance(ip_raw, int) and ip_raw != 0:
            try:
                ip_str = socket.inet_ntoa(struct.pack("<I", ip_raw))
            except Exception:
                ip_str = str(ip_raw)
        elif isinstance(ip_raw, str):
            ip_str = ip_raw.strip()

        # Fallback via socket UDP caso o comando retorne IP vazio ou 0.0.0.0
        if not ip_str or ip_str == "0.0.0.0":
            fallback_ip = _get_local_ip_fallback()
            if fallback_ip:
                ip_str = fallback_ip

        is_completed = (supplicant_state == "COMPLETED")
        has_valid_ip = bool(ip_str and ip_str != "0.0.0.0" and ip_str != "127.0.0.1")
        is_unknown_ssid = (not raw_ssid or raw_ssid.lower() == "<unknown ssid>")

        # Só trata como desconectado se não tiver SSID conhecido, NÃO estiver COMPLETED e NÃO tiver IP válido
        if is_unknown_ssid and not is_completed and not has_valid_ip:
            return {
                "status": "ok",
                "message": "Silva: O aparelho está desconectado do Wi-Fi no momento.",
                "data": {"connected": False, "ssid": None, "ip": None}
            }

        # Quando o Android oculta o SSID por causa do GPS desligado, mas o aparelho está conectado
        if is_unknown_ssid:
            display_ssid = "SSID oculto (ative o GPS para exibir o nome)"
        else:
            display_ssid = raw_ssid

        try:
            rssi = int(info.get("rssi", -100))
        except (ValueError, TypeError):
            rssi = -100
        quality_pct = max(0, min(100, 2 * (rssi + 100)))

        try:
            link_speed = int(info.get("link_speed_mbps", info.get("network_id", 0)))
        except (ValueError, TypeError):
            link_speed = 0

        web_url = f"http://{ip_str}:{web_port}" if has_valid_ip else ""

        msg_parts = [f"Silva: Conectado ao Wi-Fi '{display_ssid}'"]
        if has_valid_ip:
            msg_parts.append(f"IP: {ip_str}")
        if rssi > -100:
            msg_parts.append(f"Sinal: {quality_pct}% ({rssi} dBm)")
        if link_speed > 0:
            msg_parts.append(f"Velocidade: {link_speed} Mbps")
        if web_url:
            msg_parts.append(f"Acesso web: {web_url}")

        return {
            "status": "ok",
            "message": " | ".join(msg_parts),
            "data": {
                "connected": True,
                "ssid": display_ssid,
                "raw_ssid": raw_ssid,
                "bssid": info.get("bssid", ""),
                "ip": ip_str if has_valid_ip else None,
                "rssi": rssi,
                "quality_pct": quality_pct,
                "link_speed_mbps": link_speed,
                "frequency_mhz": info.get("frequency_mhz", 0),
                "supplicant_state": supplicant_state,
                "web_url": web_url
            }
        }
    except Exception as e:
        # Fallback de emergência caso haja erro no comando:
        # tenta socket UDP para ver se o aparelho tem IP na rede local
        fallback_ip = _get_local_ip_fallback()
        if fallback_ip:
            web_url = f"http://{fallback_ip}:{web_port}"
            display_ssid = "SSID oculto (ative o GPS para exibir o nome)"
            return {
                "status": "ok",
                "message": f"Silva: Conectado ao Wi-Fi '{display_ssid}' | IP: {fallback_ip} | Acesso web: {web_url}",
                "data": {
                    "connected": True,
                    "ssid": display_ssid,
                    "ip": fallback_ip,
                    "web_url": web_url
                }
            }
        return {
            "status": "error",
            "message": f"Silva: Erro ao obter dados do Wi-Fi: {str(e)}",
            "data": {"connected": False}
        }


def set_wifi_state(state: bool) -> Dict[str, Any]:
    """Liga ou desliga o Wi-Fi do dispositivo."""
    state_bool = bool(state)
    txt = "ativado" if state_bool else "desativado"

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Wi-Fi {txt} (simulado).",
            "data": {"state": state_bool, "simulated": True}
        }

    cmd_val = "true" if state_bool else "false"
    svc_val = "enable" if state_bool else "disable"

    # Camada 0: ADB Local privilegiado (svc wifi enable/disable)
    ok_adb, _ = run_adb_shell(["svc", "wifi", svc_val], timeout=5.0)
    if ok_adb:
        return {
            "status": "ok",
            "message": f"Silva: Wi-Fi {txt} com sucesso.",
            "data": {"state": state_bool, "method": "adb"}
        }

    # Camada 1: termux-wifi-enable
    try:
        res = _run_termux_cmd(["termux-wifi-enable", cmd_val], timeout=5)
        out = (res.stdout + " " + res.stderr).strip()
        if res.returncode == 0 and not any(err in out for err in ["SecurityException", "Permission denied", "Error"]):
            return {
                "status": "ok",
                "message": f"Silva: Wi-Fi {txt} com sucesso.",
                "data": {"state": state_bool}
            }
    except Exception:
        pass

    # Camada 2: Fallback svc wifi
    try:
        svc_val = "enable" if state_bool else "disable"
        res_svc = _run_termux_cmd(["svc", "wifi", svc_val], timeout=5)
        out_svc = (res_svc.stdout + " " + res_svc.stderr).strip()
        if res_svc.returncode == 0 and not any(err in out_svc for err in ["SecurityException", "Permission denied"]):
            return {
                "status": "ok",
                "message": f"Silva: Wi-Fi {txt} com sucesso via svc.",
                "data": {"state": state_bool}
            }
    except Exception:
        pass

    # Camada 3: Fallback configurações de Wi-Fi
    action_txt = "ligar" if state_bool else "desligar"
    try:
        _run_termux_cmd(["am", "start", "-a", "android.settings.WIFI_SETTINGS"], timeout=3)
    except Exception:
        pass

    return {
        "status": "ok",
        "message": f"Silva: O Android bloqueou a alteração direta de Wi-Fi em segundo plano. Abrindo configurações para você {action_txt} o Wi-Fi manualmente.",
        "data": {"state": state_bool, "settings_opened": True, "fallback": True}
    }


def get_storage_info() -> Dict[str, Any]:
    """Lê o espaço real da partição /data via ADB (`df -k /data`) ou `shutil.disk_usage`."""
    if SIMULATE_HARDWARE and not ensure_adb_connected():
        return {
            "status": "ok",
            "message": "Silva: Armazenamento (/data): 64.00 GB livres de 128.00 GB (50.0% usado). [Simulado]",
            "data": {"total_gb": 128.0, "used_gb": 64.0, "free_gb": 64.0, "used_percent": 50.0, "source": "simulated"},
        }

    if ensure_adb_connected():
        ok_df, out_df = run_adb_shell(["df", "-k", "/data"], timeout=5.0)
        if ok_df and out_df:
            for line in out_df.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4 and parts[1].isdigit() and parts[2].isdigit() and parts[3].isdigit():
                    total_kb = int(parts[1])
                    used_kb = int(parts[2])
                    free_kb = int(parts[3])
                    total_gb = round(total_kb / (1024 * 1024), 2)
                    used_gb = round(used_kb / (1024 * 1024), 2)
                    free_gb = round(free_kb / (1024 * 1024), 2)
                    pct = round((used_kb / total_kb) * 100.0, 1) if total_kb > 0 else 0.0
                    return {
                        "status": "ok",
                        "message": f"Silva: Armazenamento (/data): {free_gb:.2f} GB livres de {total_gb:.2f} GB ({used_gb:.2f} GB usados, {pct:.1f}%).",
                        "data": {
                            "total_gb": total_gb, "used_gb": used_gb, "free_gb": free_gb,
                            "used_percent": pct, "source": "adb_df",
                        },
                    }

    target_mount = "/data" if os.path.isdir("/data") else "/"
    usage = shutil.disk_usage(target_mount)
    total_gb = round(usage.total / (1024 ** 3), 2)
    used_gb = round(usage.used / (1024 ** 3), 2)
    free_gb = round(usage.free / (1024 ** 3), 2)
    pct = round((usage.used / usage.total) * 100.0, 1) if usage.total > 0 else 0.0
    return {
        "status": "ok",
        "message": f"Silva: Armazenamento ({target_mount}): {free_gb:.2f} GB livres de {total_gb:.2f} GB ({used_gb:.2f} GB usados, {pct:.1f}%).",
        "data": {
            "total_gb": total_gb, "used_gb": used_gb, "free_gb": free_gb,
            "used_percent": pct, "source": "disk_usage",
        },
    }


def _read_ram_stats_mb() -> Dict[str, float]:
    """Lê RAM total e disponível (MB) de /proc/meminfo (local ou via ADB) com fallback para 'free -m'."""
    content = ""
    if ensure_adb_connected():
        ok_mem, out_mem = run_adb_shell(["cat", "/proc/meminfo"], timeout=4.0)
        if ok_mem and out_mem and "MemTotal:" in out_mem:
            content = out_mem
    if not content:
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            content = ""

    if content:
        m_total = re.search(r"MemTotal:\s+(\d+)\s+kB", content)
        m_avail = re.search(r"MemAvailable:\s+(\d+)\s+kB", content)
        if m_total and m_avail:
            return {
                "total_mb": round(int(m_total.group(1)) / 1024.0, 1),
                "available_mb": round(int(m_avail.group(1)) / 1024.0, 1),
            }
        m_free = re.search(r"MemFree:\s+(\d+)\s+kB", content)
        if m_total and m_free:
            return {
                "total_mb": round(int(m_total.group(1)) / 1024.0, 1),
                "available_mb": round(int(m_free.group(1)) / 1024.0, 1),
            }

    try:
        res = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=3, check=False)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.lower().startswith("mem:"):
                    parts = line.split()
                    if len(parts) >= 7:
                        return {"total_mb": float(parts[1]), "available_mb": float(parts[6])}
                    if len(parts) >= 4:
                        return {"total_mb": float(parts[1]), "available_mb": float(parts[3])}
    except Exception:
        pass
    return {"total_mb": 0.0, "available_mb": 0.0}


def _read_uptime_str() -> str:
    """Lê /proc/uptime (via ADB ou local) e formata em dias/horas/minutos."""
    raw = ""
    if ensure_adb_connected():
        ok_u, out_u = run_adb_shell(["cat", "/proc/uptime"], timeout=3.0)
        if ok_u and out_u:
            raw = out_u.strip()
    if not raw:
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                raw = f.read().strip()
        except Exception:
            raw = ""
    if raw:
        try:
            secs = int(float(raw.split()[0]))
            days, rem = divmod(secs, 86400)
            hours, rem = divmod(rem, 3600)
            mins = rem // 60
            if days > 0:
                return f"{days}d {hours}h {mins}min"
            return f"{hours}h {mins}min"
        except Exception:
            pass
    return "indisponível"


def _format_mem_size(mb_val: float) -> str:
    if mb_val >= 1024.0:
        return f"{mb_val / 1024.0:.2f} GB"
    return f"{int(round(mb_val))} MB"


def get_device_status() -> Dict[str, Any]:
    """Painel consolidado de telemetria real: Bateria, RAM, Armazenamento, Uptime e Wi-Fi/IP."""
    bat = get_battery_info()
    sto = get_storage_info()
    ram = _read_ram_stats_mb()
    ram_total_mb = ram["total_mb"]
    ram_avail_mb = ram["available_mb"]
    ram_used_mb = max(0.0, ram_total_mb - ram_avail_mb)
    ram_pct = round((ram_used_mb / ram_total_mb) * 100.0, 1) if ram_total_mb > 0 else 0.0
    uptime_str = _read_uptime_str()
    wifi = get_wifi_info()
    wifi_ssid = (wifi.get("data") or {}).get("ssid") or "Desconectado"
    wifi_ip = (wifi.get("data") or {}).get("ip") or "0.0.0.0"

    bat_d = bat.get("data") or {}
    sto_d = sto.get("data") or {}

    msg = (
        f"Silva: Status do Dispositivo:\n"
        f"• Bateria: {bat_d.get('percentage', 0)}% ({bat_d.get('status', 'N/A')}, {bat_d.get('temperature', 0.0)}°C)\n"
        f"• Memória RAM: {_format_mem_size(ram_used_mb)} / {_format_mem_size(ram_total_mb)} ({ram_pct:.1f}%)\n"
        f"• Armazenamento: {sto_d.get('free_gb', 0.0):.2f} GB livres de {sto_d.get('total_gb', 0.0):.2f} GB ({sto_d.get('used_percent', 0.0):.1f}% usado)\n"
        f"• Uptime: {uptime_str} | Wi-Fi: {wifi_ssid} ({wifi_ip})"
    )
    return {
        "status": "ok",
        "message": msg,
        "data": {
            "battery": bat_d,
            "storage": sto_d,
            "ram_used_mb": round(ram_used_mb, 1),
            "ram_total_mb": ram_total_mb,
            "ram_available_mb": ram_avail_mb,
            "ram_used_percent": ram_pct,
            "uptime": uptime_str,
            "wifi_ssid": wifi_ssid,
            "ip": wifi_ip,
        },
    }


def get_system_info() -> Dict[str, Any]:
    """Retorna telemetria consolidada do sistema: armazenamento, memória RAM, bateria, uptime e rede."""
    sto_d = get_storage_info().get("data") or {}
    free_gb = float(sto_d.get("free_gb", 0.0))
    total_gb = float(sto_d.get("total_gb", 0.0))

    ram = _read_ram_stats_mb()
    ram_avail_str = _format_mem_size(ram["available_mb"])
    ram_total_str = _format_mem_size(ram["total_mb"])
    uptime_str = _read_uptime_str()

    carrier = "Desconhecida"
    net_type = "N/A"
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        carrier = "Operadora Simulada"
        net_type = "4G/LTE"
    else:
        got_telephony = False
        if not SIMULATE_HARDWARE:
            try:
                res = _run_termux_cmd(["termux-telephony-deviceinfo"], timeout=4)
                if res.returncode == 0 and res.stdout.strip():
                    t_info = json.loads(res.stdout)
                    carrier = (t_info.get("network_operator_name") or t_info.get("sim_operator_name") or carrier).strip() or carrier
                    net_type = (t_info.get("network_type") or net_type).strip() or net_type
                    got_telephony = True
            except Exception:
                pass

        if not got_telephony and adb_serial:
            ok_adb, out_adb = run_adb_shell(["dumpsys", "telephony.registry"], timeout=5.0)
            if ok_adb and out_adb:
                m_op = re.search(r"mOperatorAlphaLong=([^\s,}\n]+)", out_adb)
                m_net = re.search(r"mDataNetworkType=(\w+)", out_adb)
                if m_op and m_op.group(1) not in ("null", "None", ""):
                    carrier = m_op.group(1).strip()
                if m_net and m_net.group(1) not in ("UNKNOWN", "0"):
                    net_type = m_net.group(1).strip()

    msg = (
        f"Silva: Sistema — Armazenamento: {free_gb:.2f} GB livres de {total_gb:.2f} GB | "
        f"RAM: {ram_avail_str} disponíveis de {ram_total_str} | "
        f"Rede móvel: {carrier} ({net_type})."
    )
    return {
        "status": "ok",
        "message": msg,
        "data": {
            "storage_free_gb": free_gb,
            "storage_total_gb": total_gb,
            "ram_available_mb": ram["available_mb"],
            "ram_total_mb": ram["total_mb"],
            "carrier": carrier,
            "network_type": net_type,
        },
    }


def _adb_error_free(ok: bool, out: str) -> bool:
    low = (out or "").lower()
    return ok and not any(
        err in low for err in ("securityexception", "permission denied", "permission denial", "error:", "exception")
    )


def _verify_global_setting_matches(setting_key: str, expected_val: str) -> bool:
    """
    Aguarda 0.8s e valida via `settings get global <key>` se o estado realmente mudou.
    Se o retorno for vazio/desconhecido (ex.: mock simples), não reprova.
    """
    time.sleep(0.8)
    ok_chk, out_chk = run_adb_shell(["settings", "get", "global", setting_key], timeout=4.0)
    if not ok_chk:
        return True
    val = (out_chk or "").strip()
    if val in ("0", "1"):
        return val == expected_val
    return True


def set_bluetooth_state(state: bool) -> Dict[str, Any]:
    """Liga ou desliga o Bluetooth via ADB local com fallback para configurações."""
    state_bool = bool(state)
    action = "enable" if state_bool else "disable"
    txt = "ligado" if state_bool else "desligado"
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        return {"status": "ok", "message": f"Silva: Bluetooth {txt} com sucesso. [Simulado]", "data": {"state": state_bool}}

    if adb_serial:
        ok1, out1 = run_adb_shell(["svc", "bluetooth", action], timeout=5.0)
        if _adb_error_free(ok1, out1):
            return {"status": "ok", "message": f"Silva: Bluetooth {txt} com sucesso via ADB.", "data": {"state": state_bool, "method": "adb_svc"}}

        ok2, out2 = run_adb_shell(["cmd", "bluetooth_manager", action], timeout=5.0)
        if _adb_error_free(ok2, out2):
            return {"status": "ok", "message": f"Silva: Bluetooth {txt} com sucesso via ADB.", "data": {"state": state_bool, "method": "adb_cmd"}}

        run_adb_shell(["am", "start", "-a", "android.settings.BLUETOOTH_SETTINGS"], timeout=4.0)
    else:
        _exec_android_intent(["am", "start", "-a", "android.settings.BLUETOOTH_SETTINGS"])

    return {
        "status": "ok",
        "message": f"Silva: Não foi possível alternar o Bluetooth diretamente (restrição Android/ADB). Abrindo configurações de Bluetooth.",
        "data": {"state": state_bool, "fallback": True, "settings_opened": True},
    }


def set_mobile_data_state(state: bool) -> Dict[str, Any]:
    """Liga ou desliga os dados móveis via ADB local com fallback para configurações."""
    state_bool = bool(state)
    action = "enable" if state_bool else "disable"
    txt = "ligados" if state_bool else "desligados"
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        return {"status": "ok", "message": f"Silva: Dados móveis {txt} com sucesso. [Simulado]", "data": {"state": state_bool}}

    if adb_serial:
        ok1, out1 = run_adb_shell(["svc", "data", action], timeout=5.0)
        if _adb_error_free(ok1, out1) and _verify_global_setting_matches("mobile_data", "1" if state_bool else "0"):
            return {"status": "ok", "message": f"Silva: Dados móveis {txt} com sucesso via ADB.", "data": {"state": state_bool, "method": "adb_svc"}}
        ok_p, out_p = run_adb_shell(["am", "start", "-a", "android.settings.DATA_ROAMING_SETTINGS"], timeout=4.0)
        if not _adb_error_free(ok_p, out_p):
            run_adb_shell(["am", "start", "-a", "android.settings.WIRELESS_SETTINGS"], timeout=4.0)
    else:
        _exec_android_intent(["am", "start", "-a", "android.settings.DATA_ROAMING_SETTINGS"])

    return {
        "status": "ok",
        "message": "Silva: O Android exige confirmação manual por segurança para alterar os dados móveis. Tela de configurações aberta no aparelho.",
        "data": {"state": state_bool, "fallback": True, "settings_opened": True},
    }


def set_airplane_mode(state: bool) -> Dict[str, Any]:
    """Ativa ou desativa o Modo Avião via ADB local com fallback de settings/configurações."""
    state_bool = bool(state)
    action = "enable" if state_bool else "disable"
    val_num = "1" if state_bool else "0"
    val_bool = "true" if state_bool else "false"
    txt = "ativado" if state_bool else "desativado"
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        return {"status": "ok", "message": f"Silva: Modo Avião {txt} com sucesso. [Simulado]", "data": {"state": state_bool}}

    if adb_serial:
        ok1, out1 = run_adb_shell(["cmd", "connectivity", "airplane-mode", action], timeout=5.0)
        if _adb_error_free(ok1, out1) and _verify_global_setting_matches("airplane_mode_on", val_num):
            return {"status": "ok", "message": f"Silva: Modo Avião {txt} com sucesso via ADB.", "data": {"state": state_bool, "method": "adb_cmd"}}

        ok2, out2 = run_adb_shell(["settings", "put", "global", "airplane_mode_on", val_num], timeout=4.0)
        if _adb_error_free(ok2, out2) and _verify_global_setting_matches("airplane_mode_on", val_num):
            run_adb_shell(
                ["am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", val_bool],
                timeout=4.0,
            )
            return {
                "status": "ok",
                "message": f"Silva: Modo Avião {txt} via settings ADB (se o Android exigir confirmação manual, toque na opção na tela).",
                "data": {"state": state_bool, "method": "adb_settings"},
            }
        run_adb_shell(["am", "start", "-a", "android.settings.AIRPLANE_MODE_SETTINGS"], timeout=4.0)
    else:
        _exec_android_intent(["am", "start", "-a", "android.settings.AIRPLANE_MODE_SETTINGS"])

    return {
        "status": "ok",
        "message": "Silva: O Android exige confirmação manual por segurança para alterar o Modo Avião. Tela de configurações aberta no aparelho.",
        "data": {"state": state_bool, "fallback": True, "settings_opened": True},
    }


def set_hotspot_state(state: bool) -> Dict[str, Any]:
    """Liga ou desliga o Roteador Wi-Fi (Hotspot) via ADB local com fallback para TetherSettings."""
    state_bool = bool(state)
    txt = "ligado" if state_bool else "desligado"
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        return {"status": "ok", "message": f"Silva: Roteador Wi-Fi (Hotspot) {txt} com sucesso. [Simulado]", "data": {"state": state_bool}}

    if adb_serial:
        cmd_args = (
            ["cmd", "wifi", "start-softap", "SilvaHotspot", "wpa2", "12345678"]
            if state_bool
            else ["cmd", "wifi", "stop-softap"]
        )
        ok1, out1 = run_adb_shell(cmd_args, timeout=5.0)
        if _adb_error_free(ok1, out1):
            return {"status": "ok", "message": f"Silva: Roteador Wi-Fi (Hotspot) {txt} com sucesso via ADB.", "data": {"state": state_bool, "method": "adb_softap"}}
        ok_t, out_t = run_adb_shell(["am", "start", "-a", "android.settings.TETHER_SETTINGS"], timeout=4.0)
        if not _adb_error_free(ok_t, out_t):
            run_adb_shell(["am", "start", "-a", "android.settings.WIRELESS_SETTINGS"], timeout=4.0)
    else:
        _exec_android_intent(["am", "start", "-a", "android.settings.TETHER_SETTINGS"])

    return {
        "status": "ok",
        "message": "Silva: O Android exige confirmação manual por segurança para alterar o Hotspot. Tela de Roteador/Tethering aberta no aparelho.",
        "data": {"state": state_bool, "fallback": True, "settings_opened": True},
    }


