"""
Testes automatizados para Memória Conversacional de Curto Prazo (multi-turno),
resolução anafórica e encadeamento real de ferramentas via '$prev_result'.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

from android_agent.llm_client import SilvaLLMClient
from android_agent.parser import execute_call
from android_agent.intent_fallback import match_intent_fallback
from android_agent.tools import memory_schedule
from android_agent import conversation_context


class TestConversationPipeline(unittest.TestCase):
    """Testa contexto multi-turno, isolamento de sessões e encadeamento $prev_result."""

    def setUp(self):
        with conversation_context._CTX_LOCK:
            conversation_context._SESSIONS.clear()
        self.client = SilvaLLMClient()

    def test_weather_multiturn_and_session_isolation(self):
        sid_a = "sess_weather_a"
        sid_b = "sess_weather_b"

        with patch("android_agent.tools.weather_web.get_weather") as mock_weather:
            # Garante que AVAILABLE_TOOLS aponte para o mock ou simule retorno via execute_call
            with patch.dict(
                "android_agent.parser.AVAILABLE_TOOLS",
                {
                    "get_weather": lambda day="hoje", time="", location="": {
                        "status": "ok",
                        "message": f"Clima para {location or 'GPS'} ({day}): 28°C",
                        "data": {"location": location, "day": day},
                    }
                },
            ):
                # Turno 1: define Recife na sessão A
                call_1, _, err_1 = self.client.generate_call("Qual o clima em Recife hoje?", session_id=sid_a)
                self.assertIsNone(err_1)
                self.assertIn("get_weather", call_1)
                self.assertIn("Recife", call_1)
                res_1 = execute_call(call_1, session_id=sid_a, user_text="Qual o clima em Recife hoje?")
                self.assertEqual(res_1["status"], "ok")

                # Turno 2 (mesma sessão): "E amanhã?" deve herdar Recife
                call_2, _, err_2 = self.client.generate_call("E amanhã?", session_id=sid_a)
                self.assertIsNone(err_2)
                self.assertIn("get_weather", call_2)
                self.assertIn("Recife", call_2)
                self.assertIn("amanhã", call_2)

                # Turno 2b (mesma sessão): "E em Olinda?" deve trocar a cidade mantendo o contexto de clima
                call_2b, _, err_2b = self.client.generate_call("E em Olinda?", session_id=sid_a)
                self.assertIsNone(err_2b)
                self.assertIn("get_weather", call_2b)
                self.assertIn("Olinda", call_2b)

                # Turno 3 (nova sessão): "E amanhã?" NÃO pode vazar Recife da sessão A
                call_3, _, _ = self.client.generate_call("E amanhã?", session_id=sid_b)
                self.assertNotIn("Recife", call_3 or "")

    def test_piped_multicall_calculate_and_remember_note_sqlite(self):
        sid = "sess_pipe_calc"
        prompt = "Calcula 25 * 4 e anota o resultado como meta"

        raw_call = match_intent_fallback(prompt)
        self.assertIsNotNone(raw_call)
        self.assertIn("calculate(", raw_call)
        self.assertIn("remember_note(", raw_call)
        self.assertIn("$prev_result", raw_call)

        res = execute_call(raw_call, session_id=sid, user_text=prompt)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(res["calls"]), 2)

        saved_value = res["calls"][1]["args"]["value"]
        self.assertIn("100", saved_value)
        self.assertNotIn("$prev_result", saved_value)

        recalled = memory_schedule.recall_note("meta")
        self.assertEqual(recalled["status"], "ok")
        self.assertIn("100", recalled["message"])

    def test_piped_multicall_battery_and_sms_and_search_save(self):
        sms_call = match_intent_fallback(
            "Vê quanto está minha bateria e manda isso por SMS para 11988887777"
        )
        self.assertIsNotNone(sms_call)
        self.assertIn("<call>get_battery()</call>", sms_call)
        self.assertIn("send_sms(", sms_call)
        self.assertIn("11988887777", sms_call)
        self.assertIn("$prev_result", sms_call)

        search_call = match_intent_fallback(
            "Pesquisa a cotação do dólar e salva isso na memória"
        )
        self.assertIsNotNone(search_call)
        self.assertIn("search_google(", search_call)
        self.assertIn("remember_note(", search_call)
        self.assertIn("$prev_result", search_call)

    def test_multiturn_save_and_sms_chaining(self):
        sid = "sess_multiturn_chain"

        # Turno 1: get_battery
        call_1, _, err_1 = self.client.generate_call("Qual o nível da bateria?", session_id=sid)
        self.assertIsNone(err_1)
        res_1 = execute_call(call_1, session_id=sid, user_text="Qual o nível da bateria?")
        self.assertEqual(res_1["status"], "ok")
        battery_msg = res_1["message"]

        # Turno 2: "Salva isso como status bateria"
        call_2, _, err_2 = self.client.generate_call("Salva isso como status bateria", session_id=sid)
        self.assertIsNone(err_2)
        self.assertIn("remember_note(", call_2)
        self.assertIn("$prev_result", call_2)

        res_2 = execute_call(call_2, session_id=sid, user_text="Salva isso como status bateria")
        self.assertEqual(res_2["status"], "ok")
        self.assertEqual(res_2["calls"][0]["args"]["key"], "status bateria")
        self.assertTrue(len(res_2["calls"][0]["args"]["value"]) > 0)
        self.assertIn(battery_msg[:20], res_2["calls"][0]["args"]["value"])

        recalled = memory_schedule.recall_note("status bateria")
        self.assertEqual(recalled["status"], "ok")

        # Turno 3: "Manda isso por SMS para 11977776666"
        call_3, _, err_3 = self.client.generate_call("Manda isso por SMS para 11977776666", session_id=sid)
        self.assertIsNone(err_3)
        self.assertIn("send_sms(", call_3)
        self.assertIn("11977776666", call_3)
        self.assertIn("$prev_result", call_3)

    def test_prev_result_missing_returns_friendly_error(self):
        sid = "sess_empty_prev"
        res = execute_call(
            "<call>remember_note(key='teste', value='$prev_result')</call>",
            session_id=sid,
            user_text="anota isso",
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("Não há um resultado anterior recente", res["message"])


if __name__ == "__main__":
    unittest.main()
