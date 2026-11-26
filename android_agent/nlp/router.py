"""
Roteador determinístico de intenções por pontuação (ScoredIntentRouter).
Resolve ambiguidades contextuais por pesos, trata anti-perguntas conceituais
e garante cobertura completa das 36 ferramentas do Silva com formatação segura via repr().
"""

import ast
import difflib
import re
import unicodedata
from typing import Callable, List, Optional, Tuple


def normalize_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e remove pontuação excessiva."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    text_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    text_clean = re.sub(r"[?!.,;:~—–]+", " ", text_clean)
    return " ".join(text_clean.split()).strip()


def _strip_accents(text: str) -> str:
    """Remove acentos preservando caixa e caracteres especiais."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _mask_protected_entities(text: str) -> str:
    """
    Camada 1: Mascaramento reversível de marcas/tecnologias numéricas antes de numbers.py e colloquial.py.
    """
    if not text:
        return ""
    s = re.sub(r"\b99\s*food\b", "__APP_99FOOD__", text, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(um|o|de|no|na|pelo|pela|chama|chamar|pe[çc]a|pede|pedir)\s+99\b",
        r"\1 __APP_99__",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\b99\s*pop\b", "__APP_99__", s, flags=re.IGNORECASE)
    s = re.sub(r"\b4g\b", "__REDE_4G__", s, flags=re.IGNORECASE)
    s = re.sub(r"\b5g\b", "__REDE_5G__", s, flags=re.IGNORECASE)
    s = re.sub(r"\b3g\b", "__REDE_3G__", s, flags=re.IGNORECASE)
    return s


def _unmask_protected_entities(text: str) -> str:
    """Restaura placeholders protegidos da Camada 1."""
    if not text:
        return ""
    s = text.replace("__APP_99FOOD__", "99food")
    s = s.replace("__APP_99__", "99")
    s = s.replace("__REDE_4G__", "4g")
    s = s.replace("__REDE_5G__", "5g")
    s = s.replace("__REDE_3G__", "3g")
    return s


def _strip_conversational_fillers(text: str) -> str:
    """
    Camada 2: Limpeza centralizada de vocativos iniciais e sufixos de cortesia finais.
    """
    if not text:
        return ""
    s = str(text).strip()
    lead_pat = r"(?i)^(?:(?:ei|oi|ol[aá])\s+silva[\s,!.:;-]*|silva[\s,!.:;-]+|(?:por\s+favor|pfv|pfvr)[\s,!.:;-]+)"
    trail_pat = r"(?i)[\s,]+(?:para\s+mim|pra\s+mim|por\s+favor|pfv|pfvr|por\s+gentileza|agora\s+mesmo|a[ií])$"
    for _ in range(5):
        prev = s
        s = re.sub(lead_pat, "", s).strip()
        s = re.sub(trail_pat, "", s).strip()
        if s == prev:
            break
    return s


def _prepare_texts(user_text: str) -> Tuple[str, str]:
    """
    Normalização estrutural única na entrada (com limpeza de bordas da Camada 2):
    1. raw_clean: unifica espaços/quebras e remove vocativos/cortesias de borda.
    2. norm_clean: normaliza acentos e caixa baixa para detecção de intenção.
    """
    raw_clean = re.sub(r"\s+", " ", user_text or "").strip()
    raw_clean = _strip_conversational_fillers(raw_clean)
    norm_clean = normalize_text(raw_clean)
    return raw_clean, norm_clean


def _sanitize_entity_arg(value: str, strip_articles: bool = True) -> str:
    """
    Sanitizador obrigatório antes de montar chamadas com entidades:
    1. Remove pontuações de borda (?, !, ., ,, :, ;, aspas soltas).
    2. Remove prefixos residuais de comando/cortesia e próclises (se/me conecta, abra, etc.).
    3. Remove preposições e artigos de ligação no início se strip_articles=True.
    4. Remove sufixos de cortesia no final (por favor, pfv, agora, silva, etc.).
    """
    if not value:
        return ""

    s = str(value).strip()
    border_punct = r"""^[\s\.\?!,;:~—–"'`«»]+|[\s\.\?!,;:~—–"'`«»]+$"""

    prefix_cmd_pat = (
        r"^(?:ei\s+)?(?:silva[,\s]+)?(?:por\s+favor\s+|pfv\s+|pfvr\s+)?"
        r"(?:se\s+|me\s+)?"
        r"(?:conecte(?:-se)?|conectar(?:-se)?|conecta(?:r)?|conecte|entra(?:r)?|entre|acesse?|acessa(?:r)?|loga(?:r)?|logue|"
        r"abra|abre|abrir|inicia|inicie|iniciar|roda|rode|rodar|executa|execute|executar|"
        r"pesquise|pesquisa(?:r)?|busque|busca(?:r)?|procure|procura(?:r)?|"
        r"instale|instala(?:r)?|baixe|baixa(?:r)?|chame|chama(?:r)?|pede|pedir|peça|peca)\s+"
    )

    prefix_articles_pat = (
        r"^(?:ao|aos|à|às|no|na|nos|nas|em|de|do|da|dos|das|sobre|por|para|pro|pra|o|a|os|as|um|uma|uns|umas)\s+"
    )

    suffix_cortesia_pat = (
        r"\s+(?:por\s+favor|pfv|pfvr|agora|agr|blz|vlw|valeu|silva|obrigad[oa])$"
    )

    for _ in range(8):
        prev = s
        s = re.sub(border_punct, "", s).strip()
        s = re.sub(suffix_cortesia_pat, "", s, flags=re.IGNORECASE).strip()
        s = re.sub(border_punct, "", s).strip()
        s = re.sub(prefix_cmd_pat, "", s, flags=re.IGNORECASE).strip()
        s = re.sub(border_punct, "", s).strip()
        if strip_articles:
            s = re.sub(prefix_articles_pat, "", s, flags=re.IGNORECASE).strip()
            s = re.sub(border_punct, "", s).strip()
        if s == prev:
            break

    return s.strip()


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
            v_clean = _unmask_protected_entities(_unprotect_compound_names(v))
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
    """Limpa destino de corrida de transporte removendo ruídos coloquiais de origem, beneficiário e urgência."""
    if not raw_dest:
        return ""
    text = str(raw_dest).strip()
    suffix_pat = (
        r"(?i)\s+(?:pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|rapidinho|r[aá]pido|"
        r"aqui|blz|beleza|valeu|vlw|obrigad[oa]|silva|logo|j[aá]|aí|ai|"
        r"de\s+uber|de\s+99|no\s+uber|na\s+99|no\s+99|na\s+99\s*pop|no\s+99\s*pop|"
        r"pelo\s+uber|pela\s+99|pelo\s+99)$"
    )
    for _ in range(6):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    prefix_patterns = [
        r"(?i)^(?:de\s+onde\s+estou|daqui|aqui)\b\s*",
        r"(?i)^(?:pra\s+mim|para\s+mim|mim|eu|gente|nós|nos)\b\s*",
        r"(?i)^(?:por\s+favor|pfv|pfvr|rapidinho|r[aá]pido|agora|agr|j[aá]|logo)\b\s*",
        r"(?i)^(?:me\s+levar|me\s+leva|me\s+leve|levar|leva|leve|chegar|voltar|ir)\b\s*",
        r"(?i)^(?:para|pra|pro|pras|pros)\b\s*",
        r"(?i)^p/\s*",
        r"(?i)^(?:ao|aos|à|às|no|na|nos|nas|em|até|ate)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
    ]
    for _ in range(12):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    for _ in range(6):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
        if text == prev:
            break
    return _sanitize_entity_arg(text, strip_articles=True)


def _clean_food_query(raw_query: str) -> str:
    """Limpa nome de comida para pedido de delivery."""
    if not raw_query:
        return ""
    text = str(raw_query).strip()
    suffix_pat = r"(?i)\s+(?:no\s+ifood|pelo\s+ifood|na\s+99\s*food|no\s+99\s*food|pela\s+99\s*food|pelo\s+99\s*food|na\s+99|no\s+99|pela\s+99|pelo\s+99|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    prefix_patterns = [
        r"(?i)^(?:silva|ei|oi)\b[,\s]*",
        r"(?i)^(?:t[oô]\s+com\s+fome|estou\s+com\s+fome|com\s+fome)\b[,\s]*",
        r"(?i)^(?:pe[çc]a|peca|pede|pedir|quero|compra|comprar|compre|busca|buscar|procura|me\s+v[eê]|chama|chamar|traz|manda)\s+(?:um\s+|uma\s+)?(?:99\s*food\s+de\s+|ifood\s+de\s+)?",
        r"(?i)^(?:abre\s+o\s+ifood\s+e\s+pede|abre\s+o\s+ifood\s+e\s+peça|abre\s+o\s+ifood\s+e\s+peca|abre\s+o\s+ifood\s+e\s+pedir)\b\s*",
        r"(?i)^(?:abre\s+o\s+99\s+e\s+pede|abre\s+a\s+99\s+e\s+pede)\b\s*",
        r"(?i)^(?:quero\s+pedir|quero|gostaria\s+de\s+pedir|gostaria\s+de|me\s+vê|me\s+ve)\b\s*",
        r"(?i)^(?:peça|peca|pede|pedir|compra|comprar|compre|busca|busque|buscar|procura|procure|procurar|acha|achar|pesquisa|pesquisar)\b\s*",
        r"(?i)^(?:no\s+ifood|pelo\s+ifood|na\s+99\s*food|no\s+99\s*food|pela\s+99\s*food|pelo\s+99\s*food|na\s+99|no\s+99|pela\s+99|pelo\s+99)\b\s*",
        r"(?i)^(?:delivery\s+de|delivery)\b\s*",
        r"(?i)^(?:um|uma|uns|umas)\b\s*",
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
    return _sanitize_entity_arg(text, strip_articles=True)


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
    return _sanitize_entity_arg(text, strip_articles=True)


def _clean_weather_location(raw_loc: str) -> str:
    """Limpa e normaliza nome de localidade para consulta de clima."""
    s = _unprotect_compound_names(raw_loc.strip())
    if not s:
        return ""

    # Remove resíduos de perguntas de clima como "previsao do tempo em", "clima de"
    s = re.sub(r"(?i)^(?:previs[aã]o\s+d[oa]\s+tempo\s+|previs[aã]o\s+|clima\s+|tempo\s+)(?:em|para|pra|no|na|de)?\s*", "", s).strip()

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
    s = _sanitize_entity_arg(s, strip_articles=True)

    if not s:
        return ""

    invalid_words = {
        "hoje", "amanha", "amanhã", "depois", "aqui", "minha cidade",
        "mim", "graus", "tempo", "chuva", "sol", "calor", "frio", "clima", "previsao", "previsão"
    }
    s_norm = _strip_accents(s.lower()).strip()
    relative_local_keywords = {
        "minha cidade", "meu bairro", "minha regiao", "minha regiao atual",
        "meu estado", "meu pais", "aqui", "por aqui", "onde estou", "onde eu estou",
        "onde to", "onde eu to", "local atual", "meu local", "minha localizacao",
        "minha area", "meu setor", "meu redor", "ao meu redor", "na minha cidade",
        "no meu bairro", "na minha regiao", "no local atual"
    }
    if (
        s.lower() in invalid_words
        or s_norm in relative_local_keywords
        or bool(re.search(r"^(?:minha\s+cidade|meu\s+bairro|minha\s+regi[aã]o|onde\s+(?:eu\s+)?(?:estou|t[oô])|local\s+atual|meu\s+local|minha\s+localiza[cç][aã]o|por\s+aqui|aqui)$", s, re.IGNORECASE))
    ):
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


def _strip_leading_articles(q: str) -> str:
    """Remove artigos definidos e indefinidos isolados no início da query e pontuações finais."""
    if not q:
        return ""
    cleaned = re.sub(r"(?i)^\s*(?:o|a|os|as|um|uma|uns|umas)\s+", "", q.strip())
    return re.sub(r"[\s\.\?!,;:~—–-]+$", "", cleaned).strip()


def _clean_search_query(raw_query: str) -> str:
    """
    Limpa e normaliza termos de pesquisa na web:
    1. Remove comandos imperativos e preposições (pesquise, busca, sobre, por, a respeito de, etc.)
    2. Remove sufixos de plataforma e cortesia (no google, no chrome, na internet, por favor, etc.)
    3. Remove artigos definidos e indefinidos no início (o, a, os, as, um, uma, uns, umas)
    4. Remove pontuações e caracteres residuais via _sanitize_entity_arg.
    """
    if not raw_query:
        return ""
    q = re.sub(r"\s+", " ", raw_query).strip()
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

    # Aplica sanitizador universal
    return _sanitize_entity_arg(q, strip_articles=True)


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
    has_wifi_kw = any(w in norm for w in ["wifi", "wifis", "wi-fi", "wi-fis", "rede sem fio", "redes sem fio", "ip"])
    has_network_kw = (
        any(w in norm for w in [
            "redes ao redor", "rede ao redor", "redes por aqui", "rede por aqui",
            "redes disponiveis", "rede disponivel", "redes proximas", "rede proxima",
            "redes perto", "rede perto", "buscar redes", "busca redes",
            "escanear redes", "escaneie redes", "listar redes", "lista redes", "scanear redes",
            "quais redes", "ver redes", "mostre redes", "mostrar redes", "procurar redes"
        ])
        or bool(re.search(r"\b(?:qual|em\s+qual|que|o\s+que)\s+rede\b", norm))
        or bool(re.search(r"\b(?:rede|conexao)\s+(?:conectad[oa]|atual)\b", norm))
        or bool(re.search(r"\b(?:estou|to|conectado\s+em|conectado\s+na)\s+rede\b", norm))
    )

    if not (has_wifi_kw or has_network_kw):
        return 0.0, None

    # Deixa lembretes contextuais por Wi-Fi para extract_remind_on_wifi
    if re.search(r"\b(?:quando|assim\s+que)\b.*\b(?:lembra|lembre|lembrar|avisa|avise)\b", norm) or re.search(r"\b(?:lembra|lembre|avisa|avise)\b.*\bquando\b", norm):
        return 0.0, None

    # Verificação prévia de menção a senha
    has_pwd = any(w in norm for w in ["senha", "password", "pass", "codigo", "chave", "passe"])

    # Verbos imperativos de conexão (cobrindo próclise e ênclise)
    connect_patterns = [
        r"\b(?:se\s+|me\s+)?(?:conecte(?:-se)?|conectar(?:-se)?|conecta|conecte|conectar|entra|entre|entrar|acessa|acesse|acessar|loga|logar|logue)\b",
    ]
    has_connect_verbs = any(re.search(p, norm) for p in connect_patterns)

    # Caso 1: get_wifi_info (informações da conexão atual, IP)
    connected_info_patterns = [
        r"\b(?:qual|em\s+qual|que)\s+(?:o\s+|a\s+)?(?:wi-?fi|rede|conexao)\b.*\b(?:conectad[oa]|estou|to|ta|esta)\b",
        r"\b(?:qual|em\s+qual)\s+(?:o\s+|a\s+)?(?:wi-?fi|rede|conexao)\s+(?:conectad[oa])\b",
        r"\b(?:wi-?fi|rede|conexao)\s+(?:conectad[oa]|atual)\b",
        r"\b(?:estou|to|ta|esta)\s+conectad[oa]\s+(?:em|no|na)\s+(?:qual|que)?\s*(?:wi-?fi|rede)\b",
        r"\b(?:estou|to)\s+conectad[oa]\b",
    ]
    is_connected_info = any(re.search(p, norm) for p in connected_info_patterns)

    info_triggers = [
        "qual wifi estou", "qual wi-fi estou", "qual wifi eu to", "qual wifi to",
        "qual rede estou", "qual rede eu to", "qual rede to", "qual rede que estou",
        "qual wifi conectado", "qual wi-fi conectado", "qual rede conectado", "qual rede conectada",
        "rede que estou", "wifi que estou", "rede atual", "wifi atual", "conexao atual",
        "qual conexao", "qual meu ip", "meu ip", "qual o ip", "qual e o ip",
        "ip do celular", "ip do telefone", "ip do aparelho", "ip da rede", "ip local",
        "status do wifi", "status da rede", "status da conexao", "info do wifi", "informacoes do wifi",
        "dados da rede wifi", "dados do wifi", "detalhes do wifi", "estou conectado", "to conectado",
        "qual meu wifi", "qual o meu wifi", "qual e o meu wifi", "qual e meu wifi",
        "qual meu wi-fi", "qual o meu wi-fi", "qual e o meu wi-fi", "qual e meu wi-fi",
        "meu wifi", "o meu wifi", "meu wi-fi", "o meu wi-fi"
    ]
    if (is_connected_info or any(t in norm for t in info_triggers)) and not has_connect_verbs and not has_pwd:
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
        clean_raw = re.sub(r"(?i)^(?:silva,?\s*)", "", raw).strip()

        # 1. Ancoragem: Com Senha
        pat_with_pwd = (
            r"(?:(?:rede\s+(?:sem\s+fio\s+)?(?:de\s+)?|conex[aã]o\s+)?(?:wi-?fi|wifi)|rede\s+(?:sem\s+fio)?)\s+"
            r"(?:chamad[oa]\s+|de\s+nome\s+)?"
            r"(?P<ssid>.+?)\s+"
            r"(?:com\s+(?:a\s+)?)?(?:senha|chave|pass(?:word)?)\s*[:=]?\s*"
            r"(?P<password>\S+)"
        )
        m_with_pwd = re.search(pat_with_pwd, clean_raw, re.IGNORECASE | re.DOTALL)

        # 2. Ancoragem: Sem Senha / Rede Aberta
        pat_no_pwd = (
            r"(?:(?:rede\s+(?:sem\s+fio\s+)?(?:de\s+)?|conex[aã]o\s+)?(?:wi-?fi|wifi)|rede\s+(?:sem\s+fio)?)\s+"
            r"(?:chamad[oa]\s+|de\s+nome\s+)?"
            r"(?P<ssid>.+?)"
            r"(?:\s+(?:aberta|sem\s+senha))?$"
        )
        m_no_pwd = re.search(pat_no_pwd, clean_raw, re.IGNORECASE | re.DOTALL) if not m_with_pwd else None

        ssid = ""
        pwd = ""

        if m_with_pwd:
            raw_ssid = m_with_pwd.group("ssid")
            pwd = m_with_pwd.group("password").strip("\"'")
            ssid = _sanitize_entity_arg(raw_ssid, strip_articles=True)
        elif m_no_pwd:
            raw_ssid = m_no_pwd.group("ssid")
            ssid = _sanitize_entity_arg(raw_ssid, strip_articles=True)
        else:
            pat_fallback = (
                r"(?:\b(?:se\s+|me\s+)?(?:conecte(?:-se)?|conectar(?:-se)?|conecta|conecte|conectar|entra|entre|entrar|acessa|acesse|acessar)\b)\s+"
                r"(?:ao|a\s+o|no|na|a|o|em|pro|pra)?\s*"
                r"(?P<ssid>.+?)"
                r"(?:\s+(?:com\s+(?:a\s+)?)?(?:senha|chave|pass(?:word)?)\s*[:=]?\s*(?P<password>\S+)|$)"
            )
            m_fb = re.search(pat_fallback, clean_raw, re.IGNORECASE | re.DOTALL)
            if m_fb:
                raw_ssid = m_fb.group("ssid")
                if m_fb.group("password"):
                    pwd = m_fb.group("password").strip("\"'")
                ssid = _sanitize_entity_arg(raw_ssid, strip_articles=True)

        invalid_ssids = {"wifi", "wi-fi", "wifis", "wi-fis", "rede", "redes", "conexao", "conexão", "internet"}
        norm_ssid = normalize_text(ssid)
        if ssid and norm_ssid not in invalid_ssids and norm_ssid != normalize_text(clean_raw):
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
        "escanear", "escaneie", "escaneia", "listar", "lista", "proximas", "proxima", "perto",
        "disponiveis", "disponivel", "redes", "quais", "ver", "mostre", "mostrar", "tem", "buscar", "busca",
        "scan", "scanear", "rastrear", "procurar", "procura", "ao redor", "redor", "por aqui"
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


FOOD_KEYWORDS = (
    "comida", "lanche", "pizza", "hamburguer", "hamburgueres", "sushi", "acai",
    "marmita", "almoco", "jantar", "cafe", "esfiha", "pastel", "pasteis",
    "sorvete", "bebida", "refrigerante", "combo", "restaurante", "lanchonete",
    "pizzaria", "fome", "comer", "salgado", "doce", "sobremesa",
)

RIDE_KEYWORDS = (
    "corrida", "carro", "motorista", "viagem", "carona", "embarque", "destino",
    "me leva", "me levar", "ir para", "ir pro", "ir pra", "taxi",
)

_FOOD_KW_RE = re.compile(r"\b(?:" + "|".join(FOOD_KEYWORDS) + r")(?:s)?\b")
_FOOD_APP_RE = re.compile(r"\b(?:ifood|99\s*food|__app_99food__)\b")


def _has_food_domain(norm: str) -> bool:
    """Retorna True se a frase pertence ao domínio semântico de comida/delivery."""
    return bool(_FOOD_KW_RE.search(norm) or _FOOD_APP_RE.search(norm) or "delivery" in norm)


def extract_ride(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Solicitação de transporte (Uber / 99) governada por vocabulário de mobilidade/trajeto e verbos coloquiais."""
    if _has_food_domain(norm):
        return 0.0, None
    if norm.startswith(("anota", "anote", "lembra", "lembre", "salva", "salve", "guarda", "guarde")) or "vaga" in norm:
        return 0.0, None
    if any(w in norm for w in ("converte", "converter", "converta", "transforma", "dolar", "dolares", "euro", "euros", "reais", "brl", "usd", "eur")):
        return 0.0, None

    has_direction_prep = bool(re.search(r"\b(?:para|pra|pro|ate|p/)\s+\S+", norm))
    has_ride_kw = any(k in norm for k in RIDE_KEYWORDS)
    if norm.startswith(("abre ", "abra ", "abrir ")) and not has_direction_prep and not has_ride_kw:
        return 0.0, None

    ride_verbs = [
        "peca", "pede", "pedir", "chama", "chamar", "solicita", "solicitar", "solicite",
        "peco", "quero", "preciso", "consegue",
        "bota", "botar", "bote", "solta", "soltar", "solte",
        "manda", "mandar", "mande", "pega", "pegar", "pegue",
        "joga", "jogar", "jogue", "ve", "ver", "veja",
        "cota", "cotar", "cote", "faz", "fazer", "faca",
        "quanto ta", "quanto custa", "quanto fica", "qual o valor",
    ]
    has_ride_verb = any(v in norm for v in ride_verbs)
    is_uber = "uber" in norm
    is_99 = bool(re.search(r"\b99\b|noventa\s+e\s+nove|__app_99__", norm))

    if is_uber or has_ride_kw or (is_99 and (has_direction_prep or has_ride_verb)):
        # Táxi é atendido pelo super-app 99 (99 Táxi), salvo menção explícita ao Uber.
        is_taxi = bool(re.search(r"\btaxis?\b|\btáxis?\b", norm))
        app = "99" if (is_99 or (is_taxi and not is_uber)) else "uber"
        dest = ""
        m_dest = re.search(r"\b(?:para|pra|pro|ate|até|p/)\s+([^\n\r,\.;?!]+)", raw, re.IGNORECASE)
        if m_dest:
            dest = _clean_ride_destination(m_dest.group(1))
        if not dest:
            m_alt = re.search(r"\b(?:uber|99|__APP_99__|noventa\s+e\s+nove|carro|corrida|taxi)\s+([^\n\r,\.;?!]+)", raw, re.IGNORECASE)
            if m_alt:
                dest = _clean_ride_destination(m_alt.group(1))
        if not dest:
            cleaned = re.sub(
                r"(?i)^(?:silva,?\s*)?(?:peça|peca|pede|pedir|chama|chamar|solicita|solicitar|"
                r"bota|botar|solta|soltar|manda|mandar|pega|pegar|joga|jogar|ver|vê|ve|cota|cotar|"
                r"faz|fazer|quero|preciso\s+de|quanto\s+t[aá]|quanto\s+custa)?\s*"
                r"(?:um\s+|uma\s+)?(?:uber|99|carro|corrida|motorista|taxi)?\s*",
                "",
                raw,
            )
            dest = _clean_ride_destination(cleaned)
        if not dest:
            dest = "destino"
        return 0.96, _format_call("request_ride", destination=dest, app=app)

    return 0.0, None


def extract_food(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Pedido de comida e delivery (iFood / 99Food) com precedência semântica de alimentos."""
    has_food_kw = bool(_FOOD_KW_RE.search(norm))
    is_food_app = bool(_FOOD_APP_RE.search(norm))
    is_delivery = "delivery" in norm
    is_99 = bool(re.search(r"\b99\b|99\s*food|__app_99__|__app_99food__|noventa\s+e\s+nove", norm))

    if norm.startswith(("abre ", "abra ", "abrir ")) and not has_food_kw:
        return 0.0, None

    food_verbs = ["pede", "pedir", "peca", "quero", "compra", "comprar", "compre", "busca", "buscar", "procura", "me ve", "chama", "chamar", "traz", "manda"]
    has_food_verb = any(v in norm for v in food_verbs)

    if (has_food_kw and (has_food_verb or is_food_app or is_99 or is_delivery or "fome" in norm or "comer" in norm)) or is_food_app or is_delivery:
        app = "99food" if (is_99 and "ifood" not in norm) else "ifood"
        query = _clean_food_query(_unmask_protected_entities(raw))
        if not query or query.lower() in ("algo", "alguma coisa", "qualquer coisa"):
            query = "comida"
        return 0.96, _format_call("order_food", query=query, app=app)

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
    """Abertura de aplicativos e interação de toque com elementos da tela atual via uiautomator."""
    m_tap = re.search(
        r"^(?:silva,?\s*)?(?:clica|clique|clicar|toca|toque|tocar|aperta|aperte|apertar|pressiona|pressione)\s+(?:em|no|na)\s+(?:o\s+bot[aã]o\s+|bot[aã]o\s+)?(.+)$",
        raw.strip().rstrip("?!.,;:"),
        re.IGNORECASE,
    )
    if m_tap:
        label = m_tap.group(1).strip().strip("'\"")
        if label:
            return 0.94, _format_call("open_app", app_name=f"ui:tap:{label}", action="tap", label=label)

    m_open = re.search(
        r"\b(?:abre|abra|abrir|inicia|inicie|iniciar|roda|rode|rodar|executa|execute|executar)\s+(?:o|a)?\s*(?:o\s+app\s+|o\s+aplicativo\s+|app\s+|aplicativo\s+)?([^\n\r,\.;?!]+)",
        raw,
        re.IGNORECASE | re.DOTALL
    )
    if m_open:
        app_raw = m_open.group(1).strip()
        app_name = _sanitize_entity_arg(app_raw, strip_articles=True)
        app_name = re.sub(r"(?i)^(?:o\s+app\s+|o\s+aplicativo\s+|app\s+|aplicativo\s+)", "", app_name).strip()
        norm_app = normalize_text(app_name)
        system_tools = {
            "lanterna", "camera", "foto", "timer", "alarme", "print", "screenshot", "tela",
            "volume", "brilho", "wifi", "wi-fi", "bluetooth", "gps", "localizacao", "localização"
        }
        other_domain_verbs = ("pedir", "chamar", "mandar", "tocar", "lembrar", "converter")
        has_explicit_open = bool(re.match(r"^(?:abre|abra|abrir|inicia|inicie|iniciar)\b", norm))
        if (
            app_name
            and norm_app not in system_tools
            and (has_explicit_open or not any(v in norm_app for v in other_domain_verbs))
        ):
            return 0.88, _format_call("open_app", app_name=app_name)
    return 0.0, None


_HARDWARE_TARGETS = {
    "gps", "localizacao", "localização", "wifi", "wi-fi", "bluetooth", "bt",
    "lanterna", "flash", "dados", "dados moveis", "dados móveis", "internet",
    "4g", "5g", "roteador", "hotspot", "modo aviao", "modo avião", "tela",
}
_HARDWARE_TARGET_RE = re.compile(
    r"(?:^|\b)(?:"
    + "|".join(
        re.escape(t)
        for t in sorted(
            {normalize_text(x) for x in _HARDWARE_TARGETS}
            | {"__rede_4g__", "__rede_5g__", "__rede_3g__", "torch", "3g"},
            key=len,
            reverse=True,
        )
    )
    + r")(?:\b|$)"
)


def extract_call(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Chamada telefônica prioritária sobre lanterna/Wi-Fi quando acompanhada de alvo humano ou numérico."""
    # Nunca rotear pedidos de corrida/transporte (Uber, 99, carro, corrida) ou consulta de telefone para make_call
    if any(w in norm for w in ["uber", "corrida", "carro", "qual o telefone", "qual e o telefone", "qual o numero", "qual e o numero"]) or re.search(r"\b99\b|noventa\s+e\s+nove", norm):
        return 0.0, None
    if re.search(r"\b(?:me\s+)?(?:lembra|lembre|lembrar)\s+(?:de|do|da)\b", norm):
        return 0.0, None

    system_devices = {
        "lanterna", "torch", "flash", "wifi", "wi-fi", "bluetooth", "bt",
        "dados moveis", "dados", "internet movel", "4g", "5g", "3g", "__rede_4g__", "__rede_5g__", "__rede_3g__",
        "modo aviao", "hotspot", "roteador", "compartilhamento de internet",
        "alarme", "timer", "volume", "som", "brilho", "gps", "localizacao", "localização", "camera", "tela",
        "uber", "carro", "corrida", "taxi", "99"
    }

    # Padrão 1: "fazer / faz / efetuar uma ligação / chamada para ..."
    m1 = re.search(
        r"(?:(?:faz|fazer|faca|faça|efetua|efetuar|realiza|realizar)\s+(?:uma\s+)?(?:ligacao|ligação|chamada|telefonema))\s+(?:para\s+o|para\s+a|para\s+os|para\s+as|para|pro|pra|ao|a)?\s*([^\n\r,\.;]+)",
        raw,
        re.IGNORECASE
    )

    # Padrão 2: "ligar / liga / ligue / discar / disca / disque / telefonar / telefona para ..."
    m2 = re.search(
        r"(?:(?:ligar|liga|ligue|discar|disca|disque|telefonar|telefona|telefone))\s+(?:para\s+o|para\s+a|para\s+os|para\s+as|para|pro|pra|ao|a)?\s*([^\n\r,\.;]+)",
        raw,
        re.IGNORECASE
    )

    # Padrão 3: "chama / chamar o/a / para ..."
    m3 = re.search(
        r"(?:(?:chamar|chama|chame))\s+(?:o|a|os|as|para\s+o|para\s+a|para|pro|pra|ao)\s+([^\n\r,\.;]+)",
        raw,
        re.IGNORECASE
    )

    m_call = m1 or m2 or m3
    if not m_call:
        return 0.0, None

    target = m_call.group(1).strip()
    # Remove artigos e possessivos iniciais no target se sobraram
    target = re.sub(r"(?i)^(?:o|a|os|as|um|uma|meu|minha|meus|minhas)\s+", "", target).strip()
    # Remove preposições residuais
    target = re.sub(r"(?i)^(?:para\s+o|para\s+a|para|pro|pra|ao|a)\s+", "", target).strip()
    # Remove artigos/possessivos após preposição
    target = re.sub(r"(?i)^(?:o|a|os|as|meu|minha|meus|minhas)\s+", "", target).strip()
    # Remove sufixos de cortesia e pontuação
    target = re.sub(r"(?i)\s+(?:pra mim|pro silva|por favor|pfv|agora|rapido|imediatamente|urgente)$", "", target).strip()
    target = target.strip("'\"` .,;!?")

    if not target:
        return 0.0, ""

    norm_target = normalize_text(target)
    if (
        norm_target in system_devices
        or _HARDWARE_TARGET_RE.search(norm_target)
        or any(w in norm_target for w in ["lanterna", "torch", "flash", "wifi", "wi-fi", "bluetooth", "dados moveis", "modo aviao", "hotspot", "roteador", "uber", "carro", "corrida"])
    ):
        return 0.0, ""

    # Prioridade máxima (0.97) sobre lanterna/Wi-Fi quando acompanhado de alvo humano ou numérico
    return 0.97, _format_call("make_call", target=target)


def extract_send_sms(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Envio de SMS e mensagens no WhatsApp."""
    # 1. WhatsApp (prioridade 0.97)
    m_wpp_explicit = re.search(
        r"(?:envia|enviar|envie|manda|mandar|mande|escreve|escrever|fala|falar|fale)\s+"
        r"(?:um\s+|uma\s+)?(?:mensagem\s+)?(?:no|pelo|via)?\s*(?:whatsapp|zap|wpp)\s+"
        r"(?:para|pro|pra|com)\s+(?:o\s+|a\s+)?(.+?)\s*(?::|dizendo|falando|que)\s*(.+)",
        raw,
        re.IGNORECASE,
    )
    if m_wpp_explicit:
        to_target = re.sub(r"^(?:o|a)\s+", "", m_wpp_explicit.group(1).strip(), flags=re.IGNORECASE).strip()
        msg_body = m_wpp_explicit.group(2).strip()
        if to_target and msg_body:
            return 0.97, _format_call("send_whatsapp", contact_name=to_target, message=msg_body)

    m_wpp_short = re.search(
        r"(?:envia|enviar|envie|manda|mandar|mande)\s+"
        r"(?:uma\s+)?(?:mensagem\s+)?(?:no|pelo|via)?\s*(?:whatsapp|zap|wpp)\s+"
        r"(?:para|pro|pra)\s+(?:o\s+|a\s+)?([^\s:]+)\s+(.+)",
        raw,
        re.IGNORECASE,
    )
    if m_wpp_short:
        to_target = m_wpp_short.group(1).strip()
        msg_body = m_wpp_short.group(2).strip()
        if to_target and msg_body:
            return 0.97, _format_call("send_whatsapp", contact_name=to_target, message=msg_body)

    # 2. SMS tradicional (aceita números, nomes próprios acentuados e apelidos)
    m_sms = re.search(
        r"(?:envia|enviar|envie|manda|mandar|mande|escreve|escrever)\s+(?:um\s+)?(?:sms|mensagem\s+de\s+texto|torpedo)\s+(?:para|pro|pra)\s+(?:o\s+|a\s+)?([a-zA-ZÀ-ÿ0-9_\+\s]+?)\s+(?:falando|dizendo|com a mensagem|que|de)\s+(.+)",
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
        if re.search(r"\b(?:desliga|desligue|desligar|desativa|desative|desativar|desabilita|desabilite|desabilitar|tira|tirar|sai|sair|off|cancela|cancelar)\b", norm):
            return 0.96, _format_call("set_location_state", state=False)
        if re.search(r"\b(?:liga|ligue|ligar|ativa|ative|ativar|habilita|habilite|habilitar|on)\b", norm):
            return 0.96, _format_call("set_location_state", state=True)

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


def extract_remind_on_wifi(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Lembretes contextuais disparados ao conectar a uma rede Wi-Fi ou local salvo."""
    clean_raw = raw.strip().rstrip("?!.,;:")

    # 1. "quando eu chegar em casa / no trabalho / no escritório me lembra de ..."
    m_arrival = re.search(
        r"(?:quando|assim\s+que)\s+(?:eu\s+)?chegar\s+(?:em\s+|no\s+|na\s+)?(minha\s+casa|casa|meu\s+trabalho|trabalho|meu\s+escrit[oó]rio|escrit[oó]rio)\s*(?:,?\s*(?:me\s+)?(?:lembra|lembre|lembrar|avisa|avise)(?:\s+de|\s+que)?\s+(.+))",
        clean_raw,
        re.IGNORECASE,
    )
    if m_arrival:
        alias = re.sub(r"(?i)^(?:minha|meu)\s+", "", m_arrival.group(1)).strip().lower()
        reminder = m_arrival.group(2).strip()
        if reminder:
            return 0.96, _format_call("remind_on_wifi", ssid=alias, reminder=reminder)

    # 2. "quando conectar no wifi Trabalho me lembra de ..." / "quando conectar neste wifi lembra de ..."
    m_wifi_curr = re.search(
        r"(?:quando|assim\s+que)\s+(?:eu\s+)?(?:conectar|entrar|chegar)?\s*(?:neste|nesse)\s+wi-?fi\s*(?:,?\s*(?:me\s+)?(?:lembra|lembre|lembrar|avisa|avise)(?:\s+de|\s+que)?\s+(.+))",
        clean_raw,
        re.IGNORECASE,
    )
    if m_wifi_curr:
        reminder = m_wifi_curr.group(1).strip()
        if reminder:
            return 0.96, _format_call("remind_on_wifi", ssid="neste wifi", reminder=reminder)

    m_wifi_named = re.search(
        r"(?:quando|assim\s+que)\s+(?:eu\s+)?(?:conectar|entrar|chegar)?\s*(?:no|na|ao)?\s*wi-?fi\s+([^\s,]+)\s*(?:,?\s*(?:me\s+)?(?:lembra|lembre|lembrar|avisa|avise)(?:\s+de|\s+que)?\s+(.+))",
        clean_raw,
        re.IGNORECASE,
    )
    if m_wifi_named:
        ssid_val = m_wifi_named.group(1).strip().strip("'\"")
        reminder = m_wifi_named.group(2).strip()
        if ssid_val and reminder:
            return 0.96, _format_call("remind_on_wifi", ssid=ssid_val, reminder=reminder)

    # 3. Ordem inversa: "me lembra de pagar o boleto quando eu chegar em casa / conectar no wifi X"
    m_rev = re.search(
        r"^(?:silva,?\s*)?(?:me\s+)?(?:lembra|lembre|avisa|avise)\s+(?:de\s+|que\s+)?(.+?)\s+(?:quando|assim\s+que)\s+(?:eu\s+)?(?:chegar\s+(?:em\s+|no\s+|na\s+)?(minha\s+casa|casa|meu\s+trabalho|trabalho|meu\s+escrit[oó]rio|escrit[oó]rio)|(?:conectar|entrar)\s+(?:no|na)?\s*wi-?fi\s+([^\s,]+))",
        clean_raw,
        re.IGNORECASE,
    )
    if m_rev:
        reminder = m_rev.group(1).strip()
        ssid_val = (m_rev.group(2) or m_rev.group(3) or "").strip().strip("'\"")
        ssid_val = re.sub(r"(?i)^(?:minha|meu)\s+", "", ssid_val).strip()
        if ssid_val and reminder:
            return 0.96, _format_call("remind_on_wifi", ssid=ssid_val, reminder=reminder)

    return 0.0, None


def extract_schedule(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Agenda e calendário."""
    triggers = ["agenda", "agende", "agendar", "marca", "marque", "marcar", "compromisso", "reuniao", "lembrete"]
    has_temporal_reminder = bool(
        re.search(r"\b(?:me\s+)?(?:lembra|lembre|lembrar)\s+(?:de|do|da)\b", norm)
        and (
            re.search(r"\b\d{1,2}[:h]\d{0,2}\b", raw, re.IGNORECASE)
            or re.search(r"\b(?:amanha|hoje|depois de amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo|\d{1,2}/\d{1,2})\b", norm)
        )
    )
    if (any(t in norm for t in triggers) or has_temporal_reminder) and not (norm.startswith(("abre", "abra", "abrir")) and any(a in norm for a in ["agenda", "calendario"])):
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
                cleaned = re.sub(r"(?i)^(?:me\s+)?(?:lembra|lembre|lembrar)\s+(?:de\s+|do\s+|da\s+)?", "", cleaned).strip()
                cleaned = re.sub(r"(?i)^(?:compromisso|lembrete)\s+(?:de\s+|sobre\s+|para\s+)?", "", cleaned).strip()
                cleaned = re.sub(r"(?i)\s+(?:por\s+favor|pra\s+mim|agora)$", "", cleaned).strip()
                cleaned = re.sub(r"(?i)\s+(?:na|no|em|de|para|pra)$", "", cleaned).strip()
                cleaned = re.sub(r'[?!.,;:]+$', '', cleaned).strip()
                title_val = cleaned or "Compromisso"

        score = 0.96 if has_temporal_reminder else 0.91
        return score, _format_call("schedule_event", title=title_val, date=date_val, time=time_val)

    return 0.0, None


def extract_memory(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Notas, lembranças de longo prazo, captura livre com TTL, listagem e esquecimento."""
    clean_raw = raw.strip().rstrip("?!.,;:")

    # 1. list_memories ("o que você tem anotado?", "o que você sabe sobre mim?", "lista minhas memórias", "mostra minhas anotações de senha")
    if (
        any(t in norm for t in ("o que voce tem anotado", "o que vc tem anotado", "o que voce sabe sobre mim", "o que vc sabe sobre mim", "lista minhas memorias", "listar memorias", "minhas memorias", "todas as memorias"))
        or re.search(r"\b(?:mostra|mostre|lista|liste|ver|veja)\s+(?:as\s+)?minhas\s+(?:anotac(?:ao|oes)|notas|memorias)\b", norm)
    ):
        cat = ""
        m_cat = re.search(r"(?:anotac(?:ao|oes)|notas|memorias)\s+(?:de|da|do)\s+([a-zA-ZÀ-ÿ0-9_]+)", norm)
        if m_cat:
            cat = m_cat.group(1).strip()
            if cat in ("senha", "senhas"):
                cat = "senha"
        return 0.95, _format_call("list_memories", category=cat)

    # 2. forget_note ("esquece onde eu estacionei", "apaga a anotação do portão", "remove a senha antiga do wifi")
    m_forget = re.search(
        r"^(?:silva,?\s*)?(?:esquece|esquecer|esqueca|esqueça|apaga|apagar|apague|remove|remover|remova|deleta|deletar|delete)\s+(.+)$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_forget and not any(w in norm for w in ("lista", "alarme", "compromisso")):
        target_q = re.sub(
            r"^(?:(?:a\s+)?anota[cç][aã]o\s*(?:do|da|de)?\s*|(?:a\s+)?nota\s*(?:do|da|de)?\s*|(?:a\s+)?lembran[cç]a\s*(?:do|da|de)?\s*|a\s+|o\s+)",
            "",
            m_forget.group(1).strip(),
            flags=re.IGNORECASE,
        ).strip()
        if target_q and ("esquece" in norm or "esquec" in norm or any(w in norm for w in ("anotac", "nota", "memoria", "senha", "portao", "vaga"))):
            return 0.95, _format_call("forget_note", query=target_q)

    # 3. remember_note (estruturado, captura livre e TTL)
    if any(w in norm for w in ["lembra que", "lembrar que", "lembre que", "anota que", "anotar que", "anote que", "anota ai que", "anote ai que", "salva que", "salvar que", "salve que", "guarda que", "guardar que", "guarde que", "lembra disso"]):
        ttl_hours = 0
        m_ttl_h = re.search(r"\bpor\s+(\d+)\s*horas?\b", norm)
        if m_ttl_h:
            ttl_hours = max(1, int(m_ttl_h.group(1)))
        elif "so por hoje" in norm or "apenas hoje" in norm:
            ttl_hours = 12
        elif "ate amanha" in norm:
            ttl_hours = 24

        content = re.sub(
            r"(?i)^(?:silva,?\s*)?(?:lembra|lembrar|lembre|anota|anotar|anote|salva|salvar|salve|guarda|guardar|guarde)\s+(?:a[ií]\s+)?(?:disso\s+|que\s+)",
            "",
            raw,
        ).strip()
        content = re.sub(r"(?i)^(?:s[oó]\s+por\s+hoje|apenas\s+hoje|at[eé]\s+amanh[aã]|por\s+\d+\s+horas?)\s*:\s*", "", content).strip()

        if "=" in content:
            k, v = content.split("=", 1)
            return 0.95, _format_call("remember_note", key=k.strip(), value=v.strip(), ttl_hours=ttl_hours)
        if re.search(r"\s+[eé]\s*:\s*", content, re.IGNORECASE):
            parts = re.split(r"\s+[eé]\s*:\s*", content, maxsplit=1, flags=re.IGNORECASE)
            return 0.95, _format_call("remember_note", key=parts[0].strip(), value=parts[1].strip(), ttl_hours=ttl_hours)
        if re.search(r"\s+[eé]\s+", content, re.IGNORECASE):
            parts = re.split(r"\s+[eé]\s+", content, maxsplit=1, flags=re.IGNORECASE)
            return 0.95, _format_call("remember_note", key=parts[0].strip(), value=parts[1].strip(), ttl_hours=ttl_hours)
        if ":" in content:
            parts = content.split(":", 1)
            return 0.95, _format_call("remember_note", key=parts[0].strip(), value=parts[1].strip(), ttl_hours=ttl_hours)
        # Captura livre em uma frase: passa frase em key para extração semântica automática
        return 0.95, _format_call("remember_note", key=content.strip(), value="", ttl_hours=ttl_hours)

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
    """Volume e som (Camada 3: valida faixa 0..100 para números explícitos)."""
    if "volume" in norm or (("som" in norm or "musica" in norm) and any(w in norm for w in ["aumenta", "diminui", "bota", "coloca"])):
        m_num = re.search(r"(-?\d+)", norm)
        if m_num:
            val = int(m_num.group(1))
            if val < 0 or val > 100:
                return 0.0, None
        level = _extract_level(norm, default=50)
        return 0.92, _format_call("set_volume", stream="music", level=level)
    return 0.0, None


def extract_brightness(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Brilho da tela (Camada 3: valida faixa 0..100 para números explícitos)."""
    if "brilho" in norm:
        m_num = re.search(r"(-?\d+)", norm)
        if m_num:
            val = int(m_num.group(1))
            if val < 0 or val > 100:
                return 0.0, None
        level = _extract_level(norm, default=50)
        return 0.92, _format_call("set_brightness", level=level)
    return 0.0, None


def extract_weather(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Previsão do tempo e clima."""
    is_weather_intent = (
        any(w in norm for w in ["clima", "previsao", "tempo", "chover", "chuva", "temperatura"])
        or bool(re.search(r"\bquantos?\s+graus\b", norm))
        or bool(re.search(r"\bquanto\s+(?:est[aá]|t[aá])\s+fazendo\b", norm))
        or bool(re.search(r"\bcomo\s+(?:est[aá]|t[aá])\s+o\s+tempo\b", norm))
        or bool(re.search(r"\bcomo\s+(?:est[aá]|t[aá])\s+a\s+temperatura\b", norm))
        or bool(re.search(r"\bqual\s+(?:o\s+)?clima\b", norm))
        or bool(re.search(r"\bqual\s+(?:a\s+)?temperatura\b", norm))
        or bool(re.search(r"\bprevis[aã]o\s+d[oa]\s+tempo\b", norm))
    )
    if is_weather_intent:
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
            pattern = r"\b(?:em|para|pra|no|na|de\s+(?!chuva\b|tempo\b|clima\b|temperatura\b|graus\b))\s*([a-zA-ZÀ-ÿ0-9\s,\-_]+)"
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


def extract_datetime(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Data, hora e dia da semana."""
    if any(w in norm for w in ["alarme", "timer", "cronometro", "despertador", "agenda", "agendar", "reuniao", "previsao", "clima"]):
        return 0.0, None
    datetime_patterns = (
        r"\bque\s+horas?\s+(?:sao|e)\b",
        r"\b(?:qual|me\s+diga|diga|diz)\s+(?:a|as)\s+horas?\b",
        r"\b(?:qual\s+(?:e\s+)?a\s+data|data\s+de\s+hoje)\b",
        r"\bque\s+dia\s+(?:da\s+semana\s+)?(?:e|é)\s+hoje\b",
        r"\bque\s+dia\s+e\s+hoje\b",
        r"\bque\s+dia\s+da\s+semana\b",
    )
    if any(re.search(pat, norm) for pat in datetime_patterns):
        return 0.95, _format_call("get_datetime")
    return 0.0, None


def extract_system_info(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Telemetria do sistema: armazenamento, RAM e operadora."""
    sys_triggers = (
        "espaco livre", "armazenamento", "memoria ram", "quanta ram", "quanto de ram",
        "status do sistema", "info do sistema", "informacoes do sistema",
        "qual minha operadora", "qual a operadora", "minha operadora", "rede movel",
    )
    if any(t in norm for t in sys_triggers) or re.search(r"\b(?:quanto|qual)\b.*\b(?:espaco|armazenamento|ram)\b", norm):
        return 0.95, _format_call("get_system_info")
    return 0.0, None


def extract_read_screen(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Leitura do conteúdo legível da tela atual via uiautomator."""
    screen_patterns = (
        r"\bo\s+que\s+(?:esta|tem)\s+(?:escrito\s+)?na\s+(?:minha\s+)?tela\b",
        r"\b(?:le|leia|ler|resuma|resumir|mostra|mostre)\s+(?:o\s+que\s+(?:esta|tem)\s+na\s+(?:minha\s+)?tela|conteudo\s+da\s+tela|a\s+(?:minha\s+)?tela)\b",
        r"\bresumo\s+da\s+tela\b",
    )
    if any(re.search(pat, norm) for pat in screen_patterns):
        return 0.96, _format_call("read_screen")
    return 0.0, None


def extract_save_contact(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Cadastro direto de contato (nome e telefone)."""
    m_save = re.search(
        r"(?:salva|salve|salvar|cadastra|cadastre|cadastrar|adiciona|adicione|adicionar|guarda|guarde|guardar)\s+"
        r"(?:o\s+)?(?:contato|n[uú]mero|telefone)(?:\s+(?:do|da|de))?\s+"
        r"([a-zA-ZÀ-ÿ\s]{2,45}?)\s*(?:como|:|é|e)?\s*(\+?\d[\d\s\-()]{6,18}\d)\b",
        raw,
        re.IGNORECASE,
    )
    if m_save:
        c_name = re.sub(r"^(?:do|da|de|o|a)\s+", "", m_save.group(1).strip(), flags=re.IGNORECASE).strip()
        c_phone = re.sub(r"[\s\-()]", "", m_save.group(2).strip())
        if c_name and c_phone:
            return 0.97, _format_call("save_contact", name=c_name, phone=c_phone)
    return 0.0, None


def extract_get_contact(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Consulta de contato na memória e na agenda."""
    m_get = re.search(
        r"(?:qual\s+(?:é\s+|e\s+)?(?:o\s+)?(?:telefone|n[uú]mero|celular|contato|whatsapp|zap)|"
        r"me\s+passa\s+(?:o\s+)?(?:contato|n[uú]mero|telefone)|"
        r"busca(?:r)?\s+(?:o\s+)?contato|procura(?:r)?\s+(?:o\s+)?contato)\s+"
        r"(?:do|da|de)\s+([a-zA-ZÀ-ÿ0-9\s]{2,45})",
        raw.strip().rstrip("?!.,;:"),
        re.IGNORECASE,
    )
    if m_get:
        c_name = re.sub(r"^(?:do|da|de|o|a)\s+", "", m_get.group(1).strip(), flags=re.IGNORECASE).strip()
        if c_name:
            return 0.98, _format_call("get_contact", name=c_name)
    return 0.0, None


def extract_connectivity_controls(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Controles de conectividade via ADB: Bluetooth, Dados Móveis, Modo Avião e Hotspot."""
    on_verbs = ("liga", "ligar", "ligue", "ativa", "ativar", "ative", "habilita", "habilitar", "habilite", "entra", "coloca", "bota", "abre")
    off_verbs = ("desliga", "desligar", "desligue", "desativa", "desativar", "desative", "desabilita", "desabilitar", "desabilite", "tira", "sai", "remove", "fecha")

    is_on = any(re.search(rf"\b{v}\b", norm) for v in on_verbs)
    is_off = any(re.search(rf"\b{v}\b", norm) for v in off_verbs)
    if not (is_on or is_off):
        return 0.0, None

    state_val = False if is_off else True

    if re.search(r"\b(?:bluetooth|bt)\b", norm):
        return 0.96, _format_call("set_bluetooth_state", state=state_val)

    if any(t in norm for t in ("dados moveis", "internet movel", "rede movel")) or re.search(r"\b(?:os\s+dados|4g|5g|3g|__rede_4g__|__rede_5g__|__rede_3g__)\b", norm):
        return 0.96, _format_call("set_mobile_data_state", state=state_val)

    if "modo aviao" in norm:
        return 0.96, _format_call("set_airplane_mode", state=state_val)

    if any(t in norm for t in ("hotspot", "roteador", "compartilhamento de internet", "tethering", "ancoragem")):
        return 0.96, _format_call("set_hotspot_state", state=state_val)

    return 0.0, None


def extract_voice_notes(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Notas e lembretes multimodais com checklist interativo (voz e texto digitado)."""
    clean_raw = raw.strip().rstrip("?!.,;:")

    # 1. check_voice_note ("marca como check a nota do aluguel", "conclui o lembrete de...", "apaga a última nota de voz")
    if (
        any(k in norm for k in ("marca como check", "marcar como check", "dar check", "da check", "conclui o lembrete", "concluir o lembrete", "conclui a nota", "marcar como concluido", "marca como concluido"))
        or re.search(r"\b(?:apaga|apagar|remove|remover|deleta|deletar|exclui|excluir)\s+(?:a\s+)?(?:ultima|ultimo|recente)?\s*nota\s+de\s+voz\b", norm)
    ):
        if any(w in norm for w in ("ultima", "ultimo", "recente")):
            return 0.97, _format_call("check_voice_note", query="última")
        m_chk = re.search(
            r"(?:nota\s+de\s+voz|nota|lembrete)(?:\s+do|\s+da|\s+de|\s+sobre)?\s+(.+)$",
            clean_raw,
            re.IGNORECASE,
        )
        q_chk = m_chk.group(1).strip() if m_chk else clean_raw
        return 0.97, _format_call("check_voice_note", query=q_chk)

    # 2. save_voice_note Modo Digitado (text_only=True)
    m_txt = re.search(
        r"^(?:silva,?\s*)?(?:adiciona|adicione|coloca|coloque|anota|anote|cria|crie|salva|salve)\s+(?:na\s+lista\s+de\s+lembretes|no\s+checklist|um\s+lembrete\s+r[aá]pido|um\s+lembrete)(?:\s*:\s*|\s+(?:para|de|que)\s+|\s+)(.+)$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_txt:
        title_val = m_txt.group(1).strip().lstrip(":").strip()
        if title_val:
            return 0.97, _format_call("save_voice_note", title=title_val, duration=15, text_only=True)

    # 3. get_voice_notes ("quais notas de voz eu tenho?", "mostra meus lembretes", "lembra o que eu gravei sobre o aluguel", "abrir checklist de notas")
    if (
        any(k in norm for k in ("quais notas de voz", "minhas notas de voz", "meus lembretes", "lista de lembretes", "checklist de notas", "abrir checklist", "abre o checklist", "ver checklist"))
        or re.search(r"\b(?:mostra|mostre|lista|liste|ver|veja|abre|abra)\s+(?:os\s+|as\s+)?(?:meus\s+|minhas\s+)?(?:lembretes|notas\s+de\s+voz|checklist)\b", norm)
        or re.search(r"\b(?:o\s+que\s+(?:eu\s+)?gravei)\b", norm)
    ):
        m_q = re.search(r"(?:sobre|do|da|de)\s+(?!voz\b|notas\b|lembretes\b)(.+)$", clean_raw, re.IGNORECASE)
        q_val = m_q.group(1).strip() if m_q else ""
        return 0.97, _format_call("get_voice_notes", query=q_val)

    # 4. save_voice_note Modo Voz (text_only=False)
    if (
        any(k in norm for k in ("nota de voz", "lembrete de voz", "minha voz"))
        and any(v in norm for v in ("grava", "gravar", "grave", "lembrar", "dizendo", "segundo", "nota de voz", "lembrete de voz"))
    ):
        dur = 15
        m_sec = re.search(r"(\d+)\s*(?:s|seg|segundo|segundos)\b", norm)
        if m_sec:
            dur = max(1, min(120, int(m_sec.group(1))))
        m_title = re.search(
            r"(?:\s*:\s*|\b(?:para\s+lembrar(?:\s+de)?|lembrar(?:\s+de)?|dizendo|sobre|para|titulo|t[ií]tulo)\s+)(.+)$",
            clean_raw,
            re.IGNORECASE,
        )
        title_val = m_title.group(1).strip().lstrip(":").strip() if m_title else ""
        if title_val and re.fullmatch(r"\d+\s*(?:s|seg|segundo|segundos)", _normalize_ascii_lower(title_val) if "_normalize_ascii_lower" in globals() else title_val.lower()):
            title_val = ""
        return 0.97, _format_call("save_voice_note", title=title_val, duration=dur, text_only=False)

    return 0.0, None


def extract_news(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Leitura de notícias reais via RSS (geral, tecnologia, economia, esportes)."""
    if any(k in norm for k in ("noticias", "noticia", "manchetes", "manchete", "resumo do dia")) and any(
        t in norm for t in ("quais", "hoje", "atualiza", "resumo", "mostra", "ler", "le ", "me da", "tecnologia", "economia", "esportes", "geral", "ultimas")
    ):
        topic = "geral"
        if any(w in norm for w in ("tecnologia", "tech", "inovacao")):
            topic = "tecnologia"
        elif any(w in norm for w in ("economia", "financas", "mercado", "bolsa")):
            topic = "economia"
        elif any(w in norm for w in ("esportes", "esporte", "futebol")):
            topic = "esportes"
        limit = 5
        m_lim = re.search(r"\b(\d+)\s*(?:noticias|manchetes)\b", norm)
        if m_lim:
            limit = max(1, min(10, int(m_lim.group(1))))
        return 0.96, _format_call("get_news", topic=topic, limit=limit)
    return 0.0, None


def extract_contact_alias(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Vinculação de apelido/relação pessoal a contato real (save_contact_alias)."""
    # Ex.: "apelido amor para Ana" / "salva apelido amor para Ana"
    m_ap = re.search(
        r"(?:salva(?:r)?\s+)?apelido\s+(?:de\s+)?([^\n\r,;]+?)\s+(?:para|pro|pra|como)\s+([^\n\r,;\.!?]+)",
        raw,
        re.IGNORECASE,
    )
    if m_ap:
        alias_v = m_ap.group(1).strip()
        target_v = m_ap.group(2).strip()
        if alias_v and target_v:
            return 0.97, _format_call("save_contact_alias", alias=alias_v, target_name=target_v)

    # Ex.: "minha mãe é a Maria Silva" / "salva que meu pai é o João" / "o dentista é o Dr. Carlos"
    m_rel = re.search(
        r"^(?:silva,?\s*)?(?:salva\s+que\s+|anota\s+que\s+|lembra\s+que\s+)?(?:(?:meu|minha|o|a)\s+)?(m[ãa]e|pai|amor|esposa|marido|namorad[oa]|chefe|dentista|m[eé]dic[oa]|av[oó]|irm[ãa]o?)\s+[ée]\s+(?:o|a|os|as)?\s*([^\n\r,;\.!?]+)$",
        raw.strip(),
        re.IGNORECASE,
    )
    if m_rel:
        alias_v = m_rel.group(1).strip()
        target_v = m_rel.group(2).strip()
        if alias_v and target_v and not re.search(r"\d{4,}", target_v):
            return 0.97, _format_call("save_contact_alias", alias=alias_v, target_name=target_v)
    return 0.0, None


def extract_manage_sleep(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Comandos manuais do monitor de sono: start_now, discard_last, status."""
    if re.search(r"\b(?:vou\s+(?:dormir|deitar)|indo\s+(?:dormir|deitar)|ja\s+vou\s+(?:dormir|deitar))\b", norm):
        return 0.97, _format_call("manage_sleep", action="start_now")
    if (
        "sono" in norm
        and any(v in norm for v in ("desconsidera", "desconsiderar", "apaga", "apagar", "exclui", "excluir", "remove", "remover", "descarta", "descartar"))
    ):
        return 0.97, _format_call("manage_sleep", action="discard_last")
    if "status" in norm and "sono" in norm:
        return 0.97, _format_call("manage_sleep", action="status")
    return 0.0, None


def extract_sleep_report(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Relatório científico e evolução longitudinal do sono noturno."""
    sleep_triggers = (
        "meu sono", "relatorio do sono", "relatorio de sono", "como foi meu sono",
        "como eu dormi", "evolucao do sono", "evolucao do meu sono", "qualidade do sono",
        "sono melhorando", "sono piorando", "horas eu dormi", "dormi ontem",
    )
    if any(t in norm for t in sleep_triggers) or (
        "sono" in norm and any(k in norm for k in ("relatorio", "evolucao", "melhorando", "piorando", "como foi", "analise", "semana", "noite", "historico"))
    ):
        days = 7
        m_days = re.search(r"(\d+)\s*dias?\b", norm)
        if m_days:
            days = max(1, min(30, int(m_days.group(1))))
        elif "mes" in norm or "30 dias" in norm:
            days = 30
        elif "hoje" in norm or "ontem" in norm or "ultima noite" in norm:
            days = 7
        return 0.96, _format_call("get_sleep_report", days=days)
    return 0.0, None


def extract_record_audio(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Gravação genérica de áudio/som (sem menção a nota/lembrete de voz)."""
    if any(k in norm for k in ("nota de voz", "lembrete de voz")):
        return 0.0, None
    if any(t in norm for t in ("gravar audio", "grava audio", "grava um audio", "gravar um audio", "grave um audio", "gravar som", "grava som", "grave o som", "grava o som", "gravar voz", "grava voz")):
        dur = 10
        m_min = re.search(r"(\d+)\s*(?:min|minuto|minutos)\b", norm)
        m_sec = re.search(r"(\d+)\s*(?:s|seg|segundo|segundos)\b", norm)
        if m_min:
            dur = int(m_min.group(1)) * 60
        elif m_sec:
            dur = int(m_sec.group(1))
        dur = max(1, min(120, dur))
        return 0.95, _format_call("record_audio", duration=dur)
    return 0.0, None


_CURRENCY_QUOTE_MAP = {
    "dolar": "USD", "dolares": "USD", "usd": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "libra": "GBP", "libras": "GBP", "libra esterlina": "GBP", "gbp": "GBP",
    "iene": "JPY", "ienes": "JPY", "jpy": "JPY",
    "peso argentino": "ARS", "ars": "ARS",
    "real": "BRL", "reais": "BRL", "brl": "BRL",
}

_KNOWN_CONVERT_UNITS = {
    "km", "quilometro", "quilometros", "kilometro", "kilometros",
    "m", "metro", "metros", "cm", "centimetro", "centimetros", "mm", "milimetro", "milimetros",
    "mi", "milha", "milhas", "yd", "jarda", "jardas", "ft", "pe", "pes", "in", "polegada", "polegadas",
    "kg", "quilo", "quilos", "quilograma", "quilogramas", "kilo", "kilos",
    "g", "grama", "gramas", "mg", "miligrama", "miligramas",
    "t", "ton", "tonelada", "toneladas", "lb", "lbs", "libra", "libras", "oz", "onca", "oncas",
    "c", "celsius", "grau celsius", "graus celsius", "centigrados",
    "f", "fahrenheit", "grau fahrenheit", "graus fahrenheit", "k", "kelvin",
    "l", "litro", "litros", "ml", "mililitro", "mililitros", "gal", "galao", "galoes",
    "brl", "real", "reais", "r$", "usd", "dolar", "dolares", "us$", "$",
    "eur", "euro", "euros", "gbp", "libra esterlina", "libras esterlinas",
    "ars", "peso argentino", "pesos argentinos", "jpy", "iene", "ienes",
}


def _is_known_convert_unit(unit_str: str) -> bool:
    norm_u = normalize_text(unit_str).replace("°", "").strip()
    norm_u = re.sub(r"\s+", " ", norm_u)
    return norm_u in _KNOWN_CONVERT_UNITS


def extract_convert_units(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Conversão de unidades físicas, moedas e cotações sem valor numérico."""
    clean_raw = raw.strip().rstrip("?!.,;:")

    # Bloqueia colisão com corridas 99 ("peça um 99 para o shopping...")
    if re.search(r"\b(?:um|o|de|no|na|chama|chamar|peca|pede|pedir|solicita|solicitar)\s+99\b", norm):
        return 0.0, None

    # 1. Cotação de moeda sem número explícito ("qual a cotação do dólar hoje", "quanto tá o euro hoje", "valor da libra")
    if not re.search(r"\b(?:pesquisa|pesquise|pesquisar|google)\b", norm):
        m_quote = re.search(
            r"\b(?:(?:cotacao|valor|preco)\s+(?:do|da|de)|quanto\s+(?:ta|esta(?:\s+valendo)?|custa|vale))\s+(?:o\s+|a\s+)?(dolar|dolares|euro|euros|libra(?:\s+esterlina)?|iene|peso\s+argentino|usd|eur|gbp|jpy|ars)\b(?:\s+(?:em|para|pra)\s+(real|reais|brl|dolar|usd|euro|eur))?",
            norm,
        )
        if m_quote:
            from_cur = _CURRENCY_QUOTE_MAP.get(m_quote.group(1).strip())
            to_cur = _CURRENCY_QUOTE_MAP.get((m_quote.group(2) or "").strip(), "BRL")
            if from_cur:
                return 0.96, _format_call("convert_units", amount=1.0, from_unit=from_cur, to_unit=to_cur)

    # 2. Padrão invertido: "quantos reais são 100 euros?"
    m_inv = re.search(
        r"quantos?\s+([a-zA-ZÀ-ÿ$\s]{1,25}?)\s+(?:s[aã]o|tem|equivalem?\s+a)\s+(\d+(?:[.,]\d+)?)\s*(?:graus?\s+)?([a-zA-ZÀ-ÿ$°\s]{1,25})$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_inv:
        to_u = re.sub(r"^(?:em|de|graus?)\s+", "", m_inv.group(1).strip(), flags=re.IGNORECASE).strip()
        amt = float(m_inv.group(2).replace(",", "."))
        from_u = re.sub(r"^(?:de|graus?)\s+", "", m_inv.group(3).strip(), flags=re.IGNORECASE).strip()
        if _is_known_convert_unit(from_u) and _is_known_convert_unit(to_u):
            return 0.96, _format_call("convert_units", amount=amt, from_unit=from_u, to_unit=to_u)

    # 3. Padrão direto: "converter 50 dólares para reais", "32 graus celsius em fahrenheit", "quanto dá 5 libras em quilos"
    m_dir = re.search(
        r"(?:(?:converter|converte|converta|transformar|transforma|quanto\s+(?:d[aá]|[eé]|valem?))\s+)?(\d+(?:[.,]\d+)?)\s*(?:graus?\s+)?([a-zA-ZÀ-ÿ$°\s]{1,25}?)\s+(?:para|em|pra)\s+(?:graus?\s+)?([a-zA-ZÀ-ÿ$°\s]{1,25})$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_dir:
        amt = float(m_dir.group(1).replace(",", "."))
        from_u = re.sub(r"^(?:de|graus?)\s+", "", m_dir.group(2).strip(), flags=re.IGNORECASE).strip()
        to_u = re.sub(r"^(?:de|graus?)\s+", "", m_dir.group(3).strip(), flags=re.IGNORECASE).strip()
        if _is_known_convert_unit(from_u) and _is_known_convert_unit(to_u):
            return 0.96, _format_call("convert_units", amount=amt, from_unit=from_u, to_unit=to_u)

    return 0.0, None


def extract_summarize_notifications(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Resumo inteligente e filtrado de notificações ativas."""
    notif_triggers = (
        "algo importante nas notificacoes", "algo importante na notificacao",
        "resume minhas notificacoes", "resumir notificacoes", "resuma minhas notificacoes",
        "resuma as notificacoes", "resumo das notificacoes", "resumo de notificacoes",
        "notificacoes do ", "notificacoes da ", "notificacoes de ",
        "chegou alguma mensagem", "chegou mensagem",
    )
    if any(t in norm for t in notif_triggers):
        app_filter = ""
        m_app = re.search(r"notificac(?:ao|oes)\s+(?:do|da|de)\s+([a-zA-Z0-9_\s]{2,30})", norm)
        if m_app:
            app_filter = m_app.group(1).strip().rstrip("?!.,;:")
            if app_filter in ("celular", "android", "sistema"):
                app_filter = ""
        return 0.95, _format_call("summarize_notifications", app_filter=app_filter)
    return 0.0, None


def extract_navigate_to(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Navegação GPS curva a curva (Google Maps / Waze), sem colidir com Uber/99."""
    if any(w in norm for w in ("uber", "corrida", "taxi")) or re.search(r"\b99\b|noventa\s+e\s+nove", norm):
        return 0.0, None

    nav_cues = (
        "me leva", "leva ate", "inicia rota", "iniciar rota", "traca rota", "tracar rota",
        "rota para", "rota pra", "rota pro",
        "navegacao", "navegar", "como chegar", "waze", "google maps", "no maps",
    )
    if not any(c in norm for c in nav_cues):
        return 0.0, None

    m_nav = re.search(
        r"(?:me\s+leva|leva|levar|inicia|iniciar|abre|abrir|tra[çc]a|tra[çc]ar|como\s+chegar|navega|navegar|rota)\s+"
        r"(?:uma\s+)?(?:rota|navega[çc][ãa]o|caminho)?\s*(?:para|pro|pra|at[eé]|no|na)\s+(.+)",
        raw.strip().rstrip("?!.,;:"),
        re.IGNORECASE,
    )
    if not m_nav:
        return 0.0, None

    dest = m_nav.group(1).strip()
    app_val = "waze" if "waze" in norm else "maps"
    dest = re.sub(r"(?i)\s+(?:no|pelo|via)\s+(?:waze|google\s+maps|maps)$", "", dest).strip()
    dest = re.sub(r"(?i)^(?:o|a|os|as)\s+", "", dest).strip()
    if dest:
        return 0.97, _format_call("navigate_to", destination=dest, app=app_val)
    return 0.0, None


def extract_play_media(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Busca e reprodução de música, artista, playlist ou vídeo (Spotify / YouTube / padrão)."""
    if any(w in norm for w in ("alarme", "timer", "uber", "corrida", "99", "ifood", "volume", "brilho")):
        return 0.0, None

    m_play = re.search(
        r"^(?:silva,?\s*)?(?:toca|tocar|toque|coloca|colocar|coloque|p[oõ]e|por|reproduz|reproduzir)\s+(.+)$",
        raw.strip().rstrip("?!.,;:"),
        re.IGNORECASE,
    )
    if not m_play:
        return 0.0, None

    body = m_play.group(1).strip()
    norm_body = normalize_text(body)
    # Comandos simples de transporte ficam em extract_media_control
    if norm_body in ("musica", "a musica", "o som", "som", "a faixa", "faixa", "a midia", "midia", "o video", "video", "play", "de novo"):
        return 0.0, None

    app_val = ""
    if re.search(r"\b(?:youtube\s+music|yt\s+music)\b", norm_body):
        app_val = "youtube music"
    elif re.search(r"\b(?:youtube|yt)\b", norm_body):
        app_val = "youtube"
    elif "spotify" in norm_body:
        app_val = "spotify"

    query = re.sub(r"(?i)\s+(?:no|na|pelo|via)\s+(?:spotify|youtube\s+music|yt\s+music|youtube|yt)$", "", body).strip()
    query = re.sub(r"(?i)^(?:uma\s+m[uú]sica\s+de|m[uú]sica\s+de|uma\s+m[uú]sica|um\s+v[ií]deo\s+de|v[ií]deo\s+de|um\s+v[ií]deo|uma\s+playlist\s+de|playlist\s+de)\s+", "", query).strip()
    if query:
        return 0.96, _format_call("play_media", query=query, app=app_val)
    return 0.0, None


def extract_lists(raw: str, norm: str) -> Tuple[float, Optional[str]]:
    """Listas dinâmicas persistentes (compras, tarefas, etc.)."""
    clean_raw = raw.strip().rstrip("?!.,;:")

    # 1. Consultar todas as listas
    if re.search(r"\bquais\s+(?:sao\s+)?(?:as\s+)?minhas\s+listas\b", norm):
        return 0.97, _format_call("get_list", list_name="todas")

    # 2. O que falta comprar
    if re.search(r"\bo\s+que\s+(?:falta|precisa|tenho\s+(?:que|de))\s+comprar\b", norm):
        return 0.97, _format_call("get_list", list_name="compras")

    # 3. Limpar lista inteira
    m_clear = re.search(
        r"^(?:silva,?\s*)?(?:limpa|limpar|limpe|esvazia|esvaziar|esvazie|apaga|apagar|apague)\s+(?:toda\s+)?(?:a\s+)?(?:minha\s+)?lista(?:\s+(?:de|do|da)\s+([a-zA-ZÀ-ÿ0-9_\s]+))?$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_clear:
        lname = (m_clear.group(1) or "compras").strip()
        return 0.97, _format_call("remove_list_item", item="tudo", list_name=lname)

    # 4. Remover item específico da lista
    m_rem = re.search(
        r"^(?:silva,?\s*)?(?:tira|tirar|tire|remove|remover|remova|apaga|apagar|apague|deleta|deletar|delete|risca|riscar)\s+"
        r"(?:o\s+|a\s+|os\s+|as\s+)?(.+?)\s+(?:da|do)\s+(?:minha\s+)?(?:lista(?:\s+(?:de|do|da)\s+([a-zA-ZÀ-ÿ0-9_\s]*))?|(mercado|supermercado))$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_rem:
        item_val = m_rem.group(1).strip()
        lname = (m_rem.group(2) or m_rem.group(3) or "compras").strip() or "compras"
        if item_val:
            return 0.97, _format_call("remove_list_item", item=item_val, list_name=lname)

    # 5. Adicionar item(ns) na lista
    m_add = re.search(
        r"^(?:silva,?\s*)?(?:coloca|colocar|coloque|bota|botar|bote|adiciona|adicionar|adicione|p[oõ]e|por|inclui|incluir|insere|inserir)\s+"
        r"(.+?)\s+(?:na|no|para\s+a|para\s+o|pra)\s+(?:minha\s+)?(?:lista\s+(?:de|do|da)\s+)?([a-zA-ZÀ-ÿ0-9_\s]+)$",
        clean_raw,
        re.IGNORECASE,
    )
    if m_add:
        item_val = m_add.group(1).strip()
        lname = m_add.group(2).strip()
        norm_lname = normalize_text(lname)
        if any(k in norm_lname for k in ("compra", "mercado", "supermercado", "feira", "tarefa", "afazer", "viagem", "farmacia", "lista")):
            lname_clean = re.sub(r"^(?:lista\s+de\s+|lista\s+do\s+|lista\s+da\s+)", "", lname, flags=re.IGNORECASE).strip() or "compras"
            if item_val:
                return 0.97, _format_call("add_list_item", item=item_val, list_name=lname_clean)

    # 6. Consultar lista específica
    m_get = re.search(
        r"(?:o\s+que\s+tem\s+na|l[eê]|leia|ler|mostra|mostre|ver|veja|qual\s+(?:[eé]\s+)?a)\s+"
        r"(?:minha\s+)?lista(?:\s+(?:de|do|da)\s+([a-zA-ZÀ-ÿ0-9_\s]+))?",
        clean_raw,
        re.IGNORECASE,
    )
    if m_get:
        lname = (m_get.group(1) or "compras").strip() or "compras"
        return 0.97, _format_call("get_list", list_name=lname)

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
            extract_datetime,
            extract_system_info,
            extract_read_screen,
            extract_save_contact,
            extract_get_contact,
            extract_connectivity_controls,
            extract_navigate_to,
            extract_play_media,
            extract_lists,
            extract_news,
            extract_contact_alias,
            extract_manage_sleep,
            extract_sleep_report,
            extract_voice_notes,
            extract_record_audio,
            extract_convert_units,
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
            extract_remind_on_wifi,
            extract_schedule,
            extract_memory,
            extract_summarize_notifications,
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

    MIN_CONFIDENCE_MARGIN = 0.12

    @staticmethod
    def _extract_func_name(call_str: str) -> str:
        m = re.match(r"<call>([a-zA-Z0-9_]+)\(", (call_str or "").strip())
        return m.group(1) if m else ""

    @staticmethod
    def _is_negation_or_past_narrative(norm_cmd: str) -> bool:
        """Camada 4: Guarda global de negações explícitas e narrativas no passado sem imperativo."""
        if re.match(r"^(?:nao|nunca|jamais|para\s+de|pare\s+de)\s+", norm_cmd):
            return True
        if norm_cmd.startswith(("cancela isso", "deixa pra la", "nao precisa")):
            return True
        if re.match(
            r"^(?:ontem\s+eu|hoje\s+eu\s+(?:ja|gastei|comprei|pedi|fui|viajei|paguei)|semana\s+passada\s+eu|eu\s+comprei|eu\s+viajei|eu\s+gastei|gastei)\b",
            norm_cmd,
        ):
            return True
        return False

    def _resolve_tie_break(self, candidates: List[Tuple[float, str, str]], norm_cmd: str) -> Optional[str]:
        """Camada 5: Tabela explícita de desempate quando top1 - top2 < MIN_CONFIDENCE_MARGIN."""
        top1_score, top1_call, top1_fn = candidates[0]
        top2_score, top2_call, top2_fn = candidates[1]
        pair = {top1_fn, top2_fn}

        # 1. recall_note > connect_wifi / get_wifi_info quando houver "senha" ou "qual e"
        if "recall_note" in pair and (pair & {"connect_wifi", "get_wifi_info"}) and any(
            w in norm_cmd for w in ("senha", "qual e", "qual a")
        ):
            return top1_call if top1_fn == "recall_note" else top2_call

        # 2. request_ride > convert_units quando houver verbo de transporte ou destino
        if pair == {"request_ride", "convert_units"}:
            return top1_call if top1_fn == "request_ride" else top2_call

        # 3. order_food > open_app quando houver referência a comida/prato/pedido
        if pair == {"order_food", "open_app"} and _has_food_domain(norm_cmd):
            return top1_call if top1_fn == "order_food" else top2_call

        # 4. send_whatsapp / send_sms > request_ride / open_app quando a ação principal é enviar mensagem
        if (pair & {"send_whatsapp", "send_sms"}) and (pair & {"request_ride", "open_app"}):
            return top1_call if top1_fn in ("send_whatsapp", "send_sms") else top2_call

        # 5. remind_on_wifi > set_wifi_state / set_bluetooth_state / connect_wifi quando condicional
        if "remind_on_wifi" in pair and (pair & {"set_wifi_state", "set_bluetooth_state", "connect_wifi"}):
            return top1_call if top1_fn == "remind_on_wifi" else top2_call

        if top1_score < 0.65:
            return None
        return top1_call

    def route(self, raw_cmd: str) -> Optional[str]:
        """Avalia todos os extratores e retorna a chamada da melhor intenção."""
        if not raw_cmd or not raw_cmd.strip():
            return None

        raw_clean, norm_cmd = _prepare_texts(raw_cmd)
        if not raw_clean or not norm_cmd:
            return None

        # Camada 4: Guarda global de negações explícitas e narrativas no passado
        if self._is_negation_or_past_narrative(norm_cmd):
            return _format_call("none")

        # Bloqueia perguntas conceituais para que o LLM responda
        if self.is_conceptual_question(norm_cmd):
            return None

        candidates: List[Tuple[float, str, str]] = []
        for extractor in self.extractors:
            try:
                score, call_str = extractor(raw_clean, norm_cmd)
                if score > 0 and call_str:
                    candidates.append((score, call_str, self._extract_func_name(call_str)))
            except Exception:
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0], reverse=True)
        top1_score, top1_call, top1_fn = candidates[0]
        if top1_score < 0.5:
            return None

        # Camada 5: Margem mínima de confiança + desempate explícito
        if len(candidates) >= 2:
            top2_score, _, top2_fn = candidates[1]
            if top1_fn != top2_fn and (top1_score - top2_score) < self.MIN_CONFIDENCE_MARGIN:
                return self._resolve_tie_break(candidates, norm_cmd)

        return top1_call
