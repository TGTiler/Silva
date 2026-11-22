"""
Testes do Parser AST, Whitelist de Execução e Intent Fallback.
"""

import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

from android_agent.parser import parse_function_calls, execute_call
from android_agent.intent_fallback import match_intent_fallback, parse_single_intent


class TestParserAndFallback(unittest.TestCase):
    """Testes unitários para parser.py e intent_fallback.py."""

    def test_parse_single_and_multi_calls(self):
        """Testa parsing de chamada única e de chamadas múltiplas."""
        single_raw = "<call>get_battery()</call>"
        parsed = parse_function_calls(single_raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0], ("get_battery", {}))

        multi_raw = "<call>get_battery()</call><call>set_torch(state=True)</call>"
        parsed_multi = parse_function_calls(multi_raw)
        self.assertEqual(len(parsed_multi), 2)
        self.assertEqual(parsed_multi[0], ("get_battery", {}))
        self.assertEqual(parsed_multi[1], ("set_torch", {"state": True}))

    def test_whitelist_and_injection_blocking(self):
        """Testa rejeição de funções fora da whitelist e comandos maliciosos."""
        invalid_raw = "<call>system_exec(cmd='rm -rf /')</call>"
        self.assertEqual(parse_function_calls(invalid_raw), [("none", {})])

        injection_raw = "<call>calculate(expression='__import__(\"os\").system(\"ls\")')</call>"
        # O parser pode aceitar os args da assinatura, mas calculate() deve bloquear com erro de segurança
        res = execute_call(injection_raw)
        self.assertEqual(res["status"], "error")
        self.assertIn("não permitida", res["message"])

    def test_status_propagation(self):
        """Testa a propagação de status 'ok', 'partial_error' e 'error'."""
        # 1. Status 'ok'
        ok_res = execute_call("<call>get_battery()</call>")
        self.assertEqual(ok_res["status"], "ok")

        # 2. Status 'error' (expressão inválida)
        err_res = execute_call("<call>calculate(expression='invalid_syntax++')</call>")
        self.assertEqual(err_res["status"], "error")

        # 3. Status 'partial_error' (uma OK e uma com erro)
        partial_res = execute_call(
            "<call>get_battery()</call><call>calculate(expression='invalid_syntax++')</call>"
        )
        self.assertEqual(partial_res["status"], "partial_error")

    def test_media_items_accumulation(self):
        """Testa o acúmulo de media_items ao tirar foto e captura de tela."""
        call_raw = "<call>take_photo(camera_id=0)</call><call>take_screenshot()</call>"
        res = execute_call(call_raw)
        self.assertIn("media_items", res)
        self.assertIsInstance(res["media_items"], list)
        self.assertGreaterEqual(len(res["media_items"]), 2)
        for item in res["media_items"]:
            self.assertIn("type", item)
            self.assertIn("url", item)
            self.assertTrue(item["url"].startswith("/captures/"))

    def test_fallback_wifi(self):
        """Testa fallback de intenção para escaneamento de Wi-Fi."""
        prompts = [
            "quais redes wifi tem aqui",
            "escanear redes wifi disponíveis",
            "quais as redes wi-fi proximas",
            "ver redes wifi"
        ]
        for p in prompts:
            call = match_intent_fallback(p)
            self.assertIsNotNone(call, f"Deveria detectar Wi-Fi para: {p}")
            self.assertIn("scan_wifi()", call)

    def test_fallback_math_scientific_and_words(self):
        """Testa fallback para expressões matemáticas por extenso e científicas."""
        # Operações por extenso
        call_words = match_intent_fallback("quanto é doze vezes doze")
        self.assertIsNotNone(call_words)
        self.assertIn("calculate(", call_words)
        self.assertIn("12", call_words)

        # Científica: raiz quadrada
        call_sqrt = match_intent_fallback("calcule a raiz quadrada de 144")
        self.assertIsNotNone(call_sqrt)
        self.assertIn("sqrt(144)", call_sqrt)

    def test_fallback_weather_prepositions_and_compound_names(self):
        """Testa resolução de clima com preposições e proteção de nomes compostos."""
        # Preposição de/em
        c1 = match_intent_fallback("qual a previsão do tempo de recife hoje?")
        self.assertIsNotNone(c1)
        self.assertIn("location='Recife'", c1)

        c2 = match_intent_fallback("como vai ser o clima em são paulo amanhã?")
        self.assertIsNotNone(c2)
        self.assertIn("location='São Paulo'", c2)

        # Nome composto com ' e ' (não deve quebrar em cláusulas separadas)
        c3 = match_intent_fallback("previsão do tempo em Abreu e Lima amanhã")
        self.assertIsNotNone(c3)
        self.assertIn("location='Abreu e Lima'", c3)


if __name__ == "__main__":
    unittest.main()
