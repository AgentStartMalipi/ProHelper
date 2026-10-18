"""Puntos flojos de la 1.a ronda (Puppet, trazabilidad en contenedores): donde encajan, el
copiloto los aplica y deja ver que Maria los estudio desde entonces. Sin juez: reglas.

    python -m speak.tests.cern2_weak_spots              # lista de casos (gratis)
    python -m speak.tests.cern2_weak_spots --case 1,4   # solo esos (1 llamada cada uno)
    python -m speak.tests.cern2_weak_spots --all
Cada resultado se anade a cern2_review/weak_spots.jsonl.
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

LEARNED = r"since (?:our|the|my) first (?:conversation|interview)|weak spot|been (?:reading|learning|studying)|(?:went|going|gone) back over|struggled with"
CLAIMED = (r"\bI (?:have )?(?:configured|used|deployed|wrote|managed|ran|set up)\b[^.]{0,40}\bPuppet\b"
           r"|\bPuppet\b[^.]{0,30}\bI (?:configured|deployed|used)\b|\bmy Puppet\b|(?<!n.t )used Puppet in production")

# (pregunta, tema esperado: "puppet" | "containers" | None = no debe aparecer)
CASES = [
    ("How would you roll out a new security setting to all of our Linux servers?", "puppet"),
    ("Someone keeps re-enabling password login for SSH on a server. How would you stop it and notice it?", "puppet"),
    ("How would you make sure fifteen thousand machines all have the same hardened SSH configuration?", "puppet"),
    ("How do you detect configuration drift on our hosts?", "puppet"),
    ("How would you verify that a hardening baseline is really applied across the whole fleet?", "puppet"),
    ("You'll have to pick up our tools quickly. Give me an example of something you learned recently on your own.",
     "puppet"),
    ("What did you take away from our first interview?", "puppet"),
    ("What part of this role worries you, and how would you deal with it?", "puppet"),
    ("How would you investigate a suspicious process running inside a Kubernetes pod?", "containers"),
    ("Last time your answer on containers was only about the network. What would you do differently now?",
     "containers"),
    ("A container in production starts making strange outbound connections. Walk me through your investigation.",
     "containers"),
    # Ya lo dijo en la respuesta anterior: aplica Puppet pero NO repite la frase de aprendizaje.
    ("How would you verify that a hardening baseline is really applied across the whole fleet?", "puppet_again"),
    ("What is SSRF and why is it dangerous in a cloud?", None),
    ("How do you store passwords in a web app?", None),
    ("Explain XSS. Stored versus reflected?", None),
]


PRIOR_Q = "How do you detect configuration drift on our hosts?"
PRIOR_SAID = ("I would use Puppet. That was my weak spot in our first interview, so I've been reading about it since. "
              "The agent pulls its catalog and corrects drift on the next run, and the run reports show it.")


def check(said: str, topic: str | None) -> list[str]:
    fails = []
    if re.search(CLAIMED, said, re.I):
        fails.append("dice que uso/configuro Puppet")
    if topic == "puppet":
        if not re.search(r"\bPuppet\b", said):
            fails.append("no aplica Puppet")
        if not re.search(LEARNED, said, re.I):
            fails.append("no deja ver que lo estudio desde la 1.a ronda")
    elif topic == "puppet_again":
        if not re.search(r"Puppet", said):
            fails.append("no aplica Puppet")
        if re.search(LEARNED, said, re.I):
            fails.append("repite la frase de aprendizaje (ya la dijo)")
    elif topic == "containers":
        if not re.search(r"\b(?:process|parent|execve|syscall|runtime|Falco|eBPF)\b", said, re.I):
            fails.append("no habla de lo que pasa dentro del contenedor")
        if not re.search(LEARNED, said, re.I):
            fails.append("no deja ver que lo estudio desde la 1.a ronda")
    else:
        if re.search(r"\bPuppet\b|weak spot|first (?:conversation|interview)", said, re.I):
            fails.append("lo mete donde no encaja")
    return fails


def run(i: int, kb, brief, guide, index, cfg) -> dict:
    q, topic = CASES[i]
    segs = [Segment(0, 4, q, THEM)]
    if topic == "puppet_again":  # conversacion previa en la que Yo ya dijo que lo estudio
        segs = [Segment(0, 4, PRIOR_Q, THEM), Segment(5, 25, PRIOR_SAID, ME), Segment(30, 34, q, THEM)]
    tr = Transcript(segs, "weak")
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), kb, brief, snapshot=lambda: tr,
                  now=lambda: segs[-1].end + 2.0, mode="llamada", guide=guide, instant=index.match)
    t0 = time.time()
    ans = cop._answer(cop.pending_question(tr), tr)
    while not ans.done and time.time() - t0 < 150:
        time.sleep(0.1)
    cop.stop()
    _, rest = split_warning(ans.text)
    said = _SOURCE.sub("", rest).strip()
    fails = check(said, topic)
    return {"case": i, "q": q, "topic": topic, "pass": not fails, "fails": fails, "memoria": ans.instant_key,
            "said": said, "secs": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%d %H:%M")}


def main(argv: list[str]) -> None:
    if "--case" not in argv and "--all" not in argv:
        for i, (q, topic) in enumerate(CASES):
            print(f"{i:2} [{topic or 'no'}] {q}")
        return
    ids = range(len(CASES)) if "--all" in argv else [int(x) for x in argv[argv.index("--case") + 1].split(",")]
    cfg = Config()
    kb, brief, guide, _ = load_library("cern2")
    index = PreparedIndex(kb.extra_texts(), min_score=cfg.COPILOT_INSTANT_MIN_SCORE,
                          min_precision=cfg.COPILOT_INSTANT_MIN_PRECISION)
    log = Path("cern2_review/weak_spots.jsonl")
    ok = 0
    for i in ids:
        r = run(i, kb, brief, guide, index, cfg)
        ok += r["pass"]
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{'PASA' if r['pass'] else 'FALLA'} {i} [{r['topic'] or 'no'}] M={r['memoria'] or '-'} "
              f"{'; '.join(r['fails'])}", flush=True)
        if "--show" in argv:
            print("    " + r["said"].replace("\n", " "))
    print(f"{ok}/{len(list(ids))} pasan; llamadas al modelo: {len(list(ids))}")


if __name__ == "__main__":
    main(sys.argv[1:])
