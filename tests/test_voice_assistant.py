"""
Testes unitários automatizados para o Assistente de Voz Offline (whisper.cpp + notificação persistente).
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


class TestVoiceAssistant(unittest.TestCase):
    """Validação da máquina de estados, conversão de áudio, transcrição e integração com /api/chat."""

    def setUp(self):
        # Isola o diretório data para testes temporários
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

        self.orig_data_dir = va.DATA_DIR
        self.orig_state_file = va.STATE_FILE
        self.orig_raw_file = va.RAW_AUDIO_FILE
        self.orig_wav_file = va.WAV_AUDIO_FILE
        self.orig_sim_hw = va.SIMULATE_HARDWARE

        va.DATA_DIR = self.tmp_path
        va.STATE_FILE = self.tmp_path / "voice_state.json"
        va.RAW_AUDIO_FILE = self.tmp_path / "voice_raw.m4a"
        va.WAV_AUDIO_FILE = self.tmp_path / "voice_input.wav"
        va.SIMULATE_HARDWARE = False

    def tearDown(self):
        va.DATA_DIR = self.orig_data_dir
        va.STATE_FILE = self.orig_state_file
        va.RAW_AUDIO_FILE = self.orig_raw_file
        va.WAV_AUDIO_FILE = self.orig_wav_file
        va.SIMULATE_HARDWARE = self.orig_sim_hw
        self.tmp_dir.cleanup()

    def test_clean_whisper_text(self):
        """Verifica a higienização de timestamps e marcadores sonoros do Whisper."""
        raw = "[00:00:00.000 --> 00:00:03.500]   qual o meu wifi? [Música] (silêncio)  "
        cleaned = va.clean_whisper_text(raw)
        self.assertEqual(cleaned, "qual o meu wifi?")

        raw_multiline = (
            "[00:00:00.000 --> 00:00:02.000] Silva, ligue a lanterna.\n"
            "[00:00:02.000 --> 00:00:04.000] [Ruído de fundo] Por favor."
        )
        cleaned_multi = va.clean_whisper_text(raw_multiline)
        self.assertEqual(cleaned_multi, "Silva, ligue a lanterna. Por favor.")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_update_voice_notification(self, mock_subproc, mock_which):
        """Verifica se termux-notification é invocado com parâmetros e botões corretos."""
        mock_which.return_value = "/data/data/com.termux/files/usr/bin/termux-notification"
        mock_subproc.return_value = MagicMock(returncode=0)

        ok = va.update_voice_notification("Silva — Teste", "Conteúdo do teste")
        self.assertTrue(ok)
        self.assertTrue(mock_subproc.called)

        cmd = mock_subproc.call_args[0][0]
        self.assertEqual(cmd[0], "termux-notification")
        self.assertIn("--id", cmd)
        self.assertIn("silva_voice", cmd)
        self.assertIn("--ongoing", cmd)
        self.assertIn("--button1", cmd)
        self.assertIn("Falar", cmd)
        self.assertIn("--button2", cmd)
        self.assertIn("Parar", cmd)
        self.assertIn("--title", cmd)
        self.assertIn("Silva — Teste", cmd)
        self.assertIn("--content", cmd)
        self.assertIn("Conteúdo do teste", cmd)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_start(self, mock_subproc, mock_which):
        """Testa início da gravação, feedback háptico e gravação de estado."""
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"
        mock_subproc.return_value = MagicMock(returncode=0)

        va.handle_action_start()

        state = va.get_voice_state()
        self.assertTrue(state.get("recording"))
        self.assertGreater(state.get("started_at"), 0)

        # Checa chamadas a termux-vibrate e termux-microphone-record
        calls = [c[0][0] for c in mock_subproc.call_args_list]
        has_vibrate = any("termux-vibrate" in c[0] and "-d" in c and "80" in c for c in calls)
        has_record = any("termux-microphone-record" in c[0] and "-l" in c and "60" in c for c in calls)

        self.assertTrue(has_vibrate, "Deveria ter disparado vibração háptica curta (80ms)")
        self.assertTrue(has_record, "Deveria ter iniciado gravação via termux-microphone-record")

    @patch("urllib.request.urlopen")
    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_stop_and_chat_dispatch(self, mock_subproc, mock_which, mock_urlopen):
        """Testa parada da gravação, conversão ffmpeg, whisper e despacho para /api/chat."""
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"

        # Cria arquivo simulado m4a gravado
        va.RAW_AUDIO_FILE.write_bytes(b"dummy_raw_audio")

        # Mock do retorno do subprocess.run
        def mock_run_side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            # Se for whisper-cli, retorna saída simulada
            if "whisper" in cmd[0]:
                return MagicMock(returncode=0, stdout="[00:00:00.000 --> 00:00:02.000] qual o meu wifi?")
            # Se for ffmpeg, simula criação do WAV
            if cmd[0] == "ffmpeg":
                va.WAV_AUDIO_FILE.write_bytes(b"dummy_wav_audio")
                return MagicMock(returncode=0)
            return MagicMock(returncode=0, stdout="")

        mock_subproc.side_effect = mock_run_side_effect

        # Mock da resposta do /api/chat
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "status": "ok",
            "message": "Silva: Conectado ao Wi-Fi 'Casa_5G' | IP: 192.168.0.106",
            "raw_call": "<call>get_wifi_info()</call>"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Força detecção de modelo e binário whisper
        with patch("android_agent.voice_assistant.find_whisper_bin", return_value="whisper-cli"), \
             patch("android_agent.voice_assistant.find_whisper_model", return_value="/models/ggml-base.bin"), \
             patch("os.path.isfile", return_value=True):

            va.handle_action_stop()

        # 1. Verifica estado de gravação encerrado
        state = va.get_voice_state()
        self.assertFalse(state.get("recording"))

        # 2. Verifica se ffmpeg foi chamado com os parâmetros de áudio corretos
        calls = [c[0][0] for c in mock_subproc.call_args_list]
        ffmpeg_call = next((c for c in calls if c[0] == "ffmpeg"), None)
        self.assertIsNotNone(ffmpeg_call, "FFmpeg deveria ter sido executado")
        self.assertIn("-ar", ffmpeg_call)
        self.assertIn("16000", ffmpeg_call)
        self.assertIn("-ac", ffmpeg_call)
        self.assertIn("1", ffmpeg_call)
        self.assertIn("pcm_s16le", ffmpeg_call)

        # 3. Verifica se whisper-cli foi executado com -nt e -l pt
        whisper_call = next((c for c in calls if "whisper" in c[0]), None)
        self.assertIsNotNone(whisper_call, "whisper-cli deveria ter sido executado")
        self.assertIn("-l", whisper_call)
        self.assertIn("pt", whisper_call)
        self.assertIn("-nt", whisper_call)

        # 4. Verifica envio para /api/chat via urllib.request
        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/api/chat", req.full_url)
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body.get("message"), "qual o meu wifi?")
        if va.ACCESS_PIN:
            self.assertEqual(req.headers.get("X-access-pin"), va.ACCESS_PIN)

        # 5. Verifica se arquivos temporários foram excluídos por privacidade
        self.assertFalse(va.RAW_AUDIO_FILE.exists(), "RAW_AUDIO_FILE deve ser apagado após o processamento")
        self.assertFalse(va.WAV_AUDIO_FILE.exists(), "WAV_AUDIO_FILE deve ser apagado após o processamento")

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_action_stop_service(self, mock_subproc, mock_which):
        """Testa encerramento do serviço e remoção da notificação."""
        mock_which.side_effect = lambda cmd: f"/bin/{cmd}"
        mock_subproc.return_value = MagicMock(returncode=0)

        va.set_voice_state(recording=True)
        va.handle_action_stop_service()

        state = va.get_voice_state()
        self.assertFalse(state.get("recording"))

        calls = [c[0][0] for c in mock_subproc.call_args_list]
        has_remove = any("termux-notification-remove" in c[0] and "silva_voice" in c for c in calls)
        self.assertTrue(has_remove, "Deveria ter chamado termux-notification-remove silva_voice")


if __name__ == "__main__":
    unittest.main()
