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

    def test_all_39_tools_smoke_execution(self):
        """Testa a execução smoke de todas as 39 ferramentas do catálogo em modo simulado."""
        self.assertEqual(len(tools.AVAILABLE_TOOLS), 39, "O catálogo formal deve conter exatamente 39 ferramentas.")

        sample_args = {
            "calculate": {"expression": "2 + 2"},
            "cancel_alarm": {"time": "07:00"},
            "connect_wifi": {"ssid": "TesteNet", "password": "123"},
            "get_battery": {},
            "get_clipboard": {},
            "get_last_location": {},
            "get_last_sms": {"limit": 3},
            "get_location": {},
            "get_notifications": {"app": "whatsapp"},
            "get_weather": {"day": "hoje", "location": "Recife"},
            "get_wifi_info": {},
            "install_app": {"app_name": "spotify"},
            "list_capabilities": {},
            "make_call": {"number": "11999999999"},
            "media_control": {"action": "play"},
            "none": {},
            "open_app": {"app_name": "YouTube"},
            "order_food": {"query": "pizza"},
            "recall_note": {"query": "teste"},
            "record_video": {"duration": 5, "camera_id": 0},
            "remember_note": {"key": "teste", "value": "123"},
            "request_ride": {"destination": "Shopping"},
            "scan_wifi": {},
            "schedule_event": {"title": "Reuniao", "date": "amanha", "time": "14:00"},
            "search_google": {"query": "Python", "open_browser": False},
            "send_sms": {"number": "11999999999", "message": "ola"},
            "set_alarm": {"time": "07:00", "label": "Acordar"},
            "set_brightness": {"level": 50},
            "set_clipboard": {"text": "conteudo de teste"},
            "set_dnd": {"state": True},
            "set_location_state": {"state": True},
            "set_timer": {"minutes": 10},
            "set_torch": {"state": True},
            "set_volume": {"stream": "music", "level": 50},
            "set_wifi_state": {"state": True},
            "take_photo": {"camera_id": 0},
            "take_screenshot": {},
            "tell_joke": {},
            "vibrate": {"duration_ms": 500},
        }

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


if __name__ == "__main__":
    unittest.main()
