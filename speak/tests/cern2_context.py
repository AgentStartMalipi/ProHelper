"""Referencias a incidentes con contexto y sin repetirse (grabacion 20261017-182634: "how the CERN
attack in July worked" sin contexto, y dos veces). Tambien la politica de Conditional Access que el
entrevistador corrigio. Sin juez: reglas. ~1 llamada por caso.

    python -m speak.tests.cern2_context --all [--show]
Resultados en cern2_review/context.jsonl.
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

JULY = r"\bJuly\b|\b108\b|One click"
CONTEXT = r"wrote about|article|One click to many|108|five thousand|campaign"
# Volver a CONTARLO (no una referencia corta como "that July phishing campaign"):
REEXPLAIN = r"wrote about|article|One click to many|108|five thousand"

Q1 = ("Good afternoon. I'm Stefan Lueders. You have recently joined CERN, and you're reviewing Microsoft 365 "
      "authentication settings. You discover that device code authentication is enabled for thousands of users. You "
      "believe it creates a phishing risk, but some engineering teams legitimately depend on it for command line tools "
      "and devices. Would you block it, restrict it, or leave it enabled? Walk me through your reasoning.")
A1 = ("I would restrict it, not fully block it. The risk is real: in July, your team wrote about a device code phishing "
      "campaign, One click to many, and 108 people clicked. First, I would check the logs to see who uses device code.")
Q2 = ("I'm the lead of a scientific engineering team. One of our critical research workflows depends on device code "
      "authentication, and your restrictions could interrupt an experiment that cannot easily be restarted. How would "
      "you explain the risk to me, negotiate a mitigation and decide whether to grant an exception?")
Q3 = ("Describe how you'd configure a Microsoft Entra Conditional Access policy to control device code "
      "authentication. Specifically, how would you target the policy, enforce the restriction, and avoid disrupting "
      "legitimate engineering workflows?")
Q4 = "What is the biggest security risk to CERN right now, in your opinion?"

# (conversacion previa, pregunta, comprobacion)
CASES = [
    ([], Q1, "first"),                       # si nombra julio, con contexto
    ([(THEM, Q1), (ME, A1)], Q2, "again"),   # ya lo dijo: no volver a explicarlo ni usarlo de argumento
    ([], Q3, "ca"),                          # bloquear para todos + excluir el grupo, con Authentication flows
    ([(THEM, Q1), (ME, A1)], Q4, "again"),
    ([], Q4, "first"),
]


def check(said: str, kind: str) -> list[str]:
    fails = []
    if kind == "first" and re.search(JULY, said) and not re.search(CONTEXT, said, re.I):
        fails.append("nombra julio sin contexto")
    if kind == "again":
        if re.search(REEXPLAIN, said, re.I):
            fails.append("vuelve a explicar el caso de julio (ya lo dijo)")
        if re.search(r"how the (?:CERN )?attack in July", said, re.I):
            fails.append("'the attack in July' otra vez")
    if kind == "ca":
        if not re.search(r"authentication flows?", said, re.I):
            fails.append("no usa la condicion Authentication flows")
        if not re.search(r"\bexclud", said, re.I):
            fails.append("no excluye el grupo aprobado (bloqueo para todos)")
    return fails


def run(i: int, kb, brief, guide, index, cfg) -> dict:
    before, q, kind = CASES[i]
    segs, t = [], 0.0
    for who, text in before:
        segs.append(Segment(t, t + 8.0, text, who))
        t += 10.0
    segs.append(Segment(t, t + 8.0, q, THEM))
    tr = Transcript(segs, "ctx")
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), kb, brief, snapshot=lambda: tr,
                  now=lambda: t + 10.0, mode="llamada", guide=guide, instant=index.match)
    t0 = time.time()
    ans = cop._answer(cop.pending_question(tr), tr)
    while not ans.done and time.time() - t0 < 150:
        time.sleep(0.1)
    cop.stop()
    _, rest = split_warning(ans.text)
    said = _SOURCE.sub("", rest).strip()
    fails = check(said, kind)
    return {"case": i, "kind": kind, "q": q[-80:], "pass": not fails, "fails": fails, "memoria": ans.instant_key,
            "said": said, "at": time.strftime("%Y-%m-%d %H:%M")}


def main(argv: list[str]) -> None:
    ids = range(len(CASES)) if "--all" in argv else [int(x) for x in argv[argv.index("--case") + 1].split(",")]
    cfg = Config()
    kb, brief, guide, _ = load_library("cern2")
    index = PreparedIndex(kb.extra_texts(), min_score=cfg.COPILOT_INSTANT_MIN_SCORE,
                          min_precision=cfg.COPILOT_INSTANT_MIN_PRECISION)
    ok = 0
    for i in ids:
        r = run(i, kb, brief, guide, index, cfg)
        ok += r["pass"]
        with Path("cern2_review/context.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{'PASA' if r['pass'] else 'FALLA'} {i} [{r['kind']}] M={r['memoria'] or '-'} {'; '.join(r['fails'])}",
              flush=True)
        if "--show" in argv:
            print("    " + r["said"].replace("\n", " / "))
    print(f"{ok}/{len(list(ids))} pasan; llamadas al modelo: {len(list(ids))}")


if __name__ == "__main__":
    main(sys.argv[1:])
