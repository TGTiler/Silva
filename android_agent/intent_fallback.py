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
        _prepare_texts,
        _format_call,
        _protect_compound_names,
        _mask_protected_entities,
    )
except ImportError:
    from nlp import (
        parse_ptbr_numbers,
        normalize_colloquial_ptbr,
        ScoredIntentRouter,
        normalize_text,
        _prepare_texts,
        _format_call,
        _protect_compound_names,
        _mask_protected_entities,
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
    "salve", "salva", "salvar", "guarda", "guarde", "guardar",
    "pesquise", "pesquisa", "pesquisar", "busque", "busca", "buscar",
    "baixe", "baixa", "baixar", "instale", "instala", "instalar", "leia", "ler", "mostre", "mostrar",
    "veja", "ver", "ve", "vê", "qual", "quais", "quanto", "quantos", "tempo", "clima", "calcula", "calcule",
    "vibra", "vibrar", "aumenta", "aumentar", "diminui", "diminuir", "tire", "tira", "tirar",
    "grave", "grava", "gravar", "silencie", "silencia", "muta", "mutar"
}

_ANAPHORA_REF_RE = (
    r"(?:isso|disso|esse\s+resultado|o\s+resultado|essa\s+informa[çc][ãa]o|"
    r"esse\s+valor|o\s+valor|a\s+previs[ãa]o|a\s+cota[çc][ãa]o|quanto\s+deu)"
)

_PIPE_WPP_RE = re.compile(
    rf"^(?:envia|enviar|envie|manda|mandar|mande|fala|falar|fale)\s+"
    rf"(?:{_ANAPHORA_REF_RE}\s+)?(?:no|pelo|via)?\s*(?:whatsapp|zap|wpp)\s+"
    rf"(?:para|pro|pra|com)\s+(?:o\s+|a\s+)?(.+?)$",
    re.IGNORECASE,
)

_PIPE_SMS_RE = re.compile(
    rf"^(?:envia|enviar|envie|manda|mandar|mande)\s+{_ANAPHORA_REF_RE}\s+"
    rf"(?:por\s+sms\s+)?(?:para|pro|pra)\s+(.+?)(?:\s+por\s+sms)?$",
    re.IGNORECASE,
)

_PIPE_SAVE_RE = re.compile(
    rf"^(?:anota|anotar|anote|salva|salvar|salve|lembra|lembrar|lembre|guarda|guardar|guarde)"
    rf"(?:\s+{_ANAPHORA_REF_RE})?"
    rf"(?:\s+(?:na\s+mem[óo]ria))?"
    rf"(?:\s+como\s+(.+?))?"
    rf"(?:\s+(?:na\s+mem[óo]ria))?$",
    re.IGNORECASE,
)


def _infer_key_from_prev_call(prev_call: str) -> str:
    """Infere uma chave descritiva curta a partir da chamada <call> anterior."""
    m_query = re.search(r"query=(['\"])(.*?)\1", prev_call)
    if m_query and m_query.group(2).strip():
        return m_query.group(2).strip()[:60]
    m_loc = re.search(r"location=(['\"])(.*?)\1", prev_call)
    if m_loc and m_loc.group(2).strip():
        return f"clima {m_loc.group(2).strip()}"[:60]
    m_func = re.match(r"<call>([a-zA-Z0-9_]+)\(", prev_call.strip())
    func = m_func.group(1) if m_func else ""
    defaults = {
        "get_battery": "bateria",
        "get_weather": "previsão do tempo",
        "calculate": "cálculo",
        "search_google": "pesquisa",
        "get_location": "localização",
        "get_wifi_info": "wi-fi",
        "read_screen": "conteúdo da tela",
        "get_datetime": "data e hora",
        "get_system_info": "sistema",
    }
    return defaults.get(func, "anotação")


def _resolve_piped_clause(clause: str, prev_calls: List[str]) -> Optional[str]:
    """
    Resolve cláusulas dependentes que referenciam o resultado da cláusula anterior
    via pronomes anafóricos ('isso', 'o resultado', 'esse valor', etc.),
    emitindo chamadas com o token '$prev_result'.
    """
    if not prev_calls:
        return None
    clean_clause = clause.strip().rstrip("?!.,;:")
    m_wpp = _PIPE_WPP_RE.match(clean_clause)
    if m_wpp:
        target = m_wpp.group(1).strip()
        if target:
            return _format_call("send_whatsapp", contact_name=target, message="$prev_result")

    m_sms = _PIPE_SMS_RE.match(clean_clause)
    if m_sms:
        target = m_sms.group(1).strip()
        if target:
            return _format_call("send_sms", number=target, message="$prev_result")

    m_save = _PIPE_SAVE_RE.match(clean_clause)
    if m_save:
        custom_key = (m_save.group(1) or "").strip()
        key = custom_key if custom_key else _infer_key_from_prev_call(prev_calls[-1])
        return _format_call("remember_note", key=key, value="$prev_result")

    return None


# Instância singleton do roteador de pontuação
_ROUTER = ScoredIntentRouter()


def parse_single_intent(raw_cmd: str) -> Optional[str]:
    """
    Tenta identificar uma intenção única e retornar uma tag <call>...</call>.
    Aplica normalização estrutural de espaços/quebras de linha,
    números compostos, normalização de gírias e pontuação ponderada.
    """
    if not raw_cmd or not raw_cmd.strip():
        return None

    raw_clean, _ = _prepare_texts(raw_cmd)
    if not raw_clean:
        return None

    masked_cmd = _mask_protected_entities(raw_clean)
    parsed_cmd = parse_ptbr_numbers(masked_cmd)
    normalized_cmd = normalize_colloquial_ptbr(parsed_cmd)

    return _ROUTER.route(normalized_cmd)


def _should_skip_clause_split(text: str) -> bool:
    """
    Camada 6: Protege cláusulas únicas de serem quebradas em 'e' / 'depois' / ';'
    quando pertencem a listas de itens, corpo de mensagem (WhatsApp/SMS) ou rotas/destinos.
    """
    norm = normalize_text(text)
    if re.search(r"\b(?:na|da|do)\s+lista\b", norm) and any(
        v in norm for v in ("coloca", "coloque", "adiciona", "adicione", "bota", "bote", "tira", "tire", "remove", "remova")
    ):
        return True
    if re.search(r"\b(?:whatsapp|zap|wpp|sms)\b", norm) and re.search(
        r"\b(?:dizendo|falando|escrevendo|com\s+a\s+mensagem)\b", norm
    ):
        return True
    if re.search(r"\b(?:rota|como\s+chegar|navega(?:r)?)\b", norm):
        return True
    return False


def match_intent_fallback(user_prompt: str) -> Optional[str]:
    """
    Roteador de intenções composto (Pilar D) com blindagem universal contra erros de formatação.
    1. Normalização Estrutural Única: unifica \n, \r, tabs e múltiplos espaços em um único espaço,
       preservando maiúsculas e símbolos técnicos.
    2. Protege nomes de cidades e expressões compostas com 'e'.
    3. Converte números compostos ('vinte e cinco' -> '25') antes do splitter de frases.
    4. Normaliza gírias de celular ('no talo' -> '100%', 'zap' -> 'whatsapp') e corrige typos.
    5. Divide cláusulas encadeadas por conectores fortes e 'e' condicional a verbos.
    6. Concatena chamadas múltiplas ou retorna intenção única.
    """
    if not user_prompt:
        return None

    # 1. Normalização Estrutural Única na Entrada: unifica quebras de linha e espaços múltiplos
    raw_clean, _ = _prepare_texts(user_prompt)
    if not raw_clean:
        return None

    # Caso especial: Instalação ou busca combinada na Play Store
    if re.search(r"(?i)\babre\s+(?:a|o)?\s*(?:play\s*store|playstore|google\s+play)\s+e\s+(?:baixa|instala|procura|pesquisa|busca)\b", raw_clean):
        single = parse_single_intent(raw_clean)
        if single:
            return single

    # 2. Protege nomes compostos e entidades numéricas de marcas/redes (Camada 1)
    protected = _protect_compound_names(_mask_protected_entities(raw_clean))

    # 3. Converte números compostos (Pilar A) ANTES do splitter de frases
    num_normalized = parse_ptbr_numbers(protected)

    # 4. Normaliza gírias e erros de digitação (Pilar B)
    colloquial_normalized = normalize_colloquial_ptbr(num_normalized)

    # Camada 6: Evita split de cláusulas únicas (listas, corpo de mensagem, rotas compostas)
    if _should_skip_clause_split(colloquial_normalized):
        return _ROUTER.route(colloquial_normalized)

    # Fast-path: sem conectores compostos, roteia diretamente (< 2ms)
    low_col = colloquial_normalized.lower()
    if ";" not in low_col and " e " not in low_col and " depois " not in low_col and " em seguida " not in low_col:
        return _ROUTER.route(colloquial_normalized)

    # 5. Divisão primária por separadores fortes
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
            piped_call = _resolve_piped_clause(clause, matched_calls)
            call = piped_call if piped_call else _ROUTER.route(clause)
            if call:
                matched_calls.append(call)

    # Deduplica chamadas idênticas consecutivas (ex: 'qual meu ip e qual wifi estou conectado')
    unique_calls = []
    for call in matched_calls:
        if not unique_calls or call != unique_calls[-1]:
            unique_calls.append(call)

    if len(unique_calls) >= 2:
        return "".join(unique_calls)
    if len(unique_calls) == 1 and len(matched_calls) >= 2:
        return unique_calls[0]

    # Caso não seja comando composto, avalia o prompt normalizado
    return _ROUTER.route(colloquial_normalized)
