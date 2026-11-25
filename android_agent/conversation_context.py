"""
Gerenciador thread-safe de memória conversacional de curto prazo (multi-turno)
e resolução anafórica determinística para o micro-agente Silva.
"""

import re
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

try:
    from .nlp import normalize_text
except ImportError:
    try:
        from nlp import normalize_text
    except ImportError:
        from android_agent.nlp import normalize_text

SESSION_TTL_SECONDS = 30 * 60  # 30 minutos
MAX_RECENT_TURNS = 6

_CTX_LOCK = threading.RLock()
_SESSIONS: Dict[str, Dict[str, Any]] = {}

_DEFAULT_KEYS_BY_TOOL = {
    "get_battery": "bateria",
    "get_weather": "previsão do tempo",
    "calculate": "cálculo",
    "search_google": "pesquisa",
    "get_location": "localização",
    "get_last_location": "última localização",
    "get_wifi_info": "wi-fi",
    "get_clipboard": "clipboard",
    "get_notifications": "notificações",
    "get_last_sms": "último sms",
}

_DAY_FOLLOWUP_PATTERN = re.compile(
    r"^(?:e\s+)?(?:para\s+|pra\s+)?("
    r"hoje|amanh[ãa]|depois\s+de\s+amanh[ãa]|"
    r"segunda(?:-feira)?|ter[çc]a(?:-feira)?|quarta(?:-feira)?|"
    r"quinta(?:-feira)?|sexta(?:-feira)?|s[áa]bado|domingo|"
    r"[àa]\s+noite|de\s+noite|noite|de\s+tarde|[àa]\s+tarde|tarde|"
    r"de\s+manh[ãa]|pela\s+manh[ãa]|manh[ãa]|de\s+madrugada|madrugada"
    r")$",
    re.IGNORECASE,
)

_CITY_FOLLOWUP_PATTERN = re.compile(
    r"^e\s+(?:em|para|pra|no|na)\s+([a-zA-ZÀ-ÿ0-9\s,\-_]{2,50})$",
    re.IGNORECASE,
)

_SAVE_ANAPHORA_PATTERN = re.compile(
    r"^(?:silva,?\s*)?(?:anota|anotar|anote|salva|salvar|salve|lembra|lembrar|lembre|guarda|guardar|guarde)\s+"
    r"(?:isso|disso|esse\s+resultado|o\s+resultado|essa\s+informa[çc][ãa]o|esse\s+valor|o\s+valor|"
    r"a\s+previs[ãa]o|a\s+cota[çc][ãa]o|quanto\s+deu)"
    r"(?:\s+(?:na\s+mem[óo]ria))?"
    r"(?:\s+como\s+(.+?))?"
    r"(?:\s+(?:na\s+mem[óo]ria))?$",
    re.IGNORECASE,
)

_WPP_ANAPHORA_PATTERN = re.compile(
    r"^(?:silva,?\s*)?(?:envia|enviar|envie|manda|mandar|mande)\s+"
    r"(?:isso|esse\s+resultado|o\s+resultado|essa\s+informa[çc][ãa]o|esse\s+valor|o\s+valor|"
    r"a\s+previs[ãa]o|a\s+cota[çc][ãa]o|quanto\s+deu)\s+"
    r"(?:no|pelo|via)?\s*(?:whatsapp|zap|wpp)\s+(?:para|pro|pra)\s+(?:o\s+|a\s+)?(.+?)$",
    re.IGNORECASE,
)

_SMS_ANAPHORA_PATTERN = re.compile(
    r"^(?:silva,?\s*)?(?:envia|enviar|envie|manda|mandar|mande)\s+"
    r"(?:isso|esse\s+resultado|o\s+resultado|essa\s+informa[çc][ãa]o|esse\s+valor|o\s+valor|"
    r"a\s+previs[ãa]o|a\s+cota[çc][ãa]o|quanto\s+deu)\s+"
    r"(?:por\s+sms\s+)?(?:para|pro|pra)\s+(.+?)(?:\s+por\s+sms)?$",
    re.IGNORECASE,
)


def _new_session(now: float) -> Dict[str, Any]:
    return {
        "recent_turns": deque(maxlen=MAX_RECENT_TURNS),
        "last_tool": "",
        "last_args": {},
        "last_result_text": "",
        "last_entities": {"location": "", "contact": "", "query": ""},
        "updated_at": now,
    }


def _cleanup_expired_sessions(now: float) -> None:
    expired = [
        sid for sid, data in _SESSIONS.items()
        if (now - data.get("updated_at", 0.0)) > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        del _SESSIONS[sid]


def _normalize_session_id(session_id: Optional[str]) -> str:
    sid = (session_id or "default").strip()
    return sid or "default"


def _clean_result_summary(text: str, max_len: int = 300) -> str:
    clean = re.sub(r"\s+", " ", (text or "").strip())
    if len(clean) > max_len:
        return clean[: max_len - 3].rstrip() + "..."
    return clean


def _format_call_literal(func_name: str, **kwargs: Any) -> str:
    args_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
    return f"<call>{func_name}({args_str})</call>"


def get_session_state(session_id: str = "default") -> Dict[str, Any]:
    """Retorna um snapshot seguro do estado conversacional da sessão."""
    sid = _normalize_session_id(session_id)
    now = time.time()
    with _CTX_LOCK:
        _cleanup_expired_sessions(now)
        sess = _SESSIONS.get(sid)
        if not sess:
            return {
                "recent_turns": [],
                "last_tool": "",
                "last_args": {},
                "last_result_text": "",
                "last_entities": {"location": "", "contact": "", "query": ""},
            }
        return {
            "recent_turns": list(sess["recent_turns"]),
            "last_tool": sess["last_tool"],
            "last_args": dict(sess["last_args"]),
            "last_result_text": sess["last_result_text"],
            "last_entities": dict(sess["last_entities"]),
        }


def update_session_state(session_id: str, user_text: str, exec_result: Dict[str, Any]) -> None:
    """Atualiza o histórico recente, última ferramenta e entidades extraídas da sessão."""
    sid = _normalize_session_id(session_id)
    now = time.time()
    clean_user = (user_text or "").strip()

    with _CTX_LOCK:
        _cleanup_expired_sessions(now)
        sess = _SESSIONS.get(sid)
        if not sess:
            sess = _new_session(now)
            _SESSIONS[sid] = sess

        sess["updated_at"] = now

        calls = exec_result.get("calls") or []
        successful_calls = [
            c for c in calls
            if c.get("status") != "error" and c.get("func_name") and c.get("func_name") != "none"
        ]

        last_call = successful_calls[-1] if successful_calls else None
        func_name = last_call.get("func_name", "") if last_call else exec_result.get("func_name", "")
        args = dict(last_call.get("args") or {}) if last_call else {}
        result_msg = (exec_result.get("message") or "").strip()

        if clean_user:
            sess["recent_turns"].append({
                "role": "user",
                "text": clean_user,
                "func_name": func_name,
                "args": args,
                "result_summary": "",
                "timestamp": now,
            })

        if result_msg:
            sess["recent_turns"].append({
                "role": "assistant",
                "text": result_msg,
                "func_name": func_name,
                "args": args,
                "result_summary": _clean_result_summary(result_msg),
                "timestamp": now,
            })

        if last_call and exec_result.get("status") != "error":
            sess["last_tool"] = func_name
            sess["last_args"] = args
            sess["last_result_text"] = (last_call.get("message") or result_msg).strip()

            entities = sess["last_entities"]
            if func_name == "get_weather":
                entities["location"] = str(args.get("location") or "").strip()
            elif args.get("location") or args.get("destination"):
                entities["location"] = str(args.get("location") or args.get("destination")).strip()

            if args.get("number") or args.get("target"):
                entities["contact"] = str(args.get("number") or args.get("target")).strip()

            if args.get("query") or args.get("expression") or args.get("key"):
                entities["query"] = str(
                    args.get("query") or args.get("expression") or args.get("key")
                ).strip()


def infer_note_key(last_tool: str, last_entities: Optional[Dict[str, Any]] = None) -> str:
    """Infere um título curto para remember_note a partir da última ferramenta/entidade."""
    entities = last_entities or {}
    if last_tool == "search_google" and entities.get("query"):
        return str(entities["query"]).strip()[:60]
    if last_tool == "get_weather" and entities.get("location"):
        return f"clima {entities['location']}".strip()[:60]
    return _DEFAULT_KEYS_BY_TOOL.get(last_tool, "anotação")


def resolve_anaphora(user_text: str, session_id: str = "default") -> str:
    """
    Reescreve referências curtas de continuação (ex: 'e amanhã?', 'salva isso',
    'manda isso pro João') usando o contexto imediato da sessão.
    """
    raw = (user_text or "").strip()
    if not raw or (raw.startswith("<call>") and raw.endswith("</call>")):
        return raw

    state = get_session_state(session_id)
    last_tool = state.get("last_tool", "")
    last_args = state.get("last_args") or {}
    last_entities = state.get("last_entities") or {}
    last_result_text = state.get("last_result_text", "")

    cleaned = re.sub(r"^(?:silva,?\s*)", "", raw, flags=re.IGNORECASE).strip()
    cleaned_no_punct = cleaned.rstrip("?!.,;: ").strip()

    # 1. Continuação de clima (ex: "e amanhã?", "e à noite?", "e em Olinda?")
    if last_tool == "get_weather":
        m_day = _DAY_FOLLOWUP_PATTERN.match(cleaned_no_punct)
        if m_day:
            term = m_day.group(1).strip()
            loc = str(last_entities.get("location") or "").strip()
            if loc:
                return f"previsão do tempo {term} em {loc}"
            return f"previsão do tempo {term}"

        m_city = _CITY_FOLLOWUP_PATTERN.match(cleaned_no_punct)
        if m_city:
            city = m_city.group(1).strip()
            # Evita conflito com comandos explícitos de busca/chamada
            norm_city = normalize_text(city)
            if norm_city and not any(w in norm_city for w in ("sms", "google", "memoria")):
                day = str(last_args.get("day") or "hoje").strip()
                time_val = str(last_args.get("time") or "").strip()
                time_part = f" {time_val}" if time_val else ""
                return f"previsão do tempo {day}{time_part} em {city}"

    # 2. Continuação de salvamento na memória ("anota isso", "salva isso como X")
    if last_result_text:
        m_save = _SAVE_ANAPHORA_PATTERN.match(cleaned_no_punct)
        if m_save:
            custom_key = (m_save.group(1) or "").strip()
            key = custom_key if custom_key else infer_note_key(last_tool, last_entities)
            return _format_call_literal("remember_note", key=key, value="$prev_result")

        # 3. Continuação de envio por WhatsApp ou SMS
        m_wpp = _WPP_ANAPHORA_PATTERN.match(cleaned_no_punct)
        if m_wpp:
            target = m_wpp.group(1).strip()
            if target:
                return _format_call_literal("send_whatsapp", contact_name=target, message="$prev_result")

        m_sms = _SMS_ANAPHORA_PATTERN.match(cleaned_no_punct)
        if m_sms:
            target = m_sms.group(1).strip()
            if target:
                return _format_call_literal("send_sms", number=target, message="$prev_result")

    return raw


def format_recent_context(session_id: str = "default", max_turns: int = 2) -> str:
    """Formata os últimos turnos de forma compacta para caber na janela do llama-server."""
    state = get_session_state(session_id)
    turns: List[Dict[str, Any]] = state.get("recent_turns") or []
    if not turns:
        return ""

    # Cada interação tem user + assistant (até max_turns * 2 mensagens)
    slice_turns = turns[-(max_turns * 2):]
    lines = []
    for t in slice_turns:
        role = "U" if t.get("role") == "user" else "A"
        content = t.get("text") if role == "U" else (t.get("result_summary") or t.get("text", ""))
        content = _clean_result_summary(content, max_len=120)
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)
