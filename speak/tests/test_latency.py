"""Latencia del copiloto: respuesta preparada al instante, disparo anticipado
y metricas. Sin red ni modelos (FakeLLM)."""

from __future__ import annotations

import time
import unittest

from speak.notes.pipeline import ME, THEM, Transcript
from speak.transcriber import Segment

PREP = """# Respuestas
## why_not_stay_at_aws - Why didn't you stay at AWS after the internship?
I was preparing for a Solutions Architect role.
(Only if asked about the program: I passed two of three.)

## salary_below_band - Our band is lower than your range, would that work?
Forty thousand is the minimum that works for me.

## proudest_experience - What experience are you most proud of? | Your proudest achievement
It's the hackathon.

## no_heading_question
Esta no tiene pregunta en el titulo: no entra al indice.
"""


class SlowLLM:
    """Como el CLI: se queda bloqueado antes del primer trozo sin mirar `cancel`."""

    def __init__(self, first_after: float, rest_after: float = 0.0, reply: str = "ajustada"):
        self.first_after, self.rest_after, self.reply = first_after, rest_after, reply

    def stream(self, system, prompt, cancel=None, images=None):
        time.sleep(self.first_after)
        yield self.reply[:3]
        time.sleep(self.rest_after)
        yield self.reply[3:]


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class PreparedIndexTests(unittest.TestCase):
    def index(self, **kw):
        from speak.notes.instant import PreparedIndex

        return PreparedIndex({"Prepared answers": PREP}, **kw)

    def test_matches_rephrased_question(self):
        m = self.index().match("Okay, thanks. And why didn't you stay at AWS once the internship ended?")
        self.assertIsNotNone(m)
        self.assertEqual(m.key, "why_not_stay_at_aws")
        self.assertEqual(m.text, "I was preparing for a Solutions Architect role.")  # sin la nota entre parentesis

    def test_alternative_phrasings(self):
        self.assertEqual(self.index().match("What's your proudest achievement so far?").key, "proudest_experience")

    def test_one_shared_word_is_not_enough(self):
        # "Can you hear me?" compartia solo "hear" con "How did you hear about this role?"
        self.assertIsNone(self.index().match("Hi Maria! Can you hear me okay?"))
        self.assertIsNone(self.index().match("Tell me about your band at university"))

    def test_only_the_end_of_a_long_turn_counts(self):
        long_turn = ("why didn't you stay at AWS " + "bla " * 60 + "What experience are you most proud of?")
        self.assertEqual(self.index().match(long_turn).key, "proudest_experience")

    def test_tie_goes_to_the_most_specific_heading(self):
        from speak.notes.instant import PreparedIndex

        prep = ("## why_leaving - Why leave after six months\nporque...\n\n"
                "## flight_risk - How do we know you won't leave after six months too?\ncompromiso...\n")
        m = PreparedIndex({"p": prep}).match("How do we know you won't leave us after six months too?")
        self.assertEqual(m.key, "flight_risk")

    def test_single_keyword_heading(self):
        from speak.notes.instant import PreparedIndex

        m = PreparedIndex({"p": "## why_valencia - Why Valencia?\nCosto de vida.\n"}).match("Why Valencia, by the way?")
        self.assertEqual(m.key, "why_valencia")

    def test_sections_without_question_are_ignored(self):
        keys = {e.key for e in self.index().entries}
        self.assertNotIn("no_heading_question", keys)


class InstantAndEagerCopilotTests(unittest.TestCase):
    def make(self, segs, now, llm=None, **kw):
        from speak.llm_client import FakeLLM
        from speak.notes.copilot import Copilot

        self.clock = [now]
        self.updates = []
        return Copilot(llm or FakeLLM("ajustada"), None, "", snapshot=lambda: Transcript(list(segs), "t"),
                       now=lambda: self.clock[0], mode="venta",
                       on_answer=lambda a: self.updates.append((a.instant_key, a.text, a.done)), **kw)

    def test_prepared_answer_is_shown_before_the_llm(self):
        from speak.notes.instant import PreparedIndex

        idx = PreparedIndex({"p": PREP})
        cop = self.make([Segment(1, 4, "Why didn't you stay at AWS after the internship?", THEM)], now=6.0,
                        instant=idx.match)
        ans = cop.step()
        self.assertEqual(ans.instant_key, "why_not_stay_at_aws")
        self.assertEqual(self.updates[0], ("why_not_stay_at_aws", "", False))  # primero MEMORIA, sin LLM
        self.assertTrue(wait_for(lambda: ans.done))
        self.assertEqual(ans.text, "ajustada")  # luego AL VUELO
        self.assertEqual(ans.instant, "I was preparing for a Solutions Architect role.")  # MEMORIA se conserva
        self.assertAlmostEqual(ans.trigger_lag, 2.0, delta=0.01)

    def test_memorized_answer_is_given_whole_without_llm(self):
        from speak.llm_client import FakeLLM
        from speak.notes.copilot import Copilot
        from speak.notes.instant import PreparedIndex

        prep = ("## intro - Tell me about yourself\n(Memorized intro: give it exactly as written.)\n"
                + "\n".join(f"Line {i}." for i in range(1, 13)) + "\n")

        class KB:
            chunks = []

            def extra_texts(self):
                return {"p": prep}

        llm = FakeLLM("seis lineas")
        segs = [Segment(1, 4, "Tell me about yourself", THEM)]
        cop = Copilot(llm, KB(), "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 6.0, mode="llamada",
                      instant=PreparedIndex({"p": prep}).match)
        ans = cop.step()
        self.assertTrue(ans.done and ans.memorized)
        self.assertEqual(ans.text, ans.instant)
        self.assertIn("Line 12.", ans.instant)  # entera, sin el recorte de 6 lineas
        self.assertEqual(llm.calls, [])  # sin AL VUELO

    def test_intro_in_other_words_finds_the_memorized_intro(self):
        from speak.notes.copilot import _INTRO_RE

        for q in ("Before we start, could you say a few words about who you are?", "Introduce yourself, please.",
                  "Walk us through your path so far, briefly.", "Tell us a little about your background."):
            self.assertTrue(_INTRO_RE.search(q), q)
        from speak.notes.copilot import _BURNING_RE

        self.assertTrue(_BURNING_RE.search("What is Maria Alejandra burning for? So what is your interest? I'm all yours."))
        for q in ("Tell us about your background in Kubernetes networking",
                  "What did you learn about yourself from that failure?",
                  "How would you present yourself to a user whose laptop was compromised?"):
            self.assertFalse(_INTRO_RE.search(q), q)

    def test_vague_words_are_dropped(self):
        from speak.notes.copilot import for_reading

        self.assertEqual(for_reading("Not instinct, I check the timeline first."), "I check the timeline first.")
        self.assertEqual(for_reading("That is proof, not instinct."), "That is proof, not guesses.")
        self.assertEqual(for_reading("My instinct is to check the logs."), "My habit is to check the logs.")

    def test_memory_is_not_delayed_by_a_slow_llm(self):
        from speak.notes.instant import PreparedIndex

        cop = self.make([Segment(1, 4, "Why didn't you stay at AWS after the internship?", THEM)], now=6.0,
                        llm=SlowLLM(first_after=1.0), instant=PreparedIndex({"p": PREP}).match)
        t0 = time.time()
        ans = cop.step()
        self.assertLess(time.time() - t0, 0.2)  # step() no espera al LLM
        self.assertEqual(self.updates[0], ("why_not_stay_at_aws", "", False))  # MEMORIA ya visible
        self.assertTrue(wait_for(lambda: ans.done, timeout=3))
        self.assertEqual(ans.text, "ajustada")  # AL VUELO llega despues, cuando esta lista
        self.assertFalse(ans.timed_out)

    def test_live_timeout_leaves_only_memory(self):
        from speak.notes.instant import PreparedIndex

        cop = self.make([Segment(1, 4, "Why didn't you stay at AWS after the internship?", THEM)], now=6.0,
                        llm=SlowLLM(first_after=1.5), instant=PreparedIndex({"p": PREP}).match,
                        live_timeout_s=0.2)
        t0 = time.time()
        ans = cop.step()
        self.assertTrue(wait_for(lambda: ans.done, timeout=1))
        self.assertLess(time.time() - t0, 0.6)  # no espera los 1,5 s del LLM
        self.assertTrue(ans.timed_out)
        self.assertEqual(ans.text, "")
        self.assertEqual(self.updates[-1], ("why_not_stay_at_aws", "", True))
        time.sleep(1.6)  # el LLM termina tarde: no pisa nada
        self.assertEqual(ans.text, "")
        self.assertIn("Solutions Architect", cop.render_log())  # en copilot.md queda MEMORIA

    def test_llm_failure_marks_the_question_unanswered(self):
        # Sin internet el CLI sale con codigo 1 al instante: la pregunta no puede quedarse
        # en espera con la respuesta anterior en pantalla (grabacion 2026-10-18 23:24).
        from speak.llm_client import LLMError

        class DeadLLM:
            def stream(self, system, user, cancel=None):
                raise LLMError("claude termino con codigo 1 sin mensaje: probablemente sin internet")
                yield ""

        cop = self.make([Segment(1, 4, "What is the timeline for the rollout?", THEM)], now=6.0,
                        llm=DeadLLM(), live_timeout_s=5)
        ans = cop.step()
        self.assertTrue(wait_for(lambda: ans.done, timeout=1))
        self.assertTrue(ans.timed_out)
        self.assertEqual(ans.text, "")

    def test_live_timeout_does_not_cut_an_answer_that_started(self):
        cop = self.make([Segment(1, 4, "What is the timeline for the rollout?", THEM)], now=6.0,
                        llm=SlowLLM(first_after=0.05, rest_after=0.5), live_timeout_s=0.2)
        ans = cop.step()
        self.assertTrue(wait_for(lambda: ans.done, timeout=3))
        self.assertFalse(ans.timed_out)
        self.assertEqual(ans.text, "ajustada")

    def test_without_a_near_exact_match_only_the_llm_answers(self):
        from speak.notes.instant import PreparedIndex

        idx = PreparedIndex({"p": PREP}, min_score=0.9, min_precision=0.75)
        cop = self.make([Segment(1, 4, "Why didn't you stay at AWS and what did your manager say?", THEM)],
                        now=6.0, instant=idx.match)
        ans = cop.step()
        self.assertEqual(ans.instant, "")
        self.assertTrue(wait_for(lambda: ans.done))
        self.assertEqual(ans.text, "ajustada")

    def test_strict_match_needs_a_near_exact_question(self):
        from speak.notes.instant import PreparedIndex

        idx = PreparedIndex({"p": PREP}, min_score=0.9, min_precision=0.75)
        self.assertEqual(idx.match("Okay. Why didn't you stay at AWS after the internship?").key,
                         "why_not_stay_at_aws")
        self.assertIsNone(idx.match("Why didn't you stay at AWS? What did your manager think about it?"))
        self.assertIsNone(idx.match("What experience are you most proud of in security work at CERN?"))

    def test_trailing_give_me_an_example_belongs_to_the_question_before(self):
        # Simulacro 2026-10-18 12:26: "What is SSRF...? Give me one concrete example." saco la historia
        # del login porque su titulo incluye "Give me a concrete example of that".
        from speak.notes.instant import PreparedIndex

        prep = ("## login_failure_case - Tell me about a recent incident | Give me a concrete example of that\n"
                "Last week, users at one airport couldn't log in.\n")
        idx = PreparedIndex({"p": prep}, min_score=0.9, min_precision=0.75)
        self.assertIsNone(idx.match("Let's move to web security. What is SSRF and why can it be dangerous "
                                    "in a cloud environment? Give me one concrete example."))
        self.assertEqual(idx.match("Okay. Give me a concrete example of that.").key, "login_failure_case")
        self.assertEqual(idx.match("So what did you do? Give me a concrete example of that.").key,
                         "login_failure_case")

    def test_broken_instant_matcher_does_not_block_the_answer(self):
        def boom(_q):
            raise RuntimeError("indice roto")

        cop = self.make([Segment(1, 4, "What is the timeline for the rollout?", THEM)], now=6.0, instant=boom)
        ans = cop.step()
        self.assertEqual(ans.instant, "")
        self.assertTrue(wait_for(lambda: ans.done))
        self.assertEqual(ans.text, "ajustada")

    def test_eager_fires_earlier_on_a_closed_question(self):
        seg = [Segment(1, 4, "What is the timeline for the rollout?", THEM)]
        slow = self.make(seg, now=4.6)  # 0,6 s de silencio: sin eager, espera 1,2 s
        self.assertIsNone(slow.step())
        fast = self.make(seg, now=4.6, eager_s=0.5)
        self.assertIsNotNone(fast.step())

    def test_eager_does_not_apply_to_unfinished_or_non_questions(self):
        seg = [Segment(1, 4, "And what would the price be for?", THEM)]  # colgada: espera larga
        cop = self.make(seg, now=4.6, eager_s=0.5)
        self.assertIsNone(cop.step())
        seg2 = [Segment(1, 4, "Tell me about your experience with Kubernetes", THEM)]  # sin "?"
        cop2 = self.make(seg2, now=4.6, eager_s=0.5)
        self.assertIsNone(cop2.step())

    def test_eager_answer_is_redone_if_they_keep_talking(self):
        segs = [Segment(1, 4, "What is the timeline for the rollout?", THEM)]
        cop = self.make(segs, now=4.6, eager_s=0.5)
        first = cop.step()
        self.assertIsNotNone(first)
        segs.append(Segment(4.8, 8, "And how many people would you need for the whole project?", THEM))
        self.clock[0] = 8.6
        second = cop.step()
        self.assertIs(second, first)  # misma tarjeta, reescrita con la pregunta completa
        self.assertIn("how many people", second.question)


if __name__ == "__main__":
    unittest.main()


class FollowupTests(unittest.TestCase):
    """Tras "Do you have questions for me?", lo que el otro explica trae
    preguntas de seguimiento (sin MEMORIA)."""

    ANSWER = ("Good question. We did disable device code login for most users, but some experiments still "
              "need it for their scripts, so we kept an exception list and we shortened the tokens.")

    def make(self, segs, now):
        from speak.notes.copilot import Copilot

        class Recording:
            prompts = []

            def stream(self, system, prompt, cancel=None, images=None):
                self.prompts.append(prompt)
                yield "ok"

            def warm(self, system):
                pass

        self.llm = Recording()
        self.llm.prompts = []
        self.clock = [now]
        return Copilot(self.llm, None, "", snapshot=lambda: Transcript(list(segs), "t"),
                       now=lambda: self.clock[0], mode="venta")

    def test_their_answer_after_my_question_gets_followups(self):
        segs = [Segment(1, 3, "Alright, Maria, do you have questions for me?", THEM)]
        cop = self.make(segs, now=5.0)
        first = cop.step()
        self.assertFalse(first.followup)
        self.assertTrue(wait_for(lambda: first.done))
        segs += [Segment(6, 12, "Yes. Did you end up disabling device code login?", ME),
                 Segment(13, 25, self.ANSWER, THEM)]
        self.clock[0] = 26.0
        self.assertIsNone(cop.step())  # aun sin los 2 s de silencio
        self.clock[0] = 27.5
        ans = cop.step()
        self.assertTrue(ans.followup)
        self.assertEqual(ans.instant, "")
        self.assertTrue(wait_for(lambda: ans.done))
        self.assertIn("follow-up questions", self.llm.prompts[-1])
        self.assertIn("<said>", self.llm.prompts[-1])

    def test_statements_before_the_questions_turn_are_ignored(self):
        cop = self.make([Segment(1, 12, self.ANSWER, THEM)], now=20.0)
        self.assertIsNone(cop.step())

    def test_short_reaction_gets_no_followup(self):
        segs = [Segment(1, 3, "Any questions for us?", THEM)]
        cop = self.make(segs, now=5.0)
        self.assertFalse(cop.step().followup)
        segs += [Segment(6, 9, "What is the team like?", ME), Segment(10, 12, "It's a great team, really.", THEM)]
        self.clock[0] = 20.0
        self.assertIsNone(cop.step())

    def test_who_asks_for_questions(self):
        from speak.notes.copilot import asks_for_questions

        for t in ("Do you have questions for me?", "Alright, Maria, any questions for us?",
                  "Is there anything you'd like to ask me?", "Okay. Do you have any questions?"):
            self.assertTrue(asks_for_questions(t), t)
        for t in ("I have some questions for you.", "Who are you?", "What questions did you prepare about TLS?"):
            self.assertFalse(asks_for_questions(t), t)
