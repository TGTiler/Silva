"""
Testes automatizados para Resolvedor Unificado de Contatos (contacts.py),
Agenda Unificada (scheduled_events no memory.db) e Scheduler Proativo com TTS.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

from android_agent.tools import contacts, comms, memory_schedule
from android_agent.intent_fallback import match_intent_fallback
from android_agent import scheduler


class TestContactsAndScheduler(unittest.TestCase):
    """Testa resolução de contatos, migração de agenda e disparo proativo com TTS."""

    def setUp(self):
        contacts._CONTACTS_CACHE["timestamp"] = 0.0
        contacts._CONTACTS_CACHE["contacts"] = []
        scheduler.pop_triggered_alerts()

    def test_contact_resolution_memory_alias_exact_fuzzy_and_disambiguation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data):
                memory_schedule.remember_note("número da minha mãe", "81988887777")

                # 1. Apelido salvo na memória ("mãe" / "minha mãe")
                num, name, src = contacts.resolve_contact("minha mãe")
                self.assertEqual(num, "81988887777")
                self.assertEqual(src, "memory")

        # 2. Agenda Android mockada: match exato, fuzzy e desambiguação
        mock_agenda = [
            {"name": "João Silva", "number": "81991112222"},
            {"name": "João Souza", "number": "81993334444"},
            {"name": "Carlos Pereira", "number": "11977776666"},
        ]
        mock_proc = subprocess.CompletedProcess(
            args=["termux-contact-list"],
            returncode=0,
            stdout=json.dumps(mock_agenda),
            stderr="",
        )
        with patch("android_agent.tools.contacts._run_termux_cmd", return_value=mock_proc):
            # Exato
            n1, nm1, s1 = contacts.resolve_contact("Carlos Pereira")
            self.assertEqual(n1, "11977776666")
            self.assertEqual(nm1, "Carlos Pereira")
            self.assertEqual(s1, "android_contacts")

            # Fuzzy (typo em Carlos Pereir)
            n2, nm2, s2 = contacts.resolve_contact("Carlos Pereir")
            self.assertEqual(n2, "11977776666")
            self.assertEqual(s2, "android_contacts")

            # Desambiguação para "João"
            info = contacts.resolve_contact_detailed("João")
            self.assertTrue(info["ambiguous"])
            self.assertEqual(info["source"], "ambiguous")
            self.assertEqual(len(info["candidates"]), 2)

    def test_send_sms_and_make_call_with_contact_name(self):
        mock_agenda = [{"name": "Maria Clara", "number": "81995551234"}]
        mock_proc = subprocess.CompletedProcess(
            args=["termux-contact-list"],
            returncode=0,
            stdout=json.dumps(mock_agenda),
            stderr="",
        )
        with patch("android_agent.tools.contacts._run_termux_cmd", return_value=mock_proc):
            sms_res = comms.send_sms("Maria Clara", "Cheguei bem!")
            self.assertEqual(sms_res["status"], "ok")
            self.assertIn("Maria Clara", sms_res["message"])
            self.assertEqual(sms_res["data"]["number"], "81995551234")

            call_res = comms.make_call(target="Maria Clara")
            self.assertEqual(call_res["status"], "ok")
            self.assertIn("Maria Clara", call_res["message"])
            self.assertEqual(call_res["data"]["number"], "81995551234")

        # Roteamento NLP natural com acento ("minha mãe")
        nlp_call = match_intent_fallback("Manda um SMS pra minha mãe dizendo que cheguei")
        self.assertIsNotNone(nlp_call)
        self.assertIn("send_sms(", nlp_call)
        self.assertIn("minha mãe", nlp_call)

    def test_events_json_migration_to_scheduled_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            legacy_events = tmp_data / "events.json"
            future_dt = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)
            legacy_events.write_text(
                json.dumps([
                    {
                        "id": "abc123",
                        "title": "Consulta Médica",
                        "date": future_dt.strftime("%Y-%m-%d"),
                        "time": future_dt.strftime("%H:%M"),
                        "timestamp": int(future_dt.timestamp()),
                        "notified": False,
                    }
                ]),
                encoding="utf-8",
            )

            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data):
                conn = memory_schedule._get_memory_db()
                cur = conn.cursor()
                cur.execute("SELECT title, event_type, status FROM scheduled_events")
                rows = cur.fetchall()
                conn.close()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Consulta Médica")
            self.assertEqual(rows[0]["status"], "pending")
            self.assertFalse(legacy_events.exists())
            self.assertTrue((tmp_data / "events.json.migrated").is_file())

    def test_proactive_scheduler_tts_notification_and_daily_recurrence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            past_dt = (datetime.now() - timedelta(minutes=1)).replace(microsecond=0)
            past_str = past_dt.strftime("%Y-%m-%d %H:%M:%S")

            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data):
                conn = memory_schedule._get_memory_db()
                with conn:
                    conn.execute(
                        "INSERT INTO scheduled_events (title, event_type, trigger_at, recurrence, status, spoken_alert) "
                        "VALUES (?, 'event', ?, 'daily', 'pending', 1)",
                        ("Tomar remédio", past_str),
                    )
                conn.close()

                termux_cmds = []

                def fake_termux(cmd, timeout=5):
                    termux_cmds.append(cmd)
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

                with patch.dict(os.environ, {"ENABLE_PROACTIVE_TTS": "true"}), \
                     patch("android_agent.scheduler.SIMULATE_HARDWARE", False), \
                     patch("android_agent.scheduler._run_termux_cmd", side_effect=fake_termux):
                    scheduler.check_and_notify_events()

                # Verifica notificação + vibração + termux-tts-speak
                self.assertTrue(any(c[0] == "termux-vibrate" for c in termux_cmds))
                self.assertTrue(any(c[0] == "termux-notification" for c in termux_cmds))
                self.assertTrue(any(c[0] == "termux-tts-speak" and "Tomar remédio" in " ".join(c) for c in termux_cmds))

                # Verifica fila de alertas da UI Web
                alerts = scheduler.pop_triggered_alerts()
                self.assertEqual(len(alerts), 1)
                self.assertEqual(alerts[0]["title"], "Tomar remédio")

                # Verifica reagendamento automático (+1 dia) mantendo status='pending'
                conn = memory_schedule._get_memory_db()
                cur = conn.cursor()
                cur.execute("SELECT trigger_at, status FROM scheduled_events WHERE title = 'Tomar remédio'")
                row = cur.fetchone()
                conn.close()

                expected_next = (past_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                self.assertEqual(row["status"], "pending")
                self.assertEqual(row["trigger_at"], expected_next)

    def test_save_and_get_contact_with_nlp_and_resolve_integration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_data = Path(tmpdir)
            with patch("android_agent.tools.memory_schedule.DATA_DIR", tmp_data), \
                 patch("android_agent.tools.contacts._run_termux_cmd") as mock_cmd:
                mock_cmd.return_value = subprocess.CompletedProcess(
                    args=["termux-contact-list"], returncode=0, stdout="[]", stderr=""
                )
                save_res = comms.save_contact("Carlos Eduardo", "(11) 99999-8888")
                self.assertEqual(save_res["status"], "ok")
                self.assertEqual(save_res["data"]["phone"], "11999998888")
                self.assertEqual(save_res["data"]["category"], "contato")

                # Deve resolver imediatamente via resolve_contact e get_contact
                num, disp, src = contacts.resolve_contact("Carlos Eduardo")
                self.assertEqual(num, "11999998888")
                self.assertEqual(src, "memory")

                get_res = comms.get_contact("Carlos Eduardo")
                self.assertEqual(get_res["status"], "ok")
                self.assertTrue(get_res["data"]["found"])
                self.assertEqual(get_res["data"]["phone"], "11999998888")

                # Deve funcionar também em make_call
                call_res = comms.make_call(target="Carlos Eduardo")
                self.assertEqual(call_res["status"], "ok")
                self.assertEqual(call_res["data"]["number"], "11999998888")

        # NLP routing
        c_save = match_intent_fallback("salva o contato Carlos 11999998888")
        self.assertIn("save_contact(", c_save)
        self.assertIn("Carlos", c_save)
        self.assertIn("11999998888", c_save)

        c_get = match_intent_fallback("qual o telefone do João?")
        self.assertEqual(c_get, "<call>get_contact(name='João')</call>")

    def test_connectivity_controls_adb_and_fallbacks(self):
        from android_agent.tools import hardware

        adb_calls = []

        def fake_adb_ok(args, timeout=5.0):
            adb_calls.append(args)
            return True, ""

        with patch("android_agent.tools.hardware.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.hardware.run_adb_shell", side_effect=fake_adb_ok):
            self.assertEqual(hardware.set_bluetooth_state(True)["data"]["method"], "adb_svc")
            self.assertEqual(hardware.set_mobile_data_state(False)["data"]["method"], "adb_svc")
            self.assertEqual(hardware.set_airplane_mode(True)["data"]["method"], "adb_cmd")
            self.assertEqual(hardware.set_hotspot_state(True)["data"]["method"], "adb_softap")

        self.assertIn(["svc", "bluetooth", "enable"], adb_calls)
        self.assertIn(["svc", "data", "disable"], adb_calls)
        self.assertIn(["cmd", "connectivity", "airplane-mode", "enable"], adb_calls)
        self.assertIn(["cmd", "wifi", "start-softap", "SilvaHotspot", "wpa2", "12345678"], adb_calls)

        # Fallback quando ADB bloqueia com SecurityException
        with patch("android_agent.tools.hardware.ensure_adb_connected", return_value="127.0.0.1:5555"), \
             patch("android_agent.tools.hardware.run_adb_shell", return_value=(False, "SecurityException")):
            fb_bt = hardware.set_bluetooth_state(False)
            self.assertTrue(fb_bt["data"].get("fallback"))
            fb_hs = hardware.set_hotspot_state(False)
            self.assertTrue(fb_hs["data"].get("fallback"))

        # NLP routing conectividade
        self.assertEqual(match_intent_fallback("liga o bluetooth"), "<call>set_bluetooth_state(state=True)</call>")
        self.assertEqual(match_intent_fallback("desativa o bt"), "<call>set_bluetooth_state(state=False)</call>")
        self.assertEqual(match_intent_fallback("liga os dados móveis"), "<call>set_mobile_data_state(state=True)</call>")
        self.assertEqual(match_intent_fallback("desativa o 4g"), "<call>set_mobile_data_state(state=False)</call>")
        self.assertEqual(match_intent_fallback("ativa o modo avião"), "<call>set_airplane_mode(state=True)</call>")
        self.assertEqual(match_intent_fallback("tira do modo avião"), "<call>set_airplane_mode(state=False)</call>")
        self.assertEqual(match_intent_fallback("liga o roteador"), "<call>set_hotspot_state(state=True)</call>")
        self.assertEqual(match_intent_fallback("desliga o compartilhamento de internet"), "<call>set_hotspot_state(state=False)</call>")


if __name__ == "__main__":
    unittest.main()
