"""Evaluacion del copiloto con el LLM real (no es una prueba unitaria: gasta
llamadas a `claude`).

    .venv-speak\\Scripts\\python.exe -m speak.tests.copilot_eval [cern] [--mode entrevista] [--out archivo.json]

Preguntas de la practica de CERN (2026-10-12) y fallos vistos en vivo. Por
respuesta mide:
- fuga: lo que se lee en voz alta habla de fuentes, de adivinar o de confirmar;
- anuncio: promete una historia sin contarla ("the cheese lab story is...");
- cita: la linea Fuente nombra la respuesta preparada que toca (si hay una);
- aviso: pone ⚠ cuando si hay respuesta preparada, o no lo pone cuando falta;
- inventado: un juez (otra llamada) lista lo que dice de Yo y no esta en la
  biblioteca (el conocimiento tecnico general no cuenta);
- largo, primer texto y tokens de cache.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from speak.config import Config
from speak.knowledge import KnowledgeBase
from speak.llm_client import ClaudeCLIClient
from speak.notes.copilot import Copilot, split_warning
from speak.notes.pipeline import THEM, Transcript
from speak.transcriber import Segment

LIBRARY = Path(__file__).resolve().parents[1] / "data" / "library"

# (pregunta, clave preparada que deberia usar; None = falta el dato (pide ⚠); "" = cualquiera)
CASES = [
    ("So, who are you? Tell me about yourself.", "tell_me_about_yourself"),
    ("You mentioned two engineering degrees, chemical and computing. Why both?", "why_two_degrees"),
    ("What did you take from chemical engineering that's useful in IT?", "chemical_engineering_useful"),
    ("Why are you applying to CERN, and to this team in particular?", "why_cern"),
    ("Why security, if your experience so far is in cloud and operations?", "why_security"),
    ("What was the worst incident you've been involved in, and how did you handle it?", "incident_hard_amadeus"),
    ("You worked with Kubernetes and OpenShift. What is your experience there?", "kubernetes_openshift"),
    ("How do you handle secrets and least privilege?", "secrets_and_least_privilege"),
    ("You said you kept the credentials in Key Vault. How exactly was the secret retrieved at runtime, "
     "and what identity was used?", "key_vault_details"),
    ("What service did you use to host and serve those landing pages?", "landing_pages_tech"),
    ("Tell me about a project you are proud of, and why.", "proud_project_landing_pages"),
    ("Tell me about a hard technical challenge you faced.", "hackathon_secure_tunnel"),
    ("Do you have a home lab, CTFs, anything on GitHub?", "learning_security_gaps"),
    ("Have you ever rotated or revoked a certificate in a live environment?", "cert_lifecycle_live"),
    ("When could you start, and are you willing to relocate to Geneva?", "salary_and_availability"),
    ("You said it uses your own authenticated access. How exactly was the authentication handled in the "
     "script? Did it use a token, a key, or something else?", "triage_script_details"),
    ("What bores you in IT?", ""),  # sin una clave: vale responder con lo que hay
    ("You said you already operate daily in English. How do you currently handle communication when team "
     "members are not native English speakers?", "non_native_communication"),
]

_LEAK = re.compile(r"\b(my|your) (sources|notes|docs)\b|not in (my|the|your) |won'?t guess|"
                   r"\bI'?d (want to )?confirm\b|follow up (with|on) (that|it)|aviso|don'?t have (that|the) "
                   r"(detail|exact)|can'?t speak to", re.I)
_TEASER = re.compile(r"\b(story|example) is the (best|clearest)\b|\bI can tell you about\b|"
                     r"\bhappy to (walk|tell)\b|\bthere'?s a story\b", re.I)
_SOURCE = re.compile(r"^\s*(?:Fuente|Source)s?:\s*(.*)$", re.I | re.M)

JUDGE_SYSTEM = """You check an interview answer against the candidate's own notes. List every claim the answer
makes about the candidate (Yo) - experience, projects, tools, numbers, dates, reasons, feelings - that the
NOTES do not support. Paraphrases of the notes are supported. General technical knowledge stated as general
knowledge or as "how I would do it" is NOT a claim about Yo.
Also judge whether the answer ANSWERS THE QUESTION: its opening directly gives what was asked (a "why" gets
a reason, a "how" gets the method, a yes/no gets yes or no), and the rest supports it instead of drifting into
unrelated experience. Reply with JSON only:
{"unsupported": ["<claim>", ...], "answers_question": true|false, "drift": "<what is off-topic, or empty>"}"""


def load_library(name: str) -> tuple[KnowledgeBase, str, str, str]:
    folder = LIBRARY / name
    read = lambda p: p.read_text(encoding="utf-8") if p.exists() else ""
    kb = KnowledgeBase()
    texts = []
    for path in sorted((folder / "extra").glob("*.md")):
        text = read(path)
        if text.strip():
            kb.add_text(path.stem, text)
            texts.append(f"<notes name=\"{path.stem}\">\n{text}\n</notes>")
    brief, guide = read(folder / "brief.md"), read(folder / "guide.md")
    # El juez ve tambien la guia: ahi hay datos ("the tunnel was AWS infrastructure").
    notes = (f"<notes name=\"brief\">\n{brief}\n</notes>\n<notes name=\"guide\">\n{guide}\n</notes>\n"
             + "\n".join(texts))
    return kb, brief, guide, notes


def keys_of(kb: KnowledgeBase) -> set[str]:
    return {m.group(1) for t in kb.extra_texts().values() for m in re.finditer(r"^## (\w+)", t, re.M)}


def check(answer: str, expected: str | None, keys: set[str]) -> dict:
    note, rest = split_warning(answer)
    cited = " ".join(_SOURCE.findall(rest))
    said = _SOURCE.sub("", rest).strip()
    cited_keys = set(re.findall(r"\w+", cited)) & keys
    return {
        "fuga": bool(_LEAK.search(said)),
        "anuncio": bool(_TEASER.search(said)),
        "cita_ok": not expected or expected in cited_keys or expected in cited,
        "aviso_mal": bool(note) if expected else (expected is None and not note),
        "palabras": len(said.split()),
        "said": said,
        "note": note,
        "cited": cited,
    }


def judge(llm: ClaudeCLIClient, notes: str, question: str, said: str) -> dict:
    raw = llm.complete(JUDGE_SYSTEM, f"<notes>\n{notes}\n</notes>\n\n<question>{question}</question>\n\n"
                                     f"<answer>\n{said}\n</answer>")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return {"unsupported": ["(juez sin JSON)"], "answers_question": True, "drift": ""}
    return {"unsupported": list(data.get("unsupported", [])),
            "answers_question": bool(data.get("answers_question", True)), "drift": data.get("drift", "")}


def run(name: str = "cern", mode: str = "llamada") -> dict:
    cfg = Config()
    kb, brief, guide, notes = load_library(name)
    keys = keys_of(kb)
    llm = ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT, prewarm=False)
    results = []
    for question, expected in CASES:
        segs = [Segment(0.0, 4.0, question, THEM)]
        cop = Copilot(llm, kb, brief, snapshot=lambda s=segs: Transcript(list(s), "t"), now=lambda: 10.0,
                      mode=mode, guide=guide)
        ans = cop._answer(cop.pending_question(Transcript(segs, "t")), Transcript(segs, "t"))
        t0 = time.time()
        while not ans.done and time.time() - t0 < 120:
            time.sleep(0.1)
        row = {"q": question, "expected": expected, **check(ans.text, expected, keys),
               "usage": dict(llm.last_usage), "secs": round(time.time() - t0, 1)}
        results.append(row)
        print(f"· {question[:60]:60} {row['secs']:5.1f}s cache_read={row['usage'].get('cache_read_input_tokens')}",
              flush=True)
    jl = ClaudeCLIClient(cfg.LLM_MODEL, "low", prewarm=False)
    with ThreadPoolExecutor(4) as pool:
        verdicts = list(pool.map(lambda r: judge(jl, notes, r["q"], r["said"]), results))
    for r, v in zip(results, verdicts):
        r["inventado"] = v["unsupported"]
        r["responde"] = v["answers_question"]
        r["desvio"] = v["drift"]
    return {"cases": results, "summary": summarize(results)}


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "casos": n,
        "fuga": sum(r["fuga"] for r in rows),
        "anuncio": sum(r["anuncio"] for r in rows),
        "cita_mal": sum(not r["cita_ok"] for r in rows),
        "aviso_mal": sum(r["aviso_mal"] for r in rows),
        "con_inventos": sum(bool(r["inventado"]) for r in rows),
        "inventos": sum(len(r["inventado"]) for r in rows),
        "largas_110": sum(r["palabras"] > 110 for r in rows),
        "no_responde": sum(not r.get("responde", True) for r in rows),
        "segundos_medio": round(sum(r["secs"] for r in rows) / n, 1),
        "cache_read_medio": round(sum(r["usage"].get("cache_read_input_tokens", 0) or 0 for r in rows) / n),
        "input_medio": round(sum((r["usage"].get("input_tokens", 0) or 0)
                                 + (r["usage"].get("cache_read_input_tokens", 0) or 0)
                                 + (r["usage"].get("cache_creation_input_tokens", 0) or 0) for r in rows) / n),
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    out, mode = None, "llamada"
    if "--mode" in args:
        i = args.index("--mode")
        mode = args[i + 1]
        del args[i:i + 2]
    if "--search" in args:  # control: notas por trozos buscados, no enteras
        args.remove("--search")
        import speak.notes.copilot as cp
        cp.FULL_NOTES_CHARS = 0
    if "--out" in args:
        i = args.index("--out")
        out = args[i + 1]
        del args[i:i + 2]
    report = run(args[0] if args else "cern", mode)
    for r in report["cases"]:
        flags = [k for k in ("fuga", "anuncio", "aviso_mal") if r[k]] + ([] if r["cita_ok"] else ["cita_mal"])
        if r["inventado"]:
            flags.append(f"inventado={len(r['inventado'])}")
        if not r.get("responde", True):
            flags.append(f"no_responde: {r.get('desvio', '')}")
        print(f"\n## {r['q']}\n{r['note']}\n{r['said']}\nFuente: {r['cited']}\n-> {', '.join(flags) or 'ok'}"
              + "".join(f"\n   - {c}" for c in r["inventado"]))
    print("\nRESUMEN", json.dumps(report["summary"], ensure_ascii=False))
    if out:
        Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
