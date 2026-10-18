"""Pizarra fluida como en la guia del matching engine: todo lo que se escribe tiene su frase roja,
cada pregunta se dice en voz alta, se para en la pregunta y retoma las que quedaron sin responder.
Flujo completo con el Copilot real (sin supervisor: mide lo que escribe la pizarra sola). Sin juez.

    python -m speak.tests.cern2_narration --all [--show]
Resultados en cern2_review/narration.jsonl.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from speak.config import Config
from speak.llm_client import ClaudeCLIClient, make_llm
from speak.notes.copilot import Copilot
from speak.notes.editor import awaiting_answer, parse_editor, run_code, runnable_python, typed_code
from speak.notes.pipeline import ME, THEM, Transcript
from speak.transcriber import Segment

# Conversaciones (quien, texto). Tras cada turno de Ellos se mira la pizarra.
CASES = [
    ("puppet (grabacion 18:52)", [
        (THEM, "Right. Now let's ground that in something practical. Write a Puppet manifest snippet that ensures a "
               "security setting, for example disabling password SSH login. Show the resource and the key parameters."),
        (ME, "So the task is a Puppet manifest snippet for a security setting. One question first."),
        (THEM, "Take a moment. What you're missing is validation and service handling. Show me a Puppet class that "
               "disables root login and password authentication, makes sure sshd is running, checks the config before "
               "applying, and reloads only when the configuration changes."),
        (ME, "So the task is a Puppet class for SSH hardening with validation and reload. Should I use the core file "
             "resource?"),
        (THEM, "Exactly. Go ahead and write it."),
    ]),
    ("ssh brute force", [
        (THEM, "Write a Python function that takes a list of login events, each with a timestamp, an IP and an event "
               "type, and returns the IPs with five or more failed SSH logins within any sixty second window."),
        (ME, "One question: is the window sliding, any sixty seconds, or fixed minutes?"),
        (THEM, "Sliding. And the events may not be sorted."),
    ]),
    ("log parser, sin respuesta", [
        (THEM, "Write a Python function to parse a simple log line and extract the timestamp, the user and the action."),
        (ME, "Is the format always the same? I would propose space separated fields."),
        (THEM, "Your call, go on."),
    ]),
]


def problems(board: str, fresh: bool) -> list[str]:
    out, quiet = [], 0
    boxes = parse_editor(board)
    prev_say = ""
    for title, lines in boxes:
        code_box = re.match(r"(?:c[oó]digo|code|cambio|prueba)", title, re.I)
        quiet = 0
        for kind, line in lines:
            if kind == "say":
                prev_say, quiet = line, 0
                continue
            s = line.strip()
            if not s:
                continue
            if s.startswith("# Q:") and "[" not in s:
                out.append(f"pregunta escrita en negro (solo se dice): {s[:60]}")
            if ("[confirmed]" in s or "[assumed]" in s) and not prev_say:
                out.append(f"decision sin frase roja: {s[:60]}")
            if s.startswith("#") and not code_box:
                quiet += 1
                if quiet == 3:
                    out.append(f"3 notas seguidas sin rojo en '{title}'")
            prev_say = "" if s.startswith("# Q:") else prev_say
    asked = any(k == "say" and l.rstrip().endswith("?") for _, ls in boxes for k, l in ls)
    if fresh and asked and not awaiting_answer(board) and "[assumed]" not in board and "[confirmed]" not in board:
        out.append("pregunto pero no se paro (ya hay codigo)")
    return out


def run_case(i: int, cfg) -> dict:
    name, turns = CASES[i]
    sup = fb = None
    if SUPERVISED:  # como en la app: el supervisor revisa y anade lo que falte
        sup = make_llm(cfg, model=cfg.COPILOT_SUPERVISOR_MODEL, effort=cfg.COPILOT_SUPERVISOR_EFFORT)
        fb = make_llm(cfg, model=cfg.COPILOT_SUPERVISOR_FALLBACK_MODEL, effort=cfg.COPILOT_SUPERVISOR_EFFORT)
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), None, "", snapshot=None, now=None,
                  mode="llamada", editor_llm=make_llm(cfg, effort=cfg.COPILOT_EDITOR_EFFORT),
                  supervisor_llm=sup, supervisor_fallback_llm=fb)
    segs, t, steps, fails = [], 0.0, [], []
    for who, text in turns:
        segs.append(Segment(t, t + 6.0, text, who))
        t += 8.0
        if who != THEM:
            continue
        tr = Transcript(list(segs), "n")
        cop.snapshot, cop.now = (lambda tr=tr: tr), (lambda t=t: t + 2.0)
        ans = cop.step()
        t0 = time.time()
        while ans and (ans.editor_pending or (ans.editor_on and not ans.editor_done)
                       or ans.editor_check == "revisando") and time.time() - t0 < 300:
            time.sleep(0.2)
        part = ans.editor if ans else ""
        steps.append({"them": text, "board": part})
        for p in problems(part, fresh=len(steps) == 1):
            fails.append(f"turno {len(steps)}: {p}")
    cop.stop()
    board = "\n\n".join(s["board"] for s in steps)
    if "[assumed]" not in board and "[confirmed]" not in board and re.search(r"^» .*\?\s*$", board, re.M):
        fails.append("ninguna pregunta quedo resuelta ([assumed]/[confirmed])")
    code = typed_code(board)
    run = None
    if runnable_python(code):
        rc, run = run_code(code)
        if rc != 0:
            fails.append("el codigo no corre: " + (run.splitlines() or ["?"])[-1][:100])
    return {"case": i, "name": name, "pass": not fails, "fails": fails, "steps": steps, "run": run,
            "at": time.strftime("%Y-%m-%d %H:%M")}


SUPERVISED = False


def main(argv: list[str]) -> None:
    global SUPERVISED
    SUPERVISED = "--supervised" in argv
    ids = range(len(CASES)) if "--all" in argv else [int(x) for x in argv[argv.index("--case") + 1].split(",")]
    cfg = Config()
    ok = 0
    for i in ids:
        r = run_case(i, cfg)
        ok += r["pass"]
        with Path("cern2_review/narration.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{'PASA' if r['pass'] else 'FALLA'} {i} {r['name']}: {'; '.join(r['fails'])}", flush=True)
        if "--show" in argv:
            for s in r["steps"]:
                print(f"--- Ellos: {s['them'][:90]}\n{s['board']}")
    print(f"{ok}/{len(list(ids))} pasan")


if __name__ == "__main__":
    main(sys.argv[1:])
