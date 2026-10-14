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
    """Casos sacados de la corrida e2e con la CPU al 100%."""

    def make(self, segs, now, me=(), them=(), llm=None):
        from speak.llm_client import FakeLLM
        from speak.notes.copilot import Copilot

        self.clock = [now]
        self.speech = {ME: list(me), THEM: list(them)}
        return Copilot(llm or FakeLLM("ok"), None, "", snapshot=lambda: Transcript(list(segs), "t"),
                       now=lambda: self.clock[0], mode="venta", speech=lambda who: list(self.speech[who]))

    def test_whisper_question_mark_on_a_fragment_waits_longer(self):
        cop = self.make([Segment(1, 3, "And what would the price be for?", THEM)], now=4.6)
        self.assertIsNone(cop.step())  # 1,6 s: con "?" normal ya dispararia; aqui no
        self.clock[0] = 6.2
        self.assertIsNotNone(cop.step())

    def test_complete_question_keeps_fast_path(self):
        cop = self.make([Segment(1, 3, "What is the timeline for the rollout?", THEM)], now=4.3)
        self.assertIsNotNone(cop.step())

    def test_waits_while_they_keep_talking_after_a_pause(self):
        # "...be for?" y tras 2,6 s sigue hablando: su segunda parte aun no
        # es texto, pero el VAD la ve en curso.
        cop = self.make([Segment(1, 3, "And what would the price be for?", THEM)], now=7.0,
                        them=[(1, 3), (5.6, 7.0)])
        self.assertIsNone(cop.step())
        self.speech[THEM][-1] = (5.6, 8.0)  # ya termino: ahora espera a Whisper
        self.clock[0] = 9.0
        pending = [1]
        cop.pending = lambda: pending[0]
        self.assertIsNone(cop.step())
        pending[0] = 0  # y su texto no llego (era un "mm-hmm" descartado): no bloquea

        self.assertIsNotNone(cop.step())

    def test_my_voice_closes_the_question_before_whisper(self):
        cop = self.make([Segment(1, 3, "How long would the audit take, and", THEM)], now=3.5)
        self.assertIsNone(cop.step())  # frase colgada: esperaria 3 s
        self.speech[ME].append((3.3, 3.5))  # empece a responder (VAD); mi texto aun no llega
        self.assertIsNotNone(cop.step())

    def test_answers_even_after_my_stall_is_transcribed(self):
        # Antes: si tu "buena pregunta, dejame ver" llegaba a texto antes de
        # disparar, la pregunta no se respondia nunca.
        cop = self.make([Segment(1, 3, "How long would the audit take?", THEM),
                         Segment(3.2, 5.0, "Great question, let me walk you through it.", ME)], now=5.2,
                        me=[(3.2, 5.0)])
        ans = cop.step()
        self.assertIsNotNone(ans)
        self.assertEqual(ans.question, "How long would the audit take?")
        self.assertIsNone(cop.step())  # y una sola vez

    def test_my_untranscribed_reply_splits_their_turns(self):
        # Ellos: afirmacion + pregunta A; yo respondo (sin texto aun); Ellos:
        # pregunta B. Debe responder B sola, no "afirmacion + A + B".
        segs = [Segment(1, 4, "We run five plants, three of them in Colombia.", THEM),
                Segment(4.5, 8, "Do you think Aurora can handle ten times that load?", THEM),
                Segment(12, 15, "Can you tell me about your PCI experience?", THEM)]
        cop = self.make(segs, now=17.0, me=[(8.8, 11.5)])
        ans = cop.step()
        self.assertEqual(ans.question, "Can you tell me about your PCI experience?")

    def test_speaker_echo_on_my_mic_is_not_me_talking(self):
        # Parlantes: tu micro capta cada frase suya ~60 ms despues. Sin filtro,
        # el eco de "...be for?" / "all three plants" partia la pregunta en dos
        # y la segunda mitad (sin "?") no se respondia.
        segs = [Segment(1, 3, "And what would the price be for", THEM),
                Segment(5.6, 8, "all three plants in Bogota?", THEM)]
        cop = self.make(segs, now=9.5, them=[(1, 3), (5.6, 8)], me=[(1.06, 3.1), (5.66, 8.1)])
        ans = cop.step()
        self.assertEqual(ans.question, "And what would the price be for all three plants in Bogota?")
        # Una respuesta tuya de verdad (no empieza con la suya) si corta el turno.
        cop2 = self.make(segs, now=9.5, them=[(1, 3), (5.6, 8)], me=[(3.5, 5.0)])
        self.assertEqual(cop2.step().question, "all three plants in Bogota?")

    def test_new_question_does_not_cancel_previous_answer(self):
        import threading as th

        from speak.llm_client import LLMClient

        release = th.Event()

        class SlowLLM(LLMClient):
            def stream(self, system, prompt, cancel=None, images=None):
                yield "primera parte "
                release.wait(3)
                if cancel is not None and cancel.is_set():
                    return
                yield "fin"

        segs = [Segment(1, 3, "How long would the audit take?", THEM)]
        cop = self.make(segs, now=5.0, llm=SlowLLM())
        first = cop.step()
        self.assertTrue(wait_for(lambda: first.text.startswith("primera")))
        segs.append(Segment(6, 7, "Sure.", ME))
        segs.append(Segment(8, 10, "And what is the price per plant?", THEM))
        self.speech[ME].append((6, 7))
        self.clock[0] = 12.0
        second = cop.step()
        self.assertIsNot(second, first)
        release.set()
        self.assertTrue(wait_for(lambda: first.done and second.done))
        self.assertTrue(first.text.endswith("fin"))

    def test_warning_note_is_split_from_what_is_read(self):
        from speak.notes.copilot import split_warning

        # Casos de la entrevista del 2026-10-12: la nota pegada a la frase.
        note, rest = split_warning("⚠ Not in my sources, the exact auth method there. Honestly, that's it,\n"
                                   "so I won't guess.\nFuente: [prepared_answers]")
        self.assertEqual(note, "⚠ Not in my sources, the exact auth method there.")
        self.assertEqual(rest, "Honestly, that's it,\nso I won't guess.\nFuente: [prepared_answers]")
        self.assertEqual(split_warning("⚠ Auth method not in your sources.\nSure, it was Azure Key Vault."),
                         ("⚠ Auth method not in your sources.", "Sure, it was Azure Key Vault."))
        self.assertEqual(split_warning("⚠ Not in"), ("⚠ Not in", ""))  # a medio llegar (streaming)
        self.assertEqual(split_warning("Sure, it was Azure Key Vault."), ("", "Sure, it was Azure Key Vault."))

    def test_seems_unfinished(self):
        from speak.notes.copilot import seems_unfinished

        self.assertTrue(seems_unfinished("And what would the price be for?"))
        self.assertTrue(seems_unfinished("Tell me about the steam audit and"))
        self.assertFalse(seems_unfinished("Can you tell me about PCI?"))
        self.assertFalse(seems_unfinished("¿Cuánto cuesta la auditoría?"))


class SpeechTimesTests(unittest.TestCase):
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
        spans = live.speech(ME)
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0][0], 0.8, delta=0.15)  # con pre-roll
        self.assertEqual(live.speech(THEM), [])


class LongMonologueTests(unittest.TestCase):
    """El otro habla ~35 s sin pausa: el segmentador corta a los 20 s. Medido
    2026-10-08: la continuacion heredaba el inicio del primer trozo, asi que el
    copiloto creia que el otro ya habia callado y respondia al trozo suelto."""

    A = "How would you design the payment service for a bank with our current load, and"
    B = "how would you handle PCI in Colombia?"

    class ScriptedSTT(SpeechToText):
        def __init__(self, texts):
            self.texts = list(texts)

        def transcribe(self, audio, sample_rate, prompt=""):
            return self.texts.pop(0) if self.texts else ""

        def transcribe_file(self, path):
            return []

    def push(self, live, start, end):
        for i in range(int(start * 10), int(end * 10)):
            live.push("them", tone(0.1), 16000, (i + 1) / 10)
        track = live._tracks[THEM]
        self.assertTrue(wait_for(lambda: track.fed >= int(end * SR) - 480 and track._q.empty()))

    def test_copilot_waits_for_the_whole_monologue(self):
        from speak.llm_client import FakeLLM
        from speak.notes.copilot import Copilot
        from speak.notes.live import LiveNotes

        clock = [0.0]  # quieto mientras llega el audio: asi no se rellena con silencio
        live = LiveNotes(self.ScriptedSTT([self.A, self.B]), None, clock=lambda: clock[0])
        live.start()
        cop = Copilot(FakeLLM("ok"), None, "", snapshot=live.snapshot, now=live.now,
                      pending=lambda: live.pending(THEM), mode="venta", speech=live.speech)
        try:
            self.push(live, 0.0, 25.0)
            self.assertTrue(wait_for(lambda: len(live.snapshot().segments) == 1))
            clock[0] = 25.0  # 5 s despues del corte, y el otro sigue hablando
            first = live.snapshot().segments[0]
            self.assertEqual((round(first.start), round(first.end)), (0, 20))
            self.assertIsNone(cop.step())  # no responde al trozo suelto
            self.assertEqual(cop.answers, [])
            self.assertAlmostEqual(live.speech(THEM)[-1][0], first.end, delta=0.05)  # la frase abierta empieza en el corte

            self.push(live, 25.0, 35.0)
            clock[0] = 36.0  # callo: el relleno de silencio cierra la frase
            self.assertTrue(wait_for(lambda: len(live.snapshot().segments) == 2 and live.pending(THEM) == 0))
            second = live.snapshot().segments[1]
            self.assertAlmostEqual(second.start, first.end, places=6)
            self.assertAlmostEqual(second.end, 35.5, delta=0.1)  # + hangover del VAD y hueco que cierra
            self.assertIsNone(cop.step())  # aun no pasa el silencio de espera (quiet_s)
            clock[0] = 38.5
            ans = cop.step()
            self.assertIsNotNone(ans)
            self.assertEqual(ans.question, f"{self.A} {self.B}")
            self.assertEqual(len(cop.answers), 1)
        finally:
            live.stop()
            cop.stop()


class StickyLanguageTests(unittest.TestCase):
    class LangSTT(SpeechToText):
        """Detecta "es" siempre; registra con que idioma lo llamaron."""

        language = None

        def __init__(self, prob=0.95):
            self.asked = []
            self.prob = prob

        def transcribe(self, audio, sample_rate, prompt=""):
            return "x"

        def transcribe_lang(self, audio, sample_rate, prompt="", language=None):
            self.asked.append(language)
            return "hola", "es", self.prob

        def transcribe_file(self, path):
            return []

    def run_phrases(self, stt, phrases, **kw):
        from speak.notes.live import LiveTranscriber

        lt = LiveTranscriber(stt, lambda who, ev: None, **kw)
        for who, dur, t in phrases:
            lt.submit(who, tone(dur), t, t + dur)
            self.assertTrue(wait_for(lambda: lt.pending(who) == 0))
        lt.close()
        lt.join(5)
        return lt

    def test_detects_once_then_fixes_and_rechecks(self):
        stt = self.LangSTT()
        lt = self.run_phrases(stt, [(THEM, 2.5, 10.0 * k) for k in range(6)], recheck_every=4)
        self.assertEqual(lt.language[THEM], "es")
        # 1a: detecta (larga y segura -> fija); 2a-4a: "es"; 5a: revisa; 6a: "es".
        self.assertEqual(stt.asked, [None, "es", "es", "es", None, "es"])

    def test_short_phrase_borrows_the_other_speakers_language(self):
        stt = self.LangSTT()
        lt = self.run_phrases(stt, [(THEM, 2.5, 0.0), (ME, 0.8, 5.0)])
        self.assertEqual(stt.asked, [None, "es"])
        self.assertIsNone(lt.language[ME])  # prestado, no fijado

    def test_unsure_detection_needs_two_votes(self):
        stt = self.LangSTT(prob=0.7)
        lt = self.run_phrases(stt, [(THEM, 2.5, 0.0), (THEM, 2.5, 10.0), (THEM, 2.5, 20.0)])
        self.assertEqual(stt.asked, [None, None, "es"])
        self.assertEqual(lt.language[THEM], "es")

    def test_user_fixed_language_wins(self):
        stt = self.LangSTT()
        stt.language = "en"
        self.run_phrases(stt, [(THEM, 2.5, 0.0), (THEM, 2.5, 10.0)])
        self.assertEqual(stt.asked, ["en", "en"])

    def test_per_phrase_detector_never_fixes_language(self):
        # Deepgram "multi": cada frase se detecta sola, asi se puede cambiar
        # de ingles a espanol en cualquier momento de la llamada.
        stt = self.LangSTT()
        stt.detects_language_per_phrase = True
        self.run_phrases(stt, [(THEM, 2.5, 10.0 * k) for k in range(4)] + [(ME, 0.8, 50.0)])
        self.assertEqual(stt.asked, [None] * 5)

    def test_deepgram_multi_detects_per_phrase(self):
        from speak.transcriber import DeepgramSTT

        self.assertTrue(DeepgramSTT("k").detects_language_per_phrase)
        self.assertFalse(DeepgramSTT("k", language="es").detects_language_per_phrase)


class GlossaryAndSpanishTests(unittest.TestCase):
    def test_glossary_keeps_names_and_acronyms(self):
        from speak.notes.live import glossary_from

        brief = ("# Brief de la llamada\n## Contexto y objetivo\nReunion con Acme (Juan Pérez). Migrar pagos a "
                 "AWS con API Gateway y Aurora PostgreSQL, cumplir PCI DSS.\n- 200 TPS en Bogotá y Medellín.")
        g = glossary_from(brief, "El caso de Cementos X bajó 11%.")
        self.assertTrue(g.startswith("Glosario: "))
        for term in ("AWS", "PCI", "PostgreSQL", "Aurora", "Bogotá", "Acme"):
            self.assertIn(term, g)
        for word in ("Brief", "Contexto", "Reunion", "El"):
            self.assertNotIn(f" {word},", g)
        self.assertLessEqual(len(g), 181)
        self.assertEqual(glossary_from("", "hola a todos"), "")

    def test_glossary_goes_into_the_whisper_prompt(self):
        from speak.notes.live import LiveTranscriber

        prompts = []

        class Rec(SpeechToText):
            def transcribe(self, audio, sample_rate, prompt=""):
                prompts.append(prompt)
                return "ok"

            def transcribe_file(self, path):
                return []

        lt = LiveTranscriber(Rec(), lambda who, ev: None, glossary="Glosario: PCI, AWS.")
        lt.submit(THEM, tone(1.0), 0, 1)
        lt.submit(THEM, tone(1.0), 10, 11)
        self.assertTrue(wait_for(lambda: len(prompts) == 2))
        lt.close()
        self.assertEqual(prompts[0], "Glosario: PCI, AWS.")
        self.assertEqual(prompts[1], "Glosario: PCI, AWS. ok")  # + lo ya dicho por ese hablante

    def test_spanish_yes_no_questions_without_question_marks(self):
        from speak.turn_detector import question_kind

        questions = ["Ustedes creen que Aurora aguanta 10 veces esa carga.",
                     "Usted es creen que aurora aguanta 10 veces esa carga.",  # como la oye Whisper base
                     "Usted es creing que Aurora aguanta 10 veces esa carga.",
                     "Tienen experiencia con PCI DSS.", "Es posible hacerlo en dos semanas.",
                     "Pueden enviarme la propuesta.", "Y hay alguna forma de bajar el precio."]
        statements = ["Tenemos cinco plantas, tres en Colombia.", "Tienen cinco plantas.",
                      "Hoy procesamos 200 transacciones.", "Creo que eso está bien.",
                      "Creemos que la carga va a crecer.",
                      "Nosotros ya trabajamos con otro proveedor."]
        for q in questions:
            self.assertEqual(question_kind(q), "question", q)
        for s in statements:
            self.assertEqual(question_kind(s), "statement", s)


class NoiseFilterTests(unittest.TestCase):
    def test_values_measured_on_a_real_webcam_mic(self):
        from speak.transcriber import looks_like_noise

        ctx = "Good morning, good morning. Good morning. How are you?"
        # Ruido (tos/teclado) que Whisper convirtio en copia del contexto.
        self.assertTrue(looks_like_noise("Good morning. Good morning.", ctx, 0.43))
        self.assertTrue(looks_like_noise("Good morning. Good morning.", ctx, 0.75))
        self.assertTrue(looks_like_noise("I'm sorry.", "", 0.62))
        # Voz real (baja) del mismo microfono: se queda.
        self.assertFalse(looks_like_noise("How are you?", ctx, 0.07))
        self.assertFalse(looks_like_noise("I think I'm like...", ctx, 0.29))
        self.assertFalse(looks_like_noise("Hello, how are you?", "How are we doing?", 0.09))
        # Repetir lo dicho con voz clara (no_speech bajo) tambien se queda.
        self.assertFalse(looks_like_noise("Good morning.", ctx, 0.12))
        # Dudoso pero con palabras nuevas: se queda.
        self.assertFalse(looks_like_noise("We need the PCI report by Friday.", ctx, 0.35))


class AnswerLanguageTests(unittest.TestCase):
    def test_honestly_is_removed_from_live_answers(self):
        from speak.notes.copilot import drop_honestly

        self.assertEqual(drop_honestly("Honestly, what gets me is X.\nAnd honestly, I like it."),
                         "What gets me is X.\nAnd I like it.")
        self.assertEqual(drop_honestly("It is, honestly, hard. To be honest I agree."), "It is hard. I agree.")
        self.assertEqual(drop_honestly("Honest work is good."), "Honest work is good.")

    def test_answer_language_follows_the_question(self):
        from speak.notes.copilot import answer_prompt, guess_language

        self.assertEqual(guess_language("Can you tell me about your PCI experience?"), "English")
        self.assertEqual(guess_language("¿Qué experiencia tienen con PCI?"), "Spanish")
        self.assertEqual(guess_language("Usted es creen que Aurora aguanta 10 veces esa carga."), "Spanish")
        # 2026-10-12: el "de los" del nombre de la universidad la hacia espanola
        self.assertEqual(guess_language("You mentioned two degrees at Universidad de los Andes. Why both?"),
                         "English")
        self.assertEqual(guess_language("¿Por qué estudiaste en la Universidad de los Andes?"), "Spanish")
        # Turno largo en espanol que termina cambiando a ingles: manda el final.
        long_es = ("Vale, ahora cambiamos un momento a español. ¿Has trabajado en remoto antes? ¿Cómo te organizas con "
                   "tu equipo cuando no lo ves en persona? Pues nosotros nos comunicamos en inglés y dejamos todo escrito. "
                   "Eso es muy útil aquí, porque trabajamos mucho entre Barcelona y Varsovia. ")
        self.assertEqual(guess_language(long_es + "Okay. Back to English. Tell me about a time you had to learn "
                                        "something new quickly. What was it, and how did you approach it?"), "English")
        self.assertEqual(guess_language("Thanks, that was great. Let's continue in Spanish now. ¿Y por qué quieres "
                                        "dejar Amadeus después de seis meses?"), "Spanish")
        # Brief y fuentes en espanol, pregunta en ingles: la respuesta en ingles.
        system, user = answer_prompt("Do you think Aurora can handle ten times that load?",
                                     "Reunión con Acme", "Precio: 12.000 USD", "", "venta",
                                     guide="Siempre en español")
        self.assertTrue(user.rstrip().endswith("Answer language: English"))
        self.assertIn("Answer language", system)
        # La guia va despues y puede cambiar el idioma ("Siempre en español").
        self.assertGreater(system.index("Siempre en español"), system.index("Answer language"))


class PrewarmTests(unittest.TestCase):
    def make(self):
        import io
        import json

        from speak.llm_client import ClaudeCLIClient

        spawned = []

        class FakeProc:
            def __init__(self, system, json_input):
                self.system, self.json_input = system, json_input
                self.stdin = io.StringIO()
                self.stdin.close = lambda: None
                delta = {"type": "stream_event", "event": {"type": "content_block_delta",
                                                           "delta": {"type": "text_delta", "text": "hola"}}}
                self.stdout = iter([json.dumps(delta) + "\n", json.dumps({"type": "result"}) + "\n"])
                self.stderr = io.StringIO()
                self.killed = False
                self.returncode = None

            def poll(self):
                return 0 if self.killed else None

            def kill(self):
                self.killed = True

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        client = ClaudeCLIClient("m", prewarm=True)

        def spawn(system, json_input, system_file=None):
            proc = FakeProc(system, json_input)
            spawned.append(proc)
            return proc
        client._spawn = spawn
        return client, spawned

    def test_uses_the_warm_process_and_refills(self):
        client, spawned = self.make()
        client.warm("S")
        self.assertTrue(wait_for(lambda: client._warm is not None))
        warm = spawned[0]
        self.assertEqual("".join(client.stream("S", "pregunta")), "hola")
        self.assertIn('"pregunta"', warm.stdin.getvalue())  # fue al pre-arrancado, en JSON
        self.assertTrue(wait_for(lambda: client._warm is not None and client._warm[1] is not warm))
        client.close()
        self.assertTrue(spawned[-1].killed)

    def test_other_system_prompt_discards_the_warm_one(self):
        client, spawned = self.make()
        client.warm("guia vieja")
        self.assertTrue(wait_for(lambda: client._warm is not None))
        old = spawned[0]
        self.assertEqual("".join(client.stream("guia nueva", "p")), "hola")
        self.assertTrue(old.killed)
        self.assertEqual(spawned[1].system, "guia nueva")
        client.close()

    def test_long_system_prompt_is_prewarmed_too(self):
        # Medido 2026-10-08: con una guia de ~21.000 caracteres no se
        # pre-arrancaba y cada respuesta arrancaba en frio (2,6-14 s).
        import os

        client, spawned = self.make()
        files = []
        orig = client._spawn

        def spawn(system, json_input, system_file=None):
            files.append(system_file)
            return orig(system, json_input, system_file)
        client._spawn = spawn
        long_system = "x" * (client.MAX_ARG_SYSTEM + 10)
        client.warm(long_system)
        self.assertTrue(wait_for(lambda: client._warm is not None))
        warm = spawned[0]
        self.assertTrue(files[0] and os.path.exists(files[0]))  # el archivo vive mientras espera
        self.assertEqual("".join(client.stream(long_system, "pregunta")), "hola")
        self.assertIn('"pregunta"', warm.stdin.getvalue())  # uso el pre-arrancado
        self.assertFalse(os.path.exists(files[0]))  # y su archivo se borro al terminar
        client.close()


class RewriteLogTests(unittest.TestCase):
    def test_stop_mid_rewrite_keeps_last_complete_answer(self):
        from speak.notes.copilot import Answer, Copilot

        cop = Copilot.__new__(Copilot)  # solo render_log: sin hilos ni LLM
        ok = Answer(1, 9.0, "How long?", text="**Respuesta:** 8 semanas.", done=True)
        mid = Answer(2, 30.0, "And the price for all three plants?", text="**Resp", done=False,
                     last_done="**Respuesta:** 12.000 USD por planta.")
        fresh = Answer(3, 60.0, "PCI?", text="**Respuesta:** Si", done=False)
        cop.answers = [ok, mid, fresh]
        log = cop.render_log()
        self.assertIn("8 semanas", log)
        self.assertIn("12.000 USD por planta", log)
        self.assertNotIn("**Resp\n", log)
        self.assertIn("no alcanzo a terminar", log)
        self.assertIn("**Respuesta:** Si", log)  # sin respuesta previa: queda lo que hubo


if __name__ == "__main__":
    unittest.main()
