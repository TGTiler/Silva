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
        self.assertIn("send_whatsapp(", call_wpp)
        self.assertIn("João", call_wpp)

        call_piped = match_intent_fallback("Vê quanto está minha bateria e manda no WhatsApp para o João")
        self.assertIsNotNone(call_piped)
        self.assertIn("<call>get_battery()</call>", call_piped)
        self.assertIn("send_whatsapp(", call_piped)
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

    def test_send_whatsapp_and_summarize_notifications(self):
        import json
        import subprocess

        # 1. send_whatsapp com sucesso via ADB + ui_automator
        adb_cmds = []

        def fake_adb(args, timeout=6.0):
            adb_cmds.append(args)
            if args[:2] == ["uiautomator", "dump"]:
                return True, "UI hierchary dumped to: /sdcard/silva_ui.xml"
            if args[:2] == ["cat", "/sdcard/silva_ui.xml"]:
                return True, SAMPLE_WHATSAPP_XML
            return True, ""

        with patch("android_agent.tools.comms.resolve_contact_detailed", return_value={"number": "81999998888", "name": "João", "source": "android_contacts", "ambiguous": False, "candidates": []}), \
             patch("android_agent.tools.comms.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.comms.run_adb_shell", side_effect=fake_adb), \
             patch("android_agent.tools.ui_automator.run_adb_shell", side_effect=fake_adb), \
             patch("android_agent.tools.comms.time.sleep", return_value=None):
            res_ok = comms.send_whatsapp("João", "Tô chegando!")
            self.assertEqual(res_ok["status"], "ok")
            self.assertTrue(res_ok["data"]["sent"])
            self.assertTrue(any("https://wa.me/5581999998888" in " ".join(c) for c in adb_cmds))
            self.assertIn(["input", "tap", "1025", "2195"], adb_cmds)

        # 2. send_whatsapp desambiguação e fallback ADB offline
        with patch("android_agent.tools.comms.resolve_contact_detailed", return_value={"number": None, "name": None, "source": "ambiguous", "ambiguous": True, "candidates": [{"name": "João A", "number": "111"}, {"name": "João B", "number": "222"}]}):
            res_amb = comms.send_whatsapp("João", "Oi")
            self.assertEqual(res_amb["status"], "error")
            self.assertIn("João A", res_amb["message"])

        with patch("android_agent.tools.comms.SIMULATE_HARDWARE", False), \
             patch("android_agent.tools.comms.resolve_contact_detailed", return_value={"number": "11999998888", "name": "Maria", "source": "direct", "ambiguous": False, "candidates": []}), \
             patch("android_agent.tools.comms.ensure_adb_connected", return_value=None), \
             patch("android_agent.tools.comms._exec_android_intent", return_value=True):
            res_off = comms.send_whatsapp("11999998888", "Já saí")
            self.assertEqual(res_off["status"], "ok")
            self.assertFalse(res_off["data"]["sent"])
            self.assertIn("aguarda toque manual", res_off["message"])

        # 3. summarize_notifications filtrando ruído técnico e agrupando por app
        mock_notifs = [
            {"packageName": "com.whatsapp", "title": "João", "content": "Oi, tudo bem?"},
            {"packageName": "com.nu.production", "title": "Nubank", "content": "Pix recebido de R$ 100"},
            {"packageName": "com.android.systemui", "title": "Sistema", "content": "Carregando"},
            {"packageName": "android", "title": "USB", "content": "Depuração USB conectada"},
        ]
        mock_proc = subprocess.CompletedProcess(
            args=["termux-notification-list"], returncode=0, stdout=json.dumps(mock_notifs), stderr=""
        )
        with patch("android_agent.tools.comms.SIMULATE_HARDWARE", False), \
             patch("android_agent.tools.comms.ensure_adb_connected", return_value=None), \
             patch("android_agent.tools.comms._run_termux_cmd", return_value=mock_proc):
            sum_all = comms.summarize_notifications()
            self.assertEqual(sum_all["status"], "ok")
            self.assertEqual(sum_all["data"]["total"], 2)
            self.assertIn("WhatsApp (1)", sum_all["message"])
            self.assertIn("Bancos (1)", sum_all["message"])
            self.assertNotIn("Depuração USB", sum_all["message"])

            sum_wpp = comms.summarize_notifications(app_filter="whatsapp")
            self.assertEqual(sum_wpp["data"]["total"], 1)

        # 4. Roteamento NLP
        self.assertEqual(match_intent_fallback("tem algo importante nas notificações?"), "<call>summarize_notifications(app_filter='')</call>")
        self.assertEqual(match_intent_fallback("notificações do whatsapp"), "<call>summarize_notifications(app_filter='whatsapp')</call>")

    def test_ifood_dynamic_placeholder_ignores_bottom_nav_and_dismisses_modal(self):
        import subprocess

        # 1. XML com modal promocional -> após fechar, barra superior "Mercado perto de mim" (y < 22%) e aba "Busca" (y > 85%)
        modal_nodes = [
            {"text": "Fechar", "content_desc": "Fechar", "resource_id": "", "class_name": "android.widget.Button", "clickable": True, "x1": 900, "y1": 120, "x2": 1020, "y2": 200, "cx": 960, "cy": 160},
            {"text": "Aproveite 50% OFF", "content_desc": "", "resource_id": "", "class_name": "android.widget.TextView", "clickable": False, "x1": 100, "y1": 800, "x2": 980, "y2": 900, "cx": 540, "cy": 850},
        ]
        home_nodes = [
            {"text": "Mercado perto de mim", "content_desc": "", "resource_id": "br.com.brainweb.ifood:id/search_bar", "class_name": "android.widget.TextView", "clickable": True, "x1": 40, "y1": 120, "x2": 1040, "y2": 240, "cx": 540, "cy": 180},
            {"text": "Busca", "content_desc": "Busca", "resource_id": "br.com.brainweb.ifood:id/nav_search", "class_name": "android.widget.FrameLayout", "clickable": True, "x1": 220, "y1": 2180, "x2": 420, "y2": 2360, "cx": 320, "cy": 2270},
        ]
        search_focus_nodes = [
            {"text": "", "content_desc": "Buscar em todo o iFood", "resource_id": "br.com.brainweb.ifood:id/input_query", "class_name": "android.widget.EditText", "clickable": True, "x1": 120, "y1": 120, "x2": 1020, "y2": 230, "cx": 570, "cy": 175},
        ]

        with patch.object(apps_mobility, "SIMULATE_HARDWARE", False), \
             patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:38893"), \
             patch.object(apps_mobility, "_exec_android_intent", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Starting: Intent", stderr="")), \
             patch.object(apps_mobility, "get_screen_dimensions", return_value=(1080, 2400)), \
             patch.object(apps_mobility, "dump_ui_nodes", side_effect=[modal_nodes, home_nodes, search_focus_nodes]), \
             patch.object(apps_mobility, "tap_coords") as mock_tap, \
             patch.object(apps_mobility, "type_text_unicode", return_value=(True, "ok")) as mock_type, \
             patch.object(apps_mobility, "press_key") as mock_key, \
             patch.object(apps_mobility, "set_clipboard"), \
             patch("time.sleep"):
            res = apps_mobility.order_food(query="hambúrguer", app="ifood")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["data"]["method"], "ui_automator_search")
            # 1º tap: Fechar modal (960, 160); 2º tap: Barra superior (540, 180) — NUNCA (320, 2270); 3º tap: EditText (570, 175)
            self.assertEqual(mock_tap.call_args_list[0].args, (960, 160))
            self.assertEqual(mock_tap.call_args_list[1].args, (540, 180))
            self.assertEqual(mock_tap.call_args_list[2].args, (570, 175))
            mock_type.assert_called_once_with("hambúrguer")
            mock_key.assert_called_once_with(66)


if __name__ == "__main__":
    unittest.main()
