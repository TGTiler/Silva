"""
Testes unitários para o Monitoramento Autônomo de Sono Noturno (sleep_monitor.py),
análise longitudinal persistente, relatório científico e roteamento NLP.
"""

import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

from android_agent.intent_fallback import match_intent_fallback
from android_agent.tools import AVAILABLE_TOOLS, memory_schedule, sleep_monitor


class TestSleepMonitor(unittest.TestCase):
    """Valida máquina de estados noturna, arquitetura NREM/REM, evolução multi-noite e NLP."""

    def setUp(self):
        sleep_monitor.pop_pending_sleep_reports()

    def _make_db_factory(self, db_path: Path):
        def _connect():
            conn = sqlite3.connect(str(db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout = 5000;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    category TEXT DEFAULT 'geral',
                    updated_at TEXT NOT NULL
                )
                """
            )
            return conn
        return _connect

    def test_multi_night_baseline_improving_and_worsening(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            factory = self._make_db_factory(db_path)

            with patch.object(sleep_monitor, "_get_memory_db", side_effect=factory), \
                 patch.object(memory_schedule, "_get_memory_db", side_effect=factory):

                # --- NOITE 1 (baseline): dorme 01:30 às 07:00 (5h30 = 330 min) ---
                # Inicializa estado ativo à 01:30
                sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 20, 1, 30), is_user_active=True)
                # Após 2h05 de inatividade (03:35), entra em 'sleeping' retroativo para 01:30
                r_sleep1 = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 20, 3, 35), is_user_active=False)
                self.assertEqual(r_sleep1["status"], "sleeping")
                self.assertEqual(r_sleep1["sleep_start_ts"], "2026-11-20T01:30:00")

                # Acorda às 07:00
                r_wake1 = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 20, 7, 0), is_user_active=True)
                self.assertTrue(r_wake1["report_generated"])
                self.assertEqual(r_wake1["duration_minutes"], 330)
                self.assertEqual(r_wake1["trend_status"], "baseline")
                md1 = r_wake1["report_markdown"]
                for token in ("N1", "N2", "N3", "REM", "23:30", "23:15", "07:00"):
                    self.assertIn(token, md1)

                queued = sleep_monitor.pop_pending_sleep_reports()
                self.assertEqual(len(queued), 1)
                self.assertEqual(len(sleep_monitor.pop_pending_sleep_reports()), 0)

                # --- NOITE 2 (improving): dorme 23:15 às 07:00 (7h45 = 465 min) ---
                sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 20, 23, 15), is_user_active=True)
                r_sleep2 = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 21, 1, 20), is_user_active=False)
                self.assertEqual(r_sleep2["status"], "sleeping")

                r_wake2 = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 21, 7, 0), is_user_active=True)
                self.assertTrue(r_wake2["report_generated"])
                self.assertEqual(r_wake2["duration_minutes"], 465)
                self.assertEqual(r_wake2["trend_status"], "improving")

                # --- NOITE 3 (worsening): dorme 02:00 às 07:00 (5h00 = 300 min) ---
                sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 22, 2, 0), is_user_active=True)
                r_sleep3 = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 22, 4, 10), is_user_active=False)
                self.assertEqual(r_sleep3["status"], "sleeping")

                r_wake3 = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 22, 7, 0), is_user_active=True)
                self.assertTrue(r_wake3["report_generated"])
                self.assertEqual(r_wake3["duration_minutes"], 300)
                self.assertEqual(r_wake3["trend_status"], "worsening")

                # Verifica sincronização da memória persistente e ferramenta get_sleep_report
                conn = factory()
                mem_row = conn.execute(
                    "SELECT value, category FROM memories WHERE key = 'sleep_evolution_summary'"
                ).fetchone()
                conn.close()
                self.assertIsNotNone(mem_row)
                self.assertEqual(mem_row["category"], "saude")
                self.assertIn("worsening", mem_row["value"])

                rep = sleep_monitor.get_sleep_report(days=7)
                self.assertEqual(rep["status"], "ok")
                self.assertEqual(rep["data"]["count"], 3)
                self.assertIn("Linha do Tempo do Sono", rep["message"])

    def test_get_sleep_report_registered_and_nlp_routing(self):
        self.assertIn("get_sleep_report", AVAILABLE_TOOLS)
        for prompt in (
            "como foi meu sono?",
            "meu sono está melhorando ou piorando?",
            "relatório do meu sono",
            "evolução do meu sono na semana",
        ):
            with self.subTest(prompt=prompt):
                self.assertEqual(match_intent_fallback(prompt), "<call>get_sleep_report(days=7)</call>")


if __name__ == "__main__":
    unittest.main()
