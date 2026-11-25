"""
Agendador proativo em segundo plano para o Silva.
Monitora a tabela scheduled_events no SQLite (memory.db) a cada 10s,
dispara pré-alertas (10 min antes), vibração, notificação de alta prioridade,
voz falada (termux-tts-speak), gerencia recorrências e alimenta a UI Web.
"""

import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List

try:
    from .tools.core import SIMULATE_HARDWARE, _FILE_LOCK, _run_termux_cmd, cleanup_orphaned_captures
    from .tools.hardware import get_wifi_info
    from .tools.memory_schedule import _get_memory_db, compute_next_trigger
    from .tools.sleep_monitor import evaluate_sleep_cycle
except ImportError:
    from tools.core import SIMULATE_HARDWARE, _FILE_LOCK, _run_termux_cmd, cleanup_orphaned_captures
    from tools.hardware import get_wifi_info
    from tools.memory_schedule import _get_memory_db, compute_next_trigger
    from tools.sleep_monitor import evaluate_sleep_cycle

_SCHEDULER_STARTED = False
_SCHEDULER_THREAD = None
_SCHEDULER_LOCK = threading.Lock()

_ALERTS_LOCK = threading.Lock()
_TRIGGERED_ALERTS: List[Dict[str, Any]] = []


def _is_proactive_tts_enabled() -> bool:
    return os.getenv("ENABLE_PROACTIVE_TTS", "true").strip().lower() in ("1", "true", "yes")


def _speak_proactive(phrase: str) -> None:
    """Executa síntese de voz nativa PT-BR via termux-tts-speak."""
    if SIMULATE_HARDWARE:
        return
    try:
        res = _run_termux_cmd(
            ["termux-tts-speak", "-l", "pt-BR", "-r", "1.05", phrase],
            timeout=12,
        )
        if res.returncode != 0:
            _run_termux_cmd(
                [
                    "am", "broadcast",
                    "-a", "com.termux.tts.SPEAK",
                    "--es", "text", phrase,
                ],
                timeout=5,
            )
    except Exception:
        pass


def pop_triggered_alerts() -> List[Dict[str, Any]]:
    """Retorna e limpa a fila de alertas recém-disparados para entrega na UI Web."""
    with _ALERTS_LOCK:
        if not _TRIGGERED_ALERTS:
            return []
        alerts = list(_TRIGGERED_ALERTS)
        _TRIGGERED_ALERTS.clear()
        return alerts


def check_and_notify_events() -> None:
    """Verifica scheduled_events no memory.db e executa pré-alertas, disparos e recorrências."""
    now = datetime.now()
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            cur = conn.cursor()
            cur.execute(
                "SELECT id, title, event_type, trigger_at, recurrence, status, spoken_alert "
                "FROM scheduled_events WHERE status IN ('pending', 'pre_alerted') "
                "ORDER BY trigger_at ASC"
            )
            rows = cur.fetchall()
        except Exception:
            return

        updates = []
        dispatches = []

        for row in rows:
            ev_id = row["id"]
            title = str(row["title"] or "Compromisso")
            ev_type = str(row["event_type"] or "event")
            trig_str = str(row["trigger_at"] or "")
            recurrence = str(row["recurrence"] or "none")
            status = str(row["status"] or "pending")
            spoken_flag = int(row["spoken_alert"] if row["spoken_alert"] is not None else 1)

            try:
                trig_dt = datetime.strptime(trig_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            diff_sec = (trig_dt - now).total_seconds()

            # 1. Alerta antecipado (10 minutos antes para compromissos)
            if ev_type == "event" and status == "pending" and 0 < diff_sec <= 600:
                if not SIMULATE_HARDWARE:
                    try:
                        _run_termux_cmd([
                            "termux-notification",
                            "--id", f"silva_pre_{ev_id}",
                            "--title", "Silva — Em breve",
                            "--content", f"{title} às {trig_dt.strftime('%H:%M')}",
                            "--priority", "default",
                        ], timeout=5)
                    except Exception:
                        pass
                updates.append(("pre_alerted", trig_str, ev_id))
                continue

            # 2. Disparo principal no horário
            if diff_sec <= 0:
                hh_mm = trig_dt.strftime("%H:%M")
                if ev_type == "alarm":
                    phrase = f"Alarme das {hh_mm}: {title}"
                else:
                    phrase = f"Atenção, compromisso agora: {title}"

                dispatches.append({
                    "id": ev_id,
                    "title": title,
                    "event_type": ev_type,
                    "trigger_at": trig_str,
                    "message": phrase,
                    "spoken": bool(spoken_flag),
                })

                next_trig = compute_next_trigger(trig_str, recurrence)
                if next_trig:
                    updates.append(("pending", next_trig, ev_id))
                else:
                    updates.append(("triggered", trig_str, ev_id))

        if updates:
            try:
                with conn:
                    for new_status, new_trig, ev_id in updates:
                        conn.execute(
                            "UPDATE scheduled_events SET status = ?, trigger_at = ? WHERE id = ?",
                            (new_status, new_trig, ev_id),
                        )
            except Exception:
                pass
        conn.close()

    # Executa notificações, vibração e TTS fora do lock de arquivo
    tts_enabled = _is_proactive_tts_enabled()
    for item in dispatches:
        if not SIMULATE_HARDWARE:
            try:
                _run_termux_cmd(["termux-vibrate", "-d", "600"], timeout=5)
                _run_termux_cmd([
                    "termux-notification",
                    "--id", f"silva_alert_{item['id']}",
                    "--title", "Silva — Lembrete",
                    "--content", item["title"],
                    "--priority", "max",
                    "--sound",
                ], timeout=5)
            except Exception:
                pass
            if tts_enabled and item["spoken"]:
                _speak_proactive(item["message"])

        with _ALERTS_LOCK:
            _TRIGGERED_ALERTS.append({
                "id": item["id"],
                "title": item["title"],
                "event_type": item["event_type"],
                "trigger_at": item["trigger_at"],
                "message": item["message"],
            })


def check_and_notify_context_reminders() -> None:
    """
    Verifica lembretes contextuais por Wi-Fi em context_reminders.
    Só consulta get_wifi_info() quando há lembretes ativos pendentes (baixo consumo).
    """
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM context_reminders WHERE is_active = 1 LIMIT 1")
            if not cur.fetchone():
                conn.close()
                return
            cur.execute(
                "SELECT id, trigger_value, reminder_text "
                "FROM context_reminders WHERE is_active = 1 AND trigger_type = 'wifi'"
            )
            active_rows = cur.fetchall()
            conn.close()
        except Exception:
            return

    if not active_rows:
        return

    try:
        wifi_res = get_wifi_info()
        current_ssid = str((wifi_res.get("data") or {}).get("ssid") or "").strip()
    except Exception:
        current_ssid = ""

    if not current_ssid or current_ssid.lower() in ("<unknown ssid>", "desconhecido", "none"):
        return

    current_ssid_lower = current_ssid.lower()
    matching_ids = [
        int(r["id"])
        for r in active_rows
        if str(r["trigger_value"] or "").strip().lower() == current_ssid_lower
    ]
    if not matching_ids:
        return

    dispatches: List[Dict[str, Any]] = []
    with _FILE_LOCK:
        try:
            conn = _get_memory_db()
            cur = conn.cursor()
            with conn:
                for rem_id in matching_ids:
                    cur.execute(
                        "SELECT id, trigger_value, reminder_text FROM context_reminders "
                        "WHERE id = ? AND is_active = 1",
                        (rem_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        continue
                    cur.execute(
                        "UPDATE context_reminders "
                        "SET is_active = 0, triggered_at = datetime('now', 'localtime') "
                        "WHERE id = ? AND is_active = 1",
                        (rem_id,),
                    )
                    if cur.rowcount > 0:
                        rem_text = str(row["reminder_text"] or "").strip()
                        ssid_val = str(row["trigger_value"] or current_ssid).strip()
                        dispatches.append({
                            "id": f"ctx_{rem_id}",
                            "title": rem_text,
                            "event_type": "context_wifi",
                            "trigger_at": f"Wi-Fi {ssid_val}",
                            "message": f"Você conectou no Wi-Fi '{ssid_val}'. Lembrete: {rem_text}",
                        })
            conn.close()
        except Exception:
            return

    tts_enabled = _is_proactive_tts_enabled()
    for item in dispatches:
        if not SIMULATE_HARDWARE:
            try:
                _run_termux_cmd(["termux-vibrate", "-d", "450"], timeout=5)
                _run_termux_cmd([
                    "termux-notification",
                    "--id", f"silva_{item['id']}",
                    "--title", "Silva — Lembrete de Wi-Fi",
                    "--content", item["message"],
                    "--priority", "max",
                    "--sound",
                ], timeout=5)
            except Exception:
                pass
            if tts_enabled:
                _speak_proactive(item["message"])

        with _ALERTS_LOCK:
            _TRIGGERED_ALERTS.append({
                "id": item["id"],
                "title": item["title"],
                "event_type": item["event_type"],
                "trigger_at": item["trigger_at"],
                "message": item["message"],
            })


def check_and_notify_sleep_cycle() -> None:
    """Executa evaluate_sleep_cycle() e dispara termux-notification quando um relatório matinal é gerado."""
    try:
        res = evaluate_sleep_cycle()
    except Exception:
        return
    if not res.get("report_generated"):
        return
    if not SIMULATE_HARDWARE:
        try:
            _run_termux_cmd(
                [
                    "termux-notification",
                    "--id", "9910",
                    "--title", res.get("title") or "☀️ Bom dia! Relatório & Evolução do Sono",
                    "--content", res.get("summary") or "Relatório de sono disponível.",
                    "--priority", "max",
                    "--sound",
                ],
                timeout=5,
            )
        except Exception:
            pass


def _events_scheduler_loop(interval_sec: int = 10) -> None:
    last_gc = 0.0
    gc_interval_sec = 6 * 3600
    while True:
        try:
            check_and_notify_events()
            check_and_notify_context_reminders()
            check_and_notify_sleep_cycle()
            now_mono = time.monotonic()
            if (now_mono - last_gc) >= gc_interval_sec:
                cleanup_orphaned_captures()
                last_gc = now_mono
        except Exception:
            pass
        time.sleep(interval_sec)


def start_scheduler(interval_sec: int = 10):
    """
    Inicia a thread daemon de verificação de lembretes/alarmes apenas uma vez (idempotente).
    """
    global _SCHEDULER_STARTED, _SCHEDULER_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED and _SCHEDULER_THREAD is not None and _SCHEDULER_THREAD.is_alive():
            return _SCHEDULER_THREAD
        t = threading.Thread(
            target=_events_scheduler_loop,
            args=(interval_sec,),
            daemon=True,
            name="SilvaEventsScheduler",
        )
        t.start()
        _SCHEDULER_STARTED = True
        _SCHEDULER_THREAD = t
        return t


start_events_scheduler = start_scheduler
