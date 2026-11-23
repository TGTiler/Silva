"""
Testes unitários automatizados para o Assistente de Voz Offline Nativo do Android (termux-speech-to-text).
Valida o fluxo de toque único, transcrição nativa, despacho para /api/chat e notificações persistentes.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

import android_agent.voice_assistant as va


class TestVoiceAssistantNativeSTT(unittest.TestCase):
    """Validação da notificação de toque único, transcrição nativa e integração com /api/chat."""

    def setUp(self):
        self.orig_sim_hw = va.SIMULATE_HARDWARE
        self.orig_tts = va.ENABLE_VOICE_TTS
        va.SIMULATE_HARDWARE = False
        va.ENABLE_VOICE_TTS = False

    def tearDown(self):
        va.SIMULATE_HARDWARE = self.orig_sim_hw
        va.ENABLE_VOICE_TTS = self.orig_tts

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_update_voice_notification_single_button(self, mock_subproc, mock_which):
        """Verifica se termux-notification é invocado com toque único (apenas botão Falar para listen)."""
        mock_which.return_value = "/data/data/com.termux/files/usr/bin/termux-notification"
        mock_subproc.return_value = MagicMock(returncode=0)

        ok = va.update_voice_notification("Silva — Teste", "Conteúdo de teste")
        self.assertTrue(ok)
        self.assertTrue(mock_subproc.called)

        cmd = mock_subproc.call_args[0][0]
        self.assertEqual(cmd[0], "termux-notification")
        self.assertIn("--id", cmd)
        self.assertIn("silva_voice", cmd)
        self.assertIn("--ongoing", cmd)
        self.assertIn("--priority", cmd)
        self.assertIn("high", cmd)
        self.assertIn("--title", cmd)
        self.assertIn("Silva — Teste", cmd)
        self.assertIn("--content", cmd)
        self.assertIn("Conteúdo de teste", cmd)
        self.assertIn("--button1", cmd)
        self.assertIn("Falar", cmd)
        self.assertIn("--button1-action", cmd)

        action_idx = cmd.index("--button1-action") + 1
        self.assertIn("--action listen", cmd[action_idx])

        # Garante a ausência do botão 2 (fluxo simplificado de toque único)
        self.assertNotIn("--button2", cmd)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_remove_voice_notification(self, mock_subproc, mock_which):
        """Verifica remoção da notificação persistente via termux-notification-remove."""
        mock_which.return_value = "/data/data/com.termux/files/usr/bin/termux-notification-remove"
        mock_subproc.return_value = MagicMock(returncode=0)

        ok = va.remove_voice_notification()
        self.assertTrue(ok)

        cmd = mock_subproc.call_args[0][0]
        self.assertEqual(cmd, ["termux-notification-remove", "silva_voice"])

    @patch("android_agent.voice_assistant.update_voice_notification")
    def test_action_init(self, mock_update_notif):
        """Testa inicialização do serviço com estado 'Pronto' e instrução para toque único."""
        va.handle_action_init()
        mock_update_notif.assert_called_once_with(
            "Silva — Pronto",
            "Toque em Falar para dar um comando de voz."
        )

    @patch("android_agent.voice_assistant.remove_voice_notification")
    def test_action_stop_service(self, mock_remove_notif):
        """Testa interrupção do serviço e remoção da notificação."""
        va.handle_action_stop_service()
        mock_remove_notif.assert_called_once()

    @patch("urllib.request.urlopen")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_listen_success_with_chat_dispatch_and_tts(self, mock_subproc, mock_which, mock_urlopen):
        """
        Mockar termux-speech-to-text retornando 'Abra o YouTube':
        - Valida vibração tátil (60ms)
        - Valida envio para /api/chat com X-Access-Pin
        - Valida atualização da notificação --id silva_voice
        - Valida chamada ao TTS em voz alta
        """
        va.ENABLE_VOICE_TTS = True
        mock_which.side_effect = lambda cmd: f"/data/data/com.termux/files/usr/bin/{cmd}"

        def mock_subproc_side_effect(cmd, **kwargs):
            if cmd[0] == "termux-speech-to-text":
                return MagicMock(returncode=0, stdout="Abra o YouTube\n")
            return MagicMock(returncode=0, stdout="")

        mock_subproc.side_effect = mock_subproc_side_effect

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "ok",
            "message": "Silva: Abrindo YouTube...",
            "raw_call": "<call>open_app(app_name='YouTube')</call>"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        va.handle_action_listen()

        # 1. Verifica vibração háptica curta de 60ms
        calls = [c[0][0] for c in mock_subproc.call_args_list]
        has_vibrate = any(c[0] == "termux-vibrate" and "-d" in c and "60" in c for c in calls)
        self.assertTrue(has_vibrate, "Deveria ter disparado vibração de 60ms")

        # 2. Verifica execução do termux-speech-to-text com timeout de 20s
        stt_calls = [c for c in mock_subproc.call_args_list if c[0][0][0] == "termux-speech-to-text"]
        self.assertEqual(len(stt_calls), 1)
        self.assertEqual(stt_calls[0][1].get("timeout"), 20)

        # 3. Verifica envio para /api/chat via urllib.request
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/api/chat", req.full_url)
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body.get("message"), "Abra o YouTube")
        if va.ACCESS_PIN:
            self.assertEqual(req.headers.get("X-access-pin"), va.ACCESS_PIN)

        # 4. Verifica atualização da notificação com a transcrição e resposta
        notif_calls = [c[0][0] for c in mock_subproc.call_args_list if c[0][0][0] == "termux-notification"]
        self.assertTrue(len(notif_calls) >= 2)  # "Ouvindo..." seguido de "Pronto" com resposta
        last_notif = notif_calls[-1]
        self.assertIn("silva_voice", last_notif)
        self.assertIn("Silva — Pronto", last_notif)
        content_idx = last_notif.index("--content") + 1
        self.assertIn('"Abra o YouTube" -> Silva: Abrindo YouTube...', last_notif[content_idx])

        # 5. Verifica síntese de voz TTS via termux-tts-speak
        tts_call = next((c for c in calls if c[0] == "termux-tts-speak"), None)
        self.assertIsNotNone(tts_call, "Deveria ter executado termux-tts-speak")
        self.assertIn("-l", tts_call)
        self.assertIn("pt-BR", tts_call)
        self.assertIn("Silva: Abrindo YouTube...", tts_call)

    @patch("urllib.request.urlopen")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_listen_empty_cancels_cleanly_without_chat(self, mock_subproc, mock_which, mock_urlopen):
        """
        Mockar termux-speech-to-text retornando string vazia:
        - Valida restauração limpa da notificação sem chamar /api/chat
        """
        mock_which.side_effect = lambda cmd: f"/data/data/com.termux/files/usr/bin/{cmd}"

        def mock_subproc_side_effect(cmd, **kwargs):
            if cmd[0] == "termux-speech-to-text":
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="")

        mock_subproc.side_effect = mock_subproc_side_effect

        va.handle_action_listen()

        # Valida que /api/chat NUNCA foi chamado
        mock_urlopen.assert_not_called()

        # Valida restauração da notificação
        notif_calls = [c[0][0] for c in mock_subproc.call_args_list if c[0][0][0] == "termux-notification"]
        self.assertTrue(len(notif_calls) >= 2)
        last_notif = notif_calls[-1]
        self.assertIn("Silva — Pronto", last_notif)
        content_idx = last_notif.index("--content") + 1
        self.assertEqual(last_notif[content_idx], "Nenhum comando captado. Toque em Falar para tentar novamente.")


if __name__ == "__main__":
    unittest.main()
