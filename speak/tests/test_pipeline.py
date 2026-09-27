"""Pruebas de las demas piezas: audio, clasificador, contexto, secciones,
simulador de punta a punta (con dobles) y Notas de llamada. Nada de red,
microfono ni modelos reales."""

from __future__ import annotations

import time
import unittest

import numpy as np

from speak import audio_capture as ac
from speak.answer_generator import evaluation_prompt, extract_score, split_sections
from speak.config import Config
from speak.context_manager import ContextManager
from speak.llm_client import LLMClient
from speak.notes.analyzer import notes_prompt, pair_questions
from speak.notes.pipeline import Transcript, dedupe_echo, parse_transcript_text
from speak.question_classifier import QType, classify
from speak.simulator import Listener, Phase, Simulator
from speak.transcriber import Segment, SpeechToText, looks_like_hallucination
from speak.turn_detector import segment_turns

SR = 16000


def tone(seconds: float, amp: float = 0.2) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return (np.random.default_rng(0).normal(0, 0.001, int(SR * seconds))).astype(np.float32)


class SegmenterTests(unittest.TestCase):
    def feed(self, audio: np.ndarray):
        events = []
        seg = ac.UtteranceSegmenter(SR, ac.EnergyVAD(), events.append)
        block = int(SR * 0.03)
        for i in range(0, len(audio), block):
            seg.feed(audio[i:i + block])
        seg.flush()
        return events

    def test_two_phrases_split_on_gap(self):
        audio = np.concatenate([silence(0.5), tone(1.0), silence(0.6), tone(0.8), silence(0.5)])
        utts = [e for e in self.feed(audio) if isinstance(e, ac.Utterance)]
        self.assertEqual(len(utts), 2)
        self.assertAlmostEqual(utts[0].start, 0.3, delta=0.1)  # incluye ~200 ms de pre-roll

    def test_short_pause_stays_in_one_phrase(self):
        audio = np.concatenate([silence(0.5), tone(0.8), silence(0.15), tone(0.8), silence(0.6)])
        utts = [e for e in self.feed(audio) if isinstance(e, ac.Utterance)]
        self.assertEqual(len(utts), 1)

    def test_click_is_ignored(self):
        audio = np.concatenate([silence(0.5), tone(0.05), silence(0.6)])
        self.assertEqual([e for e in self.feed(audio) if isinstance(e, ac.Utterance)], [])

    def test_silence_ticks_grow(self):
        audio = np.concatenate([silence(0.3), tone(0.6), silence(1.0)])
        ticks = [e.silence_ms for e in self.feed(audio) if isinstance(e, ac.SilenceTick)]
        self.assertGreaterEqual(max(ticks), 800)


class ClassifierTests(unittest.TestCase):
    def test_types(self):
        cases = {
            "Tell me about a time you disagreed with your manager.": QType.BEHAVIORAL,
            "Given an array of integers, return the length of the longest increasing subarray.": QType.CODING,
            "Design a URL shortener that handles millions of users.": QType.SYSTEM_DESIGN,
            "What is the difference between a process and a thread?": QType.TECHNICAL_CONCEPT,
            "Tell me about yourself.": QType.GENERAL,
            "Why Amazon?": QType.GENERAL,
        }
        for text, expected in cases.items():
            self.assertEqual(classify(text).qtype, expected, text)

    def test_follow_up_and_clarification(self):
        self.assertEqual(classify("Why?", is_follow_up=True).qtype, QType.FOLLOW_UP)
        self.assertEqual(classify("Can I assume the array is sorted?", from_candidate=True).qtype,
                         QType.CLARIFICATION)


class ContextTests(unittest.TestCase):
    def test_compact_context(self):
        ctx = ContextManager(window=2, cv_max=100)
        ctx.profile.cv = "x " * 500
        for i in range(6):
            ctx.start_exchange(f"Question number {i} about hash maps?", "TECHNICAL_CONCEPT")
            ctx.record_answer(f"answer {i} " * 50)
            ctx.record_feedback("Score: 3/5", "model", "3/5")
        text = ctx.build()
        self.assertIn("Earlier in this session", text)
        self.assertIn("Question number 0", text)  # resumida en una linea
        self.assertNotIn("answer 0 answer 0", text)  # pero sin su respuesta
        self.assertIn("answer 5", text)
        self.assertIn("hash maps", text)
        self.assertLess(len(ctx.profile_block()), 250)  # CV recortado

    def test_follow_up_prompt_reuses_previous_answer(self):
        ctx = ContextManager()
        ctx.start_exchange("Design a rate limiter.", QType.SYSTEM_DESIGN.value)
        ctx.record_feedback("Score: 4/5", "PREVIOUS-MODEL-ANSWER", "4/5")
        ctx.start_exchange("What if it must work across regions?", QType.FOLLOW_UP.value)
        ctx.record_answer("I would use a global redis")
        p = evaluation_prompt(ctx, QType.FOLLOW_UP)
        self.assertIn("PREVIOUS-MODEL-ANSWER", p.user)
        self.assertIn("MODIFY", p.system)
        self.assertIn("Scaling considerations", p.system)  # hereda estructura de SYSTEM_DESIGN


class SectionTests(unittest.TestCase):
    def test_split_partial_stream(self):
        md = "## FEEDBACK\nScore: 4/5\n- good\n## QUICK ANSWER\n- a\n- b\n## DETAILED ANS"
        s = split_sections(md)
        self.assertIn("good", s["FEEDBACK"])
        self.assertIn("- b", s["QUICK ANSWER"])
        self.assertEqual(extract_score(s["FEEDBACK"]), "4/5")

    def test_hallucination_filter(self):
        self.assertTrue(looks_like_hallucination("Thank you.", 1.0))
        self.assertFalse(looks_like_hallucination("Thank you.", 5.0))


# --- simulador de punta a punta ----------------------------------------------


class FakeCapture:
    def __init__(self, on_event, **kwargs):
        self.on_event = on_event
        self.running = False
        self.muted = True

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def mute(self, m):
        self.muted = m

    def flush_now(self):
        pass


class ScriptedSTT(SpeechToText):
    def __init__(self, texts):
        self.texts = list(texts)

    def transcribe(self, audio, sample_rate, prompt=""):
        return self.texts.pop(0) if self.texts else ""

    def transcribe_file(self, path):
        return []


class ScriptedLLM(LLMClient):
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def stream(self, system, prompt, cancel=None, images=None):
        self.prompts.append((system, prompt))
        self.images = getattr(self, "images", []) + list(images or [])
        reply = self.replies.pop(0) if self.replies else "ok"
        for i in range(0, len(reply), 5):
            yield reply[i:i + 5]


class InstantSpeaker:
    culture = "en-US"

    def speak(self, text, on_done=None):
        if on_done:
            on_done()

    def stop(self):
        pass


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


EVAL = "## FEEDBACK\nScore: 3/5\n- ok\n## QUICK ANSWER\n- sort first\n## DETAILED ANSWER\n**Approach** two pointers"


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        # Las sesiones van a una carpeta temporal, no a speak/data/sessions
        # (ahi estan las del usuario).
        import tempfile
        from pathlib import Path
        from unittest import mock

        import speak.simulator as sim

        self._tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(sim, "DATA_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def make(self, stt_texts, llm_replies):
        cfg = Config()
        cfg.ANSWER_SILENCE = 1200
        self.events = {"eval": [], "clar": [], "question": []}
        listener = Listener(
            evaluation=lambda s, final: final and self.events["eval"].append(s),
            clarification=lambda a, r: self.events["clar"].append((a, r)),
            question=lambda t, q: self.events["question"].append((t, q)),
        )
        self.llm = ScriptedLLM(llm_replies)
        sim = Simulator(cfg, self.llm, ScriptedSTT(stt_texts), listener,
                        speaker=InstantSpeaker(), capture_factory=FakeCapture)
        self.addCleanup(sim.shutdown)
        return sim

    def say(self, sim, t, dur, pause_ms):
        sim._post("audio", ac.SpeechStarted(t))
        sim._post("audio", ac.Utterance(np.zeros(int(SR * dur), np.float32), t, t + dur))
        t += dur
        for ms in range(30, pause_ms + 1, 30):
            sim._post("audio", ac.SilenceTick(t + ms / 1000, ms))
            time.sleep(0.001)  # deja que el STT falso entregue en medio
        return t + pause_ms / 1000

    def test_question_answer_evaluation(self):
        sim = self.make(
            ["I would sort the array and use two pointers."],
            ["Given an array of integers, find two numbers that add up to a target.", EVAL],
        )
        sim.start()
        self.assertTrue(wait_for(lambda: sim.phase == Phase.LISTENING))
        self.assertEqual(self.events["question"][0][1], "CODING")
        self.say(sim, 1.0, 2.0, 1500)
        self.assertTrue(wait_for(lambda: sim.phase == Phase.REVIEW), sim.phase)
        self.assertIn("two pointers", self.events["eval"][-1]["DETAILED ANSWER"])
        self.assertEqual(sim.ctx.current.score, "3/5")
        self.assertIn("sort the array", sim.ctx.current.answer)
        # El evaluador recibio tu respuesta, y la pregunta no se evaluo antes.
        self.assertIn("sort the array", self.llm.prompts[1][1])

    def test_clarification_then_answer(self):
        sim = self.make(
            ["Can I assume the array is sorted?", "Then I would use two pointers from both ends."],
            ["Given an array, find a pair with sum k.", "Yes, you can assume it's sorted.", EVAL],
        )
        sim.start()
        self.assertTrue(wait_for(lambda: sim.phase == Phase.LISTENING))
        t = self.say(sim, 1.0, 1.5, 1200)
        self.assertTrue(wait_for(lambda: len(self.events["clar"]) == 1))
        self.assertTrue(wait_for(lambda: sim.phase == Phase.LISTENING))
        self.say(sim, t + 1, 2.0, 1500)
        self.assertTrue(wait_for(lambda: sim.phase == Phase.REVIEW), sim.phase)
        ex = sim.ctx.current
        self.assertEqual(ex.clarifications[0][1], "Yes, you can assume it's sorted.")
        self.assertIn("two pointers", ex.answer)

    def test_done_button_forces_evaluation(self):
        sim = self.make(["I think I would use a hash map"],
                        ["What is a hash map?", EVAL])
        sim.start()
        self.assertTrue(wait_for(lambda: sim.phase == Phase.LISTENING))
        self.say(sim, 1.0, 1.0, 300)  # termina colgado y sin silencio suficiente
        time.sleep(0.2)
        self.assertEqual(sim.phase, Phase.LISTENING)
        sim.done_answering()
        self.assertTrue(wait_for(lambda: sim.phase == Phase.REVIEW), sim.phase)


# --- Notas de llamada ---------------------------------------------------------


class NotesTests(unittest.TestCase):
    def test_parse_plain_transcript(self):
        tr = parse_transcript_text(
            "[00:05] Ana: Tell me about a time you failed.\n"
            "[00:09] Yo: Sure, in 2023 we missed a launch.\n"
            "we recovered in two weeks.\n"
            "[01:10] Ana: What would you do differently?\n")
        self.assertEqual(len(tr.segments), 3)
        self.assertTrue(tr.has_timing)
        self.assertIn("recovered", tr.segments[1].text)
        self.assertAlmostEqual(tr.segments[2].start, 70.0)

    def test_parse_vtt(self):
        vtt = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Ana Perez>How are you?</v>\n\n"
               "2\n00:00:04.000 --> 00:00:06.000\n<v Juan>Good, thanks.</v>\n")
        tr = parse_transcript_text(vtt)
        self.assertEqual([s.speaker for s in tr.segments], ["Ana Perez", "Juan"])

    def test_dedupe_echo(self):
        them = [Segment(10, 14, "Can you walk me through your last project", "Ellos")]
        me = [Segment(10.2, 14.1, "can you walk me through your last project", "Yo"),
              Segment(15, 20, "Sure, I built a payments pipeline", "Yo")]
        kept = dedupe_echo(me, them)
        self.assertEqual(len(kept), 1)
        self.assertIn("payments", kept[0].text)

    def test_dedupe_partial_echo_but_not_real_answers(self):
        # Caso real (parlantes, sin audifonos): el micro capto un trozo.
        them = [Segment(3.3, 7.5, "How long would the energy audit take, and what savings can we expect?",
                        "Ellos")]
        me = [Segment(3.7, 5.0, "How long would the...", "Yo"),
              Segment(4.0, 4.6, "Yes.", "Yo"),  # corto: no se toca
              Segment(7.0, 9.0, "It takes about eight weeks from the deposit.", "Yo")]
        kept = [s.text for s in dedupe_echo(me, them)]
        self.assertNotIn("How long would the...", kept)
        self.assertIn("Yes.", kept)
        self.assertIn("It takes about eight weeks from the deposit.", kept)

    def test_split_whisper_segment_on_word_gaps(self):
        from types import SimpleNamespace as W

        from speak.transcriber import _split_on_gaps

        seg = W(start=5.0, end=25.0, text=" What was your role? Interesting.", words=[
            W(start=5.0, end=5.3, word=" What"), W(start=5.3, end=5.5, word=" was"),
            W(start=5.5, end=5.8, word=" your"), W(start=5.8, end=6.2, word=" role?"),
            W(start=24.0, end=24.6, word=" Interesting."),
        ])
        parts = _split_on_gaps(seg, 0.8)
        self.assertEqual([p.text for p in parts], ["What was your role?", "Interesting."])
        self.assertAlmostEqual(parts[1].start, 24.0)

    def test_render_groups_turns(self):
        from speak.notes.pipeline import render

        tr = Transcript([Segment(0, 2, "Hi.", "Ellos"), Segment(2.5, 4, "How are you?", "Ellos"),
                         Segment(5, 6, "Good.", "Yo")], source="t")
        self.assertEqual(render(tr), "[00:00] Ellos: Hi. How are you?\n[00:05] Yo: Good.")

    def test_unanswered_question_and_prompt(self):
        tr = Transcript([
            Segment(0, 3, "How do you handle on-call incidents?", "Ellos"),
            Segment(4, 9, "I follow the runbook and escalate.", "Yo"),
            Segment(10, 12, "What's the salary range for this role?", "Yo"),
        ], source="t")
        qas = pair_questions(segment_turns(tr.segments))
        self.assertEqual(len(qas), 2)
        self.assertFalse(qas[0].unanswered)
        self.assertTrue(qas[1].unanswered)
        system, user = notes_prompt(tr, "entrevista")
        self.assertIn("SIN RESPUESTA", user)
        self.assertIn("Temas para estudiar", user)


class AmplitudeSTT(SpeechToText):
    """Distingue las frases por volumen: asi no importa en que orden las
    procesen los dos hilos de transcripcion."""

    def __init__(self, by_amp):
        self.by_amp = by_amp

    def transcribe(self, audio, sample_rate, prompt=""):
        peak = float(np.max(np.abs(audio)))
        return min(self.by_amp.items(), key=lambda kv: abs(kv[0] - peak))[1]

    def transcribe_file(self, path):
        return []


class LiveNotesTests(unittest.TestCase):
    def test_resample_48k_keeps_carry(self):
        from speak.notes.live import to_16k

        out, carry = to_16k(np.ones(1024, np.float32), 48000)
        self.assertEqual((len(out), len(carry)), (341, 1))
        out, carry = to_16k(np.ones(1025, np.float32), 48000, carry)
        self.assertEqual((len(out), len(carry)), (342, 0))
        out, _ = to_16k(np.ones(441, np.float32), 44100)
        self.assertEqual(len(out), 160)

    def test_two_tracks_to_transcript_and_notes(self):
        from speak.notes.live import LiveNotes

        stt = AmplitudeSTT({0.2: "Can you walk me through the design?", 0.4: "Sure, we used a queue."})
        llm = ScriptedLLM(["# Resumen hasta ahora\n- diseño"])
        notes = []
        live = LiveNotes(stt, llm, "entrevista", refresh_s=3600, on_notes=notes.append,
                         clock=lambda: 0.0)
        live.start()
        # "Ellos" a 48 kHz en bloques como los del loopback; "Yo" a 16 kHz.
        them = np.concatenate([silence(0.3), tone(1.0, 0.2), silence(0.8)])
        them48 = np.repeat(them, 3)
        for i in range(0, len(them48), 1024):
            live.push("them", them48[i:i + 1024], 48000)
        me = np.concatenate([silence(2.1), tone(1.0, 0.4), silence(0.8)])
        for i in range(0, len(me), 1600):
            live.push("me", me[i:i + 1600], 16000)
        self.assertTrue(wait_for(lambda: len(live.snapshot().segments) == 2))
        live.refresh_now()
        self.assertTrue(wait_for(lambda: bool(live.notes)))
        tr = live.stop(wait=True)
        self.assertEqual([s.speaker for s in tr.segments], ["Ellos", "Yo"])
        self.assertIn("queue", tr.segments[1].text)
        system, user = llm.prompts[0]
        self.assertIn("still in progress", user)
        self.assertIn("do not suggest", system)
        self.assertIn("walk me through", user)
        self.assertTrue(notes and notes[-1].startswith("# Resumen"))

    def test_live_prompt_is_a_draft(self):
        from speak.notes.analyzer import live_notes_prompt

        tr = Transcript([Segment(0, 3, "How do you handle on-call incidents?", "Ellos")], source="t")
        _, user = live_notes_prompt(tr, "entrevista")
        self.assertIn("(sin respuesta)", user)
        self.assertNotIn("Temas para estudiar", user)
        self.assertNotIn("stronger answer", user)


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path

        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _zip(self, name, files):
        import zipfile

        path = self.tmp / name
        with zipfile.ZipFile(path, "w") as z:
            for n, data in files.items():
                z.writestr(n, data)
        return path

    def test_reads_docx_and_pptx(self):
        from speak.knowledge import read_document

        w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
        docx = self._zip("p.docx", {"word/document.xml":
            f'<w:document {w}><w:body><w:p><w:r><w:t>Precio: 12.000 USD</w:t></w:r></w:p>'
            f'<w:p><w:r><w:t>Plazo 8 semanas</w:t></w:r></w:p></w:body></w:document>'})
        self.assertEqual(read_document(docx), "Precio: 12.000 USD\n\nPlazo 8 semanas")
        a = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        pptx = self._zip("d.pptx", {
            "ppt/slides/slide2.xml": f'<p:sld xmlns:p="x" {a}><a:p><a:r><a:t>Caso Acme</a:t></a:r></a:p></p:sld>',
            "ppt/slides/slide10.xml": f'<p:sld xmlns:p="x" {a}><a:p><a:r><a:t>Cierre</a:t></a:r></a:p></p:sld>'})
        text = read_document(pptx)
        self.assertLess(text.index("Caso Acme"), text.index("Cierre"))  # 2 antes que 10

    def test_search_folds_accents_and_plurals(self):
        from speak.knowledge import KnowledgeBase

        (self.tmp / "precios.md").write_text(
            "La cotización del servicio de auditoría energética es 12.000 USD.", encoding="utf-8")
        (self.tmp / "equipo.txt").write_text("El equipo lo forman tres ingenieros de planta.",
                                            encoding="utf-8")
        kb = KnowledgeBase(self.tmp, self.tmp / "cache.json")
        self.assertEqual(kb.load_folder(), 2)
        hits = kb.search("cuanto cuestan las cotizaciones de auditoria?")
        self.assertEqual(hits[0].source, "precios.md")
        kb.add_text("notas cliente", "El cliente pregunto por el plazo de implementacion: 8 semanas.")
        self.assertEqual(kb.search("plazo implementación")[0].source, "notas cliente")
        # Segunda carga: sale de la cache.
        self.assertEqual(KnowledgeBase(self.tmp, self.tmp / "cache.json").load_folder(), 2)

    def test_chunks_long_text(self):
        from speak.knowledge import chunk_text

        text = "\n\n".join(f"Parrafo {i}. " + "palabra " * 40 for i in range(20))
        chunks = chunk_text(text, size=900)
        self.assertGreater(len(chunks), 3)
        self.assertTrue(all(len(c) <= 1100 for c in chunks))


class CopilotTests(unittest.TestCase):
    def make(self, segs, mode="venta", now=10.0, pending=0, reply="**Respuesta:** 12.000 USD [precios.md]"):
        from speak.knowledge import KnowledgeBase
        from speak.notes.copilot import Copilot

        self.segs = segs
        self.clock = [now]
        self.pend = [pending]
        kb = KnowledgeBase()
        kb.add_text("precios.md", "El servicio de auditoria cuesta 12.000 USD.")
        self.llm = ScriptedLLM([reply] * 5)
        self.cop = Copilot(self.llm, kb, "Cliente: Acme", snapshot=lambda: Transcript(list(self.segs), "t"),
                           now=lambda: self.clock[0], pending=lambda: self.pend[0], mode=mode)
        return self.cop

    def test_answers_question_after_silence_with_sources(self):
        cop = self.make([Segment(1, 4, "How much does the energy audit cost?", "Ellos")], now=4.5)
        self.assertIsNone(cop.step())  # 0,5 s de silencio: todavia no
        self.clock[0] = 6.0
        ans = cop.step()
        self.assertIsNotNone(ans)
        self.assertTrue(wait_for(lambda: ans.done))
        self.assertIn("12.000", ans.text)
        system, user = self.llm.prompts[0]
        self.assertIn("Never invent", system)
        self.assertIn('<source name="precios.md">', user)
        self.assertIn("Cliente: Acme", user)
        self.assertIsNone(cop.step())  # no la repite

    def test_waits_for_pending_transcription_and_incomplete_endings(self):
        cop = self.make([Segment(1, 4, "What would you recommend for the plant, and", "Ellos")], now=6.0)
        self.assertIsNone(cop.step())  # termina en "and": espera mas
        self.clock[0] = 8.0
        self.pend[0] = 1
        self.assertIsNone(cop.step())  # aun hay audio suyo sin transcribir
        self.pend[0] = 0
        self.assertIsNotNone(cop.step())

    def test_continuation_after_pause_rewrites_same_answer(self):
        cop = self.make([Segment(1, 3, "Can you tell me about pricing?", "Ellos")], now=5.0)
        first = cop.step()
        self.assertTrue(wait_for(lambda: first.done))
        # Pausa larga y sigue la misma idea: se suma y se rehace.
        self.segs.append(Segment(6, 9, "Especially for three plants in Bogota and Medellin.", "Ellos"))
        self.clock[0] = 11.0
        again = cop.step()
        self.assertIs(again, first)
        self.assertEqual(len(cop.answers), 1)
        self.assertIn("three plants", again.question)
        self.assertIn("pricing", again.question)

    def test_me_speaking_closes_the_question_at_once(self):
        cop = self.make([Segment(1, 3, "What is the timeline?", "Ellos")], now=3.3)
        self.assertIsNone(cop.step())  # 0,3 s de silencio: todavia no
        # Empiezas a responder ("So,"): no se espera el silencio, se responde
        # la pregunta de ELLOS (no lo tuyo).
        self.segs.append(Segment(3.2, 3.8, "So,", "Yo"))
        self.clock[0] = 3.9
        ans = cop.step()
        self.assertIsNotNone(ans)
        self.assertEqual(ans.question, "What is the timeline?")

    def test_statements_ignored_but_answer_now_forces(self):
        cop = self.make([Segment(1, 4, "We already work with another provider for this.", "Ellos")], now=9.0)
        self.assertIsNone(cop.step())
        cop.answer_now()
        ans = cop.step()
        self.assertTrue(ans.forced)

    def test_never_in_interview_mode(self):
        cop = self.make([Segment(1, 4, "Tell me about a time you failed.", "Ellos")], mode="entrevista",
                        now=9.0)
        self.assertFalse(cop.enabled)
        self.assertIsNone(cop.step())
        self.assertEqual(self.llm.prompts, [])

    def test_guide_goes_last_and_keeps_no_invention_rule(self):
        cop = self.make([Segment(1, 4, "How much does the audit cost?", "Ellos")], now=9.0)
        cop._guide = lambda: "Responde siempre en español y con una pregunta de vuelta."
        ans = cop.step()
        self.assertTrue(wait_for(lambda: ans.done))
        system, _ = self.llm.prompts[0]
        self.assertGreater(system.index("pregunta de vuelta"), system.index("Format:"))
        self.assertTrue(system.rstrip().endswith("not in the brief or\nsources."))

    def test_no_guide_leaves_prompt_untouched(self):
        from speak.notes.copilot import ANSWER_SYSTEM, answer_prompt

        system, _ = answer_prompt("q", "", "", "", "venta", guide="   ")
        self.assertEqual(system, ANSWER_SYSTEM.format(what="a sales / client call (the user, 'Yo', is on "
                                                           "the selling/consulting side)"))

    def test_guide_presets_and_persistence(self):
        from speak.knowledge import KnowledgeBase
        from speak.notes.copilot import PRESETS, PrepSession

        prep = PrepSession(KnowledgeBase(), mode="venta")
        prep.use_preset(PRESETS[0])
        self.assertEqual(prep.guide_name, PRESETS[0]["nombre"])
        prep.set_guide(prep.guide + "\nMenciona siempre el caso Cementos X.")
        self.assertEqual(prep.guide_name, "")  # ya no es la plantilla
        self.assertIn("Cementos X", prep.chat_prompt("hola")[0])
        again = PrepSession(KnowledgeBase())
        again.load_dict(prep.to_dict())
        self.assertEqual(again.guide, prep.guide)

    def test_prep_session_brief(self):
        from speak.knowledge import KnowledgeBase
        from speak.notes.copilot import PrepSession

        kb = KnowledgeBase()
        kb.add_text("propuesta.md", "Alcance: auditoria de vapor en 3 plantas. Precio 12.000 USD.")
        llm = ScriptedLLM(["¿Quien asiste?", "# Brief de la llamada\n## Contexto y objetivo\nAcme"])
        prep = PrepSession(kb, mode="venta")
        prep.chat(llm, "Reunion con Acme sobre la propuesta de vapor")
        self.assertEqual(len(prep.messages), 2)
        self.assertIn("propuesta.md", llm.prompts[0][1])
        brief = prep.build_brief(llm)
        self.assertTrue(brief.startswith("# Brief"))
        _, user = llm.prompts[1]
        self.assertIn("Preguntas probables", user)
        self.assertIn("Reunion con Acme", user)


DRAWIO_MODEL = """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="vpc" value="VPC prod" vertex="1" parent="1"/>
<mxCell id="api" value="API Gateway" vertex="1" parent="vpc"/>
<mxCell id="db" value="&lt;b&gt;Postgres&lt;/b&gt;&lt;br&gt;RDS" vertex="1" parent="vpc"/>
<mxCell id="e1" value="SQL/TLS" edge="1" source="api" target="db" parent="1"/>
</root></mxGraphModel>"""


class ArchitectureTests(unittest.TestCase):
    def test_drawio_plain_and_compressed(self):
        import base64
        import urllib.parse
        import zlib

        from speak.knowledge import _drawio_text

        plain = f'<mxfile><diagram name="Actual">{DRAWIO_MODEL}</diagram></mxfile>'
        text = _drawio_text(plain)
        self.assertIn("[Diagrama: Actual]", text)
        self.assertIn("- API Gateway (dentro de VPC prod)", text)
        self.assertIn("- API Gateway → Postgres RDS (SQL/TLS)", text)
        comp = zlib.compressobj(9, zlib.DEFLATED, -15)
        packed = comp.compress(urllib.parse.quote(DRAWIO_MODEL).encode()) + comp.flush()
        old = f'<mxfile><diagram name="Viejo">{base64.b64encode(packed).decode()}</diagram></mxfile>'
        self.assertIn("API Gateway → Postgres RDS", _drawio_text(old))

    def test_image_goes_to_claude_once_and_becomes_text(self):
        import shutil
        import tempfile
        from pathlib import Path

        from speak.knowledge import KnowledgeBase
        from speak.notes.copilot import attach_file

        tmp = Path(tempfile.mkdtemp())
        try:
            img = tmp / "diagrama.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            llm = ScriptedLLM(["Componentes:\n- Kafka\n- Lambda\nConexiones:\n- Kafka → Lambda"])
            kb = KnowledgeBase()
            name = attach_file(kb, img, lambda: llm, "arquitectura")
            self.assertEqual(name, "diagrama.png")
            self.assertEqual(llm.images, [img])
            self.assertIn("every component", llm.prompts[0][0])
            self.assertNotIn("a a ", llm.prompts[0][0])
            self.assertEqual(kb.search("kafka")[0].source, "diagrama.png")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_message_carries_image_base64(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from speak.llm_client import user_message_json

        tmp = Path(tempfile.mkdtemp())
        try:
            img = tmp / "d.jpg"
            img.write_bytes(b"\xff\xd8\xffdata")
            msg = json.loads(user_message_json("describe", [img]))
            content = msg["message"]["content"]
            self.assertEqual(content[0]["source"]["media_type"], "image/jpeg")
            self.assertEqual(content[-1], {"type": "text", "text": "describe"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_discovery_prompt_before_and_during_call(self):
        from speak.notes.copilot import discovery_prompt

        system, user = discovery_prompt(None, "Cliente: banco, migrar core a AWS", "(none)", "arquitectura")
        self.assertIn("has not started", user)
        self.assertIn("RPO/RTO", user)
        self.assertIn("propose a solution architecture", user)
        self.assertIn("Never treat an assumption as a fact", system)
        tr = Transcript([Segment(3, 8, "We process about two million transactions a day.", "Ellos")], "t")
        _, user = discovery_prompt(tr, "", "(none)", "venta")
        self.assertIn("two million transactions", user)
        self.assertIn("Quién decide", user)

    def test_discovery_auto_refresh_rules(self):
        from speak.notes.copilot import Discovery

        d = Discovery(ScriptedLLM([]), None, brief=lambda: "", snapshot=lambda: None, mode="arquitectura",
                      interval_s=90, min_new_words=40)
        t0 = d._last_run
        self.assertFalse(d.due(100, t0 + 30))  # muy pronto
        self.assertFalse(d.due(10, t0 + 120))  # casi nada nuevo
        self.assertTrue(d.due(100, t0 + 120))
        d.mode = "entrevista"
        self.assertFalse(d.due(100, t0 + 120))
        d.run_now()
        self.assertTrue(d.due(0, t0))  # el boton siempre

    def test_discovery_runs_and_reports(self):
        from speak.knowledge import KnowledgeBase
        from speak.notes.copilot import Discovery

        kb = KnowledgeBase()
        kb.add_text("arquitectura_actual.drawio", "API Gateway → Postgres RDS")
        llm = ScriptedLLM(["**Veredicto:** falta volumen\n### Pregunta ahora\n1. ¿Cuantas transacciones?"])
        updates = []
        d = Discovery(llm, kb, brief=lambda: "Banco X", snapshot=lambda: None, mode="arquitectura",
                      on_update=lambda md, done: updates.append(done))
        text = d.run_once(None)
        self.assertTrue(text.startswith("**Veredicto:**"))
        self.assertEqual(updates[-1], True)
        self.assertIn("Postgres RDS", llm.prompts[0][1])

    def test_architecture_mode_everywhere(self):
        from speak.knowledge import KnowledgeBase
        from speak.notes.analyzer import notes_prompt
        from speak.notes.copilot import COPILOT_MODES, PrepSession

        self.assertIn("arquitectura", COPILOT_MODES)
        prep = PrepSession(KnowledgeBase(), mode="arquitectura")
        _, user = prep.brief_prompt()
        self.assertIn("¿Alcanza la información?", user)
        self.assertIn("Preguntas que debo hacer yo", user)
        tr = Transcript([Segment(0, 2, "What is your RPO?", "Ellos")], "t")
        self.assertIn("Huecos de información", notes_prompt(tr, "arquitectura")[1])


if __name__ == "__main__":
    unittest.main()
