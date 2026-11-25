"""
Módulo Memória, Agendamento e Cálculo do Silva: SQLite FTS5, Alarmes, Eventos, Timer e Calculadora Científica AST.
"""

import ast
import json
import math
import re
import sqlite3
import unicodedata
import urllib.request
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from .core import (
    DATA_DIR,
    SIMULATE_HARDWARE,
    _FILE_LOCK,
    _run_termux_cmd,
)

MONTHS_PTBR = {
    "janeiro": 1, "jan": 1,
    "fevereiro": 2, "fev": 2,
    "março": 3, "marco": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "maio": 5, "mai": 5,
    "junho": 6, "jun": 6,
    "julho": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9,
    "outubro": 10, "out": 10,
    "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}


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


def parse_recurrence(text: str) -> str:
    """Reconhece expressões naturais de recorrência em PT-BR."""
    norm = _normalize_text(text)
    if not norm:
        return "none"
    if any(w in norm for w in ("todo dia", "todos os dias", "diariamente", "daily")):
        return "daily"
    if any(w in norm for w in ("segunda a sexta", "dias uteis", "dia util", "weekdays")):
        return "weekdays"
    if any(w in norm for w in ("toda semana", "semanalmente", "weekly")):
        return "weekly"
    return "none"


def compute_next_trigger(trigger_at_str: str, recurrence: str) -> Optional[str]:
    """Calcula o próximo trigger_at ISO-8601 ('YYYY-MM-DD HH:MM:SS') para eventos recorrentes."""
    rec = (recurrence or "none").strip().lower()
    if rec == "none":
        return None
    try:
        dt = datetime.strptime(trigger_at_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

    if rec == "daily":
        return (dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    if rec == "weekly":
        return (dt + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    if rec == "weekdays":
        nxt = dt + timedelta(days=1)
        while nxt.weekday() >= 5:  # 5=sabado, 6=domingo
            nxt += timedelta(days=1)
        return nxt.strftime("%Y-%m-%d %H:%M:%S")
    return None


def set_alarm(time: str, label: str = "", days: str = "") -> Dict[str, Any]:
    """Define um alarme no relógio nativo do Android e registra em scheduled_events (memory.db)."""
    hour, minute = parse_time_str(time)
    formatted_time = f"{hour:02d}:{minute:02d}"
    label_clean = str(label).strip()
    days_clean = str(days).strip()
    recurrence = parse_recurrence(f"{days_clean} {label_clean}")

    now = datetime.now()
    target_dt = datetime(now.year, now.month, now.day, hour, minute)
    if target_dt <= now:
        target_dt += timedelta(days=1)
    if recurrence == "weekdays":
        while target_dt.weekday() >= 5:
            target_dt += timedelta(days=1)
    trigger_at = target_dt.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with _FILE_LOCK:
            conn = _get_memory_db()
            with conn:
                conn.execute(
                    "INSERT INTO scheduled_events (title, event_type, trigger_at, recurrence, status, spoken_alert) "
                    "VALUES (?, 'alarm', ?, ?, 'pending', 1)",
                    (label_clean or f"Alarme das {formatted_time}", trigger_at, recurrence),
                )
            conn.close()
    except Exception:
        pass

    if SIMULATE_HARDWARE:
        lbl_msg = f" com o rótulo '{label_clean}'" if label_clean else ""
        return {
            "status": "ok",
            "message": f"Silva: Alarme definido para {formatted_time}{lbl_msg}. [Simulado]",
            "data": {"hour": hour, "minute": minute, "time": formatted_time, "label": label_clean, "days": days_clean, "recurrence": recurrence}
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


def schedule_event(title: str, date: str = "", time: str = "", recurrence: str = "") -> Dict[str, Any]:
    """Cria um compromisso na agenda unificada (memory.db/scheduled_events) e abre no Calendário."""
    title_clean = str(title).strip()
    if not title_clean:
        return {"status": "error", "message": "Título do compromisso não informado."}

    target_date = parse_ptbr_date(date)
    hour, minute = parse_time_str(time)
    dt_event = datetime(target_date.year, target_date.month, target_date.day, hour, minute)
    begin_ms = int(dt_event.timestamp() * 1000)
    end_ms = begin_ms + (3600 * 1000)  # +1 hora
    trigger_at = dt_event.strftime("%Y-%m-%d %H:%M:%S")
    rec_val = recurrence.strip().lower() if recurrence.strip() else parse_recurrence(f"{date} {title_clean}")

    formatted_date = target_date.strftime("%d/%m/%Y")
    formatted_time = f"{hour:02d}:{minute:02d}"
    event_id = str(uuid.uuid4())[:8]

    # 1. Persistência transacional na Agenda Unificada (memory.db -> scheduled_events)
    with _FILE_LOCK:
        conn = _get_memory_db()
        with conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO scheduled_events (title, event_type, trigger_at, recurrence, status, spoken_alert) "
                "VALUES (?, 'event', ?, ?, 'pending', 1)",
                (title_clean, trigger_at, rec_val),
            )
            event_id = str(cur.lastrowid or event_id)
        conn.close()

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Compromisso '{title_clean}' salvo na agenda do Silva para {formatted_date} às {formatted_time} (e aberto no Calendário Samsung para confirmar, se desejar). [Simulado]",
            "data": {
                "id": event_id,
                "title": title_clean,
                "date": target_date.strftime("%Y-%m-%d"),
                "time": formatted_time,
                "trigger_at": trigger_at,
                "recurrence": rec_val,
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                event_type TEXT DEFAULT 'event',
                trigger_at TEXT NOT NULL,
                recurrence TEXT DEFAULT 'none',
                status TEXT DEFAULT 'pending',
                spoken_alert INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_name TEXT NOT NULL,
                item TEXT NOT NULL COLLATE NOCASE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(list_name, item)
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_type TEXT NOT NULL DEFAULT 'wifi',
                trigger_value TEXT NOT NULL,
                reminder_text TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                triggered_at TIMESTAMP DEFAULT NULL
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS voice_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                note_type TEXT NOT NULL DEFAULT 'audio',
                filename TEXT DEFAULT NULL,
                is_checked INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checked_at TIMESTAMP DEFAULT NULL
            );
        """)

        # Migração transparente de events.json legado para scheduled_events
        events_legacy = DATA_DIR / "events.json"
        events_migrated = DATA_DIR / "events.json.migrated"
        if events_legacy.is_file():
            try:
                with open(events_legacy, "r", encoding="utf-8") as ef:
                    old_events = json.load(ef)
                if isinstance(old_events, list):
                    cur_ev = conn.cursor()
                    for ev in old_events:
                        if not isinstance(ev, dict):
                            continue
                        ev_title = str(ev.get("title") or "Compromisso").strip()
                        if ev.get("notified"):
                            continue
                        ts = ev.get("timestamp")
                        if ts:
                            trig = datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
                        elif ev.get("date") and ev.get("time"):
                            trig = f"{ev['date']} {ev['time']}:00"
                        else:
                            trig = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cur_ev.execute(
                            "INSERT INTO scheduled_events (title, event_type, trigger_at, recurrence, status, spoken_alert) "
                            "VALUES (?, 'event', ?, 'none', 'pending', 1)",
                            (ev_title, trig),
                        )
                try:
                    events_legacy.rename(events_migrated)
                except Exception:
                    pass
            except Exception:
                pass

        # Migração idempotente de colunas TTL e sensibilidade em memories
        cur_cols = conn.cursor()
        cur_cols.execute("PRAGMA table_info(memories)")
        existing_cols = {r["name"] for r in cur_cols.fetchall()}
        if "expires_at" not in existing_cols:
            conn.execute("ALTER TABLE memories ADD COLUMN expires_at TEXT DEFAULT NULL")
        if "is_sensitive" not in existing_cols:
            conn.execute("ALTER TABLE memories ADD COLUMN is_sensitive INTEGER DEFAULT 0")

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


_init_memory_db = _get_memory_db


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


def _purge_expired_memories(conn: sqlite3.Connection) -> int:
    """Remove memórias temporárias expiradas (mantendo memories_fts sincronizado via trigger)."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now_str,),
        )
        return cur.rowcount


def _format_relative_time(timestamp_str: str) -> str:
    """Formata timestamp em texto relativo amigável em PT-BR."""
    raw = str(timestamp_str or "").strip()
    if not raw:
        return "salvo recentemente"
    dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:19], fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return f"salvo em {raw}"

    now = datetime.now()
    diff_sec = (now - dt).total_seconds()
    if 0 <= diff_sec < 60:
        return "salvo agora"
    if 60 <= diff_sec < 3600:
        mins = int(diff_sec // 60)
        return f"salvo há {mins} min"
    if dt.date() == now.date():
        return f"salvo hoje às {dt.strftime('%H:%M')}"
    if dt.date() == (now.date() - timedelta(days=1)):
        return "salvo ontem"
    return f"salvo em {dt.strftime('%d/%m/%Y')}"


def _is_sensitive_memory(key: str, value: str, category: str) -> int:
    if category in ("senha", "wifi"):
        return 1
    norm = _normalize_text(f"{key} {value}")
    if any(w in norm for w in ("senha", "password", "pin", "codigo", "pix", "cpf", "token", "chave")):
        return 1
    return 0


def _extract_ttl_hours(text: str, explicit_ttl: int = 0) -> int:
    if explicit_ttl and int(explicit_ttl) > 0:
        return int(explicit_ttl)
    norm = _normalize_text(text)
    m_h = re.search(r"\bpor\s+(\d+)\s*horas?\b", norm)
    if m_h:
        return max(1, int(m_h.group(1)))
    if "so por hoje" in norm or "apenas hoje" in norm:
        return 12
    if "ate amanha" in norm:
        return 24
    return 0


def _extract_semantic_key_and_value(raw_text: str) -> tuple[str, str]:
    """Extrai (chave_semantica, valor_completo) para captura livre em uma frase."""
    clean = str(raw_text or "").strip()
    if "=" in clean:
        k, v = clean.split("=", 1)
        return k.strip(), v.strip()
    if ":" in clean:
        k, v = clean.split(":", 1)
        if len(k.strip()) <= 45:
            return k.strip(), v.strip()
    m_eq = re.split(r"\s+[eé]\s+", clean, maxsplit=1, flags=re.IGNORECASE)
    if len(m_eq) == 2 and len(m_eq[0].split()) <= 6:
        k_clean = re.sub(r"^(?:o|a|meu|minha)\s+", "", m_eq[0].strip(), flags=re.IGNORECASE).strip()
        return k_clean or m_eq[0].strip(), m_eq[1].strip()

    norm = _normalize_text(clean)
    if any(w in norm for w in ("estacionei", "parei", "vaga", "carro")):
        return "vaga do carro", clean
    if any(w in norm for w in ("portao", "porta", "interfone")):
        return "código do portão", clean
    if "pix" in norm:
        return "chave pix", clean

    words = [w for w in clean.split() if len(w) > 2]
    short_key = " ".join(words[:4]) if words else clean[:32]
    return short_key.strip(".,;:?! "), clean


def _find_overlapping_key(conn: sqlite3.Connection, target_key: str) -> Optional[str]:
    """Encontra chave existente equivalente ou com alta sobreposição semântica para upsert limpo."""
    cur = conn.cursor()
    cur.execute("SELECT key FROM memories WHERE lower(key) = lower(?)", (target_key,))
    row = cur.fetchone()
    if row:
        return row["key"]

    noise = {"o", "a", "os", "as", "de", "do", "da", "meu", "minha", "onde", "qual"}
    target_tokens = {t for t in _normalize_text(target_key).split() if t not in noise and len(t) >= 3}
    if not target_tokens:
        return None

    cur.execute("SELECT key FROM memories")
    for r in cur.fetchall():
        existing_k = r["key"]
        existing_tokens = {t for t in _normalize_text(existing_k).split() if t not in noise and len(t) >= 3}
        if not existing_tokens:
            continue
        inter = target_tokens.intersection(existing_tokens)
        union = target_tokens.union(existing_tokens)
        if union and (len(inter) / len(union)) >= 0.65:
            return existing_k
    return None


def remember_note(key: str, value: str = "", ttl_hours: int = 0) -> Dict[str, Any]:
    """
    Salva, atualiza ou remove uma anotação persistente na memória local do Silva (SQLite FTS5).
    Suporta captura livre em uma frase (value vazio), upsert sem duplicatas e TTL (ttl_hours).
    """
    raw_key = str(key or "").strip()
    raw_val = str(value or "").strip()
    if not raw_key:
        return {"status": "error", "message": "Chave ou conteúdo da anotação não informado."}

    # Caso explícito de exclusão via remember_note(..., 'apagar')
    if raw_val.lower() in ("apagar", "remover", "deletar", "excluir"):
        with _FILE_LOCK:
            try:
                conn = _get_memory_db()
                _purge_expired_memories(conn)
                with conn:
                    cur = conn.cursor()
                    cur.execute("DELETE FROM memories WHERE lower(key) = lower(?)", (raw_key,))
                    deleted = cur.rowcount > 0
                conn.close()
                if deleted:
                    return {
                        "status": "ok",
                        "message": f"Silva: Anotação '{raw_key}' removida da memória.",
                        "data": {"key": raw_key, "action": "deleted"},
                    }
                return {
                    "status": "ok",
                    "message": f"Silva: Nenhuma anotação encontrada com a chave '{raw_key}' para remover.",
                    "data": {"key": raw_key, "action": "not_found"},
                }
            except Exception as e:
                return {"status": "error", "message": f"Erro ao remover da memória: {str(e)}"}

    if not raw_val:
        clean_key, clean_val = _extract_semantic_key_and_value(raw_key)
    else:
        clean_key, clean_val = raw_key, raw_val

    eff_ttl = _extract_ttl_hours(f"{raw_key} {raw_val}", ttl_hours)
    expires_at = (
        (datetime.now() + timedelta(hours=eff_ttl)).strftime("%Y-%m-%d %H:%M:%S")
        if eff_ttl > 0 else None
    )

    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            _purge_expired_memories(conn)
            category = _classify_memory_category(f"{clean_key} {clean_val}")
            is_sens = _is_sensitive_memory(clean_key, clean_val, category)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            existing_key = _find_overlapping_key(conn, clean_key)
            with conn:
                if existing_key:
                    conn.execute(
                        "UPDATE memories SET key = ?, value = ?, category = ?, updated_at = ?, "
                        "expires_at = ?, is_sensitive = ? WHERE key = ?",
                        (clean_key, clean_val, category, now_str, expires_at, is_sens, existing_key),
                    )
                else:
                    conn.execute(
                        "INSERT INTO memories (key, value, category, updated_at, expires_at, is_sensitive) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (clean_key, clean_val, category, now_str, expires_at, is_sens),
                    )
            conn.close()

            ttl_msg = f" (expira automaticamente em {eff_ttl}h)" if eff_ttl > 0 else ""
            return {
                "status": "ok",
                "message": f"Silva: Anotado: {clean_key} = {clean_val}{ttl_msg}.",
                "data": {
                    "key": clean_key, "value": clean_val, "category": category,
                    "expires_at": expires_at, "is_sensitive": bool(is_sens),
                },
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
            _purge_expired_memories(conn)
            cur = conn.cursor()

            # 1. Busca FTS5 com prefixos '*'
            fts_query_parts = [f'"{re.sub(r"[^\w]", "", t)}"*' for t in query_tokens if re.sub(r"[^\w]", "", t)]
            if fts_query_parts:
                fts_query_str = " OR ".join(fts_query_parts)
                try:
                    cur.execute(
                        "SELECT m.key, m.value, m.category, m.updated_at, m.is_sensitive, bm25(memories_fts) as rank "
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
                            "is_sensitive": row["is_sensitive"],
                            "score": -float(row["rank"])
                        })
                except Exception:
                    pass

            # 2. Fallback LIKE se FTS5 não trouxe nada
            if not matches:
                for token in query_tokens:
                    like_pattern = f"%{token}%"
                    cur.execute(
                        "SELECT key, value, category, updated_at, is_sensitive FROM memories "
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
                                "is_sensitive": row["is_sensitive"],
                                "score": 1.0
                            })
            conn.close()
        except Exception:
            pass

    # 3. Busca em compromissos da agenda unificada (scheduled_events no memory.db)
    event_matches = []
    try:
        conn = _get_memory_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT title, event_type, trigger_at, status FROM scheduled_events "
            "WHERE status IN ('pending', 'pre_alerted') ORDER BY trigger_at ASC"
        )
        rows = cur.fetchall()
        conn.close()
        is_agenda_query = any(w in norm_query for w in ["agenda", "compromisso", "compromissos", "evento", "eventos", "reuniao", "lembrete", "lembretes"])
        for r in rows:
            ev_title = r["title"] or ""
            trig = r["trigger_at"] or ""
            ev_date = trig[:10]
            ev_time = trig[11:16]
            norm_title = _normalize_text(ev_title)
            if is_agenda_query or norm_query in norm_title or norm_title in norm_query or set(query_tokens).intersection(set(norm_title.split())):
                event_matches.append(f"'{ev_title}' em {ev_date} às {ev_time}")
    except Exception:
        pass

    if not matches and not event_matches:
        return {
            "status": "ok",
            "message": f"Silva: Nenhuma anotação ou compromisso encontrado sobre '{clean_query}'.",
            "data": {"found": False, "query": clean_query}
        }

    parts = []
    clipboard_text = None
    if matches:
        notes_str = "; ".join(
            f"{m['key']}: {m['value']} ({_format_relative_time(m.get('updated_at', ''))})"
            for m in matches[:3]
        )
        parts.append(f"Memória: {notes_str}")

        top_m = matches[0]
        top_val = str(top_m.get("value") or "").strip()
        should_copy = (
            bool(top_m.get("is_sensitive"))
            or top_m.get("category") in ("senha", "wifi")
            or (
                0 < len(top_val) <= 120
                and any(w in _normalize_text(top_m.get("key", "")) for w in ("pix", "cpf", "codigo", "senha", "wifi", "telefone", "cep"))
            )
        )
        if should_copy and top_val:
            try:
                from .comms import set_clipboard
                set_clipboard(top_val)
                clipboard_text = top_val
            except Exception:
                pass

    if event_matches:
        ev_str = "; ".join(event_matches[:4])
        parts.append(f"Agenda: {ev_str}")

    clip_note = " Copiado automaticamente para sua área de transferência." if clipboard_text else ""
    msg = "Silva: " + " | ".join(parts) + "." + clip_note

    return {
        "status": "ok",
        "message": msg,
        "data": {
            "found": True,
            "notes": [
                {
                    "key": m["key"], "value": m["value"],
                    "category": m.get("category", "geral"), "updated_at": m.get("updated_at"),
                }
                for m in matches[:5]
            ],
            "events": event_matches,
            "clipboard_text": clipboard_text,
        },
    }


def forget_note(query: str) -> Dict[str, Any]:
    """Busca e remove uma anotação da memória local (com pedido de desambiguação se houver múltiplas)."""
    clean_q = str(query or "").strip()
    if not clean_q:
        return {"status": "error", "message": "Informe qual anotação você deseja esquecer."}

    norm_q = _normalize_text(clean_q)
    noise = {"a", "o", "as", "os", "de", "do", "da", "anotacao", "nota", "lembranca", "antiga", "antigo"}
    tokens = [t for t in norm_q.split() if t not in noise and len(t) >= 2] or norm_q.split()

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _purge_expired_memories(conn)
            cur = conn.cursor()

            cur.execute("SELECT id, key FROM memories WHERE lower(key) = lower(?)", (clean_q,))
            exact = cur.fetchall()
            if exact:
                with conn:
                    cur.execute("DELETE FROM memories WHERE id = ?", (exact[0]["id"],))
                return {
                    "status": "ok",
                    "message": f"Silva: Anotação '{exact[0]['key']}' removida da memória.",
                    "data": {"deleted": exact[0]["key"]},
                }

            found_rows = []
            fts_parts = [f'"{re.sub(r"[^\w]", "", t)}"*' for t in tokens if re.sub(r"[^\w]", "", t)]
            if fts_parts:
                try:
                    cur.execute(
                        "SELECT m.id, m.key FROM memories_fts f JOIN memories m ON f.rowid = m.id "
                        "WHERE memories_fts MATCH ? LIMIT 5",
                        (" OR ".join(fts_parts),),
                    )
                    found_rows = cur.fetchall()
                except Exception:
                    found_rows = []

            if not found_rows:
                for tok in tokens:
                    cur.execute(
                        "SELECT id, key FROM memories WHERE key LIKE ? OR value LIKE ? LIMIT 5",
                        (f"%{tok}%", f"%{tok}%"),
                    )
                    for r in cur.fetchall():
                        if not any(fr["id"] == r["id"] for fr in found_rows):
                            found_rows.append(r)

            if not found_rows:
                return {
                    "status": "ok",
                    "message": f"Silva: Nenhuma anotação encontrada sobre '{clean_q}' para apagar.",
                    "data": {"deleted": None},
                }

            if len(found_rows) > 1:
                opts = ", ".join(f"'{r['key']}'" for r in found_rows[:5])
                return {
                    "status": "ok",
                    "message": f"Silva: Encontrei mais de uma anotação para '{clean_q}': {opts}. Qual delas você quer apagar?",
                    "data": {"ambiguous": True, "candidates": [r["key"] for r in found_rows[:5]]},
                }

            target_row = found_rows[0]
            with conn:
                cur.execute("DELETE FROM memories WHERE id = ?", (target_row["id"],))
            return {
                "status": "ok",
                "message": f"Silva: Anotação '{target_row['key']}' removida da memória.",
                "data": {"deleted": target_row["key"]},
            }
        finally:
            conn.close()


def list_memories(category: str = "") -> Dict[str, Any]:
    """Lista todas as memórias ativas não expiradas agrupadas por categoria (ou filtradas)."""
    clean_cat = _normalize_text(category)
    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _purge_expired_memories(conn)
            cur = conn.cursor()
            if clean_cat:
                cur.execute(
                    "SELECT key, value, category, updated_at, expires_at FROM memories "
                    "WHERE lower(category) = ? ORDER BY id DESC",
                    (clean_cat,),
                )
            else:
                cur.execute(
                    "SELECT key, value, category, updated_at, expires_at FROM memories "
                    "ORDER BY category ASC, id DESC"
                )
            rows = cur.fetchall()
        finally:
            conn.close()

    if not rows:
        scope = f" na categoria '{category}'" if clean_cat else ""
        return {
            "status": "ok",
            "message": f"Silva: Nenhuma memória salva{scope} no momento.",
            "data": {"total": 0, "groups": {}},
        }

    groups: Dict[str, list] = {}
    for r in rows:
        cat = r["category"] or "geral"
        rel = _format_relative_time(r["updated_at"])
        groups.setdefault(cat, []).append({
            "key": r["key"], "value": r["value"], "relative_time": rel, "expires_at": r["expires_at"],
        })

    lines = [f"Silva: Memórias salvas ({len(rows)}):"]
    for cat, items in groups.items():
        lines.append(f"[{cat.upper()}]")
        for it in items:
            lines.append(f"• {it['key']}: {it['value']} ({it['relative_time']})")

    return {
        "status": "ok",
        "message": "\n".join(lines),
        "data": {"total": len(rows), "groups": groups},
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


_UNIT_ALIASES = {
    # Distância
    "km": "km", "quilometro": "km", "quilometros": "km", "kilometro": "km", "kilometros": "km",
    "m": "m", "metro": "m", "metros": "m",
    "cm": "cm", "centimetro": "cm", "centimetros": "cm",
    "mm": "mm", "milimetro": "mm", "milimetros": "mm",
    "mi": "mi", "milha": "mi", "milhas": "mi",
    "yd": "yd", "jarda": "yd", "jardas": "yd",
    "ft": "ft", "pe": "ft", "pes": "ft",
    "in": "in", "polegada": "in", "polegadas": "in",
    # Massa / Peso
    "kg": "kg", "quilo": "kg", "quilos": "kg", "quilograma": "kg", "quilogramas": "kg", "kilo": "kg", "kilos": "kg",
    "g": "g", "grama": "g", "gramas": "g",
    "mg": "mg", "miligrama": "mg", "miligramas": "mg",
    "t": "t", "ton": "t", "tonelada": "t", "toneladas": "t",
    "lb": "lb", "lbs": "lb", "libra": "lb", "libras": "lb",
    "oz": "oz", "onca": "oz", "oncas": "oz",
    # Temperatura
    "c": "c", "celsius": "c", "grau celsius": "c", "graus celsius": "c", "centigrados": "c",
    "f": "f", "fahrenheit": "f", "grau fahrenheit": "f", "graus fahrenheit": "f",
    "k": "k", "kelvin": "k",
    # Volume
    "l": "l", "litro": "l", "litros": "l",
    "ml": "ml", "mililitro": "ml", "mililitros": "ml",
    "gal": "gal", "galao": "gal", "galoes": "gal",
    # Moedas
    "brl": "brl", "real": "brl", "reais": "brl", "r$": "brl",
    "usd": "usd", "dolar": "usd", "dolares": "usd", "us$": "usd", "$": "usd",
    "eur": "eur", "euro": "eur", "euros": "eur",
    "gbp": "gbp", "libra esterlina": "gbp", "libras esterlinas": "gbp",
    "ars": "ars", "peso argentino": "ars", "pesos argentinos": "ars",
    "jpy": "jpy", "iene": "jpy", "ienes": "jpy",
}

_DISTANCE_FACTORS_M = {
    "km": 1000.0, "m": 1.0, "cm": 0.01, "mm": 0.001,
    "mi": 1609.344, "yd": 0.9144, "ft": 0.3048, "in": 0.0254,
}
_MASS_FACTORS_G = {
    "kg": 1000.0, "g": 1.0, "mg": 0.001, "t": 1_000_000.0,
    "lb": 453.59237, "oz": 28.349523125,
}
_VOLUME_FACTORS_L = {
    "l": 1.0, "ml": 0.001, "gal": 3.785411784,
}
_TEMP_UNITS = {"c", "f", "k"}
_CURRENCY_RATES_TO_BRL = {
    "brl": 1.0,
    "usd": 5.80,
    "eur": 6.15,
    "gbp": 7.30,
    "ars": 0.0058,
    "jpy": 0.0375,
}


def _normalize_unit(unit_str: str) -> str:
    norm = _normalize_text(unit_str).replace("°", "").strip()
    norm = re.sub(r"\s+", " ", norm)
    return _UNIT_ALIASES.get(norm, norm)


def _format_physical_number(val: float) -> str:
    if abs(val - round(val)) < 1e-9:
        return str(int(round(val)))
    formatted = f"{val:.4f}".rstrip("0").rstrip(".")
    return formatted


def _fetch_currency_rate(from_cur: str, to_cur: str) -> tuple[float, bool]:
    """Retorna (taxa, is_online) consultando AwesomeAPI com fallback offline."""
    if from_cur == to_cur:
        return 1.0, True
    pair_key = f"{from_cur.upper()}{to_cur.upper()}"
    url = f"https://economia.awesomeapi.com.br/json/last/{from_cur.upper()}-{to_cur.upper()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SilvaAgent/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if pair_key in data and "bid" in data[pair_key]:
                return float(data[pair_key]["bid"]), True
    except Exception:
        pass
    rate = _CURRENCY_RATES_TO_BRL[from_cur] / _CURRENCY_RATES_TO_BRL[to_cur]
    return rate, False


def convert_units(amount: float, from_unit: str, to_unit: str) -> Dict[str, Any]:
    """Converte medidas físicas (distância, massa, temperatura, volume) e moedas (online/offline)."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return {"status": "error", "message": f"Valor numérico inválido para conversão: '{amount}'."}

    u_from = _normalize_unit(from_unit)
    u_to = _normalize_unit(to_unit)

    if not u_from or not u_to:
        return {"status": "error", "message": "Unidades de origem e destino não informadas."}

    # 1. Moedas
    if u_from in _CURRENCY_RATES_TO_BRL and u_to in _CURRENCY_RATES_TO_BRL:
        rate, is_online = _fetch_currency_rate(u_from, u_to)
        result_val = round(val * rate, 2)
        src_note = "" if is_online else " (cotação offline estimada)"
        return {
            "status": "ok",
            "message": f"Silva: {_format_physical_number(val)} {u_from.upper()} = {result_val:.2f} {u_to.upper()}{src_note}.",
            "data": {
                "amount": val, "from_unit": u_from.upper(), "to_unit": u_to.upper(),
                "result": result_val, "rate": rate, "online": is_online, "category": "currency",
            },
        }

    # 2. Temperatura
    if u_from in _TEMP_UNITS and u_to in _TEMP_UNITS:
        if u_from == u_to:
            c_res = val
        else:
            if u_from == "c":
                c_base = val
            elif u_from == "f":
                c_base = (val - 32.0) * 5.0 / 9.0
            else:
                c_base = val - 273.15

            if u_to == "c":
                c_res = c_base
            elif u_to == "f":
                c_res = (c_base * 9.0 / 5.0) + 32.0
            else:
                c_res = c_base + 273.15

        res_fmt = _format_physical_number(c_res)
        return {
            "status": "ok",
            "message": f"Silva: {_format_physical_number(val)} °{u_from.upper()} = {res_fmt} °{u_to.upper()}.",
            "data": {"amount": val, "from_unit": u_from, "to_unit": u_to, "result": round(c_res, 4), "category": "temperature"},
        }

    # 3. Distância, Massa e Volume
    for cat_name, table in (
        ("distance", _DISTANCE_FACTORS_M),
        ("mass", _MASS_FACTORS_G),
        ("volume", _VOLUME_FACTORS_L),
    ):
        if u_from in table and u_to in table:
            res_val = val * table[u_from] / table[u_to]
            res_fmt = _format_physical_number(res_val)
            return {
                "status": "ok",
                "message": f"Silva: {_format_physical_number(val)} {u_from} = {res_fmt} {u_to}.",
                "data": {"amount": val, "from_unit": u_from, "to_unit": u_to, "result": round(res_val, 4), "category": cat_name},
            }

    return {
        "status": "error",
        "message": f"Não é possível converter '{from_unit}' para '{to_unit}' (unidades desconhecidas ou de categorias incompatíveis).",
    }


_LIST_SYNONYMS = {
    "": "compras",
    "mercado": "compras",
    "supermercado": "compras",
    "feira": "compras",
    "compras": "compras",
    "lista de compras": "compras",
    "tarefa": "tarefas",
    "tarefas": "tarefas",
    "afazeres": "tarefas",
    "pendencias": "tarefas",
    "to-do": "tarefas",
    "todo": "tarefas",
    "lista de tarefas": "tarefas",
}


def _normalize_list_name(name: str) -> str:
    """Padroniza nomes comuns de listas em PT-BR."""
    norm = _normalize_text(name)
    norm = re.sub(r"^(?:lista\s+de\s+|lista\s+do\s+|lista\s+da\s+)", "", norm).strip()
    return _LIST_SYNONYMS.get(norm, norm or "compras")


def add_list_item(item: str, list_name: str = "compras") -> Dict[str, Any]:
    """Adiciona um ou múltiplos itens (separados por vírgula ou 'e') a uma lista persistente."""
    raw_item = str(item or "").strip()
    if not raw_item:
        return {"status": "error", "message": "Informe o item para adicionar à lista."}

    target_list = _normalize_list_name(list_name)
    parts = [p.strip() for p in re.split(r"\s*,\s*|\s+e\s+", raw_item, flags=re.IGNORECASE) if p.strip()]
    if not parts:
        return {"status": "error", "message": "Nenhum item válido informado."}

    added = []
    already = []
    with _FILE_LOCK:
        conn = _get_memory_db()
        with conn:
            cur = conn.cursor()
            for it in parts:
                cur.execute(
                    "INSERT OR IGNORE INTO lists (list_name, item) VALUES (?, ?)",
                    (target_list, it),
                )
                if cur.rowcount > 0:
                    added.append(it)
                else:
                    already.append(it)
        conn.close()

    msg_parts = []
    if added:
        msg_parts.append(f"Adicionado(s) à lista '{target_list}': {', '.join(added)}")
    if already:
        msg_parts.append(f"Já estava(m) na lista: {', '.join(already)}")

    return {
        "status": "ok",
        "message": f"Silva: {'. '.join(msg_parts)}.",
        "data": {"list_name": target_list, "added": added, "already_present": already},
    }


def get_list(list_name: str = "compras") -> Dict[str, Any]:
    """Consulta os itens ativos de uma lista ou resume todas as listas existentes."""
    raw_name = str(list_name or "compras").strip().lower()
    with _FILE_LOCK:
        conn = _get_memory_db()
        cur = conn.cursor()
        if raw_name in ("todas", "all", "listas"):
            cur.execute("SELECT list_name, item FROM lists ORDER BY list_name ASC, id ASC")
            rows = cur.fetchall()
            conn.close()
            if not rows:
                return {"status": "ok", "message": "Silva: Nenhuma lista possui itens no momento.", "data": {"lists": {}}}
            grouped: Dict[str, list] = {}
            for r in rows:
                grouped.setdefault(r["list_name"], []).append(r["item"])
            lines = ["Silva: Suas listas ativas:"]
            for lname, items in grouped.items():
                lines.append(f"• {lname} ({len(items)}): {', '.join(items)}")
            return {"status": "ok", "message": "\n".join(lines), "data": {"lists": grouped}}

        target_list = _normalize_list_name(list_name)
        cur.execute("SELECT item FROM lists WHERE list_name = ? ORDER BY id ASC", (target_list,))
        rows = cur.fetchall()
        conn.close()

    items = [r["item"] for r in rows]
    if not items:
        return {
            "status": "ok",
            "message": f"Silva: A lista '{target_list}' está vazia.",
            "data": {"list_name": target_list, "items": []},
        }

    numbered = "\n".join(f"{idx}. {it}" for idx, it in enumerate(items, 1))
    return {
        "status": "ok",
        "message": f"Silva: Lista '{target_list}' ({len(items)} item(ns)):\n{numbered}",
        "data": {"list_name": target_list, "items": items},
    }


def remove_list_item(item: str, list_name: str = "compras") -> Dict[str, Any]:
    """Remove um item específico (exato ou substring) ou limpa todos os itens de uma lista."""
    clean_item = str(item or "").strip()
    if not clean_item:
        return {"status": "error", "message": "Informe o item a remover (ou 'tudo' para limpar a lista)."}

    target_list = _normalize_list_name(list_name)
    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            with conn:
                cur = conn.cursor()
                if clean_item.lower() in ("tudo", "todos", "limpar", "esvaziar"):
                    cur.execute("DELETE FROM lists WHERE list_name = ?", (target_list,))
                    deleted_count = cur.rowcount
                    return {
                        "status": "ok",
                        "message": f"Silva: Lista '{target_list}' limpa ({deleted_count} item(ns) removido(s)).",
                        "data": {"list_name": target_list, "cleared": True, "removed_count": deleted_count},
                    }

                cur.execute(
                    "SELECT id, item FROM lists WHERE list_name = ? AND lower(item) = lower(?)",
                    (target_list, clean_item),
                )
                matches = cur.fetchall()
                if not matches:
                    cur.execute(
                        "SELECT id, item FROM lists WHERE list_name = ? AND lower(item) LIKE ?",
                        (target_list, f"%{clean_item.lower()}%"),
                    )
                    matches = cur.fetchall()

                if not matches:
                    return {
                        "status": "ok",
                        "message": f"Silva: O item '{clean_item}' não estava na lista '{target_list}'.",
                        "data": {"list_name": target_list, "removed": []},
                    }

                removed_names = [m["item"] for m in matches]
                ids = [m["id"] for m in matches]
                placeholders = ",".join("?" for _ in ids)
                cur.execute(f"DELETE FROM lists WHERE id IN ({placeholders})", ids)
        finally:
            conn.close()

    return {
        "status": "ok",
        "message": f"Silva: Removido(s) da lista '{target_list}': {', '.join(removed_names)}.",
        "data": {"list_name": target_list, "removed": removed_names},
    }


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




def remind_on_wifi(ssid: str, reminder: str) -> Dict[str, Any]:
    """
    Agenda um lembrete contextual proativo disparado quando o aparelho conectar a um Wi-Fi específico.
    Suporta aliases ('casa', 'trabalho', 'escritorio') via memória salva ou 'neste wifi'/'aqui' via Wi-Fi atual.
    """
    reminder_clean = str(reminder or "").strip()
    if not reminder_clean:
        return {"status": "error", "message": "Texto do lembrete não informado."}

    ssid_raw = str(ssid or "").strip()
    ssid_norm = _normalize_text(ssid_raw)
    resolved_ssid = ssid_raw

    # 1. "neste wifi" / "aqui" / vazio -> usa SSID conectado atualmente
    if not ssid_raw or ssid_norm in ("neste wifi", "este wifi", "wifi atual", "aqui", "nessa rede", "esta rede"):
        try:
            from .hardware import get_wifi_info
            wifi_res = get_wifi_info()
            current_ssid = str((wifi_res.get("data") or {}).get("ssid") or "").strip()
        except Exception:
            current_ssid = ""

        if not current_ssid or current_ssid.lower() in ("<unknown ssid>", "desconhecido", "none"):
            return {
                "status": "error",
                "message": "Não consegui identificar o Wi-Fi atual conectado. Informe o nome da rede (SSID).",
            }
        resolved_ssid = current_ssid

    # 2. Aliases amigáveis ("casa", "trabalho", "escritorio") -> consulta memória salva
    elif ssid_norm in ("casa", "minha casa", "trabalho", "meu trabalho", "escritorio", "meu escritorio"):
        alias_core = ssid_norm.replace("minha ", "").replace("meu ", "").strip()
        with _FILE_LOCK:
            try:
                conn = _get_memory_db()
                cur = conn.cursor()
                cur.execute(
                    "SELECT value FROM memories "
                    "WHERE lower(key) IN (?, ?, ?, ?) "
                    "OR (lower(key) LIKE '%wifi%' AND lower(key) LIKE ?) "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (
                        f"wifi_{alias_core}",
                        f"wifi {alias_core}",
                        f"ssid_{alias_core}",
                        f"ssid {alias_core}",
                        f"%{alias_core}%",
                    ),
                )
                row = cur.fetchone()
                conn.close()
                if row and str(row["value"] or "").strip():
                    resolved_ssid = str(row["value"]).strip()
            except Exception:
                pass

    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            with conn:
                conn.execute(
                    "INSERT INTO context_reminders (trigger_type, trigger_value, reminder_text, is_active) "
                    "VALUES ('wifi', ?, ?, 1)",
                    (resolved_ssid, reminder_clean),
                )
            conn.close()
        except Exception as e:
            return {"status": "error", "message": f"Erro ao salvar lembrete contextual: {str(e)}"}

    return {
        "status": "ok",
        "message": f"Silva: Combinado! Assim que seu celular conectar no Wi-Fi '{resolved_ssid}', vou te lembrar de: {reminder_clean}.",
        "data": {
            "trigger_type": "wifi",
            "ssid": resolved_ssid,
            "reminder": reminder_clean,
        },
    }


def active_recall_search(question: str) -> Dict[str, Any]:
    """
    Busca silenciosa de ultra-baixa latência (<2ms) no memories_fts para Recordação Ativa Pré-LLM.
    Retorna level='high' (disparo direto de recall_note), 'medium' (injeção de contexto) ou 'none'.
    """
    clean_q = str(question or "").strip()
    if not clean_q:
        return {"level": "none", "query": "", "top": None, "matches": []}

    norm_q = re.sub(r"[^\w\s]", " ", _normalize_text(clean_q))
    stopwords = {
        "qual", "quais", "onde", "quando", "quanto", "quantos", "quantas", "quem", "como",
        "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
        "em", "no", "na", "nos", "nas", "para", "pra", "pro", "por", "que", "e", "eh",
        "era", "foi", "sao", "esta", "estava", "fica", "me", "meu", "minha", "meus", "minhas",
        "voce", "vc", "sabe", "sobre", "lembra", "lembrar", "anotei", "salvei", "guardei",
        "diga", "diz", "fala", "mesmo",
    }
    tokens = [t for t in norm_q.split() if t not in stopwords and len(t) >= 2]
    if not tokens:
        return {"level": "none", "query": "", "top": None, "matches": []}

    matches = []
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            _purge_expired_memories(conn)
            cur = conn.cursor()
            fts_parts = [f'"{re.sub(r"[^\w]", "", t)}"*' for t in tokens if re.sub(r"[^\w]", "", t)]
            if fts_parts:
                fts_str = " OR ".join(fts_parts)
                cur.execute(
                    "SELECT m.key, m.value, m.category, m.updated_at, m.is_sensitive, bm25(memories_fts) as rank "
                    "FROM memories_fts f "
                    "JOIN memories m ON f.rowid = m.id "
                    "WHERE memories_fts MATCH ? "
                    "ORDER BY rank ASC LIMIT 3",
                    (fts_str,),
                )
                for row in cur.fetchall():
                    bm25_pos = max(0.0, -float(row["rank"]))
                    norm_kv = _normalize_text(f"{row['key']} {row['value']}")
                    matched_count = sum(1 for t in tokens if t in norm_kv)
                    overlap = matched_count / len(tokens)
                    matches.append({
                        "key": row["key"],
                        "value": row["value"],
                        "category": row["category"],
                        "updated_at": row["updated_at"],
                        "bm25": bm25_pos,
                        "overlap": overlap,
                    })
            conn.close()
        except Exception:
            pass

    if not matches:
        return {"level": "none", "query": " ".join(tokens), "top": None, "matches": []}

    matches.sort(key=lambda m: (m["overlap"], m["bm25"]), reverse=True)
    top = matches[0]
    if top["overlap"] >= 0.8 or (len(tokens) == 1 and top["overlap"] == 1.0 and top["bm25"] >= 0.3):
        level = "high"
    elif top["overlap"] >= 0.4 or top["bm25"] >= 0.3:
        level = "medium"
    else:
        level = "none"

    return {
        "level": level,
        "query": " ".join(tokens),
        "top": top,
        "matches": matches,
    }


# Alias de compatibilidade
_init_memory_db = _get_memory_db
