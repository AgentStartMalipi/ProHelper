"""Evalua el copiloto completo (MEMORIA + AL VUELO + pizarra) con las preguntas de
ROUND2_PANEL_QUESTIONS (speak/tests/cern2_doc_scenarios.py). LLM real: gasta llamadas.

    .venv-speak\\Scripts\\python.exe -m speak.tests.cern2_doc_eval --out dir [--only 0,5] [--workers 2]

Por paso: si la pestaña Editor se abrio cuando debia (sin LLM), y dos jueces: uno
para lo que Yo lee (AL VUELO) y otro para el guion de pizarra.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from speak.config import Config
from speak.llm_client import ClaudeCLIClient, make_llm
from speak.notes.copilot import Copilot, split_warning
from speak.notes.instant import PreparedIndex
from speak.notes.pipeline import ME, THEM, Transcript
from speak.tests.cern2_doc_scenarios import CHAINS
from speak.tests.cern2_eval import judge
from speak.tests.copilot_eval import _SOURCE, load_library
from speak.transcriber import Segment

EDITOR_JUDGE = """You grade a shared-editor script for a live coding interview. Yo (a junior candidate) reads the
red lines ("» ...") aloud while typing the black lines (code, comments, ASCII). Boxes start with "## title".
"Solo decir" boxes hold only spoken lines (an answer by talking). You get the conversation, the question, what was
already on the editor before (if any) and the new script. Grade strictly, tracing the code yourself:
- code_errors: bugs, wrong expected outputs, undefined names, missing imports, wrong commands or flags.
- narration_ok: false if typed blocks lack a » line (more than ~4 code lines in a row without one) or » lines just
  read syntax aloud.
- consistency: false if it contradicts what is already on the editor or the conversation.
- confirmed_misuse: true if it writes "[confirmed]" for something the interviewer never said.
- fit: false if the script does not do what was asked (or a "Solo decir"/change box was the wrong choice).
- score 1-5 (5 = correct, clear, an interviewer would be impressed; 3 = usable with a fix; 1 = harmful).
Reply JSON only:
{"score": n, "code_errors": [], "narration_ok": true, "consistency": true, "confirmed_misuse": false,
 "fit": true, "fix": "<one concrete improvement, or empty>"}"""


def judge_editor(jl: ClaudeCLIClient, row: dict) -> dict:
    raw = ""
    prompt = (f"<conversation>\n{chr(10).join(row['context'])}\n</conversation>\n\n<question>{row['q']}</question>\n\n"
              f"<editor_before>\n{row['board_before'] or '(empty)'}\n</editor_before>\n\n"
              f"<new_script>\n{row['editor']}\n</new_script>")
    for wait in (0, 30, 90):
        time.sleep(wait)
        try:
            raw = jl.complete(EDITOR_JUDGE, prompt)
            break
        except Exception:
            continue
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else {"score": 0, "fix": "(juez sin JSON)"}
    except json.JSONDecodeError:
        return {"score": 0, "fix": "(juez sin JSON)"}


def routing_ok(expect: str, shown: bool) -> bool:
    return {"code": shown, "follow": shown, "no": not shown}.get(expect, True)


def run_chain(i: int, chain, kb, brief, guide, index, cfg) -> list[dict]:
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), kb, brief, snapshot=None, now=None,
                  mode="llamada", guide=guide, instant=index.match,
                  editor_llm=make_llm(cfg, effort=cfg.COPILOT_EDITOR_EFFORT))
    segs, t, rows = [], 0.0, []
    try:
        for q, expect in chain:
            segs.append(Segment(t, t + 4.0, q, THEM))
            t += 5.0
            tr = Transcript(list(segs), "t")
            cop.snapshot, cop.now = (lambda tr=tr: tr), (lambda t=t: t)
            board_before = ""
            t0 = time.time()
            ans = None
            for wait in (0, 20, 60):  # sin texto = el LLM fallo (p. ej. limite de peticiones)
                time.sleep(wait)
                q_pending = cop.pending_question(tr)
                ans = cop._answer(q_pending, tr)
                board_before = cop._editor_previous(ans)
                while not ans.done and time.time() - t0 < 200:
                    time.sleep(0.1)
                if ans.text.strip():
                    break
            secs = round(time.time() - t0, 1)
            while (ans.editor_pending or (ans.editor_on and not ans.editor_done)) and time.time() - t0 < 300:
                time.sleep(0.2)
            note, rest = split_warning(ans.text)
            said = _SOURCE.sub("", rest).strip()
            rows.append({"chain": i, "q": q, "expect": expect, "said": said, "note": note, "secs": secs,
                         "memoria": ans.instant_key or None, "editor_shown": ans.editor_on, "editor": ans.editor,
                         "board_before": board_before, "editor_secs": round(time.time() - t0, 1),
                         "routing_ok": routing_ok(expect, ans.editor_on),
                         "words": len(said.split()), "context": [s.text for s in segs[:-1]]})
            print(f"[{i}] {len(rows)}/{len(chain)} {secs}s editor={'si' if ans.editor_on else 'no'} "
                  f"({expect}) {'OK' if rows[-1]['routing_ok'] else 'MAL'}", flush=True)
            segs.append(Segment(t, t + 20.0, said, ME))
            t += 21.0
    finally:
        cop.stop()
    return rows


def main(argv: list[str]) -> None:
    out = Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    only = {int(x) for x in argv[argv.index("--only") + 1].split(",")} if "--only" in argv else None
    workers = int(argv[argv.index("--workers") + 1]) if "--workers" in argv else 2
    cfg = Config()
    kb, brief, guide, notes = load_library("cern2")
    index = PreparedIndex(kb.extra_texts(), min_score=cfg.COPILOT_INSTANT_MIN_SCORE,
                          min_precision=cfg.COPILOT_INSTANT_MIN_PRECISION)
    chains = [(i, c) for i, c in enumerate(CHAINS) if only is None or i in only]
    with ThreadPoolExecutor(workers) as pool:
        rows = [r for rs in pool.map(lambda ic: run_chain(ic[0], ic[1], kb, brief, guide, index, cfg), chains)
                for r in rs]
    (out / "result.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    jl = ClaudeCLIClient(cfg.LLM_MODEL, "medium", prewarm=False)
    with ThreadPoolExecutor(2) as pool:
        verdicts = list(pool.map(lambda r: judge(jl, notes, r), rows))
        ed_rows = [r for r in rows if r["editor"]]
        ed_verdicts = list(pool.map(lambda r: judge_editor(jl, r), ed_rows))
    for r, v in zip(rows, verdicts):
        r["judge"] = v
    for r, v in zip(ed_rows, ed_verdicts):
        r["editor_judge"] = v
    (out / "result.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    scores = [r["judge"].get("score", 0) for r in rows if r["judge"].get("score", 0)]
    ed_scores = [r["editor_judge"].get("score", 0) for r in ed_rows if r["editor_judge"].get("score", 0)]
    summary = {
        "respuestas": len(rows), "juez_fallo": len(rows) - len(scores),
        "media_al_vuelo": round(sum(scores) / max(len(scores), 1), 2), "al_vuelo_<=3": sum(s <= 3 for s in scores),
        "errores_tecnicos": sum(bool(r["judge"].get("technical_errors")) for r in rows),
        "inventos": sum(bool(r["judge"].get("unsupported")) for r in rows),
        "no_responde": sum(not r["judge"].get("answers_question", True) for r in rows),
        "con_memoria": sum(bool(r["memoria"]) for r in rows),
        "segundos_al_vuelo": round(sum(r["secs"] for r in rows) / len(rows), 1),
        "pestaña_correcta": f"{sum(r['routing_ok'] for r in rows)}/{len(rows)}",
        "pizarras": len(ed_rows), "media_pizarra": round(sum(ed_scores) / max(len(ed_scores), 1), 2),
        "pizarra_<=3": sum(s <= 3 for s in ed_scores),
        "pizarra_errores_codigo": sum(bool(r["editor_judge"].get("code_errors")) for r in ed_rows),
        "pizarra_narracion_mal": sum(not r["editor_judge"].get("narration_ok", True) for r in ed_rows),
        "pizarra_confirmed_mal": sum(bool(r["editor_judge"].get("confirmed_misuse")) for r in ed_rows),
        "pizarra_segundos": round(sum(r["editor_secs"] for r in ed_rows) / max(len(ed_rows), 1), 1),
    }
    lines = []
    for r in rows:
        v = r["judge"]
        flags = [f"score={v.get('score')}"] + [f"{k}={v[k]}" for k in ("technical_errors", "unsupported",
                                                                         "hard_to_read") if v.get(k)]
        if not v.get("answers_question", True):
            flags.append("NO_RESPONDE")
        lines.append(f"## [{r['chain']}] {r['q']}\nMEMORIA: {r['memoria']} | {r['secs']}s | pestaña: "
                     f"{'Editor' if r['editor_shown'] else 'Respuestas'} ({r['expect']}) "
                     f"{'OK' if r['routing_ok'] else 'MAL'}\n{r['said']}\n-> {'; '.join(flags)}\n"
                     f"   fix: {v.get('fix', '')}\n")
        if r["editor"]:
            e = r["editor_judge"]
            lines.append(f"### Pizarra ({r['editor_secs']}s) -> score={e.get('score')} errores={e.get('code_errors')} "
                         f"narracion={e.get('narration_ok')} coherente={e.get('consistency')} "
                         f"confirmed_mal={e.get('confirmed_misuse')} encaja={e.get('fit')}\n   fix: {e.get('fix', '')}\n"
                         f"```\n{r['editor']}\n```\n")
    (out / "report.md").write_text("\n".join(lines) + "\nRESUMEN " + json.dumps(summary, ensure_ascii=False),
                                   encoding="utf-8")
    print("RESUMEN", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
