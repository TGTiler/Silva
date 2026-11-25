"""
Resolvedor Unificado de Contatos do Silva (Número Direto -> memory.db -> Agenda Android).
100% stdlib Python com cache TTL de 5 minutos para termux-contact-list e desambiguação.
"""

import difflib
import json
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from .core import _FILE_LOCK, _run_termux_cmd, sanitize_phone_number

CONTACTS_CACHE_TTL = 300.0  # 5 minutos
_CONTACTS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "contacts": []}

_ALIAS_NOISE_RE = re.compile(r"^(?:o|a|os|as|meu|minha|meus|minhas|do|da|pro|pra)\s+", re.IGNORECASE)


def _norm_text(text: str) -> str:
    deaccent = unicodedata.normalize("NFKD", str(text or "")).encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"[^\w\s]", " ", deaccent).strip().lower()


def _normalize_clean_phone(raw: str) -> Optional[str]:
    text = str(raw or "").strip()
    if not text:
        return None
    has_plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if len(digits) < 3:
        return None
    return f"+{digits}" if has_plus else digits


def _extract_phone_from_text(text: str) -> Optional[str]:
    m = re.search(r"(\+?\d[\d\s\-()]{6,18}\d)", str(text or ""))
    if not m:
        return None
    return _normalize_clean_phone(m.group(1))


def _load_android_contacts() -> List[Dict[str, Any]]:
    now = time.time()
    if (now - _CONTACTS_CACHE.get("timestamp", 0.0)) < CONTACTS_CACHE_TTL and _CONTACTS_CACHE.get("contacts"):
        return _CONTACTS_CACHE["contacts"]

    try:
        res = _run_termux_cmd(["termux-contact-list"], timeout=5)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if isinstance(data, list):
                _CONTACTS_CACHE["timestamp"] = now
                _CONTACTS_CACHE["contacts"] = data
                return data
    except Exception:
        pass
    return _CONTACTS_CACHE.get("contacts") or []


def _resolve_from_memory(query: str) -> Tuple[Optional[str], Optional[str]]:
    """Busca apelidos e contatos salvos na tabela memories do memory.db."""
    norm_q = _norm_text(query)
    stripped_q = _ALIAS_NOISE_RE.sub("", norm_q).strip()
    search_terms = [t for t in dict.fromkeys([norm_q, stripped_q]) if t]
    if not search_terms:
        return None, None

    try:
        from .memory_schedule import _get_memory_db
        conn = _get_memory_db()
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM memories ORDER BY id DESC")
        rows = cur.fetchall()
        conn.close()
    except Exception:
        return None, None

    contact_hints = ("contato", "numero", "telefone", "celular", "zap", "whatsapp", "mae", "pai", "vo", "amor", "casa")
    best_match: Optional[Tuple[int, str, str]] = None

    for row in rows:
        k_raw = str(row["key"] or "").strip()
        v_raw = str(row["value"] or "").strip()
        k_norm = _norm_text(k_raw)
        k_stripped = re.sub(r"^contato[\s_]+", "", k_norm).strip()
        v_norm = _norm_text(v_raw)

        phone = _extract_phone_from_text(v_raw) or _extract_phone_from_text(k_raw)
        if not phone:
            continue

        score = 0
        for term in search_terms:
            if term == k_norm or term == k_stripped:
                score = max(score, 100)
            elif re.search(rf"\b{re.escape(term)}\b", k_stripped or k_norm):
                score = max(score, 90)
            elif term in k_norm or term in k_stripped:
                score = max(score, 75)
            elif any(h in k_norm or h in v_norm for h in contact_hints) and term in v_norm:
                score = max(score, 70)

        if score > 0 and (best_match is None or score > best_match[0]):
            if ":" in v_raw and k_raw.lower().startswith("contato_"):
                display = v_raw.split(":", 1)[0].strip()
            else:
                display = stripped_q.title() if stripped_q else k_raw
            best_match = (score, phone, display)

    if best_match:
        return best_match[1], best_match[2]
    return None, None


def resolve_contact_detailed(query: str) -> Dict[str, Any]:
    """
    Resolve contato em 3 camadas:
    1. Número direto (>= 8 dígitos)
    2. Apelidos/contatos no memory.db
    3. Agenda nativa Android (termux-contact-list com cache TTL 5 min) e desambiguação.
    """
    raw = str(query or "").strip()
    if not raw:
        return {"number": None, "name": None, "source": "none", "ambiguous": False, "candidates": []}

    # Camada 1: Número direto
    has_letters = bool(re.search(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", raw))
    digits_only = re.sub(r"\D", "", raw)
    if (not has_letters and len(digits_only) >= 3) or len(digits_only) >= 8:
        clean = _normalize_clean_phone(raw)
        if clean:
            return {"number": clean, "name": clean, "source": "direct", "ambiguous": False, "candidates": []}

    # Camada 2: Memória persistente (memory.db)
    mem_num, mem_name = _resolve_from_memory(raw)
    if mem_num:
        return {"number": mem_num, "name": mem_name, "source": "memory", "ambiguous": False, "candidates": []}

    # Camada 3: Agenda nativa Android
    contacts = _load_android_contacts()
    if not contacts:
        return {"number": None, "name": None, "source": "not_found", "ambiguous": False, "candidates": []}

    norm_q = _ALIAS_NOISE_RE.sub("", _norm_text(raw)).strip() or _norm_text(raw)
    scored: List[Tuple[int, str, str]] = []

    for c in contacts:
        c_name = str(c.get("name") or "").strip()
        c_num_raw = c.get("number") or c.get("phone") or ""
        if isinstance(c_num_raw, list) and c_num_raw:
            c_num_raw = c_num_raw[0]
        c_num = _normalize_clean_phone(sanitize_phone_number(str(c_num_raw)))
        if not c_name or not c_num:
            continue

        c_norm = _norm_text(c_name)
        c_parts = c_norm.split()
        first_name = c_parts[0] if c_parts else ""

        score = 0
        if norm_q == c_norm:
            score = 100
        elif norm_q == first_name or c_norm.startswith(norm_q + " "):
            score = 85
        elif norm_q in c_norm:
            score = 70
        else:
            ratio = difflib.SequenceMatcher(None, norm_q, c_norm).ratio()
            if ratio >= 0.78:
                score = 60

        if score > 0:
            scored.append((score, c_name, c_num))

    if not scored:
        return {"number": None, "name": None, "source": "not_found", "ambiguous": False, "candidates": []}

    scored.sort(key=lambda item: item[0], reverse=True)
    top_score = scored[0][0]

    # Verifica múltiplos contatos distintos com o mesmo primeiro nome/score alto (sem match exato)
    if top_score < 100:
        top_matches = [item for item in scored if item[0] == top_score]
        unique_by_num = {}
        for _, name, num in top_matches:
            if num not in unique_by_num:
                unique_by_num[num] = name
        if len(unique_by_num) > 1:
            candidates = [{"name": name, "number": num} for num, name in unique_by_num.items()]
            return {
                "number": None,
                "name": None,
                "source": "ambiguous",
                "ambiguous": True,
                "candidates": candidates,
            }

    _, best_name, best_num = scored[0]
    return {
        "number": best_num,
        "name": best_name,
        "source": "android_contacts",
        "ambiguous": False,
        "candidates": [],
    }


def resolve_contact(query: str) -> Tuple[Optional[str], Optional[str], str]:
    """Retorna (numero_normalizado, nome_exibicao, fonte)."""
    info = resolve_contact_detailed(query)
    return info["number"], info["name"], info["source"]


def save_contact_to_memory(name: str, phone: str) -> Dict[str, Any]:
    """Grava contato estruturado no memory.db (categoria 'contato', chave contato_<nome_normalizado>)."""
    clean_name = str(name or "").strip()
    clean_phone = _normalize_clean_phone(sanitize_phone_number(str(phone or "").strip()))
    if not clean_name:
        return {"status": "error", "message": "Nome do contato não informado."}
    if not clean_phone or len(re.sub(r"\D", "", clean_phone)) < 3:
        return {"status": "error", "message": f"Número de telefone inválido para '{clean_name}'."}

    norm_key = re.sub(r"\s+", "_", _norm_text(clean_name))
    db_key = f"contato_{norm_key}"
    db_val = f"{clean_name}: {clean_phone}"

    try:
        from datetime import datetime
        from .memory_schedule import _get_memory_db
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _FILE_LOCK:
            conn = _get_memory_db()
            with conn:
                conn.execute(
                    "INSERT INTO memories (key, value, category, updated_at) VALUES (?, ?, 'contato', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, category='contato', updated_at=excluded.updated_at",
                    (db_key, db_val, now_str),
                )
            conn.close()
        return {
            "status": "ok",
            "message": f"Silva: Contato '{clean_name}' ({clean_phone}) salvo na memória com sucesso.",
            "data": {"key": db_key, "name": clean_name, "phone": clean_phone, "category": "contato"},
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao salvar contato: {str(e)}"}


def format_disambiguation_message(query: str, candidates: List[Dict[str, str]]) -> str:
    """Formata pedido amigável de desambiguação quando há múltiplos contatos."""
    opts = ", ".join(f"{c['name']} ({c['number']})" for c in candidates[:5])
    return f"Encontrei mais de um contato para '{query}': {opts}. Qual deles você quer?"
