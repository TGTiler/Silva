"""
Mapeador inteligente de intenções em linguagem natural (PT-BR) para chamadas de função do Silva.
Atua como camada determinística ultra-rápida e robusta para garantir que todos os comandos
sejam traduzidos com precisão imediata mesmo em micro-modelos quantizados.
Suporta números compostos (Pilar A), normalização de gírias e typos (Pilar B),
roteamento baseado em pontuação (Pilar C) e multi-ações encadeadas (Pilar D).
"""

import re
from typing import List, Optional

# Importações do pacote NLP modular com suporte tanto a pacote quanto execução direta
try:
    from .nlp import (
        parse_ptbr_numbers,
        normalize_colloquial_ptbr,
        ScoredIntentRouter,
        normalize_text,
        _format_call,
        _protect_compound_names,
        _unprotect_compound_names,
        _normalize_math_expression,
        _clean_ride_destination,
        _clean_food_query,
        _clean_install_app_name,
        _clean_weather_location,
        ALLOWED_MATH_NAMES,
    )
except ImportError:
    from nlp import (
        parse_ptbr_numbers,
        normalize_colloquial_ptbr,
        ScoredIntentRouter,
        normalize_text,
        _format_call,
        _protect_compound_names,
        _unprotect_compound_names,
        _normalize_math_expression,
        _clean_ride_destination,
        _clean_food_query,
        _clean_install_app_name,
        _clean_weather_location,
        ALLOWED_MATH_NAMES,
    )

# Dicionário de compatibilidade retroativa
NUM_WORDS_PT = {
    "zero": "0", "um": "1", "uma": "1", "dois": "2", "duas": "2",
    "tres": "3", "três": "3", "quatro": "4", "cinco": "5",
    "seis": "6", "meia": "6", "sete": "7", "oito": "8", "nove": "9",
    "dez": "10", "onze": "11", "doze": "12", "treze": "13",
    "quatorze": "14", "catorze": "14", "quinze": "15",
    "dezesseis": "16", "dezasseis": "16", "dezessete": "17",
    "dezoito": "18", "dezenove": "19", "vinte": "20",
    "trinta": "30", "quarenta": "40", "cinquenta": "50",
    "sessenta": "60", "setenta": "70", "oitenta": "80",
    "noventa": "90", "cem": "100", "cento": "100", "mil": "1000",
}

# Verbos e termos que iniciam cláusulas de comando dependentes
COMMAND_VERBS = {
    "abra", "abre", "abrir", "ligue", "liga", "ligar", "desligue", "desliga", "desligar",
    "toque", "toca", "tocar", "pause", "pausa", "pausar", "coloque", "coloca", "colocar",
    "bote", "bota", "botar", "defina", "define", "definir", "configure", "configura", "configurar",
    "chama", "chame", "chamar", "peça", "peca", "pede", "pedir", "envie", "envia", "enviar",
    "manda", "mande", "mandar", "lembra", "lembre", "lembrar", "anote", "anota", "anotar",
    "salve", "salva", "salvar", "pesquise", "pesquisa", "pesquisar", "busque", "busca", "buscar",
    "baixe", "baixa", "baixar", "instale", "instala", "instalar", "leia", "ler", "mostre", "mostrar",
    "veja", "ver", "ve", "vê", "qual", "quais", "quanto", "quantos", "tempo", "clima", "calcula", "calcule",
    "vibra", "vibrar", "aumenta", "aumentar", "diminui", "diminuir", "tire", "tira", "tirar",
    "grave", "grava", "gravar", "silencie", "silencia", "muta", "mutar"
}

# Instância singleton do roteador de pontuação
_ROUTER = ScoredIntentRouter()


def parse_single_intent(raw_cmd: str) -> Optional[str]:
    """
    Tenta identificar uma intenção única e retornar uma tag <call>...</call>.
    Aplica pré-processamento de números compostos, normalização de gírias e pontuação ponderada.
    """
    if not raw_cmd or not raw_cmd.strip():
        return None

    # Aplica normalização numérica e de gírias na cláusula única se ainda não foi feito
    parsed_cmd = parse_ptbr_numbers(raw_cmd)
    normalized_cmd = normalize_colloquial_ptbr(parsed_cmd)

    return _ROUTER.route(normalized_cmd)


def match_intent_fallback(user_prompt: str) -> Optional[str]:
    """
    Roteador de intenções composto (Pilar D).
    1. Protege nomes de cidades e expressões compostas com 'e'.
    2. Converte números compostos ('vinte e cinco' -> '25') antes do splitter de frases.
    3. Normaliza gírias de celular ('no talo' -> '100%', 'zap' -> 'whatsapp') e corrige typos.
    4. Divide cláusulas encadeadas por conectores fortes e 'e' condicional a verbos.
    5. Concatena chamadas múltiplas ou retorna intenção única.
    """
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return None

    # Caso especial: Instalação ou busca combinada na Play Store
    if re.search(r"(?i)\babre\s+(?:a|o)?\s*(?:play\s*store|playstore|google\s+play)\s+e\s+(?:baixa|instala|procura|pesquisa|busca)\b", clean_prompt):
        single = parse_single_intent(clean_prompt)
        if single:
            return single

    # 1. Protege nomes compostos como "Abreu e Lima"
    protected = _protect_compound_names(clean_prompt)

    # 2. Converte números compostos (Pilar A) ANTES do splitter de frases
    num_normalized = parse_ptbr_numbers(protected)

    # 3. Normaliza gírias e erros de digitação (Pilar B)
    colloquial_normalized = normalize_colloquial_ptbr(num_normalized)

    # 4. Divisão primária por separadores fortes
    strong_delims = r";|\s+(?:e\s+tamb[eé]m|depois|em\s+seguida)\s+"
    primary_parts = [p.strip() for p in re.split(strong_delims, colloquial_normalized, flags=re.IGNORECASE) if p.strip()]

    clauses = []
    for part in primary_parts:
        # Divide por ' e ' apenas se o trecho seguinte iniciar com verbo de comando
        tokens = re.split(r"(\s+[eE]\s+)", part)
        current_chunk = tokens[0]
        i = 1
        while i < len(tokens):
            connector = tokens[i]
            next_chunk = tokens[i + 1] if i + 1 < len(tokens) else ""
            words = next_chunk.strip().split()
            first_word = normalize_text(words[0]) if words else ""

            if first_word in COMMAND_VERBS:
                clauses.append(current_chunk.strip())
                current_chunk = next_chunk
            else:
                current_chunk += connector + next_chunk
            i += 2
        if current_chunk.strip():
            clauses.append(current_chunk.strip())

    # Se identificou múltiplas cláusulas de comando
    matched_calls = []
    if len(clauses) > 1:
        for clause in clauses:
            call = _ROUTER.route(clause)
            if call:
                matched_calls.append(call)

    if len(matched_calls) >= 2:
        return "".join(matched_calls)

    # Caso não seja comando composto, avalia o prompt inteiro como comando único
    return _ROUTER.route(colloquial_normalized)
