"""Memoria por resumen: los pasados sin re-enviar las imagenes.

Reanudar la conversacion re-envia todas las capturas previas en cada turno, y
el costo por pregunta sube sin techo: medido, $0.14 la tercera y $1.13 la
treintena. Aqui cada captura va en una conversacion nueva con solo la imagen
actual y, en texto, lo que importaba de las anteriores:

- Claude cierra cada respuesta con una linea `MEMO: ...` — lo que una pregunta
  posterior podria necesitar de esa pantalla. El panel no la muestra.
- Esa nota, mas el principio de la respuesta, viaja en las capturas
  siguientes. Unas decenas de tokens por turno en vez de una imagen.
- Si la nota no basta, Claude responde solo `NEED: 3` y se le re-envia esa
  captura (siguen en disco hasta cerrar la sesion). Una vez por pregunta: a
  la segunda tiene que responder con lo que tenga.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Cuanto de cada respuesta anterior viaja. Lo suficiente para que una
# plantilla con memoria (what if, depurar) sepa que propuso ya; no la
# respuesta entera, que es justo lo que se queria dejar de re-enviar.
ANSWER_CHARS = 500
# Turnos que viajan con respuesta; los mas viejos, solo con su nota.
FULL_TURNS = 12
# Capturas que se pueden pedir de vuelta en una pregunta.
MAX_NEED = 2

_MEMO = re.compile(r"^\s*\**MEMO\**\s*:\s*(.*)$", re.IGNORECASE)
_NEED = re.compile(r"^\s*\**NEED\**\s*:\s*((?:#?\d+[\s,]*)+)\s*$", re.IGNORECASE)


@dataclass
class Entry:
    n: int          # numero de captura en la sesion (1, 2, ...)
    memo: str
    answer: str
    question: str = ""  # solo si la escribiste tu; la de serie no aporta


def protocol(n: int) -> str:
    """Las reglas del juego, en cada mensaje (cada uno es conversacion nueva)."""
    reglas = [
        "SESSION MEMORY RULES:",
        "- End your reply with ONE final line: `MEMO: <what a later question "
        "might need from THIS screenshot: the problem or question, key numbers "
        "and names, the state of any code>`. Keep it under 300 characters. It "
        "is hidden from me, so do not refer to it in your answer.",
    ]
    if n > 1:
        reglas.append(
            f"- The earlier screenshots are still available. If the answer "
            f"depends on something in one of them that the notes above do not "
            f"contain, NEVER say you cannot see it or do not know: reply with "
            f"ONLY `NEED: <numbers>` (at most {MAX_NEED}, from 1 to {n - 1}) and "
            f"nothing else, and you will be shown them. If the notes are "
            f"enough, just answer."
        )
    reglas.append("- Write the MEMO in any language; answer as your instructions say.")
    return "\n".join(reglas)


def build_prompt(entries: list[Entry], question: str, n: int,
                 fetched: list[int] | None = None) -> str:
    """El texto que acompana a la captura `n`."""
    partes: list[str] = []
    if entries:
        lineas = ["EARLIER SCREENSHOTS IN THIS SESSION (you no longer see them; "
                  "these are your own notes):"]
        corte = len(entries) - FULL_TURNS
        for i, e in enumerate(entries):
            lineas.append(f"#{e.n}: {e.memo or '(no note)'}")
            if e.question:
                lineas.append(f"   my question: {e.question}")
            if i >= corte and e.answer:
                lineas.append(f"   your answer: {_recorte(e.answer)}")
        partes.append("\n".join(lineas))
    if fetched:
        nums = ", ".join(f"#{k}" for k in fetched)
        partes.append(
            f"You asked to see {nums} again: those images come first, the "
            f"current screenshot last. Answer now; NEED is no longer allowed."
        )
    partes.append(f"CURRENT SCREENSHOT: #{n}.")
    partes.append(question)
    partes.append(protocol(n) if not fetched else protocol(1))
    return "\n\n".join(partes)


def parse(text: str) -> tuple[str, str]:
    """(respuesta sin la linea MEMO, nota). La nota puede venir vacia."""
    lineas = text.rstrip().splitlines()
    for i in range(len(lineas) - 1, -1, -1):
        m = _MEMO.match(lineas[i])
        if m:
            memo = m.group(1).strip("`* \t")
            # Algun modelo (qwen en Groq) repite la linea: ninguna se enseña.
            limpio = "\n".join(
                l for l in lineas[:i] + lineas[i + 1:] if not _MEMO.match(l)
            ).rstrip()
            # Visto con qwen en Groq: a veces escribe la respuesta solo en la
            # nota. Mejor ensenar la nota que un panel en blanco.
            return limpio or memo, memo
        if lineas[i].strip():
            break  # la nota tiene que ser la ultima linea con texto
    return text.strip(), ""


def needs(text: str, n: int) -> list[int]:
    """Capturas pedidas de vuelta, si la respuesta es SOLO un `NEED: ...`."""
    lineas = [l for l in text.strip().splitlines() if l.strip()]
    if len(lineas) != 1:
        return []
    m = _NEED.match(lineas[0])
    if not m:
        return []
    nums: list[int] = []
    for k in re.findall(r"\d+", m.group(1)):
        k = int(k)
        if 1 <= k < n and k not in nums:
            nums.append(k)
    return nums[:MAX_NEED]


def _recorte(answer: str) -> str:
    plano = " ".join(answer.split())
    if len(plano) <= ANSWER_CHARS:
        return plano
    return plano[:ANSWER_CHARS].rsplit(" ", 1)[0] + " …"
