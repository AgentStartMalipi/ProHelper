"""Genera la pizarra con el modelo real, paso a paso (Entender -> [sin respuesta, sigue] -> codigo),
y EJECUTA las lineas negras tal cual. Pseudocodigo: comprueba que no sea Python y que este narrado.

    python -m speak.tests.cern2_board_loop --all
    python -m speak.tests.cern2_board_loop --case 0,3
Resultados en cern2_review/board_loop.jsonl. ~2 llamadas por caso (3 si hay repregunta).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from speak.config import Config
from speak.llm_client import make_llm
from speak.notes.copilot import _said_for_reading
from speak.notes.editor import awaiting_answer, editor_prompt, parse_editor
from speak.tests.board_runner import run, typed_code

# (pregunta, repregunta o None, tipo: "python" | "pseudo")
CASES = [
    ("Write a small Python function that takes a list of timestamped login events and returns whether a failure "
     "spike is isolated to one region or global.", None, "python"),
    ("Write a script that compares the loaded kernel modules to an allowlist and reports the rest.", None, "python"),
    ("Given a scanner's JSON output, a list of package and severity, write something that fails the CI build if "
     "there's any critical.", None, "python"),
    ("Can you write pseudocode for detecting password spraying against our single sign-on?", None, "pseudo"),
    ("Write a Python function that parses one log line with a timestamp, a user and an action.",
     "Before we go on, can you write the same logic as pseudocode, for someone who doesn't read Python?", "pseudo"),
]


def say_run(board: str) -> int:
    run_ = worst = 0
    for title, lines in parse_editor(board):
        if title.lower().startswith("prueba"):  # datos de prueba: excepcion permitida
            continue
        for kind, line in lines:
            run_ = 0 if kind == "say" else run_ + bool(line.strip())
            worst = max(worst, run_)
    return worst


def generate(llm, q: str, follow: str | None) -> tuple[str, int]:
    conv = f"Ellos: {q}"
    s, u = editor_prompt(q, conv)
    board = _said_for_reading(llm.complete(s, u).strip())
    calls = 1
    if awaiting_answer(board):  # nadie responde la aclaracion: sigue con la propuesta (F7)
        conv += "\nYo: (asks the clarifying question)\nEllos: Your call, go on."
        s, u = editor_prompt("Your call, go on.", conv, board, clarify=True)
        board += "\n\n" + _said_for_reading(llm.complete(s, u).strip())
        calls += 1
    cut = len(board)  # donde empieza la respuesta a la repregunta
    if follow:
        conv +=f"\nYo: (finishes the code)\nEllos: {follow}"
        s, u = editor_prompt(follow, conv, board)
        board += "\n\n" + _said_for_reading(llm.complete(s, u).strip())
        calls += 1
    return board, calls, cut


def check(board: str, kind: str, follow: str | None, cut: int | None = None) -> tuple[list[str], str]:
    cut = len(board) if cut is None else cut
    fails = []
    if not re.search(r"^\s*»", board, re.M):
        fails.append("sin frases rojas")
    if say_run(board) > 8:
        fails.append(f"{say_run(board)} lineas seguidas sin rojo")
    out = ""
    if kind == "python" or follow:
        code = typed_code(board[:cut] if follow else board)
        rc, out = run(code)
        if rc != 0:
            fails.append("el codigo copiado tal cual falla: " + (out.strip().splitlines() or ["?"])[-1][:120])
    if kind == "pseudo":
        tail = board[cut:] if follow else board
        typed = typed_code(tail)
        if re.search(r"^\s*(?:def |import |from \w+ import)", typed, re.M):
            fails.append("el pseudocodigo trae Python")
        if not re.search(r"\b(?:FOR|IF|RETURN|FUNCTION|for each|if|return)\b", typed):
            fails.append("no parece pseudocodigo")
    return fails, out


def main(argv: list[str]) -> None:
    ids = range(len(CASES)) if "--all" in argv else [int(x) for x in argv[argv.index("--case") + 1].split(",")]
    cfg = Config()
    llm = make_llm(cfg, effort=cfg.COPILOT_EDITOR_EFFORT)
    total = ok = 0
    for i in ids:
        q, follow, kind = CASES[i]
        t0 = time.time()
        board, calls, cut = generate(llm, q, follow)
        total += calls
        fails, out = check(board, kind, follow, cut)
        ok += not fails
        rec = {"case": i, "q": q, "kind": kind, "pass": not fails, "fails": fails, "board": board, "run": out,
               "calls": calls, "secs": round(time.time() - t0, 1), "at": time.strftime("%Y-%m-%d %H:%M")}
        with Path("cern2_review/board_loop.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{'PASA' if not fails else 'FALLA'} {i} [{kind}] ({calls} llamadas) {'; '.join(fails)}", flush=True)
        if "--show" in argv:
            print(board + ("\n--- ejecucion:\n" + out if out else "") + "\n")
    print(f"{ok}/{len(list(ids))} pasan; llamadas al modelo: {total}")


if __name__ == "__main__":
    main(sys.argv[1:])
