"""
Motor de Monitoramento Autônomo de Sono Noturno, Arquitetura Estimada do Sono
e Análise Longitudinal Persistente em SQLite (memory.db).
"""

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .adb_bridge import ensure_adb_connected, is_screen_unlocked
from .core import _FILE_LOCK
from .memory_schedule import _get_memory_db

_WEB_ACTIVITY_LOCK = threading.Lock()
_LAST_WEB_ACTIVITY_TS: Optional[datetime] = None

_SLEEP_QUEUE_LOCK = threading.Lock()
_PENDING_SLEEP_REPORTS: List[Dict[str, Any]] = []

_INACTIVITY_SLEEP_SECONDS = 7200  # 2 horas
_MIN_SLEEP_LOG_MINUTES = 150      # 2h30min
_IDEAL_SLEEP_MINUTES = 450        # 7h30 (5 ciclos de 90 min)
_IDEAL_BEDTIME_HOUR = 23
_IDEAL_BEDTIME_MINUTE = 30


def record_web_activity(ts: Optional[datetime] = None) -> None:
    """Registra atividade recente do usuário na Web UI para compor a detecção de vigília."""
    global _LAST_WEB_ACTIVITY_TS
    with _WEB_ACTIVITY_LOCK:
        _LAST_WEB_ACTIVITY_TS = ts or datetime.now()


def pop_pending_sleep_reports() -> List[Dict[str, Any]]:
    """Retorna e limpa a fila de relatórios de sono pendentes para entrega no Web Chat."""
    with _SLEEP_QUEUE_LOCK:
        if not _PENDING_SLEEP_REPORTS:
            return []
        items = list(_PENDING_SLEEP_REPORTS)
        _PENDING_SLEEP_REPORTS.clear()
        return items


def _queue_sleep_report(payload: Dict[str, Any]) -> None:
    with _SLEEP_QUEUE_LOCK:
        _PENDING_SLEEP_REPORTS.append(payload)


def _ensure_sleep_tables(conn) -> None:
    """Garante a existência das tabelas sleep_state e sleep_logs no memory.db."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sleep_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_status TEXT NOT NULL DEFAULT 'awake',
            last_active_ts TEXT NOT NULL,
            sleep_start_ts TEXT DEFAULT NULL,
            monitoring_enabled INTEGER NOT NULL DEFAULT 1
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _is_night_window(dt: datetime) -> bool:
    """Janela de monitoramento noturno: 19:15 até 11:59 do dia seguinte."""
    return (dt.hour > 19 or (dt.hour == 19 and dt.minute >= 15)) or (dt.hour < 12)


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
    Positivo = dormiu depois das 23:30; negativo = dormiu antes das 23:30.
    """
    if sleep_start_dt.hour >= 18:
        ideal_dt = sleep_start_dt.replace(
            hour=_IDEAL_BEDTIME_HOUR,
            minute=_IDEAL_BEDTIME_MINUTE,
            second=0,
            microsecond=0,
        )
    else:
        prev_day = sleep_start_dt - timedelta(days=1)
        ideal_dt = prev_day.replace(
            hour=_IDEAL_BEDTIME_HOUR,
            minute=_IDEAL_BEDTIME_MINUTE,
            second=0,
            microsecond=0,
        )
    return int((sleep_start_dt - ideal_dt).total_seconds() // 60)


def _compute_sleep_score(duration_minutes: int, bedtime_deviation_minutes: int) -> int:
    """Pontuação de 0 a 100 combinando duração (70 pts) e regularidade circadiana (30 pts)."""
    if 450 <= duration_minutes <= 510:
        dur_score = 70.0
    elif duration_minutes < 450:
        dur_score = max(10.0, 70.0 * (duration_minutes / 450.0))
    else:
        excess = duration_minutes - 510
        dur_score = max(35.0, 70.0 - (excess * 0.25))

    abs_dev = abs(bedtime_deviation_minutes)
    if abs_dev <= 20:
        reg_score = 30.0
    else:
        reg_score = max(0.0, 30.0 - ((abs_dev - 20) * 0.2))

    return int(max(0, min(100, round(dur_score + reg_score))))


def _analyze_sleep_trend(
    conn,
    current_duration_min: int,
    current_score: int,
    sleep_start_dt: datetime,
) -> Dict[str, Any]:
    """
    Compara a noite atual com as últimas 7 noites em sleep_logs e classifica:
    'baseline' | 'improving' | 'worsening' | 'stable'.
    Sincroniza também o resumo em memories (key='sleep_evolution_summary').
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT duration_minutes, sleep_score, bedtime_deviation_minutes, sleep_start_ts "
        "FROM sleep_logs ORDER BY id DESC LIMIT 7"
    )
    prev_rows = cur.fetchall()

    if len(prev_rows) == 0:
        trend_status = "baseline"
        avg_dur = current_duration_min
        avg_score = current_score
        delta_min = 0
        delta_score = 0
        verdict = "Noite de referência registrada para acompanhar sua evolução"
    else:
        avg_dur = int(round(sum(int(r["duration_minutes"]) for r in prev_rows) / len(prev_rows)))
        avg_score = int(round(sum(int(r["sleep_score"]) for r in prev_rows) / len(prev_rows)))
        delta_min = current_duration_min - avg_dur
        delta_score = current_score - avg_score
        short_streak = sum(1 for r in prev_rows[:2] if int(r["duration_minutes"]) < 390)

        if (delta_score >= 5 or delta_min >= 25) and current_duration_min <= 570 and current_duration_min >= 390:
            trend_status = "improving"
            sign = "+" if delta_min >= 0 else ""
            verdict = (
                f"📈 Seu sono está melhorando: você dormiu {sign}{delta_min} min "
                f"em relação à sua média recente de {_format_duration_hm(avg_dur)}"
            )
        elif delta_min <= -30 or delta_score <= -5 or (current_duration_min < 390 and short_streak >= 1):
            trend_status = "worsening"
            if current_duration_min < 360 and short_streak >= 2:
                verdict = "📉 Alerta de piora: terceira noite seguida abaixo de 6h, acumulando débito de sono"
            else:
                verdict = (
                    f"📉 Alerta de piora: variação de {delta_min} min e {delta_score:+d} pts "
                    f"frente à média recente de {_format_duration_hm(avg_dur)}"
                )
        else:
            trend_status = "stable"
            verdict = (
                f"⚖️ Sono estável: mantendo consistência próxima à média recente de "
                f"{_format_duration_hm(avg_dur)} ({delta_score:+d} pts)"
            )

    summary_mem = (
        f"Último sono ({sleep_start_dt.strftime('%d/%m')}): {_format_duration_hm(current_duration_min)}, "
        f"nota {current_score}/100, tendência={trend_status}. {verdict}."
    )
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
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

    return {
        "trend_status": trend_status,
        "avg_prev_duration": avg_dur,
        "avg_prev_score": avg_score,
        "delta_minutes": delta_min,
        "delta_score": delta_score,
        "verdict": verdict,
    }


def build_scientific_sleep_report(
    sleep_start_dt: datetime,
    wake_up_dt: datetime,
    duration_minutes: int,
    sleep_score: int,
    cycles_estimated: float,
    trend_info: Dict[str, Any],
) -> str:
    """Gera o relatório científico completo em Markdown com 4 blocos obrigatórios."""
    nrem_total = int(round(duration_minutes * 0.775))
    rem_total = max(0, duration_minutes - nrem_total)
    n1_min = int(round(duration_minutes * 0.05))
    n2_min = int(round(duration_minutes * 0.475))
    n3_min = max(0, nrem_total - n1_min - n2_min)

    ideal_sleep_dt = wake_up_dt - timedelta(minutes=_IDEAL_SLEEP_MINUTES)
    ideal_disconnect_dt = ideal_sleep_dt - timedelta(minutes=15)

    sacrifice_notes: List[str] = []
    if sleep_start_dt.hour in (0, 1, 2, 3, 4, 5) or (sleep_start_dt.hour == 23 and sleep_start_dt.minute > 45):
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
            f"Inicie a desaceleração sem telas às **{ideal_disconnect_dt.strftime('%H:%M')}** "
            f"para adormecer próximo de **{ideal_sleep_dt.strftime('%H:%M')}**."
        )
    plan_line_2 = (
        "Evite cafeína após as **14:00** e busque **10–15 min de luz solar matinal** ao acordar "
        "para ancorar seu ritmo circadiano."
    )

    return "\n".join([
        "### 1. Resumo & Evolução ao Passar das Noites",
        f"- **Duração dormida:** {_format_duration_hm(duration_minutes)} "
        f"({sleep_start_dt.strftime('%H:%M')} → {wake_up_dt.strftime('%H:%M')})",
        f"- **Nota do Sono:** {sleep_score}/100 | **Ciclos estimados (90 min):** {cycles_estimated:.1f}",
        f"- **Evolução:** {trend_info.get('verdict', 'Noite de referência registrada')}",
        "",
        "### 2. Suposição Científica da Arquitetura do Sono (Polissonografia Estimada)",
        f"- **Sono não REM (NREM) — ~75% a 80% do sono total (~{_format_duration_hm(nrem_total)}):**",
        f"  - **N1 (sono leve inicial — ~5%, ~{_format_duration_hm(n1_min)}):** transição entre estar acordado e dormindo, com relaxamento muscular rápido.",
        f"  - **N2 (sono leve intermediário — ~45% a 50%, ~{_format_duration_hm(n2_min)}):** queda da temperatura corporal e dos batimentos cardíacos; ocupa a maior parte da noite.",
        f"  - **N3 (sono profundo ou de ondas lentas — ~20% a 25%, ~{_format_duration_hm(n3_min)}):** foco na restauração física, liberação de hormônios e fortalecimento da imunidade.",
        f"- **Sono REM — ~20% a 25% do sono total (~{_format_duration_hm(rem_total)}):**",
        "  - **Movimentos rápidos dos olhos (Rapid Eye Movement):** alta atividade cerebral, semelhante à vigília, com relaxamento muscular profundo.",
        "  - **Memória e emoções:** fase mais associada a sonhos vívidos, consolidação de memórias e processamento emocional.",
        "",
        "### 3. Como Deveria Ter Sido o Sono Ideal (Comparativo Prescritivo)",
        f"- **Meta fisiológica (5 ciclos = 7h30 a 8h00):** para acordar às **{wake_up_dt.strftime('%H:%M')}** "
        f"sem cortar o último ciclo REM, você deveria ter desconectado às **{ideal_disconnect_dt.strftime('%H:%M')}** "
        f"e adormecido até **{ideal_sleep_dt.strftime('%H:%M')}**.",
        f"- **Impacto observado:** {' '.join(sacrifice_notes)}",
        "",
        "### 4. Plano Prático para Hoje à Noite",
        f"- **Rotina de desligamento:** {plan_line_1}",
        f"- **Higiene circadiana:** {plan_line_2}",
    ])


def evaluate_sleep_cycle(
    now: Optional[datetime] = None,
    is_user_active: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Máquina de estados autônoma do monitoramento noturno de sono:
    - awake -> sleeping após >= 2h de inatividade na janela noturna (19:15–11:59)
    - sleeping -> awake ao detectar retorno do usuário; se >= 150 min, persiste e gera relatório.
    """
    cur_dt = now or datetime.now()
    active = _detect_device_activity(cur_dt) if is_user_active is None else bool(is_user_active)
    now_iso = cur_dt.isoformat(timespec="seconds")

    with _FILE_LOCK:
        conn = _get_memory_db()
        try:
            _ensure_sleep_tables(conn)
            cur = conn.cursor()
            cur.execute("SELECT current_status, last_active_ts, sleep_start_ts, monitoring_enabled FROM sleep_state WHERE id = 1")
            row = cur.fetchone()
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

            if current_status == "awake":
                if active:
                    with conn:
                        conn.execute("UPDATE sleep_state SET last_active_ts = ? WHERE id = 1", (now_iso,))
                    return {"status": "awake", "report_generated": False}

                idle_sec = (cur_dt - last_active_dt).total_seconds()
                if _is_night_window(cur_dt) and idle_sec >= _INACTIVITY_SLEEP_SECONDS:
                    retro_start = last_active_dt.isoformat(timespec="seconds")
                    with conn:
                        conn.execute(
                            "UPDATE sleep_state SET current_status = 'sleeping', sleep_start_ts = ? WHERE id = 1",
                            (retro_start,),
                        )
                    return {"status": "sleeping", "sleep_start_ts": retro_start, "report_generated": False}
                return {"status": "awake", "report_generated": False}

            # current_status == 'sleeping'
            if not active:
                return {"status": "sleeping", "sleep_start_ts": sleep_start_str, "report_generated": False}

            sleep_start_dt = datetime.fromisoformat(str(sleep_start_str or row["last_active_ts"]))
            duration_minutes = max(0, int((cur_dt - sleep_start_dt).total_seconds() // 60))

            with conn:
                conn.execute(
                    "UPDATE sleep_state SET current_status = 'awake', last_active_ts = ?, sleep_start_ts = NULL WHERE id = 1",
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
                sleep_score = _compute_sleep_score(duration_minutes, bedtime_dev)
                trend_info = _analyze_sleep_trend(conn, duration_minutes, sleep_score, sleep_start_dt)
                report_md = build_scientific_sleep_report(
                    sleep_start_dt=sleep_start_dt,
                    wake_up_dt=cur_dt,
                    duration_minutes=duration_minutes,
                    sleep_score=sleep_score,
                    cycles_estimated=cycles_estimated,
                    trend_info=trend_info,
                )
                conn.execute(
                    """
                    INSERT INTO sleep_logs (
                        sleep_start_ts, wake_up_ts, duration_minutes, sleep_score,
                        cycles_estimated, bedtime_deviation_minutes, trend_status, report_markdown
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )

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
            report_payload = {
                "title": "☀️ Bom dia! Relatório & Evolução do Sono",
                "summary": notif_summary,
                "duration_minutes": duration_minutes,
                "sleep_score": sleep_score,
                "trend_status": trend_info["trend_status"],
                "report_markdown": report_md,
                "wake_up_ts": now_iso,
            }
            _queue_sleep_report(report_payload)
            return {
                "status": "awake",
                "report_generated": True,
                **report_payload,
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
            cur = conn.cursor()
            cur.execute(
                "SELECT id, sleep_start_ts, wake_up_ts, duration_minutes, sleep_score, "
                "cycles_estimated, bedtime_deviation_minutes, trend_status, report_markdown "
                "FROM sleep_logs ORDER BY id DESC LIMIT ?",
                (n_days,),
            )
            rows = cur.fetchall()
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
