"""
Testes automatizados para ui_automator.py, automação real do WhatsApp
e interação com elementos da tela via ADB (uiautomator).
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

from android_agent.tools import ui_automator, comms, apps_mobility
from android_agent.intent_fallback import match_intent_fallback

SAMPLE_WHATSAPP_XML = """UI hierchary dumped to: /sdcard/silva_ui.xml
<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" clickable="false" enabled="true" bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="com.whatsapp:id/menuitem_search" content-desc="Pesquisar" class="android.widget.ImageButton" clickable="true" enabled="true" bounds="[860,110][960,210]" />
    <node index="1" text="" resource-id="com.whatsapp:id/entry" content-desc="Mensagem" class="android.widget.EditText" clickable="true" enabled="true" bounds="[140,2140][960,2250]" />
    <node index="2" text="" resource-id="com.whatsapp:id/send" content-desc="Enviar" class="android.widget.ImageButton" clickable="true" enabled="true" bounds="[980,2150][1070,2240]" />
    <node index="3" text="" resource-id="com.whatsapp:id/confirm_container" class="android.widget.LinearLayout" clickable="true" enabled="true" bounds="[100,1200][500,1320]">
      <node index="0" text="Confirmar" resource-id="com.whatsapp:id/confirm_label" class="android.widget.TextView" clickable="false" enabled="true" bounds="[140,1230][460,1290]" />
    </node>
  </node>
</hierarchy>
"""


class TestUiAutomator(unittest.TestCase):
    """Testa dump XML, cálculo de bounds, busca semântica, WhatsApp e tela."""

    def test_dump_ui_nodes_and_exact_center_bounds(self):
        def fake_adb(args, timeout=6.0):
            if args[:2] == ["uiautomator", "dump"]:
                return True, "UI hierchary dumped to: /sdcard/silva_ui.xml"
            if args[:2] == ["cat", "/sdcard/silva_ui.xml"]:
                return True, SAMPLE_WHATSAPP_XML
            return False, ""

        with patch("android_agent.tools.ui_automator.run_adb_shell", side_effect=fake_adb):
            nodes = ui_automator.dump_ui_nodes()

        self.assertGreaterEqual(len(nodes), 5)
        send_node = ui_automator.find_ui_node("Enviar", nodes=nodes, clickable_only=True)
        self.assertIsNotNone(send_node)
        self.assertEqual(send_node["bounds"], (980, 2150, 1070, 2240))
        self.assertEqual((send_node["cx"], send_node["cy"]), (1025, 2195))

    def test_find_clickable_parent_from_non_clickable_textview(self):
        with patch(
            "android_agent.tools.ui_automator.run_adb_shell",
            side_effect=[
                (True, "UI hierchary dumped to: /sdcard/silva_ui.xml"),
                (True, SAMPLE_WHATSAPP_XML),
            ],
        ):
            nodes = ui_automator.dump_ui_nodes()

        container = ui_automator.find_ui_node("Confirmar", nodes=nodes, clickable_only=True)
        self.assertIsNotNone(container)
        self.assertTrue(container["clickable"])
        self.assertEqual(container["resource_id"], "com.whatsapp:id/confirm_container")
        self.assertEqual((container["cx"], container["cy"]), (300, 1260))

    def test_type_text_unicode_preserves_accents_via_clipboard(self):
        adb_calls = []

        def fake_adb(args, timeout=6.0):
            adb_calls.append(args)
            return True, ""

        with patch("android_agent.tools.ui_automator._set_device_clipboard", return_value=True) as mock_clip, \
             patch("android_agent.tools.ui_automator.run_adb_shell", side_effect=fake_adb):
            ok, _ = ui_automator.type_text_unicode("Olá João, ação concluída!")

        self.assertTrue(ok)
        mock_clip.assert_called_once_with("Olá João, ação concluída!")
        self.assertIn(["input", "keyevent", "279"], adb_calls)

    def test_whatsapp_full_automated_send_with_adb(self):
        adb_commands = []

        def fake_adb(args, timeout=6.0):
            adb_commands.append(args)
            if args[:2] == ["am", "start"]:
                return True, "Starting: Intent"
            if args[:2] == ["uiautomator", "dump"]:
                return True, "UI hierchary dumped to: /sdcard/silva_ui.xml"
            if args[:2] == ["cat", "/sdcard/silva_ui.xml"]:
                return True, SAMPLE_WHATSAPP_XML
            if args[:2] == ["input", "tap"]:
                return True, ""
            return True, ""

        with patch("android_agent.tools.comms._resolve_whatsapp_target", return_value=("5581999998888", "João")), \
             patch("android_agent.tools.comms.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.comms.run_adb_shell", side_effect=fake_adb), \
             patch("android_agent.tools.ui_automator.run_adb_shell", side_effect=fake_adb), \
             patch("android_agent.tools.comms.time.sleep", return_value=None):
            res = comms.send_sms("João", "Bom dia, reunião às 10h!", channel="whatsapp")

        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["data"]["sent"])
        self.assertIn("Mensagem enviada no WhatsApp para João", res["message"])
        self.assertTrue(any(cmd[:2] == ["am", "start"] and "5581999998888" in " ".join(cmd) for cmd in adb_commands))
        self.assertIn(["input", "tap", "1025", "2195"], adb_commands)

    def test_whatsapp_fallback_when_adb_disconnected(self):
        with patch("android_agent.tools.comms.SIMULATE_HARDWARE", False), \
             patch("android_agent.tools.comms._resolve_whatsapp_target", return_value=("5581999998888", "Maria")), \
             patch("android_agent.tools.comms.ensure_adb_connected", return_value=None), \
             patch("android_agent.tools.comms._exec_android_intent", return_value=True):
            res = comms.send_sms("Maria", "Oi!", channel="whatsapp")

        self.assertEqual(res["status"], "ok")
        self.assertFalse(res["data"]["sent"])
        self.assertIn("Conversa aberta no WhatsApp para Maria", res["message"])
        self.assertIn("Toque em enviar", res["message"])

    def test_nlp_whatsapp_and_screen_interaction_routing(self):
        call_wpp = match_intent_fallback("manda mensagem no whatsapp para João dizendo Cheguei agora")
        self.assertIsNotNone(call_wpp)
        self.assertIn("send_sms(", call_wpp)
        self.assertIn("channel='whatsapp'", call_wpp)
        self.assertIn("João", call_wpp)

        call_piped = match_intent_fallback("Vê quanto está minha bateria e manda no WhatsApp para o João")
        self.assertIsNotNone(call_piped)
        self.assertIn("<call>get_battery()</call>", call_piped)
        self.assertIn("send_sms(", call_piped)
        self.assertIn("channel='whatsapp'", call_piped)
        self.assertIn("$prev_result", call_piped)

        call_tap = match_intent_fallback("clica em Confirmar")
        self.assertIsNotNone(call_tap)
        self.assertIn("open_app(", call_tap)
        self.assertIn("action='tap'", call_tap)
        self.assertIn("Confirmar", call_tap)

        with patch("android_agent.tools.apps_mobility.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.apps_mobility.tap_element", return_value=(True, "Tocado em 'Confirmar' nas coordenadas (300, 1260).")):
            tap_res = apps_mobility.open_app("ui:tap:Confirmar", action="tap", label="Confirmar")
            self.assertEqual(tap_res["status"], "ok")
            self.assertIn("Confirmar", tap_res["message"])


if __name__ == "__main__":
    unittest.main()
