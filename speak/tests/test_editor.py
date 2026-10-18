"""Pestaña ✍️ Editor: deteccion de preguntas de pizarra, formato y Copilot."""

import time
import unittest

from speak.llm_client import FakeLLM
from speak.notes.copilot import Answer, Copilot
from speak.notes.editor import awaiting_answer, continues_editor, editor_html, needs_editor, parse_editor
from speak.notes.pipeline import ME, THEM, Transcript
from speak.transcriber import Segment

SCRIPT = """## Entender
» Let me write down what we have.
# input: conn.log, output: top 10 source IPs
## Código
» A Counter keeps one entry per IP.
from collections import Counter
counts = Counter()
"""


class NeedsEditorTests(unittest.TestCase):
    def test_asks_to_write(self):
        for q in ["Given a Zeek conn.log, print the top ten source IPs by number of connections.",
                  "Write a script that compares the loaded kernel modules to an allowlist.",
                  "Give me a one-liner for the five IPs with the most failed SSH logins.",
                  "Can you write some pseudocode for that?",
                  "How would you decide in code if it looks like beaconing?",
                  "Could you draw the architecture of the pipeline?",
                  "Implement a function that checks a website for missing security headers.",
                  "Escribe una función que cuente los logins fallidos.",
                  "Now you have a set of malicious IPs. Return every connection whose destination is in that set.",
                  "Write a minimal TCP port check.",
                  "What is a NetworkPolicy? Write one that denies all egress from a namespace.",
                  "Show me how you'd structure a small tool.",
                  "What's wrong with this code and how do you fix it?",
                  "Let's do a bit of code. Given a Zeek conn.log, print the top ten source IPs.",
                  "Thank you. David, let's do a coding exercise, write a Python function to parse a log line.",
                  "From var log secure, write code that counts failed logins per source IP.",
                  "Sure. Could you give me a puppet class that hardens SSH with validation and reload?"]:
            self.assertTrue(needs_editor(q), q)

    def test_not_for_talk_or_stories(self):
        for q in ["What is Zeek?",
                  "Tell me about a time you wrote code that broke production.",
                  "What does your triage script do?",
                  "Why do you want to join CERN?",
                  "How would you harden a Kubernetes cluster?",
                  "A hundred people clicked a device code phishing link. Which setting would have helped?",
                  "What would you check in a code review for security?",
                  "Infrastructure as code: why is it good for security?",
                  "Give me one Microsoft 365 setting you'd check first and why.",
                  # Practicas del 2026-10-17: abrian la pizarra sin pedir codigo.
                  "You discover that device code authentication is enabled for thousands of users. Walk me through "
                  "your reasoning and the technical steps you'd take.",
                  "I'll write that up cleanly. What controls would you put around the device code flow?",
                  "Here's the key implementation point. Targeting a group doesn't restrict the method. What next?",
                  "It's a panel set to hard mode. We'll cover coding in Python, investigations and config. "
                  "Want to start now?",
                  "Walk me through which tools you would use first, and why."]:
            self.assertFalse(needs_editor(q), q)

    def test_follow_up_on_the_code(self):
        self.assertTrue(continues_editor("The file is one point two terabytes. What changes?"))
        self.assertTrue(continues_editor("And for ten thousand sites?"))
        self.assertFalse(continues_editor("Tell me about a time you had to scale something."))


class RenderTests(unittest.TestCase):
    def test_parse_boxes_say_and_type(self):
        boxes = parse_editor(SCRIPT)
        self.assertEqual([t for t, _ in boxes], ["Entender", "Código"])
        self.assertEqual(boxes[0][1][0], ("say", "Let me write down what we have."))
        self.assertEqual(boxes[1][1][-1], ("type", "counts = Counter()"))

    def test_fences_and_text_before_title(self):
        boxes = parse_editor("```python\nx = 1\n```")
        self.assertEqual(boxes, [("", [("type", "x = 1")])])

    def test_html_red_spoken_black_typed_escaped(self):
        out = editor_html("## Código\n» Compare a < b.\nif a < b:\n    print(a)")
        self.assertIn("EDITOR", out)
        self.assertIn("#c62828", out)  # lo que se dice, en rojo
        self.assertIn("» “Compare a &lt; b.”", out)
        self.assertIn("if a &lt; b:", out)
        self.assertIn("    print(a)", out)  # la sangria se conserva

    def test_spoken_lines_read_aloud_code_untouched(self):
        from speak.notes.copilot import _said_for_reading
        self.assertEqual(_said_for_reading("» I'd use a Counter.\nmsg = \"I'd\""),
                         "» I would use a Counter.\nmsg = \"I'd\"")


class CopilotEditorTests(unittest.TestCase):
    def make(self, segs, editor_llm, mode="llamada"):
        events = []
        cop = Copilot(FakeLLM("Spoken answer."), None, "", snapshot=lambda: Transcript(list(segs), "t"),
                      now=lambda: 100.0, mode=mode, editor_llm=editor_llm, on_editor=events.append)
        return cop, events

    def wait(self, ans):
        t0 = time.time()
        while not ans.editor_done and time.time() - t0 < 5:
            time.sleep(0.01)

    def test_coding_question_gets_editor_script(self):
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, events = self.make(segs, ed)
        ans = cop.step()
        self.wait(ans)
        self.assertTrue(ans.editor_on and ans.editor_done)
        self.assertIn("Counter", ans.editor)
        self.assertTrue(events)
        self.assertIn("top ten source IPs", ed.calls[0][1])

    def test_talk_question_has_no_editor(self):
        segs = [Segment(0, 4, "What is the difference between Zeek and Suricata?", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, _ = self.make(segs, ed)
        ans = cop.step()
        time.sleep(0.1)
        self.assertFalse(ans.editor_on)
        self.assertEqual(ed.calls, [])

    def test_follow_up_continues_previous_script(self):
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, _ = self.make(segs, ed)
        self.wait(cop.step())
        segs.append(Segment(6, 25, "I would read it line by line with a Counter.", ME))
        segs.append(Segment(30, 34, "The file is one point two terabytes. What changes?", THEM))
        ans = cop.step()
        self.wait(ans)
        self.assertTrue(ans.editor_done)
        self.assertIn("<editor_so_far>", ed.calls[-1][1])

    def exercise_then(self, follow_up, reply, wait=True, me="I would read it line by line with a Counter."):
        """Un ejercicio en la pizarra y luego una repregunta; el editor responde `reply`."""
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, events = self.make(segs, ed)
        self.wait(cop.step())
        segs.append(Segment(6, 25, me, ME))
        segs.append(Segment(30, 34, follow_up, THEM))
        ed.reply = reply
        events.clear()
        ans = cop.step()
        self.wait(ans) if wait else time.sleep(0.1)
        return cop, ed, ans, events

    def test_any_follow_up_goes_to_editor_new_requirement(self):
        _, ed, ans, _ = self.exercise_then(
            "Now we also want to ignore internal addresses. How does that change things?",
            "## Cambio: ignorar internas\n» Noting the new rule.\n# Q: skip internal IPs [confirmed]")
        self.assertTrue(ans.editor_on)
        self.assertIn("Cambio", ans.editor)
        self.assertIn("Counter", ed.calls[-1][1])  # ve lo que ya estaba escrito

    def test_unrelated_follow_up_no_edit_stays_hidden(self):
        _, _, ans, events = self.exercise_then("Why do you want to join CERN?", "NO_EDIT")
        self.assertFalse(ans.editor_on)
        self.assertEqual(ans.editor, "")
        self.assertFalse(any(e.editor_on for e in events))  # la pestaña no se abrio

    def test_interviewer_answer_to_clarifying_question_updates_board(self):
        cop, ed, ans, events = self.exercise_then(
            "Define it yourself. State your assumption clearly, then implement that.",
            "## Respuesta: umbral\n» Okay, so I will assume eighty percent.\n# Q: threshold? -> 80% [assumed]",
            me="One question, what counts as isolated?")
        self.assertIsNotNone(ans)
        self.assertTrue(ans.clarify)
        self.assertTrue(ans.editor_on)
        self.assertIn("clarifying question", ed.calls[-1][1])
        self.assertIn("Respuesta", ans.editor)
        self.assertTrue(ans.board_only)  # todo va en la pizarra: AL VUELO no se escribe
        self.assertEqual(cop.llm.calls, [])

    def test_stops_at_question_then_f7_continues_with_proposal(self):
        entender = "## Entender\n» The input is one log line.\n# Q: fixed format? -> propose: yes => split"
        self.assertTrue(awaiting_answer(entender))
        # La pregunta ya no se escribe en negro: basta la frase roja con "?".
        self.assertTrue(awaiting_answer("## Entender\n» One line in, three fields out.\n# Input: one line\n"
                                        "» One question: is the format fixed, I would propose spaces?"))
        self.assertFalse(awaiting_answer(SCRIPT))  # ya tiene codigo
        segs = [Segment(0, 4, "Write a function that parses one log line.", THEM)]
        ed = FakeLLM(entender)
        cop, _ = self.make(segs, ed)
        self.wait(cop.step())
        ed.reply = "## Respuesta: formato\n» Okay, so I will assume it's fixed.\n## Código\n» I split it.\nx = 1"
        ans = cop.editor_now()  # nadie respondio: F7 sigue con la propuesta
        self.wait(ans)
        self.assertTrue(ans.clarify and ans.board_only)
        self.assertIn("clarifying question", ed.calls[-1][1])
        self.assertIn("## Código", ans.editor)

    def test_go_ahead_with_code_written_is_ignored_and_exercise_stays_open(self):
        # grabacion 2026-10-17 15:16: "Good. Go ahead." cerraba el ejercicio y la repregunta se quedaba sin pizarra
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM),
                Segment(6, 25, "Should I assume the file fits in memory?", ME),
                Segment(30, 32, "Good. Go ahead.", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, _ = self.make(segs[:1], ed)
        self.wait(cop.step())
        cop.snapshot = lambda: Transcript(list(segs), "t")
        self.assertIsNone(cop.step())  # el codigo ya esta: nada que decir
        segs += [Segment(33, 40, "Okay, I'll keep the Counter then.", ME),
                 Segment(45, 50, "Now suppose there's an extra space somewhere, how would you make it more robust?",
                         THEM)]
        ed.reply = "## Cambio: espacios\n» I split on any whitespace.\nparts = line.split()"
        ans = cop.step()
        self.wait(ans)
        self.assertTrue(ans.editor_on)  # el ejercicio sigue abierto
        self.assertIn("<editor_so_far>", ed.calls[-1][1])

    def test_clarify_with_nothing_to_write_keeps_exercise_open(self):
        _, _, ans, _ = self.exercise_then("Sounds reasonable, we can live with that assumption for now.", "NO_EDIT",
                                          me="Can I assume the file fits in memory?")
        self.assertTrue(ans.clarify)
        self.assertFalse(ans.editor_left)

    def test_board_fails_then_al_vuelo_fallback(self):
        segs = [Segment(0, 4, "Write a function that parses one log line.", THEM)]
        main = FakeLLM("Spoken fallback.")
        cop = Copilot(main, None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM("Sorry, no task here."))
        ans = cop.step()
        t0 = time.time()
        while not (ans.done and ans.text) and time.time() - t0 < 5:
            time.sleep(0.01)
        self.assertEqual(ans.text, "Spoken fallback.")  # la pizarra dio prosa: sale AL VUELO
        self.assertFalse(ans.board_only)

    def test_statement_without_exercise_is_ignored(self):
        segs = [Segment(0, 4, "That sounds fine to me, we use something very similar here.", THEM)]
        cop, _ = self.make(segs, FakeLLM(SCRIPT))
        self.assertIsNone(cop.step())

    def test_prose_never_shown_on_board(self):
        segs = [Segment(0, 4, "We'll cover coding in Python later. Want to start now?", THEM)]
        cop, events = self.make(segs, FakeLLM("This isn't a question I should answer. No task yet."))
        ans = cop.step()
        self.wait(ans)
        self.assertFalse(ans.editor_on)
        self.assertEqual(ans.editor, "")

    def test_topic_change_closes_the_exercise(self):
        cop, ed, ans, _ = self.exercise_then("OK, different topic. How would you find all web servers?", SCRIPT,
                                             wait=False)
        self.assertFalse(ans.editor_on)
        self.assertTrue(ans.editor_left)
        self.assertEqual(len(ed.calls), 1)  # el cambio de tema no consulta la pizarra
        later = Answer(99, ans.at + 30, "Why OpenSearch for this?")
        cop.answers.append(later)
        self.assertEqual(cop._editor_previous(later), "")  # ni las preguntas siguientes

    def test_story_never_goes_to_editor(self):
        _, ed, ans, _ = self.exercise_then("Tell me about a time you debugged something hard.", SCRIPT,
                                         wait=False)
        self.assertFalse(ans.editor_on)
        self.assertEqual(len(ed.calls), 1)

    def test_al_vuelo_sees_the_board(self):
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        main = FakeLLM("Spoken.")
        cop = Copilot(main, None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(SCRIPT))
        self.wait(cop.step())
        cop.editor_llm = FakeLLM("NO_EDIT")  # la pizarra no tiene nada que decir: entra AL VUELO
        segs.append(Segment(6, 25, "I would use a Counter.", ME))
        segs.append(Segment(30, 34, "Why did you choose that structure?", THEM))
        cop.step()
        t0 = time.time()
        while not main.calls and time.time() - t0 < 5:
            time.sleep(0.01)
        self.assertIn("<editor>", main.calls[-1][1])
        self.assertIn("counts = Counter()", main.calls[-1][1])

    def test_board_answer_in_exercise_has_no_competing_al_vuelo(self):
        # Grabacion 2026-10-18 09:26: la pizarra y AL VUELO respondieron a la vez y se contradecian.
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        main = FakeLLM("Spoken.")
        say = "## Solo decir\n» It would accept it, and that breaks the malformed-lines requirement."
        cop = Copilot(main, None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(SCRIPT))
        self.wait(cop.step())
        cop.editor_llm = FakeLLM(say)
        segs.append(Segment(6, 25, "I would use a Counter.", ME))
        segs.append(Segment(30, 34, "Would your function accept a line without the bytes field?", THEM))
        ans = cop.step()
        t0 = time.time()
        while not ans.editor_done and time.time() - t0 < 5:
            time.sleep(0.01)
        time.sleep(0.2)
        self.assertIn("Solo decir", ans.editor)
        self.assertEqual(main.calls, [])

    def test_f7_forces_editor(self):
        segs = [Segment(0, 4, "How would you approach this problem?", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, _ = self.make(segs, ed)
        first = cop.step()
        self.assertFalse(first.editor_on)
        ans = cop.editor_now()
        self.wait(ans)
        self.assertIs(ans, first)
        self.assertTrue(ans.editor_done)

    def test_never_in_interview_mode(self):
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        ed = FakeLLM(SCRIPT)
        cop, _ = self.make(segs, ed, mode="entrevista")
        self.assertIsNone(cop.step())
        self.assertIsNone(cop.editor_now())
        self.assertEqual(ed.calls, [])


if __name__ == "__main__":
    unittest.main()


class SupervisorTests(unittest.TestCase):
    BOARD = "## Código\n» I add them.\nprint(1 + 1)\n# -> 3"
    FIXED = "## Código\n» I add them.\nprint(1 + 1)\n# -> 2"

    def run_with(self, reply):
        segs = [Segment(0, 4, "Write code that adds one and one.", THEM)]
        sup = FakeLLM(reply)
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(self.BOARD), supervisor_llm=sup)
        ans = cop.step()
        t0 = time.time()
        while ans.editor_check in ("", "revisando") and time.time() - t0 < 10:
            time.sleep(0.02)
        return ans, sup

    def test_supervisor_fixes_in_place_and_marks_line(self):
        ans, sup = self.run_with(self.FIXED)
        self.assertEqual(ans.editor, self.FIXED)
        self.assertEqual(ans.editor_check, "corregido")
        self.assertEqual(ans.editor_changed, {3})  # solo "# -> 2"
        self.assertIn("exit code 0", sup.calls[0][1])  # se ejecuto el codigo de verdad
        self.assertIn("2", sup.calls[0][1].split("<run>")[1])
        self.assertIn("background-color", editor_html(ans.editor, ans.editor_changed))

    def test_supervisor_ok_leaves_board_untouched(self):
        ans, _ = self.run_with("OK")
        self.assertEqual(ans.editor, self.BOARD)
        self.assertEqual(ans.editor_check, "ok")
        self.assertEqual(ans.editor_changed, set())

    def test_unsafe_code_is_not_run(self):
        from speak.notes.editor import runnable_python
        self.assertTrue(runnable_python("import re\nprint(re.sub('a', 'b', 'a'))"))
        for code in ("import socket\nsocket.create_connection(('x', 80))", "import requests\nrequests.get('x')",
                     "import subprocess\nsubprocess.run(['ls'])", "import os\nos.remove('f')",
                     "#!/bin/bash\nset -euo pipefail\ngrep x y"):
            self.assertFalse(runnable_python(code), code)

    def test_run_code_catches_wrong_output(self):
        from speak.notes.editor import run_code
        rc, out = run_code("print(1 + 1)")
        self.assertEqual((rc, out), (0, "2"))
        rc, out = run_code("from collections import Counter\nprint(defaultdict)")
        self.assertNotEqual(rc, 0)
        self.assertIn("NameError", out)


class SupervisorFallbackTests(unittest.TestCase):
    """2026-10-17: el filtro de Opus 5.5 bloqueo una pizarra de seguridad y salia "✓ revisado" sin revisar."""

    class Refuses(FakeLLM):
        def complete(self, system, prompt, images=None):
            self.calls.append((system, prompt))
            raise RuntimeError("API Error: Opus 5.5's safeguards flagged this message")

    def run_with(self, fallback):
        segs = [Segment(0, 4, "Write code that adds one and one.", THEM)]
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(SupervisorTests.BOARD), supervisor_llm=self.Refuses(),
                      supervisor_fallback_llm=fallback)
        ans = cop.step()
        t0 = time.time()
        while ans.editor_check in ("", "revisando") and time.time() - t0 < 10:
            time.sleep(0.02)
        return ans

    def test_refusal_goes_to_fallback(self):
        fallback = FakeLLM(SupervisorTests.FIXED)
        ans = self.run_with(fallback)
        self.assertEqual(len(fallback.calls), 1)
        self.assertEqual(ans.editor_check, "corregido")
        self.assertEqual(ans.editor, SupervisorTests.FIXED)

    def test_no_reviewer_never_says_reviewed(self):
        ans = self.run_with(None)
        self.assertEqual(ans.editor_check, "sin revisar")
        self.assertEqual(ans.editor, SupervisorTests.BOARD)


class PurpleDiffTests(unittest.TestCase):
    def test_new_lines_purple_old_lines_black(self):
        before = "## Código\n» I start.\nclass a {\n  file { 'x':\n    ensure => file,\n  }\n}"
        part = "## Cambio: más\n» I add a parameter.\nclass a (\n  String $p = 'no',\n) {\n  file { 'x':\n" \
               "    ensure => file,\n  }\n}"
        out = editor_html(part, set(), before)
        self.assertIn('color:#7b1fa2;">  String $p = &#x27;no&#x27;,', out)  # nuevo: morado
        self.assertIn('color:#9e9e9e;">    ensure =&gt; file,', out)  # ya estaba: gris
        self.assertNotIn("#7b1fa2", editor_html(part))  # sin "antes" (ejercicio nuevo): nada morado


class CleanCodeTests(unittest.TestCase):
    def test_latest_full_code_without_notes_or_speech(self):
        from speak.notes.editor import clean_code
        board = ("## Entender\n» We parse a line.\n# Input: one line\n"
                 "## Código\n» I split it.\ndef parse(line):\n    return line.split()\n# -> ['a']\n"
                 "## Cambio: espacios\n» Now I strip first.\n# New: strip => no empty fields\n"
                 "def parse(line):\n» Strip, then split.\n    return line.strip().split()\n"
                 "## Solo decir\n» It stays the same.")
        self.assertEqual(clean_code(board), "def parse(line):\n    return line.strip().split()")

    def test_no_code_yet(self):
        from speak.notes.editor import clean_code
        self.assertEqual(clean_code("## Entender\n» We parse a line.\n# Input: one line"), "")


class ResearchPatternTests(unittest.TestCase):
    """Investigacion 2026-10-17: supervisor solo con senal, asserts, datos contra notas."""

    def test_clean_run_is_not_sent_to_supervisor(self):
        segs = [Segment(0, 4, "Write code that adds one and one.", THEM)]
        sup = FakeLLM("## Código\n» I changed it anyway.\nprint(1 + 1)")
        board = "## Código\n» I add them and check it.\nassert 1 + 1 == 2\nprint('all tests pass')"
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(board), supervisor_llm=sup)
        ans = cop.step()
        t0 = time.time()
        while ans.editor_check in ("", "revisando") and time.time() - t0 < 10:
            time.sleep(0.02)
        self.assertEqual(ans.editor_check, "ok")
        self.assertEqual(sup.calls, [])  # corre limpio: ni se llama ni se toca
        self.assertEqual(ans.editor, board)

    def test_narration_and_output_signals(self):
        from speak.notes.editor import narration_issues, output_mismatches
        self.assertTrue(output_mismatches("print(1 + 1)\n# -> 3", "2"))
        self.assertFalse(output_mismatches("print(1 + 1)\n# -> 2", "2"))
        self.assertTrue(narration_issues("## Entender\n» Hi.\n# a\n# b\n# c"))
        self.assertTrue(narration_issues("## Código\n» The interviewer asked for it.\nx = 1"))
        self.assertTrue(narration_issues("## Entender\n» One question?\n# Q: fixed? -> propose: yes"))
        self.assertFalse(narration_issues("## Entender\n» We parse a line.\n# Input: one line\n» Fixed format?"))

    def test_personal_facts_checked_against_notes(self):
        from speak.notes.copilot import unsupported_facts
        notes = "I have three AWS certifications. A ten-month internship at AWS. 108 people clicked."
        self.assertEqual(unsupported_facts("I earned five certifications at AWS.", notes), ["five certifications"])
        self.assertEqual(unsupported_facts("I have three AWS certifications.", notes), [])
        self.assertEqual(unsupported_facts("Kafka buffers five streams.", notes), [])  # no habla de Yo


class LivingCodeTests(unittest.TestCase):
    """Investigacion 2026-10-17: codigo oficial que guarda la app, cambios por nombre, corte duro."""

    def test_merge_replaces_by_name_and_keeps_the_rest(self):
        from speak.notes.editor import merge_code
        old = "from collections import Counter\n\ndef parse(line):\n    return line.split()\n\ndef top(xs):\n" \
              "    return Counter(xs)"
        merged = merge_code(old, "import re\n\ndef parse(line):\n    return line.strip().split()")
        self.assertIn("return line.strip().split()", merged)
        self.assertNotIn("return line.split()\n", merged)
        self.assertIn("def top(xs):", merged)
        self.assertLess(merged.index("import re"), merged.index("def parse"))

    def test_clean_code_is_the_official_merged_version(self):
        from speak.notes.editor import clean_code
        board = ("## Código\n» Two functions.\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
                 "## Cambio: a\n» Only a changes.\ndef a():\n    return 10")
        self.assertEqual(clean_code(board), "def a():\n    return 10\n\ndef b():\n    return 2")

    def test_hard_stop_after_the_question(self):
        from speak.notes.editor import stop_point
        s = "## Entender\n» We parse a line.\n# Input: one line\n» Fixed format, I would propose spaces?\n## Plan\n"
        self.assertTrue(s[:stop_point(s)].endswith("spaces?\n"))
        self.assertIsNone(stop_point("## Código\n» I write it.\nx = 1\n"))

    def test_board_stops_even_if_model_keeps_writing(self):
        segs = [Segment(0, 4, "Write a function that parses one log line.", THEM)]
        more = "## Entender\n» One line in.\n# Input: a line\n» Is the format fixed, I would propose spaces?\n" \
               "## Código\n» I write it all anyway.\ndef parse(x):\n    return x"
        cop, _ = self.make(segs, FakeLLM(more))
        ans = cop.step()
        t0 = time.time()
        while not ans.editor_done and time.time() - t0 < 5:
            time.sleep(0.01)
        self.assertNotIn("## Código", ans.editor)
        self.assertTrue(ans.editor.rstrip().endswith("spaces?"))

    def make(self, segs, editor_llm):
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=editor_llm)
        return cop, None

    def test_answer_prompt_has_glossary_and_used_answers(self):
        from speak.notes.copilot import answer_prompt
        _, user = answer_prompt("What is Puppet?", "", "", "", "llamada", glossary="Puppet, Zeek",
                                used=["hackathon_secure_tunnel"])
        self.assertIn("Puppet, Zeek", user)
        self.assertIn("hackathon_secure_tunnel", user)


class StableBoardTests(unittest.TestCase):
    """Grabacion 2026-10-17 21:56: la pregunta crecia y la pizarra se borraba y rehacia (3 min sin nada estable)."""

    def test_cambio_in_same_text_grays_lines_already_typed(self):
        text = ("## Código\n» I start.\ndef f(x):\n    return x\n"
                "## Cambio: doble\n» Only the return changes.\ndef f(x):\n    return 2 * x")
        out = editor_html(text)
        self.assertIn('color:#9e9e9e;">def f(x):', out)
        self.assertIn('color:#7b1fa2;">    return 2 * x', out)

    def test_growing_question_keeps_visible_board_and_appends(self):
        import threading as th
        gate = th.Event()

        class SlowLLM(FakeLLM):
            def __init__(self):
                super().__init__("")
                self.calls = 0

            def stream(self, system, user, cancel=None):
                self.calls += 1
                if self.calls == 1:
                    yield "## Código\n» I write it.\ndef top(lines):\n"
                    gate.wait(5)
                    yield "    return lines\n"
                else:
                    yield "## Qué cambia\n» First, tuples.\n# New: tuples => return pairs\n"

        segs = [Segment(0, 4, "Write a function that returns the top IPs from log lines.", THEM)]
        llm = SlowLLM()
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=llm)
        ans = cop.step()
        t0 = time.time()
        while "def top" not in ans.editor and time.time() - t0 < 5:
            time.sleep(0.01)
        segs.append(Segment(5, 9, "And return tuples with the count, please.", THEM))
        cop._start_editor(ans, Transcript(list(segs), "t"))  # la pregunta crecio
        self.assertIn("def top", ans.editor)  # no se borro
        gate.set()
        while "Qué cambia" not in ans.editor and time.time() - t0 < 5:
            time.sleep(0.01)
        self.assertLess(ans.editor.index("return lines"), ans.editor.index("Qué cambia"))
        self.assertEqual(llm.calls, 2)


class PruneNarrationTests(unittest.TestCase):
    def test_red_only_where_code_changes(self):
        from speak.notes.editor import prune_unchanged_narration
        before = "## Código\n» Start.\ndef f(xs, n):\n    total = 0\n    for x in xs:\n        total += x\n" \
                 "    return total"
        cambio = ("## Cambio: guardia\n» I add a guard for n.\ndef f(xs, n):\n» If n is zero, I stop early.\n"
                  "    if n <= 0:\n        return 0\n» Same loop as before.\n    total = 0\n    for x in xs:\n"
                  "        total += x\n» Same return.\n    return total\n## Prueba\n» Zero gives zero.\n"
                  "assert f([1], 0) == 0")
        out = prune_unchanged_narration(cambio, before)
        self.assertIn("I add a guard", out)  # la primera se queda
        self.assertIn("If n is zero", out)  # antes de lineas nuevas
        self.assertNotIn("Same loop", out)
        self.assertNotIn("Same return", out)
        self.assertIn("    for x in xs:", out)  # el codigo no se toca
        self.assertIn("Zero gives zero", out)  # fuera del Cambio, nada cambia


class SeparateTestsTests(unittest.TestCase):
    def test_tests_go_in_their_own_box(self):
        from speak.notes.editor import clean_code, clean_tests
        board = ("## Código\n» The function.\ndef f(x):\n    return x\n"
                 "## Prueba\n» One check.\nassert f(1) == 1\nprint(\"all tests pass\")")
        self.assertEqual(clean_code(board), "def f(x):\n    return x")
        self.assertEqual(clean_tests(board), "assert f(1) == 1\nprint(\"all tests pass\")")


class FluidBoardTests(unittest.TestCase):
    """Grabacion 2026-10-18 09:59: sin red se colgaba, cambios enormes, y el entrevistador hallaba los bugs."""

    def test_follow_here_marker_before_next_unsaid_line(self):
        text = "## Código\n» First.\nx = 1\n» Second.\ny = 2\n» Third.\nz = 3"
        out = editor_html(text, said=[True, False, False], cursor=True)
        self.assertLess(out.index("sigue aquí"), out.index("Second."))
        self.assertGreater(out.index("sigue aquí"), out.index("First."))
        self.assertNotIn("sigue aquí", editor_html(text, said=[False, False, False], cursor=True))

    def test_assert_with_new_expected_value_replaces_the_old_one(self):
        from speak.notes.editor import clean_tests
        board = ("## Prueba\n» Two checks.\nassert f(1) == 20.0\nassert f(2) == 7\nprint(\"all tests pass\")\n"
                 "## Prueba\n» Now thirty.\nassert f(1) == 30.0\nassert f(3) == 0\nprint(\"all tests pass\")")
        tests = clean_tests(board)
        self.assertNotIn("20.0", tests)
        self.assertIn("assert f(1) == 30.0", tests)
        self.assertIn("assert f(2) == 7", tests)
        self.assertTrue(tests.endswith('print("all tests pass")'))
        self.assertEqual(tests.count("all tests pass"), 1)

    def test_cross_check_finds_a_counterexample(self):
        from speak.notes.editor import cross_check
        code = "def biggest(xs):\n    return xs[0] if xs else None"
        ref = ("def reference(xs):\n    return max(xs) if xs else None\n"
               "def random_case(rng):\n    return ([rng.randint(-3, 3) for _ in range(rng.randint(0, 5))],)")
        self.assertIn("brute force gives", cross_check(code, ref, "biggest"))
        self.assertIsNone(cross_check("def biggest(xs):\n    return max(xs) if xs else None", ref, "biggest"))

    def test_stalled_model_shows_an_error_instead_of_waiting_forever(self):
        import threading as th
        from unittest import mock

        class Silent(FakeLLM):
            def stream(self, system, user, cancel=None):
                while not cancel.is_set():
                    time.sleep(0.01)
                return
                yield

        segs = [Segment(0, 4, "Write a function that returns the top IPs from log lines.", THEM)]
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=Silent(""))
        real = th.Timer
        with mock.patch("speak.notes.copilot.threading.Timer", lambda s, f: real(s / 300, f)):
            ans = cop.step()
            t0 = time.time()
            while "90 s" not in ans.editor_error and time.time() - t0 < 5:
                time.sleep(0.01)
        self.assertIn("F7", ans.editor_error)
        self.assertIn("90 s", ans.editor_error)
        self.assertFalse(ans.editor_pending)


class GeneralQuestionMidExerciseTests(unittest.TestCase):
    def test_general_question_during_exercise_still_gets_al_vuelo_at_once(self):
        segs = [Segment(0, 4, "Write a function that returns the top ten source IPs.", THEM)]
        main = FakeLLM("Spoken.")
        cop = Copilot(main, None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(SCRIPT))
        ans = cop.step()
        t0 = time.time()
        while not ans.editor_done and time.time() - t0 < 5:
            time.sleep(0.01)
        cop.editor_llm = FakeLLM("NO_EDIT")
        segs.append(Segment(6, 25, "I would use a Counter.", ME))
        segs.append(Segment(30, 34, "What do you know about our SOC?", THEM))
        ans2 = cop.step()
        self.assertFalse(ans2.board_only)


class SupervisorLeavesQuestionBoardTests(unittest.TestCase):
    def test_question_only_board_is_not_sent_to_the_supervisor(self):
        board = ("## Entender\n» So the function takes one log line.\n# Input: a line\n"
                 "» One question: is the format fixed, I would propose that?")
        segs = [Segment(0, 4, "Write a Python function to parse a simple log line.", THEM)]
        sup = FakeLLM("## Code\n» I will write it all.\ndef f(x):\n    return x")
        cop = Copilot(FakeLLM("x"), None, "", snapshot=lambda: Transcript(list(segs), "t"), now=lambda: 100.0,
                      mode="llamada", editor_llm=FakeLLM(board), supervisor_llm=sup)
        ans = cop.step()
        t0 = time.time()
        while (not ans.editor_done or ans.editor_check in ("", "revisando")) and time.time() - t0 < 5:
            time.sleep(0.01)
        self.assertIn("One question", ans.editor)
        self.assertNotIn("def f", ans.editor)
        self.assertEqual(sup.calls, [])
