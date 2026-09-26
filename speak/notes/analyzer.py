"""Transcripcion → notas de estudio / de reunion.

Dos pasadas:

1. **Reglas** (gratis, instantaneo): `segment_turns` del detector de turnos
   une frases en turnos y marca preguntas y repreguntas; aqui se empareja
   cada pregunta con la respuesta del otro lado y se marcan las que quedaron
   sin responder. Eso se muestra aunque no haya LLM y ademas se le pasa al
   LLM como pistas.
2. **LLM**: arma las notas con secciones fijas segun el modo.

`notes_prompt` es para despues de la llamada. Durante la llamada, `live.py`
usa `live_notes_prompt`: un borrador mas corto, que solo registra lo dicho.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..llm_client import LLMClient
from ..turn_detector import OfflineTurn, segment_turns
from .pipeline import ME, Transcript, _fmt, render


@dataclass
class QA:
    question: OfflineTurn
    answer: OfflineTurn | None

    @property
    def unanswered(self) -> bool:
        # Solo las interrogativas: una peticion de cierre ("please review
        # caching") no espera respuesta.
        return self.answer is None and self.question.kind == "question"


def pair_questions(turns: list[OfflineTurn]) -> list[QA]:
    """Cada pregunta con el siguiente turno de OTRO hablante. Si antes de que
    el otro hable el mismo hablante cambia de tema con otra pregunta, o se
    acaba la llamada, queda sin responder."""
    out = []
    for i, turn in enumerate(turns):
        if not turn.is_question:
            continue
        answer = None
        for nxt in turns[i + 1:]:
            if nxt.speaker != turn.speaker:
                answer = nxt
                break
            if nxt.is_question and not nxt.is_follow_up:
                break
        out.append(QA(turn, answer))
    return out


def heuristic_report(tr: Transcript) -> str:
    turns = segment_turns(tr.segments)
    qas = pair_questions(turns)
    lines = [f"Turnos: {len(turns)} · Hablantes: {', '.join(tr.speakers())} · "
             f"Preguntas detectadas: {len(qas)}"]
    for qa in qas:
        q = qa.question
        stamp = f"[{_fmt(q.start)}] " if tr.has_timing else ""
        tag = " (repregunta)" if q.is_follow_up else ""
        miss = "  ← SIN RESPUESTA" if qa.unanswered else ""
        lines.append(f"- {stamp}{q.speaker}{tag}: {q.text[:220]}{miss}")
    return "\n".join(lines)


MODES = {
    "entrevista": "a job interview (the user, 'Yo', is the CANDIDATE)",
    "reunion": "a work meeting",
    "venta": "a sales / client call (the user, 'Yo', is on the selling/consulting side)",
    "llamada": "a general call",
}

NOTES_SYSTEM = """You turn call transcripts into study-quality notes for the user, who appears as "Yo" (others: "Ellos",
"Ellos A", named speakers, etc.). The transcript comes from speech recognition: ignore filler words and fix obvious
mis-hearings silently, but never invent content. Cite timestamps like [12:34] when available.
Write in {language}. Use markdown. Be concrete and dense; no fluff. If a section has nothing, write "—"."""

_SECTIONS_COMMON = """
# Resumen
3-6 bullets: what the call was about and how it went.

## Preguntas que {them_asked}
For each: timestamp, the question (condensed), then one line on how it was answered{answer_eval}.

## Preguntas que hice yo
Questions "Yo" asked, and the answer received.

## Problemas, dolores y riesgos mencionados
Who raised it, what exactly, why it matters. Include technical problems, blockers, complaints, concerns.

## Decisiones y acuerdos

## Pendientes
Checklist `- [ ] quien — que — cuando` (only if stated or clearly implied; mark [implícito] otherwise).

## Preguntas abiertas / sin responder
Questions nobody answered well, and things that remained ambiguous.

## Datos clave
Names, roles, numbers, dates, tools, technologies, links mentioned.
"""

_SECTIONS_MODE = {
    "entrevista": """
## Cómo me fue y qué mejorar
For each of the 3-5 most important questions: what was weak in my answer and a stronger answer outline
(STAR for behavioral; approach + complexity for coding; key components + tradeoffs for design).

## Señales del entrevistador
Interest, concerns, hints about what they value, next steps of the process.

## Temas para estudiar
Concrete topics to review before the next round, prioritized.
""",
    "venta": """
## Objeciones y cómo responderlas
## Señales de compra y próximos pasos
""",
    "reunion": "",
    "llamada": "",
}


def notes_prompt(tr: Transcript, mode: str = "entrevista", language: str = "Spanish",
                 max_chars: int = 150_000) -> tuple[str, str]:
    mode = mode if mode in MODES else "llamada"
    body = render(tr)
    if len(body) > max_chars:
        # Muy largo: principio y final completos, el medio recortado.
        half = max_chars // 2
        body = body[:half] + "\n[... transcript trimmed ...]\n" + body[-half:]
    interview = mode == "entrevista"
    sections = _SECTIONS_COMMON.format(
        them_asked="me hicieron" if interview else "hicieron ellos",
        answer_eval=" and whether my answer was solid, partial or weak" if interview else "",
    ) + _SECTIONS_MODE[mode]
    system = NOTES_SYSTEM.format(language=language)
    user = f"""This is {MODES[mode]}.

## Heuristic hints (questions detected by rules; may contain errors)
{heuristic_report(tr)}

## Transcript
{body}

## Output format
{sections}"""
    return system, user


LIVE_SYSTEM = """You keep running notes of a call that is STILL IN PROGRESS, for the user, who appears as "Yo"
(others: "Ellos"). The transcript is live speech recognition: ignore filler, fix obvious mis-hearings silently,
never invent content, and do not speculate about how the call will end. Only record what was said: do not suggest
answers, replies or arguments for the user. Cite timestamps like [12:34]. Write in {language}. Use markdown. Be
brief: these notes are re-written every minute. If a section has nothing yet, write "—"."""

_LIVE_SECTIONS = """
# Resumen hasta ahora
2-5 bullets.

## Preguntas y temas tratados
Timestamp, who asked, the question or topic (condensed). Mark the ones still unanswered with "(sin respuesta)".

## Problemas y riesgos mencionados

## Decisiones y acuerdos

## Pendientes
Checklist `- [ ] quien — que — cuando`.

## Datos clave
Names, roles, numbers, dates, tools mentioned.
"""


def live_notes_prompt(tr: Transcript, mode: str = "llamada", language: str = "Spanish",
                      max_chars: int = 60_000) -> tuple[str, str]:
    """Borrador durante la llamada: mas corto que `notes_prompt` y sin
    evaluar ni sugerir respuestas; eso queda para las notas finales."""
    mode = mode if mode in MODES else "llamada"
    body = render(tr)
    if len(body) > max_chars:
        # En vivo pesa lo reciente: se queda el final.
        body = "[... earlier part trimmed ...]\n" + body[-max_chars:]
    user = f"""This is {MODES[mode]}, still in progress.

## Heuristic hints (questions detected by rules; may contain errors)
{heuristic_report(tr)}

## Transcript so far
{body}

## Output format
{_LIVE_SECTIONS}"""
    return LIVE_SYSTEM.format(language=language), user


def generate_notes(llm: LLMClient, tr: Transcript, mode: str = "entrevista",
                   language: str = "Spanish", on_chunk=None, cancel=None) -> str:
    system, user = notes_prompt(tr, mode, language)
    acc = ""
    for chunk in llm.stream(system, user, cancel):
        acc += chunk
        if on_chunk:
            on_chunk(acc)
    return acc.strip()


def me_share(tr: Transcript) -> float:
    """Fraccion de palabras dichas por "Yo" (util en entrevistas: si hablas
    el 20% o el 90%, algo anda raro)."""
    total = sum(len(s.text.split()) for s in tr.segments) or 1
    mine = sum(len(s.text.split()) for s in tr.segments if s.speaker == ME)
    return mine / total
