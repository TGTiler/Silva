"""
Parser gramatical e semântico de números compostos em Português do Brasil (PT-BR).
Trata expressões temporais contextuais, desambiguação de artigos indefinidos e
composição aritmética de grupos inteiros (centenas, dezenas, unidades e multiplicadores).
"""

import re
from typing import List, Optional, Tuple


# Unidades
UNITS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2,
    "tres": 3, "três": 3, "quatro": 4, "cinco": 5,
    "seis": 6, "sete": 7, "oito": 8, "nove": 9
}

# Números especiais de 10 a 19
TEENS = {
    "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "quatorze": 14, "catorze": 14, "quinze": 15,
    "dezesseis": 16, "dezasseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19
}

# Dezenas
TENS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
    "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90
}

# Centenas
HUNDREDS = {
    "cem": 100, "cento": 100,
    "duzentos": 200, "duzentas": 200,
    "trezentos": 300, "trezentas": 300,
    "quatrocentos": 400, "quatrocentas": 400,
    "quinhentos": 500, "quinhentas": 500,
    "seiscentos": 600, "seiscentas": 600,
    "setecentos": 700, "setecentas": 700,
    "oitocentos": 800, "oitocentas": 800,
    "novecentos": 900, "novecentas": 900
}

# Multiplicadores
SCALES = {
    "mil": 1000,
    "milhao": 1000000,
    "milhão": 1000000,
    "milhoes": 1000000,
    "milhões": 1000000
}

ALL_NUM_WORDS = set(UNITS.keys()) | set(TEENS.keys()) | set(TENS.keys()) | set(HUNDREDS.keys()) | set(SCALES.keys())

# Unidades de medida que forçam "um"/"uma" como número 1
MEASURE_UNITS_FOLLOWING = {
    "minuto", "minutos", "min", "segundo", "segundos", "seg", "s",
    "hora", "horas", "h", "dia", "dias", "vez", "vezes",
    "por cento", "%", "grau", "graus", "metro", "metros", "km", "quilometro", "quilometros"
}

# Substantivos de ação que NÃO devem ser quantificados por "um"/"uma"
ACTION_NOUNS_FOLLOWING = {
    "uber", "carro", "corrida", "taxi", "motorista",
    "foto", "selfie", "print", "screenshot", "video", "gravação", "gravacao",
    "piada", "mensagem", "sms", "torpedo", "notificacao", "notificação",
    "alarme", "timer", "temporizador", "lembrete", "compromisso", "evento",
    "lanche", "pizza", "comida", "refeicao", "refeição", "hamburguer", "pastel",
    "aplicativo", "app", "jogo"
}

# Operadores matemáticos adjacentes
MATH_OPERATORS_ADJACENT = {
    "mais", "menos", "vezes", "dividido", "multiplicado", "igual",
    "+", "-", "*", "/", "^", "%", "x", "X"
}


def _handle_contextual_time(text: str) -> str:
    """Substitui expressões de tempo contextuais e coloquiais prioritárias."""
    # Meia-noite e meio-dia
    text = re.sub(r"\bmeia[- ]noite\b", "00:00", text, flags=re.IGNORECASE)
    text = re.sub(r"\bmeio[- ]dia\b", "12:00", text, flags=re.IGNORECASE)

    # Contexto de alarme para 'uma hora e meia'
    alarm_ctx = bool(re.search(r"\b(?:alarme|acordar|acorda|despertador|despertar|desperta)\b", text, re.IGNORECASE))
    if alarm_ctx:
        text = re.sub(r"\b(?:uma\s+hora\s+e\s+meia|1\s+hora\s+e\s+meia)\b", "01:30", text, flags=re.IGNORECASE)
    else:
        text = re.sub(r"\b(?:uma\s+hora\s+e\s+meia|1\s+hora\s+e\s+meia)\b", "90 minutos", text, flags=re.IGNORECASE)

    # Frações de hora
    text = re.sub(r"\bmeia\s+hora\b", "30 minutos", text, flags=re.IGNORECASE)
    text = re.sub(r"\bum\s+quarto\s+de\s+hora\b", "15 minutos", text, flags=re.IGNORECASE)

    return text


def _evaluate_compound_group(words: List[str]) -> Optional[str]:
    """
    Avalia uma sequência de palavras numéricas em português.
    Se for uma sequência de dígitos soltos (ex: ['nove', 'nove', 'oito', 'seis', 'cinco']),
    retorna como dígitos concatenados ou com espaços.
    Se for uma expressão composta aritmética (ex: ['dois', 'mil', 'quinhentos']),
    retorna o valor numérico somado.
    """
    if not words:
        return None

    clean_words = [w.lower() for w in words if w.lower() != "e"]
    if not clean_words:
        return None

    # Verifica se é uma sequência puramente de dígitos soltos (unidades)
    # Ex: 'nove nove oito meia cinco' -> '9 9 8 6 5'
    all_single_units = all(w in UNITS or w.isdigit() for w in clean_words)
    has_e = any(w.lower() == "e" for w in words)
    has_scale_or_tens = any(w in TENS or w in TEENS or w in HUNDREDS or w in SCALES for w in clean_words)

    if all_single_units and len(clean_words) > 1 and not has_e and not has_scale_or_tens:
        # Sequência ditada dígito a dígito (ex: telefone ou código)
        digits = []
        for w in clean_words:
            if w.isdigit():
                digits.append(w)
            elif w in UNITS:
                digits.append(str(UNITS[w]))
        return " ".join(digits)

    total = 0
    current = 0

    for w in clean_words:
        if w.isdigit():
            current += int(w)
        elif w in UNITS:
            current += UNITS[w]
        elif w in TEENS:
            current += TEENS[w]
        elif w in TENS:
            current += TENS[w]
        elif w in HUNDREDS:
            current += HUNDREDS[w]
        elif w in SCALES:
            mult = SCALES[w]
            if current == 0:
                current = 1
            total += current * mult
            current = 0
        else:
            return None

    total += current
    return str(total)


def parse_ptbr_numbers(text: str) -> str:
    """
    Normaliza números por extenso em português para dígitos numéricos arábicos,
    respeitando composições complexas, artigos indefinidos e ambiguidades de contexto.
    """
    if not text:
        return ""

    # 1. Tratamento Contextual Prioritário
    processed = _handle_contextual_time(text)

    # 2. Tokenização preservando espaçamento original e pontuação
    # Tokens: palavras, espaços, outros símbolos
    tokens = re.findall(r"\w+|[^\w\s]|\s+", processed)
    n = len(tokens)

    # 3. Identifica palavras
    is_word = [bool(re.match(r"^\w+$", t)) for t in tokens]

    # 4. Trata 'meia' adjacente a dígitos ou palavras de dígitos
    for i in range(n):
        if is_word[i] and tokens[i].lower() == "meia":
            prev_word = ""
            for j in range(i - 1, -1, -1):
                if is_word[j]:
                    prev_word = tokens[j].lower()
                    break
            next_word = ""
            for j in range(i + 1, n):
                if is_word[j]:
                    next_word = tokens[j].lower()
                    break

            single_digits_words = {
                "zero", "um", "uma", "dois", "duas", "tres", "três", "quatro",
                "cinco", "seis", "sete", "oito", "nove", "6"
            }
            has_prev = prev_word.isdigit() or prev_word in single_digits_words
            has_next = next_word.isdigit() or next_word in single_digits_words
            if has_prev or has_next:
                tokens[i] = "6"

    # 5. Avalia máscara de palavras numéricas válidas
    # Protege dígitos que pertençam a horários já estruturados (ex: 00:00, 01:30)
    is_in_time_format = [False] * n
    for i in range(n):
        if tokens[i] == ":" and i > 0 and i < n - 1:
            if tokens[i - 1].isdigit() and tokens[i + 1].isdigit():
                is_in_time_format[i - 1] = True
                is_in_time_format[i] = True
                is_in_time_format[i + 1] = True

    valid_num_mask = [False] * n
    for i in range(n):
        if not is_word[i] or is_in_time_format[i]:
            continue
        low = tokens[i].lower()
        if low in (ALL_NUM_WORDS - {"um", "uma"}) or low.isdigit():
            valid_num_mask[i] = True
        elif low in {"um", "uma"}:
            next_word = ""
            for j in range(i + 1, n):
                if is_word[j]:
                    next_word = tokens[j].lower()
                    break
            prev_word = ""
            for j in range(i - 1, -1, -1):
                if is_word[j]:
                    prev_word = tokens[j].lower()
                    break

            # Se anteceder substantivo de ação -> ARTIGO (NÃO CONVERTER)
            if next_word in ACTION_NOUNS_FOLLOWING:
                valid_num_mask[i] = False
                continue

            # Se preceder unidade de medida -> NÚMERO
            if next_word in MEASURE_UNITS_FOLLOWING:
                valid_num_mask[i] = True
                continue

            # Se preceder ou suceder operador matemático -> NÚMERO
            if next_word in MATH_OPERATORS_ADJACENT or prev_word in MATH_OPERATORS_ADJACENT:
                valid_num_mask[i] = True
                continue

            # Se compor número com 'e' ou escalas
            if prev_word in {"e"} or next_word in {"e", "mil", "milhao", "milhão", "milhoes", "milhões"}:
                valid_num_mask[i] = True
                continue

            valid_num_mask[i] = False

    # 6. Agrupamento de números compostos preservando espaços adjacentes
    result = []
    i = 0
    while i < n:
        if not valid_num_mask[i]:
            result.append(tokens[i])
            i += 1
            continue

        # Inicia bloco numérico
        num_words = [tokens[i]]
        last_num_idx = i
        j = i + 1

        while j < n:
            if tokens[j].isspace():
                # Olha adiante para ver se o próximo token válido faz parte do número
                k = j + 1
                while k < n and tokens[k].isspace():
                    k += 1
                if k < n and (valid_num_mask[k] or tokens[k].lower() == "e"):
                    # Pode ser parte do bloco numérico
                    if tokens[k].lower() == "e":
                        # Olha mais adiante se depois do 'e' tem outro número
                        m_idx = k + 1
                        while m_idx < n and tokens[m_idx].isspace():
                            m_idx += 1
                        if m_idx < n and valid_num_mask[m_idx]:
                            num_words.append("e")
                            num_words.append(tokens[m_idx])
                            last_num_idx = m_idx
                            j = m_idx + 1
                            continue
                        else:
                            break
                    else:
                        num_words.append(tokens[k])
                        last_num_idx = k
                        j = k + 1
                        continue
                else:
                    break
            elif valid_num_mask[j]:
                num_words.append(tokens[j])
                last_num_idx = j
                j += 1
            else:
                break

        val_str = _evaluate_compound_group(num_words)
        if val_str is not None:
            result.append(val_str)
            i = last_num_idx + 1
        else:
            result.append(tokens[i])
            i += 1

    return "".join(result)
