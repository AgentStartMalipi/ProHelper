"""Respuesta preparada al instante (un "cache semantico" pre-sembrado).

Las respuestas preparadas viven en los textos de la preparacion con un titulo
que incluye la pregunta hablada:

    ## why_not_stay_at_aws - Why didn't you stay at AWS after the internship?
    ## proudest_experience - What are you most proud of? | Your proudest achievement

(varias formas de preguntar lo mismo van separadas por " | "). Cuando el otro
termina una pregunta que se parece a uno de esos titulos, el copiloto muestra
esa respuesta en ~1 ms, mientras el LLM escribe la version ajustada a la
conversacion (que llega 2-6 s despues).

Por que no Redis/Qdrant/FAISS: son ~40 respuestas de una sola persona en una
app de escritorio. Un indice en memoria por solapamiento de palabras clave
cuesta 0 de operacion, no tiene servicio que se caiga y, medido con 45
preguntas de una entrevista de prueba (2026-10-08), con umbral 0.6 y al menos 2
palabras clave en comun acerto todas las coincidencias que devolvio; las de
una sola palabra ("hear", "role") eran falsas y quedan fuera.

Si algo falla aqui, el copiloto sigue como siempre: solo se pierde el atajo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"(?m)^##\s+(\w+)\s+-\s+(.+)$")
_WORD_RE = re.compile(r"[a-záéíóúñü0-9]+")
_STOP = set(
    "a an the you your to of in and or at for on with did do does how what why when where who is are was were me "
    "i we it that this tell about time can could would there their our be have has had any some by from as".split()
)

# Muletillas que pueden ir con "?" sin ser la pregunta: "Really? Give me an example."
_FILLER = set("okay right really interesting sure yeah yes thanks thank good great alright sorry hmm".split())


def _keywords(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 2}


@dataclass
class Match:
    key: str
    text: str
    score: float
    overlap: int


@dataclass
class _Entry:
    key: str
    phrasings: list[set[str]]
    text: str


class PreparedIndex:
    """Indice de respuestas preparadas. `texts`: {nombre: texto} de la preparacion."""

    def __init__(self, texts: dict[str, str], min_score: float = 0.6, min_overlap: int = 2,
                 tail_words: int = 40, min_precision: float = 0.0) -> None:
        self.min_score = min_score
        self.min_overlap = min_overlap
        self.tail_words = tail_words
        # min_precision > 0: ademas, la ULTIMA frase de la pregunta no puede traer
        # mucho mas que el titulo (fraccion de sus palabras clave que estan en el
        # titulo). Con 0.9/0.75 solo pasa una pregunta casi igual al titulo.
        self.min_precision = min_precision
        self.entries: list[_Entry] = []
        for text in texts.values():
            heads = list(_HEADING_RE.finditer(text))
            for i, m in enumerate(heads):
                end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
                body = text[m.end():end]
                # El siguiente "## clave" sin pregunta tambien corta la respuesta.
                body = re.split(r"(?m)^##\s", body, maxsplit=1)[0]
                answer = _for_reading(body)
                phrasings = [k for k in (_keywords(p) for p in m.group(2).split("|")) if k]
                if answer and phrasings:
                    self.entries.append(_Entry(m.group(1), phrasings, answer))

    def match(self, question: str) -> Match | None:
        # Solo el final: un turno largo puede arrastrar minutos de charla.
        words = _keywords(" ".join(question.split()[-self.tail_words:]))
        sentences = [s for s in re.split(r"[.!?]+", question) if _keywords(s)]
        last = _keywords(sentences[-1]) if sentences else words
        # La pregunta anterior del mismo turno, si la hay: "What is SSRF...? Give me one concrete
        # example." pide un ejemplo DE ESO, no la historia de "Give me a concrete example"
        # (simulacro 2026-10-18 12:26: salio el caso del login para SSRF). Solo si la ultima frase es
        # corta (un "dame un ejemplo", "que miras primero"): una frase larga ya es la pregunta.
        asked = [s for s in re.findall(r"[^.!?]+[.!?]*", question) if _keywords(s)]
        prev_q = _keywords(asked[-2]) - _FILLER if len(asked) > 1 and asked[-2].rstrip().endswith("?") else set()
        best: Match | None = None
        for entry in self.entries:
            for phrasing in entry.phrasings:
                overlap = len(words & phrasing)
                score = overlap / len(phrasing)
                # Un titulo de una sola palabra clave ("Why Valencia?") coincide
                # con esa palabra; los demas piden al menos `min_overlap`.
                needed = min(self.min_overlap, len(phrasing))
                if overlap < needed or score < self.min_score:
                    continue
                if self.min_precision and len(last & phrasing) / len(last) < self.min_precision:
                    continue
                if prev_q and len(last) <= 4 and len(prev_q & phrasing) / len(prev_q) < (self.min_precision or 0.5):
                    continue  # casa con el "dame un ejemplo" final, no con el centro de la pregunta
                # Empate de puntaje: gana la que comparte mas palabras ("How do we
                # know you won't leave after six months?" -> la de compromiso, no
                # la de "por que dejas Amadeus").
                if best is None or (score, overlap) > (best.score, best.overlap):
                    best = Match(entry.key, entry.text, score, overlap)
        return best


def _for_reading(body: str) -> str:
    """La respuesta tal como se lee: sin las notas entre parentesis para el
    copiloto ("(If the hackathon was already told...)")."""
    lines = [ln.strip() for ln in body.strip().splitlines()]
    return "\n\n".join(ln for ln in lines if ln and not ln.startswith("("))
