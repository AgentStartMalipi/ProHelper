"""Audio sin hardware: remuestreo, ganancia de "Ellos", eleccion de
dispositivos, relleno por reloj de la grabadora, apertura de microfonos que
rechazan 16 kHz y el veredicto de `--mics`.

Lo que si necesita hardware (microfono y loopback reales) se verifico aparte
con SAPI sonando por los parlantes; ver el docstring de notes/recorder.py."""

from __future__ import annotations

import shutil
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest import mock

import numpy as np

from speak import audio_capture as ac
from speak.notes import recorder as rec_mod
from speak.notes.recorder import AutoGain, DualRecorder, _WavSink, pick_loopback


def sine(rate: int, seconds: float, hz: float = 440.0, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def in_blocks(x: np.ndarray, n: int):
    for i in range(0, len(x), n):
        yield x[i:i + n]


class ResamplerTests(unittest.TestCase):
    def check_stream(self, rate: int, block: int):
        x = sine(rate, 3.0)
        r = ac.Resampler16k(rate)
        out = np.concatenate([r(b) for b in in_blocks(x, block)])
        expected = len(x) * 16000 / rate
        self.assertLess(abs(len(out) - expected), 3, (rate, block, len(out), expected))
        # Sin saltos entre bloques: el mismo resultado que remuestrear de una vez.
        t_out = np.arange(len(out)) / 16000
        ref = (0.5 * np.sin(2 * np.pi * 440 * t_out)).astype(np.float32)
        err = np.abs(out[10:-10] - ref[10:-10]).max()
        self.assertLess(err, 0.08, (rate, block, err))

    def test_integer_ratio_48k_odd_blocks(self):
        self.check_stream(48000, 1024)  # 1024 no es multiplo de 3: hay arrastre

    def test_fractional_44k(self):
        self.check_stream(44100, 4410)
        self.check_stream(44100, 1000)

    def test_16k_passthrough(self):
        x = sine(16000, 0.5)
        self.assertTrue(np.array_equal(ac.Resampler16k(16000)(x), x))


class AutoGainTests(unittest.TestCase):
    def feed(self, g: AutoGain, x: np.ndarray, rate: int = 48000):
        return np.concatenate([g(b, rate) for b in in_blocks(x, 1024)])

    def test_quiet_loopback_reaches_target(self):
        # Medido: con el volumen de Windows bajo, una voz llega a pico 0,013.
        g = AutoGain()
        out = self.feed(g, sine(48000, 2.0, amp=0.013))
        self.assertAlmostEqual(float(np.abs(out[-4800:]).max()), 0.3, delta=0.03)

    def test_loud_audio_is_not_attenuated(self):
        g = AutoGain()
        x = sine(48000, 1.0, amp=0.8)
        out = self.feed(g, x)
        self.assertTrue(np.allclose(out, x))

    def test_digital_silence_stays_silent_and_gain_capped(self):
        g = AutoGain(max_gain=100)
        out = self.feed(g, np.zeros(48000, np.float32))
        self.assertFalse(np.any(out))
        self.assertEqual(g.gain, 1.0)
        self.feed(g, sine(48000, 1.0, amp=0.0005))
        self.assertEqual(g.gain, 100.0)

    def test_release_is_gradual(self):
        g = AutoGain(release_s=4.0)
        self.feed(g, sine(48000, 1.0, amp=0.3))
        self.assertAlmostEqual(g.gain, 1.0, places=2)
        self.feed(g, sine(48000, 1.0, amp=0.01))  # un segundo bajo: casi no sube
        self.assertLess(g.gain, 2.0)
        self.feed(g, sine(48000, 20.0, amp=0.01))  # sostenido: llega al objetivo
        self.assertAlmostEqual(g.gain, 30.0, delta=1.5)


class DeviceChoiceTests(unittest.TestCase):
    LOOPS = [{"name": "Speaker (Realtek(R) Audio) [Loopback]", "index": 13},
             {"name": "Headphones (Jabra Evolve2) [Loopback]", "index": 14}]

    def test_default_output(self):
        self.assertEqual(pick_loopback(self.LOOPS, "Speaker (Realtek(R) Audio)", "")["index"], 13)

    def test_by_name_case_insensitive(self):
        self.assertEqual(pick_loopback(self.LOOPS, "Speaker (Realtek(R) Audio)", "jabra")["index"], 14)

    def test_unknown_name_falls_back_to_default(self):
        self.assertEqual(pick_loopback(self.LOOPS, "Speaker (Realtek(R) Audio)", "bose")["index"], 13)

    def test_nothing_matches(self):
        self.assertIsNone(pick_loopback([], "Speaker", ""))

    def test_recorder_reads_loopback_from_config(self):
        from speak.config import Config

        cfg = Config()
        cfg.LOOPBACK_DEVICE = "Jabra"
        with mock.patch.object(Config, "load", return_value=cfg):
            self.assertEqual(DualRecorder(Path("x")).loopback_device, "Jabra")
        self.assertEqual(DualRecorder(Path("x"), loopback_device="").loopback_device, "")


class OpenInputTests(unittest.TestCase):
    """Medido en esta maquina: la webcam por WASAPI rechaza 16 kHz
    ("Invalid sample rate") y abre a 44,1 kHz."""

    def test_falls_back_to_native_rate_and_resamples(self):
        import sounddevice as sd

        opened = []

        class FakeStream:
            def __init__(self, samplerate, callback, **kw):
                if samplerate == 16000:
                    raise sd.PortAudioError("Error opening InputStream: Invalid sample rate")
                opened.append(samplerate)
                self.callback = callback

        dev = {"name": "Microphone (HP 320 FHD Webcam)", "hostapi": 2, "default_samplerate": 44100.0}
        got = []
        with mock.patch.object(sd, "query_devices", return_value=dev), \
                mock.patch.object(sd, "query_hostapis", return_value={"name": "Windows WASAPI"}), \
                mock.patch.object(sd, "InputStream", FakeStream):
            stream, info = ac.open_input_16k(12, lambda x, status: got.append(x))
        self.assertEqual(opened, [44100])
        self.assertTrue(info["resampled"])
        stream.callback(sine(44100, 1.0)[:, None], 44100, None, None)
        self.assertAlmostEqual(len(got[0]), 16000, delta=2)

    def test_reports_clear_error_when_nothing_opens(self):
        import sounddevice as sd

        def boom(**kw):
            raise sd.PortAudioError("Device unavailable")

        dev = {"name": "Mic X", "hostapi": 0, "default_samplerate": 48000.0}
        with mock.patch.object(sd, "query_devices", return_value=dev), \
                mock.patch.object(sd, "query_hostapis", return_value={"name": "MME"}), \
                mock.patch.object(sd, "InputStream", side_effect=boom):
            with self.assertRaises(ac.AudioError) as ctx:
                ac.open_input_16k(3, lambda x, s: None)
        self.assertIn("Mic X", str(ctx.exception))


class RecorderClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wavsink_fill_gap_respects_tolerance(self):
        sink = _WavSink(self.tmp / "a.wav", 16000, 1)
        self.assertEqual(sink.fill_gap(0.05, 0), 0)  # 50 ms: dentro de la tolerancia
        self.assertEqual(sink.fill_gap(1.0, 1600), 16000 - 1600)
        sink.write(np.zeros(1600, "<i2").tobytes())
        self.assertEqual(sink.frames, 16000)
        sink.close()

    def test_mic_stall_is_padded_and_tracks_end_equal(self):
        """El bug medido: PyAudio (o cualquier cosa que retenga Python) hacia
        perder ~1,6 s del microfono y "Yo" quedaba 1,6 s adelantado."""
        blocks = {}

        class FakeStream:
            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

        def fake_open(device, on_block, block_ms=100):
            blocks["cb"] = on_block
            return FakeStream(), {"name": "fake", "opened_rate": 16000, "resampled": False}

        r = DualRecorder(self.tmp / "rec", capture_system=False, loopback_device="")
        with mock.patch.object(ac, "open_input_16k", fake_open):
            r.start()
            blocks["cb"](np.full(1600, 0.1, np.float32), None)  # 100 ms de "voz"
            time.sleep(0.6)  # el microfono no entrega nada: "se colgo"
            blocks["cb"](np.full(1600, 0.1, np.float32), None)
            time.sleep(0.1)
            elapsed = r.elapsed
            r.stop()
        with wave.open(str(self.tmp / "rec" / "me.wav")) as w:
            dur = w.getnframes() / 16000
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2")
        self.assertAlmostEqual(dur, elapsed, delta=0.05)
        # el segundo bloque quedo en su sitio (~0,7 s), no pegado al primero
        loud = np.nonzero(x)[0] / 16000
        self.assertGreater(loud[-1], 0.55)

    def test_them_feed_is_boosted_but_wav_is_raw(self):
        r = DualRecorder(self.tmp / "rec", capture_system=False, loopback_device="")
        fed = []
        r.on_audio = lambda track, x, rate: fed.append(x)
        quiet = (sine(48000, 2.0, amp=0.013) * 32767).astype("<i2")
        stereo = np.repeat(quiet, 2)
        r._them = _WavSink(self.tmp / "them.wav", 48000, 2)
        r._t0 = time.monotonic()
        # misma logica que el callback real del loopback (sin PyAudio)
        for b in in_blocks(stereo, 2048):
            mono = b.reshape(-1, 2).mean(axis=1).astype(np.float32) / 32768.0
            r._them.write(b.tobytes())
            fed.append(r.gain(mono, 48000))
        r._them.close()
        self.assertGreater(float(np.abs(fed[-1]).max()), 0.25)
        with wave.open(str(self.tmp / "them.wav")) as w:
            raw = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768
        self.assertLess(float(np.abs(raw).max()), 0.02)


class MicVerdictTests(unittest.TestCase):
    def test_verdicts(self):
        from speak import app

        self.assertEqual(app._mic_verdict(0.0, 0), app.BLOCKED)
        # Medido: la webcam funcionando, en silencio, pica 0,00008
        self.assertEqual(app._mic_verdict(0.00008, 22334), app.NO_VOICE)
        self.assertEqual(app._mic_verdict(0.03, 1000), app.LOW)
        self.assertEqual(app._mic_verdict(0.4, 1000), app.GOOD)
        self.assertEqual(app._mic_verdict(0.99, 1000), app.CLIPPED)

    def test_recommendation_prefers_good_then_louder(self):
        from speak import app

        results = [(0.05, 11, "Intel", app.LOW), (0.3, 12, "Webcam", app.GOOD),
                   (0.6, 13, "Headset", app.GOOD), (0.0, 14, "Off", app.BLOCKED)]
        self.assertEqual(app.recommend_mic(results)[0], 13)
        self.assertIsNone(app.recommend_mic([(0.0, 1, "x", app.BLOCKED), (0.001, 2, "y", app.NO_VOICE)]))

    def test_report_file_and_no_keyboard(self):
        """--mics sin teclado (EOF) no revienta y deja el informe en disco."""
        from speak import app
        from speak.config import Config

        tmp = Path(tempfile.mkdtemp())
        try:
            class NoAudioSTT:
                def warmup(self):
                    pass

                def transcribe(self, *a):
                    return "hola"

            def fake_open(dev, on_block, block_ms=100):
                class S:
                    def __enter__(self_):
                        on_block(np.full(1600, 0.4, np.float32), None)
                        return self_

                    def __exit__(self_, *a):
                        return False
                return S(), {"opened_rate": 16000, "resampled": False}

            import sounddevice as sd

            devs = [{"name": "Mic A", "hostapi": 0, "max_input_channels": 1, "default_samplerate": 16000.0}]
            with mock.patch.object(app, "DATA_DIR", tmp), \
                    mock.patch("speak.transcriber.make_stt", return_value=NoAudioSTT()), \
                    mock.patch.object(ac, "open_input_16k", fake_open), \
                    mock.patch.object(sd, "query_hostapis", return_value=[{"name": "Windows WASAPI"}]), \
                    mock.patch.object(sd, "query_devices", return_value=devs), \
                    mock.patch("builtins.input", side_effect=EOFError), \
                    mock.patch.object(app.time, "sleep"):
                code = app.mics(Config(), seconds=1)
            self.assertEqual(code, 0)
            report = (tmp / "mic_test.txt").read_text(encoding="utf-8")
            self.assertIn("MIC_DEVICE=0", report)
            self.assertIn("bien", report)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
