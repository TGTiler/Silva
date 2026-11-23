"""
Testes unitários automatizados para o Assistente de Voz Offline Vosk (vosk-model-small-pt-0.3).
Valida botões da notificação persistente, máquina de estados, conversão de áudio,
reconhecimento com gramática das 39 tools, limpeza de tokens [unk] e integração com /api/chat.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))

import android_agent.voice_assistant as va


class TestVoiceAssistantVosk(unittest.TestCase):
    """Validação completa da notificação, gravação, transcrição Vosk e despacho para /api/chat."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.orig_data_dir = va.DATA_DIR
        self.orig_state_file = va.STATE_FILE
        self.orig_raw_file = va.RAW_AUDIO_FILE
        self.orig_wav_file = va.WAV_AUDIO_FILE
        self.orig_sim_hw = va.SIMULATE_HARDWARE
        self.orig_tts = va.ENABLE_VOICE_TTS
        self.orig_has_vosk = va.HAS_VOSK

        va.DATA_DIR = self.tmp_path
        va.STATE_FILE = self.tmp_path / "voice_state.json"
        va.RAW_AUDIO_FILE = self.tmp_path / "voice_raw.m4a"
        va.WAV_AUDIO_FILE = self.tmp_path / "voice_input.wav"
        va.SIMULATE_HARDWARE = False
        va.ENABLE_VOICE_TTS = False
        va.HAS_VOSK = True

    def tearDown(self):
        va.DATA_DIR = self.orig_data_dir
        va.STATE_FILE = self.orig_state_file
        va.RAW_AUDIO_FILE = self.orig_raw_file
        va.WAV_AUDIO_FILE = self.orig_wav_file
        va.SIMULATE_HARDWARE = self.orig_sim_hw
        va.ENABLE_VOICE_TTS = self.orig_tts
        va.HAS_VOSK = self.orig_has_vosk
        self.tmp_dir.cleanup()

    def test_clean_vosk_text(self):
        """Testa remoção de tokens de incerteza do Vosk ([unk], <unk>) e normalização de espaços."""
        raw = "silva [unk] abra o youtube  <UNK>  agora"
        cleaned = va._clean_vosk_text(raw)
        self.assertEqual(cleaned, "silva abra o youtube agora")

        self.assertEqual(va._clean_vosk_text("[unk]"), "")
        self.assertEqual(va._clean_vosk_text(""), "")
        self.assertEqual(va._clean_vosk_text(None), "")

    def test_vosk_grammar_structure(self):
        """Valida que a gramática Vosk contém termos-chave das 39 tools e termina com [unk]."""
        grammar = va.SILVA_VOSK_GRAMMAR
        self.assertIsInstance(grammar, list)
        self.assertIn("[unk]", grammar)
        self.assertEqual(grammar[-1], "[unk]", "O token [unk] deve ser o último da gramática Vosk")

        # Verifica ferramentas essenciais e conectivos PT-BR
        required_tools_terms = [
            "silva", "bateria", "foto", "lanterna", "wifi", "clima", "alarme",
            "calcula", "youtube", "whatsapp", "volume", "brilho", "uber", "ifood",
            "o", "a", "de", "do", "da", "para", "pra", "pro", "com", "sem"
        ]
        for term in required_tools_terms:
            self.assertIn(term, grammar, f"Termo '{term}' deve estar presente na gramática")

    def test_postprocess_transcript(self):
        """Testa pós-processamento de correções fonéticas comuns do Vosk PT-BR."""
        self.assertEqual(va._postprocess_transcript("abra o you tube"), "abra o youtube")
        self.assertEqual(va._postprocess_transcript("abre o iutube"), "abre o youtube")
        self.assertEqual(va._postprocess_transcript("manda no uatisapi"), "manda no whatsapp")
        self.assertEqual(va._postprocess_transcript("entra no whats app"), "entra no whatsapp")
        self.assertEqual(va._postprocess_transcript("abre o instagran"), "abre o instagram")
        self.assertEqual(va._postprocess_transcript("liga o uai fai"), "liga o wifi")
        self.assertEqual(va._postprocess_transcript("conecta no wi fi"), "conecta no wifi")
        self.assertEqual(va._postprocess_transcript(""), "")
        self.assertEqual(va._postprocess_transcript(None), "")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_update_voice_notification_two_buttons(self, mock_subproc, mock_which):
        """Verifica se termux-notification é invocado com 2 botões ('Falar' para start e 'Parar' para stop)."""
        mock_which.return_value = "/data/data/com.termux/files/usr/bin/termux-notification"
        mock_subproc.return_value = MagicMock(returncode=0)

        ok = va.update_voice_notification("Silva — Teste", "Conteúdo teste")
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
        self.assertIn("Conteúdo teste", cmd)
        self.assertIn("--button1", cmd)
        self.assertIn("Falar", cmd)
        self.assertIn("--button1-action", cmd)
        idx_b1 = cmd.index("--button1-action") + 1
        self.assertIn("--action start", cmd[idx_b1])

        self.assertIn("--button2", cmd)
        self.assertIn("Parar", cmd)
        self.assertIn("--button2-action", cmd)
        idx_b2 = cmd.index("--button2-action") + 1
        self.assertIn("--action stop", cmd[idx_b2])

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_remove_voice_notification(self, mock_subproc, mock_which):
        """Verifica remoção da notificação persistente via termux-notification-remove."""
        mock_which.return_value = "/data/data/com.termux/files/usr/bin/termux-notification-remove"
        mock_subproc.return_value = MagicMock(returncode=0)

        ok = va.remove_voice_notification()
        self.assertTrue(ok)
        mock_subproc.assert_called_once_with(
            ["termux-notification-remove", "silva_voice"],
            capture_output=True,
            text=True,
            timeout=5
        )

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_start(self, mock_subproc, mock_which):
        """Testa o início da gravação com vibração de 70ms e gravação de estado."""
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"
        mock_subproc.return_value = MagicMock(returncode=0)

        va.handle_action_start()

        state = va.get_voice_state()
        self.assertTrue(state.get("recording"))
        self.assertGreater(state.get("started_at"), 0)

        calls = [c[0][0] for c in mock_subproc.call_args_list]
        has_vibrate = any(c[0] == "termux-vibrate" and "-d" in c and "70" in c for c in calls)
        has_record = any(
            c[0] == "termux-microphone-record"
            and "-e" in c and "aac" in c
            and "-r" in c and "16000" in c
            and "-b" in c and "64000" in c
            and "-l" in c and "60" in c
            for c in calls
        )
        self.assertTrue(has_vibrate, "Deve disparar vibração de 70ms")
        self.assertTrue(has_record, "Deve iniciar gravação termux-microphone-record em 16kHz")

    @patch("urllib.request.urlopen")
    @patch("wave.open")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_stop_success_with_vosk_and_chat_dispatch(self, mock_subproc, mock_which, mock_wave_open, mock_urlopen):
        """
        Testa ação do botão 'Parar':
        - Converte áudio com ffmpeg
        - Reconhece fala via Vosk KaldiRecognizer
        - Limpa marcações [unk]
        - Envia texto para /api/chat
        - Fala resposta com TTS
        - Remove arquivos temporários
        """
        va.ENABLE_VOICE_TTS = True
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"
        def mock_subproc_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                va.WAV_AUDIO_FILE.write_bytes(b"dummy_wav_audio")
            return MagicMock(returncode=0)

        mock_subproc.side_effect = mock_subproc_side_effect

        # Cria arquivo gravado bruto m4a
        va.RAW_AUDIO_FILE.write_bytes(b"dummy_m4a_audio")

        # Mock do wave.open para simular áudio PCM
        mock_wf = MagicMock()
        mock_wf.getframerate.return_value = 16000
        mock_wf.readframes.side_effect = [b"audio_chunk_1", b""]
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        # Mock do Vosk Model e KaldiRecognizer
        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.FinalResult.return_value = json.dumps({"text": "silva [unk] abra o youtube"})

        mock_model_cls = MagicMock()
        mock_rec_cls = MagicMock(return_value=mock_rec)

        # Mock da resposta do /api/chat
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "ok",
            "message": "Silva: Abrindo o YouTube...",
            "raw_call": "<call>open_app(app_name='YouTube')</call>"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        with patch("android_agent.voice_assistant.Model", mock_model_cls), \
             patch("android_agent.voice_assistant.KaldiRecognizer", mock_rec_cls), \
             patch("os.path.isdir", return_value=True):
            va.handle_action_stop()

        # 1. Verifica chamada ao ffmpeg para conversão WAV 16kHz mono com filtro dynaudnorm
        calls = [c[0][0] for c in mock_subproc.call_args_list]
        ffmpeg_call = next((c for c in calls if c[0] == "ffmpeg"), None)
        self.assertIsNotNone(ffmpeg_call, "FFmpeg deve ser chamado para converter o áudio")
        self.assertIn("-ar", ffmpeg_call)
        self.assertIn("16000", ffmpeg_call)
        self.assertIn("-ac", ffmpeg_call)
        self.assertIn("1", ffmpeg_call)
        self.assertIn("-af", ffmpeg_call)
        self.assertIn("highpass=f=80,dynaudnorm", ffmpeg_call)
        self.assertIn("pcm_s16le", ffmpeg_call)

        # 2. Verifica envio para /api/chat
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/api/chat", req.full_url)
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body.get("message"), "silva abra o youtube")
        if va.ACCESS_PIN:
            self.assertEqual(req.headers.get("X-access-pin"), va.ACCESS_PIN)

        # 3. Verifica notificação atualizada com resultado
        notif_calls = [c[0][0] for c in mock_subproc.call_args_list if len(c[0]) > 0 and len(c[0][0]) > 0 and c[0][0][0] == "termux-notification"]
        self.assertTrue(len(notif_calls) >= 2)
        last_notif = notif_calls[-1]
        self.assertIn("silva_voice", last_notif)
        self.assertIn("Silva — Pronto", last_notif)
        content_idx = last_notif.index("--content") + 1
        self.assertIn('"silva abra o youtube" -> Silva: Abrindo o YouTube...', last_notif[content_idx])

        # 4. Verifica TTS ativado
        tts_call = next((c for c in calls if c[0] == "termux-tts-speak"), None)
        self.assertIsNotNone(tts_call)
        self.assertIn("Silva: Abrindo o YouTube...", tts_call)

        # 5. Verifica estado de gravação resetado e arquivos limpos
        state = va.get_voice_state()
        self.assertFalse(state.get("recording"))
        self.assertFalse(va.RAW_AUDIO_FILE.exists())
        self.assertFalse(va.WAV_AUDIO_FILE.exists())

    @patch("urllib.request.urlopen")
    @patch("wave.open")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_stop_empty_speech(self, mock_subproc, mock_which, mock_wave_open, mock_urlopen):
        """Testa áudio sem fala reconhecida (apenas silêncio ou [unk])."""
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"
        
        def mock_subproc_side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                va.WAV_AUDIO_FILE.write_bytes(b"dummy_wav_audio")
            return MagicMock(returncode=0)

        mock_subproc.side_effect = mock_subproc_side_effect

        va.RAW_AUDIO_FILE.write_bytes(b"dummy_m4a_audio")

        mock_wf = MagicMock()
        mock_wf.getframerate.return_value = 16000
        mock_wf.readframes.side_effect = [b"silence", b""]
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        mock_rec = MagicMock()
        mock_rec.FinalResult.return_value = json.dumps({"text": "[unk]"})

        with patch("android_agent.voice_assistant.Model", MagicMock()), \
             patch("android_agent.voice_assistant.KaldiRecognizer", MagicMock(return_value=mock_rec)), \
             patch("os.path.isdir", return_value=True):
            va.handle_action_stop()

        # Garante que /api/chat não é chamado
        mock_urlopen.assert_not_called()

        # Notificação restaurada
        notif_calls = [c[0][0] for c in mock_subproc.call_args_list if len(c[0]) > 0 and len(c[0][0]) > 0 and c[0][0][0] == "termux-notification"]
        self.assertTrue(len(notif_calls) >= 2)
        last_notif = notif_calls[-1]
        self.assertIn("Silva — Pronto", last_notif)
        content_idx = last_notif.index("--content") + 1
        self.assertEqual(last_notif[content_idx], "Nenhuma fala reconhecida. Toque em Falar.")

        # Arquivos temporários removidos
        self.assertFalse(va.RAW_AUDIO_FILE.exists())
        self.assertFalse(va.WAV_AUDIO_FILE.exists())

    @patch("urllib.request.urlopen")
    @patch("wave.open")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_stop_vosk_grammar_toggle(self, mock_subproc, mock_which, mock_wave_open, mock_urlopen):
        """Testa se KaldiRecognizer é instanciado com ou sem gramática conforme VOSK_USE_GRAMMAR."""
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"
        mock_subproc.side_effect = lambda cmd, **kwargs: MagicMock(returncode=0)

        mock_wf = MagicMock()
        mock_wf.getframerate.return_value = 16000
        mock_wf.readframes.side_effect = [b"audio", b""]
        mock_wave_open.return_value.__enter__.return_value = mock_wf

        mock_rec = MagicMock()
        mock_rec.AcceptWaveform.return_value = True
        mock_rec.FinalResult.return_value = json.dumps({"text": "silva bateria"})
        mock_rec_cls = MagicMock(return_value=mock_rec)

        # 1. Com VOSK_USE_GRAMMAR = False (padrão)
        va.VOSK_USE_GRAMMAR = False
        va.RAW_AUDIO_FILE.write_bytes(b"dummy")
        va.WAV_AUDIO_FILE.write_bytes(b"dummy")

        with patch("android_agent.voice_assistant.Model", MagicMock()), \
             patch("android_agent.voice_assistant.KaldiRecognizer", mock_rec_cls), \
             patch("os.path.isdir", return_value=True):
            va.handle_action_stop()

        self.assertEqual(mock_rec_cls.call_count, 1)
        args, kwargs = mock_rec_cls.call_args
        self.assertEqual(len(args), 2, "Sem gramática deve passar apenas model e framerate")

        # 2. Com VOSK_USE_GRAMMAR = True
        mock_rec_cls.reset_mock()
        mock_wf.readframes.side_effect = [b"audio", b""]
        va.VOSK_USE_GRAMMAR = True
        va.RAW_AUDIO_FILE.write_bytes(b"dummy")
        va.WAV_AUDIO_FILE.write_bytes(b"dummy")

        with patch("android_agent.voice_assistant.Model", MagicMock()), \
             patch("android_agent.voice_assistant.KaldiRecognizer", mock_rec_cls), \
             patch("os.path.isdir", return_value=True):
            va.handle_action_stop()

        self.assertEqual(mock_rec_cls.call_count, 1)
        args, kwargs = mock_rec_cls.call_args
        self.assertEqual(len(args), 3, "Com gramática deve passar model, framerate e JSON da gramática")
        self.assertIn("silva", args[2])
        self.assertIn("[unk]", args[2])


if __name__ == "__main__":
    unittest.main()
