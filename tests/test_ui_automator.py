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

    # ------------------------------------------------------------------
    # Super-app 99 (com.taxis99): XML simulado das 3 telas reais
    # ------------------------------------------------------------------
    @staticmethod
    def _n(text="", desc="", res="", cls="android.widget.TextView", clickable=False, bounds=(0, 0, 0, 0)):
        x1, y1, x2, y2 = bounds
        return {"text": text, "content_desc": desc, "resource_id": res, "class_name": cls, "clickable": clickable,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2, "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2}

    def _99_screens(self):
        n = self._n
        bottom_nav = [
            n("Corrida", "Corrida", "com.taxis99:id/tab_ride", "android.widget.FrameLayout", True, (100, 2140, 332, 2280)),
            n("Food", "Food", "com.taxis99:id/tab_food", "android.widget.FrameLayout", True, (332, 2140, 532, 2280)),
            n("Buscar", "Buscar", "com.taxis99:id/tab_search", "android.widget.FrameLayout", True, (532, 2140, 732, 2280)),
        ]
        ride_home = [
            n("Para onde vamos?", "", "com.taxis99:id/where_to", "android.widget.TextView", True, (60, 820, 1020, 910)),
        ] + bottom_nav
        promo = [
            n("R$99 em cupons só pra você!", bounds=(120, 900, 960, 1000)),
            n("Peça já!", "", "com.taxis99:id/promo_cta", "android.widget.Button", True, (200, 1650, 880, 1760)),
            n("", "Fechar", "com.taxis99:id/promo_close", "android.widget.ImageView", True, (490, 1900, 590, 2000)),
        ]
        food_home = [
            n("açaí", "", "com.taxis99:id/food_search_bar", "android.widget.TextView", True, (40, 300, 1040, 396)),
        ] + bottom_nav
        return ride_home, promo, food_home

    def _99_common_patches(self, dumps):
        import subprocess
        return [
            patch.object(apps_mobility, "SIMULATE_HARDWARE", False),
            patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:32913"),
            patch.object(apps_mobility, "is_screen_unlocked", return_value=(True, "ok")),
            patch.object(apps_mobility, "run_adb_shell", return_value=(True, "")),
            patch.object(apps_mobility, "_exec_android_intent", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Starting: Intent", stderr="")),
            patch.object(apps_mobility, "get_screen_dimensions", return_value=(1080, 2400)),
            patch.object(apps_mobility, "dump_ui_nodes", side_effect=dumps),
            patch.object(apps_mobility, "set_location_state", return_value={"status": "ok"}),
            patch.object(apps_mobility, "set_clipboard"),
            patch("time.sleep"),
        ]

    def test_99food_closes_coupon_modal_and_switches_ride_to_food_tab(self):
        from contextlib import ExitStack
        ride_home, promo, food_home = self._99_screens()
        # 1º dump: aba Corrida + modal de cupons; 2º: modal fechado (Corrida); 3º: aba Food
        dumps = [ride_home + promo, ride_home, food_home]
        with ExitStack() as stack:
            for p in self._99_common_patches(dumps):
                stack.enter_context(p)
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            mock_type = stack.enter_context(patch.object(apps_mobility, "type_text_unicode", return_value=(True, "ok")))
            mock_key = stack.enter_context(patch.object(apps_mobility, "press_key"))
            res = apps_mobility.order_food(query="pizza", app="99food")

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["data"]["method"], "ui_automator_search")
        self.assertEqual(res["data"]["package"], "com.taxis99")
        taps = [c.args for c in mock_tap.call_args_list]
        # X do modal (540, 1950) — NUNCA 'Peça já!' (540, 1705); aba Food (432, 2210); barra de busca (540, 348)
        self.assertEqual(taps, [(540, 1950), (432, 2210), (540, 348)])
        self.assertNotIn((540, 1705), taps)
        mock_type.assert_called_once_with("pizza")
        mock_key.assert_called_once_with(66)

    def test_99_promo_without_close_label_uses_safe_x_coordinate(self):
        _, promo, _ = self._99_screens()
        promo_no_close = [p for p in promo if p["content_desc"] != "Fechar"]
        with patch.object(apps_mobility, "tap_coords") as mock_tap, \
             patch.object(apps_mobility, "dump_ui_nodes", return_value=[]), \
             patch("time.sleep"):
            self.assertEqual(apps_mobility._dismiss_99_promo(promo_no_close, 1080, 2400), [])
            mock_tap.assert_called_once_with(540, 1788)
            # Sem modal: nada é tocado
            mock_tap.reset_mock()
            self.assertIsNone(apps_mobility._dismiss_99_promo([], 1080, 2400))
            mock_tap.assert_not_called()

    def test_99_ride_switches_food_to_ride_tab_and_fills_destination(self):
        from contextlib import ExitStack
        ride_home, _, food_home = self._99_screens()
        suggestions = [
            self._n("shopping tacaruna", "", "com.taxis99:id/dest_input", "android.widget.EditText", True, (120, 260, 1000, 350)),
            self._n("Shopping Tacaruna", "", "com.taxis99:id/addr_title", "android.widget.TextView", True, (60, 560, 1020, 640)),
            self._n("Shopping Recife", "", "com.taxis99:id/addr_title", "android.widget.TextView", True, (60, 700, 1020, 780)),
        ]
        dumps = [food_home, ride_home, suggestions]
        with ExitStack() as stack:
            for p in self._99_common_patches(dumps):
                stack.enter_context(p)
            stack.enter_context(patch.object(apps_mobility, "_load_memory", return_value={}))
            stack.enter_context(patch.object(apps_mobility, "recall_note", return_value={"status": "error"}))
            stack.enter_context(patch.object(apps_mobility, "_geocode_destination", return_value=None))
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            mock_type = stack.enter_context(patch.object(apps_mobility, "type_text_unicode", return_value=(True, "ok")))
            res = apps_mobility.request_ride(destination="shopping tacaruna", app="99")

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["data"]["method"], "ui_automator_destination")
        self.assertTrue(res["data"]["suggestion_selected"])
        taps = [c.args for c in mock_tap.call_args_list]
        # Aba Corrida (216, 2210); campo 'Para onde vamos?' (540, 865); 1ª sugestão correspondente (540, 600)
        self.assertEqual(taps, [(216, 2210), (540, 865), (540, 600)])
        mock_type.assert_called_once_with("shopping tacaruna")

    def test_99_ride_screen_locked_falls_back_without_touching_ui(self):
        import subprocess
        with patch.object(apps_mobility, "SIMULATE_HARDWARE", False), \
             patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:32913"), \
             patch.object(apps_mobility, "is_screen_unlocked", return_value=(False, "Tela bloqueada")), \
             patch.object(apps_mobility, "_exec_android_intent", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Starting: Intent", stderr="")), \
             patch.object(apps_mobility, "_load_memory", return_value={}), \
             patch.object(apps_mobility, "recall_note", return_value={"status": "error"}), \
             patch.object(apps_mobility, "_geocode_destination", return_value=None), \
             patch.object(apps_mobility, "set_clipboard"), \
             patch.object(apps_mobility, "dump_ui_nodes") as mock_dump, \
             patch.object(apps_mobility, "tap_coords") as mock_tap, \
             patch("time.sleep"):
            res = apps_mobility.request_ride(destination="aeroporto", app="99")
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["data"]["method"], "deep_link")
        mock_dump.assert_not_called()
        mock_tap.assert_not_called()

    def test_99_accepts_location_accuracy_dialog_and_enters_manual_location_screen(self):
        """
        Valida:
        1. Pré-ativação silenciosa set_location_state(True) antes de abrir com.taxis99;
        2. Aceite do diálogo 'Precisão de Local' tocando em 'Ativar' (e nunca 'Agora não');
        3. Tela 'Habilitar Serviços de Localização' avançando via 'Inserir localização manualmente'
           e preenchendo o destino no EditText da tela seguinte.
        """
        from contextlib import ExitStack
        accuracy_dialog = [
            self._n("Para uma experiência melhor, o dispositivo precisa usar a Precisão de Local", bounds=(80, 900, 1000, 1100)),
            self._n("Agora não", "", "com.google.android.gms:id/negative_btn", "android.widget.Button", True, (180, 1300, 460, 1400)),
            self._n("Ativar", "", "com.google.android.gms:id/positive_btn", "android.widget.Button", True, (620, 1300, 900, 1400)),
        ]
        location_blocker = [
            self._n("Habilitar Serviços de Localização", bounds=(100, 700, 980, 820)),
            self._n("Ativar nas Configurações", "", "com.taxis99:id/btn_settings", "android.widget.Button", True, (120, 1200, 960, 1320)),
            self._n("Inserir localização manualmente", "", "com.taxis99:id/btn_manual", "android.widget.Button", True, (120, 1360, 960, 1480)),
        ]
        manual_address_screen = [
            self._n("", "Digite seu destino", "com.taxis99:id/dest_input", "android.widget.EditText", True, (120, 260, 1000, 350)),
        ]
        suggestions = [
            self._n("shopping tacaruna", "", "com.taxis99:id/dest_input", "android.widget.EditText", True, (120, 260, 1000, 350)),
            self._n("Shopping Tacaruna", "", "com.taxis99:id/addr_title", "android.widget.TextView", True, (60, 560, 1020, 640)),
        ]

        dumps = [accuracy_dialog, location_blocker, manual_address_screen, suggestions]
        with ExitStack() as stack:
            for p in self._99_common_patches(dumps):
                stack.enter_context(p)
            mock_loc = stack.enter_context(patch.object(apps_mobility, "set_location_state", return_value={"status": "ok"}))
            stack.enter_context(patch.object(apps_mobility, "_load_memory", return_value={}))
            stack.enter_context(patch.object(apps_mobility, "recall_note", return_value={"status": "error"}))
            stack.enter_context(patch.object(apps_mobility, "_geocode_destination", return_value=None))
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            mock_type = stack.enter_context(patch.object(apps_mobility, "type_text_unicode", return_value=(True, "ok")))
            res = apps_mobility.request_ride(destination="shopping tacaruna", app="99")

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["data"]["method"], "ui_automator_destination")
        self.assertTrue(res["data"]["suggestion_selected"])
        self.assertGreaterEqual(mock_loc.call_count, 2)
        mock_loc.assert_called_with(True)

        taps = [c.args for c in mock_tap.call_args_list]
        # 1º: 'Ativar' (760, 1350) — NUNCA 'Agora não' (320, 1350); 2º: 'Inserir localização manualmente' (540, 1420);
        # 3º: EditText (560, 305); 4º: Sugestão 'Shopping Tacaruna' (540, 600)
        self.assertEqual(taps, [(760, 1350), (540, 1420), (560, 305), (540, 600)])
        self.assertNotIn((320, 1350), taps)
        mock_type.assert_called_once_with("shopping tacaruna")

    def test_99food_coupon_60_off_compact_imageview_x_before_search(self):
        """Modal 'CUPONS DE ATÉ 60% OFF' com ImageView sem texto em (50%, 74.5%) é fechado antes da busca."""
        from contextlib import ExitStack
        _, _, food_home = self._99_screens()
        promo_60 = [
            self._n("CUPONS DE ATÉ 60% OFF", bounds=(120, 820, 960, 920)),
            self._n("ENTREGA GRÁTIS", bounds=(200, 980, 880, 1050)),
            self._n("APROVEITE JÁ", "", "com.taxis99:id/cta_btn", "android.widget.Button", True, (180, 1450, 900, 1560)),
            self._n("", "", "", "android.widget.ImageView", True, (495, 1743, 585, 1833)),
        ]
        dumps = [promo_60, food_home]
        with ExitStack() as stack:
            for p in self._99_common_patches(dumps):
                stack.enter_context(p)
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            mock_type = stack.enter_context(patch.object(apps_mobility, "type_text_unicode", return_value=(True, "ok")))
            mock_key = stack.enter_context(patch.object(apps_mobility, "press_key"))
            res = apps_mobility.order_food(query="pizza", app="99food")

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["data"]["method"], "ui_automator_search")
        taps = [c.args for c in mock_tap.call_args_list]
        # 1º: X compacto ImageView (540, 1788) — NUNCA 'APROVEITE JÁ' (540, 1505); 2º: barra de busca (540, 348)
        self.assertEqual(taps, [(540, 1788), (540, 348)])
        self.assertNotIn((540, 1505), taps)
        mock_type.assert_called_once_with("pizza")
        mock_key.assert_called_once_with(66)

    def test_ifood_activates_abertos_agora_filter_after_search(self):
        """Após enviar busca no iFood, toca no chip 'Abertos agora' na faixa y=18%–35%."""
        import subprocess
        home_nodes = [
            self._n("O que vai pedir hoje?", "", "br.com.brainweb.ifood:id/search_bar", "android.widget.TextView", True, (40, 120, 1040, 240)),
        ]
        search_focus_nodes = [
            self._n("", "Buscar em todo o iFood", "br.com.brainweb.ifood:id/input_query", "android.widget.EditText", True, (120, 120, 1020, 230)),
        ]
        results_nodes = [
            self._n("Ordenar", "Ordenar", "br.com.brainweb.ifood:id/chip_sort", "android.widget.TextView", True, (40, 560, 240, 640)),
            self._n("Abertos agora", "Abertos agora", "br.com.brainweb.ifood:id/chip_open_now", "android.widget.TextView", True, (260, 560, 520, 640)),
        ]

        with patch.object(apps_mobility, "SIMULATE_HARDWARE", False), \
             patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:33169"), \
             patch.object(apps_mobility, "is_screen_unlocked", return_value=(True, "ok")), \
             patch.object(apps_mobility, "_exec_android_intent", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Starting: Intent", stderr="")), \
             patch.object(apps_mobility, "get_screen_dimensions", return_value=(1080, 2400)), \
             patch.object(apps_mobility, "dump_ui_nodes", side_effect=[home_nodes, search_focus_nodes, results_nodes]), \
             patch.object(apps_mobility, "tap_coords") as mock_tap, \
             patch.object(apps_mobility, "type_text_unicode", return_value=(True, "ok")) as mock_type, \
             patch.object(apps_mobility, "press_key") as mock_key, \
             patch.object(apps_mobility, "set_clipboard"), \
             patch("time.sleep"):
            res = apps_mobility.order_food(query="pizza", app="ifood")

        self.assertEqual(res["status"], "ok")
        self.assertTrue(res["data"]["open_now_filter"])
        self.assertIn("Abertos agora", res["message"])
        taps = [c.args for c in mock_tap.call_args_list]
        # 1º: barra (540, 180); 2º: EditText (570, 175); 3º: chip 'Abertos agora' (390, 600)
        self.assertEqual(taps, [(540, 180), (570, 175), (390, 600)])
        mock_type.assert_called_once_with("pizza")
        mock_key.assert_called_once_with(66)

    def test_playstore_install_app_direct_search_already_installed_and_locked(self):
        """
        Valida install_app autônomo na Google Play Store:
        1. Rota direta (uber -> market://details?id=com.ubercab) clicando em 'Instalar';
        2. Rota busca autônoma (Duolingo -> market://search?q=Duolingo&c=apps) -> card -> 'Instalar';
        3. App já instalado ('Abrir'/'Desinstalar') e tela bloqueada abortando via is_screen_unlocked().
        """
        import subprocess
        from contextlib import ExitStack

        # 1. Rota direta ('uber')
        details_install = [
            self._n("Uber", "", "com.android.vending:id/title", "android.widget.TextView", False, (260, 220, 700, 300)),
            self._n("Instalar", "Instalar", "com.android.vending:id/install_btn", "android.widget.Button", True, (120, 620, 960, 740)),
        ]
        details_progress = [
            self._n("Cancelar", "Cancelar", "com.android.vending:id/cancel_btn", "android.widget.Button", True, (120, 620, 500, 740)),
        ]
        intent_cmds = []

        def fake_intent(cmd, timeout=6):
            intent_cmds.append(cmd)
            return subprocess.CompletedProcess(args=[cmd], returncode=0, stdout="Starting: Intent", stderr="")

        with ExitStack() as stack:
            stack.enter_context(patch.object(apps_mobility, "APP_PACKAGES", {"uber": "com.ubercab"}))
            stack.enter_context(patch.object(apps_mobility, "SIMULATE_HARDWARE", False))
            stack.enter_context(patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:43073"))
            stack.enter_context(patch.object(apps_mobility, "is_screen_unlocked", return_value=(True, "ok")))
            stack.enter_context(patch.object(apps_mobility, "run_adb_shell", return_value=(True, "")))
            stack.enter_context(patch.object(apps_mobility, "_exec_android_intent", side_effect=fake_intent))
            stack.enter_context(patch.object(apps_mobility, "get_screen_dimensions", return_value=(1080, 2400)))
            stack.enter_context(patch.object(apps_mobility, "dump_ui_nodes", side_effect=[details_install, details_progress]))
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            stack.enter_context(patch("time.sleep"))
            res_direct = apps_mobility.install_app("uber")

        self.assertEqual(res_direct["status"], "ok")
        self.assertEqual(res_direct["data"]["action"], "install_started")
        self.assertTrue(any("market://details?id=com.ubercab" in c for c in intent_cmds))
        mock_tap.assert_called_once_with(540, 680)

        # 2. Rota busca autônoma (Duolingo -> card -> 'Instalar')
        search_results = [
            self._n("Duolingo: idiomas", "", "com.android.vending:id/app_card", "android.widget.LinearLayout", True, (60, 520, 1020, 780)),
        ]
        duolingo_details = [
            self._n("Instalar", "Instalar", "com.android.vending:id/install_btn", "android.widget.Button", True, (120, 620, 960, 740)),
        ]
        intent_cmds.clear()
        with ExitStack() as stack:
            stack.enter_context(patch.object(apps_mobility, "APP_PACKAGES", {"uber": "com.ubercab"}))
            stack.enter_context(patch.object(apps_mobility, "SIMULATE_HARDWARE", False))
            stack.enter_context(patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:43073"))
            stack.enter_context(patch.object(apps_mobility, "is_screen_unlocked", return_value=(True, "ok")))
            stack.enter_context(patch.object(apps_mobility, "run_adb_shell", return_value=(True, "")))
            stack.enter_context(patch.object(apps_mobility, "_exec_android_intent", side_effect=fake_intent))
            stack.enter_context(patch.object(apps_mobility, "get_screen_dimensions", return_value=(1080, 2400)))
            stack.enter_context(patch.object(apps_mobility, "dump_ui_nodes", side_effect=[search_results, duolingo_details, details_progress]))
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            stack.enter_context(patch("time.sleep"))
            res_search = apps_mobility.install_app("Duolingo")

        self.assertEqual(res_search["status"], "ok")
        self.assertEqual(res_search["data"]["action"], "install_started")
        self.assertTrue(any("market://search?q=Duolingo&c=apps" in c for c in intent_cmds))
        self.assertEqual([c.args for c in mock_tap.call_args_list], [(540, 650), (540, 680)])

        # 3. App já instalado ('Abrir'/'Desinstalar')
        already_nodes = [
            self._n("Desinstalar", "Desinstalar", "", "android.widget.Button", True, (120, 620, 500, 740)),
            self._n("Abrir", "Abrir", "", "android.widget.Button", True, (540, 620, 960, 740)),
        ]
        with ExitStack() as stack:
            stack.enter_context(patch.object(apps_mobility, "APP_PACKAGES", {"uber": "com.ubercab"}))
            stack.enter_context(patch.object(apps_mobility, "SIMULATE_HARDWARE", False))
            stack.enter_context(patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:43073"))
            stack.enter_context(patch.object(apps_mobility, "is_screen_unlocked", return_value=(True, "ok")))
            stack.enter_context(patch.object(apps_mobility, "run_adb_shell", return_value=(True, "")))
            stack.enter_context(patch.object(apps_mobility, "_exec_android_intent", side_effect=fake_intent))
            stack.enter_context(patch.object(apps_mobility, "dump_ui_nodes", return_value=already_nodes))
            mock_tap = stack.enter_context(patch.object(apps_mobility, "tap_coords"))
            stack.enter_context(patch("time.sleep"))
            res_installed = apps_mobility.install_app("uber")
        self.assertEqual(res_installed["status"], "ok")
        self.assertEqual(res_installed["data"]["action"], "already_installed")
        mock_tap.assert_not_called()

        # 4. Tela bloqueada aborta via is_screen_unlocked()
        with patch.object(apps_mobility, "SIMULATE_HARDWARE", False), \
             patch.object(apps_mobility, "ensure_adb_connected", return_value="192.168.0.106:43073"), \
             patch.object(apps_mobility, "is_screen_unlocked", return_value=(False, "Tela bloqueada")), \
             patch.object(apps_mobility, "tap_coords") as mock_tap_locked:
            res_locked = apps_mobility.install_app("uber")
        self.assertEqual(res_locked["status"], "error")
        self.assertTrue(res_locked["data"]["screen_locked"])
        mock_tap_locked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
