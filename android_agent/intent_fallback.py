"""
Mapeador inteligente de intenções em linguagem natural (PT-BR) para chamadas de função do Silva.
Atua como camada de fallback ultra-rápida e robusta para garantir que todos os comandos
sejam traduzidos com precisão imediata mesmo em micro-modelos quantizados.
Suporta comandos únicos e multi-ações encadeadas ("e", "depois", "também").
"""

import ast
import re
import unicodedata
from typing import List, Optional


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

COMMAND_VERBS = {
    "abra", "abre", "abrir", "ligue", "liga", "ligar", "desligue", "desliga", "desligar",
    "toque", "toca", "tocar", "pause", "pausa", "pausar", "coloque", "coloca", "colocar",
    "bote", "bota", "botar", "defina", "define", "definir", "configure", "configura", "configurar",
    "chama", "chame", "chamar", "peça", "peca", "pede", "pedir", "envie", "envia", "enviar",
    "manda", "mande", "mandar", "lembra", "lembre", "lembrar", "anote", "anota", "anotar",
    "salve", "salva", "salvar", "pesquise", "pesquisa", "pesquisar", "busque", "busca", "buscar",
    "baixe", "baixa", "baixar", "instale", "instala", "instalar", "leia", "ler", "mostre", "mostrar",
    "veja", "ver", "qual", "quais", "quanto", "quantos", "tempo", "clima", "calcula", "calcule",
    "vibra", "vibrar", "aumenta", "aumentar", "diminui", "diminuir", "tire", "tira", "tirar",
    "grave", "grava", "gravar", "silencie", "silencia", "muta", "mutar"
}


def _protect_compound_names(text: str) -> str:
    """Protege termos compostos com conectores 'e' para evitar separação prematura de cláusulas."""
    return re.sub(r"\bAbreu\s+[eE]\s+Lima\b", "Abreu__E__Lima", text, flags=re.IGNORECASE)


def _unprotect_compound_names(text: str) -> str:
    """Restaura nomes próprios que tiveram seu conector protegido temporariamente."""
    return re.sub(r"\bAbreu__E__Lima\b", "Abreu e Lima", text, flags=re.IGNORECASE)


def _format_call(func_name: str, **kwargs) -> str:
    """
    Formata chamada de função garantindo escaping 100% seguro para ast.parse.
    Strings são representadas com repr(), números e booleanos mantêm seu formato nativo.
    """
    args = []
    for k, v in kwargs.items():
        if isinstance(v, str):
            v_clean = _unprotect_compound_names(v)
            args.append(f"{k}={repr(v_clean)}")
        else:
            args.append(f"{k}={v}")
    return f"<call>{func_name}({', '.join(args)})</call>"


ALLOWED_MATH_NAMES = {
    "sqrt", "cbrt", "sin", "cos", "tan", "asin", "acos", "atan",
    "log", "log10", "log2", "exp", "factorial", "abs", "round", "floor", "ceil",
    "pi", "e"
}


def _normalize_math_expression(raw_text: str) -> Optional[str]:
    """
    Normaliza operadores, símbolos, funções científicas e expressões em linguagem natural (PT-BR)
    para uma expressão aritmética/científica Python válida executável pelo SafeMathEvaluator.
    Retorna a expressão normalizada ou None se não for um cálculo válido.
    """
    if not raw_text:
        return None

    clean = raw_text.strip().rstrip("?!.,;:")
    lower = clean.lower()
    norm = normalize_text(lower)

    # 1. Verifica se há intenção de cálculo ou expressão matemática direta
    math_triggers = [
        "quanto e", "quanto da", "quanto fica", "calcule", "calcular",
        "calcula", "resultado de", "raiz quadrada", "raiz cubica", "raiz de",
        "fatorial", "seno", "cosseno", "tangente", "logaritmo", "log",
        "conta de", "valor de", "ao quadrado", "ao cubo", "elevado a"
    ]
    has_trigger = any(trig in norm for trig in math_triggers)
    has_direct_math = bool(re.search(r"\b\d+\s*(?:[\+\-\*\/÷×\^%]|x|vezes|dividido|mais|menos)\s*\d+\b", norm, re.IGNORECASE))
    has_math_func = any(f"{fn}(" in lower for fn in ALLOWED_MATH_NAMES)

    if not has_trigger and not has_direct_math and not has_math_func:
        return None

    s = lower

    # 2. Acréscimos e descontos de porcentagem: "X + Y%" -> "X * (1 + Y/100)" e "X - Y%" -> "X * (1 - Y/100)"
    s = re.sub(
        r"(\d+(?:[\.,]\d+)?)\s*(?:\+|\bmais\b|\bsomado\s+a\b)\s*(\d+(?:[\.,]\d+)?)\s*(?:%|por\s+cento)",
        r"\1 * (1 + \2 / 100)",
        s
    )
    s = re.sub(
        r"(\d+(?:[\.,]\d+)?)\s*(?:\-|\bmenos\b|\bsubtra[ií]do\s+de\b)\s*(\d+(?:[\.,]\d+)?)\s*(?:%|por\s+cento)",
        r"\1 * (1 - \2 / 100)",
        s
    )

    # 3. Porcentagem simples: "X% de Y" ou "X por cento de Y" -> "(X / 100) * Y"
    s = re.sub(
        r"(\d+(?:[\.,]\d+)?)\s*(?:%|por\s+cento)\s+de\s+(\d+(?:[\.,]\d+)?)",
        r"(\1 / 100) * \2",
        s
    )

    # 4. Frações: "A/B de X" -> "(A / B) * X" e "metade de X" -> "0.5 * X"
    s = re.sub(r"(\d+)\s*/\s*(\d+)\s+de\s+(\d+(?:[\.,]\d+)?)", r"(\1 / \2) * \3", s)
    s = re.sub(r"\bmetade\s+de\s+(\d+(?:[\.,]\d+)?)", r"0.5 * \1", s)

    # 5. Raiz quadrada e cúbica
    s = re.sub(r"(?:a\s+)?raiz\s+c[uú]bica\s+de\s+(\d+(?:[\.,]\d+)?|\([^\)]+\))", r"cbrt(\1)", s)
    s = re.sub(r"(?:a\s+)?raiz\s+(?:quadrada\s+)?de\s+(\d+(?:[\.,]\d+)?|\([^\)]+\))", r"sqrt(\1)", s)

    # 6. Fatorial: "X fatorial" ou "fatorial de X" ou "X!" -> "factorial(X)"
    s = re.sub(r"fatorial\s+de\s+(\d+)", r"factorial(\1)", s)
    s = re.sub(r"(\d+)\s*fatorial\b", r"factorial(\1)", s)
    s = re.sub(r"(\d+)!", r"factorial(\1)", s)

    # 7. Trigonometria (em graus por padrão)
    s = re.sub(r"seno\s+de\s+(\d+(?:[\.,]\d+)?)\s*(?:graus?|°|º)?", r"sin(\1 * pi / 180)", s)
    s = re.sub(r"cosseno\s+de\s+(\d+(?:[\.,]\d+)?)\s*(?:graus?|°|º)?", r"cos(\1 * pi / 180)", s)
    s = re.sub(r"tangente\s+de\s+(\d+(?:[\.,]\d+)?)\s*(?:graus?|°|º)?", r"tan(\1 * pi / 180)", s)

    # 8. Logaritmo
    s = re.sub(r"logaritmo\s+natural\s+de\s+(\d+(?:[\.,]\d+)?)", r"log(\1)", s)
    s = re.sub(r"\bln\s+de\s+(\d+(?:[\.,]\d+)?)", r"log(\1)", s)
    s = re.sub(r"logaritmo\s+de\s+(\d+(?:[\.,]\d+)?)", r"log10(\1)", s)
    s = re.sub(r"\blog\s+de\s+(\d+(?:[\.,]\d+)?)", r"log10(\1)", s)

    # 9. Potências e expoentes
    s = re.sub(r"\bao\s+quadrado\b", " ** 2", s)
    s = re.sub(r"\bao\s+cubo\b", " ** 3", s)
    s = re.sub(r"\belevado\s+a(?:o|\s+a)?\b", " ** ", s)

    # 10. Converter palavras numéricas em português para dígitos
    for word, digit in sorted(NUM_WORDS_PT.items(), key=lambda item: len(item[0]), reverse=True):
        s = re.sub(rf"\b{word}\b", digit, s)

    # 11. Converter operadores textuais e alternativos
    s = re.sub(r"\bmultiplicado\s+por\b", " * ", s)
    s = re.sub(r"\bvezes\b", " * ", s)
    s = re.sub(r"×", " * ", s)
    s = re.sub(r"(?<=\d|\))\s*[xX]\s*(?=\d|\()", " * ", s)
    s = re.sub(r"\b[xX]\b", " * ", s)

    s = re.sub(r"\bdividido\s+por\b", " / ", s)
    s = re.sub(r"\bdividido\b", " / ", s)
    s = re.sub(r"÷", " / ", s)

    s = re.sub(r"\bmais\b", " + ", s)
    s = re.sub(r"\bsomado\s+(?:a|com)\b", " + ", s)

    s = re.sub(r"\bmenos\b", " - ", s)
    s = re.sub(r"\bsubtra[ií]do\s+de\b", " - ", s)

    # 12. Vírgula decimal entre números para ponto
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)

    # 13. Remover palavras de preenchimento (fillers)
    filler_patterns = [
        r"(?i)\bquanto\s+[eé]\s+(?:o\s+resultado\s+de\s+)?",
        r"(?i)\bquanto\s+d[aá]\s+",
        r"(?i)\bquanto\s+fica\s+",
        r"(?i)\bcalcule\s+(?:o\s+resultado\s+de\s+|a\s+)?",
        r"(?i)\bcalcula\s+(?:o\s+resultado\s+de\s+|a\s+)?",
        r"(?i)\bcalcular\s+",
        r"(?i)\bresultado\s+de\s+",
        r"(?i)\bo\s+resultado\s+de\s+",
        r"(?i)\bconta\s+de\s+",
        r"(?i)\bqual\s+[eé]\s+(?:o\s+resultado\s+de\s+|o\s+valor\s+de\s+)?",
        r"(?i)\bqual\s+o\s+resultado\s+de\s+",
        r"(?i)\bme\s+diga\s+",
        r"(?i)\bpor\s+favor\b",
        r"(?i)\bpfv\b",
        r"[?!]+$"
    ]
    for pat in filler_patterns:
        s = re.sub(pat, " ", s)

    # Substitui potências '^' por '**'
    s = s.replace("^", " ** ")

    # Normaliza múltiplos espaços
    s = re.sub(r"\s+", " ", s).strip()

    # 14. Validação estrita via AST e Whitelist
    if not re.match(r"^[0-9a-zA-Z_\+\-\*\/\(\)\.\s%,]+$", s):
        return None

    try:
        parsed = ast.parse(s, mode="eval")
        # Garante que todo identificador pertença estritamente à whitelist matemática
        all_names = {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
        if not all_names.issubset(ALLOWED_MATH_NAMES):
            return None

        # Deve conter pelo menos uma operação aritmética, chamada de função ou constante
        if isinstance(parsed.body, (ast.BinOp, ast.UnaryOp, ast.Call)):
            return s
    except Exception:
        return None

    return None


def normalize_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e remove pontuação excessiva."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    text_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return text_clean.strip()


def _clean_ride_destination(raw_dest: str) -> str:
    """
    Remove prefixos conversacionais e sufixos de cortesia de um destino de corrida.
    Exemplos:
      "mim ir ao Shopping Recife" -> "Shopping Recife"
      "eu ir pro aeroporto pfv" -> "aeroporto"
      "ir na casa da minha tia" -> "casa da minha tia"
    """
    if not raw_dest:
        return ""
    text = str(raw_dest).strip()

    # 1. Sufixos de cortesia e ruídos no final
    suffix_pat = r"(?i)\s+(?:por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|de\s+uber|de\s+99|no\s+uber|na\s+99|pelo\s+uber|pela\s+99|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos conversacionais no início (repetidos até limpar completamente)
    prefix_patterns = [
        r"(?i)^(?:me\s+levar|me\s+leva|me\s+leve|levar|leva|leve|chegar|voltar|ir)\b\s*",
        r"(?i)^(?:para|pra|pro|pras|pros)\b\s*",
        r"(?i)^p/\s*",
        r"(?i)^(?:mim|eu|gente|nós|nos)\b\s*",
        r"(?i)^(?:ao|aos|à|às|no|na|nos|nas|em|até|ate)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
    ]

    for _ in range(10):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    text = re.sub(suffix_pat, "", text).strip()
    text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
    return text.strip()


def _clean_food_query(raw_query: str) -> str:
    """
    Remove prefixos de comando e sufixos de aplicativo/cortesia de uma busca de comida.
    Exemplos:
      "peça um hamburguer no ifood" -> "hamburguer"
      "silva quero pedir uma pizza de calabresa no ifood pfv" -> "pizza de calabresa"
      "busca acai na 99" -> "acai"
    """
    if not raw_query:
        return ""
    text = str(raw_query).strip()

    # 1. Sufixos de app e cortesia no final (repetidos até limpar)
    suffix_pat = r"(?i)\s+(?:no\s+ifood|pelo\s+ifood|na\s+99|no\s+99|no\s+99\s*food|pelo\s+99|pelo\s+99\s*food|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos de comando no início da frase (repetidos até limpar)
    prefix_patterns = [
        r"(?i)^(?:silva|ei|oi)\b\s*",
        r"(?i)^(?:abre\s+o\s+ifood\s+e\s+pede|abre\s+o\s+ifood\s+e\s+peça|abre\s+o\s+ifood\s+e\s+peca|abre\s+o\s+ifood\s+e\s+pedir)\b\s*",
        r"(?i)^(?:abre\s+o\s+99\s+e\s+pede|abre\s+a\s+99\s+e\s+pede)\b\s*",
        r"(?i)^(?:quero\s+pedir|quero|gostaria\s+de\s+pedir|gostaria\s+de|me\s+vê|me\s+ve)\b\s*",
        r"(?i)^(?:peça|peca|pede|pedir|compra|comprar|compre|busca|busque|buscar|procura|procure|procurar|acha|achar|pesquisa|pesquisar)\b\s*",
        r"(?i)^(?:delivery\s+de|delivery)\b\s*",
        r"(?i)^(?:um|uma|uns|umas)\b\s*",
        r"(?i)^(?:comida|lanche)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
        r"(?i)^(?:de)\b\s*",
    ]

    for _ in range(10):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    text = re.sub(suffix_pat, "", text).strip()
    text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
    return text.strip()


def _clean_install_app_name(raw_name: str) -> str:
    """Limpa o nome do aplicativo removendo artigos, pronomes e termos de loja/cortesia."""
    if not raw_name:
        return ""
    text = str(raw_name).strip()

    suffix_pat = r"(?i)\s+(?:no\s+google\s+play|na\s+google\s+play|no\s+play\s*store|na\s+play\s*store|no\s+playstore|na\s+playstore|pelo\s+google\s+play|pela\s+play\s*store|pelo\s+play\s*store|google\s+play|play\s*store|playstore|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    prefix_patterns = [
        r"(?i)^(?:silva|ei|oi)\b\s*",
        r"(?i)^(?:abre\s+a\s+play\s*store\s+e\s+(?:baixa|instala|procura|pesquisa|busca))\b\s*",
        r"(?i)^(?:abre\s+o\s+google\s+play\s+e\s+(?:baixa|instala|procura|pesquisa|busca))\b\s*",
        r"(?i)^(?:instalar|instala|instale|baixar|baixa|baixe|download\s+do|download\s+de|download)\b\s*",
        r"(?i)^(?:pesquisar|pesquisa|pesquise|buscar|busca|busque|procurar|procura|procure)\b\s*",
        r"(?i)^(?:o\s+aplicativo|aplicativo|o\s+app|app|o\s+jogo|jogo)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
        r"(?i)^(?:do|da|dos|das|de)\b\s*",
    ]

    for _ in range(10):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    text = re.sub(suffix_pat, "", text).strip()
    text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
    return text.strip()


def _clean_weather_location(raw_loc: str) -> str:
    """Limpa e normaliza nome de localidade removendo palavras de tempo, fillers e pontuação."""
    s = _unprotect_compound_names(raw_loc.strip())
    if not s:
        return ""

    time_noise_tokens = [
        r"depois de amanh[aã]",
        r"fim de semana",
        r"de madrugada",
        r"de manh[aã]",
        r"pela manh[aã]",
        r"[aà] tarde",
        r"[aà] noite",
        r"por favor",
        r"hoje", r"hj", r"amanh[aã]", r"amn",
        r"segunda", r"ter[cç]a", r"quarta", r"quinta", r"sexta", r"s[aá]bado", r"domingo",
        r"fds", r"manh[aã]", r"tarde", r"noite", r"madrugada",
        r"pfvr?", r"silva", r"agora", r"agr",
        r"\d{1,2}h(?:\d{2})?", r"\d{1,2}:\d{2}",
    ]

    changed = True
    while changed:
        changed = False
        s = re.sub(r"^[?!.,;\s]+|[?!.,;\s]+$", "", s).strip()
        for pat in time_noise_tokens:
            m_end = re.search(r"(?:\s+(?:no|na|em|de|para|pra))?\s+" + pat + r"[?!.,;\s]*$", s, re.IGNORECASE)
            if m_end:
                s = s[:m_end.start()].strip()
                changed = True
            m_start = re.search(r"^[?!.,;\s]*" + pat + r"(?:\s+(?:no|na|em|de|para|pra))?\s+", s, re.IGNORECASE)
            if m_start:
                s = s[m_start.end():].strip()
                changed = True

    s = re.sub(r"^[?!.,;\s]+|[?!.,;\s]+$", "", s).strip()
    s = re.sub(r"^(?:em|para|pra|no|na|de)\s+", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"\s+(?:em|para|pra|no|na|de)$", "", s, flags=re.IGNORECASE).strip()

    if not s:
        return ""

    invalid_words = {
        "hoje", "amanha", "amanhã", "depois", "aqui", "minha cidade",
        "mim", "graus", "tempo", "chuva", "sol", "calor", "frio", "clima", "previsao", "previsão"
    }
    if s.lower() in invalid_words:
        return ""

    # Preserva cidade e estado separados por vírgula com capitalização limpa
    parts = [p.strip() for p in s.split(",") if p.strip()]
    cleaned_parts = []
    for part in parts:
        if len(part) == 2 and part.isalpha():
            cleaned_parts.append(part.upper())
        else:
            words = part.split()
            cap_words = []
            for i, w in enumerate(words):
                w_lower = w.lower()
                if i > 0 and w_lower in {"de", "da", "do", "das", "dos", "e"}:
                    cap_words.append(w_lower)
                else:
                    cap_words.append(w.capitalize())
            cleaned_parts.append(" ".join(cap_words))

    return ", ".join(cleaned_parts)


def parse_single_intent(raw_cmd: str) -> Optional[str]:
    """Tenta identificar uma intenção específica e retornar uma tag <call>...</call>."""
    if not raw_cmd:
        return None

    cmd = normalize_text(raw_cmd)
    if not cmd:
        return None

    # Anti-pergunta conceitual/enciclopédica (deixa para o LLM responder semântico)
    conceptual_prefixes = (
        "o que e ", "o que sao ", "o que significa ", "qual a diferenca ",
        "quem foi ", "quem e ", "me explica ", "me explique ", "explique o que ", "explique "
    )
    if cmd.startswith(conceptual_prefixes):
        is_capabilities_query = any(h in cmd for h in [
            "o que voce", "o que vc", "suas funco", "suas capacida", "seus comando"
        ])
        if not is_capabilities_query:
            operational_verbs = ("pesquise", "pesquisa", "busque", "busca", "ligue", "liga", "abra", "abre", "baixe", "baixa", "instale", "instala", "toque", "toca")
            if not any(v in cmd for v in operational_verbs):
                return None

    # 0. Pedido de Ajuda / Lista de Capacidades (list_capabilities)
    cmd_clean = re.sub(r"(?i)^(?:silva,?\s*|ei,?\s*|oi,?\s*|ola,?\s*)?", "", cmd).strip().rstrip("?!.,;:")
    cmd_clean = re.sub(r"(?i)\s+(?:por\s+favor|pra\s+mim|pfv|pfvr|agora|agr|aí|ai)$", "", cmd_clean).strip()

    help_phrases = [
        "o que voce faz", "o que vc faz", "o que voce pode fazer", "o que vc pode fazer",
        "o que voce sabe fazer", "o que vc sabe fazer", "quais suas funcoes", "quais suas capacidades",
        "suas funcoes", "suas capacidades", "lista de comandos", "seus comandos", "quais comandos",
        "o que posso pedir", "o que você pode fazer", "quais são suas funções", "quais sao suas funcoes",
        "o que você faz", "quais suas funções", "suas funções", "o que você sabe fazer"
    ]
    if any(p in cmd_clean for p in help_phrases) or cmd_clean in ["ajuda", "help", "menu", "comandos", "funcoes", "funções"]:
        return _format_call("list_capabilities")

    # 0.1 Calculadora matemática com normalização completa (PT-BR)
    if not any(w in cmd for w in ["volume", "brilho", "timer", "alarme", "lembrete"]):
        math_expr = _normalize_math_expression(raw_cmd)
        if math_expr:
            return _format_call("calculate", expression=math_expr)

    # 1. Lanterna (set_torch)
    if "lanterna" in cmd or "torch" in cmd or "flash" in cmd:
        if any(neg in cmd for neg in ["deslig", "desativ", "apag", "off", "fecha", "cort", "tir"]):
            return _format_call("set_torch", state=False)
        return _format_call("set_torch", state=True)

    # 2. Bateria (get_battery)
    if any(w in cmd for w in ["bateria", "carga", "porcentagem", "nivel de bateria", "quanta bateria", "status da bateria"]):
        return _format_call("get_battery")

    # 2.1 Redes Wi-Fi disponíveis nas proximidades (scan_wifi)
    # Garante que perguntas sobre senhas salvas não colidam (vão para recall_note)
    is_wifi_term = any(w in cmd for w in ["wifi", "wifis", "wi-fi", "wi-fis", "redes sem fio", "rede sem fio"])
    is_scan_action = any(w in cmd for w in [
        "disponiveis", "disponivel", "por perto", "proximas", "proxima", "proximo",
        "redes", "lista", "listar", "escanear", "escaneie", "buscar", "busca",
        "procurar", "procura", "encontrar", "quais", "ver", "mostre", "mostrar", "tem"
    ])
    has_pwd_term = any(w in cmd for w in ["senha", "password", "pin", "chave de acesso"])
    if is_wifi_term and is_scan_action and not has_pwd_term:
        return _format_call("scan_wifi")
    elif any(p in cmd for p in ["scan wifi", "escanear wifi", "escanear redes wifi", "buscar wifi", "procurar wifi", "wifis por perto", "wifis proximas"]) and not has_pwd_term:
        return _format_call("scan_wifi")

    # 3. Vibração (vibrate)
    if any(w in cmd for w in ["vibra", "vibrar", "vibracao", "treme", "tremer"]):
        m = re.search(r"(\d+)\s*(?:ms|milissegundos|segundos|s)?", cmd)
        duration = 500
        if m:
            val = int(m.group(1))
            if "segundo" in cmd or " s" in cmd:
                duration = val * 1000
            else:
                duration = val
        return _format_call("vibrate", duration_ms=duration)

    # 4. Não Perturbe / Silencioso (set_dnd)
    if any(w in cmd for w in ["perturbe", "pertube", "dnd", "silencioso", "silenciar", "mutar", "mudo"]):
        if any(neg in cmd for neg in ["desativ", "deslig", "tir", "sair", "off", "cancel", "voltar"]):
            return _format_call("set_dnd", state=False)
        return _format_call("set_dnd", state=True)

    # 5. Captura de Tela / Print (take_screenshot)
    if any(w in cmd for w in ["print", "screenshot", "captura de tela", "capturar tela", "foto da tela"]):
        return _format_call("take_screenshot")

    # 6. Câmera / Foto (take_photo)
    if any(w in cmd for w in ["foto", "selfie", "retrato", "fotografa"]) and not any(s in cmd for s in ["tela", "screen", "print", "video", "gravar", "filmar"]):
        if any(w in cmd for w in ["frontal", "selfie", "frente", "minha foto", "foto minha"]):
            return _format_call("take_photo", camera_id=1)
        return _format_call("take_photo", camera_id=0)

    # 6.0 Controle de Mídia (media_control)
    # Não conflitar com volume, brilho, alarme ou timer
    if not any(w in cmd for w in ["volume", "brilho", "alarme", "timer"]):
        clean_media_cmd = re.sub(r"(?i)^(?:silva,?\s*)?", "", cmd).strip()
        clean_media_cmd = re.sub(r"(?i)\s+(?:por\s+favor|pra\s+mim|agora|aí|ai)$", "", clean_media_cmd).strip()

        # A) Next / Próxima
        if any(w in clean_media_cmd for w in [
            "proxima musica", "proxima faixa", "pula a musica", "pula essa musica",
            "pular musica", "pula musica", "passa a musica", "passar musica", "proxima cancao",
            "avancar musica", "avanca a musica", "next track", "next song"
        ]) or clean_media_cmd in ["proxima", "proximo", "next", "pula", "passa"]:
            return _format_call("media_control", action="next")

        # B) Previous / Anterior
        if any(w in clean_media_cmd for w in [
            "volta a musica", "voltar a musica", "voltar musica", "volta musica",
            "musica anterior", "faixa anterior", "cancao anterior", "retrocede a musica",
            "previous track", "previous song"
        ]) or clean_media_cmd in ["anterior", "volta", "voltar", "previous"]:
            return _format_call("media_control", action="previous")

        # C) Play / Despausa / Continuar
        if any(w in clean_media_cmd for w in [
            "despausa", "despausar", "continua a musica", "continuar a musica",
            "retoma a musica", "retomar a musica", "retoma o video", "retomar o video",
            "toca a musica", "tocar a musica", "reproduz a musica", "reproduzir a musica",
            "da o play", "dar o play", "dar play", "da play"
        ]) or clean_media_cmd in ["play", "despausa", "despausar", "tocar", "continuar", "retomar"]:
            return _format_call("media_control", action="play")

        # D) Pause / Parar
        if any(w in clean_media_cmd for w in [
            "pausa a musica", "pausar a musica", "pausa o video", "pausar o video",
            "para a musica", "parar a musica", "interrompe a musica", "pausa reproducao",
            "pausar reproducao"
        ]) or clean_media_cmd in ["pause", "pausa", "pausar", "stop"]:
            return _format_call("media_control", action="pause")

    # 6.1 Gravação de Vídeo (record_video)
    if any(w in cmd for w in ["video", "gravar", "grave", "grava", "filmar", "filma", "filme"]) and not any(w in cmd for w in ["youtube", "tiktok", "pausa", "pausar", "retoma", "retomar", "continua", "continuar", "toca", "tocar", "play"]):
        m_dur = re.search(r"(\d+)\s*(?:segundos?|s|minutos?|min)?", cmd)
        duration = 10
        if m_dur:
            val = int(m_dur.group(1))
            if "minuto" in cmd or "min" in cmd:
                duration = val * 60
            else:
                duration = val
        duration = max(3, min(duration, 120))
        camera_id = 1 if any(w in cmd for w in ["frontal", "selfie", "frente", "me film", "me grav", "minha cara"]) else 0
        return _format_call("record_video", duration=duration, camera_id=camera_id)

    # 6.2 Corrida / Transporte (request_ride)
    if not (cmd.startswith(("abre ", "abra ", "abrir ")) and not any(p in cmd for p in ["para", "pra", "pro", "ate", "até", "p/"])):
        ride_verbs = ["peca", "pede", "pedir", "chama", "chamar", "solicita", "solicitar", "solicite", "peco", "quero", "preciso", "consegue"]
        has_ride_verb = any(v in cmd for v in ride_verbs)
        is_uber = "uber" in cmd
        is_99 = "99" in cmd
        ride_triggers = [
            "uber", "corrida", "chama um carro", "chamar um carro", "chama carro", "chamar carro",
            "pede um carro", "pedir um carro", "pede carro", "pedir carro", "chama corrida",
            "chamar corrida", "pede corrida", "pedir corrida", "solicita um carro", "solicitar um carro",
            "solicita carro", "solicitar carro"
        ]
        is_99_ride = (is_99 and (any(w in cmd for w in ["carro", "corrida", "chama", "pede", "pedir", "peca", "solicita", "solicitar", "motorista", "viagem", "taxi", "para", "pra", "pro", "ate"]) or has_ride_verb) and not any(f in cmd for f in ["food", "comida", "lanche", "pizza", "almoco", "almoço", "acai", "açaí", "sushi", "hamburguer", "pastel"]))
        if any(t in cmd for t in ride_triggers) or is_99_ride or ((is_uber or is_99) and has_ride_verb):
            app = "99" if is_99 else "uber"
            dest = ""
            m_dest = re.search(r"(?:para|pra|pro|ate|até|p/)\s+([^\n\r,\.;]+)", raw_cmd, re.IGNORECASE)
            if m_dest:
                dest = _clean_ride_destination(m_dest.group(1))
            if not dest:
                m_alt = re.search(r"(?:uber|99|carro|corrida|taxi)\s+([^\n\r,\.;]+)", raw_cmd, re.IGNORECASE)
                if m_alt:
                    dest = _clean_ride_destination(m_alt.group(1))
            if not dest:
                cleaned = re.sub(r"(?i)^(?:silva,?\s*)?(?:peça|peca|pede|pedir|chama|chamar|solicita|solicitar|quero|preciso\s+de)?\s*(?:um\s+|uma\s+)?(?:uber|99|carro|corrida|motorista|taxi)?\s*", "", raw_cmd)
                dest = _clean_ride_destination(cleaned)
            if not dest:
                dest = "destino"
            return _format_call("request_ride", destination=dest, app=app)

    # 6.3 Delivery / Pedir Comida (order_food)
    if not (cmd.startswith(("abre ", "abra ", "abrir ")) and not any(f in cmd for f in ["pizza", "lanche", "hamburguer", "hambúrguer", "comida", "sushi", "acai", "açaí", "pastel"])):
        food_triggers = ["ifood", "99 food", "99food", "pedir comida", "pede comida", "peca comida", "peça comida", "pedir lanche", "pede lanche", "peca lanche", "peça lanche", "busca comida", "buscar comida", "delivery"]
        food_items = ["pizza", "hamburguer", "hambúrguer", "lanche", "comida", "sushi", "acai", "açaí", "marmita", "almoco", "almoço", "jantar", "pastel", "salgado", "doce", "sobremesa", "refeicao", "refeição", "churrasco", "poke", "tapioca"]
        has_food_item = any(f in cmd for f in food_items)
        food_verbs = ["pede", "pedir", "peca", "peça", "quero", "compra", "comprar", "compre", "busca", "buscar", "busque", "procura", "procurar", "procure", "acha", "achar", "me ve", "me vê"]
        has_food_verb = any(v in cmd for v in food_verbs)
        is_ifood_or_99food = "ifood" in cmd or "99 food" in cmd or "99food" in cmd
        is_food_query = (has_food_item and has_food_verb) or (has_food_item and ("99" in cmd or "ifood" in cmd))

        if any(t in cmd for t in food_triggers) or is_food_query or is_ifood_or_99food:
            app = "99" if ("99" in cmd and "ifood" not in cmd) else "ifood"
            query = _clean_food_query(raw_cmd)
            if not query:
                query = "comida"
            return _format_call("order_food", query=query, app=app)

    # 6.5 Instalação de Aplicativos / Play Store (install_app)
    # Não conflitar com volume, brilho, alarme ou lanterna
    if not any(w in cmd for w in ["volume", "brilho", "alarme", "timer", "lanterna", "camera", "foto"]):
        has_store_kw = any(k in cmd for k in ["play store", "playstore", "google play"])
        has_install_verb = any(v in cmd for v in ["baixa", "baixar", "baixe", "instala", "instalar", "instale", "download"])
        is_only_open_store = cmd in [
            "abre a play store", "abre o play store", "abre a playstore", "abre o google play",
            "abrir play store", "abrir playstore", "abrir google play", "inicia a play store",
            "inicia o play store", "inicia a playstore", "inicia o google play"
        ]

        if (has_store_kw or has_install_verb) and not is_only_open_store:
            clean_app = _clean_install_app_name(raw_cmd)
            if clean_app:
                return _format_call("install_app", app_name=clean_app)

    # 7. Abrir Aplicativo (open_app)
    m_open = re.search(r"(?:abre|abra|abrir|inicia|inicie|iniciar|roda|rode|rodar|executa|execute|executar)\s+(?:o|a)?\s*([a-zA-Z0-9_\-\s]+)", cmd)
    if m_open and not any(w in cmd for w in ["lanterna", "camera", "foto", "timer", "alarme", "print", "screenshot", "tela"]):
        app_name = m_open.group(1).strip()
        # Remove palavras parasitas no final
        app_name = re.sub(r"\s+(?:pra mim|por favor|agora|rapido)$", "", app_name).strip()
        if app_name:
            return _format_call("open_app", app_name=app_name)

    # 7. Ligação telefônica (make_call)
    m_call = re.search(r"(?:liga|ligar|disca|discar|chama|chamar|telefone|telefonar)\s+(?:para\s+o|para\s+a|para|pro|pra|a)?\s*([^\n\r,\.;]+)", raw_cmd, re.IGNORECASE)
    if m_call and not any(w in cmd for w in ["lanterna", "alarme", "som", "brilho"]):
        target = m_call.group(1).strip()
        target = re.sub(r"(?i)\s+(?:pra mim|por favor|agora|rapido)$", "", target).strip()
        if target:
            return _format_call("make_call", number=target)

    # 8. Envio de SMS (send_sms)
    m_sms = re.search(
        r"(?:envia|enviar|manda|mandar|escreve|escrever)\s+(?:um\s+)?(?:sms|mensagem\s+de\s+texto|torpedo)\s+(?:para|pro|pra)?\s*([a-zA-Z0-9_\+\s]+?)\s+(?:falando|dizendo|com a mensagem|que|de)\s+(.+)",
        raw_cmd,
        re.IGNORECASE
    )
    if m_sms:
        to_target = m_sms.group(1).strip()
        msg_body = m_sms.group(2).strip()
        return _format_call("send_sms", number=to_target, message=msg_body)

    # 9. Leitura de SMS (get_last_sms)
    is_sms_target = bool(re.search(r"\b(?:sms|mensagens?\s+de\s+texto|torpedos?|caixa\s+de\s+entrada|mensagens?)\b", cmd))
    is_sms_action = bool(re.search(r"\b(?:ler|leia|mostrar|mostre|ver|veja|listar|liste|quais|qual|recebi|recebido|recebidos|recebidas|chegou|chegaram|ultim[oa]s?|nov[oa]s?|recentes?)\b", cmd))

    if (is_sms_target and is_sms_action) or any(w in cmd for w in ["ler sms", "leia sms", "ultimos sms", "ultimo sms", "mensagens recentes", "ver sms", "minhas mensagens", "ler mensagens", "caixa de entrada"]):
        # Garante que não é comando de envio
        if not any(v in cmd for v in ["enviar", "envia ", "mandar", "manda ", "escrever", "escreve "]):
            m_num = re.search(r"\b(\d+)\s*(?:ultim[oa]s?|sms|mensagens?|torpedos?)\b", cmd) or re.search(r"(?:ultim[oa]s?|ler|mostrar|ver)\s+(\d+)\b", cmd)
            if m_num:
                limit = max(1, min(int(m_num.group(1)), 20))
            elif re.search(r"\bqual\s+(?:sms|mensagem)\s+recebi\b", cmd):
                limit = 3
            elif any(w in cmd for w in ["ultimo sms", "ultima mensagem", "ultimo torpedo", "o ultimo", "a ultima"]):
                limit = 1
            else:
                limit = 5
            return _format_call("get_last_sms", limit=limit)

    # 10. Localização / GPS
    if any(w in cmd for w in ["ultima localizacao", "última localização", "ultimo gps", "onde estive", "onde eu estava", "posicao anterior", "localizacao anterior"]):
        return _format_call("get_last_location")

    if any(w in cmd for w in ["gps", "localizacao"]):
        if any(neg in cmd for neg in ["desativ", "deslig", "desliga", "tirar", "sair", "off", "cancel"]):
            return _format_call("set_location_state", state=False)
        if any(pos in cmd for pos in ["ativ", "ligar", "liga ", "habilita", "habilitar", "on"]):
            return _format_call("set_location_state", state=True)

    if any(w in cmd for w in ["localizacao", "onde estou", "onde eu estou", "gps", "coordenadas", "minha posicao", "minha localizacao"]):
        return _format_call("get_location")

    # 11. Contar Piada (tell_joke)
    if any(w in cmd for w in ["piada", "engracado", "conta uma piada", "me faz rir"]):
        return _format_call("tell_joke")

    # 12. Área de transferência (get_clipboard / set_clipboard)
    if "clipboard" in cmd or "area de transferencia" in cmd or "o que copiei" in cmd or "copiado" in cmd:
        # Prioriza consulta se contiver palavras interrogativas/de leitura
        if any(q in cmd for q in ["o que", "qual", "ler", "le ", "ver", "mostra", "tem", "copiado", "conteudo", "consulte", "consultar"]):
            return _format_call("get_clipboard")
        # Verifica se há verbo de escrita explícito
        if any(w in cmd for w in ["copia ", "copie ", "salva ", "salve ", "coloca ", "coloque ", "define ", "definir "]) or cmd.startswith(("copia", "copie", "salva", "salve", "coloca", "coloque", "define", "definir")):
            m_clip = re.search(r"(?:copia|copie|salva|salve|coloca|coloque|define|definir)\s+(?:no\s+clipboard|na\s+area\s+de\s+transferencia|o\s+texto)?\s*(.+)", raw_cmd, re.IGNORECASE)
            text_val = m_clip.group(1).strip() if m_clip else ""
            text_val = re.sub(r"(?i)^(?:no\s+clipboard|na\s+area\s+de\s+transferencia|o\s+texto)\s*", "", text_val).strip()
            text_val = re.sub(r"(?i)\s+(?:no\s+clipboard|na\s+area\s+de\s+transferencia|para\s+o\s+clipboard)$", "", text_val).strip()
            if text_val:
                return _format_call("set_clipboard", text=text_val)
        return _format_call("get_clipboard")

    # 13. Alarme (set_alarm / cancel_alarm)
    if any(w in cmd for w in ["alarme", "despertador", "desperta", "despertar", "me acorda", "acordar"]):
        if any(w in cmd for w in ["cancela", "cancelar", "desativa", "desativar", "apaga", "apagar", "remover", "remove", "desliga", "desligar"]):
            m_time = re.search(r"(\d{1,2}(?::\d{2})?)", cmd)
            t_str = m_time.group(1) if m_time else ""
            if t_str and ":" not in t_str:
                t_str = f"{int(t_str):02d}:00"
            return _format_call("cancel_alarm", time=t_str, day="", label="")
        else:
            m_time = re.search(r"(\d{1,2}(?::\d{2})?)", cmd)
            t_str = m_time.group(1) if m_time else "07:00"
            if ":" not in t_str:
                t_str = f"{int(t_str):02d}:00"
            return _format_call("set_alarm", time=t_str, label="Alarme", days=[])

    # 14. Timer / Cronômetro (set_timer)
    if any(w in cmd for w in ["timer", "temporizador", "cronometro", "cronômetro"]):
        m_min = re.search(r"(\d+)\s*(?:minutos?|min)?", cmd)
        minutes = int(m_min.group(1)) if m_min else 5
        return _format_call("set_timer", minutes=minutes, label="Timer")

    # 14.1 Agendamentos na Agenda / Calendário (schedule_event)
    triggers_sched = ["agenda", "agende", "agendar", "marca", "marque", "marcar", "compromisso", "reuniao", "lembrete"]
    if any(t in cmd for t in triggers_sched) and not (cmd.startswith(("abre", "abra", "abrir")) and any(a in cmd for a in ["agenda", "calendario"])):
        # 1. Extrair Time
        time_val = ""
        time_match = re.search(r"\b(?:[aàá]s|para\s+[aàá]s|pras|pra\s+[aàá]s)?\s*(\d{1,2})(?:[:h](\d{2})?|h)\b", raw_cmd, re.IGNORECASE)
        time_span = None
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            if 0 <= h <= 23 and 0 <= m <= 59:
                time_val = f"{h:02d}:{m:02d}"
                time_span = time_match.span()

        # 2. Extrair Date
        date_val = ""
        date_span = None
        m_ext = re.search(r"\b(?:no\s+dia|dia)?\s*(\d{1,2}\s+de\s+[a-zçA-ZÀ-ÿ]+(?:\s+de\s+\d{2,4})?)(?:\s+deste\s+ano)?\b", raw_cmd, re.IGNORECASE)
        if m_ext:
            date_val = m_ext.group(1).strip()
            date_span = m_ext.span()
        else:
            m_rel = re.search(r"\b(depois\s+de\s+amanh[aã]|amanh[aã]|hoje|segunda(?:-feira)?|ter[cç]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|s[aá]bado|domingo)\b", raw_cmd, re.IGNORECASE)
            if m_rel:
                date_val = m_rel.group(1).strip()
                date_span = m_rel.span()
            else:
                m_num = re.search(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{1,2}-\d{1,2})\b", raw_cmd)
                if m_num:
                    date_val = m_num.group(1).strip()
                    date_span = m_num.span()

        # 3. Extrair Title
        title_val = ""
        m_quotes = re.search(r'["\']([^"\']+)["\']', raw_cmd)
        if m_quotes:
            title_val = m_quotes.group(1).strip()
        else:
            cleaned = raw_cmd
            if time_span:
                cleaned = cleaned[:time_span[0]] + " " + cleaned[time_span[1]:]
            if date_span:
                cleaned = cleaned[:date_span[0]] + " " + cleaned[date_span[1]:]

            cleaned = re.sub(r"(?i)^(?:silva,?\s*)?", "", cleaned).strip()
            m_chamado = re.search(r"(?i)\b(?:chamado|chamada|com\s+o\s+nome|com\s+o\s+t[ií]tulo)\s+(.+)", cleaned)
            if m_chamado:
                title_val = m_chamado.group(1).strip()
            else:
                cleaned = re.sub(
                    r"(?i)^(?:agende|agenda|agendar|marque|marca|marcar|coloque|coloca|colocar|criar|cria|crie)\s+(?:um\s+compromisso(?:\s+de|\s+sobre|\s+para)?\s*|um\s+|uma\s+)?",
                    "",
                    cleaned
                ).strip()
                cleaned = re.sub(r"(?i)^(?:compromisso|lembrete)\s+(?:de\s+|sobre\s+|para\s+)?", "", cleaned).strip()
                cleaned = re.sub(r"(?i)\s+(?:por\s+favor|pra\s+mim|agora)$", "", cleaned).strip()
                cleaned = re.sub(r"(?i)\s+(?:na|no|em|de|para|pra)$", "", cleaned).strip()
                cleaned = re.sub(r'[?!.,;:]+$', '', cleaned).strip()
                title_val = cleaned or "Compromisso"

        return _format_call("schedule_event", title=title_val, date=date_val, time=time_val)

    # 15. Memória (remember_note / recall_note)
    if any(w in cmd for w in ["lembra que", "lembrar que", "anota que", "salva que", "guarda que"]):
        content = re.sub(r"(?i)^(?:silva,?\s*)?(?:lembra|lembrar|anota|anotar|salva|salvar|guarda|guardar)\s+que\s+", "", raw_cmd).strip()
        if "=" in content:
            k, v = content.split("=", 1)
        elif re.search(r"\s+[eé]\s*:\s*", content, re.IGNORECASE):
            parts = re.split(r"\s+[eé]\s*:\s*", content, maxsplit=1, flags=re.IGNORECASE)
            k, v = parts[0], parts[1]
        elif re.search(r"\s+[eé]\s+", content, re.IGNORECASE):
            parts = re.split(r"\s+[eé]\s+", content, maxsplit=1, flags=re.IGNORECASE)
            k, v = parts[0], parts[1]
        elif ":" in content:
            parts = content.split(":", 1)
            k, v = parts[0], parts[1]
        else:
            k, v = "nota", content
        return _format_call("remember_note", key=k.strip(), value=v.strip())

    if any(w in cmd for w in ["o que voce lembra", "qual a senha", "onde guardei", "lembra de", "lembra do", "lembra da"]) or (
        any(w in cmd for w in ["qual o", "qual a"]) and not any(w in cmd for w in ["bateria", "clima", "tempo", "previsao", "temperatura", "localizacao", "hora", "clipboard", "foto", "print"])
    ):
        q = re.sub(r"(?i)^(?:silva,?\s*)?(?:qual|onde|o que|lembra)\s+(?:voce\s+lembra\s+)?(?:de|do|da|o|a)?\s*", "", raw_cmd).strip().rstrip("?")
        return _format_call("recall_note", query=q)

    # 16. Notificações (get_notifications)
    if any(w in cmd for w in ["notificacoes", "notificacao", "notificacoes do"]):
        m_app = re.search(r"(?:do|da|de)\s+([a-zA-Z0-9_\-]+)", cmd)
        app_filter = m_app.group(1).strip() if m_app else ""
        if app_filter in ["celular", "meu", "sistema"]:
            app_filter = ""
        return _format_call("get_notifications", app=app_filter)

    # 17. Volume (set_volume)
    if "volume" in cmd:
        m_vol = re.search(r"(\d+)\s*(?:%|porcento)?", cmd)
        level = int(m_vol.group(1)) if m_vol else 50
        return _format_call("set_volume", stream="music", level=level)

    # 18. Brilho (set_brightness)
    if "brilho" in cmd:
        m_bri = re.search(r"(\d+)\s*(?:%|porcento)?", cmd)
        level = int(m_bri.group(1)) if m_bri else 50
        return _format_call("set_brightness", level=level)

    # 19. Calculadora (calculate)
    math_expr = _normalize_math_expression(raw_cmd)
    if math_expr:
        return _format_call("calculate", expression=math_expr)

    # 20. Previsão do tempo / Clima (get_weather)
    if any(w in cmd for w in ["clima", "previsao", "tempo", "chover", "chuva", "temperatura"]) and not any(w in cmd for w in ["no google", "pesquisa no google"]):
        day = "hoje"
        if "depois de amanha" in cmd or "depois de amanhã" in cmd:
            day = "depois de amanhã"
        elif "amanha" in cmd or "amanhã" in cmd:
            day = "amanhã"
        else:
            for wd in ["segunda", "terca", "terça", "quarta", "quinta", "sexta", "sabado", "sábado", "domingo"]:
                if wd in cmd:
                    day = wd
                    break

        time_val = ""
        if "noite" in cmd:
            time_val = "noite"
        elif "tarde" in cmd:
            time_val = "tarde"
        elif "madrugada" in cmd:
            time_val = "madrugada"
        elif re.search(r"\bde manh[aã]\b|\bpela manh[aã]\b|\bmanh[aã]\b", cmd) and not re.search(r"\bamanh[aã]\b", cmd):
            time_val = "manhã"
        else:
            m_t = re.search(r"(\d{1,2}(?::\d{2}|h\d{0,2})?)", cmd)
            if m_t and not any(c in m_t.group(1) for c in ["graus", "º", "°"]):
                time_val = m_t.group(1)

        loc = ""
        pattern = r"\b(?:em|para|pra|no|na|de\s+(?!chuva\b|tempo\b|clima\b))\s*([a-zA-ZÀ-ÿ0-9\s,\-_]+)"
        matches = re.findall(pattern, raw_cmd, re.IGNORECASE)
        for m in reversed(matches):
            c = _clean_weather_location(m)
            if c:
                loc = c
                break

        return _format_call("get_weather", day=day, time=time_val, location=loc)

    # 21. Pesquisa no Google (search_google)
    if any(w in cmd for w in ["pesquisa", "pesquise", "busca", "busque", "procura", "procure", "google", "no google"]):
        q = raw_cmd
        q = re.sub(r"(?i)^(?:silva,?\s*)?", "", q).strip()
        q = re.sub(
            r"(?i)^(?:pesquise\s+no\s+google|pesquisa\s+no\s+google|busca\s+no\s+google|busque\s+no\s+google|procura\s+no\s+google|procure\s+no\s+google|"
            r"pesquisa(?:r|ndo)?|pesquise|busca(?:r|ndo)?|busque|procura(?:r|ndo)?|procure|google|fazer\s+uma\s+busca\s+no\s+google\s+por|"
            r"fazer\s+uma\s+busca\s+por|faz\s+uma\s+busca\s+no\s+google\s+por|faz\s+uma\s+busca\s+por)\s+",
            "",
            q
        ).strip()
        q = re.sub(r"(?i)^(?:no\s+google\s+|pelo\s+google\s+|sobre\s+|por\s+|para\s+)?", "", q).strip()
        q = re.sub(r"(?i)\s+(?:no\s+google|pelo\s+google)?\s*(?:por\s+favor|pra\s+mim|agora)?$", "", q).strip().rstrip("?")
        q = re.sub(r"(?i)\s+(?:no\s+google|pelo\s+google)$", "", q).strip().rstrip("?")
        if q:
            return _format_call("search_google", query=q)

    return None


def match_intent_fallback(user_prompt: str) -> Optional[str]:
    """
    Roteador de intenções composto.
    Detecta multi-comandos combinados com 'e', 'depois', 'alem disso', etc.
    Exemplo: "liga a lanterna e vibra o celular" -> <call>set_torch(state=True)</call><call>vibrate(duration_ms=500)</call>
    """
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return None

    # Se a frase completa corresponder a uma busca/instalação composta na Play Store
    if re.search(r"(?i)\babre\s+(?:a|o)?\s*(?:play\s*store|playstore|google\s+play)\s+e\s+(?:baixa|instala|procura|pesquisa|busca)\b", clean_prompt):
        single = parse_single_intent(clean_prompt)
        if single:
            return single

    # Protege nomes compostos como "Abreu e Lima"
    protected_prompt = _protect_compound_names(clean_prompt)

    # Divisão primária por separadores fortes
    strong_delims = r";|\s+(?:e\s+tamb[eé]m|depois|em\s+seguida)\s+"
    primary_parts = [p.strip() for p in re.split(strong_delims, protected_prompt, flags=re.IGNORECASE) if p.strip()]

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

    matched_calls = []
    if len(clauses) > 1:
        for clause in clauses:
            call = parse_single_intent(clause)
            if call:
                matched_calls.append(call)

    # Se conseguiu multi-chamadas
    if len(matched_calls) >= 2:
        return "".join(matched_calls)

    # Tenta frase inteira como comando único
    return parse_single_intent(protected_prompt)
