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

    def test_relative_weather_queries(self):
        """Valida comandos de clima e temperatura com referências locais relativas ou explícitas."""
        self.assertEqual(
            match_intent_fallback("Qual a temperatura está fazendo na minha cidade?"),
            "<call>get_weather(day='hoje', time='', location='')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Qual o clima está fazendo no meu bairro"),
            "<call>get_weather(day='hoje', time='', location='')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Como está a temperatura em Paulista?"),
            "<call>get_weather(day='hoje', time='', location='Paulista')</call>"
        )
        self.assertEqual(
            match_intent_fallback("quantos graus esta fazendo na minha regiao"),
            "<call>get_weather(day='hoje', time='', location='')</call>"
        )
        self.assertEqual(
            match_intent_fallback("quanto esta fazendo aqui"),
            "<call>get_weather(day='hoje', time='', location='')</call>"
        )
        self.assertEqual(
            match_intent_fallback("previsao do tempo por aqui"),
            "<call>get_weather(day='hoje', time='', location='')</call>"
        )

    def test_make_call_intent_priorities(self):
        """Valida que intenções de chamada têm prioridade máxima com alvo e não colidem com lanterna/Wi-Fi."""
        self.assertEqual(
            match_intent_fallback("Faz uma ligação para 11988887777"),
            "<call>make_call(target='11988887777')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Liga pro Carlos"),
            "<call>make_call(target='Carlos')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Chama o Carlos"),
            "<call>make_call(target='Carlos')</call>"
        )
        self.assertEqual(
            match_intent_fallback("fazer ligacao para a Maria por favor"),
            "<call>make_call(target='Maria')</call>"
        )
        # Garante que liga lanterna e liga wifi continuam indo para as ferramentas de sistema
        self.assertEqual(
            match_intent_fallback("liga a lanterna"),
            "<call>set_torch(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("liga o wifi"),
            "<call>set_wifi_state(state=True)</call>"
        )

    def test_99_ride_vs_food_semantic_separation(self):
        """Valida separação semântica estrita entre 99 Corridas (request_ride) e 99Food (order_food)."""
        self.assertEqual(
            match_intent_fallback("Pede um 99 pro centro"),
            "<call>request_ride(destination='centro', app='99')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede um 99 pro shopping"),
            "<call>request_ride(destination='shopping', app='99')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Chama um 99 pra casa"),
            "<call>request_ride(destination='casa', app='99')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede uma pizza na 99"),
            "<call>order_food(query='pizza', app='99food')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede um hambúrguer na 99"),
            "<call>order_food(query='hambúrguer', app='99food')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede comida pelo 99"),
            "<call>order_food(query='comida', app='99food')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede um açaí na 99"),
            "<call>order_food(query='açaí', app='99food')</call>"
        )
        # Super-app 99: táxi -> 99, delivery '99 food' -> 99food, Uber explícito preservado
        cases_99 = [
            ("chama um táxi para o aeroporto", "<call>request_ride(destination='aeroporto', app='99')</call>"),
            ("chama um taxi pro shopping recife", "<call>request_ride(destination='shopping recife', app='99')</call>"),
            ("peça um 99 para o shopping tacaruna", "<call>request_ride(destination='shopping tacaruna', app='99')</call>"),
            ("pede uma pizza no 99", "<call>order_food(query='pizza', app='99food')</call>"),
            ("pedir comida no 99 food", "<call>order_food(query='comida', app='99food')</call>"),
            ("peça um uber para o shopping", "<call>request_ride(destination='shopping', app='uber')</call>"),
        ]
        for phrase, expected in cases_99:
            with self.subTest(phrase=phrase):
                self.assertEqual(match_intent_fallback(phrase), expected)

    def test_colloquial_ride_expressions_and_priority_over_call(self):
        """Valida gírias brasileiras de corrida, destino sem preposição, limpeza de ruídos e prioridade sobre make_call."""
        self.assertEqual(
            match_intent_fallback("Bota um Uber pra casa"),
            "<call>request_ride(destination='casa', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Solta um Uber aqui pro shopping"),
            "<call>request_ride(destination='shopping', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pega um Uber pra mim até o aeroporto"),
            "<call>request_ride(destination='aeroporto', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Quanto tá um Uber pro centro?"),
            "<call>request_ride(destination='centro', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Chama um Uber Arena Castelão"),
            "<call>request_ride(destination='Arena Castelão', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Uber Shopping Recife"),
            "<call>request_ride(destination='Shopping Recife', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede um Uber aqui pra mim pra casa da minha mãe agora por favor"),
            "<call>request_ride(destination='casa da minha mãe', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Chama um Uber pra casa do Pedro"),
            "<call>request_ride(destination='casa do Pedro', app='uber')</call>"
        )

    def test_ride_food_and_call_disambiguation(self):
        """Valida desambiguação entre request_ride, make_call e order_food (incluindo 'Tô com fome')."""
        self.assertEqual(
            match_intent_fallback("Chama um Uber pra casa"),
            "<call>request_ride(destination='casa', app='uber')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede um 99 para o Shopping Paulista por favor"),
            "<call>request_ride(destination='Shopping Paulista', app='99')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Chama o Carlos"),
            "<call>make_call(target='Carlos')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Pede uma pizza de calabresa no iFood"),
            "<call>order_food(query='pizza de calabresa', app='ifood')</call>"
        )
        self.assertEqual(
            match_intent_fallback("Tô com fome, pede um hambúrguer artesanal"),
            "<call>order_food(query='hambúrguer artesanal', app='ifood')</call>"
        )
        self.assertEqual(
            match_intent_fallback("peça uma comida no ifood"),
            "<call>order_food(query='comida', app='ifood')</call>"
        )
        self.assertEqual(
            match_intent_fallback("quero pedir algo no ifood"),
            "<call>order_food(query='comida', app='ifood')</call>"
        )
        self.assertEqual(
            match_intent_fallback("busca pizza no ifood"),
            "<call>order_food(query='pizza', app='ifood')</call>"
        )
        self.assertEqual(
            match_intent_fallback("peça um 99 para o shopping north way para mim"),
            "<call>request_ride(destination='shopping north way', app='99')</call>"
        )
        self.assertEqual(
            match_intent_fallback("qual a cotação do dolar hoje"),
            "<call>convert_units(amount=1.0, from_unit='USD', to_unit='BRL')</call>"
        )
        self.assertEqual(
            match_intent_fallback("quanto está o euro hoje"),
            "<call>convert_units(amount=1.0, from_unit='EUR', to_unit='BRL')</call>"
        )
        self.assertEqual(
            match_intent_fallback("ligue o gps para mim"),
            "<call>set_location_state(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("ligue a localização para mim"),
            "<call>set_location_state(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("desliga o gps"),
            "<call>set_location_state(state=False)</call>"
        )
        self.assertEqual(
            match_intent_fallback("onde eu estou agora?"),
            "<call>get_location()</call>"
        )
        # Desambiguação de 'ligue' + possessivos/artigos: hardware/GPS vs ligação telefônica
        self.assertEqual(
            match_intent_fallback("ligue minha localização"),
            "<call>set_location_state(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("ligue a minha localização"),
            "<call>set_location_state(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("ligue meu gps"),
            "<call>set_location_state(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("ativa minha localização"),
            "<call>set_location_state(state=True)</call>"
        )
        self.assertEqual(
            match_intent_fallback("ligue para o João"),
            "<call>make_call(target='João')</call>"
        )


if __name__ == "__main__":
    unittest.main()
