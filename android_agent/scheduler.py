"""
Agendador de notificações e lembretes em segundo plano para o Silva.
Monitora periodicamente android_agent/data/events.json e dispara
termux-notification + termux-vibrate na hora marcada.
"""

import threading
import time
from pathlib import Path

try:
    from tools import _load_events, _save_events, _run_termux_cmd, SIMULATE_HARDWARE
except ImportError:
    from android_agent.tools import _load_events, _save_events, _run_termux_cmd, SIMULATE_HARDWARE

_SCHEDULER_STARTED = False
_SCHEDULER_THREAD = None
_SCHEDULER_LOCK = threading.Lock()


def check_and_notify_events():
    """Verifica eventos pendentes e dispara notificação e vibração nativa na hora marcada."""
    events = _load_events()
    if not events:
        return

    now_ts = time.time()
    updated = False
    for ev in events:
        if not ev.get("notified", False) and now_ts >= ev.get("timestamp", 0):
            title = ev.get("title", "Compromisso")
            t_str = ev.get("time", "")
            if not SIMULATE_HARDWARE:
                try:
                    _run_termux_cmd([
                        "termux-notification",
                        "--title", "Lembrete do Silva",
                        "--content", f"{title} ({t_str})",
                        "--priority", "high",
                        "--sound"
                    ], timeout=5)
                    _run_termux_cmd(["termux-vibrate", "-d", "600"], timeout=5)
                except Exception:
                    pass
            ev["notified"] = True
            updated = True

    if updated:
        _save_events(events)


def _events_scheduler_loop(interval_sec: int = 30):
    while True:
        try:
            check_and_notify_events()
        except Exception:
            pass
        time.sleep(interval_sec)


def start_scheduler(interval_sec: int = 30):
    """
    Inicia a thread daemon leve de verificação de lembretes e compromissos apenas uma vez (idempotente).
    Protegida por flag global _SCHEDULER_STARTED e _SCHEDULER_LOCK.
    """
    global _SCHEDULER_STARTED, _SCHEDULER_THREAD
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED and _SCHEDULER_THREAD is not None and _SCHEDULER_THREAD.is_alive():
            return _SCHEDULER_THREAD
        t = threading.Thread(
            target=_events_scheduler_loop,
            args=(interval_sec,),
            daemon=True,
            name="SilvaEventsScheduler"
        )
        t.start()
        _SCHEDULER_STARTED = True
        _SCHEDULER_THREAD = t
        return t


start_events_scheduler = start_scheduler

