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


if __name__ == "__main__":
    unittest.main()
