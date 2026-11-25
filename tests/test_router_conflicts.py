"""
Suíte Adversarial de Testes Cruzados para Blindagem em 6 Camadas do Roteador NLP.
Cobre colisões numéricas, multi-domínios, negações, narrativas no passado,
validação de slots, vocativos/cortesias e proteção do splitter.
"""

import sys
import time
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

from android_agent.intent_fallback import match_intent_fallback


class TestRouterConflicts(unittest.TestCase):
    """Testes adversariais cruzando domínios concorrentes."""

    def test_numeric_collisions_masked_and_disambiguated(self):
        cases = [
            ("peça um 99 para o shopping north way para mim", "<call>request_ride(destination='shopping north way', app='99')</call>"),
            ("chama um 99 pop para o aeroporto", "<call>request_ride(destination='aeroporto', app='99')</call>"),
            ("converte 99 dólares para reais", "<call>convert_units(amount=99.0, from_unit='dólares', to_unit='reais')</call>"),
            ("qual a cotação do dolar hoje", "<call>convert_units(amount=1.0, from_unit='USD', to_unit='BRL')</call>"),
            ("quanto está o euro hoje", "<call>convert_units(amount=1.0, from_unit='EUR', to_unit='BRL')</call>"),
            ("liga o 4g agora", "<call>set_mobile_data_state(state=True)</call>"),
            ("desativa o 5g por favor", "<call>set_mobile_data_state(state=False)</call>"),
            ("ativa o 3g", "<call>set_mobile_data_state(state=True)</call>"),
            ("anota que parei o carro no g2 vaga 42", "<call>remember_note(key='parei o carro no g2 vaga 42', value='', ttl_hours=0)</call>"),
            ("lembra que deixei a moto no subsolo 1", "<call>remember_note(key='deixei a moto no subsolo 1', value='', ttl_hours=0)</call>"),
            ("peça um 99food de pizza", "<call>order_food(query='pizza', app='99food')</call>"),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self.assertEqual(match_intent_fallback(prompt), expected)

    def test_multidomain_and_splitter_protection(self):
        cases = [
            ("manda um whatsapp para o João dizendo que já pedi um 99", "<call>send_whatsapp(contact_name='João', message='que já pedi um 99')</call>"),
            ("manda whatsapp pro João dizendo tô saindo e já chego", "<call>send_whatsapp(contact_name='João', message='tô saindo e já chego')</call>"),
            ("coloca leite, café e pão na lista de compras", "<call>add_list_item(item='leite, café e pão', list_name='compras')</call>"),
            ("adiciona arroz e feijão na lista de compras", "<call>add_list_item(item='arroz e feijão', list_name='compras')</call>"),
            ("quando eu conectar no wifi casa me lembra de ligar o bluetooth", "<call>remind_on_wifi(ssid='casa', reminder='ligar o bluetooth')</call>"),
            ("quando eu chegar em casa me lembra de pagar o boleto", "<call>remind_on_wifi(ssid='casa', reminder='pagar o boleto')</call>"),
            ("rota para shopping norte e sul", "<call>navigate_to(destination='shopping norte e sul', app='maps')</call>"),
            ("qual a senha do wifi da sala", "<call>recall_note(query='senha do wifi da sala')</call>"),
            ("me lembra de tomar remédio às 20h", "<call>schedule_event(title='tomar remédio', date='', time='20:00')</call>"),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self.assertEqual(match_intent_fallback(prompt), expected)

    def test_negations_and_past_tense_narratives_return_none(self):
        prompts = [
            "não liga o bluetooth agora",
            "não precisa chamar um uber",
            "nunca apaga minhas notas",
            "para de tocar música",
            "cancela isso por favor",
            "deixa pra lá",
            "hoje eu gastei 99 reais no ifood",
            "ontem eu viajei de avião",
            "ontem eu pedi um ifood",
            "semana passada eu comprei um celular",
            "hoje eu já fui pro trabalho",
        ]
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                self.assertEqual(match_intent_fallback(prompt), "<call>none()</call>")

    def test_courtesy_fillers_vocatives_and_slot_gates(self):
        cases = [
            ("ei silva, toca linkin park no spotify por favor", "<call>play_media(query='linkin park', app='spotify')</call>"),
            ("oi silva, qual a porcentagem da bateria para mim?", "<call>get_battery()</call>"),
            ("peça uma comida no ifood pra mim", "<call>order_food(query='comida', app='ifood')</call>"),
            ("silva, abre o youtube por gentileza", "<call>open_app(app_name='youtube')</call>"),
            ("toca coldplay no youtube agora mesmo", "<call>play_media(query='coldplay', app='youtube')</call>"),
            ("ligue minha localização", "<call>set_location_state(state=True)</call>"),
            ("ligue a minha localização", "<call>set_location_state(state=True)</call>"),
            ("ligue meu gps", "<call>set_location_state(state=True)</call>"),
            ("ligue para o João", "<call>make_call(target='João')</call>"),
            ("ligue o gps para mim", "<call>set_location_state(state=True)</call>"),
            ("ligue a localização para mim", "<call>set_location_state(state=True)</call>"),
            ("desliga o gps", "<call>set_location_state(state=False)</call>"),
            ("onde eu estou agora?", "<call>get_location()</call>"),
        ]
        for prompt, expected in cases:
            with self.subTest(prompt=prompt):
                self.assertEqual(match_intent_fallback(prompt), expected)

        # Camada 3: Rejeição de slots fora da faixa 0..100
        self.assertIsNone(match_intent_fallback("coloca o volume em 150"))
        self.assertIsNone(match_intent_fallback("define brilho para 200"))

    def test_deterministic_latency_under_2ms(self):
        from android_agent.intent_fallback import _ROUTER
        sample = "peça um 99 para o shopping north way para mim"
        _ROUTER.route(sample)  # warm-up
        t0 = time.perf_counter()
        for _ in range(50):
            _ROUTER.route(sample)
        avg_ms = ((time.perf_counter() - t0) / 50.0) * 1000.0
        self.assertLess(avg_ms, 2.0, f"Latência média do roteador excedeu 2ms: {avg_ms:.3f}ms")


if __name__ == "__main__":
    unittest.main()
