"""Copiloto de llamada: preparacion previa + respuestas en vivo.

**Preparar llamada** (`PrepSession`): un mini chat antes de la llamada. Le
cuentas de que va, le adjuntas o pegas documentos, y con eso y tu base de
conocimiento arma un *brief*: contexto, datos clave, preguntas probables con
respuesta preparada, objeciones. El brief viaja en cada respuesta en vivo.

**En vivo** (`Copilot`): mira la transcripcion de `LiveNotes`. Cuando el otro
lado termina una pregunta, busca en el brief y en los documentos y Claude
escribe que puedes decir, citando la fuente.

Cuando dar la pregunta por terminada (lo delicado: la gente hace pausas a
mitad de una idea):

- La "pregunta" es TODO lo que el otro dijo desde la ultima vez que hablaste
  tu, no solo la ultima frase. Si retoma tras una pausa, lo nuevo se suma.
- Se responde cuando empiezas a hablar tu, o tras `quiet_s` de silencio del
  otro (mas si la frase quedo colgada: "...and", "porque", "..."), y nunca
  con frases suyas aun sin transcribir.
- Si ya se respondio y el otro sigue hablando, la respuesta se rehace con la
  pregunta completa (la vieja se cancela si iba a medias).
- **Responder ahora** fuerza una respuesta a lo ultimo que dijo el otro,
  aunque no parezca pregunta.

No responde en modo `entrevista`: soplar respuestas en una entrevista real
engana al entrevistador. Para entrevistas esta el simulador.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from ..knowledge import KnowledgeBase, format_sources
from ..llm_client import LLMClient
from ..turn_detector import ends_incomplete, only_fillers, question_kind
from .analyzer import MODES
from .pipeline import ME, Transcript, _fmt, render

log = logging.getLogger(__name__)

COPILOT_MODES = {"venta", "reunion", "soporte", "llamada"}


# --- prompts -----------------------------------------------------------------

ANSWER_SYSTEM = """You are the silent real-time assistant of the user ("Yo") during a live {what}. The other side
just said something that needs an answer. Write what Yo can say, ready to be spoken aloud.

Rules:
- Ground every fact in the BRIEF or the SOURCES, stated exactly as written there: do not add scope, qualifiers or
  conditions they don't state (no "per unit" if it doesn't say so). Cite the source by its exact name attribute, in
  brackets: [<name>], or [brief].
- If the answer is not in them, start with "⚠ No está en tus fuentes." and give a safe way to respond (acknowledge,
  offer to confirm and follow up). Never invent prices, numbers, dates, names, deadlines or commitments.
- Answer in the language the other side is speaking.
- Short: this is read during a live conversation. At most ~80 words.

Format:
**Respuesta:** one or two sentences Yo can say as-is.
- up to 3 bullets with supporting facts, numbers or next step
Fuente: [<name>]"""


def answer_prompt(question: str, brief: str, sources: str, recent: str, mode: str) -> tuple[str, str]:
    what = MODES.get(mode, MODES["llamada"])
    user = f"""## BRIEF (prepared before the call)
{brief.strip() or "(no brief)"}

## SOURCES (retrieved from Yo's documents)
{sources}

## Recent conversation
{recent}

## Answer this (said by the other side)
{question}"""
    return ANSWER_SYSTEM.format(what=what), user


PREP_SYSTEM = """You help the user ("Yo") prepare for an upcoming {what}. Yo will tell you what it is about and which
documents matter; you study them and help get ready to answer well. Be a sharp, practical partner: ask about what
is missing (who attends, their goal, what Yo wants out of it), point out gaps and contradictions in the documents,
and propose likely questions. Ground facts in the SOURCES and cite them in brackets. Never invent numbers, prices or
commitments. Write in {language}. Be concise; use markdown."""

BRIEF_SECTIONS = """
# Brief de la llamada
## Contexto y objetivo
Who, what, why, and what Yo wants to achieve.
## Mensajes clave
3-5 points Yo should get across.
## Datos clave
Facts, numbers, prices, dates, names — each with its source in brackets.
## Preguntas probables y respuesta preparada
For each: the question, then a 1-3 sentence answer Yo can say, with source.
## Objeciones y riesgos
For each: the objection and how to handle it.
## Lo que no sabemos
Things to confirm or avoid promising.
"""


# --- preparacion -------------------------------------------------------------


@dataclass
class PrepSession:
    kb: KnowledgeBase
    mode: str = "venta"
    language: str = "Spanish"
    messages: list[tuple[str, str]] = field(default_factory=list)  # (rol, texto)
    brief: str = ""

    def _context(self, query: str, max_chars: int = 12_000) -> str:
        docs = self.kb.sources()
        listing = "\n".join(f"- {d}" for d in docs[:80]) or "(none)"
        hits = format_sources(self.kb.search(query, k=12, max_chars=max_chars)) if docs else "(none)"
        return f"## Documents available\n{listing}\n\n## SOURCES (most relevant passages)\n{hits}"

    def _history(self, last: int = 12) -> str:
        return "\n\n".join(f"**{'Yo' if r == 'user' else 'Asistente'}:** {t}"
                           for r, t in self.messages[-last:])

    def chat_prompt(self, message: str) -> tuple[str, str]:
        query = " ".join(t for r, t in self.messages if r == "user") + " " + message
        user = f"""{self._context(query)}

## Current brief
{self.brief.strip() or "(not written yet)"}

## Conversation so far
{self._history() or "(start)"}

## Yo says now
{message}"""
        return PREP_SYSTEM.format(what=MODES.get(self.mode, MODES["llamada"]), language=self.language), user

    def brief_prompt(self) -> tuple[str, str]:
        query = " ".join(t for _, t in self.messages)
        user = f"""{self._context(query, max_chars=20_000)}

## Preparation conversation
{self._history(last=40) or "(none: build the brief from the documents)"}

## Previous brief (improve it, keep what is still right)
{self.brief.strip() or "(none)"}

Write the brief for the call now. Only the brief, in this format:
{BRIEF_SECTIONS}"""
        return PREP_SYSTEM.format(what=MODES.get(self.mode, MODES["llamada"]), language=self.language), user

    def chat(self, llm: LLMClient, message: str, on_chunk=None, cancel=None) -> str:
        system, user = self.chat_prompt(message)
        self.messages.append(("user", message))
        acc = ""
        for chunk in llm.stream(system, user, cancel):
            acc += chunk
            if on_chunk:
                on_chunk(acc)
        self.messages.append(("assistant", acc.strip()))
        return acc.strip()

    def build_brief(self, llm: LLMClient, on_chunk=None, cancel=None) -> str:
        system, user = self.brief_prompt()
        acc = ""
        for chunk in llm.stream(system, user, cancel):
            acc += chunk
            if on_chunk:
                on_chunk(acc)
        self.brief = acc.strip()
        return self.brief

    def to_dict(self) -> dict:
        return {"mode": self.mode, "messages": self.messages, "brief": self.brief}

    def load_dict(self, data: dict) -> None:
        self.mode = data.get("mode", self.mode)
        self.messages = [tuple(m) for m in data.get("messages", [])]
        self.brief = data.get("brief", "")


# --- en vivo -----------------------------------------------------------------


@dataclass
class Answer:
    id: int
    at: float
    question: str
    text: str = ""
    done: bool = False
    forced: bool = False


@dataclass
class _Pending:
    start: float
    end: float
    text: str


class Copilot:
    """`snapshot()` → Transcript actual; `now()` → segundos de llamada;
    `pending()` → frases del otro aun sin transcribir. `step()` es una
    iteracion (las pruebas la llaman a mano); `start()` la corre en un hilo."""

    def __init__(self, llm: LLMClient, kb: KnowledgeBase | None, brief: Callable[[], str] | str,
                 snapshot: Callable[[], Transcript], now: Callable[[], float],
                 pending: Callable[[], int] = lambda: 0, mode: str = "venta",
                 on_answer: Callable[[Answer], None] = lambda a: None,
                 on_status: Callable[[str], None] = lambda m: None,
                 quiet_s: float = 1.2, incomplete_quiet_s: float = 3.0, min_words: int = 3) -> None:
        self.llm = llm
        self.kb = kb
        self._brief = brief if callable(brief) else (lambda b=brief: b)
        self.snapshot = snapshot
        self.now = now
        self.pending = pending
        self.mode = mode
        self.on_answer = on_answer
        self.on_status = on_status
        self.quiet_s = quiet_s
        self.incomplete_quiet_s = incomplete_quiet_s
        self.min_words = min_words
        self.answers: list[Answer] = []
        self._answered: tuple[float, str] | None = None  # (inicio del bloque, texto respondido)
        self._force = threading.Event()
        self._stop = threading.Event()
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.mode in COPILOT_MODES

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="speak-copilot", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._cancel:
            self._cancel.set()

    def answer_now(self) -> None:
        self._force.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.step()
            except Exception:
                log.exception("copiloto")
            self._stop.wait(0.25)

    # --- cuando responder ---

    def pending_question(self, tr: Transcript) -> _Pending | None:
        """Todo lo que el otro dijo desde tu ultima intervencion."""
        segs = tr.segments
        i = len(segs)
        while i > 0 and segs[i - 1].speaker != ME:
            i -= 1
        block = [s for s in segs[i:] if not only_fillers(s.text)]
        if not block:
            return None
        return _Pending(block[0].start, block[-1].end, " ".join(s.text for s in block))

    def step(self) -> Answer | None:
        forced = self._force.is_set()
        if not self.enabled and not forced:
            return None
        tr = self.snapshot()
        q = self.pending_question(tr)
        me_after = bool(tr.segments) and tr.segments[-1].speaker == ME
        if forced:
            self._force.clear()
            if q is None:
                q = self._last_other_block(tr)
            if q is None:
                self.on_status("Todavia no hay nada del otro lado para responder.")
                return None
            return self._answer(q, tr, forced=True)
        if q is None:
            return None
        if self._answered and self._answered[0] == q.start:
            # Ya respondido: solo se rehace si el otro siguio hablando.
            if len(q.text.split()) - len(self._answered[1].split()) < self.min_words:
                return None
        if len(q.text.split()) < self.min_words or question_kind(q.text) == "statement":
            return None
        if self.pending() > 0:
            return None
        wait = self.incomplete_quiet_s if ends_incomplete(q.text) else self.quiet_s
        if not me_after and self.now() - q.end < wait:
            return None
        return self._answer(q, tr)

    def _last_other_block(self, tr: Transcript) -> _Pending | None:
        segs = [s for s in tr.segments if s.speaker != ME]
        if not segs:
            return None
        last = segs[-1]
        return _Pending(last.start, last.end, last.text)

    # --- respuesta ---

    def _answer(self, q: _Pending, tr: Transcript, forced: bool = False) -> Answer:
        with self._lock:
            if self._cancel:
                self._cancel.set()  # la anterior quedo vieja
            self._cancel = cancel = threading.Event()
            self._answered = (q.start, q.text)
            prev = self.answers[-1] if self.answers else None
            if prev and prev.at == q.start:
                # El otro siguio hablando tras la pausa: misma pregunta, ahora
                # completa. Se reescribe en su sitio, no se apila otra.
                ans = prev
                ans.question, ans.text, ans.done, ans.forced = q.text, "", False, forced
            else:
                ans = Answer(len(self.answers) + 1, q.start, q.text, forced=forced)
                self.answers.append(ans)
        threading.Thread(target=self._generate, args=(ans, tr, cancel), name="speak-copilot-llm",
                         daemon=True).start()
        return ans

    def _generate(self, ans: Answer, tr: Transcript, cancel: threading.Event) -> None:
        recent = render(tr)[-2000:]
        sources = "(no documents loaded)"
        if self.kb is not None and self.kb.chunks:
            query = ans.question + " " + recent[-400:]
            sources = format_sources(self.kb.search(query, k=6, max_chars=6000))
        system, user = answer_prompt(ans.question, self._brief(), sources, recent, self.mode)
        acc = ""
        t0 = time.time()
        try:
            for chunk in self.llm.stream(system, user, cancel):
                if cancel.is_set():
                    return
                acc += chunk
                ans.text = acc
                self.on_answer(ans)
        except Exception as exc:
            log.exception("copiloto: respuesta")
            self.on_status(f"copiloto: {exc}")
            return
        if cancel.is_set():
            return
        ans.text, ans.done = acc.strip(), True
        log.info("copiloto: respuesta en %.1fs", time.time() - t0)
        self.on_answer(ans)

    def render_log(self) -> str:
        return "\n\n---\n\n".join(
            f"**[{_fmt(a.at)}] {'(forzada) ' if a.forced else ''}Pregunta:** {a.question}\n\n{a.text}"
            for a in self.answers)
