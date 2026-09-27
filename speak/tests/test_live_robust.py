"""Notas en vivo con la CPU ocupada: prioridad, lotes, relleno por hora de
llegada, y cuando dispara el copiloto. Sin microfono, red ni modelos."""

from __future__ import annotations

import threading
import time
import unittest

import numpy as np

from speak.notes.pipeline import ME, THEM, Transcript
from speak.transcriber import Segment, SpeechToText

SR = 16000


def tone(seconds, amp=0.2):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class GatedSTT(SpeechToText):
    """Cada llamada espera a que la prueba la suelte; registra lo que recibe."""

    def __init__(self):
        self.calls = []  # duracion del audio de cada llamada
        self.gate = threading.Semaphore(0)

    def transcribe(self, audio, sample_rate, prompt=""):
        self.calls.append(round(len(audio) / sample_rate, 1))
        self.gate.acquire()
        return f"texto {len(self.calls)}"

    def transcribe_file(self, path):
        return []


class LiveTranscriberTests(unittest.TestCase):
    def make(self):
        from speak.notes.live import LiveTranscriber

        self.stt = GatedSTT()
        self.out = []
        return LiveTranscriber(self.stt, lambda who, ev: self.out.append((who, ev.start, ev.end, ev.text)))

    def test_them_first_and_same_turn_batched(self):
        lt = self.make()
        lt.submit(ME, tone(1.0), 0.0, 1.0)  # arranca ya (no hay nada mas)
        self.assertTrue(wait_for(lambda: len(self.stt.calls) == 1))
        # Mientras Whisper esta ocupado llegan: otra de Yo y tres de Ellos
        # (dos del mismo turno, una mucho despues).
        lt.submit(ME, tone(1.0), 2.0, 3.0)
        lt.submit(THEM, tone(1.0), 4.0, 5.0)
        lt.submit(THEM, tone(2.0), 5.5, 7.5)
        lt.submit(THEM, tone(1.0), 20.0, 21.0)
        self.assertEqual(lt.pending(THEM), 3)
        self.assertEqual(lt.pending(ME), 2)  # la de la cola + la que se transcribe
        for _ in range(4):
            self.stt.gate.release()
        lt.close()
        lt.join(5)
        self.assertEqual([o[0] for o in self.out], [ME, THEM, THEM, ME])
        # Ellos 4-7.5 en UNA llamada (1 s + hueco + 2 s), la de las 20 s aparte.
        self.assertEqual(self.out[1][1:3], (4.0, 7.5))
        self.assertEqual(self.stt.calls[1], 3.3)
        self.assertEqual(self.out[2][1:3], (20.0, 21.0))
        self.assertEqual(lt.pending(THEM), 0)

    def test_batch_is_capped(self):
        from speak.notes.live import LiveTranscriber

        stt = GatedSTT()
        lt = LiveTranscriber(stt, lambda who, ev: None, max_batch_s=5.0)
        lt.submit(THEM, tone(1.0), 0.0, 1.0)
        self.assertTrue(wait_for(lambda: len(stt.calls) == 1))
        for k in range(4):  # 4 frases de 2 s seguidas: 8 s > tope de 5 s
            lt.submit(THEM, tone(2.0), 2.0 + 2.2 * k, 4.0 + 2.2 * k)
        for _ in range(5):
            stt.gate.release()
        lt.close()
        lt.join(5)
        self.assertEqual(len(stt.calls), 3)  # 1 + (2+2) + (2+2)
        self.assertTrue(all(c <= 5.0 for c in stt.calls))

    def test_close_discard_drops_queue(self):
        lt = self.make()
        lt.submit(THEM, tone(1.0), 0.0, 1.0)
        self.assertTrue(wait_for(lambda: len(self.stt.calls) == 1))
        lt.submit(THEM, tone(1.0), 30.0, 31.0)
        lt.close(discard=True)
        self.stt.gate.release()
        lt.join(5)
        self.assertEqual(len(self.stt.calls), 1)


class ArrivalPaddingTests(unittest.TestCase):
    def test_late_processing_does_not_split_phrases(self):
        """Con el hilo atrasado (reloj muy adelante), los bloques en cola no
        deben recibir silencio falso entre ellos."""
        from speak.audio_capture import Utterance
        from speak.notes.live import _LiveTrack

        utts = []
        clock = [100.0]  # la CPU se atraso: el reloj va 100 s por delante
        track = _LiveTrack(THEM, lambda who, u: utts.append(u), lambda: clock[0])
        x = np.concatenate([np.zeros(SR // 2, np.float32), tone(2.0), np.zeros(SR, np.float32)])
        x48 = np.repeat(x, 3)
        for i in range(0, len(x48), 1024):
            block = x48[i:i + 1024]
            if np.any(block):  # como WASAPI: nada durante el silencio
                track.push(block, 48000, (i + len(block)) / 48000)
        track.close(timeout=5)
        self.assertEqual(len(utts), 1)
        self.assertIsInstance(utts[0], Utterance)
        self.assertAlmostEqual(utts[0].end - utts[0].start, 2.2, delta=0.5)  # tono + pre-roll


class CopilotTriggerTests(unittest.TestCase):
    def make(self, segs, now, me_spoke=lambda t: False):
        from speak.llm_client import FakeLLM
        from speak.notes.copilot import Copilot

        self.clock = [now]
        return Copilot(FakeLLM("ok"), None, "", snapshot=lambda: Transcript(list(segs), "t"),
                       now=lambda: self.clock[0], mode="venta", me_spoke_since=me_spoke)

    def test_whisper_question_mark_on_a_fragment_waits_longer(self):
        cop = self.make([Segment(1, 3, "And what would the price be for?", THEM)], now=4.6)
        self.assertIsNone(cop.step())  # 1,6 s: con "?" normal ya dispararia; aqui no
        self.clock[0] = 6.2
        self.assertIsNotNone(cop.step())

    def test_complete_question_keeps_fast_path(self):
        cop = self.make([Segment(1, 3, "What is the timeline for the rollout?", THEM)], now=4.3)
        self.assertIsNotNone(cop.step())

    def test_my_voice_closes_the_question_before_whisper(self):
        spoke = [False]
        cop = self.make([Segment(1, 3, "How long would the audit take, and", THEM)], now=3.5,
                        me_spoke=lambda t: spoke[0] and t <= 3.4)
        self.assertIsNone(cop.step())  # frase colgada: esperaria 3 s
        spoke[0] = True  # empece a responder (VAD), mi texto aun no llega
        self.assertIsNotNone(cop.step())

    def test_seems_unfinished(self):
        from speak.notes.copilot import seems_unfinished

        self.assertTrue(seems_unfinished("And what would the price be for?"))
        self.assertTrue(seems_unfinished("Tell me about the steam audit and"))
        self.assertFalse(seems_unfinished("Can you tell me about PCI?"))
        self.assertFalse(seems_unfinished("¿Cuánto cuesta la auditoría?"))


class SpokeSinceTests(unittest.TestCase):
    def test_vad_times_are_tracked(self):
        from speak.notes.live import LiveNotes

        class Silent(SpeechToText):
            def transcribe(self, audio, sample_rate, prompt=""):
                return ""

            def transcribe_file(self, path):
                return []

        clock = [0.0]
        live = LiveNotes(Silent(), None, clock=lambda: clock[0])
        live.start()
        x = np.concatenate([np.zeros(SR, np.float32), tone(1.0), np.zeros(SR, np.float32)])
        for i in range(0, len(x), 1600):
            live.push("me", x[i:i + 1600], 16000, (i + 1600) / 16000)
        live.stop(wait=True)
        self.assertTrue(live.spoke_since(ME, 0.5))
        self.assertFalse(live.spoke_since(ME, 2.5))
        self.assertFalse(live.spoke_since(THEM, 0.0))


if __name__ == "__main__":
    unittest.main()
