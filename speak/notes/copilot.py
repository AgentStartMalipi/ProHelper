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

**Guia** (como el pre-prompt de SCREEN): quien eres y como quieres que
responda. Va DESPUES de las reglas de serie, asi que gana en formato, largo,
tono e idioma; lo que no puede quitar es "no inventes cifras ni
compromisos", que se repite al final. Se lee en cada respuesta: cambiarla a
mitad de llamada vale para la siguiente. `PRESETS` son las plantillas.

**Exploracion** (`discovery_prompt`, `Discovery`): "¿que me falta?". Con la
conversacion (si la hay), el brief y los documentos, marca que dimensiones
del modo estan cubiertas (en arquitectura: objetivo, volumen, integraciones,
datos, RPO/RTO, seguridad...), dice si la informacion alcanza para proponer y
da las 3 proximas preguntas. Antes de la llamada sirve para ver si el
contexto que te dieron es suficiente; durante, se actualiza sola.

**Archivos** (`attach_file`): documentos se leen tal cual; las imagenes
(diagramas) las describe Claude una vez (componentes, conexiones, zonas) y
esa descripcion entra a la base como texto.

No responde en modo `entrevista`: soplar respuestas en una entrevista real
engana al entrevistador. Para entrevistas esta el simulador.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from pathlib import Path

from ..knowledge import IMAGE_EXT, KnowledgeBase, format_sources
from ..llm_client import LLMClient
from ..turn_detector import _DANGLING, _WORD_RE, ends_incomplete, only_fillers, question_kind
from .analyzer import MODES
from .pipeline import ME, THEM, Transcript, _fmt, render

log = logging.getLogger(__name__)

COPILOT_MODES = {"venta", "reunion", "soporte", "arquitectura", "llamada"}


# --- prompts -----------------------------------------------------------------

ANSWER_SYSTEM = """You are the silent real-time assistant of the user ("Yo") during a live call ({what}). The other side
just said something that needs an answer. Write what Yo can say, ready to be spoken aloud.

Rules:
- Ground every fact in the BRIEF or the SOURCES, stated exactly as written there: do not add scope, qualifiers or
  conditions they don't state (no "per unit" if it doesn't say so). Cite the source by its exact name attribute, in
  brackets: [<name>], or [brief].
- If the answer is not in them, start with "⚠" and a 3-5 word note saying so, written in the answer language
  ("⚠ Not in your sources." / "⚠ No está en tus fuentes."), then give a safe way to respond (acknowledge, offer to
  confirm and follow up). Never invent prices, numbers, dates, names, deadlines or commitments.
- Write it in the language given under "Answer language" (the language of the question), even if the brief,
  the sources or the speaker labels ("Yo", "Ellos") are in another language: Yo reads it aloud in the call.
- Short: this is read during a live conversation. At most ~80 words.

Format:
**Respuesta:** one or two sentences Yo can say as-is.
- up to 3 bullets with supporting facts, numbers or next step
Fuente: [<name>]"""


# --- guia --------------------------------------------------------------------

PRESETS = [
    {
        "nombre": "Venta consultiva B2B",
        "texto": """Soy del lado que vende/asesora. Responde como consultor, no como vendedor:
- Traduce cada dato a lo que gana el cliente (ahorro, riesgo que evita, tiempo).
- Cierra la Respuesta con UNA pregunta de descubrimiento que me ayude a entender su necesidad.
- Si preguntan por precio o descuentos, da el dato de las fuentes pero no ofrezcas rebajas: propon revisar alcance.""",
    },
    {
        "nombre": "Manejo de objeciones",
        "texto": """Cuando el otro plantee una duda, queja o comparacion con otro proveedor, estructura la Respuesta asi:
1. Reconoce la preocupacion en una frase (sin darle la razon ni discutir).
2. Responde con un dato o un caso de exito de las fuentes.
3. Termina con una pregunta que confirme si quedo resuelta.
Nunca hables mal de la competencia.""",
    },
    {
        "nombre": "Soporte tecnico",
        "texto": """Soy quien da el soporte. Responde con:
- Primero, si falta informacion para diagnosticar, la pregunta concreta que debo hacer (version, error exacto, desde cuando).
- Luego pasos numerados, cortos, en el orden en que se hacen.
- No prometas fechas de solucion ni compensaciones: ofrece escalar y hacer seguimiento.""",
    },
    {
        "nombre": "Reunion con gerencia",
        "texto": """Reunion interna con directivos. Respuestas ejecutivas:
- Primero la conclusion o la cifra, despues el porque.
- Si hay riesgo, dilo con su impacto y la accion propuesta.
- Si piden una decision, di claramente que necesito de ellos.""",
    },
    {
        "nombre": "Solutions architect",
        "texto": """Soy el arquitecto de soluciones frente al cliente. Cuando pregunten algo tecnico:
- Da una recomendacion concreta y su principal tradeoff (costo, complejidad, lock-in, operacion).
- Si la respuesta depende de un requisito que no conocemos (volumen, latencia, RPO/RTO, cumplimiento), dilo y
  termina con la pregunta exacta que lo aclara.
- No comprometas dimensionamiento, costos ni plazos sin datos: ofrece estimarlo despues de la exploracion.
- Usa los nombres de componentes tal como aparecen en sus diagramas y documentos.""",
    },
    {
        "nombre": "Solo la frase (lo mas rapido)",
        "texto": """Solo la linea **Respuesta:**, maximo 25 palabras, sin bullets ni linea de Fuente.
Si no esta en las fuentes, una frase segura para ganar tiempo.""",
    },
    {
        "nombre": "Siempre en español",
        "texto": """Escribe siempre en español, aunque el otro hable en ingles: yo traduzco al hablar.
Deja en ingles solo los terminos tecnicos que se dicen asi.""",
    },
]

_GUIDE_HEADER = """## User's guide (follow it: it overrides the default format, length, tone and language above)
{guide}

Whatever the guide says, never invent prices, numbers, dates, names or commitments that are not in the brief or
sources."""


def with_guide(system: str, guide: str) -> str:
    guide = (guide or "").strip()
    return f"{system}\n\n{_GUIDE_HEADER.format(guide=guide)}" if guide else system


_ES = set("que de la el los las y en con por para es se nos del una un cuánto cuánta qué cómo cuál "
           "cuándo dónde tienen pueden ustedes usted tu su sus pero muy también hay está están son".split())
_EN = set("the and you what how is are do does can could would of to for with your we our it this that "
          "have has be will about which when where there".split())


def guess_language(text: str) -> str:
    """Idioma de la pregunta, para que la respuesta salga en el mismo. Medido:
    con brief y fuentes en espanol, Claude contestaba en espanol preguntas
    hechas en ingles (4 de 4) aunque el prompt pedia el idioma del otro."""
    # Solo el FINAL cuenta: ahi esta la pregunta. Medido 2026-10-08: un turno
    # de 5 min casi todo en espanol terminaba con "Back to English... Tell me
    # about a time..." y se contestaba en espanol porque ganaba el conteo total.
    tail = _question_tail(text)
    low = tail.lower()
    if re.search(r"\b(back to english|in english|switch to english)\b", low):
        return "English"
    if re.search(r"\b(en español|en espanol|volvamos al español|pasemos a español)\b", low):
        return "Spanish"
    words = re.findall(r"[a-záéíóúñü]+", low)
    es = sum(w in _ES for w in words) + 2 * sum(c in "¿¡ñáéíóú" for c in low)
    en = sum(w in _EN for w in words)
    return "Spanish" if es > en else "English"


def _question_tail(text: str, max_words: int = 40) -> str:
    """Lo ultimo que dijeron: desde la ultima frase anterior a la pregunta final,
    como maximo unas 40 palabras."""
    words = text.split()
    return " ".join(words[-max_words:])


# La llamada vista por el copiloto. Con 2000 caracteres, a la pregunta 10 ya no
# veia "Tell me about yourself" y volvia a contar historias ya dichas.
RECENT_CHARS = 6000


def copilot_sources(kb: KnowledgeBase, question: str, recent: str, max_chars: int = 7000) -> list:
    """Pasajes para responder: primero los que encajan con la PREGUNTA sola y
    despues los de pregunta + final de la llamada. Medido 2026-10-08: con solo
    la busqueda mezclada, el ruido de la transcripcion tapaba la respuesta
    preparada y 9 de 10 preguntas con respuesta preparada improvisaban."""
    out, used, seen = [], 0, set()
    for chunk in (kb.search(question, k=3, max_chars=3000)
                  + kb.search(question + " " + recent[-400:], k=6, max_chars=6000)):
        if id(chunk) in seen or (used + len(chunk.text) > max_chars and out):
            continue
        seen.add(id(chunk))
        out.append(chunk)
        used += len(chunk.text)
    return out


def answer_prompt(question: str, brief: str, sources: str, recent: str, mode: str,
                  guide: str = "") -> tuple[str, str]:
    what = MODES.get(mode, MODES["llamada"])
    user = f"""## BRIEF (prepared before the call)
{brief.strip() or "(no brief)"}

## SOURCES (retrieved from Yo's documents)
{sources}

## Recent conversation
{recent}

## Answer this (said by the other side)
{question}

Answer language: {guess_language(question)}"""
    return with_guide(ANSWER_SYSTEM.format(what=what), guide), user


PREP_SYSTEM = """You help the user ("Yo") prepare for an upcoming call ({what}). Yo will tell you what it is about and which
documents matter; you study them and help get ready to answer well. Be a sharp, practical partner: ask about what
is missing (who attends, their goal, what Yo wants out of it), point out gaps and contradictions in the documents,
and propose likely questions. Ground facts in the SOURCES and cite them in brackets. Never invent numbers, prices or
commitments. Write in {language}. Be concise; use markdown."""

BRIEF_SECTIONS_MODE = {
    "arquitectura": """## Arquitectura actual (según los documentos)
Components, integrations, data flows, infra — each with its source. Mark what is inferred as [supuesto].
## ¿Alcanza la información?
One-line verdict: enough to propose what, and what is missing to propose a solution.
""",
}

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
## Preguntas que debo hacer yo
Exploration questions, prioritized by how much they change the proposal; each ready to say, open-ended.
## Objeciones y riesgos
For each: the objection and how to handle it.
## Lo que no sabemos
Things to confirm or avoid promising.
"""


# --- exploracion -------------------------------------------------------------

DIMENSIONS = {
    "arquitectura": [
        "Objetivo de negocio y criterio de éxito",
        "Usuarios, volumen, picos y crecimiento",
        "Arquitectura actual: componentes y tecnologías",
        "Integraciones y sistemas externos (APIs, protocolos, sincrónico/asíncrono)",
        "Datos: volumen, tipos, sensibilidad, residencia y retención",
        "No funcionales: disponibilidad/SLA, latencia, RPO/RTO",
        "Seguridad e identidad (IAM/SSO, cifrado, red)",
        "Cumplimiento y regulación",
        "Infraestructura y restricciones (nube, on-prem, licencias, proveedor)",
        "Operación: despliegue, monitoreo, soporte, equipo y skills",
        "Presupuesto, plazos y quién decide",
        "Dolores actuales y riesgos",
    ],
    "venta": [
        "Necesidad y dolor concreto",
        "Impacto: cuánto le cuesta el problema",
        "Situación y solución actual",
        "Quién decide y cómo es el proceso de compra",
        "Presupuesto",
        "Plazos y urgencia",
        "Competencia o alternativas que evalúan",
        "Criterios de decisión",
        "Próximo paso acordado",
    ],
    "soporte": [
        "Síntoma o error exacto",
        "Desde cuándo y qué cambió",
        "Alcance: usuarios o sistemas afectados",
        "Entorno y versiones",
        "Se puede reproducir (pasos)",
        "Lo que ya se probó",
        "Impacto y urgencia",
        "Seguimiento: quién y cuándo",
    ],
    "reunion": [
        "Objetivo de la reunión",
        "Decisiones tomadas",
        "Responsables y fechas",
        "Bloqueos",
        "Riesgos",
        "Información pendiente",
    ],
    "llamada": [
        "Objetivo de la llamada",
        "Necesidades de la otra parte",
        "Acuerdos",
        "Pendientes",
    ],
}

DISCOVERY_SYSTEM = """You help the user ("Yo") run discovery in a call ({what}). Judge what is already known and what is
missing, from the conversation so far (if any), the BRIEF and the SOURCES. Never treat an assumption as a fact; if
something is only in a document but was not confirmed in the call, say so. Write in {language}. Be terse: this is
read during the call."""

_DISCOVERY_FORMAT = """
**Veredicto:** one line — is the information enough to {goal}? If not, what blocks it.

### Pregunta ahora
The 3 next questions, most important first: the ones whose answer changes the {goal_short} the most and that were
NOT already answered. Each ready to say (open-ended, one sentence), then "— " and why it matters (max 10 words).

### Cobertura
One line per dimension: ✅ covered / ◐ partial / ❌ missing, then what is known (max 12 words, cite [mm:ss] or
[source]). Dimensions:
{dimensions}

### Ojo
Up to 3: contradictions, unconfirmed assumptions, risks. "—" if none."""

_GOALS = {
    "arquitectura": ("propose a solution architecture", "architecture"),
    "venta": ("make a solid proposal", "proposal"),
    "soporte": ("diagnose the problem", "diagnosis"),
}


def discovery_prompt(tr: Transcript | None, brief: str, sources: str, mode: str,
                     language: str = "Spanish", guide: str = "", max_chars: int = 40_000) -> tuple[str, str]:
    mode = mode if mode in DIMENSIONS else "llamada"
    goal, short = _GOALS.get(mode, ("reach the goal of the call", "outcome"))
    dims = "\n".join(f"- {d}" for d in DIMENSIONS[mode])
    body = render(tr) if tr and tr.segments else ""
    if len(body) > max_chars:
        body = "[... earlier part trimmed ...]\n" + body[-max_chars:]
    user = f"""## BRIEF
{brief.strip() or "(no brief)"}

## SOURCES
{sources}

## Conversation so far
{body or "(the call has not started: judge only from the brief and sources)"}

## Output format
{_DISCOVERY_FORMAT.format(goal=goal, goal_short=short, dimensions=dims)}"""
    system = DISCOVERY_SYSTEM.format(what=MODES.get(mode, MODES["llamada"]), language=language)
    return with_guide(system, guide), user


def discovery_sources(kb: KnowledgeBase | None, tr: Transcript | None, brief: str) -> str:
    if kb is None or not kb.chunks:
        return "(no documents loaded)"
    query = brief[:1500] + " " + (render(tr)[-1500:] if tr and tr.segments else "")
    return format_sources(kb.search(query, k=10, max_chars=10_000))


class Discovery:
    """Exploracion en vivo: se reescribe sola cada `interval_s` si hubo al
    menos `min_new_words` nuevas; `run_now()` la pide ya (tambien sin llamada)."""

    def __init__(self, llm: LLMClient, kb: KnowledgeBase | None, brief: Callable[[], str],
                 snapshot: Callable[[], Transcript | None], mode: str = "arquitectura",
                 language: str = "Spanish", guide: Callable[[], str] = lambda: "",
                 interval_s: float = 90.0, min_new_words: int = 40,
                 on_update: Callable[[str, bool], None] = lambda md, done: None,
                 on_status: Callable[[str], None] = lambda m: None) -> None:
        self.llm, self.kb = llm, kb
        self.brief, self.snapshot, self.guide = brief, snapshot, guide
        self.mode, self.language = mode, language
        self.interval_s, self.min_new_words = interval_s, min_new_words
        self.on_update, self.on_status = on_update, on_status
        self.text = ""
        self._words_at_run = 0
        self._last_run = time.monotonic()
        self._force = threading.Event()
        self._stop = threading.Event()
        self._running = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return self.mode in COPILOT_MODES

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="speak-discovery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def run_now(self) -> None:
        self._force.set()

    def due(self, words: int, now: float) -> bool:
        if self._force.is_set():
            return True
        return (self.enabled and self.interval_s > 0 and now - self._last_run >= self.interval_s
                and words - self._words_at_run >= self.min_new_words)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._force.wait(timeout=1.0)
            if self._stop.is_set():
                return
            tr = self.snapshot()
            words = sum(len(s.text.split()) for s in tr.segments) if tr else 0
            if self.due(words, time.monotonic()):
                self._force.clear()
                self._words_at_run, self._last_run = words, time.monotonic()
                self.run_once(tr)

    def run_once(self, tr: Transcript | None = None) -> str:
        if not self._running.acquire(blocking=False):
            return self.text  # ya hay una en curso
        try:
            brief = self.brief()
            system, user = discovery_prompt(tr, brief, discovery_sources(self.kb, tr, brief), self.mode,
                                            self.language, self.guide())
            acc = ""
            for chunk in self.llm.stream(system, user, self._stop):
                acc += chunk
                self.on_update(acc, False)
            if acc.strip():
                self.text = acc.strip()
                self.on_update(self.text, True)
        except Exception as exc:
            log.exception("exploracion")
            self.on_status(f"exploracion: {exc}")
        finally:
            self._running.release()
        return self.text


# --- archivos ----------------------------------------------------------------

DESCRIBE_SYSTEM = """You turn an image shared during a call ({what}) into searchable text. If it is an architecture or
flow diagram, list: every component (name exactly as written, type, technology), every connection
("A → B: protocol / data", direction as drawn), zones and boundaries (VPC, subnets, on-prem, cloud accounts,
regions), data stores, external systems, and all other visible text. If it is something else (a table, a slide, a
screenshot), transcribe its content faithfully. Do not guess what is not drawn; list ambiguities at the end under
"Dudas". Write in {language}, keep names as written."""


def describe_image(llm: LLMClient, path: Path, mode: str = "arquitectura", language: str = "Spanish") -> str:
    system = DESCRIBE_SYSTEM.format(what=MODES.get(mode, MODES["llamada"]), language=language)
    return llm.complete(system, f"Describe the attached image ({Path(path).name}).", images=[Path(path)]).strip()


def attach_file(kb: KnowledgeBase, path: Path, llm_factory: Callable[[], LLMClient] | None = None,
                mode: str = "arquitectura", language: str = "Spanish") -> str:
    """Anade un archivo a los documentos de la llamada. Devuelve el nombre."""
    path = Path(path)
    if path.suffix.lower() in IMAGE_EXT:
        if llm_factory is None:
            raise RuntimeError("para leer imagenes hace falta el LLM")
        text = describe_image(llm_factory(), path, mode, language)
        kb.add_text(path.name, f"[Imagen descrita por Claude: {path.name}]\n\n{text}")
    else:
        kb.add_file(path)
    return path.name


# --- preparacion -------------------------------------------------------------


@dataclass
class PrepSession:
    kb: KnowledgeBase
    mode: str = "venta"
    language: str = "Spanish"
    messages: list[tuple[str, str]] = field(default_factory=list)  # (rol, texto)
    brief: str = ""
    guide: str = ""
    guide_name: str = ""  # la plantilla de la que salio la guia, si no se toco

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
        return self._system(), user

    def brief_prompt(self) -> tuple[str, str]:
        query = " ".join(t for _, t in self.messages)
        user = f"""{self._context(query, max_chars=20_000)}

## Preparation conversation
{self._history(last=40) or "(none: build the brief from the documents)"}

## Previous brief (improve it, keep what is still right)
{self.brief.strip() or "(none)"}

Write the brief for the call now. Only the brief, in this format:
{BRIEF_SECTIONS}{BRIEF_SECTIONS_MODE.get(self.mode, "")}"""
        return self._system(), user

    def _system(self) -> str:
        system = PREP_SYSTEM.format(what=MODES.get(self.mode, MODES["llamada"]), language=self.language)
        guide = self.guide.strip()
        if not guide:
            return system
        # En la preparacion la guia orienta el enfoque (quien soy, como vendo) y
        # como deben quedar las respuestas preparadas del brief.
        return (f"{system}\n\n## User's guide (apply it to the prepared answers and the approach)\n{guide}")

    def use_preset(self, preset: dict) -> None:
        self.guide = preset["texto"]
        self.guide_name = preset["nombre"]

    def set_guide(self, text: str) -> None:
        """Texto escrito a mano: si ya no es el de la plantilla, pierde su nombre."""
        self.guide = text
        match = next((p for p in PRESETS if p["texto"].strip() == text.strip()), None)
        self.guide_name = match["nombre"] if match else ""

    def chat(self, llm: LLMClient, message: str, on_chunk=None, cancel=None) -> str:
        system, user = self.chat_prompt(message)
        acc = ""
        for chunk in llm.stream(system, user, cancel):
            acc += chunk
            if on_chunk:
                on_chunk(acc)
        # El turno entra completo o no entra: si Claude falla, un "Yo" sin
        # respuesta quedaria en la historia y se colaria en el brief.
        self.messages += [("user", message), ("assistant", acc.strip())]
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
        return {"mode": self.mode, "messages": self.messages, "brief": self.brief,
                "guide": self.guide, "guide_name": self.guide_name}

    def load_dict(self, data: dict) -> None:
        self.mode = data.get("mode", self.mode)
        self.messages = [tuple(m) for m in data.get("messages", [])]
        self.brief = data.get("brief", "")
        self.guide = data.get("guide", "")
        self.guide_name = data.get("guide_name", "")


# --- en vivo -----------------------------------------------------------------


def seems_unfinished(text: str) -> bool:
    """Como `ends_incomplete`, pero sin fiarse del "?" de Whisper: en vivo le
    pone signo de pregunta a los trozos ("And what would the price be for?")
    aunque la persona solo hizo una pausa y va a seguir. Si la ultima palabra
    pide continuacion (for, and, the, de, para...), se espera mas."""
    if ends_incomplete(text):
        return True
    t = text.strip()
    if not t.endswith("?"):
        return False
    words = _WORD_RE.findall(t.lower())
    return bool(words) and words[-1] in _DANGLING


@dataclass
class Answer:
    id: int
    at: float
    question: str
    text: str = ""
    done: bool = False
    forced: bool = False
    last_done: str = ""  # la ultima respuesta completa, por si la reescritura no termina


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
                 speech: Callable[[str], list[tuple[float, float]]] | None = None,
                 on_answer: Callable[[Answer], None] = lambda a: None,
                 on_status: Callable[[str], None] = lambda m: None,
                 guide: Callable[[], str] | str = "",
                 quiet_s: float = 1.2, incomplete_quiet_s: float = 3.0, min_words: int = 3) -> None:
        self.llm = llm
        self.kb = kb
        self._brief = brief if callable(brief) else (lambda b=brief: b)
        self._guide = guide if callable(guide) else (lambda g=guide: g)
        self.snapshot = snapshot
        self.now = now
        self.pending = pending
        # Cuando hablo cada uno segun el VAD (instantaneo), no segun Whisper
        # (con la CPU ocupada tu texto puede llegar 10-50 s tarde). `speech(who)`
        # -> [(inicio, fin)], con la frase en curso hasta "ahora".
        self.speech = speech
        self.mode = mode
        self.on_answer = on_answer
        self.on_status = on_status
        self.quiet_s = quiet_s
        self.incomplete_quiet_s = incomplete_quiet_s
        self.min_words = min_words
        self.answers: list[Answer] = []
        self._answered: tuple[float, str] | None = None  # (inicio del bloque, texto respondido)
        self._cancels: dict[int, threading.Event] = {}
        self._force = threading.Event()
        self._stop = threading.Event()
        self._cancel: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.mode in COPILOT_MODES

    def _system(self) -> str:
        return answer_prompt("", "", "", "", self.mode, self._guide())[0]

    def start(self) -> None:
        # Con un cliente que lo soporte, deja un `claude` arrancado esperando
        # la primera pregunta (~1,2 s menos hasta el primer texto).
        self.llm.warm(self._system())
        self._thread = threading.Thread(target=self._loop, name="speak-copilot", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for ev in self._cancels.values():
            ev.set()
        self.llm.close()

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

    def _intervals(self, who: str, tr: Transcript) -> list[tuple[float, float]]:
        spans = [(x.start, x.end) for x in tr.segments if x.speaker == who]
        if self.speech is not None:
            vad = self.speech(who)
            if who == ME:
                # Con parlantes tu micro capta al otro: esa "voz tuya" empieza a
                # la vez que una frase suya (eco, ~60 ms). No es que hablaras.
                theirs = self.speech(THEM)
                vad = [(a, b) for a, b in vad if not any(abs(a - c) <= 0.35 for c, _ in theirs)]
            spans += vad
        return spans

    def pending_question(self, tr: Transcript) -> _Pending | None:
        """El ultimo turno del otro: sus frases seguidas sin que tu hablaras en
        medio. Lo que es "hablar" lo dice el VAD de tu micro, no tu texto:
        asi no se juntan dos preguntas si tu respuesta aun no se transcribio."""
        mine = self._intervals(ME, tr)
        theirs = [x for x in tr.segments if x.speaker != ME and not only_fillers(x.text)]
        if not theirs:
            return None
        block = [theirs[-1]]
        for seg in reversed(theirs[:-1]):
            nxt = block[0]
            if any(seg.end - 0.1 <= a <= nxt.start + 0.1 for a, _ in mine):
                break  # hablaste entre esta frase y la siguiente: otro turno
            block.insert(0, seg)
        return _Pending(block[0].start, block[-1].end, " ".join(x.text for x in block))

    def _they_are_talking(self, q: _Pending) -> bool:
        """El otro esta hablando AHORA, despues de la pregunta (p. ej. sigue la
        idea tras una pausa). Lo que ya dijo y espera a Whisper lo cubre
        `pending()`; un "mm-hmm" que Whisper descarta no bloquea nada."""
        if self.speech is None:
            return False
        # Frase ABIERTA ahora (el VAD aun no la cierra). No se compara su inicio
        # con q.end: el pre-roll (200 ms) y el hueco que cierra frases (350 ms)
        # hacen que una continuacion tras una coma "empiece" antes de q.end.
        now = self.now()
        return any(b >= now - 0.1 and a > q.start for a, b in self.speech(THEM))

    def step(self) -> Answer | None:
        forced = self._force.is_set()
        if not self.enabled and not forced:
            return None
        tr = self.snapshot()
        q = self.pending_question(tr)
        if forced:
            self._force.clear()
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
        if self.pending() > 0 or self._they_are_talking(q):
            return None
        # Si ya empezaste a responder ("buena pregunta, dejame ver..."), no se
        # espera el silencio: justo ahi es cuando mas sirve la ayuda.
        me_after = any(a >= q.end - 0.2 for a, _ in self._intervals(ME, tr))
        wait = self.incomplete_quiet_s if seems_unfinished(q.text) else self.quiet_s
        if not me_after and self.now() - q.end < wait:
            return None
        return self._answer(q, tr)

    # --- respuesta ---

    def _answer(self, q: _Pending, tr: Transcript, forced: bool = False) -> Answer:
        with self._lock:
            self._answered = (q.start, q.text)
            prev = self.answers[-1] if self.answers else None
            if prev and prev.at == q.start and prev.id in self._cancels:
                # Solo se cancela la respuesta a ESTA misma pregunta (quedo
                # vieja); la de una pregunta anterior termina de escribirse.
                self._cancels[prev.id].set()
            cancel = threading.Event()
            if prev and prev.at == q.start:
                # El otro siguio hablando tras la pausa: misma pregunta, ahora
                # completa. Se reescribe en su sitio, no se apila otra.
                ans = prev
                if prev.done and prev.text:
                    ans.last_done = prev.text
                ans.question, ans.text, ans.done, ans.forced = q.text, "", False, forced
            else:
                ans = Answer(len(self.answers) + 1, q.start, q.text, forced=forced)
                self.answers.append(ans)
            self._cancels[ans.id] = cancel
            self._cancel = cancel
        threading.Thread(target=self._generate, args=(ans, tr, cancel), name="speak-copilot-llm",
                         daemon=True).start()
        return ans

    def _generate(self, ans: Answer, tr: Transcript, cancel: threading.Event) -> None:
        recent = render(tr)[-RECENT_CHARS:]
        sources = "(no documents loaded)"
        if self.kb is not None and self.kb.chunks:
            sources = format_sources(copilot_sources(self.kb, ans.question, recent))
        system, user = answer_prompt(ans.question, self._brief(), sources, recent, self.mode, self._guide())
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

    @staticmethod
    def _final_text(a: Answer) -> str:
        """Lo que queda guardado: si la llamada se detuvo mientras se
        reescribia, la ultima respuesta completa y no el trozo a medias."""
        if a.done or not a.last_done:
            return a.text
        return f"{a.last_done}\n\n_(respuesta anterior: la nueva no alcanzo a terminar)_"

    def render_log(self) -> str:
        return "\n\n---\n\n".join(
            f"**[{_fmt(a.at)}] {'(forzada) ' if a.forced else ''}Pregunta:** {a.question}\n\n"
            f"{self._final_text(a)}"
            for a in self.answers)
