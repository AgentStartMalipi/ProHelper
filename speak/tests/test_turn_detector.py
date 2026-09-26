"""Pruebas del detector de turnos, sin microfono ni modelo.

`run_script` simula la linea de tiempo real: voz → fin de frase → ticks de
silencio cada 30 ms, con el texto de la frase llegando 300 ms despues (la
latencia tipica de faster-whisper en CPU). Asi se prueba tambien que el turno
no se cierra mientras la transcripcion esta pendiente.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from speak.turn_detector import (
    TurnComplete,
    TurnConfig,
    TurnDetector,
    TurnReopened,
    TurnState,
    ends_incomplete,
    question_kind,
    segment_turns,
)

TICK_MS = 30


def run_script(det: TurnDetector, script, stt_latency_ms: int = 300, t0: float = 0.0):
    """script: lista de ("say", texto, duracion_s) y ("pause", ms)."""
    events = []
    t = t0
    pending: tuple[str, float, float] | None = None
    for step in script:
        if step[0] == "say":
            _, text, dur = step
            if pending:  # llego tarde: se entrega antes de la nueva voz
                events += det.add_text(pending[0], pending[1], pending[2], t)
                pending = None
            events += det.speech_started(t)
            start = t
            t += dur
            events += det.utterance_ended(t)
            pending = (text, start, t)
        else:
            _, ms = step
            elapsed = 0
            while elapsed < ms:
                elapsed += TICK_MS
                t += TICK_MS / 1000
                if pending and elapsed >= stt_latency_ms:
                    events += det.add_text(pending[0], pending[1], pending[2], t)
                    pending = None
                events += det.silence(t, elapsed)
    return events, t


def completes(events):
    return [e for e in events if isinstance(e, TurnComplete)]


class TurnDetectorTests(unittest.TestCase):
    def setUp(self):
        self.det = TurnDetector(TurnConfig(silence_threshold_ms=900, max_silence_ms=3000))

    def test_short_question(self):
        events, _ = run_script(self.det, [("say", "What is a hash map?", 1.2), ("pause", 1500)])
        done = completes(events)
        self.assertEqual(len(done), 1)
        self.assertTrue(done[0].is_question)
        self.assertEqual(done[0].kind, "question")
        self.assertEqual(self.det.state, TurnState.QUESTION_COMPLETE)

    def test_short_question_closes_before_generic_threshold(self):
        # Pregunta redonda: basta 0.8 x umbral (720 ms), no los 900 completos.
        events, _ = run_script(self.det, [("say", "What is a hash map?", 1.2), ("pause", 800)])
        self.assertEqual(len(completes(events)), 1)

    def test_multi_sentence_question_is_one_turn(self):
        events, _ = run_script(self.det, [
            ("say", "Tell me about a time you disagreed with your manager.", 3.0),
            ("pause", 1000),  # mas que el umbral base, menos que el de apertura
            ("say", "What happened and how did you handle it?", 2.0),
            ("pause", 1500),
        ])
        done = completes(events)
        self.assertEqual(len(done), 1, done)
        self.assertIn("disagreed", done[0].text)
        self.assertIn("how did you handle it", done[0].text)
        self.assertNotIn(True, [isinstance(e, TurnReopened) for e in events])

    def test_pause_inside_question_with_ellipsis(self):
        events, _ = run_script(self.det, [
            ("say", "Given an array of integers, find the maximum...", 2.5),
            ("pause", 1400),
            ("say", "subarray whose sum is less than k.", 1.8),
            ("pause", 1500),
        ])
        done = completes(events)
        self.assertEqual(len(done), 1, done)
        self.assertIn("subarray whose sum is less than k", done[0].text)
        self.assertEqual(done[0].kind, "request")

    def test_pause_inside_question_without_ellipsis(self):
        # Whisper a veces cierra con punto: "maximum" sigue pidiendo sustantivo.
        events, _ = run_script(self.det, [
            ("say", "Given an array of integers, find the maximum.", 2.5),
            ("pause", 1400),
            ("say", "Subarray whose sum is less than k.", 1.8),
            ("pause", 1500),
        ])
        self.assertEqual(len(completes(events)), 1)

    def test_given_without_task_waits(self):
        events, _ = run_script(self.det, [
            ("say", "Given a binary tree.", 1.5),
            ("pause", 1500),
        ])
        self.assertEqual(completes(events), [])

    def test_follow_up(self):
        run_script(self.det, [
            ("say", "How would you design a rate limiter?", 2.0), ("pause", 1500),
        ])
        self.det.reset()
        events, _ = run_script(self.det, [
            ("say", "And what if it has to work across regions?", 2.0), ("pause", 1500),
        ], t0=30.0)
        done = completes(events)
        self.assertEqual(len(done), 1)
        self.assertTrue(done[0].is_follow_up)

    def test_bare_why_is_follow_up(self):
        run_script(self.det, [("say", "Which database would you pick?", 1.5), ("pause", 1500)])
        self.det.reset()
        events, _ = run_script(self.det, [("say", "Why?", 0.5), ("pause", 1500)], t0=30.0)
        done = completes(events)
        self.assertTrue(done and done[0].is_follow_up and done[0].is_question)

    def test_no_follow_up_without_previous_question(self):
        events, _ = run_script(self.det, [("say", "Why do you want this role?", 1.5),
                                          ("pause", 1500)])
        self.assertFalse(completes(events)[0].is_follow_up)

    def test_thinking_aloud_does_not_close_early(self):
        events, _ = run_script(self.det, [
            ("say", "Hmm, let me think. So maybe we could use a", 3.0),
            ("pause", 1800),
        ])
        self.assertEqual(completes(events), [], "cerro con la frase colgada")
        events, _ = run_script(self.det, [
            ("say", "heap to keep the top k elements.", 2.0), ("pause", 1200),
        ], t0=10.0)
        done = completes(events)
        self.assertEqual(len(done), 1)
        self.assertIn("maybe we could use a heap", done[0].text)
        self.assertFalse(done[0].is_question)

    def test_trailing_filler_needs_longer_silence(self):
        events, _ = run_script(self.det, [("say", "I would start with a queue, um", 2.0),
                                          ("pause", 1200)])
        self.assertEqual(completes(events), [])

    def test_only_filler_is_discarded(self):
        events, _ = run_script(self.det, [("say", "Umm.", 0.6), ("pause", 3300)])
        self.assertEqual(completes(events), [])
        self.assertEqual(self.det.state, TurnState.LISTENING)

    def test_statement_is_not_a_question(self):
        events, _ = run_script(self.det, [("say", "Okay, great, thanks for sharing that.", 2.0),
                                          ("pause", 1500)])
        done = completes(events)
        self.assertEqual(len(done), 1)
        self.assertFalse(done[0].is_question)
        self.assertEqual(done[0].kind, "statement")

    def test_answer_starting_with_what_is_statement(self):
        self.assertEqual(question_kind("What I did was refactor the payment service."),
                         "statement")

    def test_reopen_when_speaker_resumes(self):
        events, _ = run_script(self.det, [
            ("say", "Tell me about your last project.", 2.0),
            ("pause", 1000),  # cierra a ~720 ms
            ("say", "Especially the architecture decisions.", 2.0),
            ("pause", 1500),
        ])
        self.assertTrue(any(isinstance(e, TurnReopened) for e in events))
        done = completes(events)
        self.assertEqual(len(done), 2)
        self.assertIn("last project", done[-1].text)
        self.assertIn("architecture", done[-1].text)

    def test_waits_for_pending_transcription(self):
        # STT lento (2.5 s): el silencio ya bastaba, pero sin texto no se cierra.
        events, _ = run_script(self.det, [("say", "What is a heap?", 1.0), ("pause", 2000)],
                               stt_latency_ms=2500)
        self.assertEqual(completes(events), [])
        self.assertEqual(self.det.state, TurnState.POSSIBLE_END)

    def test_max_silence_always_closes(self):
        events, _ = run_script(self.det, [("say", "We could use the", 1.0), ("pause", 3100)])
        self.assertEqual(len(completes(events)), 1)

    def test_spanish(self):
        events, _ = run_script(self.det, [("say", "¿Cómo manejarías un conflicto con tu jefe?", 2.0),
                                          ("pause", 1500)])
        self.assertTrue(completes(events)[0].is_question)
        self.assertEqual(question_kind("Cuéntame de un proyecto difícil."), "request")
        self.assertEqual(question_kind("Como te decía, eso salió bien."), "statement")


class TextAnalysisTests(unittest.TestCase):
    def test_incomplete_endings(self):
        self.assertTrue(ends_incomplete("find the longest"))
        self.assertTrue(ends_incomplete("we store it in the"))
        self.assertTrue(ends_incomplete("first we sort,"))
        self.assertFalse(ends_incomplete("How would you handle that?"))
        self.assertFalse(ends_incomplete("I would use a hash map."))

    def test_kinds(self):
        self.assertEqual(question_kind("Walk me through your resume."), "request")
        self.assertEqual(question_kind("Design a URL shortener."), "request")
        self.assertEqual(question_kind("That sounds good, right?"), "question")
        self.assertEqual(question_kind("I led the migration last year."), "statement")


@dataclass
class Seg:
    speaker: str
    start: float
    end: float
    text: str


class OfflineTests(unittest.TestCase):
    def test_segment_turns_merges_and_flags(self):
        segs = [
            Seg("Ellos", 0.0, 3.0, "Tell me about a time you failed."),
            Seg("Ellos", 3.5, 5.0, "What did you learn?"),
            Seg("Yo", 6.0, 20.0, "Sure. In my last job we missed a launch date."),
            Seg("Ellos", 21.0, 22.0, "Why?"),
            Seg("Yo", 23.0, 30.0, "Because we underestimated the migration."),
        ]
        turns = segment_turns(segs)
        self.assertEqual(len(turns), 4)
        self.assertTrue(turns[0].is_question)
        self.assertIn("What did you learn", turns[0].text)
        self.assertFalse(turns[1].is_question)
        self.assertTrue(turns[2].is_follow_up)


if __name__ == "__main__":
    unittest.main()
