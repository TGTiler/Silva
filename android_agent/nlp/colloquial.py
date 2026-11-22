"""
Normalizador de gírias, expressões coloquiais de celular e tolerância a typos via difflib.
Permite compreensão de termos populares (zap, no talo, mudo) e corrige erros de digitação rápidos.
"""

import difflib
import re
from typing import Set


CANONICAL_VOCAB = [
    "bateria", "lanterna", "calculadora", "calcula", "alarme", "timer",
    "cronometro", "notificacoes", "localizacao", "temperatura", "previsao",
    "screenshot", "volume", "brilho", "bluetooth", "whatsapp", "instagram",
    "telegram", "youtube", "spotify", "tiktok", "uber", "ifood", "camera",
    "selfie", "silencioso", "perturbe"
]

STOPWORDS_PT: Set[str] = {
    "agora", "favor", "depois", "sobre", "quando", "onde", "quem", "como",
    "quanto", "quantos", "quanta", "quantas", "minha", "minhas", "nosso", "nossa",
    "estou", "estava", "estive", "posso", "poder", "fazer", "tenho", "tinha",
    "falar", "dizer", "pedir", "chamar", "mandar", "enviar", "abrir", "ligar",
    "tempo", "clima", "segunda", "terca", "quarta", "quinta", "sexta", "sabado",
    "domingo", "manha", "tarde", "noite", "madrugada", "cidade", "estado",
    "brasil", "recife", "paulista", "olinda", "salvar", "anotar", "lembrar"
}


def _normalize_token_simple(token: str) -> str:
    """Normalização leve para comparação fuzzy (sem acentos e minúsculo)."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", token.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_colloquial_ptbr(text: str) -> str:
    """
    Normaliza gírias de celular, expressões de volume/brilho e corrige
    pequenos erros de digitação (typos) em palavras-chave de comando.
    """
    if not text:
        return ""

    s = text

    # 1. Expressões de nível (Volume / Brilho / Áudio / Tela)
    level_ctx = bool(re.search(r"\b(?:volume|som|brilho|tela|audio|áudio|luz|musica|música)\b", s, re.IGNORECASE))
    
    # "no talo" é quase exclusivamente 100%
    s = re.sub(r"\bno\s+talo\b", "100%", s, flags=re.IGNORECASE)
    
    if level_ctx:
        s = re.sub(r"\b(?:total(?:mente)?|no\s+m[aá]ximo|ao\s+m[aá]ximo|m[aá]ximo|no\s+[uú]ltimo|completo|tudo)\b", "100%", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:no\s+m[ií]nimo|ao\s+m[ií]nimo|m[ií]nimo|no\s+mudo|zerado|zero|mudo|silenciar)\b", "0%", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:na\s+metade|metade|meio\s+termo|meio)\b", "50%", s, flags=re.IGNORECASE)
    else:
        # Padrões com verbos de ação para volume/brilho ("bota no máximo", "deixa mudo", "aumente total")
        s = re.sub(r"\b(?:bota|coloca|deixa|define|aumenta|aumente|diminui|diminua)\s+no\s+m[aá]ximo\b", r"\g<0> 100%", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(?:bota|coloca|deixa|define|aumenta|aumente)\s+total(?:mente)?\b", r"\g<0> 100%", s, flags=re.IGNORECASE)

    # 2. Gírias de Aplicativos e Serviços
    app_slang = [
        (r"\b(?:zap\s*zap|zapzap|zap|wpp|whats)\b", "whatsapp"),
        (r"\binsta\b", "instagram"),
        (r"\bface\b", "facebook"),
        (r"\bplay\s*store\b|\bplaystore\b|\bloja\s+de\s+apps\b", "play store"),
        (r"\bspot\b", "spotify"),
    ]
    for pat, repl in app_slang:
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)

    # 'yt' e 'tubo' para youtube em contexto claro
    s = re.sub(r"\b(?:no|no\s+app|abre\s+o|no)\s+yt\b", " no youtube", s, flags=re.IGNORECASE)
    s = re.sub(r"\byoutube\b|\byt\b", "youtube", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(?:no|pelo)\s+tubo\b", "no youtube", s, flags=re.IGNORECASE)

    # 3. Correção Fuzzy Leve via difflib para palavras de comando com erros de digitação
    # Ex: 'baterria' -> 'bateria', 'lanterana' -> 'lanterna', 'calcura' -> 'calcula'
    tokens = re.findall(r"\w+|[^\w\s]|\s+", s)
    result_tokens = []

    for tok in tokens:
        if not re.match(r"^\w+$", tok):
            result_tokens.append(tok)
            continue

        raw_low = tok.lower()
        norm_low = _normalize_token_simple(tok)

        # Se tiver menos de 5 caracteres ou for dígito ou stopword, mantém
        if len(norm_low) < 5 or norm_low.isdigit() or norm_low in STOPWORDS_PT:
            result_tokens.append(tok)
            continue

        # Se já estiver no vocabulário canônico exato, mantém
        if norm_low in CANONICAL_VOCAB:
            result_tokens.append(tok)
            continue

        # Busca aproximação com threshold 0.82
        matches = difflib.get_close_matches(norm_low, CANONICAL_VOCAB, n=1, cutoff=0.82)
        if matches:
            corrected = matches[0]
            # Preserva capitalização se a primeira letra era maiúscula
            if tok[0].isupper():
                corrected = corrected.capitalize()
            result_tokens.append(corrected)
        else:
            result_tokens.append(tok)

    return "".join(result_tokens)
