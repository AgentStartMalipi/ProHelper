"""MEMORIA solo cuando casa con el centro de la pregunta, no con un "dame un ejemplo" al final.

Simulacro 2026-10-18 12:26: "What is SSRF...? Give me one concrete example." saco la historia del
login, cuyo titulo incluye "Give me a concrete example of that". Aqui se prueba cada pregunta
preparada de la biblioteca cern2 seguida de un remate corto: la MEMORIA, si sale, es la suya.
"""

import re
import unittest

from speak.notes.instant import PreparedIndex
from speak.tests.copilot_eval import load_library

TAILS = ["Give me one concrete example.", "Can you give me an example?", "What would you check first?",
         "Who fixed it?", "What exactly would you do?", "Give me a concrete example of that."]


class InstantCoreTests(unittest.TestCase):
    def test_short_tail_never_brings_another_topic(self):
        kb, *_ = load_library("cern2")
        idx = PreparedIndex(kb.extra_texts(), min_score=0.9, min_precision=0.75)
        wrong = []
        for text in kb.extra_texts().values():
            for m in re.finditer(r"(?m)^##\s+(\w+)\s+-\s+(.+)$", text):
                question = m.group(2).split("|")[0].strip().rstrip("?. ") + "?"
                for tail in TAILS:
                    hit = idx.match(f"Thanks, let's move on. {question} {tail}")
                    if hit and hit.key != m.group(1):
                        wrong.append(f"{m.group(1)} + {tail!r} -> {hit.key}")
        self.assertEqual(wrong, [])


if __name__ == "__main__":
    unittest.main()
