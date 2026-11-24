"""
Testes da Ponte ADB Local (adb_bridge.py) e integração com fallback transparente para Termux:API.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

import android_agent.tools.adb_bridge as adb_bridge
import android_agent.tools.hardware as tools_hw
import android_agent.tools.weather_web as tools_weather
import android_agent.tools.media as tools_media
import android_agent.tools.comms as tools_comms


class TestAdbBridge(unittest.TestCase):
    """Testes isolados de adb_bridge e integração privilegiada nas ferramentas."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp_dir)

    def test_ensure_adb_connected_reconnects_target_and_runs_shell(self):
        """Valida auto-reconexão via ADB_TARGET e execução segura sem shell=True."""
        calls = []
        devices_calls = {"count": 0}

        def fake_run(cmd, capture_output=True, text=True, timeout=3.0, check=False):
            calls.append(cmd)
            if cmd == ["/usr/bin/adb", "devices"]:
                devices_calls["count"] += 1
                if devices_calls["count"] == 1:
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="List of devices attached\n\n", stderr="")
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="List of devices attached\n127.0.0.1:37845\tdevice\n",
                    stderr="",
                )
            if cmd == ["/usr/bin/adb", "connect", "127.0.0.1:37845"]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="connected to 127.0.0.1:37845", stderr="")
            if cmd == ["/usr/bin/adb", "-s", "127.0.0.1:37845", "shell", "svc", "wifi", "enable"]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unknown")

        with patch.dict(os.environ, {"ADB_TARGET": "127.0.0.1:37845"}), \
             patch("shutil.which", return_value="/usr/bin/adb"), \
             patch("subprocess.run", side_effect=fake_run):
            serial = adb_bridge.ensure_adb_connected()
            self.assertEqual(serial, "127.0.0.1:37845")
            ok, _ = adb_bridge.run_adb_shell(["svc", "wifi", "enable"])
            self.assertTrue(ok)
            self.assertIn(["/usr/bin/adb", "connect", "127.0.0.1:37845"], calls)

    def test_grant_termux_permissions(self):
        """Valida aplicação automática de appops e permissões via ADB."""
        executed = []

        def fake_shell(args, timeout=6.0):
            executed.append(args)
            return True, ""

        with patch.object(adb_bridge, "ensure_adb_connected", return_value="127.0.0.1:37845"), \
             patch.object(adb_bridge, "run_adb_shell", side_effect=fake_shell):
            granted = adb_bridge.grant_termux_permissions()
            self.assertEqual(len(granted), 7)
            self.assertTrue(any(c[:3] == ["appops", "set", "com.termux.api"] for c in executed))
            self.assertTrue(any("android.permission.CALL_PHONE" in c for c in executed))

    def test_tools_via_adb_when_connected(self):
        """Valida execução privilegiada via ADB em set_wifi_state, connect_wifi, set_location_state, set_dnd, make_call e take_screenshot."""
        adb_cmds = []

        def fake_adb_shell(args, timeout=6.0):
            adb_cmds.append(args)
            return True, ""

        def fake_pull(remote_path, local_path, timeout=8.0):
            # Escreve PNG válido (>= 10KB para passar em _is_valid_png)
            png_header = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 11000)
            local_path.write_bytes(png_header)
            return True

        with patch.object(tools_hw, "SIMULATE_HARDWARE", False), \
             patch.object(tools_weather, "SIMULATE_HARDWARE", False), \
             patch.object(tools_media, "SIMULATE_HARDWARE", False), \
             patch.object(tools_comms, "SIMULATE_HARDWARE", False), \
             patch.object(tools_media, "CAPTURES_DIR", self.tmp_path), \
             patch.object(tools_hw, "run_adb_shell", side_effect=fake_adb_shell), \
             patch.object(tools_weather, "run_adb_shell", side_effect=fake_adb_shell), \
             patch.object(tools_media, "ensure_adb_connected", return_value="127.0.0.1:37845"), \
             patch.object(tools_media, "run_adb_shell", side_effect=fake_adb_shell), \
             patch.object(tools_media, "pull_adb_file", side_effect=fake_pull), \
             patch.object(tools_comms, "run_adb_shell", side_effect=fake_adb_shell):

            r_wifi = tools_hw.set_wifi_state(True)
            self.assertEqual(r_wifi["data"]["method"], "adb")
            self.assertIn(["svc", "wifi", "enable"], adb_cmds)

            r_conn = tools_hw.connect_wifi("Casa_5G", "Senha@123")
            self.assertEqual(r_conn["data"]["method"], "adb")
            self.assertIn(["cmd", "wifi", "connect-network", "Casa_5G", "wpa2", "Senha@123"], adb_cmds)

            r_loc = tools_weather.set_location_state(True)
            self.assertEqual(r_loc["data"]["method"], "adb")
            self.assertIn(["cmd", "location", "set-location-enabled", "true"], adb_cmds)

            r_dnd = tools_hw.set_dnd(True)
            self.assertEqual(r_dnd["data"]["method"], "adb")
            self.assertIn(["cmd", "notification", "set_dnd", "on"], adb_cmds)

            r_call = tools_comms.make_call(target="11988887777")
            self.assertEqual(r_call["data"]["method"], "adb_call")
            self.assertIn(["am", "start", "-a", "android.intent.action.CALL", "-d", "tel:11988887777"], adb_cmds)

            r_shot = tools_media.take_screenshot()
            self.assertEqual(r_shot["status"], "ok")
            self.assertEqual(r_shot["data"]["method"], "adb")
            self.assertTrue(any(c[0] == "screencap" for c in adb_cmds))

    def test_transparent_fallback_when_adb_disconnected(self):
        """Valida fallback limpo para Termux:API quando ensure_adb_connected() retorna None."""
        termux_calls = []

        def fake_termux_cmd(cmd, timeout=10):
            termux_calls.append(cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch.object(adb_bridge, "ensure_adb_connected", return_value=None), \
             patch.object(tools_hw, "SIMULATE_HARDWARE", False), \
             patch.object(tools_comms, "SIMULATE_HARDWARE", False), \
             patch.object(tools_hw, "_run_termux_cmd", side_effect=fake_termux_cmd), \
             patch.object(tools_comms, "_run_termux_cmd", side_effect=fake_termux_cmd):

            r_wifi = tools_hw.set_wifi_state(False)
            self.assertEqual(r_wifi["status"], "ok")
            self.assertIn(["termux-wifi-enable", "false"], termux_calls)

            r_call = tools_comms.make_call(target="11988887777")
            self.assertEqual(r_call["status"], "ok")
            self.assertEqual(r_call["data"]["method"], "telephony_call")
            self.assertIn(["termux-telephony-call", "11988887777"], termux_calls)


if __name__ == "__main__":
    unittest.main()
