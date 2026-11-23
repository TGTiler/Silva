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

    def test_fallback_wifi_expanded_rules(self):
        """Valida novas regras expandidas de scan_wifi e get_wifi_info com variações coloquiais."""
        # 1. scan_wifi()
        self.assertEqual(match_intent_fallback("Quais wifi tem ao meu redor"), "<call>scan_wifi()</call>")
        self.assertEqual(match_intent_fallback("Quais redes wifi tem por aqui"), "<call>scan_wifi()</call>")
        self.assertEqual(match_intent_fallback("wifis ao meu redor"), "<call>scan_wifi()</call>")
        self.assertEqual(match_intent_fallback("redes ao redor"), "<call>scan_wifi()</call>")
        self.assertEqual(match_intent_fallback("wifis por aqui"), "<call>scan_wifi()</call>")
        self.assertEqual(match_intent_fallback("redes disponiveis"), "<call>scan_wifi()</call>")
        self.assertEqual(match_intent_fallback("buscar redes wifi"), "<call>scan_wifi()</call>")

        # 2. get_wifi_info()
        self.assertEqual(match_intent_fallback("Qual wifi estou conectado"), "<call>get_wifi_info()</call>")
        self.assertEqual(match_intent_fallback("qual wifi to conectado"), "<call>get_wifi_info()</call>")
        self.assertEqual(match_intent_fallback("qual rede estou conectado"), "<call>get_wifi_info()</call>")
        self.assertEqual(match_intent_fallback("em qual wifi estou conectado"), "<call>get_wifi_info()</call>")
        self.assertEqual(match_intent_fallback("qual wifi conectado"), "<call>get_wifi_info()</call>")

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

    def test_fallback_compound_numbers_ptbr(self):
        """Testa parsing de números compostos por extenso (centenas, dezenas, multiplicadores)."""
        # vinte e cinco vezes quatro -> 25 * 4
        call_mult = match_intent_fallback("quanto é vinte e cinco vezes quatro")
        self.assertEqual(call_mult, "<call>calculate(expression='25 * 4')</call>")

        # dois mil e quinhentos dividido por cento e vinte e cinco -> 2500 / 125
        call_div = match_intent_fallback("quanto dá dois mil e quinhentos dividido por cento e vinte e cinco")
        self.assertEqual(call_div, "<call>calculate(expression='2500 / 125')</call>")

    def test_fallback_contextual_time_and_alarms(self):
        """Testa expressões contextuais de tempo (meia hora, meia-noite, um quarto de hora)."""
        # meia hora -> 30 minutos (artigo 'um' antes de timer não deve virar número)
        call_timer = match_intent_fallback("coloca um timer de meia hora")
        self.assertIsNotNone(call_timer)
        self.assertIn("set_timer(minutes=30", call_timer)

        # alarme pra meia-noite -> 00:00
        call_alarm = match_intent_fallback("coloca alarme pra meia-noite")
        self.assertIsNotNone(call_alarm)
        self.assertIn("set_alarm(time='00:00'", call_alarm)

    def test_fallback_typos_and_slangs(self):
        """Testa tolerância a erros de digitação (typos) e gírias de celular."""
        # Typos em comando multi-ação: baterria -> bateria, lanterana -> lanterna
        call_typo = match_intent_fallback("silva vê a baterria e liga a lanterana")
        self.assertEqual(call_typo, "<call>get_battery()</call><call>set_torch(state=True)</call>")

        # Gírias: no talo -> 100%, zap -> whatsapp
        call_slang = match_intent_fallback("bota o brilho no talo e abre o zap")
        self.assertEqual(call_slang, "<call>set_brightness(level=100)</call><call>open_app(app_name='whatsapp')</call>")

    def test_fallback_wifi_disambiguation_and_payloads(self):
        """Testa desambiguação de Wi-Fi e proteção de payloads de transporte."""
        # Senha de Wi-Fi -> recall_note
        call_pwd = match_intent_fallback("qual a senha do wifi")
        self.assertIsNotNone(call_pwd)
        self.assertIn("recall_note(", call_pwd)
        self.assertIn("senha do wifi", call_pwd)

        # Redes próximas -> scan_wifi
        call_scan = match_intent_fallback("quais wifis tem perto")
        self.assertEqual(call_scan, "<call>scan_wifi()</call>")

        # Corrida com destino composto 'Abreu e Lima' e artigo 'um'
        call_ride = match_intent_fallback("chama um uber para Abreu e Lima")
        self.assertEqual(call_ride, "<call>request_ride(destination='Abreu e Lima', app='uber')</call>")

    def test_fallback_volume_math_and_recall_refinements(self):
        """Testa melhorias de sinônimos de volume/brilho, tolerância a typos matemáticos e restrição de recall_note."""
        # 1. Volume total / máximo / mínimo / meio
        self.assertEqual(match_intent_fallback("Aumente total o volume"), "<call>set_volume(stream='music', level=100)</call>")
        self.assertEqual(match_intent_fallback("abaixe o volume no minimo"), "<call>set_volume(stream='music', level=0)</call>")
        self.assertEqual(match_intent_fallback("volume pela metade"), "<call>set_volume(stream='music', level=50)</call>")

        # 2. Typos em funções matemáticas: quadrade -> quadrada
        self.assertEqual(match_intent_fallback("Qual a raiz quadrade de 144"), "<call>calculate(expression='sqrt(144)')</call>")
        self.assertEqual(match_intent_fallback("qual a raiz cubica de 27"), "<call>calculate(expression='cbrt(27)')</call>")

        # 3. Perguntas gerais enciclopédicas não devem acionar recall_note (devem ir para o LLM)
        self.assertIsNone(match_intent_fallback("qual a capital da franca"))
        self.assertIsNone(match_intent_fallback("quem foi albert einstein"))

        # 4. Busca de memória pessoal explícita
        call_wifi = match_intent_fallback("qual a senha do wifi")
        self.assertIsNotNone(call_wifi)
        self.assertIn("recall_note", call_wifi)

    def test_fallback_wifi_ecosystem_and_memory(self):
        """Testa ecossistema Wi-Fi completo (connect_wifi, get_wifi_info, set_wifi_state)."""
        # 1. connect_wifi com senha preservando case
        c1 = match_intent_fallback("Silva, conecte-se ao wifi Casa_5G com a senha 1234565")
        self.assertEqual(c1, "<call>connect_wifi(ssid='Casa_5G', password='1234565')</call>")

        # 2. connect_wifi rede aberta
        c2 = match_intent_fallback("conectar ao wi-fi RedeAberta")
        self.assertEqual(c2, "<call>connect_wifi(ssid='RedeAberta', password='')</call>")

        # 3. get_wifi_info
        c3 = match_intent_fallback("qual meu ip e qual wifi estou conectado?")
        self.assertEqual(c3, "<call>get_wifi_info()</call>")

        c4 = match_intent_fallback("qual wifi estou conectado")
        self.assertEqual(c4, "<call>get_wifi_info()</call>")

        c4b = match_intent_fallback("qual meu wifi")
        self.assertEqual(c4b, "<call>get_wifi_info()</call>")

        c4c = match_intent_fallback("qual o meu wifi")
        self.assertEqual(c4c, "<call>get_wifi_info()</call>")

        # Desambiguação com senha de Wi-Fi -> recall_note
        c_pwd_meu = match_intent_fallback("qual a senha do meu wifi")
        self.assertEqual(c_pwd_meu, "<call>recall_note(query='senha do wifi')</call>")

        # 4. set_wifi_state
        c5 = match_intent_fallback("desativa o wi-fi pfv")
        self.assertEqual(c5, "<call>set_wifi_state(state=False)</call>")

        c6 = match_intent_fallback("liga o wifi")
        self.assertEqual(c6, "<call>set_wifi_state(state=True)</call>")

        # 5. Execução simulada salvando credencial no SQLite memory.db
        from android_agent.tools import connect_wifi, recall_note
        res_conn = connect_wifi(ssid="Casa_5G", password="MinhaSenhaForte2026")
        self.assertEqual(res_conn["status"], "ok")
        self.assertTrue(res_conn["data"]["saved_to_memory"])

        # Recupera do banco de memórias SQLite FTS5
        res_recall = recall_note(query="wifi Casa_5G")
        self.assertEqual(res_recall["status"], "ok")
        self.assertTrue(res_recall["data"]["found"])
        keys_found = [n["key"] for n in res_recall["data"]["notes"]]
        self.assertIn("wifi Casa_5G", keys_found)

    def test_search_query_cleaning_and_multi_source(self):
        """Testa limpeza de artigos e ruídos na query de busca e retorno de search_google."""
        call = match_intent_fallback("pesquise sobre o GTA 6 no google")
        self.assertEqual(call, "<call>search_google(query='GTA 6')</call>")

        call_v = match_intent_fallback("pesquise sobre o GTA V")
        self.assertEqual(call_v, "<call>search_google(query='GTA V')</call>")

        call_dot = match_intent_fallback("pesquisar por um hotel em SP no google por favor.")
        self.assertEqual(call_dot, "<call>search_google(query='hotel em SP')</call>")

        from android_agent.tools import search_google
        from android_agent.parser import execute_call

        # Testa sanitização de artigos na própria função search_google
        res_o = search_google("o GTA V", open_browser=False)
        self.assertEqual(res_o["data"]["query"], "GTA V")

        res = search_google("GTA 6", open_browser=False)
        self.assertEqual(res["status"], "ok")
        self.assertIn("google_url", res["data"])
        self.assertIn("wiki", res["data"])
        self.assertIn("results", res["data"])
        self.assertNotIn("\n\n\n", res["message"])

        # Valida que não há URLs cruas e sim links Markdown no message
        self.assertIn("[Ler artigo completo na Wikipédia]", res["message"])
        self.assertIn("[Ver todos os resultados no Google]", res["message"])
        self.assertNotIn("Link: https://", res["message"])
        self.assertNotIn("Fonte: https://", res["message"])
        self.assertNotIn("Pesquisar no Google: https://", res["message"])

        # Valida propagação de tool_data em execute_call
        exec_res = execute_call("<call>search_google(query='GTA V')</call>")
        self.assertIn("tool_data", exec_res)
        self.assertIsNotNone(exec_res["tool_data"])
        self.assertEqual(exec_res["tool_data"]["query"], "GTA V")

    def test_dictation_battery_and_punctuation_fallback(self):
        """Testa frases de ditado por voz do teclado com pontuação terminal e termos coloquiais de bateria."""
        # 1. Teste explícito obrigatório
        self.assertEqual(
            match_intent_fallback("Quantos por cento está minha bateria?"),
            "<call>get_battery()</call>"
        )

        # 2. Variações coloquiais de ditado
        variations = [
            ("quantos porcento ta minha bateria", "<call>get_battery()</call>"),
            ("quantos porcento ta minha bateria?", "<call>get_battery()</call>"),
            ("porcentagem da bateria", "<call>get_battery()</call>"),
            ("porcentagem de bateria", "<call>get_battery()</call>"),
            ("quanto tem de bateria", "<call>get_battery()</call>"),
            ("quanto sobrou de bateria", "<call>get_battery()</call>"),
            ("como esta a bateria", "<call>get_battery()</call>"),
            ("como esta a bateria?", "<call>get_battery()</call>"),
            ("nivel da bateria", "<call>get_battery()</call>"),
            ("quanto ta a bateria?", "<call>get_battery()</call>"),
            ("quanto sobrou de carga?", "<call>get_battery()</call>"),
            ("qual o nivel da bateria?", "<call>get_battery()</call>"),
        ]
        for query, expected in variations:
            with self.subTest(query=query):
                self.assertEqual(match_intent_fallback(query), expected)


if __name__ == "__main__":
    unittest.main()
