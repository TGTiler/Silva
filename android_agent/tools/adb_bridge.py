"""
Ponte ADB Local (Depuração por Wi-Fi em localhost / 127.0.0.1) com fallback transparente.
Permite executar comandos privilegiados (svc, cmd, appops, pm, screencap, input, am, monkey)
sem root no Android 14/15 (One UI 7.0), mantendo 100% de compatibilidade caso o ADB esteja offline.
"""

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import List, Optional, Tuple

_ADB_LOCK = threading.RLock()


def _get_adb_bin() -> Optional[str]:
    """Localiza o binário adb no PATH."""
    return shutil.which("adb")


def _get_adb_target() -> str:
    """Lê ADB_TARGET do ambiente ou do .env caso atualizado em runtime."""
    target = os.getenv("ADB_TARGET", "").strip()
    if target:
        return target
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.is_file():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("ADB_TARGET="):
                        return s.split("=", 1)[1].strip().strip("'\"")
    except Exception:
        pass
    return ""


def _parse_connected_local_serial(devices_output: str, target: str = "") -> Optional[str]:
    """Extrai o serial local (127.0.0.1:* ou localhost:* ou ADB_TARGET) com status 'device'."""
    for line in (devices_output or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serial = parts[0]
            if serial.startswith(("127.0.0.1:", "localhost:")) or (target and serial == target):
                return serial
    return None


def ensure_adb_connected() -> Optional[str]:
    """
    Detecta se há uma sessão ADB local ativa (127.0.0.1:* ou localhost:*).
    Se desconectado e ADB_TARGET estiver configurado, tenta 'adb connect <ADB_TARGET>'.
    Nunca lança exceções; retorna None caso indisponível.
    """
    adb_bin = _get_adb_bin()
    if not adb_bin:
        return None

    target = _get_adb_target()

    with _ADB_LOCK:
        try:
            res = subprocess.run(
                [adb_bin, "devices"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                serial = _parse_connected_local_serial(res.stdout, target)
                if serial:
                    return serial
        except Exception:
            return None

        if not target:
            return None

        # Tenta reconectar ao alvo configurado
        try:
            subprocess.run(
                [adb_bin, "connect", target],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            res2 = subprocess.run(
                [adb_bin, "devices"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            if res2.returncode == 0:
                return _parse_connected_local_serial(res2.stdout, target)
        except Exception:
            return None

    return None


def run_adb_shell(args: List[str], timeout: float = 6.0) -> Tuple[bool, str]:
    """
    Executa ['adb', '-s', serial, 'shell', *args] sem shell=True.
    Retorna (sucesso, stdout_ou_erro).
    """
    if not args:
        return False, "Comando ADB vazio."

    adb_bin = _get_adb_bin()
    if not adb_bin:
        return False, "Binário adb não encontrado."

    serial = ensure_adb_connected()
    if not serial:
        return False, "ADB local não conectado."

    try:
        res = subprocess.run(
            [adb_bin, "-s", serial, "shell", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = (res.stdout or "").strip()
        stderr = (res.stderr or "").strip()
        if res.returncode == 0:
            return True, stdout
        return False, stderr or stdout or f"Erro ADB (exit {res.returncode})"
    except Exception as e:
        return False, str(e)


def pull_adb_file(remote_path: str, local_path: Path, timeout: float = 8.0) -> bool:
    """Copia um arquivo do dispositivo via 'adb -s <serial> pull' sem shell=True."""
    adb_bin = _get_adb_bin()
    if not adb_bin:
        return False
    serial = ensure_adb_connected()
    if not serial:
        return False
    try:
        res = subprocess.run(
            [adb_bin, "-s", serial, "pull", remote_path, str(local_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return res.returncode == 0 and local_path.is_file()
    except Exception:
        return False


def grant_termux_permissions() -> List[str]:
    """
    Aplica permissões privilegiadas e appops para Termux e Termux:API quando o ADB local estiver conectado.
    Retorna a lista de permissões aplicadas com sucesso.
    """
    if not ensure_adb_connected():
        return []

    specs = [
        ("READ_CLIPBOARD (com.termux.api)", ["appops", "set", "com.termux.api", "READ_CLIPBOARD", "allow"]),
        ("READ_CLIPBOARD (com.termux)", ["appops", "set", "com.termux", "READ_CLIPBOARD", "allow"]),
        ("CALL_PHONE", ["pm", "grant", "com.termux.api", "android.permission.CALL_PHONE"]),
        ("ACCESS_FINE_LOCATION", ["pm", "grant", "com.termux.api", "android.permission.ACCESS_FINE_LOCATION"]),
        ("CAMERA", ["pm", "grant", "com.termux.api", "android.permission.CAMERA"]),
        ("RECORD_AUDIO", ["pm", "grant", "com.termux.api", "android.permission.RECORD_AUDIO"]),
        ("READ_CONTACTS", ["pm", "grant", "com.termux.api", "android.permission.READ_CONTACTS"]),
    ]

    granted: List[str] = []
    for label, cmd in specs:
        ok, _ = run_adb_shell(cmd, timeout=5.0)
        if ok:
            granted.append(label)
    return granted
