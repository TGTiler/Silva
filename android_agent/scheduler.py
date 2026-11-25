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
    from .tools.core import SIMULATE_HARDWARE, _FILE_LOCK, _run_termux_cmd
    from .tools.memory_schedule import _get_memory_db, compute_next_trigger
except ImportError:
    from tools.core import SIMULATE_HARDWARE, _FILE_LOCK, _run_termux_cmd
    from tools.memory_schedule import _get_memory_db, compute_next_trigger

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


def _events_scheduler_loop(interval_sec: int = 10) -> None:
    while True:
        try:
            check_and_notify_events()
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
