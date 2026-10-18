"""Bucle barato de errores: repite SOLO las preguntas que fallaron, con reglas (sin juez).

    python -m speak.tests.cern2_fix_loop                 # lista los casos y las comprobaciones gratis
    python -m speak.tests.cern2_fix_loop --case headers  # 1-2 llamadas: solo esa pregunta
    python -m speak.tests.cern2_fix_loop --all           # todos los casos (~1-2 llamadas cada uno)

El contexto (preguntas anteriores, lo que Yo respondio, la pizarra) sale de una
ejecucion guardada (--base, por defecto cern2_review/doc_it1/result.json): solo la
pregunta del caso llama al modelo. Cada resultado se anade a cern2_review/fix_loop.jsonl.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from speak.config import Config
from speak.llm_client import ClaudeCLIClient, make_llm
from speak.notes.copilot import Answer, Copilot, split_warning
from speak.notes.editor import changes_topic, is_story, needs_editor, parse_editor
from speak.notes.instant import PreparedIndex
from speak.notes.pipeline import ME, THEM, Transcript
from speak.tests.copilot_eval import _SOURCE, load_library
from speak.transcriber import Segment

# id: (inicio de la pregunta, comprobaciones). Comprobaciones:
#   memoria=clave  editor=True/False  said_has=regex  said_not=regex  max_run=n (lineas seguidas sin »)
CASES = {
    "least_priv": ("What's least privilege? Give an example", dict(
        memoria="least_privilege_example", said_not=r"couldn.t (?:modify|write|change)|can.t (?:modify|write)")),
    "headers": ("Write a function that checks a website for missing security", dict(
        said_not=r"X[- ]Frame[- ]Security", said_has=r"X[- ]Frame[- ]Options")),
    "vm_fleet": ("At CERN, VMs run on OpenStack", dict(memoria="vm_fleet_openstack", said_has=r"security group")),
    "m365_first": ("Give me one Microsoft 365 setting", dict(memoria="m365_first_setting", said_has=r"legacy")),
    "pick_you": ("Thanks, that's all from my side", dict(
        said_not=r"calm under pressure|in a few months|from AWS infrastructure")),
    "domains": ("And for domains?", dict(editor=True)),
    "kafka": ("Why put Kafka between sensors and storage?", dict(editor=False)),
    "spraying": ("How would you detect password spraying against the SSO?", dict(editor=False)),
    "cve_hour": ("A new CVE in a web framework is published", dict(editor=False)),
    "opensearch": ("Why OpenSearch for this", dict(editor=False)),
    "connlog_narration": ("Given a Zeek conn.log, tab-separated", dict(editor=True, max_run=8)),
    "scanner_narration": ("Write a scanner that goes through a repository", dict(editor=True, max_run=8)),
    "as_mentioned": ("Zeek versus Suricata or Snort?", dict(said_not=r"\bas I (?:mentioned|said)\b")),
}
ALWAYS_NOT = r"\bI['’]d\b|\[confirmed\]"


def max_run(script: str) -> int:
    """Lineas escritas seguidas sin una linea » (lo que Yo no narra)."""
    run = worst = 0
    for _, lines in parse_editor(script):
        for kind, line in lines:
            if kind == "say":
                run = 0
            elif line.strip():
                run += 1
                worst = max(worst, run)
    return worst


def check(spec: dict, said: str, memoria: str, editor_on: bool, editor: str) -> list[str]:
    fails = []
    if "memoria" in spec and memoria != spec["memoria"]:
        fails.append(f"MEMORIA {memoria or '-'} != {spec['memoria']}")
    if "editor" in spec and editor_on != spec["editor"]:
        fails.append(f"pestaña Editor {'abierta' if editor_on else 'cerrada'}, debia estar "
                     f"{'abierta' if spec['editor'] else 'cerrada'}")
    if said is not None:
        if spec.get("said_has") and not re.search(spec["said_has"], said, re.I):
            fails.append(f"falta /{spec['said_has']}/")
        if spec.get("said_not") and re.search(spec["said_not"], said, re.I):
            fails.append(f"dice /{spec['said_not']}/")
        if re.search(ALWAYS_NOT, said + "\n" + (editor or "")):
            fails.append("I'd o [confirmed]")
    if spec.get("max_run") and editor and max_run(editor) > spec["max_run"]:
        fails.append(f"{max_run(editor)} lineas seguidas sin rojo (max {spec['max_run']})")
    return fails


def find(rows: list[dict], prefix: str) -> tuple[list[dict], dict]:
    target = next(r for r in rows if r["q"].startswith(prefix))
    chain = [r for r in rows if r["chain"] == target["chain"]]
    return chain[:chain.index(target)], target


def offline(rows, index) -> None:
    """Gratis: MEMORIA y deteccion de la pizarra, sin llamar al modelo."""
    for cid, (prefix, spec) in CASES.items():
        _, target = find(rows, prefix)
        m = index.match(target["q"])
        notes = []
        if "memoria" in spec:
            notes.append("MEMORIA ok" if m and m.key == spec["memoria"] else f"MEMORIA {m.key if m else '-'} ✗")
        if spec.get("editor") and target["chain"] is not None:
            notes.append(f"detecta codigo: {needs_editor(target['q'])}")
        print(f"{cid:18} {' | '.join(notes) or '(necesita el modelo)'}")


def run_case(cid: str, rows, kb, brief, guide, index, cfg) -> dict:
    prefix, spec = CASES[cid]
    before, target = find(rows, prefix)
    editor_llm = make_llm(cfg, effort=cfg.COPILOT_EDITOR_EFFORT)
    cop = Copilot(ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False), kb, brief, snapshot=None,
                  now=None, mode="llamada", guide=guide, instant=index.match, editor_llm=editor_llm)
    segs, t = [], 0.0
    closed = False
    for n, r in enumerate(before, 1):  # el contexto guardado: sin llamadas
        segs.append(Segment(t, t + 4.0, r["q"], THEM))
        left = changes_topic(r["q"]) or is_story(r["q"])
        closed = (closed or left) and not needs_editor(r["q"])
        # Tras un cambio de tema la version actual ya no sigue la pizarra: no se arrastra la vieja.
        editor = "" if closed else r["editor"]
        cop.answers.append(Answer(n, t, r["q"], text=r["said"], done=True, editor=editor,
                                  editor_on=bool(editor), editor_done=True,
                                  editor_fresh=bool(editor) and not r["board_before"], editor_left=left))
        t += 5.0
        segs.append(Segment(t, t + 20.0, r["said"], ME))
        t += 21.0
    segs.append(Segment(t, t + 4.0, target["q"], THEM))
    tr = Transcript(list(segs), "fix")
    cop.snapshot, cop.now = (lambda: tr), (lambda: t + 5.0)
    t0 = time.time()
    ans = cop._answer(cop.pending_question(tr), tr)
    calls = 1 + (ans.id in cop._editor_cancels)
    while (not ans.done or ans.editor_pending or (ans.editor_on and not ans.editor_done)) \
            and time.time() - t0 < 240:
        time.sleep(0.2)
    cop.stop()
    _, rest = split_warning(ans.text)
    said = _SOURCE.sub("", rest).strip()
    fails = check(spec, said, ans.instant_key, ans.editor_on, ans.editor)
    return {"case": cid, "q": target["q"], "pass": not fails, "fails": fails, "calls": calls,
            "secs": round(time.time() - t0, 1), "memoria": ans.instant_key, "said": said,
            "editor_on": ans.editor_on, "editor": ans.editor, "at": time.strftime("%Y-%m-%d %H:%M")}


def main(argv: list[str]) -> None:
    base = Path(argv[argv.index("--base") + 1]) if "--base" in argv else Path("cern2_review/doc_it1/result.json")
    rows = json.loads(base.read_text(encoding="utf-8"))
    cfg = Config()
    kb, brief, guide, _ = load_library("cern2")
    index = PreparedIndex(kb.extra_texts(), min_score=cfg.COPILOT_INSTANT_MIN_SCORE,
                          min_precision=cfg.COPILOT_INSTANT_MIN_PRECISION)
    if "--case" not in argv and "--all" not in argv:
        offline(rows, index)
        return
    ids = list(CASES) if "--all" in argv else argv[argv.index("--case") + 1].split(",")
    log = Path("cern2_review/fix_loop.jsonl")
    total = 0
    for cid in ids:
        res = run_case(cid, rows, kb, brief, guide, index, cfg)
        total += res["calls"]
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
        print(f"{'PASA' if res['pass'] else 'FALLA'} {cid} ({res['calls']} llamadas, {res['secs']}s) "
              f"{'; '.join(res['fails'])}", flush=True)
        if "--show" in argv:
            print("   AL VUELO:", res["said"].replace("\n", " "))
            if res["editor"]:
                print("   PIZARRA:\n" + res["editor"])
    print(f"llamadas al modelo: {total}")


if __name__ == "__main__":
    main(sys.argv[1:])
