"""Repite una grabacion real turno a turno con el copiloto actual (pizarra + supervisor).

    python -m speak.tests.replay_recording speak/data/notes/<carpeta> [--from mm:ss] [--to mm:ss] [--no-supervisor]

Por cada turno de Ellos muestra la pizarra nueva y avisa de: frases rojas que hablan del
entrevistador en tercera persona, la pizarra empezando de cero a mitad de ejercicio, y nombres
de clase o funcion que cambian. Gasta 1-2 llamadas por turno (3 con supervisor).
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path

from speak.config import Config
from speak.llm_client import ClaudeCLIClient, make_llm
from speak.notes.copilot import Copilot
from speak.notes.editor import parse_editor
from speak.notes.pipeline import ME, THEM, Transcript
from speak.tests.copilot_eval import load_library
from speak.transcriber import Segment


def secs(mmss: str) -> int:
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("speak.notes.copilot").setLevel(logging.INFO)  # tiempos y fuerza bruta
    folder = Path(argv[0])
    lo = secs(argv[argv.index("--from") + 1]) if "--from" in argv else 0
    hi = secs(argv[argv.index("--to") + 1]) if "--to" in argv else 10 ** 6
    segs = []
    for line in folder.joinpath("transcript_live.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\[(\d+:\d+)\] (Ellos|Yo): (.*)", line)
        if m and lo <= secs(m[1]) <= hi:
            t = secs(m[1])
            segs.append(Segment(t, t + 4.0, m[3], THEM if m[2] == "Ellos" else ME))
    cfg = Config()
    kb, brief, guide, _ = load_library("cern2")
    sup = fb = None
    if "--no-supervisor" not in argv:
        sup = make_llm(cfg, model=cfg.COPILOT_SUPERVISOR_MODEL, effort=cfg.COPILOT_SUPERVISOR_EFFORT)
        fb = make_llm(cfg, model=cfg.COPILOT_SUPERVISOR_FALLBACK_MODEL, effort=cfg.COPILOT_SUPERVISOR_EFFORT)
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), kb, brief, snapshot=None, now=None,
                  mode="llamada", guide=guide, editor_llm=make_llm(cfg, effort=cfg.COPILOT_EDITOR_EFFORT),
                  supervisor_llm=sup, supervisor_fallback_llm=fb)
    names, warnings = set(), []
    for n, seg in enumerate(segs, 1):
        if seg.speaker != THEM:
            continue
        tr = Transcript(segs[:n], "replay")
        cop.snapshot, cop.now = (lambda tr=tr: tr), (lambda tr=tr: tr.segments[-1].end + 3.0)
        ans = cop.step()
        stamp = f"{int(seg.start // 60):02}:{int(seg.start % 60):02}"
        print(f"\n######## [{stamp}] Ellos: {seg.text}")
        if ans is None:
            print("(no dispara)")
            continue
        t0 = time.time()
        while (ans.editor_pending or (ans.editor_on and not ans.editor_done) or ans.editor_check == "revisando"
               or not ans.done) and time.time() - t0 < 300:
            time.sleep(0.2)
        kind = "aclaracion" if ans.clarify else "pizarra" if ans.editor_on else "respuesta"
        print(f"[{kind}{' · ' + ans.editor_check if ans.editor_check else ''}]")
        print(ans.editor if ans.editor_on else ans.text)
        boxes = parse_editor(ans.editor) if ans.editor_on else []
        for _, lines in boxes:
            for k, line in lines:
                if k == "say" and re.search(r"\bthe interviewer\b|\bYo\b", line):
                    warnings.append(f"[{stamp}] habla del entrevistador en tercera persona: {line[:70]}")
        if names and boxes and boxes[0][0].lower().startswith("entender"):
            warnings.append(f"[{stamp}] la pizarra empezo de cero a mitad de ejercicio")
        for found in re.findall(r"^\s*(?:class|def)\s+(\w+)", ans.editor, re.M):
            names.add(found)
    cop.stop()
    from speak.notes.editor import clean_code, clean_tests, run_code
    board = cop._board_at(segs[-1].end + 10.0) if segs else ""
    if board:
        final = "\n\n".join(x for x in (clean_code(board), clean_tests(board)) if x)
        print("\n======== codigo oficial final (pestaña Código):\n" + final)
        from speak.notes.editor import runnable_python
        print("======== al ejecutarlo:", run_code(final) if runnable_python(final) else "(no es Python: no se ejecuta)")
    print("\n======== avisos:", *(warnings or ["ninguno"]), sep="\n  ")
    print("  nombres de clase/funcion:", sorted(names))


if __name__ == "__main__":
    main(sys.argv[1:])
