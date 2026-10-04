"""Tu perfil de entrevista (un .md que mantienes tu) para el SIMULADOR.

Se lee tal cual y se recarga solo cuando el archivo cambia: lo que le
agregues aparece en la siguiente pregunta, sin reiniciar nada.

Viaja completo al entrevistador y al evaluador (unas pocas miles de
palabras caben de sobra), asi no se pierde nada de lo que vayas anadiendo
aunque no siga un formato fijo. Del archivo se extraen ademas, por
convencion:

- la tabla de vacantes ("Active applications": | Empresa | Rol | Enfoque |)
  → el selector de vacante y lo que el entrevistador debe evaluar;
- la linea "Avoid these words: a, b, c" → se marcan al instante en tu
  respuesta, sin esperar al LLM.

Solo para practicar: el copiloto de llamadas no lo usa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

MAX_CHARS = 40_000


@dataclass
class Target:
    company: str
    role: str
    focus: str

    @property
    def label(self) -> str:
        # "Amazon (several: ...)" → "Amazon": el detalle va en block().
        short = re.split(r"\s*\(", self.company, maxsplit=1)[0]
        return f"{short} — {self.role}" if self.role else short

    def block(self) -> str:
        return f"Company: {self.company}\nRole: {self.role}\nWhat their interviews test: {self.focus}"


@dataclass
class InterviewProfile:
    path: Path | None = None
    text: str = ""
    targets: list[Target] = field(default_factory=list)
    banned_words: list[str] = field(default_factory=list)
    _mtime: float = 0.0

    @property
    def loaded(self) -> bool:
        return bool(self.text.strip())

    def refresh(self) -> bool:
        """Relee el archivo si cambio. Devuelve True si hubo cambios."""
        if self.path is None or not self.path.exists():
            changed = self.loaded
            self.text, self.targets, self.banned_words, self._mtime = "", [], [], 0.0
            return changed
        mtime = self.path.stat().st_mtime
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        self.text = self.path.read_text(encoding="utf-8", errors="replace")[:MAX_CHARS]
        self.targets = parse_targets(self.text)
        self.banned_words = parse_banned_words(self.text)
        return True

    def target(self, label: str) -> Target | None:
        return next((t for t in self.targets if t.label == label), None)


def load(path: str | Path | None) -> InterviewProfile:
    prof = InterviewProfile(Path(path).expanduser() if path else None)
    prof.refresh()
    return prof


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_targets(text: str) -> list[Target]:
    """La primera tabla cuya cabecera tenga Company y Role."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        head = [c.lower() for c in _cells(line)]
        if not any("company" in c or "empresa" in c for c in head):
            continue
        if not any("role" in c or "rol" in c for c in head):
            continue
        out = []
        for row in lines[i + 2:]:
            if not row.lstrip().startswith("|"):
                break
            cells = _cells(row)
            if len(cells) < 2 or not cells[0] or set(cells[0]) <= {"-", ":"}:
                continue
            company = re.sub(r"\*\*", "", cells[0])
            # "Others submitted earlier" es una lista, no una vacante a practicar.
            if company.lower().startswith(("others", "otras", "otros")):
                continue
            focus = cells[2] if len(cells) > 2 else ""
            out.append(Target(company, cells[1] if cells[1] != "—" else "",
                              "" if focus == "—" else re.sub(r"\*\*", "", focus)))
        return out
    return []


def parse_banned_words(text: str) -> list[str]:
    m = re.search(r"avoid these words:?\**\s*(.+)", text, re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1).split(".")[0]
    return [w.strip(" *_`\"'") for w in raw.split(",") if w.strip(" *_`\"'")]


def banned_hits(answer: str, words: list[str]) -> list[str]:
    """Palabras prohibidas que aparecen en tu respuesta (sin LLM, al instante)."""
    low = answer.lower()
    return [w for w in words if re.search(r"\b" + re.escape(w.lower()) + r"\b", low)]
