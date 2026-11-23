"""
Roteador determinístico de intenções por pontuação (ScoredIntentRouter).
Resolve ambiguidades contextuais por pesos, trata anti-perguntas conceituais
e garante cobertura completa das 36 ferramentas do Silva com formatação segura via repr().
"""

import ast
import difflib
import re
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple, Any


def normalize_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e remove pontuação excessiva."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    text_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    text_clean = re.sub(r"[?!.,;:~—–]+", " ", text_clean)
    return " ".join(text_clean.split()).strip()


def _protect_compound_names(text: str) -> str:
    """Protege termos compostos com conectores 'e' para evitar separação prematura de cláusulas."""
    text = re.sub(r"\bAbreu\s+[eE]\s+Lima\b", "Abreu__E__Lima", text, flags=re.IGNORECASE)
    text = re.sub(r"\bJaboat[aã]o\s+dos\s+Guararapes\b", "Jaboatao__DOS__Guararapes", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCabo\s+de\s+Santo\s+Agostinho\b", "Cabo__DE__Santo__Agostinho", text, flags=re.IGNORECASE)
    text = re.sub(r"\bS[aã]o\s+Louren[cç]o\s+da\s+Mata\b", "Sao__Lourenco__DA__Mata", text, flags=re.IGNORECASE)
    return text


def _unprotect_compound_names(text: str) -> str:
    """Restaura nomes próprios que tiveram seu conector protegido temporariamente."""
    text = re.sub(r"\bAbreu__E__Lima\b", "Abreu e Lima", text, flags=re.IGNORECASE)
    text = re.sub(r"\bJaboatao__DOS__Guararapes\b", "Jaboatão dos Guararapes", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCabo__DE__Santo__Agostinho\b", "Cabo de Santo Agostinho", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSao__Lourenco__DA__Mata\b", "São Lourenço da Mata", text, flags=re.IGNORECASE)
    return text


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


# Whitelist de funções e constantes permitidas na calculadora
ALLOWED_MATH_NAMES = {
    "sqrt", "cbrt", "sin", "cos", "tan", "asin", "acos", "atan",
    "log", "log10", "log2", "exp", "factorial", "abs", "round", "floor", "ceil",
    "pi", "e"
}


def _normalize_math_expression(raw_text: str) -> Optional[str]:
    """
    Normaliza operadores, símbolos, funções científicas e expressões aritméticas
    para uma expressão aritmética/científica Python válida executável pelo SafeMathEvaluator.
    Retorna a expressão normalizada ou None se não for um cálculo válido.
    """
    if not raw_text:
        return None

    clean = raw_text.strip().rstrip("?!.,;:")
    lower = clean.lower()

    # Pré-tratamento com difflib para tolerar typos em palavras-chave matemáticas
    math_fuzzy_keywords = [
        "raiz", "quadrada", "cubica", "seno", "cosseno",
        "tangente", "fatorial", "logaritmo", "calcula", "calcular"
    ]
    tokens = re.findall(r"\w+|[^\w\s]|\s+", lower)
    corrected_tokens = []
    for tok in tokens:
        norm_tok = normalize_text(tok)
        if re.match(r"^[a-zA-Z]+$", norm_tok) and len(norm_tok) >= 4:
            matches = difflib.get_close_matches(norm_tok, math_fuzzy_keywords, n=1, cutoff=0.80)
            if matches:
                corrected_tokens.append(matches[0])
                continue
        corrected_tokens.append(tok)
    s = "".join(corrected_tokens)
    norm = normalize_text(s)

    math_triggers = [
        "quanto e", "quanto da", "quanto fica", "calcule", "calcular",
        "calcula", "resultado de", "raiz quadrada", "raiz cubica", "raiz de", "raiz",
        "fatorial", "seno", "cosseno", "tangente", "logaritmo", "log",
        "conta de", "valor de", "ao quadrado", "ao cubo", "elevado a"
    ]
    has_trigger = any(trig in norm for trig in math_triggers)
    has_direct_math = bool(re.search(r"\b\d+\s*(?:[\+\-\*\/÷×\^%]|x|vezes|dividido|mais|menos)\s*\d+\b", norm, re.IGNORECASE))
    has_math_func = any(f"{fn}(" in s for fn in ALLOWED_MATH_NAMES)

    if not has_trigger and not has_direct_math and not has_math_func:
        return None

    # Acréscimos e descontos de porcentagem
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

    # Porcentagem simples
    s = re.sub(
        r"(\d+(?:[\.,]\d+)?)\s*(?:%|por\s+cento)\s+de\s+(\d+(?:[\.,]\d+)?)",
        r"(\1 / 100) * \2",
        s
    )

    # Frações
    s = re.sub(r"(\d+)\s*/\s*(\d+)\s+de\s+(\d+(?:[\.,]\d+)?)", r"(\1 / \2) * \3", s)
    s = re.sub(r"\bmetade\s+de\s+(\d+(?:[\.,]\d+)?)", r"0.5 * \1", s)

    # Raízes cúbicas (aceita c[uú]bic[aoei]\w*)
    s = re.sub(
        r"(?:a\s+)?raiz\s+c[uú]bic[aoei]\w*\s*(?:de\s+)?(\d+(?:[\.,]\d+)?|\([^\)]+\))",
        r"cbrt(\1)",
        s
    )
    # Raízes quadradas e raízes diretas (aceita quadrad[aoei]\w* ou simplesmente raiz de)
    s = re.sub(
        r"(?:a\s+)?raiz\s+(?:quadrad[aoei]\w*\s+)?(?:de\s+)?(\d+(?:[\.,]\d+)?|\([^\)]+\))",
        r"sqrt(\1)",
        s
    )

    # Fatorial
    s = re.sub(r"fatorial\s+de\s+(\d+)", r"factorial(\1)", s)
    s = re.sub(r"(\d+)\s*fatorial\b", r"factorial(\1)", s)
    s = re.sub(r"(\d+)!", r"factorial(\1)", s)

    # Trigonometria (graus)
    s = re.sub(r"seno\s+de\s+(\d+(?:[\.,]\d+)?)\s*(?:graus?|°|º)?", r"sin(\1 * pi / 180)", s)
    s = re.sub(r"cosseno\s+de\s+(\d+(?:[\.,]\d+)?)\s*(?:graus?|°|º)?", r"cos(\1 * pi / 180)", s)
    s = re.sub(r"tangente\s+de\s+(\d+(?:[\.,]\d+)?)\s*(?:graus?|°|º)?", r"tan(\1 * pi / 180)", s)

    # Logaritmos
    s = re.sub(r"logaritmo\s+natural\s+de\s+(\d+(?:[\.,]\d+)?)", r"log(\1)", s)
    s = re.sub(r"\bln\s+de\s+(\d+(?:[\.,]\d+)?)", r"log(\1)", s)
    s = re.sub(r"logaritmo\s+de\s+(\d+(?:[\.,]\d+)?)", r"log10(\1)", s)
    s = re.sub(r"\blog\s+de\s+(\d+(?:[\.,]\d+)?)", r"log10(\1)", s)

    # Potências
    s = re.sub(r"\bao\s+quadrado\b", " ** 2", s)
    s = re.sub(r"\bao\s+cubo\b", " ** 3", s)
    s = re.sub(r"\belevado\s+a(?:o|\s+a)?\b", " ** ", s)

    # Operadores textuais
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

    # Vírgula decimal
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)

    # Remoção de fillers
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
        r"(?i)\bqual\s+(?:[eé]|a|o)\s+(?:o\s+resultado\s+de\s+|o\s+valor\s+de\s+|a\s+|o\s+)?",
        r"(?i)\bqual\s+[ao]\s+",
        r"(?i)\bqual\s+",
        r"(?i)\bme\s+diga\s+",
        r"(?i)\bme\s+diz\s+",
        r"(?i)\bpor\s+favor\b",
        r"(?i)\bpfv\b",
        r"[?!]+$"
    ]
    for pat in filler_patterns:
        s = re.sub(pat, " ", s)

    s = s.replace("^", " ** ")
    s = re.sub(r"\s+", " ", s).strip()

    if not re.match(r"^[0-9a-zA-Z_\+\-\*\/\(\)\.\s%,]+$", s):
        return None

    try:
        parsed = ast.parse(s, mode="eval")
        all_names = {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
        if not all_names.issubset(ALLOWED_MATH_NAMES):
            return None
        if isinstance(parsed.body, (ast.BinOp, ast.UnaryOp, ast.Call)):
            return s
    except Exception:
        return None

    return None


def _clean_ride_destination(raw_dest: str) -> str:
    """Limpa destino de corrida de transporte."""
    if not raw_dest:
        return ""
    text = str(raw_dest).strip()
    suffix_pat = r"(?i)\s+(?:por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|de\s+uber|de\s+99|no\s+uber|na\s+99|pelo\s+uber|pela\s+99|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

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
    """Limpa nome de comida para pedido de delivery."""
    if not raw_query:
        return ""
    text = str(raw_query).strip()
    suffix_pat = r"(?i)\s+(?:no\s+ifood|pelo\s+ifood|na\s+99|no\s+99|no\s+99\s*food|pelo\s+99|pelo\s+99\s*food|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

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
    """Limpa nome do aplicativo a ser instalado."""
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
    """Limpa e normaliza nome de localidade para consulta de clima."""
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


def _clean_search_query(raw_query: str) -> str:
    """
    Limpa e normaliza termos de pesquisa na web:
    1. Remove comandos imperativos e preposições (pesquise, busca, sobre, por, a respeito de, etc.)
    2. Remove sufixos de plataforma e cortesia (no google, no chrome, na internet, por favor, etc.)
    3. Remove artigos definidos e indefinidos no início (o, a, os, as, um, uma, uns, umas)
    4. Remove pontuações e caracteres residuais.
    """
    if not raw_query:
        return ""
    q = raw_query.strip()
    q = re.sub(r"(?i)^(?:silva,?\s*)?", "", q).strip()

    cmd_prefixes = [
        r"(?:pesquise|pesquisa|busca|busque|procura|procure)\s+(?:no\s+google|no\s+chrome|na\s+internet|na\s+web|no\s+navegador)\s+(?:sobre|por|a\s+respeito\s+de)?",
        r"fazer\s+uma\s+busca\s+(?:no\s+google\s+|no\s+chrome\s+|na\s+internet\s+)?(?:sobre|por|a\s+respeito\s+de)?",
        r"faz\s+uma\s+busca\s+(?:no\s+google\s+|no\s+chrome\s+|na\s+internet\s+)?(?:sobre|por|a\s+respeito\s+de)?",
        r"fazer\s+busca\s+(?:no\s+google\s+|no\s+chrome\s+|na\s+internet\s+)?(?:sobre|por|a\s+respeito\s+de)?",
        r"faz\s+busca\s+(?:no\s+google\s+|no\s+chrome\s+|na\s+internet\s+)?(?:sobre|por|a\s+respeito\s+de)?",
        r"(?:pesquisar|pesquise|pesquisa|pesquisando)\s+(?:sobre|por|a\s+respeito\s+de)?",
        r"(?:buscar|busque|busca|buscando)\s+(?:sobre|por|a\s+respeito\s+de)?",
        r"(?:procurar|procure|procura|procurando)\s+(?:sobre|por|a\s+respeito\s+de)?",
        r"google\s+(?:sobre|por|a\s+respeito\s+de)?",
        r"a\s+respeito\s+de",
        r"quem\s+foi",
        r"quem\s+[eé]",
        r"o\s+que\s+[eé]",
        r"o\s+que\s+s[aã]o",
        r"sobre",
        r"por",
    ]
    for p in cmd_prefixes:
        q = re.sub(rf"(?i)^\b{p}\b\s*", "", q).strip()

    # Preposições residuais no início
    q = re.sub(r"(?i)^(?:sobre\s+|por\s+|para\s+|pra\s+|a\s+respeito\s+de\s+)", "", q).strip()

    # Sufixos de plataforma e cortesia
    platform_suffixes = [
        r"no\s+google",
        r"pelo\s+google",
        r"no\s+navegador",
        r"pelo\s+navegador",
        r"no\s+chrome",
        r"pelo\s+chrome",
        r"na\s+internet",
        r"pela\s+internet",
        r"na\s+web",
        r"pela\s+web",
        r"por\s+favor",
        r"pra\s+mim",
        r"pfvr?",
        r"agora",
        r"agr",
        r"blz",
        r"silva",
    ]
    changed = True
    while changed:
        changed = False
        q = re.sub(r"[?!.,;\s]+$", "", q).strip()
        for s in platform_suffixes:
            new_q = re.sub(rf"(?i)\s+\b{s}\b[?!.,;\s]*$", "", q).strip()
            if new_q != q:
                q = new_q
                changed = True

    q = re.sub(r"[?!.,;\s]+$", "", q).strip()

    # Remove artigos definidos e indefinidos no início da query
    q = re.sub(r"(?i)^(?:o|a|os|as|um|uma|uns|umas)\s+", "", q).strip()

    return re.sub(r"[?!.,;\s]+$", "", q).strip()


# ==============================================================================
# EXTRATORES POR DOMÍNIO
# ==============================================================================

def extract_help(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Capacidades e ajuda do Silva."""
    clean = re.sub(r"(?i)^(?:silva,?\s*|ei,?\s*|oi,?\s*|ola,?\s*)?", "", norm).strip().rstrip("?!.,;:")
    clean = re.sub(r"(?i)\s+(?:por\s+favor|pra\s+mim|pfv|pfvr|agora|agr|aí|ai)$", "", clean).strip()
    help_phrases = [
        "o que voce faz", "o que vc faz", "o que voce pode fazer", "o que vc pode fazer",
        "o que voce sabe fazer", "o que vc sabe fazer", "quais suas funcoes", "quais suas capacidades",
        "suas funcoes", "suas capacidades", "lista de comandos", "seus comandos", "quais comandos",
        "o que posso pedir", "quais sao suas funcoes"
    ]
    if any(p in clean for p in help_phrases) or clean in ["ajuda", "help", "menu", "comandos", "funcoes"]:
        return 0.98, _format_call("list_capabilities")
    return 0.0, None


def extract_math(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Calculadora matemática e científica."""
    if any(w in norm for w in ["volume", "brilho", "timer", "alarme", "lembrete"]):
        return 0.0, None
    expr = _normalize_math_expression(raw)
    if expr:
        return 0.95, _format_call("calculate", expression=expr)
    return 0.0, None


def extract_torch(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Controle da lanterna."""
    if any(w in norm for w in ["lanterna", "torch", "flash"]):
        if any(neg in norm for neg in ["deslig", "desativ", "apag", "off", "fecha", "cort", "tir"]):
            return 0.92, _format_call("set_torch", state=False)
        return 0.92, _format_call("set_torch", state=True)
    return 0.0, None


def extract_battery(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Consulta de nível da bateria e carga do aparelho com suporte a ditado coloquial."""
    clean_norm = norm.rstrip("?!.,;:")
    # Construções coloquiais explícitas de ditado por voz e termos-chave de bateria/carga
    if any(w in clean_norm for w in ["bateria", "carga"]):
        return 0.95, _format_call("get_battery")

    # Frases de porcentagem ou nível associadas ao aparelho/celular
    if any(p in clean_norm for p in ["por cento", "porcento", "porcentagem", "nivel"]):
        if any(dev in clean_norm for dev in ["celular", "telefone", "aparelho", "smartphone", "dispositivo"]):
            return 0.95, _format_call("get_battery")

    return 0.0, None


def extract_wifi_and_notes(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """
    Desambiguação explícita de Wi-Fi e rede:
    1. get_wifi_info: informações da conexão atual, sinal, IP local
    2. set_wifi_state: ligar/desligar Wi-Fi
    3. connect_wifi: conectar a rede Wi-Fi informando SSID e senha opcional
    4. recall_note: consultar senhas de Wi-Fi salvas
    5. open_app: abrir configurações de Wi-Fi
    6. scan_wifi: escanear redes próximas
    """
    is_wifi = any(w in norm for w in ["wifi", "wifis", "wi-fi", "wi-fis", "rede sem fio", "redes sem fio", "ip"])
    if not is_wifi:
        return 0.0, None

    # Verificação prévia de menção a senha
    has_pwd = any(w in norm for w in ["senha", "password", "pass", "codigo", "chave", "passe"])

    # Verbos imperativos de conexão
    connect_patterns = [
        r"\bconecte-se\b", r"\bconectar-se\b", r"\bconecta\b", r"\bconecte\b",
        r"\bconectar\b", r"\bentrar\s+n[ao]\b", r"\bentra\s+n[ao]\b", r"\bentre\s+n[ao]\b",
        r"\bacessar\s+(?:o|a)?\b", r"\bacessa\s+(?:o|a)?\b"
    ]
    has_connect_verbs = any(re.search(p, norm) for p in connect_patterns)

    # Caso 1: get_wifi_info (informações da conexão atual, IP)
    info_triggers = [
        "qual wifi estou", "qual wi-fi estou", "qual wifi eu to", "qual wifi to",
        "qual rede estou", "qual rede eu to", "qual rede to", "qual rede que estou",
        "rede que estou", "wifi que estou", "rede atual", "wifi atual", "conexao atual",
        "qual conexao", "qual meu ip", "meu ip", "qual o ip", "qual e o ip",
        "ip do celular", "ip do telefone", "ip do aparelho", "ip da rede", "ip local",
        "status do wifi", "status da rede", "status da conexao", "info do wifi", "informacoes do wifi",
        "dados da rede wifi", "dados do wifi", "detalhes do wifi", "estou conectado", "to conectado",
        "qual meu wifi", "qual o meu wifi", "qual e o meu wifi", "qual e meu wifi",
        "qual meu wi-fi", "qual o meu wi-fi", "qual e o meu wi-fi", "qual e meu wi-fi",
        "meu wifi", "o meu wifi", "meu wi-fi", "o meu wi-fi"
    ]
    if any(t in norm for t in info_triggers) and not has_connect_verbs and not has_pwd:
        return 0.96, _format_call("get_wifi_info")

    # Caso 2: set_wifi_state (liga / desliga wifi)
    turn_off_wifi = any(re.search(rf"\b{v}\b.*\b(?:wi-?fi|rede\s+sem\s+fio)\b|\b(?:wi-?fi|rede\s+sem\s+fio)\b.*\b{v}\b", norm) for v in [
        "desliga", "desligar", "desligue", "desativa", "desativar", "desative",
        "deshabilita", "deshabilitar", "deshabilite", "apaga", "apagar", "off"
    ])
    if turn_off_wifi:
        return 0.96, _format_call("set_wifi_state", state=False)

    turn_on_wifi = any(re.search(rf"\b{v}\b.*\b(?:wi-?fi|rede\s+sem\s+fio)\b|\b(?:wi-?fi|rede\s+sem\s+fio)\b.*\b{v}\b", norm) for v in [
        "liga", "ligar", "ligue", "ativa", "ativar", "ative",
        "habilita", "habilitar", "habilite", "on"
    ])
    if turn_on_wifi and not has_connect_verbs:
        return 0.96, _format_call("set_wifi_state", state=True)

    # Caso 3: connect_wifi (conectar a rede com SSID e senha opcional)
    if has_connect_verbs:
        clean_text = re.sub(r"^(?:silva,?\s*)", "", raw, flags=re.IGNORECASE).strip().rstrip("?!.,;:")
        pwd_pat = r"\s+(?:com\s+a\s+senha|com\s+senha|senha|com\s+a\s+chave|com\s+chave|chave|password|pass)(?:\s*[:=]?\s*|\s+)(.+)$"
        m_pwd = re.search(pwd_pat, clean_text, re.IGNORECASE)
        if m_pwd:
            prefix_and_ssid = clean_text[:m_pwd.start()].strip()
            pwd = m_pwd.group(1).strip()
        else:
            prefix_and_ssid = clean_text
            pwd = ""

        curr = prefix_and_ssid.strip()
        curr = re.sub(r"^(?:por\s+favor,?\s*|pfv,?\s*)", "", curr, flags=re.IGNORECASE).strip()
        curr = re.sub(r"^(?:conecte-se|conectar-se|conecta|conecte|conectar|entra|entre|entrar|acesse|acessa|acessar)\b", "", curr, flags=re.IGNORECASE).strip()
        curr = re.sub(r"^(?:ao|a\s+o|no|na|a|o|em|de|da|do|pra|para)\b\s*", "", curr, flags=re.IGNORECASE).strip()
        curr = re.sub(r"^(?:rede(?:\s+sem\s+fio)?\s*(?:wi-?fi)?|wi-?fi)\b\s*", "", curr, flags=re.IGNORECASE).strip()
        curr = re.sub(r"^(?:ao|no|na|a|o)?\s*(?:wi-?fi|rede(?:\s+sem\s+fio)?)\b\s*", "", curr, flags=re.IGNORECASE).strip()
        ssid = curr.strip("\"'")
        pwd = pwd.strip("\"'")
        if ssid:
            return 0.96, _format_call("connect_wifi", ssid=ssid, password=pwd)

    # Caso 4: Senha de Wi-Fi salva -> recall_note
    if has_pwd:
        m_q = re.search(r"(?:senha|password|chave|codigo|passe)(?:\s+d[oa]|\s+de)?\s*(?:wi-?fi|wifi)?\s*(.*)", norm)
        target = m_q.group(1).strip() if m_q else ""
        target = re.sub(r"^(?:d[oa]\s+|de\s+)?(?:meu\s+|minha\s+)?(?:wi-?fi|wifi|rede)\s*", "", target).strip()
        target = re.sub(r"\b(?:meu|minha)\s+(?:wi-?fi|wifi|rede)\b", "", target).strip()
        target = re.sub(r"^(?:wi-?fi|wifi|rede)\s*", "", target).strip().rstrip("?!.,;:")
        query = f"senha do wifi {target}".strip() if target else "senha do wifi"
        return 0.95, _format_call("recall_note", query=query)

    # Caso 5: Abrir configurações de Wi-Fi -> open_app
    has_open = any(w in norm for w in ["abre", "abra", "abrir", "configura", "configurar", "configuracoes", "ajustes", "tela"])
    if has_open and not any(s in norm for s in ["escanear", "escaneie", "buscar", "procurar", "quais", "listar"]):
        return 0.90, _format_call("open_app", app_name="wifi")

    # Caso 6: Escanear redes próximas -> scan_wifi
    scan_triggers = [
        "escanear", "escaneie", "listar", "lista", "proximas", "proxima", "perto",
        "disponiveis", "disponivel", "redes", "quais", "ver", "mostre", "mostrar", "tem", "buscar", "busca", "scan"
    ]
    if any(t in norm for t in scan_triggers):
        return 0.95, _format_call("scan_wifi")

    return 0.85, _format_call("scan_wifi")


def extract_vibration(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Vibração háptica."""
    if any(w in norm for w in ["vibra", "vibrar", "vibracao", "treme", "tremer"]):
        m = re.search(r"(\d+)\s*(?:ms|milissegundos|segundos|s)?", norm)
        duration = 500
        if m:
            val = int(m.group(1))
            if "segundo" in norm or " s" in norm:
                duration = val * 1000
            else:
                duration = val
        return 0.90, _format_call("vibrate", duration_ms=duration)
    return 0.0, None


def extract_dnd(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Modo Não Perturbe / Silencioso."""
    if any(w in norm for w in ["perturbe", "pertube", "dnd", "silencioso", "silenciar"]):
        if any(neg in norm for neg in ["desativ", "deslig", "tir", "sair", "off", "cancel", "voltar"]):
            return 0.92, _format_call("set_dnd", state=False)
        return 0.92, _format_call("set_dnd", state=True)
    return 0.0, None


def extract_screenshot(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Captura de tela / Print."""
    if any(w in norm for w in ["print", "screenshot", "captura de tela", "capturar tela", "foto da tela"]):
        return 0.95, _format_call("take_screenshot")
    return 0.0, None


def extract_photo(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Tirar foto / Câmera."""
    if any(w in norm for w in ["foto", "selfie", "retrato", "fotografa"]):
        if not any(s in norm for s in ["tela", "screen", "print", "video", "gravar", "filmar"]):
            camera_id = 1 if any(w in norm for w in ["frontal", "selfie", "frente", "minha foto", "foto minha"]) else 0
            return 0.93, _format_call("take_photo", camera_id=camera_id)
    return 0.0, None


def extract_media_control(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Controle de reprodução de mídia."""
    if any(w in norm for w in ["volume", "brilho", "alarme", "timer"]):
        return 0.0, None

    clean = re.sub(r"(?i)^(?:silva,?\s*)?", "", norm).strip()
    clean = re.sub(r"(?i)\s+(?:por\s+favor|pra\s+mim|agora|aí|ai)$", "", clean).strip()

    # Next
    if any(w in clean for w in [
        "proxima musica", "proxima faixa", "pula a musica", "pula essa musica",
        "pular musica", "pula musica", "passa a musica", "passar musica", "proxima cancao",
        "avancar musica", "avanca a musica", "next track", "next song"
    ]) or clean in ["proxima", "proximo", "next", "pula", "passa"]:
        return 0.92, _format_call("media_control", action="next")

    # Previous
    if any(w in clean for w in [
        "volta a musica", "voltar a musica", "voltar musica", "volta musica",
        "musica anterior", "faixa anterior", "cancao anterior", "retrocede a musica",
        "previous track", "previous song"
    ]) or clean in ["anterior", "volta", "voltar", "previous"]:
        return 0.92, _format_call("media_control", action="previous")

    # Play
    if any(w in clean for w in [
        "despausa", "despausar", "continua a musica", "continuar a musica",
        "retoma a musica", "retomar a musica", "retoma o video", "retomar o video",
        "toca a musica", "tocar a musica", "reproduz a musica", "reproduzir a musica",
        "da o play", "dar o play", "dar play", "da play"
    ]) or clean in ["play", "despausa", "despausar", "tocar", "continuar", "retomar"]:
        return 0.90, _format_call("media_control", action="play")

    # Pause
    if any(w in clean for w in [
        "pausa a musica", "pausar a musica", "pausa o video", "pausar o video",
        "para a musica", "parar a musica", "interrompe a musica", "pausa reproducao",
        "pausar reproducao"
    ]) or clean in ["pause", "pausa", "pausar", "stop"]:
        return 0.90, _format_call("media_control", action="pause")

    return 0.0, None


def extract_record_video(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Gravação de vídeo."""
    if any(w in norm for w in ["video", "gravar", "grave", "grava", "filmar", "filma", "filme"]):
        if not any(w in norm for w in ["youtube", "tiktok", "pausa", "pausar", "retoma", "retomar", "continua", "continuar", "toca", "tocar", "play"]):
            m_dur = re.search(r"(\d+)\s*(?:segundos?|s|minutos?|min)?", norm)
            duration = 10
            if m_dur:
                val = int(m_dur.group(1))
                duration = val * 60 if ("minuto" in norm or "min" in norm) else val
            duration = max(3, min(duration, 120))
            camera_id = 1 if any(w in norm for w in ["frontal", "selfie", "frente", "me film", "me grav", "minha cara"]) else 0
            return 0.92, _format_call("record_video", duration=duration, camera_id=camera_id)
    return 0.0, None


def extract_ride(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Solicitação de transporte (Uber / 99)."""
    if norm.startswith(("abre ", "abra ", "abrir ")) and not any(p in norm for p in ["para", "pra", "pro", "ate", "p/"]):
        return 0.0, None

    ride_verbs = ["peca", "pede", "pedir", "chama", "chamar", "solicita", "solicitar", "solicite", "peco", "quero", "preciso", "consegue"]
    has_ride_verb = any(v in norm for v in ride_verbs)
    is_uber = "uber" in norm
    is_99 = "99" in norm
    ride_triggers = [
        "uber", "corrida", "chama um carro", "chamar um carro", "chama carro", "chamar carro",
        "pede um carro", "pedir um carro", "pede carro", "pedir carro", "chama corrida",
        "chamar corrida", "pede corrida", "pedir corrida", "solicita um carro", "solicitar um carro"
    ]
    is_99_ride = (is_99 and (any(w in norm for w in ["carro", "corrida", "chama", "pede", "pedir", "motorista", "viagem", "taxi"]) or has_ride_verb)
                  and not any(f in norm for f in ["food", "comida", "lanche", "pizza", "almoco", "pastel"]))

    if any(t in norm for t in ride_triggers) or is_99_ride or ((is_uber or is_99) and has_ride_verb):
        app = "99" if is_99 else "uber"
        dest = ""
        m_dest = re.search(r"(?:para|pra|pro|ate|até|p/)\s+([^\n\r,\.;]+)", raw, re.IGNORECASE)
        if m_dest:
            dest = _clean_ride_destination(m_dest.group(1))
        if not dest:
            m_alt = re.search(r"(?:uber|99|carro|corrida|taxi)\s+([^\n\r,\.;]+)", raw, re.IGNORECASE)
            if m_alt:
                dest = _clean_ride_destination(m_alt.group(1))
        if not dest:
            cleaned = re.sub(r"(?i)^(?:silva,?\s*)?(?:peça|peca|pede|pedir|chama|chamar|solicita|solicitar|quero|preciso\s+de)?\s*(?:um\s+|uma\s+)?(?:uber|99|carro|corrida|motorista|taxi)?\s*", "", raw)
            dest = _clean_ride_destination(cleaned)
        if not dest:
            dest = "destino"
        return 0.93, _format_call("request_ride", destination=dest, app=app)

    return 0.0, None


def extract_food(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Pedido de comida e delivery (iFood / 99 Food)."""
    if norm.startswith(("abre ", "abra ", "abrir ")) and not any(f in norm for f in ["pizza", "lanche", "hamburguer", "comida", "sushi", "acai", "pastel"]):
        return 0.0, None

    food_triggers = ["ifood", "99 food", "99food", "pedir comida", "pede comida", "peca comida", "pedir lanche", "pede lanche", "delivery"]
    food_items = ["pizza", "hamburguer", "lanche", "comida", "sushi", "acai", "marmita", "almoco", "jantar", "pastel", "salgado", "doce", "sobremesa"]
    has_food_item = any(f in norm for f in food_items)
    food_verbs = ["pede", "pedir", "peca", "quero", "compra", "comprar", "compre", "busca", "buscar", "procura", "me ve"]
    has_food_verb = any(v in norm for v in food_verbs)
    is_food_app = "ifood" in norm or "99 food" in norm or "99food" in norm

    if any(t in norm for t in food_triggers) or (has_food_item and has_food_verb) or (has_food_item and is_food_app) or is_food_app:
        app = "99" if ("99" in norm and "ifood" not in norm) else "ifood"
        query = _clean_food_query(raw)
        if not query:
            query = "comida"
        return 0.92, _format_call("order_food", query=query, app=app)

    return 0.0, None


def extract_install_app(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Instalação de aplicativo na Play Store."""
    if any(w in norm for w in ["volume", "brilho", "alarme", "timer", "lanterna", "camera", "foto"]):
        return 0.0, None

    has_store = any(k in norm for k in ["play store", "google play"])
    has_install_verb = any(v in norm for v in ["baixa", "baixar", "baixe", "instala", "instalar", "instale", "download"])
    is_only_open = norm in [
        "abre a play store", "abre o play store", "abrir play store",
        "inicia a play store", "inicia o google play"
    ]

    if (has_store or has_install_verb) and not is_only_open:
        clean_app = _clean_install_app_name(raw)
        if clean_app:
            return 0.91, _format_call("install_app", app_name=clean_app)

    return 0.0, None


def extract_open_app(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Abertura de aplicativos."""
    m_open = re.search(r"(?:abre|abra|abrir|inicia|inicie|iniciar|roda|rode|rodar|executa|execute|executar)\s+(?:o|a)?\s*([a-zA-Z0-9_\-\s]+)", norm)
    if m_open and not any(w in norm for w in ["lanterna", "camera", "foto", "timer", "alarme", "print", "screenshot", "tela"]):
        app_name = m_open.group(1).strip()
        app_name = re.sub(r"\s+(?:pra mim|por favor|agora|rapido)$", "", app_name).strip()
        if app_name:
            return 0.88, _format_call("open_app", app_name=app_name)
    return 0.0, None


def extract_call(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Chamada telefônica."""
    m_call = re.search(r"(?:liga|ligar|disca|discar|chama|chamar|telefone|telefonar)\s+(?:para\s+o|para\s+a|para|pro|pra|a)?\s*([^\n\r,\.;]+)", raw, re.IGNORECASE)
    if m_call and not any(w in norm for w in ["lanterna", "alarme", "som", "brilho", "uber", "carro", "corrida"]):
        target = m_call.group(1).strip()
        target = re.sub(r"(?i)\s+(?:pra mim|por favor|agora|rapido)$", "", target).strip()
        if target:
            return 0.90, _format_call("make_call", number=target)
    return 0.0, None


def extract_send_sms(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Envio de SMS."""
    m_sms = re.search(
        r"(?:envia|enviar|manda|mandar|escreve|escrever)\s+(?:um\s+)?(?:sms|mensagem\s+de\s+texto|torpedo)\s+(?:para|pro|pra)?\s*([a-zA-Z0-9_\+\s]+?)\s+(?:falando|dizendo|com a mensagem|que|de)\s+(.+)",
        raw,
        re.IGNORECASE
    )
    if m_sms:
        to_target = m_sms.group(1).strip()
        msg_body = m_sms.group(2).strip()
        return 0.95, _format_call("send_sms", number=to_target, message=msg_body)
    return 0.0, None


def extract_get_sms(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Leitura de mensagens SMS."""
    is_sms_target = bool(re.search(r"\b(?:sms|mensagens?\s+de\s+texto|torpedos?|caixa\s+de\s+entrada|mensagens?)\b", norm))
    is_sms_action = bool(re.search(r"\b(?:ler|leia|mostrar|mostre|ver|veja|listar|liste|quais|qual|recebi|recebido|recebidos|chegou|chegaram|ultim[oa]s?|nov[oa]s?|recentes?)\b", norm))

    if (is_sms_target and is_sms_action) or any(w in norm for w in ["ler sms", "leia sms", "ultimos sms", "mensagens recentes", "ver sms"]):
        if not any(v in norm for v in ["enviar", "envia ", "mandar", "manda ", "escrever", "escreve "]):
            m_num = re.search(r"\b(\d+)\s*(?:ultim[oa]s?|sms|mensagens?|torpedos?)\b", norm) or re.search(r"(?:ultim[oa]s?|ler|mostrar|ver)\s+(\d+)\b", norm)
            if m_num:
                limit = max(1, min(int(m_num.group(1)), 20))
            elif any(w in norm for w in ["ultimo sms", "ultima mensagem", "o ultimo", "a ultima"]):
                limit = 1
            else:
                limit = 5
            return 0.92, _format_call("get_last_sms", limit=limit)
    return 0.0, None


def extract_location(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Localização e estado do GPS."""
    if any(w in norm for w in ["ultima localizacao", "ultimo gps", "onde estive", "onde eu estava", "posicao anterior"]):
        return 0.94, _format_call("get_last_location")

    if any(w in norm for w in ["gps", "localizacao"]):
        if any(neg in norm for neg in ["desativ", "deslig", "desliga", "tirar", "sair", "off", "cancel"]):
            return 0.92, _format_call("set_location_state", state=False)
        if any(pos in norm for pos in ["ativ", "ligar", "liga ", "habilita", "habilitar", "on"]):
            return 0.92, _format_call("set_location_state", state=True)

    if any(w in norm for w in ["localizacao", "onde estou", "onde eu estou", "gps", "coordenadas", "minha posicao", "minha localizacao"]):
        return 0.90, _format_call("get_location")

    return 0.0, None


def extract_joke(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Contar piada."""
    if any(w in norm for w in ["piada", "engracado", "conta uma piada", "me faz rir"]):
        return 0.95, _format_call("tell_joke")
    return 0.0, None


def extract_clipboard(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Área de transferência."""
    if "clipboard" in norm or "area de transferencia" in norm or "o que copiei" in norm or "copiado" in norm:
        if any(q in norm for q in ["o que", "qual", "ler", "le ", "ver", "mostra", "tem", "copiado", "conteudo", "consulte"]):
            return 0.92, _format_call("get_clipboard")
        if any(w in norm for w in ["copia ", "copie ", "salva ", "salve ", "coloca ", "coloque ", "define ", "definir "]) or norm.startswith(("copia", "copie", "salva", "salve", "coloca", "coloque", "define", "definir")):
            m_clip = re.search(r"(?:copia|copie|salva|salve|coloca|coloque|define|definir)\s+(?:no\s+clipboard|na\s+area\s+de\s+transferencia|o\s+texto)?\s*(.+)", raw, re.IGNORECASE)
            text_val = m_clip.group(1).strip() if m_clip else ""
            text_val = re.sub(r"(?i)^(?:no\s+clipboard|na\s+area\s+de\s+transferencia|o\s+texto)\s*", "", text_val).strip()
            text_val = re.sub(r"(?i)\s+(?:no\s+clipboard|na\s+area\s+de\s+transferencia|para\s+o\s+clipboard)$", "", text_val).strip()
            if text_val:
                return 0.94, _format_call("set_clipboard", text=text_val)
        return 0.90, _format_call("get_clipboard")
    return 0.0, None


def extract_alarm(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Alarmes e despertador."""
    if any(w in norm for w in ["alarme", "despertador", "desperta", "despertar", "me acorda", "acordar"]):
        if any(w in norm for w in ["cancela", "cancelar", "desativa", "desativar", "apaga", "apagar", "remover", "remove", "desliga", "desligar"]):
            m_time = re.search(r"(\d{1,2}(?::\d{2})?)", norm)
            t_str = m_time.group(1) if m_time else ""
            if t_str and ":" not in t_str:
                t_str = f"{int(t_str):02d}:00"
            return 0.93, _format_call("cancel_alarm", time=t_str, day="", label="")
        else:
            m_time = re.search(r"(\d{1,2}(?::\d{2})?)", norm)
            t_str = m_time.group(1) if m_time else "07:00"
            if ":" not in t_str:
                t_str = f"{int(t_str):02d}:00"
            return 0.93, _format_call("set_alarm", time=t_str, label="Alarme", days=[])
    return 0.0, None


def extract_timer(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Timer e temporizador."""
    if any(w in norm for w in ["timer", "temporizador", "cronometro"]):
        m_min = re.search(r"(\d+)\s*(?:minutos?|min)?", norm)
        minutes = int(m_min.group(1)) if m_min else 5
        return 0.93, _format_call("set_timer", minutes=minutes, label="Timer")
    return 0.0, None


def extract_schedule(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Agenda e calendário."""
    triggers = ["agenda", "agende", "agendar", "marca", "marque", "marcar", "compromisso", "reuniao", "lembrete"]
    if any(t in norm for t in triggers) and not (norm.startswith(("abre", "abra", "abrir")) and any(a in norm for a in ["agenda", "calendario"])):
        time_val = ""
        time_span = None
        time_match = re.search(r"\b(?:[aàá]s|para\s+[aàá]s|pras|pra\s+[aàá]s)?\s*(\d{1,2})(?:[:h](\d{2})?|h)\b", raw, re.IGNORECASE)
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            if 0 <= h <= 23 and 0 <= m <= 59:
                time_val = f"{h:02d}:{m:02d}"
                time_span = time_match.span()

        date_val = ""
        date_span = None
        m_ext = re.search(r"\b(?:no\s+dia|dia)?\s*(\d{1,2}\s+de\s+[a-zçA-ZÀ-ÿ]+(?:\s+de\s+\d{2,4})?)(?:\s+deste\s+ano)?\b", raw, re.IGNORECASE)
        if m_ext:
            date_val = m_ext.group(1).strip()
            date_span = m_ext.span()
        else:
            m_rel = re.search(r"\b(depois\s+de\s+amanh[aã]|amanh[aã]|hoje|segunda(?:-feira)?|ter[cç]a(?:-feira)?|quarta(?:-feira)?|quinta(?:-feira)?|sexta(?:-feira)?|s[aá]bado|domingo)\b", raw, re.IGNORECASE)
            if m_rel:
                date_val = m_rel.group(1).strip()
                date_span = m_rel.span()
            else:
                m_num = re.search(r"\b(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{1,2}-\d{1,2})\b", raw)
                if m_num:
                    date_val = m_num.group(1).strip()
                    date_span = m_num.span()

        title_val = ""
        m_quotes = re.search(r'["\']([^"\']+)["\']', raw)
        if m_quotes:
            title_val = m_quotes.group(1).strip()
        else:
            cleaned = raw
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

        return 0.91, _format_call("schedule_event", title=title_val, date=date_val, time=time_val)

    return 0.0, None


def extract_memory(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Notas e lembranças de longo prazo."""
    if any(w in norm for w in ["lembra que", "lembrar que", "anota que", "salva que", "guarda que", "anote que", "salve que", "guarde que"]):
        content = re.sub(r"(?i)^(?:silva,?\s*)?(?:lembra|lembrar|lembre|anota|anotar|anote|salva|salvar|salve|guarda|guardar|guarde)\s+que\s+", "", raw).strip()
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
        return 0.95, _format_call("remember_note", key=k.strip(), value=v.strip())

    # Bloqueio explícito de perguntas de conhecimento geral / enciclopédicas ou termos matemáticos
    blocking_terms = [
        "quem foi", "quem e", "o que e", "o que sao", "como funciona",
        "previsao", "clima", "tempo", "temperatura",
        "raiz", "seno", "cosseno", "tangente", "fatorial", "log", "calculo",
        "por cento", "%"
    ]
    if any(term in norm for term in blocking_terms):
        return 0.0, None

    # Bloqueio explícito de perguntas sobre wifi/rede que não sejam sobre senha
    if any(w in norm for w in ["wifi", "wi-fi", "rede sem fio"]) and not any(k in norm for k in ["senha", "password", "chave", "codigo", "passe"]):
        return 0.0, None

    # Marcadores obrigatórios de memória pessoal para recall_note
    personal_memory_markers = [
        "onde eu guardei", "onde guardei", "onde deixei", "onde anotei",
        "o que eu anotei", "o que voce lembra", "na memoria",
        "qual era a senha", "qual a senha", "qual e a senha",
        "qual meu", "qual minha", "qual era o",
        "minha nota", "minhas notas", "minha anotacao", "minhas anotacoes",
        "lembra de", "lembra do", "lembra da", "lembra",
        "lembre de", "lembre do", "lembre da", "lembre"
    ]
    if any(m in norm for m in personal_memory_markers):
        q = re.sub(
            r"(?i)^(?:silva,?\s*)?(?:qual\s+(?:era\s+a\s+|era\s+o\s+|e\s+a\s+|e\s+o\s+|a\s+|o\s+|meu\s+|minha\s+)|onde\s+(?:eu\s+)?(?:guardei|deixei|anotei)\s+|o\s+que\s+(?:eu\s+anotei|voce\s+lembra)\s+(?:sobre\s+)?|minhas?\s+(?:notas?|anotac(?:ao|oes))\s+(?:sobre\s+)?|lembra\s+(?:de\s+|do\s+|da\s+|que\s+|o\s+|a\s+)?|lembre\s+(?:de\s+|do\s+|da\s+|que\s+|o\s+|a\s+)?|lembre-se\s+(?:de\s+|do\s+|da\s+)?|na\s+memoria\s+)?",
            "",
            raw
        ).strip().rstrip("?!.,;:")
        if not q:
            q = raw.strip().rstrip("?!.,;:")
        return 0.88, _format_call("recall_note", query=q)

    return 0.0, None


def extract_notifications(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Notificações."""
    if any(w in norm for w in ["notificacoes", "notificacao", "notificacoes do"]):
        m_app = re.search(r"(?:do|da|de)\s+([a-zA-Z0-9_\-]+)", norm)
        app_filter = m_app.group(1).strip() if m_app else ""
        if app_filter in ["celular", "meu", "sistema"]:
            app_filter = ""
        return 0.90, _format_call("get_notifications", app=app_filter)
    return 0.0, None


def _extract_level(norm: str, default: int = 50) -> int:
    """
    Extrai nível de intensidade (0 a 100) para volume e brilho.
    Mapeia:
      - 100: "total", "totalmente", "maximo", "ao maximo", "no maximo", "no talo", "no ultimo", "completo", "100%", "tudo"
      - 0: "minimo", "ao minimo", "no minimo", "zerado", "zero", "mudo", "silenciar", "0%"
      - 50: "metade", "meio", "50%" ou quando não houver modificador nem número
      - Número explícito caso fornecido.
    """
    # 1. Nível Máximo (100)
    max_patterns = [
        r"\bno\s+talo\b",
        r"\bao\s+maximo\b",
        r"\bno\s+maximo\b",
        r"\bno\s+ultimo\b",
        r"\btotalmente\b",
        r"\btotal\b",
        r"\bmaximo\b",
        r"\bcompleto\b",
        r"\b100\s*%",
        r"\btudo\b",
    ]
    for pat in max_patterns:
        if re.search(pat, norm, re.IGNORECASE):
            return 100

    # 2. Nível Mínimo (0)
    min_patterns = [
        r"\bao\s+minimo\b",
        r"\bno\s+minimo\b",
        r"\bzerado\b",
        r"\bzero\b",
        r"\bmudo\b",
        r"\bsilenciar\b",
        r"\bminimo\b",
        r"\b0\s*%",
    ]
    for pat in min_patterns:
        if re.search(pat, norm, re.IGNORECASE):
            return 0

    # 3. Metade / Meio (50)
    half_patterns = [
        r"\bmetade\b",
        r"\bmeio\b",
        r"\b50\s*%",
    ]
    for pat in half_patterns:
        if re.search(pat, norm, re.IGNORECASE):
            return 50

    # 4. Número explícito presente
    m = re.search(r"\b(\d+)\s*(?:%|porcento)?\b", norm)
    if m:
        try:
            val = int(m.group(1))
            return max(0, min(100, val))
        except ValueError:
            pass

    return default


def extract_volume(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Volume e som."""
    if "volume" in norm or (("som" in norm or "musica" in norm) and any(w in norm for w in ["aumenta", "diminui", "bota", "coloca"])):
        level = _extract_level(norm, default=50)
        return 0.92, _format_call("set_volume", stream="music", level=level)
    return 0.0, None


def extract_brightness(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Brilho da tela."""
    if "brilho" in norm:
        level = _extract_level(norm, default=50)
        return 0.92, _format_call("set_brightness", level=level)
    return 0.0, None


def extract_weather(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Previsão do tempo e clima."""
    if any(w in norm for w in ["clima", "previsao", "tempo", "chover", "chuva", "temperatura"]):
        if not any(w in norm for w in ["no google", "pesquisa no google"]):
            day = "hoje"
            if "depois de amanha" in norm:
                day = "depois de amanhã"
            elif "amanha" in norm:
                day = "amanhã"
            else:
                for wd in ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]:
                    if wd in norm:
                        day = wd
                        break

            time_val = ""
            if "noite" in norm:
                time_val = "noite"
            elif "tarde" in norm:
                time_val = "tarde"
            elif "madrugada" in norm:
                time_val = "madrugada"
            elif re.search(r"\bde manh[aã]\b|\bpela manh[aã]\b|\bmanh[aã]\b", norm) and not re.search(r"\bamanh[aã]\b", norm):
                time_val = "manhã"
            else:
                m_t = re.search(r"(\d{1,2}(?::\d{2}|h\d{0,2})?)", norm)
                if m_t and not any(c in m_t.group(1) for c in ["graus", "º", "°"]):
                    time_val = m_t.group(1)

            loc = ""
            pattern = r"\b(?:em|para|pra|no|na|de\s+(?!chuva\b|tempo\b|clima\b))\s*([a-zA-ZÀ-ÿ0-9\s,\-_]+)"
            matches = re.findall(pattern, raw, re.IGNORECASE)
            for m in reversed(matches):
                c = _clean_weather_location(m)
                if c:
                    loc = c
                    break

            return 0.94, _format_call("get_weather", day=day, time=time_val, location=loc)
    return 0.0, None


def extract_search(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Pesquisa no Google."""
    if any(w in norm for w in ["pesquisa", "pesquise", "busca", "busque", "procura", "procure", "google", "no google"]):
        q = _clean_search_query(raw)
        if q:
            return 0.85, _format_call("search_google", query=q)
    return 0.0, None


def extract_none(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Comando nulo explícito."""
    if norm in ["nada", "ignorar", "nenhuma acao", "nenhuma ação", "cancela", "cancelar"]:
        return 0.50, _format_call("none")
    return 0.0, None


# ==============================================================================
# CLASSE PRINCIPAL: ScoredIntentRouter
# ==============================================================================

class ScoredIntentRouter:
    """
    Roteador de intenções baseado em pontuação ponderada.
    Avalia os extratores registrados e seleciona a intenção de maior peso.
    """

    def __init__(self):
        self.extractors: List[Callable[[str, str], Tuple[float, Optional[str]]]] = [
            extract_help,
            extract_math,
            extract_torch,
            extract_battery,
            extract_wifi_and_notes,
            extract_vibration,
            extract_dnd,
            extract_screenshot,
            extract_photo,
            extract_media_control,
            extract_record_video,
            extract_ride,
            extract_food,
            extract_install_app,
            extract_open_app,
            extract_call,
            extract_send_sms,
            extract_get_sms,
            extract_location,
            extract_joke,
            extract_clipboard,
            extract_alarm,
            extract_timer,
            extract_schedule,
            extract_memory,
            extract_notifications,
            extract_volume,
            extract_brightness,
            extract_weather,
            extract_search,
            extract_none,
        ]

    def is_conceptual_question(self, norm_cmd: str) -> bool:
        """Verifica se é uma pergunta enciclopédica/conceitual pura."""
        conceptual_prefixes = (
            "o que e ", "o que sao ", "o que significa ", "qual a diferenca ",
            "quem foi ", "quem e ", "me explica ", "me explique ", "explique o que ", "explique "
        )
        if norm_cmd.startswith(conceptual_prefixes):
            is_capabilities = any(h in norm_cmd for h in [
                "o que voce", "o que vc", "suas funco", "suas capacida", "seus comando"
            ])
            if is_capabilities:
                return False
            operational_verbs = ("pesquise", "pesquisa", "busque", "busca", "ligue", "liga", "abra", "abre", "baixe", "baixa", "instale", "instala", "toque", "toca")
            if not any(v in norm_cmd for v in operational_verbs):
                return True
        return False

    def route(self, raw_cmd: str) -> Optional[str]:
        """Avalia todos os extratores e retorna a chamada da melhor intenção."""
        if not raw_cmd or not raw_cmd.strip():
            return None

        norm_cmd = normalize_text(raw_cmd)
        if not norm_cmd:
            return None

        # Bloqueia perguntas conceituais para que o LLM responda
        if self.is_conceptual_question(norm_cmd):
            return None

        best_score = 0.0
        best_call = None

        for extractor in self.extractors:
            try:
                score, call_str = extractor(raw_cmd, norm_cmd)
                if score > best_score and call_str:
                    best_score = score
                    best_call = call_str
            except Exception:
                continue

        # Threshold mínimo de confiança
        if best_score >= 0.5:
            return best_call

        return None
