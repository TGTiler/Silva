"""
Testes de resiliência a formatação, multilinhas, próclises e extração limpa de argumentos.
"""

import unittest
from android_agent.intent_fallback import match_intent_fallback


class TestFormattingResilience(unittest.TestCase):
    """Bateria de testes de estresse para inputs com quebras de linha, próclises e espaços irregulares."""

    def test_multiline_wifi_proclise_without_password(self):
        """Testa conexão Wi-Fi com quebra de linha, próclise 'Se conecte' e SSID com símbolos técnicos."""
        cmd = "Se conecte ao wifi\nHENRIQUE_NET//FERNANDA"
        expected = "<call>connect_wifi(ssid='HENRIQUE_NET//FERNANDA', password='')</call>"
        self.assertEqual(match_intent_fallback(cmd), expected)

    def test_multiline_wifi_proclise_with_password(self):
        """Testa conexão Wi-Fi com quebra de linha, próclise 'Me conecta' e senha complexa preservando símbolos técnicos."""
        cmd = "Me conecta no wi-fi\nCasa_5G\ncom a senha Abc@123!"
        expected = "<call>connect_wifi(ssid='Casa_5G', password='Abc@123!')</call>"
        self.assertEqual(match_intent_fallback(cmd), expected)

    def test_multiline_open_app_casing_and_spaces(self):
        """Testa abertura de app com espaços irregulares, quebra de linha e preservação de maiúsculas."""
        cmd = "  Abra   o\n  YouTube  por favor! "
        expected = "<call>open_app(app_name='YouTube')</call>"
        self.assertEqual(match_intent_fallback(cmd), expected)

    def test_multiline_search_google_query_cleaning(self):
        """Testa busca no Google com quebra de linha, remoção de preposição, artigos e pontuação final."""
        cmd = "Pesquise sobre\n  o GTA 6\nno google?"
        expected = "<call>search_google(query='GTA 6')</call>"
        self.assertEqual(match_intent_fallback(cmd), expected)

    def test_multiline_install_app_play_store(self):
        """Testa instalação de app com quebras de linha e sufixo de Play Store."""
        cmd = "Baixa   o\nTelegram na Play Store"
        expected = "<call>install_app(app_name='Telegram')</call>"
        self.assertEqual(match_intent_fallback(cmd), expected)

    def test_multiline_dictation_battery_question(self):
        """Testa consulta coloquial de bateria com quebra de linha e pontuação de ditado do teclado."""
        cmd = "Quantos por cento\nestá minha bateria?"
        expected = "<call>get_battery()</call>"
        self.assertEqual(match_intent_fallback(cmd), expected)

    def test_anti_dumping_rule_generic_wifi(self):
        """Garante que comandos genéricos sem SSID não despejem o comando inteiro em connect_wifi."""
        # 'conectar wifi' ou 'conectar no wifi' não tem SSID válido; não deve retornar connect_wifi corrompido
        call = match_intent_fallback("conectar wifi")
        if call is not None:
            self.assertNotIn("ssid='conectar wifi'", call)
            self.assertNotIn("ssid='wifi'", call)


if __name__ == "__main__":
    unittest.main()
