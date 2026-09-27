"""Prueba de punta a punta de Notas en vivo + copiloto, con voces de Windows
y Whisper real. Lenta (~2 min) y solo en Windows: se salta salvo con

    set SPEAK_E2E=1          (Whisper real, copiloto con LLM de mentira)
    set SPEAK_E2E_LLM=1      (ademas, Claude de verdad: ~5 llamadas)
    .venv-speak\\Scripts\\python.exe -m unittest speak.tests.test_live_e2e -v

El detalle (transcripcion, cuando disparo cada respuesta) sale con
    .venv-speak\\Scripts\\python.exe -m speak.tests.live_e2e --show
"""

from __future__ import annotations

import os
import statistics
import unittest


@unittest.skipUnless(os.environ.get("SPEAK_E2E") == "1", "lenta: SPEAK_E2E=1 para correrla")
class LiveEndToEndTests(unittest.TestCase):
    def test_two_party_call(self):
        from speak.tests.live_e2e import run

        real = os.environ.get("SPEAK_E2E_LLM") == "1"
        res = run("base", "", real_llm=real)
        print("\n" + res.summary())
        self.assertLess(res.wer_them, 0.15, res.transcript)
        self.assertEqual(res.missed, [], res.summary())
        self.assertEqual([f for f in res.false if not f.startswith("prematura")], [], res.summary())
        self.assertTrue(res.rewrite_ok, res.summary())
        self.assertLess(statistics.median(res.lag), 5.0, res.summary())
        triggers = [a["trigger_after_end"] for a in res.answers if a["line"] and a["first_text_after_end"]]
        self.assertTrue(all(t < 4.0 for t in triggers), res.summary())
        if real:
            first = [a["first_text_after_end"] for a in res.answers if a["first_text_after_end"] is not None]
            self.assertLess(max(first), 8.0, res.summary())
            english = [a["answer"] for a in res.answers if a["answer"]]
            self.assertTrue(all(" the " in f" {t.lower()} " or " we " in f" {t.lower()} " for t in english),
                            "las respuestas a preguntas en ingles deben salir en ingles")


if __name__ == "__main__":
    unittest.main()
