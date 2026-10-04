"""Perfil de entrevista (.md): parseo, recarga y uso en los prompts."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from speak.answer_generator import evaluation_prompt, question_prompt
from speak.context_manager import ContextManager
from speak.interview_profile import banned_hits, load
from speak.question_classifier import QType

SAMPLE = """# Interview profile
## 5. Skills
**Wording rules:**
- Avoid these words: passionate, results-driven, highly motivated, fast learner.

## 7. Active applications
| Company | Role | Likely focus in interviews |
|---|---|---|
| Amazon (several: SDE Berlin; DE Madrid) | SDE / Data Engineer | Online Assessment; Leadership Principles |
| Google | SWE II (L3), Málaga | Coding interviews (DS&A) |
| Others submitted earlier | Celonis, Oracle | — |

## 8. Weak spots
1. Coding interviews.
"""


class InterviewProfileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "INTERVIEW_PROFILE.md"
        self.path.write_text(SAMPLE, encoding="utf-8")

    def test_parse_targets_and_banned_words(self):
        p = load(self.path)
        self.assertEqual([t.label for t in p.targets],
                         ["Amazon — SDE / Data Engineer", "Google — SWE II (L3), Málaga"])
        self.assertIn("SDE Berlin", p.targets[0].block())  # el detalle no se pierde
        self.assertEqual(p.banned_words, ["passionate", "results-driven", "highly motivated", "fast learner"])
        self.assertEqual(banned_hits("I'm a passionate, results-driven engineer", p.banned_words),
                         ["passionate", "results-driven"])
        self.assertEqual(banned_hits("compassionate", p.banned_words), [])

    def test_reloads_when_file_changes(self):
        p = load(self.path)
        self.assertFalse(p.refresh())
        self.path.write_text(SAMPLE + "| x |", encoding="utf-8")
        t = time.time() + 5
        os.utime(self.path, (t, t))
        self.assertTrue(p.refresh())
        self.assertTrue(p.text.endswith("| x |"))

    def test_missing_file(self):
        p = load(Path(self.dir.name) / "nope.md")
        self.assertFalse(p.loaded)
        self.assertEqual(p.targets, [])

    def test_prompts_use_profile_and_target(self):
        ctx = ContextManager()
        ctx.interview = load(self.path)
        ctx.profile.target = "Amazon — SDE / Data Engineer"
        q = question_prompt(ctx)
        self.assertIn("SOURCE OF TRUTH", q.user)
        self.assertIn("Leadership Principles", q.user)
        self.assertIn("TARGET ROLE", q.user)
        ctx.start_exchange("Tell me about a time you failed.", QType.BEHAVIORAL.value)
        ctx.record_answer("I worked for a bank")
        e = evaluation_prompt(ctx, QType.BEHAVIORAL)
        self.assertIn("Profile check", e.system)
        self.assertIn("SOURCE OF TRUTH", e.user)

    def test_without_profile_prompts_are_unchanged(self):
        ctx = ContextManager()
        ctx.start_exchange("What is a hash map?", QType.TECHNICAL_CONCEPT.value)
        self.assertNotIn("Profile check", evaluation_prompt(ctx, QType.TECHNICAL_CONCEPT).system)
        self.assertNotIn("SOURCE OF TRUTH", question_prompt(ctx).user)

    def test_copilot_never_reads_the_interview_profile(self):
        # El perfil es para practicar; el copiloto de llamadas no debe usarlo.
        root = Path(__file__).resolve().parents[1]
        for f in ("notes/copilot.py", "notes/live.py", "knowledge.py", "ui/notes_window.py"):
            self.assertNotIn("interview_profile", (root / f).read_text(encoding="utf-8"), f)


if __name__ == "__main__":
    unittest.main()
