"""Clasificacion aproximada de preguntas de entrevista, por reglas.

Por reglas y no con el LLM: es instantaneo, gratis y suficiente para elegir
la plantilla de feedback. Si falla, el costo es una estructura menos
adecuada, no una respuesta mala. Cada tipo suma puntos por senales; gana el
de mayor puntaje, con GENERAL como fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class QType(str, Enum):
    BEHAVIORAL = "BEHAVIORAL"
    CODING = "CODING"
    SYSTEM_DESIGN = "SYSTEM_DESIGN"
    TECHNICAL_CONCEPT = "TECHNICAL_CONCEPT"
    FOLLOW_UP = "FOLLOW_UP"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"


_SIGNALS: dict[QType, list[tuple[str, int]]] = {
    QType.BEHAVIORAL: [
        (r"tell me about a time|describe a (?:time|situation)|give me an example of (?:a time|when)", 5),
        (r"have you ever|walk me through a (?:situation|time)|cu[eé]ntame (?:de )?una vez", 4),
        (r"\b(?:conflict|disagree\w*|failure|failed|mistake|challeng\w+|deadline|pressure|"
         r"feedback|proud|weakness|strength|customer|ownership|stakeholder|priorit\w+|"
         r"manager|teammate|lead(?:ership)?|influence|ambiguity|went wrong|learn(?:ed)?)\b", 1),
        (r"\b(?:conflicto|error|fracaso|desaf[ií]o|jefe|equipo|cliente|liderazgo)\b", 1),
    ],
    QType.CODING: [
        (r"\bgiven (?:an?|the|two) (?:array|string|list|binary|tree|graph|matrix|linked|"
         r"integer|number|sorted|set)", 5),
        (r"\b(?:write|implement|code) (?:a |an )?(?:function|method|algorithm|class)", 5),
        (r"\b(?:return|find|count|determine) (?:the|all|whether|if|a|an)\b", 2),
        (r"\b(?:array|subarray|substring|linked list|binary tree|bst|graph|matrix|heap|"
         r"hash ?map|stack|queue|trie|dynamic programming|recursion|two pointers|"
         r"sliding window|o\(n|time complexity|space complexity|leetcode|integers?)\b", 2),
    ],
    QType.SYSTEM_DESIGN: [
        (r"\b(?:design|architect|dise[nñ]a) (?:a|an|the|un|una)?\s*(?:\w+\s){0,3}?"
         r"(?:system|service|platform|app|application|api|url shortener|feed|chat|"
         r"rate limiter|cache|queue|sistema|servicio)", 6),
        (r"\b(?:scal\w+|millions? of (?:users|requests)|high availability|distributed|"
         r"load balanc\w+|sharding|replication|throughput|latency|microservices?|"
         r"cdn|partition\w*|consistency|back-of-the-envelope|qps)\b", 2),
    ],
    QType.TECHNICAL_CONCEPT: [
        (r"^(?:what is|what are|what's|explain|how does|how do|why (?:is|do|does)|"
         r"when would you use|qu[eé] es|explica|c[oó]mo funciona)\b", 3),
        (r"\bdifference between|compare|vs\.?|versus|pros and cons|diferencia entre\b", 3),
        (r"\b(?:http|tcp|udp|rest|grpc|graphql|index(?:es|ing)?|transaction|acid|thread|"
         r"process|mutex|deadlock|garbage collect\w*|docker|kubernetes|sql|nosql|"
         r"oauth|jwt|polymorphism|inheritance|closure|big-?o|hash(?:ing)?|"
         r"overfitting|gradient|regulariz\w+|p-value|normaliz\w+)\b", 2),
    ],
    QType.CLARIFICATION: [
        (r"^(?:can i assume|may i assume|should i assume|do you mean|did you mean|"
         r"just to clarify|to clarify|is it (?:ok|okay|fine) (?:if|to)|are there|is there|"
         r"is the (?:input|array|list|string)|what(?:'s| is) the (?:input|expected|size|range)|"
         r"should i|do i need to|puedo asumir|te refieres|para aclarar)", 6),
        (r"\b(?:assume|constraints?|edge case|input size|duplicates|negative numbers|"
         r"sorted|empty)\b.*\?$", 2),
    ],
    QType.GENERAL: [
        (r"tell me about yourself|walk me through your (?:resume|cv|background)|"
         r"why (?:do you want|this (?:company|role))|why amazon|where do you see yourself|"
         r"any questions for (?:me|us)|h[aá]blame de ti", 6),
    ],
}

_COMPILED = {q: [(re.compile(p, re.IGNORECASE), w) for p, w in sigs] for q, sigs in _SIGNALS.items()}
# Si empatan, gana el primero de esta lista.
_PRIORITY = [QType.CLARIFICATION, QType.SYSTEM_DESIGN, QType.CODING, QType.BEHAVIORAL,
             QType.GENERAL, QType.TECHNICAL_CONCEPT]


@dataclass
class Classification:
    qtype: QType
    confidence: float  # 0..1, aproximada
    scores: dict[str, int]


def classify(text: str, is_follow_up: bool = False, from_candidate: bool = False) -> Classification:
    """`from_candidate`: el turno lo dijo el candidato (en el simulador, una
    pregunta tuya al entrevistador); ahi casi todo es CLARIFICATION."""
    t = text.strip().lower()
    scores = {q.value: 0 for q in QType}
    for qtype, patterns in _COMPILED.items():
        for rx, weight in patterns:
            if rx.search(t):
                scores[qtype.value] += weight
    if from_candidate:
        scores[QType.CLARIFICATION.value] += 4
    if is_follow_up:
        return Classification(QType.FOLLOW_UP, 0.8, scores)
    best = max(_PRIORITY, key=lambda q: (scores[q.value], -_PRIORITY.index(q)))
    top = scores[best.value]
    if top == 0:
        return Classification(QType.GENERAL, 0.3, scores)
    total = sum(scores.values()) or 1
    return Classification(best, round(min(1.0, top / total + 0.2), 2), scores)
