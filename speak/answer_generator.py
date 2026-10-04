"""Prompts del simulador: el entrevistador y el evaluador.

El entrevistador (voz de la app):
- `next_question`: una pregunta nueva segun el perfil y lo ya preguntado.
- `clarify`: responde tu pregunta de aclaracion como lo haria un entrevistador
  (sin regalar la solucion).
- `follow_up`: repregunta sobre tu ultima respuesta.

El evaluador llega SOLO despues de que respondiste. Devuelve markdown con
tres secciones fijas, que la UI separa en paneles:

    ## FEEDBACK         nota 1-5, que funciono, que falto
    ## QUICK ANSWER     3-6 puntos brevisimos para estructurar la respuesta oral
    ## DETAILED ANSWER  la respuesta modelo, con la estructura del tipo

La estructura de DETAILED ANSWER depende del tipo (STAR, coding, system
design, concepto). En un FOLLOW_UP se le pasa la respuesta modelo anterior y
se le pide modificarla, no empezar de cero.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Iterator

from .context_manager import ContextManager
from .llm_client import LLMClient
from .question_classifier import QType

# --- entrevistador -----------------------------------------------------------

INTERVIEWER_SYSTEM = """You are a professional interviewer running a realistic PRACTICE interview.
Your words are read aloud by text-to-speech, so:
- Output ONLY what you would say out loud. No markdown, no lists, no headings, no quotes, no stage directions.
- Keep it natural and concise (1-4 sentences). Code-problem statements may be longer but still spoken-style; spell out small examples in words.
- Never reveal solutions or hints unless the candidate explicitly gives up.
Speak in {language}."""

_TYPE_HINT = {
    "Behavioral": "Ask a behavioral question (the kind answered with STAR), ideally tied to the company's leadership principles or values if known.",
    "Coding": "Ask a coding problem of LeetCode medium difficulty, stated verbally with one short example.",
    "System design": "Ask a system design question appropriate to the seniority.",
    "Technical": "Ask a technical concept question relevant to the role's stack.",
    "Mixta": "Pick whichever type (behavioral, coding, system design, technical concept) best fits the role and has been least covered so far.",
}


def _lang(code: str) -> str:
    return {"es": "Spanish", "en": "English"}.get((code or "en").lower(), "English")


@dataclass
class Prompt:
    system: str
    user: str


def question_prompt(ctx: ContextManager, forced_type: str | None = None) -> Prompt:
    itype = forced_type or ctx.profile.interview_type
    asked = ctx.asked_questions()
    user = [ctx.build(), "", "## Task",
            _TYPE_HINT.get(itype, _TYPE_HINT["Mixta"]),
            "Base it on the role, job description and CV when available."]
    if asked:
        user.append("Do NOT repeat or closely paraphrase any question already asked this session.")
    if not ctx.history:
        user.append("This is the first question: open with a one-sentence greeting, then the question.")
    if ctx.interview_block():
        user.append(
            "A candidate interview profile is provided. Ask what the TARGET ROLE's interviews really test "
            "(see 'What their interviews test'); if no target is set, pick from her active applications. "
            "Favour her listed weak spots to practise, and questions that make her be precise about what was "
            "production vs prototype, and what was hers vs her team's. Behavioral questions should be "
            "answerable from her real experience. Never mention the profile, its rules or which story to use.")
    user.append("Say only the question now.")
    return Prompt(INTERVIEWER_SYSTEM.format(language=_lang(ctx.profile.language)), "\n".join(user))


def clarify_prompt(ctx: ContextManager, candidate_question: str) -> Prompt:
    q = ctx.current.question if ctx.current else ""
    user = f"""{ctx.build()}

## Current question you asked
{q}

## The candidate now asks you
{candidate_question}

## Task
Answer the clarification briefly and realistically, as an interviewer would (confirm or set reasonable
assumptions/constraints). Do not solve the problem. End by inviting them to continue."""
    return Prompt(INTERVIEWER_SYSTEM.format(language=_lang(ctx.profile.language)), user)


def follow_up_prompt(ctx: ContextManager) -> Prompt:
    ex = ctx.current
    user = f"""{ctx.build()}

## Task
Ask ONE probing follow-up about the candidate's last answer, the way a strong interviewer digs in:
missing results/metrics, their personal contribution vs the team's, a tradeoff they skipped, an edge case,
how it scales, or what they'd do differently. Reference what they actually said.
Last question: {ex.question if ex else ''}
Say only the follow-up now."""
    return Prompt(INTERVIEWER_SYSTEM.format(language=_lang(ctx.profile.language)), user)


# --- evaluador ---------------------------------------------------------------

EVALUATOR_SYSTEM = """You are an expert interview coach reviewing a candidate's PRACTICE answer that was transcribed from speech.
Ignore transcription glitches and filler words; judge content, structure and delivery.
Be direct and specific; quote short fragments of what they said when useful.

Output markdown with EXACTLY these three top-level sections, in this order:

## FEEDBACK
First line: `Score: N/5` (5 = would clearly pass at this level).
Then 2-4 bullets on what worked and 2-4 bullets on what was missing or weak, specific to this answer.

## QUICK ANSWER
3-6 extremely short bullets (max ~8 words each) someone could glance at to structure a strong ORAL answer.

## DETAILED ANSWER
{structure}

Write everything in {language}. Keep the model answer spoken-style: something a person could say in
2-3 minutes, not an essay."""

_STRUCTURES = {
    QType.BEHAVIORAL: """A model answer in STAR, using the candidate's own story when they gave one (improve it, don't invent a different
career; mark any detail you had to assume with [assumption]). Subsections: **Situation**, **Task**, **Action**
(first person, the candidate's own actions), **Result** (quantified), then one line mapping it to the leadership
principle/value it demonstrates.""",
    QType.CODING: """Subsections: **Interpretation** (restate + clarifying assumptions), **Approach** (brute force → optimal, why),
**Complexity** (time and space), **Pseudocode**, **Python** (a clean, runnable solution in a ```python block),
**Edge cases** (bullets). If the candidate's approach was valid, build on it rather than replacing it.""",
    QType.SYSTEM_DESIGN: """Subsections: **Requirements** (functional / non-functional), **Assumptions** (with rough numbers),
**High-level architecture**, **Components**, **Data flow**, **Tradeoffs**, **Scaling considerations**.
Keep each subsection to a few tight bullets.""",
    QType.TECHNICAL_CONCEPT: """First a **Short answer** of 1-2 sentences, then **Supporting points** as 3-5 bullets
(how it works, when to use it, a concrete example, a common pitfall).""",
    QType.GENERAL: """A concise model answer (about 60-90 seconds spoken) with a clear structure: hook, 2-3 key points
tied to the role, and a closing line.""",
}


PROFILE_RULES = """

A candidate interview profile is included in the context: it is the SOURCE OF TRUTH.
The profile describes the candidate in the third person, but YOU are talking to her: address her as "you"
in FEEDBACK, and write QUICK ANSWER and DETAILED ANSWER in the first person ("I"), ready to say out loud.
- In FEEDBACK, after the strengths/weaknesses bullets, add a bold line **Profile check:** followed by bullets
  that quote anything in her answer that the profile does not support or that breaks its rules: overclaims
  (e.g. calling a prototype "production", "worked for a bank", "SDE Intern", root cause analysis at Amadeus),
  claimed tools or skills from the must-NOT-claim list, banned words, team numbers presented as hers.
  If everything was accurate, write "- Accurate: nothing beyond your profile."
  Also name the STAR story from the profile that fits this question best, if it is not the one she used.
- In QUICK ANSWER and DETAILED ANSWER use ONLY facts from the profile and its exact allowed wording. Where the
  question needs something the profile does not have, write [not in your profile] and show how to answer
  honestly with the closest real experience. Never invent experience, numbers, tools or titles."""


def evaluation_prompt(ctx: ContextManager, qtype: QType) -> Prompt:
    ex = ctx.current
    effective = qtype
    previous = None
    if qtype in (QType.FOLLOW_UP, QType.CLARIFICATION):
        # Un follow-up hereda la estructura de la pregunta que lo origino.
        base = next((e for e in reversed(ctx.history[:-1])
                     if e.qtype not in (QType.FOLLOW_UP.value, QType.CLARIFICATION.value)), None)
        effective = QType(base.qtype) if base else QType.GENERAL
        previous = base.model_answer if base and base.model_answer else None
    structure = _STRUCTURES.get(effective, _STRUCTURES[QType.GENERAL])
    if previous:
        structure += ("\nThis is a FOLLOW-UP: start from the previous model answer below and MODIFY it to "
                      "address the follow-up (say what changes and why) instead of starting from scratch.")
    user = [ctx.build(include_current=False), "", "## Question", ex.question if ex else ""]
    if ex and ex.clarifications:
        user.append("## Clarifications during the answer")
        user += [f"- Candidate: {a}\n  Interviewer: {r}" for a, r in ex.clarifications]
    user += ["", "## Candidate's answer (speech transcript)",
             (ex.answer if ex and ex.answer else "(the candidate did not answer)")]
    if previous:
        user += ["", "## Previous model answer (to modify)", previous]
    system = EVALUATOR_SYSTEM.format(structure=structure, language=_lang(ctx.profile.language))
    if ctx.interview_block():
        system += PROFILE_RULES
    return Prompt(system, "\n".join(user))


# --- parseo de secciones -----------------------------------------------------

_SECTION_RE = re.compile(r"^##\s+(FEEDBACK|QUICK ANSWER|DETAILED ANSWER)\s*$", re.MULTILINE | re.IGNORECASE)
_SCORE_RE = re.compile(r"score:\s*\**\s*(\d(?:\.\d)?)\s*/\s*5", re.IGNORECASE)


def split_sections(markdown: str) -> dict[str, str]:
    """Parte el markdown (aunque este a medio llegar) en las tres secciones.
    Lo que venga antes del primer encabezado cae en FEEDBACK."""
    out = {"FEEDBACK": "", "QUICK ANSWER": "", "DETAILED ANSWER": ""}
    matches = list(_SECTION_RE.finditer(markdown))
    if not matches:
        out["FEEDBACK"] = markdown.strip()
        return out
    if matches[0].start() > 0:
        out["FEEDBACK"] = markdown[: matches[0].start()].strip()
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        key = m.group(1).upper()
        out[key] = (out[key] + "\n" + markdown[m.end():end]).strip()
    return out


def extract_score(feedback: str) -> str:
    m = _SCORE_RE.search(feedback)
    return f"{m.group(1)}/5" if m else ""


class AnswerGenerator:
    def __init__(self, llm: LLMClient, ctx: ContextManager) -> None:
        self.llm = llm
        self.ctx = ctx

    def _run(self, p: Prompt, cancel: threading.Event | None) -> Iterator[str]:
        return self.llm.stream(p.system, p.user, cancel)

    def next_question(self, cancel=None, forced_type: str | None = None):
        return self._run(question_prompt(self.ctx, forced_type), cancel)

    def clarify(self, candidate_question: str, cancel=None):
        return self._run(clarify_prompt(self.ctx, candidate_question), cancel)

    def follow_up(self, cancel=None):
        return self._run(follow_up_prompt(self.ctx), cancel)

    def evaluate(self, qtype: QType, cancel=None):
        return self._run(evaluation_prompt(self.ctx, qtype), cancel)
