"""Respuestas que Maria puede decir sin cortarse: primera frase cortisima (empieza a
hablar ya, sin silencio) y frases cortas que termina. Casos de su practica del
17/10/2026 (grabacion 20261017-143125). Sin juez: reglas.

    python -m speak.tests.cern2_sayable --all [--show]
    python -m speak.tests.cern2_sayable --case 0,3
Cada resultado se anade a cern2_review/sayable.jsonl.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from speak.config import Config
from speak.llm_client import ClaudeCLIClient
from speak.notes.copilot import Copilot, split_warning
from speak.notes.instant import PreparedIndex
from speak.notes.pipeline import ME, THEM, Transcript
from speak.tests.copilot_eval import _SOURCE, load_library
from speak.transcriber import Segment

# Objetivo del prompt: 10 / 15 / 75. La prueba falla solo si se vuelve a lo de antes (frases de 25-40).
FIRST_MAX, SENT_MAX, TOTAL_MAX = 11, 20, 80

Q1 = ("Good afternoon. I'm Stefan Lueders, computer security officer. Let's begin with a scenario. We discover "
      "credentials for a privileged service account exposed in a public GitHub repo. Revoking them immediately could "
      "interrupt experiments and even risk losing scientific data. As a security architect, what decision would you "
      "make, and how would you justify it from both a security and operational perspective? I'm interested in your "
      "reasoning, not just follow the policy. Go ahead.")
A1 = ("I would not revoke the credentials the instant we find them. I would contain first and revoke in a controlled "
      "way. If there's no sign of active misuse, I would rotate the credential, then revoke the old one.")
Q2 = ("Trading off containment against continuity. But what precise signal would make you say this is active "
      "compromise, we pull the plug now? Name one concrete indicator you'd trust, one you would not, and why?")
A2 = ("The indicator I would trust is activity that doesn't match the account's normal pattern. I would not trust a "
      "single failed login alone.")
Q3 = ("Alright. You've now recommended a controlled rotation unless there's evidence of active misuse. Imagine the "
      "scientist says a brief rotation window could corrupt a running experiment. Do you still rotate? And if yes, "
      "how do you defend that decision to them? Calmly but firmly.")
A3 = "Yes, I still rotate. The credential is already public, so the risk is not theoretical."
Q4 = ("Suppose they push back and say we accept the risk, do nothing until the end of the week. Who ultimately "
      "decides, and what do you do if they disagree with your call?")

CASES = [  # (conversacion previa [(quien, texto)], pregunta)
    ([], Q1),
    ([(THEM, Q1), (ME, A1)], Q2),
    ([(THEM, Q1), (ME, A1), (THEM, Q2), (ME, A2)], Q3),
    ([(THEM, Q1), (ME, A1), (THEM, Q2), (ME, A2), (THEM, Q3), (ME, A3)], Q4),
    ([], "You're describing segmentation and monitoring, but not how you'd enforce segmentation in a "
         "heterogeneous legacy environment. Name one concrete mechanism, and one failure mode that could undermine it."),
]


def sentences(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return [s for ln in lines for s in re.split(r"(?<=[.!?])\s+", ln) if s.strip()]


def check(said: str) -> list[str]:
    sents = sentences(said)
    words = [len(s.split()) for s in sents]
    fails = []
    if not sents:
        return ["vacia"]
    if words[0] > FIRST_MAX:
        fails.append(f"primera frase de {words[0]} palabras (max {FIRST_MAX})")
    long = [w for w in words if w > SENT_MAX]
    if long:
        fails.append(f"{len(long)} frases de mas de {SENT_MAX} palabras ({max(long)})")
    if sum(words) > TOTAL_MAX:
        fails.append(f"{sum(words)} palabras en total (max {TOTAL_MAX})")
    return fails


def run(i: int, kb, brief, guide, index, cfg) -> dict:
    before, q = CASES[i]
    segs, t = [], 0.0
    for who, text in before:
        segs.append(Segment(t, t + 8.0, text, who))
        t += 10.0
    segs.append(Segment(t, t + 8.0, q, THEM))
    tr = Transcript(segs, "say")
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), kb, brief, snapshot=lambda: tr,
                  now=lambda: t + 10.0, mode="llamada", guide=guide, instant=index.match)
    t0 = time.time()
    ans = cop._answer(cop.pending_question(tr), tr)
    while not ans.done and time.time() - t0 < 150:
        time.sleep(0.1)
    cop.stop()
    _, rest = split_warning(ans.text)
    said = _SOURCE.sub("", rest).strip()
    fails = check(said)
    return {"case": i, "q": q[-90:], "pass": not fails, "fails": fails, "said": said,
            "words": len(said.split()), "at": time.strftime("%Y-%m-%d %H:%M")}


def main(argv: list[str]) -> None:
    ids = range(len(CASES)) if "--all" in argv else [int(x) for x in argv[argv.index("--case") + 1].split(",")]
    cfg = Config()
    kb, brief, guide, _ = load_library("cern2")
    index = PreparedIndex(kb.extra_texts(), min_score=cfg.COPILOT_INSTANT_MIN_SCORE,
                          min_precision=cfg.COPILOT_INSTANT_MIN_PRECISION)
    log = Path("cern2_review/sayable.jsonl")
    ok = 0
    for i in ids:
        r = run(i, kb, brief, guide, index, cfg)
        ok += r["pass"]
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{'PASA' if r['pass'] else 'FALLA'} {i} ({r['words']} palabras) {'; '.join(r['fails'])}", flush=True)
        if "--show" in argv:
            print("    " + r["said"].replace("\n", " / "))
    print(f"{ok}/{len(list(ids))} pasan; llamadas al modelo: {len(list(ids))}")


if __name__ == "__main__":
    main(sys.argv[1:])
