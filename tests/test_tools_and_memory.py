"""
Testes de Ferramentas, Memória SQLite FTS5, Migração e Calculadora Científica.
"""

import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

import android_agent.tools as tools
import android_agent.tools.core as tools_core
import android_agent.tools.memory_schedule as tools_mem
import android_agent.tools.hardware as tools_hw
import android_agent.tools.media as tools_media
import android_agent.tools.comms as tools_comms
import android_agent.tools.apps_mobility as tools_apps
import android_agent.tools.weather_web as tools_weather


class TestToolsAndMemory(unittest.TestCase):
    """Testes isolados de SQLite FTS5, migração JSON, calculadora AST e hardware."""

    def setUp(self):
        # Cria diretório temporário para isolar data e captures
        self.tmp_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.tmp_dir)

        # Salva caminhos originais
        self.orig_data_dir = tools_core.DATA_DIR
        self.orig_mem_data_dir = tools_mem.DATA_DIR
        self.orig_hw_data_dir = tools_hw.DATA_DIR
        self.orig_sim_hw = tools_core.SIMULATE_HARDWARE

        # Redireciona para o diretório temporário isolado
        tools_core.DATA_DIR = self.tmp_path
        tools_mem.DATA_DIR = self.tmp_path
        tools_hw.DATA_DIR = self.tmp_path
        for mod in (tools_core, tools_hw, tools_media, tools_comms, tools_weather, tools_apps, tools_mem):
            if hasattr(mod, "SIMULATE_HARDWARE"):
                mod.SIMULATE_HARDWARE = True

    def tearDown(self):
        # Restaura caminhos originais
        tools_core.DATA_DIR = self.orig_data_dir
        tools_mem.DATA_DIR = self.orig_mem_data_dir
        tools_hw.DATA_DIR = self.orig_hw_data_dir
        tools_core.SIMULATE_HARDWARE = self.orig_sim_hw
        tools_hw.SIMULATE_HARDWARE = self.orig_sim_hw
        tools_weather.SIMULATE_HARDWARE = self.orig_sim_hw

        # Limpa diretório temporário
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_sqlite_fts5_crud_and_like_fallback(self):
        """Testa inserção, categorização automática, busca FTS5 BM25 e fallback LIKE."""
        # 1. Inserção com categorização automática
        res1 = tools.remember_note("minha_senha_wifi", "SuperSenha2026")
        self.assertEqual(res1["status"], "ok")
        self.assertIn("minha_senha_wifi", res1["message"])

        # 2. Busca FTS5 direta
        recall_fts = tools.recall_note("wifi")
        self.assertEqual(recall_fts["status"], "ok")
        self.assertIn("SuperSenha2026", recall_fts["message"])

        # 3. Busca parcial via fallback LIKE
        recall_like = tools.recall_note("senha")
        self.assertEqual(recall_like["status"], "ok")
        self.assertIn("SuperSenha2026", recall_like["message"])

        # 4. Busca inexistente
        recall_none = tools.recall_note("termo_totalmente_inexistente")
        self.assertEqual(recall_none["status"], "ok")
        self.assertIn("Nenhuma anotação", recall_none["message"])

    def test_automatic_migration_from_json(self):
        """Testa migração transparente de memory.json legado para memory.db e renomeação para .migrated."""
        legacy_file = self.tmp_path / "memory.json"
        legacy_data = {
            "anotacao_legada": {
                "value": "ConteudoImportanteDoPassado",
                "timestamp": "2026-01-01 10:00:00"
            }
        }
        with open(legacy_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        # Força inicialização/migração do banco no diretório temporário
        tools_mem._migrate_json_to_sqlite()

        # Verifica se o arquivo legado foi renomeado para .migrated
        migrated_file = self.tmp_path / "memory.json.migrated"
        self.assertTrue(migrated_file.is_file(), "memory.json.migrated deve existir após migração")
        self.assertFalse(legacy_file.is_file(), "memory.json original deve ter sido renomeado")

        # Verifica se os dados migrados podem ser buscados no SQLite FTS5
        res = tools.recall_note("anotacao_legada")
        self.assertEqual(res["status"], "ok")
        self.assertIn("ConteudoImportanteDoPassado", res["message"])

    def test_scientific_calculator_ast(self):
        """Testa SafeMathEvaluator para cálculos científicos, constantes e restrições de segurança."""
        # 1. Raiz quadrada
        res_sqrt = tools.calculate("sqrt(144)")
        self.assertEqual(res_sqrt["status"], "ok")
        self.assertIn("12", res_sqrt["message"])

        # 2. Raiz cúbica
        res_cbrt = tools.calculate("cbrt(27)")
        self.assertEqual(res_cbrt["status"], "ok")
        self.assertIn("3", res_cbrt["message"])

        # 3. Fatorial
        res_fact = tools.calculate("factorial(5)")
        self.assertEqual(res_fact["status"], "ok")
        self.assertIn("120", res_fact["message"])

        # 4. Trigonometria e constante pi
        res_sin = tools.calculate("sin(90 * pi / 180)")
        self.assertEqual(res_sin["status"], "ok")
        self.assertIn("1", res_sin["message"])

        # 5. Segurança: Bloqueio de booleanos
        res_bool = tools.calculate("True + 1")
        self.assertEqual(res_bool["status"], "error")
        self.assertIn("booleanos não são permitidos", res_bool["message"])

        # 6. Segurança: Bloqueio de expoente excessivo (> 1000)
        res_exp = tools.calculate("2 ** 1005")
        self.assertEqual(res_exp["status"], "error")
        self.assertIn("muito grande", res_exp["message"])

    def test_scan_wifi_structure(self):
        """Testa ferramenta scan_wifi retornando redes em formato estruturado."""
        res = tools.scan_wifi()
        self.assertEqual(res["status"], "ok")
        self.assertIn("redes wi-fi", res["message"].lower())
        self.assertIn("networks", res.get("data", {}))
        networks = res["data"]["networks"]
        self.assertGreaterEqual(len(networks), 1)
        first_net = networks[0]
        self.assertIn("ssid", first_net)
        self.assertIn("rssi", first_net)
        self.assertIn("security", first_net)

    def test_get_weather_structure(self):
        """Testa get_weather estruturado e calibração de precipitação."""
        res = tools.get_weather(day="hoje", location="Paulista, Pernambuco")
        self.assertEqual(res["status"], "ok")
        self.assertIn("Paulista", res["message"])
        self.assertIn("data", res)
        self.assertIn("city", res["data"])

    def test_weather_three_level_fallback_chain(self):
        """Testa a cadeia de fallback em 3 níveis de clima e temperatura por localização."""
        import android_agent.tools.weather_web as weather_mod
        orig_mock = weather_mod._MOCK_LOCATION_ACTIVE

        try:
            # ------------------------------------------------------------------
            # CENÁRIO 1: GPS Ativo -> Salva last_location.json e retorna temperatura
            # ------------------------------------------------------------------
            weather_mod.LAST_LOCATION_FILE.unlink(missing_ok=True)
            weather_mod._MOCK_LOCATION_ACTIVE = (-7.9408, -34.8731, "gps")

            res_gps = tools.get_weather(day="hoje", time="", location="")
            self.assertEqual(res_gps["status"], "ok")
            self.assertTrue(weather_mod.LAST_LOCATION_FILE.is_file(), "Deve ter salvo last_location.json")

            cached_data = tools.load_last_location()
            self.assertIsNotNone(cached_data)
            self.assertAlmostEqual(cached_data["latitude"], -7.9408, places=3)
            self.assertAlmostEqual(cached_data["longitude"], -34.8731, places=3)
            self.assertIn("label", cached_data)
            self.assertIn("updated_at", cached_data)
            self.assertIn("°C", res_gps["message"])

            # ------------------------------------------------------------------
            # CENÁRIO 2: GPS Desligado + Cache Existente -> Informa última posição
            # ------------------------------------------------------------------
            weather_mod._MOCK_LOCATION_ACTIVE = False
            tools.save_last_location(
                -7.9408, -34.8731,
                label="Centro, Paulista - PE",
                updated_at="2026-11-24 10:55"
            )

            res_cache = tools.get_weather(day="hoje", time="", location="")
            self.assertEqual(res_cache["status"], "ok")
            expected_notice = "Localização atual desativada — usando última localização registrada (Centro, Paulista - PE em 2026-11-24 10:55): "
            self.assertIn(expected_notice, res_cache["message"])
            self.assertEqual(res_cache["data"].get("fallback_used"), "last_location")

            # ------------------------------------------------------------------
            # CENÁRIO 3: GPS Desligado + Sem Cache -> Retorna orientação para ligar GPS
            # ------------------------------------------------------------------
            weather_mod._MOCK_LOCATION_ACTIVE = False
            weather_mod.LAST_LOCATION_FILE.unlink(missing_ok=True)

            res_none = tools.get_weather(day="hoje", time="", location="")
            self.assertEqual(res_none["status"], "ok")
            expected_guidance = (
                "Não foi possível consultar a temperatura porque a localização do aparelho "
                "está desligada e ainda não há nenhuma localização anterior registrada. "
                "Por favor, ligue a localização (GPS) e tente novamente."
            )
            self.assertIn(expected_guidance, res_none["message"])
            self.assertEqual(res_none["data"].get("error"), "location_unavailable")

        finally:
            weather_mod._MOCK_LOCATION_ACTIVE = orig_mock

    def test_wifi_tools_simulation(self):
        """Testa connect_wifi, get_wifi_info e set_wifi_state em modo simulado."""
        # 1. connect_wifi
        r_conn = tools.connect_wifi(ssid="MinhaRede_5G", password="SenhaSegura123")
        self.assertEqual(r_conn["status"], "ok")
        self.assertEqual(r_conn["data"]["ssid"], "MinhaRede_5G")
        self.assertTrue(r_conn["data"]["protected"])

        r_empty = tools.connect_wifi(ssid="")
        self.assertEqual(r_empty["status"], "error")

        # 2. get_wifi_info
        r_info = tools.get_wifi_info()
        self.assertEqual(r_info["status"], "ok")
        self.assertIn("Silva_5G", r_info["message"])
        self.assertEqual(r_info["data"]["ssid"], "Silva_5G")
        self.assertEqual(r_info["data"]["ip"], "192.168.1.105")

        # 3. set_wifi_state
        r_on = tools.set_wifi_state(state=True)
        self.assertEqual(r_on["status"], "ok")
        self.assertTrue(r_on["data"]["state"])

        r_off = tools.set_wifi_state(state=False)
        self.assertEqual(r_off["status"], "ok")
        self.assertFalse(r_off["data"]["state"])

    def test_get_clipboard_feedback(self):
        """Testa feedback detalhado de get_clipboard quando vazio/bloqueado e quando preenchido."""
        # 1. Com conteúdo
        with patch.object(tools_comms, "SIMULATE_HARDWARE", False):
            with patch.object(tools_comms, "_run_termux_cmd") as mock_cmd:
                mock_cmd.return_value = MagicMock(returncode=0, stdout="texto copiado de teste", stderr="")
                res_filled = tools_comms.get_clipboard()
                self.assertEqual(res_filled["status"], "ok")
                self.assertIn("texto copiado de teste", res_filled["message"])
                self.assertEqual(res_filled["data"]["clipboard"], "texto copiado de teste")

        # 2. Vazio ou bloqueado pelo Android 10+
        with patch.object(tools_comms, "SIMULATE_HARDWARE", False):
            with patch.object(tools_comms, "_run_termux_cmd") as mock_cmd:
                mock_cmd.return_value = MagicMock(returncode=0, stdout="", stderr="")
                res_empty = tools_comms.get_clipboard()
                self.assertEqual(res_empty["status"], "ok")
                self.assertIn("Área de transferência vazia (ou bloqueada em segundo plano pelo Android — libere READ_CLIPBOARD via ADB para o Termux:API).", res_empty["message"])
                self.assertEqual(res_empty["data"]["clipboard"], "")

    def test_all_63_tools_smoke_execution(self):
        """Testa a execução smoke de todas as 63 ferramentas do catálogo em modo simulado."""
        self.assertEqual(len(tools.AVAILABLE_TOOLS), 63, "O catálogo formal deve conter exatamente 63 ferramentas.")

        sample_args = {
            "add_list_item": {"item": "café", "list_name": "compras"},
            "calculate": {"expression": "2 + 2"},
            "cancel_alarm": {"time": "07:00"},
            "check_voice_note": {"query": "aluguel"},
            "connect_wifi": {"ssid": "TesteNet", "password": "123"},
            "convert_units": {"amount": 10.0, "from_unit": "km", "to_unit": "mi"},
            "forget_note": {"query": "teste"},
            "get_battery": {},
            "get_clipboard": {},
            "get_contact": {"name": "Teste"},
            "get_datetime": {},
            "get_last_location": {},
            "get_last_sms": {"limit": 3},
            "get_list": {"list_name": "compras"},
            "get_location": {},
            "get_notifications": {"app": "whatsapp"},
            "get_system_info": {},
            "get_weather": {"day": "hoje", "location": "Recife"},
            "get_wifi_info": {},
            "install_app": {"app_name": "spotify"},
            "list_capabilities": {},
            "list_memories": {"category": ""},
            "make_call": {"number": "11999999999"},
            "media_control": {"action": "play"},
            "navigate_to": {"destination": "Shopping Recife", "app": "maps"},
            "none": {},
            "open_app": {"app_name": "YouTube"},
            "order_food": {"query": "pizza"},
            "play_media": {"query": "Linkin Park", "app": "spotify"},
            "read_screen": {},
            "recall_note": {"query": "teste"},
            "record_audio": {"duration": 5},
            "record_video": {"duration": 5, "camera_id": 0},
            "remember_note": {"key": "teste", "value": "123"},
            "remind_on_wifi": {"ssid": "CASA_5G", "reminder": "pagar boleto"},
            "remove_list_item": {"item": "café", "list_name": "compras"},
            "request_ride": {"destination": "Shopping"},
            "save_contact": {"name": "Teste", "phone": "11999998888"},
            "save_voice_note": {"title": "lembrete smoke", "duration": 5, "text_only": True},
            "scan_wifi": {},
            "schedule_event": {"title": "Reuniao", "date": "amanha", "time": "14:00"},
            "search_google": {"query": "Python", "open_browser": False},
            "send_sms": {"number": "11999999999", "message": "ola"},
            "send_whatsapp": {"contact_name": "11999999999", "message": "oi"},
            "set_airplane_mode": {"state": False},
            "set_alarm": {"time": "07:00", "label": "Acordar"},
            "set_bluetooth_state": {"state": True},
            "set_brightness": {"level": 50},
            "set_clipboard": {"text": "conteudo de teste"},
            "set_dnd": {"state": True},
            "set_hotspot_state": {"state": False},
            "set_location_state": {"state": True},
            "set_mobile_data_state": {"state": True},
            "set_timer": {"minutes": 10},
            "set_torch": {"state": True},
            "set_volume": {"stream": "music", "level": 50},
            "set_wifi_state": {"state": True},
            "summarize_notifications": {"app_filter": ""},
            "take_photo": {"camera_id": 0},
            "take_screenshot": {},
            "tell_joke": {},
            "vibrate": {"duration_ms": 500},
        }

        with patch("android_agent.tools.apps_mobility.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.apps_mobility.dump_ui_nodes", return_value=[{"text": "Tela OK", "content_desc": ""}]):
            for tool_name, fn in tools.AVAILABLE_TOOLS.items():
                args = sample_args.get(tool_name, {})
                with self.subTest(tool=tool_name):
                    try:
                        res = fn(**args)
                    except Exception as err:
                        self.fail(f"Ferramenta '{tool_name}' lançou exceção inesperada: {type(err).__name__}: {err}")

                    self.assertIsInstance(res, dict, f"Ferramenta '{tool_name}' deve retornar um dict.")
                    self.assertIn("status", res, f"Ferramenta '{tool_name}' deve retornar campo 'status'.")
                    self.assertEqual(res["status"], "ok", f"Ferramenta '{tool_name}' falhou: {res.get('message')}")

    def test_datetime_system_info_and_read_screen_with_nlp(self):
        """Testa get_datetime, get_system_info, read_screen (ADB online/offline) e roteamento NLP."""
        from android_agent.intent_fallback import match_intent_fallback

        # 1. get_datetime
        dt_res = tools.get_datetime()
        self.assertEqual(dt_res["status"], "ok")
        self.assertIn("Hoje é", dt_res["message"])
        self.assertIn(dt_res["data"]["period"], ("madrugada", "manhã", "tarde", "noite"))
        self.assertEqual(match_intent_fallback("que horas são?"), "<call>get_datetime()</call>")
        self.assertEqual(match_intent_fallback("qual a data de hoje?"), "<call>get_datetime()</call>")
        self.assertEqual(match_intent_fallback("que dia da semana é hoje?"), "<call>get_datetime()</call>")

        # 2. get_system_info
        sys_res = tools.get_system_info()
        self.assertEqual(sys_res["status"], "ok")
        self.assertGreater(sys_res["data"]["storage_total_gb"], 0)
        self.assertIn("Armazenamento:", sys_res["message"])
        self.assertIn("RAM:", sys_res["message"])
        self.assertEqual(match_intent_fallback("quanto tenho de espaço livre?"), "<call>get_system_info()</call>")
        self.assertEqual(match_intent_fallback("como está a memória ram?"), "<call>get_system_info()</call>")
        self.assertEqual(match_intent_fallback("qual minha operadora?"), "<call>get_system_info()</call>")

        # 3. read_screen (ADB offline -> fallback amigável)
        with patch("android_agent.tools.apps_mobility.ensure_adb_connected", return_value=None):
            off_res = tools.read_screen()
            self.assertEqual(off_res["status"], "error")
            self.assertIn("ADB local está offline", off_res["message"])

        # 4. read_screen (ADB online -> XML mockado filtrando duplicatas/ruído)
        mock_nodes = [
            {"text": "WhatsApp", "content_desc": ""},
            {"text": "WhatsApp", "content_desc": ""},
            {"text": "com.whatsapp:id/toolbar_title", "content_desc": ""},
            {"text": "Olá, tudo bem?", "content_desc": ""},
            {"text": "", "content_desc": "Enviar"},
        ]
        with patch("android_agent.tools.apps_mobility.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.apps_mobility.dump_ui_nodes", return_value=mock_nodes):
            on_res = tools.read_screen()
            self.assertEqual(on_res["status"], "ok")
            self.assertIn("WhatsApp", on_res["message"])
            self.assertIn("Olá, tudo bem?", on_res["message"])
            self.assertNotIn("com.whatsapp:id/toolbar_title", on_res["message"])

        self.assertEqual(match_intent_fallback("o que está escrito na minha tela?"), "<call>read_screen()</call>")
        self.assertEqual(match_intent_fallback("lê a tela"), "<call>read_screen()</call>")
        piped_screen = match_intent_fallback("Leia a tela e anote")
        self.assertIn("<call>read_screen()</call>", piped_screen)
        self.assertIn("remember_note(", piped_screen)
        self.assertIn("$prev_result", piped_screen)

    def test_record_audio_and_convert_units_with_parser_and_nlp(self):
        """Testa record_audio (limites, mock Termux, media_items), convert_units (físico, moeda online/offline), coerção float no parser e NLP."""
        import io
        import subprocess
        from android_agent.intent_fallback import match_intent_fallback
        from android_agent.parser import parse_function_calls, execute_call

        # 1. record_audio limites e execução real mockada
        with tempfile.TemporaryDirectory() as tmpdir:
            cap_dir = Path(tmpdir)
            rec_cmds = []

            def fake_record(cmd, timeout=15):
                rec_cmds.append(cmd)
                if "-f" in cmd:
                    f_path = Path(cmd[cmd.index("-f") + 1])
                    f_path.write_bytes(b"FAKE_AAC_AUDIO_BYTES")
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with patch("android_agent.tools.media.CAPTURES_DIR", cap_dir), \
                 patch("android_agent.tools.media.SIMULATE_HARDWARE", False), \
                 patch("android_agent.tools.media.time.sleep", return_value=None), \
                 patch("android_agent.tools.media._run_termux_cmd", side_effect=fake_record):
                aud_res = tools.record_audio(duration=999)  # deve limitar a 120s
                self.assertEqual(aud_res["status"], "ok")
                self.assertEqual(aud_res["data"]["duration"], 120)
                self.assertTrue(aud_res["audio_url"].startswith("/captures/audio_"))
                self.assertEqual(aud_res["media_items"], [{"type": "audio", "url": aud_res["audio_url"]}])
                self.assertTrue(any("-l" in c and "120" in c for c in rec_cmds))
                self.assertEqual(rec_cmds[-1], ["termux-microphone-record", "-q"])

            # execute_call propaga audio_url e media_items
            with patch("android_agent.tools.media.CAPTURES_DIR", cap_dir):
                exec_aud = execute_call("<call>record_audio(duration=5)</call>")
                self.assertEqual(exec_aud["status"], "ok")
                self.assertTrue(exec_aud["audio_url"].startswith("/captures/audio_"))
                self.assertEqual(exec_aud["media_items"][0]["type"], "audio")

        # 2. convert_units medidas físicas e erro de categorias incompatíveis
        self.assertIn("6.2137 mi", tools.convert_units(10, "km", "milhas")["message"])
        self.assertIn("89.6 °F", tools.convert_units(32, "celsius", "fahrenheit")["message"])
        self.assertIn("kg", tools.convert_units(5, "libras", "quilos")["message"])
        incompat = tools.convert_units(10, "kg", "km")
        self.assertEqual(incompat["status"], "error")

        # 3. convert_units moeda online (HTTP mock) e offline (fallback)
        class _FakeResp(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        with patch("android_agent.tools.memory_schedule.urllib.request.urlopen", return_value=_FakeResp(b'{"USDBRL":{"bid":"5.50"}}')):
            cur_on = tools.convert_units(50, "dólares", "reais")
            self.assertEqual(cur_on["status"], "ok")
            self.assertTrue(cur_on["data"]["online"])
            self.assertIn("275.00 BRL", cur_on["message"])

        with patch("android_agent.tools.memory_schedule.urllib.request.urlopen", side_effect=OSError("offline")):
            cur_off = tools.convert_units(100, "euros", "reais")
            self.assertEqual(cur_off["status"], "ok")
            self.assertFalse(cur_off["data"]["online"])
            self.assertIn("cotação offline estimada", cur_off["message"])

        # 4. Coerção int -> float no parser AST
        parsed = parse_function_calls("<call>convert_units(amount=50, from_unit='usd', to_unit='brl')</call>")
        self.assertEqual(parsed[0][0], "convert_units")
        self.assertIsInstance(parsed[0][1]["amount"], float)
        self.assertEqual(parsed[0][1]["amount"], 50.0)

        # 5. Roteamento NLP
        self.assertEqual(match_intent_fallback("grava um áudio de 15 segundos"), "<call>record_audio(duration=15)</call>")
        self.assertEqual(match_intent_fallback("gravar som por 1 minuto"), "<call>record_audio(duration=60)</call>")
        self.assertIn("convert_units(", match_intent_fallback("converter 50 dólares para reais"))
        self.assertIn("convert_units(", match_intent_fallback("quantos reais são 100 euros?"))
        self.assertIn("convert_units(", match_intent_fallback("32 graus celsius em fahrenheit"))

    def test_navigate_to_and_play_media_with_fallbacks_and_nlp_disambiguation(self):
        """Testa navigate_to (Maps, Waze, geo fallback), play_media (Spotify, YouTube, padrão) e desambiguação NLP."""
        from android_agent.intent_fallback import match_intent_fallback

        # 1. navigate_to: Maps -> fallback geo:0,0?q=...
        dispatched_nav = []

        def fake_nav_adb(args, timeout=6.0):
            dispatched_nav.append(args)
            if "google.navigation:" in " ".join(args):
                return False, "Error: Activity not found"
            return True, "Starting: Intent"

        with patch("android_agent.tools.apps_mobility.SIMULATE_HARDWARE", False), \
             patch("android_agent.tools.apps_mobility.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.apps_mobility.run_adb_shell", side_effect=fake_nav_adb):
            nav_maps = tools.navigate_to("Shopping Recife", app="maps")
            self.assertEqual(nav_maps["status"], "ok")
            self.assertIn("Google Maps", nav_maps["message"])
            self.assertTrue(any("geo:0,0?q=Shopping%20Recife" in " ".join(c) for c in dispatched_nav))

            nav_waze = tools.navigate_to("Aeroporto", app="waze")
            self.assertEqual(nav_waze["status"], "ok")
            self.assertIn("Waze", nav_waze["message"])
            self.assertTrue(any("waze.com/ul?q=Aeroporto" in " ".join(c) for c in dispatched_nav))

        # 2. play_media: Spotify fallback -> spotify:search, YouTube, e player padrão
        dispatched_media = []

        def fake_media_adb(args, timeout=6.0):
            dispatched_media.append(args)
            if "MEDIA_PLAY_FROM_SEARCH" in " ".join(args) and "com.spotify.music" in " ".join(args):
                return False, "Error: rejected"
            return True, "Starting: Intent"

        with patch("android_agent.tools.media.SIMULATE_HARDWARE", False), \
             patch("android_agent.tools.media.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.media.run_adb_shell", side_effect=fake_media_adb):
            sp_res = tools.play_media("Linkin Park", app="spotify")
            self.assertEqual(sp_res["status"], "ok")
            self.assertIn("Spotify", sp_res["message"])
            self.assertTrue(any("spotify:search:Linkin%20Park" in " ".join(c) for c in dispatched_media))

            yt_res = tools.play_media("lo-fi", app="youtube")
            self.assertEqual(yt_res["status"], "ok")
            self.assertIn("YouTube", yt_res["message"])

            def_res = tools.play_media("Bohemian Rhapsody", app="")
            self.assertEqual(def_res["status"], "ok")
            self.assertIn("Player padrão", def_res["message"])

        # 3. Roteamento NLP e desambiguação contra request_ride e media_control
        self.assertEqual(match_intent_fallback("me leva até o Shopping Recife"), "<call>navigate_to(destination='Shopping Recife', app='maps')</call>")
        self.assertEqual(match_intent_fallback("abrir navegação para o aeroporto no Waze"), "<call>navigate_to(destination='aeroporto', app='waze')</call>")
        self.assertIn("request_ride(", match_intent_fallback("pede um Uber para o Shopping Recife"))

        self.assertEqual(match_intent_fallback("toca Linkin Park no Spotify"), "<call>play_media(query='Linkin Park', app='spotify')</call>")
        self.assertEqual(match_intent_fallback("coloca uma música de lo-fi no YouTube"), "<call>play_media(query='lo-fi', app='youtube')</call>")
        self.assertEqual(match_intent_fallback("tocar Bohemian Rhapsody"), "<call>play_media(query='Bohemian Rhapsody', app='')</call>")
        self.assertEqual(match_intent_fallback("pausa a música"), "<call>media_control(action='pause')</call>")

    def test_dynamic_lists_crud_and_nlp(self):
        """Testa add_list_item, get_list, remove_list_item (SQLite, deduplicação, limpeza total) e NLP."""
        from android_agent.intent_fallback import match_intent_fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            import tools.memory_schedule as top_mem_sched
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data), \
                 patch.object(top_mem_sched, "DATA_DIR", tmp_data):
                # 1. Inserção múltipla e sinônimo 'mercado' -> 'compras'
                r_add = tools.add_list_item("leite, café e pão", list_name="mercado")
                self.assertEqual(r_add["status"], "ok")
                self.assertEqual(r_add["data"]["list_name"], "compras")
                self.assertEqual(r_add["data"]["added"], ["leite", "café", "pão"])

                # 2. Deduplicação case-insensitive
                r_dup = tools.add_list_item("LEITE", list_name="compras")
                self.assertEqual(r_dup["data"]["added"], [])
                self.assertEqual(r_dup["data"]["already_present"], ["LEITE"])

                # 3. Segunda lista ('afazeres' -> 'tarefas')
                tools.add_list_item("pagar luz", list_name="afazeres")

                # 4. Consulta por lista e geral ('todas')
                g_compras = tools.get_list("compras")
                self.assertEqual(len(g_compras["data"]["items"]), 3)
                self.assertIn("café", g_compras["message"])

                g_all = tools.get_list("todas")
                self.assertIn("compras", g_all["data"]["lists"])
                self.assertIn("tarefas", g_all["data"]["lists"])

                # 5. Remoção unitária e limpeza total
                rem_one = tools.remove_list_item("café", list_name="compras")
                self.assertEqual(rem_one["data"]["removed"], ["café"])
                self.assertEqual(len(tools.get_list("compras")["data"]["items"]), 2)

                rem_all = tools.remove_list_item("tudo", list_name="compras")
                self.assertTrue(rem_all["data"]["cleared"])
                self.assertEqual(tools.get_list("compras")["data"]["items"], [])

        # 6. Roteamento NLP
        self.assertEqual(match_intent_fallback("coloca leite e café na lista de compras"), "<call>add_list_item(item='leite e café', list_name='compras')</call>")
        self.assertEqual(match_intent_fallback("adiciona arroz no mercado"), "<call>add_list_item(item='arroz', list_name='mercado')</call>")
        self.assertEqual(match_intent_fallback("o que tem na minha lista de compras?"), "<call>get_list(list_name='compras')</call>")
        self.assertEqual(match_intent_fallback("o que falta comprar?"), "<call>get_list(list_name='compras')</call>")
        self.assertEqual(match_intent_fallback("quais são minhas listas?"), "<call>get_list(list_name='todas')</call>")
        self.assertEqual(match_intent_fallback("tira o leite da lista"), "<call>remove_list_item(item='leite', list_name='compras')</call>")
        self.assertEqual(match_intent_fallback("limpa a lista do mercado"), "<call>remove_list_item(item='tudo', list_name='mercado')</call>")

    def test_memory_v2_free_capture_ttl_upsert_clipboard_forget_and_list(self):
        """Testa Memória 2.0: captura livre, upsert sem duplicatas, TTL, timestamp relativo, auto-clipboard, forget_note, list_memories e NLP."""
        from android_agent.intent_fallback import match_intent_fallback
        from android_agent.tools import memory_schedule

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            import tools.memory_schedule as top_mem_sched
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data), \
                 patch.object(top_mem_sched, "DATA_DIR", tmp_data):
                # 1. Captura livre em uma frase + Upsert sem duplicatas
                r1 = tools.remember_note("estacionei o carro no G2 vaga 42")
                self.assertEqual(r1["status"], "ok")
                self.assertEqual(r1["data"]["key"], "vaga do carro")

                r2 = tools.remember_note("vaga carro", "G3 vaga 10")
                self.assertEqual(r2["status"], "ok")
                listed = tools.list_memories()
                self.assertEqual(listed["data"]["total"], 1)  # upsert substituiu sem duplicar

                # 2. Auto-clipboard em senha/PIX + timestamp relativo
                tools.remember_note("chave pix", "12345678900")
                with patch("android_agent.tools.comms.set_clipboard", return_value={"status": "ok"}) as mock_clip:
                    rec_pix = tools.recall_note("pix")
                    self.assertEqual(rec_pix["data"]["clipboard_text"], "12345678900")
                    self.assertIn("Copiado automaticamente", rec_pix["message"])
                    self.assertIn("salvo ", rec_pix["message"])
                    mock_clip.assert_called_once_with("12345678900")

                # 3. TTL expirado é purgado automaticamente
                tools.remember_note("codigo temporario", "9911", ttl_hours=1)
                conn = memory_schedule._get_memory_db()
                with conn:
                    conn.execute("UPDATE memories SET expires_at = '2020-01-01 00:00:00' WHERE key = 'codigo temporario'")
                conn.close()
                rec_exp = tools.recall_note("codigo temporario")
                self.assertFalse(rec_exp["data"]["found"])

                # 4. list_memories e forget_note
                all_mem = tools.list_memories()
                self.assertEqual(all_mem["data"]["total"], 2)
                f_res = tools.forget_note("chave pix")
                self.assertEqual(f_res["data"]["deleted"], "chave pix")
                self.assertEqual(tools.list_memories()["data"]["total"], 1)

        # 5. Roteamento NLP Memória 2.0
        self.assertIn("remember_note(", match_intent_fallback("anota que parei no G2 vaga 42"))
        self.assertIn("ttl_hours=12", match_intent_fallback("lembra disso só por hoje: senha temporária 9911"))
        self.assertEqual(match_intent_fallback("esquece onde eu estacionei"), "<call>forget_note(query='onde eu estacionei')</call>")
        self.assertEqual(match_intent_fallback("apaga a anotação do portão"), "<call>forget_note(query='portão')</call>")
        self.assertEqual(match_intent_fallback("o que você tem anotado?"), "<call>list_memories(category='')</call>")
        self.assertEqual(match_intent_fallback("mostra minhas anotações de senha"), "<call>list_memories(category='senha')</call>")

    def test_open_app_resilience_and_fuzzy(self):
        """Testa remoção de ruídos (hoje, o, agora, app) e fuzzy matching em open_app."""
        # 1. Ruído de tempo/fala: 'hoje youtube'
        r1 = tools.open_app("hoje youtube")
        self.assertEqual(r1["status"], "ok")
        self.assertEqual(r1["data"]["package"], "com.google.android.youtube")

        # 2. Artigo definido: 'o youtube'
        r2 = tools.open_app("o youtube")
        self.assertEqual(r2["status"], "ok")
        self.assertEqual(r2["data"]["package"], "com.google.android.youtube")

        # 3. Sufixo temporal: 'youtube agora'
        r3 = tools.open_app("youtube agora")
        self.assertEqual(r3["status"], "ok")
        self.assertEqual(r3["data"]["package"], "com.google.android.youtube")

        # 4. Prefixo e sufixo de cortesia: 'app whatsapp por favor'
        r4 = tools.open_app("app whatsapp por favor")
        self.assertEqual(r4["status"], "ok")
        self.assertEqual(r4["data"]["package"], "com.whatsapp")

        # 5. Fuzzy match para digitação/fonética próxima: 'iutube'
        r5 = tools.open_app("iutube")
        self.assertEqual(r5["status"], "ok")
        self.assertEqual(r5["data"]["package"], "com.google.android.youtube")

    def test_make_call_contact_resolution_and_fallback(self):
        """Testa resolução de contato na agenda, discagem direta e fallback para ACTION_DIAL."""
        import subprocess

        # Reseta cache de contatos
        tools_comms._CONTACTS_CACHE["timestamp"] = 0.0
        tools_comms._CONTACTS_CACHE["contacts"] = []

        fake_contacts = [
            {"name": "Carlos Silva", "number": "+5511988887777"},
            {"name": "Dra. Mariana", "number": "11977776666"}
        ]

        def fake_run_termux(cmd, timeout=10):
            if cmd == ["termux-contact-list"]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(fake_contacts), stderr="")
            if cmd[0] == "termux-telephony-call":
                if cmd[1] == "+5511988887777":
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                # Simula falha de permissão no segundo caso
                return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="SecurityException: Permission Denial")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

        def fake_exec_intent(cmd_str, timeout=6):
            return subprocess.CompletedProcess(args=[cmd_str], returncode=0, stdout="Intent started", stderr="")

        with patch.object(tools_comms, "SIMULATE_HARDWARE", False), \
             patch.object(tools_comms, "_run_termux_cmd", side_effect=fake_run_termux), \
             patch.object(tools_comms, "_exec_android_intent", side_effect=fake_exec_intent):

            # 1. Resolução com sucesso e chamada direta (Camada 1)
            r1 = tools_comms.make_call(target="Carlos")
            self.assertEqual(r1["status"], "ok")
            self.assertEqual(r1["data"]["method"], "telephony_call")
            self.assertIn("+5511988887777", r1["message"])
            self.assertIn("Iniciando chamada direta", r1["message"])

            # 2. Resolução com sucesso e fallback ACTION_DIAL (Camada 2)
            r2 = tools_comms.make_call(target="Mariana")
            self.assertEqual(r2["status"], "ok")
            self.assertEqual(r2["data"]["method"], "dial_intent")
            self.assertIn("11977776666", r2["message"])
            self.assertIn("Abrindo discador", r2["message"])

            # 3. Contato inexistente
            r3 = tools_comms.make_call(target="Desconhecido")
            self.assertEqual(r3["status"], "error")
            self.assertEqual(r3["message"], "Contato 'Desconhecido' não encontrado na agenda. Informe o número com DDD.")

            # 4. Número direto por dígitos sem passar por contatos
            r4 = tools_comms.make_call(target="11999998888")
            self.assertEqual(r4["status"], "ok")
            self.assertEqual(r4["data"]["number"], "11999998888")

    def test_order_food_99food_deeplink_and_taxis99_fallback(self):
        """Testa order_food com app='99food', fallback de pacote com.taxis99 e cópia para clipboard."""
        import subprocess

        intent_calls = []

        def fake_exec_intent(cmd_str, timeout=6):
            intent_calls.append(cmd_str)
            if "taxis99://food/search" in cmd_str:
                return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="ActivityNotFoundException")
            if "com.taxis99" in cmd_str:
                return subprocess.CompletedProcess(args=[cmd_str], returncode=0, stdout="Starting: Intent", stderr="")
            return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="Error")

        with patch.object(tools_apps, "SIMULATE_HARDWARE", False), \
             patch.object(tools_apps, "_exec_android_intent", side_effect=fake_exec_intent), \
             patch.object(tools_apps, "set_clipboard") as mock_clip:

            res = tools_apps.order_food(query="pizza", app="99food")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["data"]["app"], "99food")
            self.assertEqual(res["data"]["package"], "com.taxis99")
            self.assertEqual(res["data"]["method"], "package_fallback")
            self.assertIn("Abrindo 99 (aba Delivery) para buscar 'pizza'", res["message"])
            mock_clip.assert_called_once_with("pizza")
            self.assertTrue(any("taxis99://food/search?q=pizza" in c for c in intent_calls))
            self.assertTrue(any("com.taxis99" in c for c in intent_calls))

    def test_geocode_destination_viewbox_bias(self):
        """Valida envio do viewbox geográfico (bounded=0) baseado em last_location.json no Nominatim."""
        captured_urls = []

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload
            def read(self):
                return json.dumps(self._payload).encode("utf-8")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def fake_urlopen(req, timeout=4):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            captured_urls.append(url)
            return FakeResp([{"lat": "-7.9450", "lon": "-34.8800", "display_name": "Shopping Paulista"}])

        with patch.object(tools_apps, "load_last_location", return_value={"latitude": -7.9408, "longitude": -34.8730}), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            geo = tools_apps._geocode_destination("Shopping")
            self.assertIsNotNone(geo)
            self.assertEqual(geo["display_name"], "Shopping Paulista")
            self.assertEqual(len(captured_urls), 1)
            self.assertIn("viewbox=", captured_urls[0])
            self.assertIn("bounded=0", captured_urls[0])
            self.assertIn("-35.223000", captured_urls[0])
            self.assertIn("-7.590800", captured_urls[0])

    def test_request_ride_alias_memory_and_3layer_fallback(self):
        """Testa resolução do apelido 'casa' via remember_note e fallback em 3 camadas em request_ride."""
        import subprocess

        tools_mem.remember_note("endereco casa", "Av. Paulista, 1000, São Paulo")
        intent_calls = []

        def fake_exec_intent(cmd_str, timeout=6):
            intent_calls.append(cmd_str)
            if "uber://" in cmd_str or "com.ubercab" in cmd_str:
                return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="ActivityNotFound")
            if "https://m.uber.com/ul/" in cmd_str:
                return subprocess.CompletedProcess(args=[cmd_str], returncode=0, stdout="Starting: Intent", stderr="")
            return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="Error")

        fake_geo = {"latitude": -23.5614, "longitude": -46.6559, "display_name": "Av. Paulista, 1000"}
        with patch.object(tools_apps, "SIMULATE_HARDWARE", False), \
             patch.object(tools_apps, "_geocode_destination", return_value=fake_geo), \
             patch.object(tools_apps, "_exec_android_intent", side_effect=fake_exec_intent):
            res = tools_apps.request_ride(destination="casa", service="uber")
            self.assertEqual(res["status"], "ok")
            self.assertIn("Usando endereço salvo para 'casa': Av. Paulista, 1000, São Paulo", res["message"])
            self.assertEqual(res["data"]["method"], "web_fallback")
            self.assertIn("dropoff[latitude]=-23.5614", res["data"]["url"])
            self.assertTrue(any("uber://?action=setPickup" in c for c in intent_calls))
            self.assertTrue(any("com.ubercab" in c for c in intent_calls))
            self.assertTrue(any("https://m.uber.com/ul/" in c for c in intent_calls))

    def test_order_food_ifood_3layer_fallback(self):
        """Testa execução em 3 camadas (deep link -> pacote -> web) e quote_plus em order_food."""
        import subprocess

        intent_calls = []

        def fake_exec_intent(cmd_str, timeout=6):
            intent_calls.append(cmd_str)
            if "ifood://search" in cmd_str or "br.com.brainweb.ifood" in cmd_str:
                return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="ActivityNotFound")
            if "https://www.ifood.com.br/busca" in cmd_str:
                return subprocess.CompletedProcess(args=[cmd_str], returncode=0, stdout="Starting: Intent", stderr="")
            return subprocess.CompletedProcess(args=[cmd_str], returncode=1, stdout="", stderr="Error")

        with patch.object(tools_apps, "SIMULATE_HARDWARE", False), \
             patch.object(tools_apps, "_exec_android_intent", side_effect=fake_exec_intent), \
             patch.object(tools_apps, "set_clipboard") as mock_clip:
            res = tools_apps.order_food(query="pizza calabresa", app="ifood")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["data"]["method"], "web_fallback")
            self.assertIn("https://www.ifood.com.br/busca?q=pizza+calabresa", res["data"]["url"])
            mock_clip.assert_called_once_with("pizza calabresa")
            self.assertTrue(any("ifood://search?q=pizza+calabresa" in c for c in intent_calls))
            self.assertTrue(any("br.com.brainweb.ifood" in c for c in intent_calls))

    def test_remind_on_wifi_scheduler_active_recall_and_unified_nlp(self):
        """Testa remind_on_wifi (explícito, neste wifi, alias), disparo único no scheduler, Recordação Ativa Pré-LLM e NLP unificado."""
        from android_agent import scheduler
        from android_agent.intent_fallback import match_intent_fallback
        from android_agent.llm_client import SilvaLLMClient
        from android_agent.tools import memory_schedule

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            import tools.memory_schedule as top_mem_sched
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data), \
                 patch.object(top_mem_sched, "DATA_DIR", tmp_data):
                # 1. SSID explícito
                r1 = tools.remind_on_wifi("CASA_5G", "pagar o boleto")
                self.assertEqual(r1["status"], "ok")
                self.assertEqual(r1["data"]["ssid"], "CASA_5G")
                self.assertIn("CASA_5G", r1["message"])

                # 2. "neste wifi" -> usa get_wifi_info()
                with patch("android_agent.tools.hardware.get_wifi_info", return_value={"status": "ok", "data": {"ssid": "Escritorio_Net"}}):
                    r2 = tools.remind_on_wifi("neste wifi", "ligar o notebook")
                    self.assertEqual(r2["status"], "ok")
                    self.assertEqual(r2["data"]["ssid"], "Escritorio_Net")

                # 3. Alias via nota salva ("wifi_casa" -> "MinhaRede_Casa")
                tools.remember_note("wifi_casa", "MinhaRede_Casa")
                r3 = tools.remind_on_wifi("casa", "tirar o lixo")
                self.assertEqual(r3["status"], "ok")
                self.assertEqual(r3["data"]["ssid"], "MinhaRede_Casa")

                # 4. Scheduler dispara apenas uma vez quando Wi-Fi conecta
                scheduler.pop_triggered_alerts()
                with patch("android_agent.scheduler.get_wifi_info", return_value={"status": "ok", "data": {"ssid": "casa_5g"}}):
                    scheduler.check_and_notify_context_reminders()
                    alerts1 = scheduler.pop_triggered_alerts()
                    self.assertEqual(len(alerts1), 1)
                    self.assertEqual(alerts1[0]["event_type"], "context_wifi")
                    self.assertEqual(alerts1[0]["title"], "pagar o boleto")

                    # Segunda passagem não deve disparar novamente (is_active = 0)
                    scheduler.check_and_notify_context_reminders()
                    alerts2 = scheduler.pop_triggered_alerts()
                    self.assertEqual(len(alerts2), 0)

                # 5. Recordação Ativa Pré-LLM (alta relevância intercepta sem chamar llama-server)
                tools.remember_note("codigo armario academia", "4512")
                client = SilvaLLMClient(base_url="http://127.0.0.1:59999")
                with patch("urllib.request.urlopen") as mock_http:
                    call_out, _, err = client.generate_call("Qual é o código do armário da academia?")
                    self.assertIsNone(err)
                    self.assertIn("<call>recall_note(", call_out)
                    mock_http.assert_not_called()

        # 6. Unificação Natural de Lembretes no NLP
        self.assertEqual(
            match_intent_fallback("Quando eu chegar em casa me lembra de pagar o boleto"),
            "<call>remind_on_wifi(ssid='casa', reminder='pagar o boleto')</call>",
        )
        self.assertEqual(
            match_intent_fallback("Quando conectar no wifi Trabalho lembra de falar com o Marcos"),
            "<call>remind_on_wifi(ssid='Trabalho', reminder='falar com o Marcos')</call>",
        )
        self.assertIn("schedule_event(", match_intent_fallback("Me lembra de tomar remédio às 20h"))
        self.assertIn("schedule_event(", match_intent_fallback("Me lembra de tomar água às 23:59"))
        self.assertIn("schedule_event(", match_intent_fallback("Lembra de ligar pro banco amanhã às 10h"))
        self.assertIn("remember_note(", match_intent_fallback("Lembra que a senha do cadeado é 4512"))
        self.assertIn("remember_note(", match_intent_fallback("Anota aí que o protocolo é 98765"))

    def test_voice_notes_multimodal_checklist_and_nlp(self):
        """Testa save_voice_note (voz e texto), get_voice_notes (filtro), check_voice_note (check + remoção de .m4a) e NLP."""
        from android_agent.intent_fallback import match_intent_fallback
        from android_agent.tools import media as tools_media

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            tmp_cap = tmp_dir / "captures"
            tmp_cap.mkdir(parents=True, exist_ok=True)
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_dir), \
                 patch.object(tools_media, "CAPTURES_DIR", tmp_cap):
                # 1. Modo digitado (text_only=True)
                r_txt = tools.save_voice_note(title="ligar pro médico", text_only=True)
                self.assertEqual(r_txt["status"], "ok")
                self.assertEqual(r_txt["data"]["note_type"], "text")

                # 2. Modo voz (text_only=False)
                r_aud = tools.save_voice_note(title="pagar o aluguel", duration=15, text_only=False)
                self.assertEqual(r_aud["status"], "ok")
                self.assertEqual(r_aud["data"]["note_type"], "audio")
                self.assertIn("media_items", r_aud)
                audio_file = tmp_cap / r_aud["data"]["filename"]
                self.assertTrue(audio_file.is_file())

                # 3. Listagem mista e filtro
                g_all = tools.get_voice_notes()
                self.assertEqual(g_all["data"]["total"], 2)
                g_filt = tools.get_voice_notes("aluguel")
                self.assertEqual(g_filt["data"]["total"], 1)
                self.assertEqual(g_filt["data"]["voice_notes"][0]["title"], "pagar o aluguel")

                # 4. Check remove da lista ativa e exclui .m4a do disco
                chk_aud = tools.check_voice_note(query="aluguel")
                self.assertTrue(chk_aud["data"]["checked"])
                self.assertTrue(chk_aud["data"]["deleted_audio"])
                self.assertFalse(audio_file.exists())

                g_after = tools.get_voice_notes()
                self.assertEqual(g_after["data"]["total"], 1)
                self.assertEqual(g_after["data"]["voice_notes"][0]["title"], "ligar pro médico")

        # 5. Roteamento NLP
        self.assertIn("save_voice_note(", match_intent_fallback("grava uma nota de voz para lembrar de pagar o aluguel"))
        self.assertIn("text_only=False", match_intent_fallback("gravar lembrete de voz de 20 segundos"))
        self.assertIn("text_only=True", match_intent_fallback("adiciona na lista de lembretes: ligar pro médico"))
        self.assertIn("text_only=True", match_intent_fallback("anota no checklist pagar internet"))
        self.assertIn("get_voice_notes(", match_intent_fallback("quais notas de voz eu tenho?"))
        self.assertIn("get_voice_notes(", match_intent_fallback("mostra meus lembretes"))
        self.assertIn("check_voice_note(", match_intent_fallback("marca como check a nota do aluguel"))
        self.assertEqual(match_intent_fallback("apaga a última nota de voz"), "<call>check_voice_note(query='última')</call>")

    def test_order_food_ifood_ui_automator_active_search(self):
        """Testa order_food com Deep Link + fallback ativo via ADB UI Automator (tap na lupa, type_text_unicode e Enter)."""
        import subprocess

        fake_home_nodes = [
            {"text": "O que vai pedir hoje?", "content_desc": "", "class": "android.widget.TextView", "cx": 540, "cy": 280},
        ]
        fake_search_nodes = [
            {"text": "Item ou loja", "content_desc": "", "class": "android.widget.EditText", "cx": 500, "cy": 210},
        ]
        dump_seq = [fake_home_nodes, fake_search_nodes]

        with patch.object(tools_apps, "SIMULATE_HARDWARE", False), \
             patch.object(tools_apps, "ensure_adb_connected", return_value="192.168.0.106:38893"), \
             patch.object(tools_apps, "_exec_android_intent", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="Starting: Intent", stderr="")), \
             patch.object(tools_apps, "dump_ui_nodes", side_effect=dump_seq), \
             patch.object(tools_apps, "tap_coords") as mock_tap, \
             patch.object(tools_apps, "type_text_unicode", return_value=(True, "ok")) as mock_type, \
             patch.object(tools_apps, "press_key") as mock_key, \
             patch.object(tools_apps, "set_clipboard"), \
             patch("time.sleep"):
            res = tools_apps.order_food(query="açaí com granola", app="ifood")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["data"]["method"], "ui_automator_search")
            self.assertEqual(mock_tap.call_count, 2)
            mock_type.assert_called_once_with("açaí com granola")
            mock_key.assert_called_once_with(66)

    def test_sqlite_busy_timeout_and_cleanup_orphaned_captures(self):
        """Testa PRAGMA busy_timeout=5000 e coleta seletiva de mídias órfãs em CAPTURES_DIR."""
        import os
        import time
        from android_agent.tools import core as tools_core, media as tools_media, memory_schedule

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            tmp_cap = tmp_dir / "captures"
            tmp_cap.mkdir(parents=True, exist_ok=True)
            with patch.object(memory_schedule, "DATA_DIR", tmp_dir), \
                 patch.object(tools_core, "CAPTURES_DIR", tmp_cap), \
                 patch.object(tools_media, "CAPTURES_DIR", tmp_cap):
                # 1. PRAGMA busy_timeout
                conn = memory_schedule._get_memory_db()
                busy_val = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
                conn.close()
                self.assertEqual(busy_val, 5000)

                # 2. Cria arquivos: antigo (>7d), recente (<7d), nota ativa, nota checada e órfã >24h
                old_temp = tmp_cap / "capture_old.jpg"
                new_temp = tmp_cap / "capture_new.jpg"
                orphan_vn = tmp_cap / "voice_note_orphan.m4a"
                old_temp.write_bytes(b"old")
                new_temp.write_bytes(b"new")
                orphan_vn.write_bytes(b"orphan")

                old_ts = time.time() - (8 * 86400)
                os.utime(old_temp, (old_ts, old_ts))
                os.utime(orphan_vn, (time.time() - (2 * 86400), time.time() - (2 * 86400)))

                active_res = tools.save_voice_note(title="ativa", duration=5, text_only=False)
                active_file = tmp_cap / active_res["data"]["filename"]

                checked_res = tools.save_voice_note(title="concluida", duration=5, text_only=False)
                checked_file = tmp_cap / checked_res["data"]["filename"]
                # Marca is_checked=1 no DB sem apagar ainda do disco para testar o GC
                conn = memory_schedule._get_memory_db()
                with conn:
                    conn.execute("UPDATE voice_notes SET is_checked = 1 WHERE id = ?", (checked_res["data"]["id"],))
                conn.close()

                gc_stats = tools_core.cleanup_orphaned_captures(max_age_days=7)
                self.assertEqual(gc_stats["removed_temp"], 1)
                self.assertEqual(gc_stats["removed_voice"], 2)
                self.assertFalse(old_temp.exists())
                self.assertTrue(new_temp.exists())
                self.assertTrue(active_file.exists())
                self.assertFalse(checked_file.exists())
                self.assertFalse(orphan_vn.exists())


if __name__ == "__main__":
    unittest.main()
