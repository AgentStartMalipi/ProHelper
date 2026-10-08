"""DeepgramSTT sin red: se reemplaza `_request` por respuestas grabadas."""

from __future__ import annotations

import io
import unittest
import wave

import numpy as np

from speak.config import Config
from speak.transcriber import DeepgramSTT, STTError, _wav_bytes, make_stt


def fake(stt: DeepgramSTT, payload: dict) -> list:
    calls = []

    def _request(method, path, body=None, content_type="audio/wav", timeout=30.0, waits=(0.0,)):
        calls.append((method, path, body, content_type, timeout))
        return payload

    stt._request = _request
    return calls


class DeepgramTests(unittest.TestCase):
    def test_phrase_and_multilingual_default(self):
        stt = DeepgramSTT("k", language="")
        calls = fake(stt, {"results": {"channels": [{"alternatives": [
            {"transcript": "Tuve un hackathon el año pasado.", "confidence": 0.97,
             "languages": ["es"]}]}]}})
        text, lang, conf = stt.transcribe_lang(np.zeros(16000 * 2, np.float32), 16000)
        self.assertEqual(text, "Tuve un hackathon el año pasado.")
        self.assertEqual(lang, "es")
        self.assertIn("language=multi", calls[0][1])
        self.assertIn("model=nova-3", calls[0][1])
        self.assertTrue(calls[0][2].startswith(b"RIFF"))

    def test_fixed_language_and_hallucination_filter(self):
        stt = DeepgramSTT("k", language="en")
        calls = fake(stt, {"results": {"channels": [{"alternatives": [{"transcript": "Thank you."}]}]}})
        self.assertEqual(stt.transcribe(np.zeros(8000, np.float32), 16000), "")
        self.assertIn("language=en", calls[0][1])

    def test_file_diarization(self):
        import tempfile, pathlib

        stt = DeepgramSTT("k")
        calls = fake(stt, {"results": {"utterances": [
            {"start": 0.0, "end": 2.0, "transcript": "How much does it cost?", "speaker": 0},
            {"start": 2.5, "end": 5.0, "transcript": "Around ten thousand.", "speaker": 1},
        ]}})
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "call.wav"
            p.write_bytes(_wav_bytes(np.zeros(1600, np.float32), 16000))
            segs = stt.transcribe_file(p)
        self.assertEqual([s.speaker for s in segs], ["A", "B"])
        self.assertIn("diarize=true", calls[0][1])

    def test_network_blip_retries_then_succeeds(self):
        import socket
        from unittest import mock

        stt = DeepgramSTT("k")
        ok = mock.Mock(status=200)
        ok.read.return_value = b'{"results":{"channels":[{"alternatives":[{"transcript":"hola"}]}]}}'
        conn = mock.Mock()
        conn.request.side_effect = [socket.gaierror(11001, "getaddrinfo failed"), None]
        conn.getresponse.return_value = ok
        stt._conn = lambda: conn
        with mock.patch("speak.transcriber.time.sleep"):
            self.assertEqual(stt.transcribe(np.zeros(16000, np.float32), 16000), "hola")
        self.assertEqual(conn.request.call_count, 2)

    def test_no_network_falls_back_to_local(self):
        from speak.transcriber import STTNetworkError

        class Local:
            def transcribe_lang(self, audio, sr, prompt="", language=None):
                return "texto local", None, 0.0

        stt = DeepgramSTT("k", fallback_factory=Local)

        def down(*a, **k):
            raise STTNetworkError("no pude conectar con Deepgram: getaddrinfo failed")

        stt._request = down
        self.assertEqual(stt.transcribe(np.zeros(16000, np.float32), 16000), "texto local")
        # Sin respaldo, el error si sube.
        stt2 = DeepgramSTT("k")
        stt2._request = down
        with self.assertRaises(STTNetworkError):
            stt2.transcribe(np.zeros(16000, np.float32), 16000)

    def test_live_phrase_short_timeout_then_local(self):
        # Medido 2026-10-07: una frase colgada 22 s detenia toda la transcripcion
        # en vivo. Ahora: 8 s, un reintento con conexion nueva y luego Whisper.
        from unittest import mock

        class Local:
            def transcribe_lang(self, audio, sr, prompt="", language=None):
                return "texto local", None, 0.0

        stt = DeepgramSTT("k", fallback_factory=Local)
        conn = mock.Mock()
        conn.getresponse.side_effect = TimeoutError("timed out")
        stt._conn = lambda: conn
        with mock.patch("speak.transcriber.time.sleep"):
            self.assertEqual(stt.transcribe(np.zeros(16000, np.float32), 16000), "texto local")
        self.assertEqual(conn.request.call_count, 2)
        self.assertEqual(conn.timeout, DeepgramSTT.LIVE_TIMEOUT_S)
        conn.sock.settimeout.assert_called_with(DeepgramSTT.LIVE_TIMEOUT_S)

    def test_file_uses_long_timeout(self):
        import tempfile, pathlib

        stt = DeepgramSTT("k")
        calls = fake(stt, {"results": {"utterances": []}})
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "call.wav"
            p.write_bytes(_wav_bytes(np.zeros(1600, np.float32), 16000))
            stt.transcribe_file(p)
        self.assertEqual(calls[0][4], DeepgramSTT.FILE_TIMEOUT_S)

    def test_bad_key_does_not_fall_back(self):
        stt = DeepgramSTT("k", fallback_factory=lambda: self.fail("no debe usar respaldo"))

        def unauthorized(*a, **k):
            raise STTError("Deepgram rechazo la llave (401)")

        stt._request = unauthorized
        with self.assertRaises(STTError):
            stt.transcribe(np.zeros(16000, np.float32), 16000)

    def test_wav_is_valid_16bit(self):
        data = _wav_bytes(np.array([0.0, 0.5, -1.5], np.float32), 16000)
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()),
                             (1, 2, 16000, 3))

    def test_factory_and_missing_key(self):
        cfg = Config()
        cfg.STT_PROVIDER = "deepgram"
        cfg.DEEPGRAM_API_KEY = "k"
        stt = make_stt(cfg)
        self.assertIsInstance(stt, DeepgramSTT)
        self.assertIn("Kubernetes", stt.keyterms)
        calls = fake(stt, {"results": {"channels": [{"alternatives": [{"transcript": "ok"}]}]}})
        stt.transcribe(np.zeros(16000, np.float32), 16000)
        self.assertIn("keyterm=Kubernetes", calls[0][1])
        self.assertIsInstance(make_stt(cfg, for_files=True), DeepgramSTT)
        cfg.DEEPGRAM_API_KEY = ""
        with self.assertRaises(STTError):
            make_stt(cfg)


if __name__ == "__main__":
    unittest.main()
