"""
Motor de Monitoramento Autônomo de Sono Noturno, Arquitetura Estimada do Sono
e Análise Longitudinal Persistente em SQLite (memory.db).
"""

import json
import statistics
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .adb_bridge import ensure_adb_connected, is_screen_unlocked, run_adb_shell
from .core import _FILE_LOCK
from .memory_schedule import _get_memory_db

_WEB_ACTIVITY_LOCK = threading.Lock()
_LAST_WEB_ACTIVITY_TS: Optional[datetime] = None

_INACTIVITY_SLEEP_SECONDS = 7200  # 2 horas
_MIN_SLEEP_LOG_MINUTES = 150      # 2h30min
_FALSE_SLEEP_AWAKE_MINUTES = 15   # >= 15 min ativo antes da 01:00 descarta falso sono
_MERGE_WINDOW_MAX_AWAKE = 20      # < 20 min acordado antes das 04:30 funde blocos
_IDEAL_SLEEP_MINUTES = 450        # 7h30 (5 ciclos de 90 min)
_MAX_PHYSIOLOGICAL_SLEEP_MINUTES = 840  # 14h: trava anti-outlier (inatividade prolongada)
_IDEAL_BEDTIME_HOUR = 23
_IDEAL_BEDTIME_MINUTE = 30


def _ensure_sleep_tables(conn) -> None:
    """Garante e migra de forma idempotente as tabelas sleep_state e sleep_logs no memory.db."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sleep_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_status TEXT NOT NULL DEFAULT 'awake',
            last_active_ts TEXT NOT NULL,
            sleep_start_ts TEXT DEFAULT NULL,
            monitoring_enabled INTEGER NOT NULL DEFAULT 1,
            awake_minutes_accumulated INTEGER NOT NULL DEFAULT 0,
            brief_awake_since TEXT DEFAULT NULL,
            manual_sleep_override INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sleep_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sleep_start_ts TEXT NOT NULL,
            wake_up_ts TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            sleep_score INTEGER NOT NULL,
            cycles_estimated REAL NOT NULL,
            bedtime_deviation_minutes INTEGER DEFAULT 0,
            trend_status TEXT NOT NULL DEFAULT 'baseline',
            report_markdown TEXT NOT NULL,
            awake_minutes INTEGER NOT NULL DEFAULT 0,
            delivered_to_chat INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    state_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sleep_state)").fetchall()}
    if "awake_minutes_accumulated" not in state_cols:
        conn.execute("ALTER TABLE sleep_state ADD COLUMN awake_minutes_accumulated INTEGER NOT NULL DEFAULT 0")
    if "brief_awake_since" not in state_cols:
        conn.execute("ALTER TABLE sleep_state ADD COLUMN brief_awake_since TEXT DEFAULT NULL")
    if "manual_sleep_override" not in state_cols:
        conn.execute("ALTER TABLE sleep_state ADD COLUMN manual_sleep_override INTEGER NOT NULL DEFAULT 0")

    log_cols = {r["name"] for r in conn.execute("PRAGMA table_info(sleep_logs)").fetchall()}
    if "awake_minutes" not in log_cols:
        conn.execute("ALTER TABLE sleep_logs ADD COLUMN awake_minutes INTEGER NOT NULL DEFAULT 0")
    if "delivered_to_chat" not in log_cols:
        conn.execute("ALTER TABLE sleep_logs ADD COLUMN delivered_to_chat INTEGER NOT NULL DEFAULT 0")


def record_web_activity(ts: Optional[datetime] = None) -> None:
    """Registra atividade recente na Web UI e atualiza last_active_ts em sleep_state (anti-Doze)."""
    global _LAST_WEB_ACTIVITY_TS
    now_dt = ts or datetime.now()
    with _WEB_ACTIVITY_LOCK:
        _LAST_WEB_ACTIVITY_TS = now_dt

    now_iso = now_dt.isoformat(timespec="seconds")
    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            row = conn.execute("SELECT current_status FROM sleep_state WHERE id = 1").fetchone()
            with conn:
                if row is None:
                    conn.execute(
                        "INSERT INTO sleep_state (id, current_status, last_active_ts, sleep_start_ts, monitoring_enabled) "
                        "VALUES (1, 'awake', ?, NULL, 1)",
                        (now_iso,),
                    )
                elif str(row["current_status"]) == "awake":
                    conn.execute("UPDATE sleep_state SET last_active_ts = ? WHERE id = 1", (now_iso,))
        finally:
            conn.close()


def get_undelivered_sleep_reports() -> List[Dict[str, Any]]:
    """Retorna relatórios de sleep_logs com delivered_to_chat = 0 sem marcá-los como entregues."""
    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            rows = conn.execute(
                "SELECT id, report_markdown, created_at FROM sleep_logs "
                "WHERE delivered_to_chat = 0 ORDER BY id ASC"
            ).fetchall()
            return [
                {
                    "id": int(r["id"]),
                    "report_markdown": str(r["report_markdown"]),
                    "created_at": str(r["created_at"] or ""),
                }
                for r in rows
            ]
        finally:
            conn.close()


def ack_sleep_reports(report_ids: List[int]) -> int:
    """Marca relatórios como entregues (delivered_to_chat = 1) após confirmação do cliente."""
    clean_ids = []
    for rid in report_ids or []:
        try:
            clean_ids.append(int(rid))
        except (TypeError, ValueError):
            continue
    if not clean_ids:
        return 0

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            updated = 0
            with conn:
                for rid in clean_ids:
                    cur = conn.execute(
                        "UPDATE sleep_logs SET delivered_to_chat = 1 WHERE id = ?",
                        (rid,),
                    )
                    updated += int(cur.rowcount or 0)
            return updated
        finally:
            conn.close()


def _is_night_window(dt: datetime) -> bool:
    """Janela de monitoramento noturno: 19:15 até 11:59 do dia seguinte."""
    return (dt.hour > 19 or (dt.hour == 19 and dt.minute >= 15)) or (dt.hour < 12)


def _is_before_0100(dt: datetime) -> bool:
    """Retorna True se estiver no início da noite (19:00–23:59 ou 00:00–00:59)."""
    return dt.hour >= 19 or dt.hour < 1


def _is_before_0430(dt: datetime) -> bool:
    """Retorna True se estiver na janela de consolidação da madrugada (< 04:30)."""
    return dt.hour < 4 or (dt.hour == 4 and dt.minute < 30)


def _is_weekend_night(sleep_start_dt: datetime) -> bool:
    """Retorna True para noites de sexta->sábado (weekday=4) e sábado->domingo (weekday=5)."""
    evening_dt = sleep_start_dt if sleep_start_dt.hour >= 18 else (sleep_start_dt - timedelta(days=1))
    return evening_dt.weekday() in (4, 5)


def _is_media_playing() -> bool:
    """Verifica via ADB dumpsys media_session se há reprodução de áudio/vídeo ou cast ativo (state=3)."""
    adb_ser = ensure_adb_connected()
    if not adb_ser:
        return False
    ok, out = run_adb_shell(["dumpsys", "media_session"], timeout=4.0)
    if not ok or not out:
        return False
    return "state=3" in out or "PlaybackState {state=3" in out


def _detect_device_activity(now: datetime) -> bool:
    """
    Detecta atividade real do usuário:
    - Atividade recente na Web UI (últimos 30s), OU
    - Tela desbloqueada via ADB (lockscreen acesa por notificação NÃO conta como ativo).
    """
    with _WEB_ACTIVITY_LOCK:
        if _LAST_WEB_ACTIVITY_TS is not None:
            if (now - _LAST_WEB_ACTIVITY_TS).total_seconds() <= 30.0:
                return True

    adb_ser = ensure_adb_connected()
    if adb_ser:
        unlocked, _ = is_screen_unlocked(serial=adb_ser)
        return bool(unlocked)

    return False


def _format_duration_hm(total_minutes: int) -> str:
    mins = max(0, int(total_minutes))
    hours, rem = divmod(mins, 60)
    if hours <= 0:
        return f"{rem}min"
    if rem == 0:
        return f"{hours}h"
    return f"{hours}h {rem:02d}min"


def _compute_bedtime_deviation(sleep_start_dt: datetime) -> int:
    """
    Desvio em minutos em relação ao horário-alvo de dormir (23:30 daquela noite).
    Em fins de semana (sexta->sábado e sábado->domingo), relaxa em até 60 min o horário-alvo.
    """
    evening_dt = sleep_start_dt if sleep_start_dt.hour >= 18 else (sleep_start_dt - timedelta(days=1))
    ideal_dt = evening_dt.replace(
        hour=_IDEAL_BEDTIME_HOUR,
        minute=_IDEAL_BEDTIME_MINUTE,
        second=0,
        microsecond=0,
    )
    if _is_weekend_night(sleep_start_dt):
        ideal_dt += timedelta(minutes=60)
    return int((sleep_start_dt - ideal_dt).total_seconds() // 60)


def _compute_sleep_score(duration_minutes: int, bedtime_deviation_minutes: int, is_weekend: bool = False) -> int:
    """Pontuação de 0 a 100 combinando duração (70 pts) e regularidade circadiana (30 pts)."""
    max_opt = 540 if is_weekend else 510
    min_opt = 420 if is_weekend else 450
    if min_opt <= duration_minutes <= max_opt:
        dur_score = 70.0
    elif duration_minutes < min_opt:
        dur_score = max(10.0, 70.0 * (duration_minutes / float(min_opt)))
    else:
        excess = duration_minutes - max_opt
        dur_score = max(35.0, 70.0 - (excess * 0.25))

    abs_dev = abs(bedtime_deviation_minutes)
    tolerance = 45 if is_weekend else 20
    if abs_dev <= tolerance:
        reg_score = 30.0
    elif is_weekend:
        reg_score = max(18.0, 30.0 - ((abs_dev - tolerance) * 0.1))
    else:
        reg_score = max(0.0, 30.0 - ((abs_dev - tolerance) * 0.2))

    return int(max(0, min(100, round(dur_score + reg_score))))


def _sync_sleep_memory(conn, summary_mem: str) -> None:
    """Atualiza a chave sleep_evolution_summary na tabela memories."""
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO memories (key, value, category, updated_at)
        VALUES ('sleep_evolution_summary', ?, 'saude', ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            category = excluded.category,
            updated_at = excluded.updated_at
        """,
        (summary_mem, now_iso),
    )


def _analyze_sleep_trend(
    conn,
    current_duration_min: int,
    current_score: int,
    sleep_start_dt: datetime,
) -> Dict[str, Any]:
    """
    Compara a noite atual com a MEDIANA móvel das últimas 7 noites em sleep_logs (anti-outlier)
    e classifica: 'baseline' | 'improving' | 'worsening' | 'stable'.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT duration_minutes, sleep_score, bedtime_deviation_minutes, sleep_start_ts "
        "FROM sleep_logs ORDER BY id DESC LIMIT 7"
    )
    prev_rows = cur.fetchall()

    if len(prev_rows) == 0:
        trend_status = "baseline"
        med_dur = current_duration_min
        med_score = current_score
        delta_min = 0
        delta_score = 0
        verdict = "Noite de referência registrada para acompanhar sua evolução"
    else:
        med_dur = int(round(statistics.median(int(r["duration_minutes"]) for r in prev_rows)))
        med_score = int(round(statistics.median(int(r["sleep_score"]) for r in prev_rows)))
        delta_min = current_duration_min - med_dur
        delta_score = current_score - med_score
        short_streak = sum(1 for r in prev_rows[:2] if int(r["duration_minutes"]) < 390)

        if (delta_score >= 5 or delta_min >= 25) and 390 <= current_duration_min <= 570:
            trend_status = "improving"
            sign = "+" if delta_min >= 0 else ""
            verdict = (
                f"📈 Seu sono está melhorando: você dormiu {sign}{delta_min} min "
                f"em relação à sua mediana recente de {_format_duration_hm(med_dur)}"
            )
        elif delta_min <= -30 or delta_score <= -5 or (current_duration_min < 390 and short_streak >= 1):
            trend_status = "worsening"
            if current_duration_min < 360 and short_streak >= 2:
                verdict = "📉 Alerta de piora: terceira noite seguida abaixo de 6h, acumulando débito de sono"
            else:
                verdict = (
                    f"📉 Alerta de piora: variação de {delta_min} min e {delta_score:+d} pts "
                    f"frente à mediana recente de {_format_duration_hm(med_dur)}"
                )
        else:
            trend_status = "stable"
            verdict = (
                f"⚖️ Sono estável: mantendo consistência próxima à mediana recente de "
                f"{_format_duration_hm(med_dur)} ({delta_score:+d} pts)"
            )

    summary_mem = (
        f"Último sono ({sleep_start_dt.strftime('%d/%m')}): {_format_duration_hm(current_duration_min)}, "
        f"nota {current_score}/100, tendência={trend_status}. {verdict}."
    )
    _sync_sleep_memory(conn, summary_mem)

    return {
        "trend_status": trend_status,
        "median_prev_duration": med_dur,
        "median_prev_score": med_score,
        "delta_minutes": delta_min,
        "delta_score": delta_score,
        "verdict": verdict,
    }


def _get_cached_news_briefing(limit: int = 3) -> List[str]:
    """Lê até 3 manchetes recentes de news_cache ('geral' ou mais recente) para o briefing matinal."""
    try:
        conn = _get_memory_db()
        try:
            row = conn.execute(
                "SELECT items_json FROM news_cache WHERE topic = 'geral' LIMIT 1"
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT items_json FROM news_cache ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            if not row:
                return []
            items = json.loads(str(row["items_json"]))
            if not isinstance(items, list):
                return []
            return [str(it.get("title") or "").strip() for it in items[:limit] if isinstance(it, dict) and it.get("title")]
        finally:
            conn.close()
    except Exception:
        return []


def build_scientific_sleep_report(
    sleep_start_dt: datetime,
    wake_up_dt: datetime,
    duration_minutes: int,
    sleep_score: int,
    cycles_estimated: float,
    trend_info: Dict[str, Any],
    awake_minutes: int = 0,
) -> str:
    """Gera relatório de sono compacto (Dashboard Card) com bloco secundário expansível (NREM/REM)."""
    nrem_total = int(round(duration_minutes * 0.775))
    rem_total = max(0, duration_minutes - nrem_total)
    n1_min = int(round(duration_minutes * 0.05))
    n2_min = int(round(duration_minutes * 0.475))
    n3_min = max(0, nrem_total - n1_min - n2_min)

    is_anomalous = duration_minutes > _MAX_PHYSIOLOGICAL_SLEEP_MINUTES
    anchor_wake_dt = (
        wake_up_dt.replace(hour=7, minute=0, second=0, microsecond=0)
        if is_anomalous
        else wake_up_dt
    )
    ideal_sleep_dt = anchor_wake_dt - timedelta(minutes=_IDEAL_SLEEP_MINUTES)
    ideal_disconnect_dt = ideal_sleep_dt - timedelta(minutes=15)

    sacrifice_notes: List[str] = []
    if is_anomalous:
        sacrifice_notes.append(
            "O período registrado excedeu o limite fisiológico normal (> 14h, provável inatividade do aparelho); "
            "utilizamos 07:00 como âncora matinal de referência."
        )
    elif sleep_start_dt.hour in (0, 1, 2, 3, 4, 5) or (sleep_start_dt.hour == 23 and sleep_start_dt.minute > 45):
        sacrifice_notes.append(
            "Ao dormir após o ideal, a janela de **N3 (sono profundo)** da primeira metade da noite é comprimida."
        )
    if duration_minutes < _IDEAL_SLEEP_MINUTES:
        deficit = _IDEAL_SLEEP_MINUTES - duration_minutes
        sacrifice_notes.append(
            f"Faltaram **{_format_duration_hm(deficit)}** para completar o 5º ciclo: parte do **REM final**, "
            "responsável pela regulação emocional e consolidação de memória, foi sacrificada."
        )
    if not sacrifice_notes:
        sacrifice_notes.append(
            "Você atingiu os **5 ciclos completos (7h30–8h00)** com boa preservação tanto de N3 inicial quanto de REM final."
        )

    trend_status = trend_info.get("trend_status", "baseline")
    trend_badges = {
        "improving": "📈 Melhorando",
        "worsening": "📉 Piorando",
        "stable": "⚖️ Estável",
        "baseline": "🆕 Referência",
    }
    badge_tendencia = trend_badges.get(trend_status, "🆕 Referência")

    if trend_status == "worsening":
        plan_line_1 = (
            f"Desconecte telas até **{ideal_disconnect_dt.strftime('%H:%M')}** para recuperar "
            "o débito de sono mirando 7h30–8h00 contínuos hoje."
        )
    elif trend_status == "improving":
        plan_line_1 = (
            f"Mantenha o desligamento de telas por volta de **{ideal_disconnect_dt.strftime('%H:%M')}** "
            "para consolidar a sequência positiva das últimas noites."
        )
    else:
        plan_line_1 = (
            f"Desligue telas às **{ideal_disconnect_dt.strftime('%H:%M')}** "
            f"para adormecer próximo de **{ideal_sleep_dt.strftime('%H:%M')}**."
        )
    plan_line_2 = (
        "Evite cafeína após as **14:00** e busque **10–15 min de luz solar matinal** ao acordar."
    )

    awake_note = f" (-{awake_minutes}m acordado)" if awake_minutes > 0 else ""

    lines = [
        f"Nota: {sleep_score}/100 | Duração: {_format_duration_hm(duration_minutes)}{awake_note} "
        f"({sleep_start_dt.strftime('%H:%M')} → {wake_up_dt.strftime('%H:%M')}) | Ciclos: {cycles_estimated:.1f} | Tendência: {badge_tendencia}",
        f"Arquitetura: N1 ~{n1_min}m (5%) • N2 ~{n2_min}m (48%) • N3 ~{n3_min}m (22%) • REM ~{rem_total}m (25%)",
        f"Meta Ideal: Dormir até {ideal_sleep_dt.strftime('%H:%M')} (desconectar {ideal_disconnect_dt.strftime('%H:%M')}) para completar 5 ciclos (7h30–8h00)",
    ]
    if is_anomalous:
        lines.append(
            "⚠️ **Duração anômala (> 14h):** excedeu o limite fisiológico normal (provável inatividade do aparelho); âncora matinal ajustada para **07:00**."
        )
    lines.extend([
        f"- **Desligamento hoje:** {plan_line_1}",
        f"- **Higiene circadiana:** {plan_line_2}",
        "",
        "### Detalhes Científicos (NREM/REM)",
        f"- **Sono não REM (NREM) — ~75% a 80% (~{_format_duration_hm(nrem_total)}):**",
        f"  - **N1 (~5%, ~{n1_min}m):** transição vigília→sono com relaxamento muscular rápido.",
        f"  - **N2 (~48%, ~{n2_min}m):** queda da temperatura corporal e frequência cardíaca; ocupa a maior parte da noite.",
        f"  - **N3 (~22%, ~{n3_min}m):** sono profundo restaurador, hormônios e imunidade.",
        f"- **Sono REM — ~25% (~{_format_duration_hm(rem_total)}):**",
        "  - **Memória e emoções:** alta atividade cerebral, sonhos vívidos e consolidação emocional.",
        f"- **Impacto observado:** {' '.join(sacrifice_notes)}",
    ])
    news_titles = _get_cached_news_briefing(limit=3)
    if news_titles:
        lines.extend(["", "### 📰 Resumo Rápido do Dia"])
        lines.extend(f"- {t}" for t in news_titles)
    return "\n".join(lines)


def _finalize_sleep_session(
    conn,
    sleep_start_dt: datetime,
    wake_up_dt: datetime,
    awake_minutes: int,
) -> Dict[str, Any]:
    """Calcula duração líquida, persiste em sleep_logs e retorna payload do relatório."""
    now_iso = wake_up_dt.isoformat(timespec="seconds")
    gross_minutes = max(0, int((wake_up_dt - sleep_start_dt).total_seconds() // 60))
    duration_minutes = max(0, gross_minutes - max(0, int(awake_minutes)))

    with conn:
        conn.execute(
            "UPDATE sleep_state SET current_status = 'awake', last_active_ts = ?, "
            "sleep_start_ts = NULL, awake_minutes_accumulated = 0, "
            "brief_awake_since = NULL, manual_sleep_override = 0 WHERE id = 1",
            (now_iso,),
        )

        if duration_minutes < _MIN_SLEEP_LOG_MINUTES:
            return {
                "status": "awake",
                "duration_minutes": duration_minutes,
                "report_generated": False,
            }

        cycles_estimated = round(duration_minutes / 90.0, 2)
        bedtime_dev = _compute_bedtime_deviation(sleep_start_dt)
        sleep_score = _compute_sleep_score(
            duration_minutes,
            bedtime_dev,
            is_weekend=_is_weekend_night(sleep_start_dt),
        )
        trend_info = _analyze_sleep_trend(conn, duration_minutes, sleep_score, sleep_start_dt)
        report_md = build_scientific_sleep_report(
            sleep_start_dt=sleep_start_dt,
            wake_up_dt=wake_up_dt,
            duration_minutes=duration_minutes,
            sleep_score=sleep_score,
            cycles_estimated=cycles_estimated,
            trend_info=trend_info,
            awake_minutes=awake_minutes,
        )
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO sleep_logs (
                sleep_start_ts, wake_up_ts, duration_minutes, sleep_score,
                cycles_estimated, bedtime_deviation_minutes, trend_status,
                report_markdown, awake_minutes, delivered_to_chat
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                sleep_start_dt.isoformat(timespec="seconds"),
                now_iso,
                duration_minutes,
                sleep_score,
                cycles_estimated,
                bedtime_dev,
                trend_info["trend_status"],
                report_md,
                int(awake_minutes),
            ),
        )
        log_id = int(cur.lastrowid)

    trend_label_map = {
        "improving": "Melhorando",
        "worsening": "Piorando",
        "stable": "Estável",
        "baseline": "Referência",
    }
    trend_pt = trend_label_map.get(trend_info["trend_status"], "Estável")
    notif_summary = (
        f"Você dormiu {_format_duration_hm(duration_minutes)} (Nota {sleep_score}/100) • "
        f"Tendência: {trend_pt}"
    )
    return {
        "status": "awake",
        "report_generated": True,
        "id": log_id,
        "title": "☀️ Bom dia! Relatório & Evolução do Sono",
        "summary": notif_summary,
        "duration_minutes": duration_minutes,
        "awake_minutes": int(awake_minutes),
        "sleep_score": sleep_score,
        "anomalous_duration": duration_minutes > _MAX_PHYSIOLOGICAL_SLEEP_MINUTES,
        "trend_status": trend_info["trend_status"],
        "report_markdown": report_md,
        "wake_up_ts": now_iso,
    }


def evaluate_sleep_cycle(
    now: Optional[datetime] = None,
    is_user_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Máquina de estados blindada do monitoramento noturno de sono:
    - Bloqueia transição para 'sleeping' se houver mídia ativa (_is_media_playing).
    - Descarta falso sono antes da 01:00 se atividade durar >= 15 min (sem manual_sleep_override).
    - Merge Window antes das 04:30: despertares < 20 min são fundidos e descontados em awake_minutes_accumulated.
    """
    cur_dt = now or datetime.now()
    active = _detect_device_activity(cur_dt) if is_user_active is None else bool(is_user_active)
    now_iso = cur_dt.isoformat(timespec="seconds")

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            row = conn.execute(
                "SELECT current_status, last_active_ts, sleep_start_ts, monitoring_enabled, "
                "awake_minutes_accumulated, brief_awake_since, manual_sleep_override "
                "FROM sleep_state WHERE id = 1"
            ).fetchone()
            if row is None:
                with conn:
                    conn.execute(
                        "INSERT INTO sleep_state (id, current_status, last_active_ts, sleep_start_ts, monitoring_enabled) "
                        "VALUES (1, 'awake', ?, NULL, 1)",
                        (now_iso,),
                    )
                return {"status": "awake", "report_generated": False}

            if int(row["monitoring_enabled"] or 0) == 0:
                return {"status": "disabled", "report_generated": False}

            current_status = str(row["current_status"] or "awake")
            last_active_dt = datetime.fromisoformat(str(row["last_active_ts"]))
            sleep_start_str = row["sleep_start_ts"]
            awake_acc = int(row["awake_minutes_accumulated"] or 0)
            brief_since_str = row["brief_awake_since"]
            manual_override = int(row["manual_sleep_override"] or 0)

            if current_status == "awake":
                if active:
                    with conn:
                        conn.execute("UPDATE sleep_state SET last_active_ts = ? WHERE id = 1", (now_iso,))
                    return {"status": "awake", "report_generated": False}

                idle_sec = (cur_dt - last_active_dt).total_seconds()
                if _is_night_window(cur_dt) and idle_sec >= _INACTIVITY_SLEEP_SECONDS:
                    if _is_media_playing():
                        with conn:
                            conn.execute("UPDATE sleep_state SET last_active_ts = ? WHERE id = 1", (now_iso,))
                        return {"status": "awake", "media_blocked": True, "report_generated": False}

                    retro_start = last_active_dt.isoformat(timespec="seconds")
                    with conn:
                        conn.execute(
                            "UPDATE sleep_state SET current_status = 'sleeping', sleep_start_ts = ?, "
                            "awake_minutes_accumulated = 0, brief_awake_since = NULL, manual_sleep_override = 0 "
                            "WHERE id = 1",
                            (retro_start,),
                        )
                    return {"status": "sleeping", "sleep_start_ts": retro_start, "report_generated": False}
                return {"status": "awake", "report_generated": False}

            # current_status == 'sleeping'
            sleep_start_dt = datetime.fromisoformat(str(sleep_start_str or row["last_active_ts"]))

            if not active:
                if brief_since_str:
                    brief_dt = datetime.fromisoformat(str(brief_since_str))
                    brief_mins = max(0, int((cur_dt - brief_dt).total_seconds() // 60))
                    if brief_mins < _MERGE_WINDOW_MAX_AWAKE:
                        new_acc = awake_acc + brief_mins
                        with conn:
                            conn.execute(
                                "UPDATE sleep_state SET awake_minutes_accumulated = ?, brief_awake_since = NULL WHERE id = 1",
                                (new_acc,),
                            )
                        return {
                            "status": "sleeping",
                            "sleep_start_ts": sleep_start_str,
                            "awake_minutes_accumulated": new_acc,
                            "merged_brief_awake": True,
                            "report_generated": False,
                        }
                    # Ficou >= 20 min ativo antes de voltar a ficar inativo -> encerra naquele despertar
                    return _finalize_sleep_session(conn, sleep_start_dt, brief_dt, awake_acc)
                return {"status": "sleeping", "sleep_start_ts": sleep_start_str, "report_generated": False}

            # Usuário está ativo enquanto current_status == 'sleeping'
            if not brief_since_str:
                # Filtro de falso sono (< 01:00 sem override) ou Merge Window (< 04:30)
                if (manual_override == 0 and _is_before_0100(cur_dt)) or _is_before_0430(cur_dt):
                    with conn:
                        conn.execute(
                            "UPDATE sleep_state SET brief_awake_since = ? WHERE id = 1",
                            (now_iso,),
                        )
                    return {
                        "status": "sleeping",
                        "sleep_start_ts": sleep_start_str,
                        "brief_awake_since": now_iso,
                        "report_generated": False,
                    }
                return _finalize_sleep_session(conn, sleep_start_dt, cur_dt, awake_acc)

            brief_dt = datetime.fromisoformat(str(brief_since_str))
            brief_mins = max(0, int((cur_dt - brief_dt).total_seconds() // 60))

            # 1. Filtro de pausa noturna (falso sono antes da 01:00)
            if manual_override == 0 and _is_before_0100(cur_dt):
                if brief_mins >= _FALSE_SLEEP_AWAKE_MINUTES:
                    with conn:
                        conn.execute(
                            "UPDATE sleep_state SET current_status = 'awake', last_active_ts = ?, "
                            "sleep_start_ts = NULL, awake_minutes_accumulated = 0, "
                            "brief_awake_since = NULL, manual_sleep_override = 0 WHERE id = 1",
                            (now_iso,),
                        )
                    return {"status": "awake", "discarded_false_sleep": True, "report_generated": False}
                return {
                    "status": "sleeping",
                    "sleep_start_ts": sleep_start_str,
                    "brief_awake_since": brief_since_str,
                    "report_generated": False,
                }

            # 2. Merge Window antes das 04:30
            if _is_before_0430(cur_dt):
                if brief_mins < _MERGE_WINDOW_MAX_AWAKE:
                    return {
                        "status": "sleeping",
                        "sleep_start_ts": sleep_start_str,
                        "brief_awake_since": brief_since_str,
                        "report_generated": False,
                    }
                return _finalize_sleep_session(conn, sleep_start_dt, cur_dt, awake_acc)

            # 3. >= 04:30: encerra a noite e gera o relatório matinal
            return _finalize_sleep_session(conn, sleep_start_dt, cur_dt, awake_acc)
        finally:
            conn.close()


def manage_sleep(action: str = "status") -> Dict[str, Any]:
    """
    Controle manual do monitoramento noturno de sono:
    - 'start_now': inicia monitoramento imediatamente ('vou dormir agora').
    - 'discard_last': remove o último relatório salvo em sleep_logs e recalcula resumo.
    - 'status': retorna o estado atual do monitoramento.
    """
    act = str(action or "status").strip().lower()
    now_dt = datetime.now()
    now_iso = now_dt.isoformat(timespec="seconds")

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            if act == "start_now":
                with conn:
                    conn.execute(
                        """
                        INSERT INTO sleep_state (
                            id, current_status, last_active_ts, sleep_start_ts,
                            monitoring_enabled, awake_minutes_accumulated,
                            brief_awake_since, manual_sleep_override
                        ) VALUES (1, 'sleeping', ?, ?, 1, 0, NULL, 1)
                        ON CONFLICT(id) DO UPDATE SET
                            current_status = 'sleeping',
                            last_active_ts = excluded.last_active_ts,
                            sleep_start_ts = excluded.sleep_start_ts,
                            monitoring_enabled = 1,
                            awake_minutes_accumulated = 0,
                            brief_awake_since = NULL,
                            manual_sleep_override = 1
                        """,
                        (now_iso, now_iso),
                    )
                return {
                    "status": "ok",
                    "message": (
                        f"Boa noite! Monitoramento de sono iniciado manualmente às {now_dt.strftime('%H:%M')}. "
                        "Quando você acordar, prepararei seu relatório completo."
                    ),
                    "data": {"action": "start_now", "current_status": "sleeping", "sleep_start_ts": now_iso},
                }

            if act == "discard_last":
                last_row = conn.execute(
                    "SELECT id, sleep_start_ts, wake_up_ts, duration_minutes FROM sleep_logs ORDER BY id DESC LIMIT 1"
                ).fetchone()
                if not last_row:
                    return {
                        "status": "ok",
                        "message": "Não há nenhum relatório de sono registrado para descartar.",
                        "data": {"action": "discard_last", "deleted": False},
                    }
                with conn:
                    conn.execute("DELETE FROM sleep_logs WHERE id = ?", (int(last_row["id"]),))
                    prev_latest = conn.execute(
                        "SELECT sleep_start_ts, duration_minutes, sleep_score, trend_status "
                        "FROM sleep_logs ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if prev_latest:
                        prev_dt = datetime.fromisoformat(str(prev_latest["sleep_start_ts"]))
                        _sync_sleep_memory(
                            conn,
                            f"Último sono ({prev_dt.strftime('%d/%m')}): "
                            f"{_format_duration_hm(int(prev_latest['duration_minutes']))}, "
                            f"nota {int(prev_latest['sleep_score'])}/100, tendência={prev_latest['trend_status']}.",
                        )
                    else:
                        conn.execute("DELETE FROM memories WHERE key = 'sleep_evolution_summary'")
                return {
                    "status": "ok",
                    "message": (
                        f"Último relatório de sono ({_format_duration_hm(int(last_row['duration_minutes']))}) "
                        "descartado e histórico longitudinal recalculado."
                    ),
                    "data": {"action": "discard_last", "deleted": True, "deleted_id": int(last_row["id"])},
                }

            row = conn.execute(
                "SELECT current_status, last_active_ts, sleep_start_ts, awake_minutes_accumulated, manual_sleep_override "
                "FROM sleep_state WHERE id = 1"
            ).fetchone()
            if not row:
                return {
                    "status": "ok",
                    "message": "Monitoramento de sono ativo (estado inicial: awake). Janela noturna: 19:15–11:59.",
                    "data": {"action": "status", "current_status": "awake"},
                }
            st = str(row["current_status"])
            msg = (
                f"Monitoramento de sono em andamento desde {row['sleep_start_ts']} "
                f"(despertares acumulados: {int(row['awake_minutes_accumulated'] or 0)} min)."
                if st == "sleeping"
                else f"Monitoramento de sono ativo (estado: awake, última atividade: {row['last_active_ts']})."
            )
            return {
                "status": "ok",
                "message": msg,
                "data": {
                    "action": "status",
                    "current_status": st,
                    "sleep_start_ts": row["sleep_start_ts"],
                    "last_active_ts": row["last_active_ts"],
                    "awake_minutes_accumulated": int(row["awake_minutes_accumulated"] or 0),
                    "manual_sleep_override": bool(row["manual_sleep_override"]),
                },
            }
        finally:
            conn.close()


def get_sleep_report(days: int = 7) -> Dict[str, Any]:
    """Retorna o último relatório científico de sono e a evolução longitudinal dos últimos N dias."""
    try:
        n_days = max(1, min(30, int(days)))
    except (TypeError, ValueError):
        n_days = 7

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            rows = conn.execute(
                "SELECT id, sleep_start_ts, wake_up_ts, duration_minutes, sleep_score, "
                "cycles_estimated, bedtime_deviation_minutes, trend_status, report_markdown, awake_minutes "
                "FROM sleep_logs ORDER BY id DESC LIMIT ?",
                (n_days,),
            ).fetchall()
        finally:
            conn.close()

    if not rows:
        return {
            "status": "ok",
            "message": (
                "Ainda não há noites registradas em sleep_logs. "
                "O monitoramento noturno automático acompanha a inatividade entre 19:15 e 11:59 "
                "(após 2h sem uso do aparelho) para gerar o relatório ao acordar."
            ),
            "data": {"days": n_days, "count": 0, "history": []},
        }

    latest = rows[0]
    trend_emoji = {
        "improving": "📈 Melhorando",
        "worsening": "📉 Piorando",
        "stable": "⚖️ Estável",
        "baseline": "🆕 Referência",
    }
    history = []
    timeline_lines = [f"### Linha do Tempo do Sono (últimas {len(rows)} noites)"]
    for r in rows:
        s_dt = datetime.fromisoformat(str(r["sleep_start_ts"]))
        w_dt = datetime.fromisoformat(str(r["wake_up_ts"]))
        dur_m = int(r["duration_minutes"])
        sc = int(r["sleep_score"])
        tr = str(r["trend_status"])
        history.append({
            "id": int(r["id"]),
            "sleep_start_ts": str(r["sleep_start_ts"]),
            "wake_up_ts": str(r["wake_up_ts"]),
            "duration_minutes": dur_m,
            "awake_minutes": int(r["awake_minutes"] or 0),
            "sleep_score": sc,
            "cycles_estimated": float(r["cycles_estimated"]),
            "bedtime_deviation_minutes": int(r["bedtime_deviation_minutes"] or 0),
            "trend_status": tr,
        })
        timeline_lines.append(
            f"- **{w_dt.strftime('%d/%m')}** ({s_dt.strftime('%H:%M')}–{w_dt.strftime('%H:%M')}): "
            f"{_format_duration_hm(dur_m)} • Nota **{sc}/100** • {trend_emoji.get(tr, tr)}"
        )

    full_msg = f"{latest['report_markdown']}\n\n" + "\n".join(timeline_lines)
    return {
        "status": "ok",
        "message": full_msg,
        "data": {
            "days": n_days,
            "count": len(history),
            "latest": history[0],
            "history": history,
        },
    }
