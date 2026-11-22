"""
Módulo Memória, Agendamento e Cálculo do Silva: SQLite FTS5, Alarmes, Eventos, Timer e Calculadora Científica AST.
"""

import ast
import json
import math
import os
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from .core import (
    DATA_DIR,
    EVENTS_FILE,
    SIMULATE_HARDWARE,
    _FILE_LOCK,
    _atomic_write_json,
    _load_events,
    _save_events,
    _run_termux_cmd,
    _exec_android_intent,
)

def parse_ptbr_date(date_str: str) -> date:
    """
    Converte expressões de data em Português do Brasil para um objeto datetime.date real.
    Suporta: 'hoje', 'amanhã', 'depois de amanhã', dias da semana ('segunda', 'sexta-feira', etc.),
    datas por extenso ('29 de novembro', 'dia 29 de novembro deste ano', '15 de janeiro de 2027')
    e formatos 'DD/MM', 'DD/MM/AAAA' e 'AAAA-MM-DD'.
    """
    raw = (date_str or "").strip().lower()
    today = date.today()

    if not raw or raw in ("hoje", "today"):
        return today
    if raw in ("amanhã", "amanha", "tomorrow"):
        return today + timedelta(days=1)
    if raw in ("depois de amanhã", "depois de amanha"):
        return today + timedelta(days=2)

    # Dias da semana
    weekdays = {
        "segunda": 0, "segunda-feira": 0,
        "terça": 1, "terca": 1, "terça-feira": 1, "terca-feira": 1,
        "quarta": 2, "quarta-feira": 2,
        "quinta": 3, "quinta-feira": 3,
        "sexta": 4, "sexta-feira": 4,
        "sábado": 5, "sabado": 5,
        "domingo": 6,
    }
    for w_name, w_idx in weekdays.items():
        if raw == w_name or raw.startswith(f"próxima {w_name}") or raw.startswith(f"proxima {w_name}"):
            days_ahead = (w_idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return today + timedelta(days=days_ahead)

    # Data por extenso em português: "29 de novembro", "dia 29 de novembro deste ano", "15 de janeiro de 2027"
    m_ext = re.search(r"(?:dia\s+)?(\d{1,2})\s+de\s+([a-zç]+)(?:\s+de\s+(\d{2,4})|\s+deste\s+ano)?", raw)
    if m_ext:
        day = int(m_ext.group(1))
        month_name = m_ext.group(2)
        month = MONTHS_PTBR.get(month_name)
        if month:
            year_str = m_ext.group(3)
            year = int(year_str) if year_str else today.year
            if year < 100:
                year += 2000
            try:
                target_date = date(year, month, day)
                # Se o ano não foi informado e nem veio "deste ano", caso a data já tenha passado usa o próximo ano
                if not year_str and "deste ano" not in raw and target_date < today:
                    target_date = date(year + 1, month, day)
                return target_date
            except ValueError:
                return today

    # Padrão DD/MM ou DD/MM/AAAA
    match_br = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", raw)
    if match_br:
        day = int(match_br.group(1))
        month = int(match_br.group(2))
        year_str = match_br.group(3)
        year = int(year_str) if year_str else today.year
        if year < 100:
            year += 2000
        try:
            target_date = date(year, month, day)
            if not year_str and target_date < today:
                target_date = date(year + 1, month, day)
            return target_date
        except ValueError:
            return today

    # Padrão ISO YYYY-MM-DD
    match_iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", raw)
    if match_iso:
        try:
            return date(int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3)))
        except ValueError:
            return today

    return today


def parse_time_str(time_str: str) -> tuple[int, int]:
    """Extrai (hora, minuto) de strings como '07:30', '7:30', '7h', '7h30' ou '14:00'."""
    raw = (time_str or "").strip().lower()
    if not raw:
        return (9, 0)

    # Formato HH:MM
    match_colon = re.search(r"(\d{1,2}):(\d{2})", raw)
    if match_colon:
        h, m = int(match_colon.group(1)), int(match_colon.group(2))
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    # Formato 7h, 7h30, 14h00
    match_h = re.search(r"(\d{1,2})h(?:(\d{2}))?", raw)
    if match_h:
        h = int(match_h.group(1))
        m = int(match_h.group(2)) if match_h.group(2) else 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)

    # Apenas dígitos de hora (ex: '7')
    match_num = re.search(r"^\d{1,2}$", raw)
    if match_num:
        h = int(raw)
        if 0 <= h <= 23:
            return (h, 0)

    return (9, 0)


def set_alarm(time: str, label: str = "", days: str = "") -> Dict[str, Any]:
    """Define um alarme no relógio nativo do Android via Intent."""
    hour, minute = parse_time_str(time)
    formatted_time = f"{hour:02d}:{minute:02d}"
    label_clean = str(label).strip()
    days_clean = str(days).strip()

    if SIMULATE_HARDWARE:
        lbl_msg = f" com o rótulo '{label_clean}'" if label_clean else ""
        return {
            "status": "ok",
            "message": f"Silva: Alarme definido para {formatted_time}{lbl_msg}. [Simulado]",
            "data": {"hour": hour, "minute": minute, "time": formatted_time, "label": label_clean, "days": days_clean}
        }

    cmd = [
        "am", "start",
        "-a", "android.intent.action.SET_ALARM",
        "--ei", "android.intent.extra.alarm.HOUR", str(hour),
        "--ei", "android.intent.extra.alarm.MINUTES", str(minute),
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    if label_clean:
        cmd.extend(["--es", "android.intent.extra.alarm.MESSAGE", label_clean])

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao definir alarme: {res.stderr.strip()}"}
        lbl_msg = f" com o rótulo '{label_clean}'" if label_clean else ""
        return {
            "status": "ok",
            "message": f"Silva: Alarme definido para {formatted_time}{lbl_msg}.",
            "data": {"hour": hour, "minute": minute, "time": formatted_time, "label": label_clean, "days": days_clean}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao definir alarme: {str(e)}"}


def cancel_alarm(time: str = "", day: str = "", label: str = "") -> Dict[str, Any]:
    """Cancela ou descarta um alarme no Android via Intent."""
    time_clean = str(time).strip()
    label_clean = str(label).strip()
    day_clean = str(day).strip()

    target_desc = []
    if time_clean:
        target_desc.append(f"das {time_clean}")
    if day_clean:
        target_desc.append(f"de {day_clean}")
    if label_clean:
        target_desc.append(f"'{label_clean}'")
    desc_str = " ".join(target_desc) if target_desc else "ativo"

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Alarme {desc_str} cancelado com sucesso. [Simulado]",
            "data": {"time": time_clean, "day": day_clean, "label": label_clean}
        }

    cmd = [
        "am", "start",
        "-a", "android.intent.action.DISMISS_ALARM",
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    if time_clean:
        h, m = parse_time_str(time_clean)
        cmd.extend([
            "--ei", "android.intent.extra.alarm.HOUR", str(h),
            "--ei", "android.intent.extra.alarm.MINUTES", str(m)
        ])
    if label_clean:
        cmd.extend(["--es", "android.intent.extra.alarm.MESSAGE", label_clean])

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao cancelar alarme: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: Alarme {desc_str} cancelado com sucesso.",
            "data": {"time": time_clean, "day": day_clean, "label": label_clean}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao cancelar alarme: {str(e)}"}


def schedule_event(title: str, date: str = "", time: str = "") -> Dict[str, Any]:
    """Cria um compromisso na agenda local do Silva e abre diretamente no Calendário Samsung sem diálogo de escolha."""
    title_clean = str(title).strip()
    if not title_clean:
        return {"status": "error", "message": "Título do compromisso não informado."}

    target_date = parse_ptbr_date(date)
    hour, minute = parse_time_str(time)
    dt_event = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
    begin_ms = int(dt_event.timestamp() * 1000)
    end_ms = begin_ms + (3600 * 1000)  # +1 hora
    event_ts = int(dt_event.timestamp())

    formatted_date = target_date.strftime("%d/%m/%Y")
    formatted_time = f"{hour:02d}:{minute:02d}"
    event_id = str(uuid.uuid4())[:8]

    # 1. Persistência real na Agenda Local (android_agent/data/events.json)
    event_record = {
        "id": event_id,
        "title": title_clean,
        "date": target_date.strftime("%Y-%m-%d"),
        "time": formatted_time,
        "timestamp": event_ts,
        "notified": False
    }
    with _FILE_LOCK:
        events = _load_events()
        events.append(event_record)
        _save_events(events)

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Compromisso '{title_clean}' salvo na agenda do Silva para {formatted_date} às {formatted_time} (e aberto no Calendário Samsung para confirmar, se desejar). [Simulado]",
            "data": {
                "id": event_id,
                "title": title_clean,
                "date": target_date.strftime("%Y-%m-%d"),
                "time": formatted_time,
                "begin_ms": begin_ms,
                "end_ms": end_ms
            }
        }

    # 2. Intent direta para o Calendário Samsung (evitando pop-up do Outlook)
    cmd = [
        "am", "start",
        "-a", "android.intent.action.INSERT",
        "-t", "vnd.android.cursor.item/event",
        "-d", "content://com.android.calendar/events",
        "-p", "com.samsung.android.calendar",
        "--es", "title", title_clean,
        "--el", "beginTime", str(begin_ms),
        "--el", "endTime", str(end_ms)
    ]

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            # Fallback sem a flag -p caso o Calendário Samsung não esteja presente
            fallback_cmd = [
                "am", "start",
                "-a", "android.intent.action.INSERT",
                "-t", "vnd.android.cursor.item/event",
                "-d", "content://com.android.calendar/events",
                "--es", "title", title_clean,
                "--el", "beginTime", str(begin_ms),
                "--el", "endTime", str(end_ms)
            ]
            _run_termux_cmd(fallback_cmd, timeout=6)
    except Exception:
        pass

    return {
        "status": "ok",
        "message": f"Silva: Compromisso '{title_clean}' salvo na agenda do Silva para {formatted_date} às {formatted_time} (e aberto no Calendário Samsung para confirmar, se desejar).",
        "data": {
            "id": event_id,
            "title": title_clean,
            "date": target_date.strftime("%Y-%m-%d"),
            "time": formatted_time,
            "begin_ms": begin_ms,
            "end_ms": end_ms
        }
    }


def _classify_memory_category(key: str) -> str:
    """Classifica automaticamente a anotação para fins de organização."""
    k_norm = _normalize_text(key)
    if any(w in k_norm for w in ["wifi", "wi-fi", "roteador", "rede", "ip"]):
        return "wifi"
    if any(w in k_norm for w in ["senha", "password", "pin", "chave", "login", "acesso"]):
        return "senha"
    if any(w in k_norm for w in ["estudo", "faculdade", "curso", "aula", "escola", "livro", "prova"]):
        return "estudo"
    if any(w in k_norm for w in ["nome", "aniversario", "cpf", "rg", "nascimento", "casa", "pessoal", "parente"]):
        return "pessoal"
    return "geral"


def _get_memory_db() -> sqlite3.Connection:
    """
    Retorna conexão segura e transacional com o banco SQLite da memória (WAL mode).
    Cria tabelas e triggers FTS5 automaticamente e executa migração de memory.json se necessário.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = DATA_DIR / "memory.db"
    legacy_file = DATA_DIR / "memory.json"
    migrated_file = DATA_DIR / "memory.json.migrated"

    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'geral',
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                key,
                value,
                content='memories',
                content_rowid='id'
            );
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, value) VALUES('delete', old.id, old.key, old.value);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, key, value) VALUES('delete', old.id, old.key, old.value);
                INSERT INTO memories_fts(rowid, key, value) VALUES (new.id, new.key, new.value);
            END;
        """)

        # Migração automática zero-loss de memory.json para SQLite
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM memories")
        count = cur.fetchone()[0]
        if count == 0 and legacy_file.is_file():
            try:
                with open(legacy_file, "r", encoding="utf-8") as f:
                    old_mem = json.load(f)
                if isinstance(old_mem, dict):
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    for k, v_data in old_mem.items():
                        clean_k = str(k).strip()
                        if not clean_k:
                            continue
                        if isinstance(v_data, dict):
                            val = str(v_data.get("value", "")).strip()
                            up_at = v_data.get("timestamp", now_str)
                        else:
                            val = str(v_data).strip()
                            up_at = now_str
                        cat = _classify_memory_category(clean_k)
                        cur.execute(
                            "INSERT OR REPLACE INTO memories (key, value, category, updated_at) VALUES (?, ?, ?, ?)",
                            (clean_k, val, cat, up_at)
                        )
                try:
                    legacy_file.rename(migrated_file)
                except Exception:
                    pass
            except Exception:
                pass
    return conn


def _migrate_json_to_sqlite() -> None:
    """Função explícita de migração para testes e manutenção."""
    conn = _get_memory_db()
    conn.close()


def _load_memory() -> dict:
    """Carrega todas as memórias do banco SQLite em um dicionário para compatibilidade com código legado."""
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            cur = conn.cursor()
            cur.execute("SELECT key, value, category, updated_at FROM memories ORDER BY id ASC")
            res = {}
            for row in cur.fetchall():
                res[row["key"]] = {
                    "value": row["value"],
                    "category": row["category"],
                    "timestamp": row["updated_at"]
                }
            conn.close()
            return res
        except Exception:
            return {}


def _save_memory(data: dict):
    """Atualiza memórias no SQLite a partir de um dicionário completo (compatibilidade retroativa)."""
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with conn:
                for k, v_data in data.items():
                    clean_k = str(k).strip()
                    if not clean_k:
                        continue
                    if isinstance(v_data, dict):
                        val = str(v_data.get("value", "")).strip()
                        up_at = v_data.get("timestamp", now_str)
                    else:
                        val = str(v_data).strip()
                        up_at = now_str
                    cat = _classify_memory_category(clean_k)
                    conn.execute(
                        "INSERT INTO memories (key, value, category, updated_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category, updated_at=excluded.updated_at",
                        (clean_k, val, cat, up_at)
                    )
            conn.close()
        except Exception:
            pass


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def remember_note(key: str, value: str) -> Dict[str, Any]:
    """
    Salva, atualiza ou remove uma anotação persistente na memória local do Silva (SQLite FTS5).
    Se value for vazio ou comando de exclusão ('apagar', 'remover', 'deletar'), a nota é removida.
    """
    clean_key = str(key).strip()
    clean_val = str(value).strip()
    if not clean_key:
        return {"status": "error", "message": "Chave da anotação não informada."}

    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            # Caso de exclusão de anotação
            if clean_val.lower() in ("", "apagar", "remover", "deletar", "excluir"):
                with conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM memories WHERE lower(key) = lower(?)", (clean_key,))
                    deleted = cur.rowcount > 0
                conn.close()
                if deleted:
                    return {
                        "status": "ok",
                        "message": f"Silva: Anotação '{clean_key}' removida da memória.",
                        "data": {"key": clean_key, "action": "deleted"}
                    }
                else:
                    return {
                        "status": "ok",
                        "message": f"Silva: Nenhuma anotação encontrada com a chave '{clean_key}' para remover.",
                        "data": {"key": clean_key, "action": "not_found"}
                    }

            # Inserção ou Atualização (UPSERT)
            category = _classify_memory_category(clean_key)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with conn:
                conn.execute(
                    "INSERT INTO memories (key, value, category, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category, updated_at=excluded.updated_at",
                    (clean_key, clean_val, category, now_str)
                )
            conn.close()

            return {
                "status": "ok",
                "message": f"Silva: Anotado: {clean_key} = {clean_val}.",
                "data": {"key": clean_key, "value": clean_val, "category": category}
            }
        except Exception as e:
            return {"status": "error", "message": f"Erro ao salvar na memória: {str(e)}"}


def recall_note(query: str) -> Dict[str, Any]:
    """
    Busca anotações na memória local via SQLite FTS5 (com fallback LIKE) e na agenda local.
    Retorna os melhores resultados ranqueados.
    """
    clean_query = str(query).strip()
    if not clean_query:
        return {"status": "error", "message": "Termo de busca não informado."}

    norm_query = _normalize_text(clean_query)
    raw_tokens = norm_query.split()
    noise_words = {
        "qual", "onde", "o", "a", "os", "as", "de", "do", "da", "dos", "das",
        "em", "no", "na", "nos", "nas", "para", "pra", "pro", "que", "e",
        "me", "lembra", "lembrar", "guarda", "guardei", "salvei", "anotei",
        "minha", "meu", "minhas", "meus", "voce", "vc", "esta", "estava"
    }
    query_tokens = [t for t in raw_tokens if t not in noise_words and len(t) >= 2]
    if not query_tokens:
        query_tokens = [t for t in raw_tokens if len(t) >= 2] or raw_tokens

    matches = []
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            cur = conn.cursor()

            # 1. Busca FTS5 com prefixos '*'
            fts_query_parts = [f'"{re.sub(r"[^\w]", "", t)}"*' for t in query_tokens if re.sub(r"[^\w]", "", t)]
            if fts_query_parts:
                fts_query_str = " OR ".join(fts_query_parts)
                try:
                    cur.execute(
                        "SELECT m.key, m.value, m.category, m.updated_at, bm25(memories_fts) as rank "
                        "FROM memories_fts f "
                        "JOIN memories m ON f.rowid = m.id "
                        "WHERE memories_fts MATCH ? "
                        "ORDER BY rank ASC "
                        "LIMIT 5",
                        (fts_query_str,)
                    )
                    for row in cur.fetchall():
                        matches.append({
                            "key": row["key"],
                            "value": row["value"],
                            "category": row["category"],
                            "updated_at": row["updated_at"],
                            "score": -float(row["rank"])
                        })
                except Exception:
                    pass

            # 2. Fallback LIKE se FTS5 não trouxe nada
            if not matches:
                for token in query_tokens:
                    like_pattern = f"%{token}%"
                    cur.execute(
                        "SELECT key, value, category, updated_at FROM memories "
                        "WHERE key LIKE ? OR value LIKE ? "
                        "LIMIT 5",
                        (like_pattern, like_pattern)
                    )
                    for row in cur.fetchall():
                        if not any(m["key"] == row["key"] for m in matches):
                            matches.append({
                                "key": row["key"],
                                "value": row["value"],
                                "category": row["category"],
                                "updated_at": row["updated_at"],
                                "score": 1.0
                            })
            conn.close()
        except Exception:
            pass

    # 3. Busca em compromissos da agenda (events.json)
    events = _load_events()
    event_matches = []
    if events:
        is_agenda_query = any(w in norm_query for w in ["agenda", "compromisso", "compromissos", "evento", "eventos", "reuniao", "lembrete", "lembretes"])
        for ev in events:
            ev_title = ev.get("title", "")
            ev_date = ev.get("date", "")
            ev_time = ev.get("time", "")
            norm_title = _normalize_text(ev_title)
            if is_agenda_query or norm_query in norm_title or norm_title in norm_query or set(query_tokens).intersection(set(norm_title.split())):
                event_matches.append(f"'{ev_title}' em {ev_date} às {ev_time}")

    if not matches and not event_matches:
        return {
            "status": "ok",
            "message": f"Silva: Nenhuma anotação ou compromisso encontrado sobre '{clean_query}'.",
            "data": {"found": False, "query": clean_query}
        }

    parts = []
    if matches:
        notes_str = "; ".join(f"{m['key']}: {m['value']}" for m in matches[:3])
        parts.append(f"Memória: {notes_str}")
    if event_matches:
        ev_str = "; ".join(event_matches[:4])
        parts.append(f"Agenda: {ev_str}")

    msg = "Silva: " + " | ".join(parts) + "."

    return {
        "status": "ok",
        "message": msg,
        "data": {
            "found": True,
            "notes": [{"key": m["key"], "value": m["value"], "category": m.get("category", "geral")} for m in matches[:5]],
            "events": event_matches
        }
    }



def set_timer(minutes: int, label: str = "") -> Dict[str, Any]:
    """Inicia um cronômetro/timer no relógio nativo do Android."""
    mins = max(1, int(minutes))
    seconds = mins * 60
    clean_label = str(label).strip()

    if SIMULATE_HARDWARE:
        lbl_msg = f" ({clean_label})" if clean_label else ""
        return {
            "status": "ok",
            "message": f"Silva: Timer de {mins} minuto(s){lbl_msg} iniciado. [Simulado]",
            "data": {"minutes": mins, "seconds": seconds, "label": clean_label}
        }

    cmd = [
        "am", "start",
        "-a", "android.intent.action.SET_TIMER",
        "--ei", "android.intent.extra.alarm.LENGTH", str(seconds),
        "--ez", "android.intent.extra.alarm.SKIP_UI", "true"
    ]
    if clean_label:
        cmd.extend(["--es", "android.intent.extra.alarm.MESSAGE", clean_label])

    try:
        res = _run_termux_cmd(cmd, timeout=6)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao iniciar timer: {res.stderr.strip()}"}
        lbl_msg = f" para '{clean_label}'" if clean_label else ""
        return {
            "status": "ok",
            "message": f"Silva: Timer de {mins} minuto(s){lbl_msg} iniciado.",
            "data": {"minutes": mins, "seconds": seconds, "label": clean_label}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao iniciar timer: {str(e)}"}


class SafeMathEvaluator(ast.NodeVisitor):
    ALLOWED_OPERATORS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b,
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }

    ALLOWED_FUNCTIONS = {
        "sqrt": math.sqrt,
        "cbrt": lambda x: math.pow(x, 1/3) if x >= 0 else -math.pow(-x, 1/3),
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "exp": math.exp,
        "factorial": lambda n: math.factorial(int(n)),
        "abs": abs,
        "round": round,
        "floor": math.floor,
        "ceil": math.ceil,
    }

    ALLOWED_CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
    }

    def visit(self, node):
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        raise ValueError(f"Operação não permitida na calculadora: {node.__class__.__name__}")

    def visit_Expression(self, node):
        return self.visit(node.body)

    def visit_Constant(self, node):
        if isinstance(node.value, bool):
            raise ValueError("Valores booleanos não são permitidos.")
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Apenas valores numéricos são permitidos.")

    def visit_Name(self, node):
        if node.id in self.ALLOWED_CONSTANTS:
            return self.ALLOWED_CONSTANTS[node.id]
        raise ValueError(f"Identificador não permitido na calculadora: {node.id}")

    def visit_UnaryOp(self, node):
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Operador unário não suportado: {op_type.__name__}")
        operand = self.visit(node.operand)
        return self.ALLOWED_OPERATORS[op_type](operand)

    def visit_BinOp(self, node):
        op_type = type(node.op)
        if op_type not in self.ALLOWED_OPERATORS:
            raise ValueError(f"Operador binário não suportado: {op_type.__name__}")
        left = self.visit(node.left)
        right = self.visit(node.right)

        if op_type is ast.Pow:
            if abs(right) > 1000:
                raise ValueError("Expoente muito grande (limite: 1000).")

        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Divisão por zero não é permitida.")

        return self.ALLOWED_OPERATORS[op_type](left, right)

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Chamada de função dinâmica não permitida.")
        fn_name = node.func.id
        if fn_name not in self.ALLOWED_FUNCTIONS:
            raise ValueError(f"Função matemática não permitida: {fn_name}")
        if node.keywords:
            raise ValueError("Argumentos nomeados não são permitidos em funções matemáticas.")

        args = [self.visit(arg) for arg in node.args]
        if fn_name == "factorial":
            if len(args) != 1 or args[0] < 0 or args[0] > 170:
                raise ValueError("Fatorial aceita apenas valores inteiros entre 0 e 170.")
        elif fn_name == "sqrt":
            if len(args) != 1 or args[0] < 0:
                raise ValueError("Raiz quadrada não definida para números negativos nos reais.")
        elif fn_name in ("log", "log10", "log2"):
            if len(args) < 1 or args[0] <= 0:
                raise ValueError("Logaritmo não definido para valores menores ou iguais a zero.")

        return self.ALLOWED_FUNCTIONS[fn_name](*args)


def calculate(expression: str) -> Dict[str, Any]:
    """Calculadora científica e financeira offline segura baseada em AST (sem eval)."""
    expr_clean = str(expression).strip()
    if not expr_clean:
        return {"status": "error", "message": "Expressão matemática vazia."}

    # Normaliza x, ×, ÷ e vírgula decimal entre números
    normalized = expr_clean.replace("×", "*").replace("÷", "/")
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", normalized)
    normalized = re.sub(r"(?<=\d|\))\s*[xX]\s*(?=\d|\()", " * ", normalized)
    normalized = re.sub(r"\b[xX]\b", "*", normalized)

    try:
        tree = ast.parse(normalized, mode="eval")
        evaluator = SafeMathEvaluator()
        result = evaluator.visit(tree)

        if isinstance(result, float) and result.is_integer():
            result_fmt = str(int(result))
        elif isinstance(result, float):
            result_fmt = f"{result:.4f}".rstrip("0").rstrip(".")
        else:
            result_fmt = str(result)

        return {
            "status": "ok",
            "message": f"Silva: O resultado de {expr_clean} é {result_fmt}.",
            "data": {"expression": expr_clean, "result": result, "result_formatted": result_fmt}
        }
    except ZeroDivisionError:
        return {"status": "error", "message": "Erro de cálculo: Divisão por zero."}
    except Exception as e:
        return {"status": "error", "message": f"Não foi possível calcular '{expr_clean}': {str(e)}"}




# Alias de compatibilidade
_init_memory_db = _get_memory_db
