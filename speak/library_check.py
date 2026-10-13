"""Revision de consistencia de una entrevista contra tu perfil, ANTES de la
llamada (no corre en vivo: no cuesta nada durante la entrevista).

    .venv-speak\\Scripts\\python.exe -m speak.library_check cern [--profile ruta.json]

Compara el brief y las respuestas preparadas de data/library/<entrevista>/ con
candidate_profile.json y lista:
- contradicciones (empresa, fechas, herramientas, numeros que no cuadran);
- datos de tus notas que el perfil no tiene (quiza toca actualizar el perfil).
Medido 2026-10-12: la razon de la doble carrera estaba en el perfil y no en
CERN (el copiloto la invento), y Docplanner seguia diciendo "JavaScript" cuando
ya no aplicaba.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from .config import DATA_DIR, Config
from .llm_client import ClaudeCLIClient

LIBRARY = DATA_DIR / "library"
DEFAULT_PROFILE = Path(__file__).resolve().parents[2] / "JOBSEARCH" / "candidate_profile.json"

CHECK_SYSTEM = """You compare a candidate's interview notes (NOTES) with her master profile (PROFILE), both
written by or for the same person. Find:
1. contradictions: a fact in NOTES that conflicts with PROFILE (different company, employer, date, duration,
   tool, technology, number, degree, place, who did what). Different wording of the same fact is NOT a
   contradiction; neither is NOTES leaving something out.
2. not_in_profile: concrete facts in NOTES (tools, numbers, dates, companies, events) that PROFILE does not
   mention at all. Skip opinions, motivations and how she would do something.
Be precise and quote briefly. Reply with JSON only:
{"contradictions": [{"section": "<## key or brief>", "notes": "<what NOTES says>", "profile": "<what PROFILE
says>"}], "not_in_profile": [{"section": "<## key or brief>", "fact": "<the fact>"}]}"""


def library_text(name: str) -> str:
    folder = LIBRARY / name
    if not folder.is_dir():
        raise SystemExit(f"no existe la entrevista {name!r} en {LIBRARY}")
    parts = []
    brief = folder / "brief.md"
    if brief.exists():
        parts.append(f"<notes name=\"brief\">\n{brief.read_text(encoding='utf-8')}\n</notes>")
    for path in sorted((folder / "extra").glob("*.md")):
        parts.append(f"<notes name=\"{path.stem}\">\n{path.read_text(encoding='utf-8')}\n</notes>")
    return "\n\n".join(parts)


def check(name: str, profile: Path, llm=None) -> dict:
    if not profile.exists():
        raise SystemExit(f"no encuentro el perfil: {profile} (usa --profile o SPEAK_PROFILE)")
    if llm is None:
        cfg = Config()
        llm = ClaudeCLIClient(cfg.LLM_MODEL, "medium", timeout=600)
    prompt = (f"<profile>\n{profile.read_text(encoding='utf-8')}\n</profile>\n\n"
              f"<notes_all>\n{library_text(name)}\n</notes_all>")
    raw = llm.complete(CHECK_SYSTEM, prompt)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    if not data:
        raise SystemExit(f"la revision no devolvio JSON:\n{raw[:800]}")
    return {"contradictions": data.get("contradictions", []), "not_in_profile": data.get("not_in_profile", [])}


def report(result: dict) -> str:
    lines = [f"Contradicciones ({len(result['contradictions'])}):"]
    lines += [f"- [{c.get('section', '?')}] notas: {c.get('notes', '')}\n  perfil: {c.get('profile', '')}"
              for c in result["contradictions"]] or ["- ninguna"]
    lines += ["", f"En tus notas pero no en el perfil ({len(result['not_in_profile'])}):"]
    lines += [f"- [{c.get('section', '?')}] {c.get('fact', '')}" for c in result["not_in_profile"]] or ["- nada"]
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    profile = Path(os.environ.get("SPEAK_PROFILE", DEFAULT_PROFILE))
    if "--profile" in argv:
        i = argv.index("--profile")
        profile = Path(argv[i + 1])
        del argv[i:i + 2]
    name = argv[0] if argv else json.loads((DATA_DIR / "prep" / "current.json").read_text())["active"]
    print(f"Revisando {name} contra {profile} ...\n")
    print(report(check(name, profile)))


if __name__ == "__main__":
    main(sys.argv[1:])
