"""
Agendador de notificações e lembretes em segundo plano para o Silva.
Monitora periodicamente android_agent/data/events.json e dispara
termux-notification + termux-vibrate na hora marcada.
"""

import threading
import time
from pathlib import Path

from tools import _load_events, _save_events, _run_termux_cmd, SIMULATE_HARDWARE


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


def start_events_scheduler(interval_sec: int = 30):
    """Inicia a thread daemon leve de verificação de lembretes."""
    t = threading.Thread(
        target=_events_scheduler_loop,
        args=(interval_sec,),
        daemon=True,
        name="SilvaEventsScheduler"
    )
    t.start()
    return t
