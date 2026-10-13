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

# Con notas preparadas hasta este tamano, van ENTERAS en el system (en vez de
# trozos buscados). Medido 2026-10-12 con la biblioteca de CERN (~20 KB): con
# trozos, el LLM movio las landing pages de AWS "at Amadeus" (el trozo perdio
# su encabezado). Enteras ademas quedan en la cache del prompt.
FULL_NOTES_CHARS = 40_000


# --- prompts -----------------------------------------------------------------

ANSWER_SYSTEM = """You are the silent real-time assistant of the user ("Yo") during a live call ({what}). The other side
just said something that needs an answer. Write what Yo can say, ready to be spoken aloud.

Rules:
- Ground every fact in the BRIEF or the SOURCES, stated exactly as written there: do not add scope, qualifiers or
  conditions they don't state (no "per unit" if it doesn't say so). Cite what you used, in brackets: the "## key"
  of the prepared section ([why_two_degrees]), else the source's exact name attribute ([<name>]), or [brief].
- Answer the exact question first: the opening line gives what was asked (a "why" gets a reason, a "how" gets
  the method, a yes/no question ("Have you...?", "Did you...?") starts with "Yes" or "No", or "Yes, partly",
  then the evidence). Every other line supports that answer; leave out experience
  that doesn't (no list of achievements when they ask for a motivation).
- If a prepared section answers the question, build the answer from THAT section: its facts, in its order.
- Keep every story where the sources put it (company, project, year, who did it): never move a story to another
  employer, merge two stories, or add details they don't have (numbers, tools, frequencies, who else helped).
- If the answer needs facts about Yo, the other side or the business (experience, projects, prices, numbers,
  dates, names, products, commitments) and they are not in them:
  - The first line is "⚠" and 3-6 words naming what is missing, in the answer language ("⚠ Auth method not in
    your sources." / "⚠ El método de autenticación no está en tus fuentes."). That line is a private note for Yo,
    never read aloud: alone on its line, and no other line mentions sources, guessing or not knowing.
  - Missing detail of Yo's own past work (how Yo built, configured or ran something): say what the sources do
    state, then how Yo would do it, as general technical knowledge framed as an approach ("the way I'd set it
    up is...", "the standard approach is..."), never as something Yo did, and never tie it back to Yo's result
    ("that's what pointed me to...", "that's how I found..."). Never "I'd confirm", "I don't have
    that detail", "not at hand" or "I won't guess": it was Yo's own work, so that sounds evasive. Shape:
    "The credentials lived in Key Vault, never in the code." / "The way I'd wire the access is a managed
    identity with RBAC on the vault, so nothing secret sits in the flow."
  - Missing detail of a specific past event (what the logs or timestamps showed, the exact setting that changed,
    a concrete example they ask for): there is no "approach" for that, so never fill it with a plausible story.
    One short honest line in Yo's voice ("Honestly, I don't remember the exact setting."), then what the
    sources do state about that event, then at most one line of general knowledge framed as general ("usually
    that's..."). Never "I won't guess", "in front of me" or "I'd confirm".
  - A follow-up that drills into something Yo said earlier gets only what the sources state: what Yo said in
    the conversation is never evidence for new specifics (log lines, steps, IDs, values) about that event.
  - Missing fact about the other side or the business (prices, numbers, dates, names, deadlines, commitments):
    acknowledge it and offer to confirm and follow up.
  - Never invent prices, numbers, dates, names, deadlines or commitments, and never answer the question with a
    fact that answers a different one. Never invent Yo's experiences, projects, reasons or motivations either:
    if Yo's own reason is missing, say only what the sources state, briefly. "⚠" is only for that: Yo not
    having done something is never a reason for "⚠".
- Never announce a story or example without telling it right there ("the cheese lab story is the best
  example", "I can tell you about X"): the other side will say "go ahead" and Yo has nothing to read. If a
  story from the sources fits, tell it in one or two sentences inside the answer; if not, don't name it.
- General, public technical knowledge (how a protocol, standard or common tool works) is not a missing fact:
  explain it plainly, without "⚠" and without citing a source for it. Never present it as Yo's own experience.
- A gap the sources already state ("I haven't done X yet") is NOT missing: no "⚠", just say it as Yo would.
- Write it in the language given under "Answer language" (the language of the question), even if the brief,
  the sources or the speaker labels ("Yo", "Ellos") are in another language: Yo reads it aloud in the call.
- Short: this is read during a live conversation. At most ~80 words.

Format:
- Yo reads it aloud line by line: one idea per line, short sentences, at most 6 lines. No paragraphs, no bullets, no bold.
- It must sound like a person talking, not a CV being read:
  - Every line is something Yo can say as-is, in first person, to the other side. Never advice or comments for Yo
    ("I'd be honest with him", "mention that...") and never talk about the other side in the third person.
  - Open with a natural spoken connector that fits the question, in the answer language ("Sure,", "So,", "Well,",
    "Right,", "Yeah, so", "Good question," / "Claro,", "Pues,", "Mira,", "Sí, mira"), as part of the first
    sentence, never alone on its line. Do not reuse the opener Yo used in the last answers in the Recent
    conversation; on a quick follow-up about the same topic, starting straight with the answer is fine. If the
    answer starts with the "⚠" note, the connector opens the first line after it.
  - At most 1-2 more connectors, only where the idea changes ("on that note", "the reason is"). Not one per line,
    and "honestly" at most once every few answers.
  - Short, complete spoken sentences, about 15 words per line at most: subject and verb, not note fragments
    ("The closest I've done is...", not "Closest example is..."). No filler like "I am a person who is...".
  - Plain everyday words: Yo is not a native speaker and reads it live. "different" not "heterogeneous",
    "many" not "a wide mix of", "reach" not "connectivity", "idea" not "conceptually". Technical terms of the
    field (LDAP, Kubernetes, gateway) are fine; fancy general words are not.
  - Do not repeat what Yo already said in the Recent conversation: the same disclaimer, the same example or the
    same closing line. Build on it instead ("as I said, ...") or leave it out.
  - End on the substance. Do not close with a disclaimer or an offer to confirm ("I haven't done this myself",
    "happy to confirm", "I'd check with the team"), except for a missing fact about the other side or the business.
  - Never a list of jobs or facts glued together ("X, before that Y, currently Z"). Say it the way people talk:
    "Right now I'm at <A> doing <B>." then "Before that I did <C>."
  - Shape (pattern only, take every fact from the BRIEF or SOURCES):
    Sure — so right now I'm <role> at <company>.
    <one short line on what that looks like>.
    Before that, <previous step>.
    And honestly, <why this question matters to me, from the sources>.
    Fuente: [<key or name>]
- Safe abbreviations that read naturally are welcome: CS, SWE, AWS, K8s, Ops, IAM, SOC, PKI, TLS, M365,
  authN/authZ. Never abbreviate the key words of the answer or anything that would make Yo stumble.
- Last line: Fuente: [<key or name>]"""


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
sources. Keep the spoken voice too: open with a short natural connector, varied between answers ("Sure,",
"So,", "Well,"...; it is not a filler intro, it is how people start talking), only first-person lines Yo can say
as-is, never glue facts into a CV-style chain, never repeat a disclaimer or example Yo already gave in the Recent
conversation, and end with the Fuente line. And keep the layout: one idea per line, short sentences,
at most 6 lines, no paragraphs."""


def with_guide(system: str, guide: str) -> str:
    guide = (guide or "").strip()
    return f"{system}\n\n{_GUIDE_HEADER.format(guide=guide)}" if guide else system


_ES = set("que de la el los las y en con por para es se nos del una un cuánto cuánta qué cómo cuál "
           "cuándo dónde tienen pueden ustedes usted tu su sus pero muy también hay está están son".split())
_EN = set("the and you what how is are do does can could would of to for with your we our it this that "
          "have has be will about which when where there why who did was were tell my i so at in on both "
          "mentioned said any an".split())
# Nombres propios con "de/los/la...": "Universidad de los Andes" contaba como
# espanol y una pregunta en ingles se contesto en espanol (2026-10-12).
_PROPER_NAME = re.compile(r"\b[A-ZÁÉÍÓÚ][\wáéíóúñ]+(?:\s+(?:de|del|la|las|los|y|e)\s+[A-ZÁÉÍÓÚ][\wáéíóúñ]+)+")


def guess_language(text: str) -> str:
    """Idioma de la pregunta, para que la respuesta salga en el mismo. Medido:
    con brief y fuentes en espanol, Claude contestaba en espanol preguntas
    hechas en ingles (4 de 4) aunque el prompt pedia el idioma del otro."""
    # Solo el FINAL cuenta: ahi esta la pregunta. Medido 2026-10-08: un turno
    # de 5 min casi todo en espanol terminaba con "Back to English... Tell me
    # about a time..." y se contestaba en espanol porque ganaba el conteo total.
    tail = _PROPER_NAME.sub(" ", _question_tail(text))
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


def full_notes(kb: KnowledgeBase | None) -> str:
    """Las notas preparadas enteras (respuestas, CV...), si caben; "" si no."""
    texts = kb.extra_texts() if kb is not None else {}
    if not texts or sum(len(t) for t in texts.values()) > FULL_NOTES_CHARS:
        return ""
    return "\n\n".join(f"<source name=\"{name}\">\n{text.strip()}\n</source>" for name, text in sorted(texts.items()))


def answer_prompt(question: str, brief: str, sources: str, recent: str, mode: str,
                  guide: str = "", notes: str = "") -> tuple[str, str]:
    """`notes` (ver `full_notes`): el brief y las notas van enteros al INICIO del
    system, fijos durante la llamada (documentos largos arriba, la pregunta al
    final; y el prefijo fijo queda en la cache). Sin `notes`, el brief y los
    pasajes buscados van en el mensaje, como antes."""
    what = MODES.get(mode, MODES["llamada"])
    system = with_guide(ANSWER_SYSTEM.format(what=what), guide)
    tail = f"""## Recent conversation
<conversation>
{recent}
</conversation>

## Answer this (said by the other side)
<question>
{question}
</question>

Answer language: {guess_language(question)}"""
    if notes:
        system = f"""## BRIEF (prepared before the call)
<brief>
{brief.strip() or "(no brief)"}
</brief>

## SOURCES (Yo's prepared notes, complete: the only source of facts about Yo)
{notes}

{system}"""
        more = f"## MORE SOURCES (retrieved from Yo's other documents)\n{sources}\n\n" if sources else ""
        return system, more + tail
    user = f"""## BRIEF (prepared before the call)
{brief.strip() or "(no brief)"}

## SOURCES (retrieved from Yo's documents)
{sources}

{tail}"""
    return system, user


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


def split_warning(text: str) -> tuple[str, str]:
    """("⚠ nota", resto). La nota es para Yo, no se lee en voz alta. Medido
    2026-10-12: el LLM la pegaba a la primera frase ("⚠ Not in my sources, the
    exact auth method there. Honestly, ...") y se leia como respuesta."""
    t = (text or "").lstrip()
    if not t.startswith("⚠"):
        return "", text or ""
    first, _, rest = t.partition("\n")
    m = re.match(r"(⚠[^.!?]*[.!?]?)\s*(.*)", first)
    note, tail = m.group(1).strip(), m.group(2).strip()
    return note, f"{tail}\n{rest}".strip()


@dataclass
class Answer:
    id: int
    at: float
    question: str
    text: str = ""
    done: bool = False
    forced: bool = False
    last_done: str = ""  # la ultima respuesta completa, por si la reescritura no termina
    instant: str = ""  # respuesta preparada mostrada al instante (ver notes/instant.py)
    instant_key: str = ""
    trigger_lag: float = 0.0  # s desde que el otro termino de hablar hasta disparar
    timed_out: bool = False  # el LLM no escribio nada a tiempo (ver Copilot.live_timeout_s)


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
                 quiet_s: float = 1.2, incomplete_quiet_s: float = 3.0, min_words: int = 3,
                 eager_s: float = 0.0, instant: Callable[[str], object] | None = None,
                 live_timeout_s: float = 0.0) -> None:
        # live_timeout_s > 0: si en ese tiempo el LLM no escribio nada, AL VUELO
        # se da por perdida (queda MEMORIA, si la hay) y la vista deja de esperar.
        self.live_timeout_s = live_timeout_s
        # eager_s > 0: una pregunta que ya cerro con "?" se responde tras
        # eager_s de silencio en vez de quiet_s (si el otro sigue, se rehace).
        # instant(pregunta) -> notes.instant.Match o None: respuesta preparada
        # que se muestra al instante mientras el LLM escribe.
        self.eager_s = eager_s
        self.instant = instant
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
        # El mismo system que usara `_generate`: si coincide, se usa el `claude`
        # pre-arrancado (y su prefijo ya esta en la cache).
        return answer_prompt("", self._brief(), "", "", self.mode, self._guide(), full_notes(self.kb))[0]

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
        unfinished = seems_unfinished(q.text)
        wait = self.incomplete_quiet_s if unfinished else self.quiet_s
        if self.eager_s > 0 and not unfinished and q.text.rstrip().endswith("?"):
            # Especulativo: la pregunta ya cerro. Si el otro sigue hablando,
            # `_answer` cancela esta y la rehace con la pregunta completa.
            wait = min(wait, self.eager_s)
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
                ans.timed_out = False
            else:
                ans = Answer(len(self.answers) + 1, q.start, q.text, forced=forced)
                self.answers.append(ans)
            self._cancels[ans.id] = cancel
            self._cancel = cancel
            ans.trigger_lag = max(0.0, self.now() - q.end)
            ans.instant, ans.instant_key = self._instant_for(q.text)
        if ans.instant:
            self.on_answer(ans)  # la preparada (MEMORIA) se ve ya; la del LLM (AL VUELO) llega despues
        threading.Thread(target=self._generate, args=(ans, tr, cancel), name="speak-copilot-llm",
                         daemon=True).start()
        return ans

    def _instant_for(self, question: str) -> tuple[str, str]:
        if self.instant is None:
            return "", ""
        try:
            m = self.instant(question)
        except Exception:
            log.exception("copiloto: respuesta preparada")  # sin atajo, sigue el LLM
            return "", ""
        return (m.text, m.key) if m else ("", "")

    def _generate(self, ans: Answer, tr: Transcript, cancel: threading.Event) -> None:
        t_start = time.time()
        recent = render(tr)[-RECENT_CHARS:]
        sources = "(no documents loaded)"
        notes = full_notes(self.kb)
        if notes:
            # Las notas ya van enteras: solo se busca en los demas documentos.
            extra = set(self.kb.extra_texts())
            found = [c for c in copilot_sources(self.kb, ans.question, recent) if c.source not in extra]
            sources = format_sources(found) if found else ""
        elif self.kb is not None and self.kb.chunks:
            sources = format_sources(copilot_sources(self.kb, ans.question, recent))
        t_search = time.time()
        system, user = answer_prompt(ans.question, self._brief(), sources, recent, self.mode, self._guide(), notes)
        acc = ""
        first: float | None = None
        guard = threading.Lock()  # el primer trozo y el timeout no pueden cruzarse

        def expire() -> None:
            # Corre en su propio hilo: el del LLM puede seguir bloqueado leyendo
            # al CLI. Se da AL VUELO por perdida y se refresca la vista ya.
            with guard:
                if first is not None or cancel.is_set():
                    return
                cancel.set()  # lo que llegue despues se descarta
                ans.timed_out, ans.done = True, True
            log.info("copiloto: AL VUELO sin texto tras %.1fs (preparada %s)",
                     self.live_timeout_s, ans.instant_key or "-")
            self.on_answer(ans)

        timer = threading.Timer(self.live_timeout_s, expire) if self.live_timeout_s > 0 else None
        if timer:
            timer.daemon = True
            timer.start()
        try:
            for chunk in self.llm.stream(system, user, cancel):
                with guard:
                    if cancel.is_set():
                        return
                    if first is None and chunk:
                        first = time.time()
                if timer and first is not None:
                    timer.cancel()
                acc += chunk
                ans.text = acc
                self.on_answer(ans)
        except Exception as exc:
            log.exception("copiloto: respuesta")
            self.on_status(f"copiloto: {exc}")
            return
        finally:
            if timer:
                timer.cancel()
        if cancel.is_set():
            return
        ans.text, ans.done = acc.strip(), True
        end = time.time()
        # Metricas por respuesta: de donde sale cada segundo.
        log.info("copiloto: latencia fin_pregunta->disparo %.1fs | busqueda %d ms | primer texto %.1fs | "
                 "total %.1fs | preparada %s | %d palabras",
                 ans.trigger_lag, (t_search - t_start) * 1000, (first or end) - t_start, end - t_start,
                 ans.instant_key or "-", len(acc.split()))
        log.info("copiloto: respuesta en %.1fs", end - t_start)
        self.on_answer(ans)

    @staticmethod
    def _final_text(a: Answer) -> str:
        """Lo que queda guardado: si la llamada se detuvo mientras se
        reescribia, la ultima respuesta completa y no el trozo a medias."""
        if a.timed_out and not a.text:
            return a.instant or "_(sin respuesta: el LLM tardo demasiado)_"
        if a.done or not a.last_done:
            return a.text
        return f"{a.last_done}\n\n_(respuesta anterior: la nueva no alcanzo a terminar)_"

    def render_log(self) -> str:
        return "\n\n---\n\n".join(
            f"**[{_fmt(a.at)}] {'(forzada) ' if a.forced else ''}Pregunta:** {a.question}\n\n"
            f"{self._final_text(a)}"
            for a in self.answers)
