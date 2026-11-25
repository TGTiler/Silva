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
        pass

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

                queued = sleep_monitor.get_undelivered_sleep_reports()
                self.assertEqual(len(queued), 1)
                sleep_monitor.ack_sleep_reports([queued[0]["id"]])
                self.assertEqual(len(sleep_monitor.get_undelivered_sleep_reports()), 0)

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

        self.assertEqual(match_intent_fallback("silva, vou dormir agora"), "<call>manage_sleep(action='start_now')</call>")
        self.assertEqual(match_intent_fallback("vou deitar agora"), "<call>manage_sleep(action='start_now')</call>")
        self.assertEqual(match_intent_fallback("boa noite, vou dormir"), "<call>manage_sleep(action='start_now')</call>")
        self.assertEqual(match_intent_fallback("desconsidera o sono de hoje"), "<call>manage_sleep(action='discard_last')</call>")
        self.assertEqual(match_intent_fallback("apaga o último relatório de sono"), "<call>manage_sleep(action='discard_last')</call>")

    def test_merge_window_brief_awake_at_0310_for_5min(self):
        """Despertar breve às 03:10 por 5 min voltando a dormir até 07:30 funde blocos e desconta 5 min."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            factory = self._make_db_factory(db_path)

            with patch.object(sleep_monitor, "_get_memory_db", side_effect=factory), \
                 patch.object(memory_schedule, "_get_memory_db", side_effect=factory), \
                 patch.object(sleep_monitor, "_is_media_playing", return_value=False):
                # Dorme 23:30 (2026-11-23), detecta sono às 01:35
                sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 23, 23, 30), is_user_active=True)
                sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 1, 35), is_user_active=False)

                # Desbloqueia às 03:10 e volta a ficar inativo às 03:15 (5 min)
                r_brief = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 3, 10), is_user_active=True)
                self.assertEqual(r_brief["status"], "sleeping")
                self.assertFalse(r_brief["report_generated"])

                r_merge = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 3, 15), is_user_active=False)
                self.assertEqual(r_merge["status"], "sleeping")
                self.assertTrue(r_merge.get("merged_brief_awake"))
                self.assertEqual(r_merge["awake_minutes_accumulated"], 5)

                # Acorda definitivamente às 07:30 -> bruto 480 min - 5 min = 475 min
                r_wake = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 7, 30), is_user_active=True)
                self.assertTrue(r_wake["report_generated"])
                self.assertEqual(r_wake["awake_minutes"], 5)
                self.assertEqual(r_wake["duration_minutes"], 475)
                self.assertEqual(sleep_monitor.get_sleep_report()["data"]["count"], 1)

    def test_false_sleep_before_0100_discarded_and_media_blocks_sleep(self):
        """Falso sono interrompido antes da 01:00 por >= 15 min é descartado; mídia ativa bloqueia sleeping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            factory = self._make_db_factory(db_path)

            with patch.object(sleep_monitor, "_get_memory_db", side_effect=factory), \
                 patch.object(memory_schedule, "_get_memory_db", side_effect=factory):
                # 1. Mídia ativa às 22:05 (após 2h sem toque) bloqueia transição para sleeping
                with patch.object(sleep_monitor, "_is_media_playing", return_value=True):
                    sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 20, 0), is_user_active=True)
                    r_media = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 22, 5), is_user_active=False)
                    self.assertEqual(r_media["status"], "awake")
                    self.assertTrue(r_media.get("media_blocked"))

                # 2. Falso sono iniciado às 20:00 -> entra em sleeping às 22:05, usuário usa 22:30 -> 22:46 (>= 15 min)
                with patch.object(sleep_monitor, "_is_media_playing", return_value=False):
                    sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 20, 0), is_user_active=True)
                    r_sl = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 22, 5), is_user_active=False)
                    self.assertEqual(r_sl["status"], "sleeping")
                    sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 22, 30), is_user_active=True)
                    r_disc = sleep_monitor.evaluate_sleep_cycle(now=datetime(2026, 11, 24, 22, 46), is_user_active=True)
                    self.assertEqual(r_disc["status"], "awake")
                    self.assertTrue(r_disc.get("discarded_false_sleep"))
                    self.assertFalse(r_disc["report_generated"])
                    self.assertEqual(sleep_monitor.get_sleep_report()["data"]["count"], 0)

    def test_median_anti_outlier_and_manage_sleep_commands(self):
        """Mediana móvel ignora 1 outlier extremo; manage_sleep('start_now' / 'discard_last') funcionam."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "memory.db"
            factory = self._make_db_factory(db_path)

            with patch.object(sleep_monitor, "_get_memory_db", side_effect=factory), \
                 patch.object(memory_schedule, "_get_memory_db", side_effect=factory), \
                 patch.object(sleep_monitor, "_is_media_playing", return_value=False):
                self.assertIn("manage_sleep", AVAILABLE_TOOLS)
                conn = factory()
                sleep_monitor._ensure_sleep_tables(conn)
                # 3 noites anteriores: 460 min, 470 min e 1 outlier extremo de 180 min -> mediana = 460 (não média 370!)
                with conn:
                    for idx, dur in enumerate((460, 470, 180)):
                        conn.execute(
                            "INSERT INTO sleep_logs (sleep_start_ts, wake_up_ts, duration_minutes, sleep_score, cycles_estimated, trend_status, report_markdown) "
                            "VALUES (?, ?, ?, ?, ?, 'stable', 'ok')",
                            (f"2026-11-1{idx}T23:30:00", f"2026-11-1{idx+1}T07:00:00", dur, 85 if dur > 400 else 35, 5.0),
                        )
                    trend = sleep_monitor._analyze_sleep_trend(conn, 465, 88, datetime(2026, 11, 20, 23, 30))
                conn.close()
                # Se usasse média (370), 465 - 370 = +95 (improving falso); com mediana (460), delta = +5 -> stable!
                self.assertEqual(trend["median_prev_duration"], 460)
                self.assertEqual(trend["trend_status"], "stable")

                # manage_sleep('start_now') e manage_sleep('discard_last')
                r_start = sleep_monitor.manage_sleep("start_now")
                self.assertEqual(r_start["status"], "ok")
                self.assertEqual(r_start["data"]["current_status"], "sleeping")
                self.assertEqual(sleep_monitor.manage_sleep("status")["data"]["current_status"], "sleeping")

                r_del = sleep_monitor.manage_sleep("discard_last")
                self.assertTrue(r_del["data"]["deleted"])
                self.assertEqual(sleep_monitor.get_sleep_report()["data"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
