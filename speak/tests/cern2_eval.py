"""Evalua el copiloto con los escenarios de la 2.a ronda del CERN (LLM real, gasta llamadas).

    .venv-speak\\Scripts\\python.exe -m speak.tests.cern2_eval [--only 0,5,9] [--workers 5] [--out dir]

Por respuesta: MEMORIA (respuesta preparada que salta al instante) y AL VUELO (LLM),
y un juez que puntua 1-5 y lista errores tecnicos, inventos sobre Yo, problemas para
leer en voz alta y si responde a la pregunta.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from speak.config import Config
from speak.llm_client import ClaudeCLIClient
from speak.notes.copilot import Copilot, split_warning
from speak.notes.instant import PreparedIndex
from speak.notes.pipeline import ME, THEM, Transcript
from speak.tests.cern2_scenarios import CHAINS
from speak.tests.copilot_eval import _SOURCE, load_library
from speak.transcriber import Segment

JUDGE = """You grade a live interview copilot. Yo (Maria) is a junior candidate in a CERN Computer Security
Office panel interview (2nd round). She READS the copilot's answer aloud, live, in English (not her native
language). You get Yo's notes (the only source of facts about Yo), the conversation, the question and the answer.
Grade strictly:
- technical_errors: anything technically wrong or misleading (security, Linux, networking, code).
- unsupported: claims about Yo's own experience, actions, readings or plans that are NOT in the notes. General
  knowledge or "how I would do it" is fine. "I read your article X" counts as a claim about Yo.
- answers_question: the first sentence directly answers what was asked.
- hard_to_read: phrases hard to read aloud live (long sentences > 25 words, colons/semicolons/parentheses in
  speech, symbols, code read out badly, "I'd", jargon soup).
- too_long: more than ~110 words for a normal question, or a story longer than ~150 words.
- missing: the key point an expert panel would expect and the answer lacks (empty if none).
- score: 1-5 (5 = an expert would be impressed and it's easy to say; 3 = acceptable; 1 = harmful).
Reply JSON only:
{"score": n, "technical_errors": [], "unsupported": [], "answers_question": true, "hard_to_read": [],
 "too_long": false, "missing": "", "fix": "<one concrete improvement, or empty>"}"""


def ask(cop: Copilot, segs: list, errors: list) -> str:
    tr = Transcript(list(segs), "t")
    errors.clear()
    ans = cop._answer(cop.pending_question(tr), tr)
    t0 = time.time()
    while not ans.done and not errors and time.time() - t0 < 150:
        time.sleep(0.1)
    return ans.text


def run_chain(i: int, chain: list[str], kb, brief, guide, index, cfg) -> list[dict]:
    llm = ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False)
    segs, t, rows = [], 0.0, []
    for q in chain:
        segs.append(Segment(t, t + 4.0, q, THEM))
        t += 5.0
        errors: list = []
        cop = Copilot(llm, kb, brief, snapshot=lambda s=segs: Transcript(list(s), "t"), now=lambda: t,
                      mode="llamada", guide=guide, on_status=errors.append)
        t0 = time.time()
        text = ""
        for wait in (0, 20, 60):  # sin texto = el LLM fallo (p. ej. limite de peticiones)
            time.sleep(wait)
            text = ask(cop, segs, errors)
            if text.strip():
                break
        secs = round(time.time() - t0, 1)
        note, rest = split_warning(text)
        cited = " ".join(_SOURCE.findall(rest))
        said = _SOURCE.sub("", rest).strip()
        m = index.match(q)
        rows.append({"chain": i, "q": q, "said": said, "note": note, "cited": cited, "secs": secs,
                     "words": len(said.split()), "memoria": m.key if m else None,
                     "context": [s.text for s in segs[:-1]]})
        segs.append(Segment(t, t + 20.0, said, ME))
        t += 21.0
    return rows


def judge(jl: ClaudeCLIClient, notes: str, row: dict) -> dict:
    conv = "\n".join(row["context"])
    raw = ""
    for wait in (0, 30, 90, 180):  # la API a veces limita peticiones un rato
        time.sleep(wait)
        try:
            raw = jl.complete(JUDGE, f"<notes>\n{notes}\n</notes>\n\n<conversation>\n{conv}\n</conversation>\n\n"
                                     f"<question>{row['q']}</question>\n\n<answer>\n{row['said']}\n</answer>")
            break
        except Exception:
            continue
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        return json.loads(m.group(0)) if m else {"score": 0, "fix": "(juez sin JSON)"}
    except json.JSONDecodeError:
        return {"score": 0, "fix": "(juez sin JSON)"}


def main(argv: list[str]) -> None:
    if "--only" not in argv and "--full" not in argv:
        raise SystemExit("Choose --only IDs for a small sample, or --full explicitly. "
                         "For bounded Codex runs use speak.tests.cern2_focused.")
    only, workers, out = None, 5, Path("cern2_eval_out")
    if "--only" in argv:
        only = {int(x) for x in argv[argv.index("--only") + 1].split(",")}
    if "--workers" in argv:
        workers = int(argv[argv.index("--workers") + 1])
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    kb, brief, guide, notes = load_library("cern2")
    index = PreparedIndex(kb.extra_texts(), min_score=cfg.COPILOT_INSTANT_MIN_SCORE,
                          min_precision=cfg.COPILOT_INSTANT_MIN_PRECISION)
    chains = [(i, c) for i, c in enumerate(CHAINS) if only is None or i in only]
    with ThreadPoolExecutor(workers) as pool:
        rows = [r for rs in pool.map(lambda ic: run_chain(ic[0], ic[1], kb, brief, guide, index, cfg), chains)
                for r in rs]
    jl = ClaudeCLIClient(cfg.LLM_MODEL, "medium", prewarm=False)
    with ThreadPoolExecutor(2) as pool:  # el juez es largo: pocas a la vez para no chocar con el limite
        verdicts = list(pool.map(lambda r: judge(jl, notes, r), rows))
    for r, v in zip(rows, verdicts):
        r["judge"] = v
    (out / "result.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    for r in rows:
        v = r["judge"]
        flags = [f"score={v.get('score')}"] + [f"{k}={v[k]}" for k in ("technical_errors", "unsupported",
                                                                         "hard_to_read") if v.get(k)]
        if not v.get("answers_question", True):
            flags.append("NO_RESPONDE")
        if v.get("too_long"):
            flags.append("LARGA")
        lines.append(f"## [{r['chain']}] {r['q']}\nMEMORIA: {r['memoria']} | {r['secs']}s | {r['words']} palabras\n"
                     f"{('⚠ ' + r['note']) if r['note'] else ''}\n{r['said']}\nFuente: {r['cited']}\n"
                     f"-> {'; '.join(flags)}\n   falta: {v.get('missing', '')}\n   fix: {v.get('fix', '')}\n")
    scores = [r["judge"].get("score", 0) for r in rows if r["judge"].get("score", 0)]
    summary = {"respuestas": len(rows), "juez_fallo": len(rows) - len(scores),
               "media": round(sum(scores) / max(len(scores), 1), 2),
               "<=3": sum(s <= 3 for s in scores),
               "errores_tecnicos": sum(bool(r["judge"].get("technical_errors")) for r in rows),
               "inventos": sum(bool(r["judge"].get("unsupported")) for r in rows),
               "no_responde": sum(not r["judge"].get("answers_question", True) for r in rows),
               "largas": sum(bool(r["judge"].get("too_long")) for r in rows),
               "segundos_medio": round(sum(r["secs"] for r in rows) / len(rows), 1),
               "con_memoria": sum(bool(r["memoria"]) for r in rows)}
    (out / "report.md").write_text("\n".join(lines) + "\nRESUMEN " + json.dumps(summary, ensure_ascii=False),
                                   encoding="utf-8")
    print("RESUMEN", json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
