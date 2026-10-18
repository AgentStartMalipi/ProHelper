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
from .editor import (NO_EDIT, awaiting_answer, clean_code, code_names, parse_editor, progress_note, said_progress,
                     prune_unchanged_narration, stop_point, changed_lines, changes_topic, continues_editor, editor_prompt,
                     is_go_ahead, is_story, narration_issues, output_mismatches, run_code, runnable_python, supervisor_prompt,
                     typed_code,
                     needs_editor)
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
  conditions they don't state (no "per unit" if it doesn't say so). Cite what you used ONLY on a separate
  final "Fuente:" line, never inside the spoken sentences. Use the "## key" of the prepared section
  ([why_two_degrees]), else the source's exact name attribute ([<name>]), or [brief].
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
    One short honest line in Yo's voice ("I don't remember the exact setting."), then what the
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
- A story Yo has not told yet in the Recent conversation is new to the other side: introduce it with where and
  what happened in plain words ("At Amadeus, 25 users suddenly couldn't log in to one region."). Never refer to
  it as if they knew it ("the login case", "that case", "like the X story") and never use source names.
  The same for any thing (a script, a tool, a project): the first time, say "a" and what it does ("I wrote a
  script that automates my first checks on tickets."), never "that script", "the script" or "my tool".
- The other side's own articles or papers (their team's publications) only when the question is about their
  team, their work, the organisation or that exact incident. Never as an example of Yo's own interests,
  challenges or experience, and never to illustrate a general concept or support an opinion (2FA, phishing,
  tokens, exceptions to a policy): explain or argue it on its own. "One click to many" only when the question
  names it, the device code attack or what Yo read from them. Never add details the source doesn't say
  ("before anyone noticed", "weaker checks").
- General, public technical knowledge (how a protocol, standard or common tool works) is not a missing fact:
  explain it plainly, without "⚠" and without citing a source for it. Never present it as Yo's own experience.
- A gap the sources already state ("I haven't done X yet") is NOT missing: no "⚠", just say it as Yo would.
- Before saying Yo hasn't done something, look in the sources for the closest real thing Yo did and lead with
  it ("Yes, partly. At an AWS hackathon, I connected two VMs with a secure, authenticated tunnel."; Puppet or
  Ansible -> the AWS CDK, infrastructure as code in Python). Only if nothing is close, say the gap.
- "I haven't" at most once per answer, and never as the first words if Yo already said a gap in the Recent
  conversation: then start straight with the approach ("The way I would approach it is..."). Interview
  feedback (2026-10-14): chaining "I haven't done that" sounded weak.
- Never play down Yo's work ("I was nothing in particular", "just an intern", "only small things"): say the
  technical work from the sources.
- Never invent Yo's personal setup or habits (what Yo runs at home, labs, hobbies, side projects, tools Yo
  likes): only what the sources say. If it is not there, "⚠" and a short general answer.
- Amadeus cases stay high level: what happened and Yo's part, never internal tool names, dates ("last week"),
  ticket details or the client.
- Yo's local time is given at the end of the message: use it for small talk about time zones or the time of day.
- A specialised attack or technique that is not in the sources (Kerberoasting, pass-the-hash...): open with
  "I'm not sure about the details, but here's how I'd reason about it." then reason in plain words from
  what Yo knows. Never explain it as if Yo were an expert in it: after that opener, at most 2-3 short lines in
  plain words, no textbook internals, or it sounds read. Only for a named technique Yo may not know: never for
  a judgment scenario ("what do you do if..."), a well-known incident Yo can explain, or a topic the other side
  presents as their own (their incident, their article).
- Only say what can be observed from where the data comes from: from the network you see connections,
  domains, timing and volume, never CPU, memory or processes.
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
    and never "honestly" or "to be honest": Yo overuses it.
  - Short, complete spoken sentences, about 15 words per line at most: subject and verb, not note fragments
    ("The closest I've done is...", not "Closest example is..."). No filler like "I am a person who is...".
  - Write "I would", never "I'd": Yo reads "I'd" aloud as "I had", which claims Yo already did it (seen live
    2026-10-14: "I had scanned images", "I had approached it").
  - Easy to read aloud in one go: normal spoken order, "I" + verb early ("I'd keep..."), never a fronted
    object ("Hot storage, I'd keep short"). At most one comma per sentence, no asides between commas, no
    quotes inside a line. Each line links to the one before with a simple word ("For older data,", "That's
    because", "So", "But", "And then"), so it reads as one story.
    Bad: "Hot storage in OpenSearch, I'd keep short, maybe days to a couple weeks, for fast search." /
    "Older data I'd move to cheaper cold storage, kept longer, for hunting."
    Good: "I'd keep the recent data in OpenSearch for about two weeks." / "That's what you search during an
    investigation." / "For older data, I'd move it to cheaper storage and keep it longer."
  - Never describe the role, the job ad or the other side's own work back to them ("that's the SOC side of this
    role", "this role includes...", listing their tools): they wrote it. Give Yo's own reasoning instead.
  - Plain everyday words: Yo is not a native speaker and reads it live. "different" not "heterogeneous",
    "many" not "a wide mix of", "reach" not "connectivity", "idea" not "conceptually", "first checks" or "investigate" not "triage" (Yo
    finds it hard to pronounce). Technical terms of the
    field (LDAP, Kubernetes, gateway) are fine; fancy general words are not. Write big numbers in words
    ("two hundred thousand", not "200,000"): Yo misreads them live.
  - Do not repeat what Yo already said in the Recent conversation: the same disclaimer, the same example or the
    same closing line. Build on it instead ("as I said, ...") or leave it out.
  - A follow-up on a story Yo already told gets only the new detail the question asks for, in 2-3 lines.
    Never retell its setup or the facts already said (who was affected, the numbers, what was ruled out, who
    fixed it). If they ask for another or a "worst" example and one story was already told, use a different
    story from the sources, or say in one line that it is still that one and add only something new. Never say
    Yo has no other example.
  - The last line is a short, firm conclusion that can stand alone ("A ticket isn't closed until it's
    understood."). Nothing after it: no trailing qualifier, no afterthought, no tag question ("right?",
    "a buffer?"). Every statement ends with a period; only real questions end with "?".
  - If the other side states a wrong fact or number, correct it politely in the first line: "Actually, I think
    it was the opposite: the attack got around 2FA." / "Actually, I read it's about two hundred thousand."
    Never "that's your number" or anything that sounds like blame.
  - "That's wrong.", "You tell me." or "I disagree." with no reason is usually a pressure test: never back
    down from a sound answer and never "You're right" without a reason they gave. If Yo has not asked yet, first
    line "Could you tell me what you see differently?". If Yo already asked ("What's wrong?") and they say "You
    tell me", first line "I'd stand by it.", then one line restating the core reason, then, only if the answer
    missed a real step, "If anything, I'd add ..." with that step. Only a clear factual slip gets corrected, in
    one line ("Sorry, I meant ss, not netstat.").
  - Something that happens on a schedule ("every night at 2 AM") is not happening now: live views (netstat, ss,
    lsof, ps) show nothing. First find what schedules it (cron, systemd timers), then catch the next run.
  - Unusual traffic (a foreign IP, a new port) is not proof of an attack: say what else it could be (a backup, an
    update job) and how Yo would confirm it before calling it malicious. Name exact commands with their flags
    when they fit (ss -tunap, ps -fp, journalctl, systemctl list-timers, crontab -l). An investigation answer
    ends with containment once it is confirmed: block, isolate but keep the evidence, rotate credentials.
  - Investigation steps Yo would do are "I'd check", never "I had checked" or "I checked" (that claims Yo did it).
  - A very short, abstract question that could mean several things ("Choose two: freedom, security,
    convenience.") starts with a scope check ("Sorry, for CERN overall, or for a specific system?"), then a
    short answer for the most likely reading.
  - Something the sources say Yo "would" do or plans to do stays a plan ("I'd practice on CTFs"), never a
    present fact ("I'm practicing on CTFs").
  - After a "what" (what you'd do, how long, which tool), add one line with "because" that gives the
    long-term reason, from the sources when they have a real case.
  - Judgment questions ("Would you remove it?", "Would you log in?") start with a clear, full negative or
    positive: "No. I would not remove it." Never "won't" or a contraction that can be misheard as "will".
  - A number appears at most once and always the same: only numbers from the sources, written the way the
    brief says to say them. If a number is not in the sources, describe it without one ("a token that stays
    valid for a long time").
  - If the transcribed question looks garbled or could mean two things (a word that doesn't fit the call,
    like "S3" when the talk is about CERN overall), the first line is a short check ("Sorry, for CERN
    overall, or for a specific system?"), then answer the most likely reading.
  - End on the substance. Do not close with a disclaimer or an offer to confirm ("I haven't done this myself",
    "happy to confirm", "I'd check with the team"), except for a missing fact about the other side or the business.
  - Never a list of jobs or facts glued together ("X, before that Y, currently Z"). Say it the way people talk:
    "Right now I'm at <A> doing <B>." then "Before that I did <C>."
  - Shape (pattern only, take every fact from the BRIEF or SOURCES):
    Sure — so right now I'm <role> at <company>.
    <one short line on what that looks like>.
    Before that, <previous step>.
    And for me, <why this question matters to me, from the sources>.
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
sources. Keep the spoken voice too: follow the guide's opening style; if it gives none, use a short natural
connector varied between answers. Use only first-person lines Yo can say
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


_NUM_WORDS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve "
                                         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
                                         "twenty".split())}
_NUM_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                   "hundred": 100, "thousand": 1000})
_ABOUT_YO = re.compile(r"\b(?:I|I'm|I've|I'd|I'll|my|me|we|our|us)\b")
_NOT_NAMES = {"I", "I'm", "I've", "I'd", "I'll", "Okay", "Yes", "No", "So", "And", "But", "Then", "The", "That",
              "This", "It", "If", "When", "For", "At", "In", "On", "One", "First", "Second", "Third"}


_STOPW = {"the", "and", "that", "this", "with", "for", "will", "would", "have", "from", "into", "then", "just", "also",
          "which", "what", "about", "should", "there", "are", "was", "but", "not", "you", "your", "our", "can"}


_SINCE_RE = re.compile(r"since (?:our|the) (?:first|last) (?:interview|conversation|round)", re.I)


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z']{3,}", (text or "").lower())} - _STOPW


def _say_lines(script: str) -> list[str]:
    return [line for _, lines in parse_editor(script) for kind, line in lines if kind == "say"]


def _join(a: str, b: str) -> str:
    return f"{a}\n\n{b}" if a and b else a or b


class _AnyEvent:
    """Se cumple si se cumple cualquiera: cancelar la respuesta o el corte duro de la pizarra."""

    def __init__(self, *events: threading.Event) -> None:
        self.events = events

    def is_set(self) -> bool:
        return any(e.is_set() for e in self.events)


def unsupported_facts(answer: str, notes: str) -> list[str]:
    """Numeros y nombres propios que AL VUELO dice sobre Yo ("I...", "my...") y que no estan en sus
    notas: posibles inventos. Sin modelo (investigacion 2026-10-17: verificar cada dato contra la
    fuente, en local). Solo avisa; no borra nada."""
    low = (notes or "").lower()
    if not low:
        return []
    found: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", answer or ""):
        if not _ABOUT_YO.search(sent):
            continue
        # Un numero cuenta como respaldado si en las notas va con la misma palabra cercana:
        # "five certifications" no lo respalda un "five thousand" de otra parte (eran tres).
        words = re.findall(r"[a-z0-9][a-z0-9,.']*", sent.lower())
        for i, w in enumerate(words):
            value = _NUM_WORDS.get(w)
            if value is None and re.fullmatch(r"\d[\d,.]*", w):
                value = w
            if value is None or value in (0, 1):
                continue
            forms = {str(value), w} | {k for k, v in _NUM_WORDS.items() if str(v) == str(value)}
            nxt = next((x for x in words[i + 1:i + 4] if len(x) > 3 and x not in _NUM_WORDS), "")
            near = rf"(?:\W+[\w'-]+){{0,3}}\W+{re.escape(nxt[:6])}" if nxt else ""
            if not any(re.search(rf"\b{re.escape(f)}\b{near}", low) for f in forms):
                found.append(f"{w} {nxt}".strip())
        tokens = sent.split()
        for tok in tokens[1:]:  # la primera palabra va en mayuscula por ser el inicio
            name = tok.strip(".,;:!?\"'()“”’")
            if len(name) > 2 and name[0].isupper() and name not in _NOT_NAMES and name.lower() not in low:
                found.append(name)
    return list(dict.fromkeys(found))


FOLLOWUP_TASK = """This is NOT a question for Yo: the other side just answered one of Yo's questions (or explained
something). Help Yo keep the conversation going. Write, in the answer language, only these lines:
- Line 1: a short, natural reaction to one specific thing they just said (max 15 words). No praise ("great answer",
  "very interesting"), no summary of what they said.
- Then 1 or 2 follow-up questions Yo could ask, one per line, each built on a concrete detail they just said. Open,
  simple, easy to say. Never a question they already answered or one Yo already asked in the conversation.
- Last line: "Or next: " followed by the next question from 'questions_for_them' that Yo has NOT asked yet in the
  conversation, introduced the way the notes do ("The second one is about the role. ..."). If Yo already asked all
  three main ones, the last line is: "Or close: That's all from me, thank you, this was really helpful."
Never invent facts about them, their team or CERN: build only on what they said and on the SOURCES. Questions end
with "?"; nothing else does."""

CLARIFY_TASK = """This is NOT a new question: during a live coding exercise, the interviewer just answered Yo's
clarifying question (or told Yo to decide). Write only 1-2 short spoken lines, in the answer language: acknowledge
and state the decision Yo now takes ("Okay, so I will assume isolated means one region has eighty percent or more of
the failures."), then how Yo continues ("I will keep it as a parameter and go on with the code."). If they gave a
value or a rule, use theirs; if they told Yo to decide, use the proposal already on the editor."""


def _local_zone() -> str:
    off = -(time.altzone if time.localtime().tm_isdst > 0 else time.timezone) // 60
    return f"UTC{'+' if off >= 0 else '-'}{abs(off) // 60}"


def answer_prompt(question: str, brief: str, sources: str, recent: str, mode: str,
                  guide: str = "", notes: str = "", followup: bool = False, board: str = "",
                  clarify: bool = False, glossary: str = "", used: list[str] | None = None,
                  since_count: int = 0) -> tuple[str, str]:
    """`notes` (ver `full_notes`): el brief y las notas van enteros al INICIO del
    system, fijos durante la llamada (documentos largos arriba, la pregunta al
    final; y el prefijo fijo queda en la cache). Sin `notes`, el brief y los
    pasajes buscados van en el mensaje, como antes. `followup`: el otro acaba de
    contestar una pregunta de Yo; se piden preguntas de seguimiento (el system no
    cambia, asi sirve el `claude` pre-arrancado)."""
    what = MODES.get(mode, MODES["llamada"])
    system = with_guide(ANSWER_SYSTEM.format(what=what), guide)
    if followup:
        ask = f"""## The other side just said this
<said>
{question}
</said>

{FOLLOWUP_TASK}"""
    elif clarify:
        ask = f"""## The interviewer just said this (an answer to Yo's clarifying question)
<said>
{question}
</said>

{CLARIFY_TASK}"""
    else:
        # Al final, junto a la pregunta: es donde mas se respeta. Yo lo lee en voz
        # alta en vivo; con frases largas se pierde y las deja a medias (practica
        # del 2026-10-17: primeras frases de 12-27 palabras, frases de hasta 40).
        ask = f"""## Answer this (said by the other side)
<question>
{question}
</question>

Yo reads your answer aloud, live: the first sentence answers in 4 to 10 words, so Yo can start talking at once.
For "name one X" questions, start with the thing itself: "Unusual use of the credential." / "Firewall rules
between zones." / "Security owns that decision." Then explain in the next sentences.
Every other sentence has at most 15 words and one idea; cut a longer one into two. 3 to 5 sentences in total.
Check the conversation first: an example, story, incident or number Yo already used is not told or explained
again (at most a short "like that July case"); bring a new argument instead.
If the notes do not cover a personal fact the question needs, do not invent one: give the approach instead
("I haven't done exactly that, but here is how I would approach it.").
If the brief lists a reading of Yo's that is ABOUT this exact topic (a panel member's slides or talk, a Bulletin
article), name it in the first or second sentence; never stretch a reading to a different topic, and never cite
something the brief says Yo did not read. When it fits, name it ("In Liviu's slides I saw...", "I read your article..."): citing their own
work is what earns the points; then the concrete content."""
    shared =(f"""## What Yo already typed in the shared editor (the interviewer sees it; refer to it, stay consistent)
<editor>
{board}
</editor>

""" if board else "")
    extra = ""
    if glossary:
        extra += (f"## Terms of this interview (the transcript is speech recognition: a similar-sounding word means "
                  f"the term when the context fits)\n{glossary}\n\n")
    if since_count >= 2:
        extra += ("## Yo already said \"since our first interview/conversation\" twice: do not say it again; "
                  "for what Yo studied, say \"I read...\", \"I went through...\" or \"I looked into...\".\n\n")
    if used:
        extra += ("## Prepared answers Yo already told in this conversation: " + ", ".join(used) + ". When another "
                  "example fits, use it; for these, at most a short back-reference.\n\n")
    tail = shared + extra + f"""## Recent conversation
<conversation>
{recent}
</conversation>

{ask}

Yo's local time now: {time.strftime("%H:%M")} ({_local_zone()})
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

_HONEST = r"(?:honestly|to be honest|frankly)"
_HONEST_START = re.compile(r"(^|(?<=[.!?] )|(?<=[\"“]))" + _HONEST + r",?\s+(\w)", re.I | re.M)
_HONEST_MID = re.compile(r",?\s+" + _HONEST + r"\b,?", re.I)


def drop_honestly(text: str) -> str:
    """Quita "honestly" y parecidos aunque el prompt ya lo prohibe: Yo lo dice
    de mas y el modelo lo sigue metiendo. Si abria la frase, la siguiente
    palabra pasa a mayuscula."""
    text = _HONEST_START.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return _HONEST_MID.sub("", text)


_I_D = re.compile(r"\b([Ii])['’]d\s+(\w+)(?=(\s+\w+)?)")
_HAD_NEXT = {"been", "done", "gone", "seen", "had", "already", "made", "built", "known", "written", "taken",
             "given", "found", "thought", "heard", "told", "spent", "lost", "got", "gotten", "never"}
# "I'd read that the heat..." es pasado; "I'd read the logs" es condicional.
_READ_PAST = {"that", "about", "somewhere", "online"}


def spell_out_would(text: str) -> str:
    """"I'd" -> "I would" (o "I had" si sigue un participio): Yo lee "I'd" en
    voz alta como "I had" y suena a que ya lo hizo (entrevista 2026-10-14)."""
    def repl(m: re.Match) -> str:
        nxt = m.group(2)
        after = (m.group(3) or "").strip().lower()
        had = (nxt.lower() in _HAD_NEXT or (nxt.lower().endswith("ed") and nxt.lower() not in {"need", "feed"})
               or (nxt.lower() == "read" and after in _READ_PAST))
        return f"{m.group(1)} {'had' if had else 'would'} {nxt}"
    return _I_D.sub(repl, text)


def for_reading(text: str) -> str:
    """Lo que Yo lee en vivo: sin "honestly" y sin "I'd"."""
    return spell_out_would(drop_honestly(text))


def _is_script(text: str) -> bool:
    """Un guion tiene recuadros ("## ...") o lineas dichas ("» ..."); la prosa
    ("This isn't a question I should answer...") nunca se muestra en la pizarra."""
    return any(ln.lstrip().startswith(("##", "»")) for ln in text.splitlines())


def _said_for_reading(script: str) -> str:
    """Pizarra: las lineas "» ..." se leen en voz alta (I would, sin honestly);
    el codigo se deja tal cual."""
    return "\n".join(for_reading(ln) if ln.lstrip().startswith("»") else ln for ln in script.split("\n"))


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
    followup: bool = False  # el otro contesto una pregunta de Yo: sugerencias para seguir el hilo
    # Guion de pizarra (pestaña ✍️ Editor, ver notes/editor.py) si piden escribir algo.
    editor: str = ""
    editor_on: bool = False
    editor_done: bool = False
    editor_fresh: bool = False  # empezo un ejercicio (pizarra desde cero)
    editor_pending: bool = False  # el editor esta decidiendo (quiza NO_EDIT): la vista espera
    editor_left: bool = False  # con esta pregunta la conversacion dejo el ejercicio (cambio de tema, NO_EDIT)
    clarify: bool = False  # el entrevistador respondio la pregunta de aclaracion de Yo durante el ejercicio
    # Ejercicio en la pizarra: AL VUELO no se escribe (contaba todo el codigo por adelantado y no
    # coincidia con la pizarra). Solo si la pizarra falla (NO_EDIT, prosa, error) se escribe AL VUELO.
    board_only: bool = False
    al_vuelo_started: bool = False  # AL VUELO ya se pidio para esta pregunta (no dos veces)
    # Supervisor de la pizarra: "" | "revisando" | "ok" | "corregido" | "error"; lineas que corrigio.
    editor_check: str = ""
    editor_changed: set = field(default_factory=set)
    editor_run: str = ""  # lo que imprimio el codigo de la pizarra al ejecutarlo
    editor_before: str = ""  # lo que ya estaba escrito en el ejercicio (para marcar lo nuevo en morado)
    # La pregunta crecio con la pizarra ya visible: lo visible se queda y lo nuevo llega despues, aparte
    # (grabacion 2026-10-17 21:56: cada frase nueva la borraba y rehacia, 3 min sin nada estable).
    editor_base: str = ""  # lo ya mostrado de esta respuesta, que no se vuelve a escribir
    editor_qlen: int = 0  # hasta donde de la pregunta cubre lo ya mostrado
    editor_visible: bool = False  # la generacion en curso ya mostro algo
    editor_regrow: bool = False  # al terminar (y revisar), seguir con lo que se anadio a la pregunta
    fact_flags: list = field(default_factory=list)  # datos de Yo en AL VUELO que no estan en sus notas


# "Do you have questions for me?", "Any questions for us?", "Is there anything you'd like to ask me?"
_THEIR_TURN_RE = re.compile(r"\b(?:any|have|got)\s+(?:\w+\s+)?questions?\b|\bquestions?\s+for\s+(?:me|us)\b"
                            r"|\b(?:anything|something)\b[^.?!]{0,30}\bask\b", re.I)


def asks_for_questions(text: str) -> bool:
    """El otro le da el turno a Yo para preguntar (desde ahi, sus respuestas
    traen sugerencias de seguimiento)."""
    return question_kind(text) == "question" and bool(_THEIR_TURN_RE.search(text))


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
                 live_timeout_s: float = 0.0, followup_min_words: int = 20,
                 followup_quiet_s: float = 2.0, editor_llm: LLMClient | None = None,
                 on_editor: Callable[[Answer], None] = lambda a: None,
                 editor_window_s: float = 600.0, supervisor_llm: LLMClient | None = None,
                 supervisor_fallback_llm: LLMClient | None = None) -> None:
        # supervisor_fallback_llm: si el supervisor se niega o falla (el filtro de Opus 5.5 a
        # veces bloquea contenido de ciberseguridad legitimo, 2026-10-17), revisa este otro.
        self.supervisor_fallback_llm = supervisor_fallback_llm
        # supervisor_llm: un modelo mas capaz que revisa cada trozo de pizarra (ejecuta el
        # codigo y corrige en el sitio lo minimo). Sin el, la pizarra queda como la escribe editor_llm.
        self.supervisor_llm = supervisor_llm
        self._gloss: str | None = None
        self._prepared: list | None = None
        # editor_llm: cliente aparte para el guion de pizarra (otro system: con el
        # mismo cliente se tiraria el `claude` pre-arrancado de AL VUELO). Sin el,
        # no hay pestaña Editor. Una repregunta ("what changes if...") sigue el
        # guion anterior si llega antes de editor_window_s.
        self.editor_llm = editor_llm
        self.on_editor = on_editor
        self.editor_window_s = editor_window_s
        self._editor_cancels: dict[int, threading.Event] = {}
        # Tras "Do you have questions for me?" (ver asks_for_questions), lo que el
        # otro explica (sin pregunta) trae preguntas de seguimiento: desde
        # followup_min_words palabras y followup_quiet_s de silencio (al explicar
        # se hacen mas pausas que al preguntar).
        self.followup_min_words = followup_min_words
        self.followup_quiet_s = followup_quiet_s
        self._asking = False
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
        for ev in list(self._cancels.values()) + list(self._editor_cancels.values()):
            ev.set()
        self.llm.close()
        if self.editor_llm is not None:
            self.editor_llm.close()
        if self.supervisor_llm is not None:
            self.supervisor_llm.close()
        if self.supervisor_fallback_llm is not None:
            self.supervisor_fallback_llm.close()

    def answer_now(self) -> None:
        self._force.set()

    def editor_now(self) -> Answer | None:
        """F7: guion de pizarra para la ultima pregunta, aunque no lo pareciera. Si la
        pizarra esta parada en una pregunta de aclaracion sin respuesta, sigue con la propuesta."""
        if self.editor_llm is None or not self.enabled:
            return None
        now = self.now()
        tr = self.snapshot()
        if awaiting_answer(self._board_at(now + 1)):
            with self._lock:
                ans = Answer(len(self.answers) + 1, now, "(sin respuesta: sigo con mi propuesta)", done=True,
                             clarify=True, board_only=True)
                self.answers.append(ans)
            self._start_editor(ans, tr, forced=True)
            return ans
        with self._lock:
            last = next((a for a in reversed(self.answers) if not a.followup), None)
        if last is None:
            self.on_status("Todavia no hay pregunta para escribir en la pizarra.")
            return None
        self._start_editor(last, tr, forced=True)
        return last

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
            followup = self._asking and question_kind(q.text) == "statement"
            clarify = not followup and self._is_clarify(q, tr)
            return self._answer(q, tr, forced=True, followup=followup, clarify=clarify)
        if q is None:
            return None
        words = len(q.text.split())
        followup = self._asking and question_kind(q.text) == "statement"
        clarify = not followup and self._is_clarify(q, tr)
        if clarify and is_go_ahead(q.text) and not awaiting_answer(self._board_at(q.start)):
            return None  # "Good. Go ahead." con el codigo ya escrito: nada que decir ni escribir
        if self._answered and self._answered[0] == q.start:
            # Ya respondido: solo se rehace si el otro siguio hablando.
            grown = words - len(self._answered[1].split())
            if grown < (2 * self.min_words if followup else self.min_words):
                return None
        if followup:
            if words < self.followup_min_words:
                return None
        elif words < self.min_words or (question_kind(q.text) == "statement" and not clarify):
            return None
        if self.pending() > 0 or self._they_are_talking(q):
            return None
        # Si ya empezaste a responder ("buena pregunta, dejame ver..."), no se
        # espera el silencio: justo ahi es cuando mas sirve la ayuda.
        me_after = any(a >= q.end - 0.2 for a, _ in self._intervals(ME, tr))
        unfinished = seems_unfinished(q.text)
        wait = self.incomplete_quiet_s if unfinished else self.quiet_s
        if followup:
            wait = max(wait, self.followup_quiet_s)
        elif self.eager_s > 0 and not unfinished and q.text.rstrip().endswith("?"):
            # Especulativo: la pregunta ya cerro. Si el otro sigue hablando,
            # `_answer` cancela esta y la rehace con la pregunta completa.
            wait = min(wait, self.eager_s)
        if not me_after and self.now() - q.end < wait:
            return None
        return self._answer(q, tr, followup=followup, clarify=clarify)

    # --- respuesta ---

    def _answer(self, q: _Pending, tr: Transcript, forced: bool = False, followup: bool = False,
                clarify: bool = False) -> Answer:
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
            ans.followup = followup
            ans.clarify = clarify
            ans.al_vuelo_started = ans.board_only = False
            self._cancels[ans.id] = cancel
            self._cancel = cancel
            ans.trigger_lag = max(0.0, self.now() - q.end)
            # Lo que el otro explica no es una pregunta preparada: sin MEMORIA.
            ans.instant, ans.instant_key = ("", "") if followup or clarify else self._instant_for(q.text)
            if not followup and (ans.instant_key == "questions_for_them" or asks_for_questions(q.text)):
                self._asking = True  # desde aqui, sus respuestas traen seguimiento
        if not followup:
            board = self._start_editor(ans, tr)  # antes de mostrar nada: la vista ya sabe si hay pizarra
        else:
            board = False
        # Ejercicio nuevo o respuesta a la aclaracion: todo va en la pizarra, paso a paso
        # (ans.board_only lo decide _start_editor; si la pizarra falla, _al_vuelo_fallback).
        if not board:
            ans.board_only = False
        if ans.board_only and not ans.text:
            ans.text, ans.done = "", True
            self.on_answer(ans)
            return ans
        if ans.instant:
            self.on_answer(ans)  # la preparada (MEMORIA) se ve ya; la del LLM (AL VUELO) llega despues
        self._start_al_vuelo(ans, tr, cancel)
        return ans

    def _start_al_vuelo(self, ans: Answer, tr: Transcript, cancel: threading.Event) -> None:
        with self._lock:
            if ans.al_vuelo_started:
                return
            ans.al_vuelo_started = True
        threading.Thread(target=self._generate, args=(ans, tr, cancel), name="speak-copilot-llm",
                         daemon=True).start()

    def _al_vuelo_fallback(self, ans: Answer, tr: Transcript) -> None:
        """La pizarra no dio guion: que al menos haya respuesta para leer."""
        if not ans.board_only or ans.question.startswith("(sin respuesta"):
            return
        ans.board_only, ans.done = False, False
        cancel = self._cancels.get(ans.id) or threading.Event()
        self._start_al_vuelo(ans, tr, cancel)

    # --- pizarra (pestaña Editor) ---

    def _is_clarify(self, q: _Pending, tr: Transcript) -> bool:
        """Durante un ejercicio, el otro contesta la pregunta de aclaracion de Yo
        ("Define it yourself. State your assumption"): la pizarra se actualiza.
        Vale si no es otra pregunta y, o bien no pide nada, o Yo acababa de preguntar."""
        if not self._exercise_open(q.start):
            return False
        kind = question_kind(q.text)
        if kind == "question":
            return False
        mine = [s for s in tr.segments if s.speaker == ME and s.end <= q.start + 0.5]
        yo_asked = bool(mine) and question_kind(mine[-1].text) == "question"
        return kind == "statement" or yo_asked

    def _spec_since(self, tr: Transcript, at: float) -> str:
        """Todo lo que el entrevistador pidio en este ejercicio, en orden (registro de la especificacion)."""
        turns, cur = [], []
        for s in tr.segments:
            if s.start < at - 1:
                continue
            if s.speaker == ME:
                if cur:
                    turns.append(" ".join(cur))
                cur = []
            elif not only_fillers(s.text):
                cur.append(s.text)
        if cur:
            turns.append(" ".join(cur))
        return "\n".join(f"- {t}" for t in turns if len(t.split()) >= 3)

    def _glossary(self) -> str:
        if self._gloss is None:
            from .live import glossary_from
            texts = self.kb.extra_texts().values() if self.kb is not None else []
            self._gloss = glossary_from(self._brief(), self._guide(), *texts, max_chars=400)
        return self._gloss

    def _used_prepared(self, tr: Transcript) -> list[str]:
        """Respuestas preparadas que Yo ya dijo en esta conversacion (registro de lo ya usado)."""
        if self.kb is None:
            return []
        if self._prepared is None:
            items = []
            for text in self.kb.extra_texts().values():
                for m in re.finditer(r"^##\s+(\w+)\s+-.*\n((?:(?!##).*\n?)+)", text, re.M):
                    words = _content_words(m.group(2))
                    if len(words) >= 8:
                        items.append((m.group(1), words))
            self._prepared = items
        said = _content_words(" ".join(s.text for s in tr.segments if s.speaker == ME))
        if not said:
            return []
        return [key for key, words in self._prepared if len(words & said) / len(words) >= 0.5][:8]

    def _notes_text(self) -> str:
        texts = self.kb.extra_texts() if self.kb is not None else {}
        return "\n".join([self._brief(), *texts.values()])

    def _exercise_start(self, ans: Answer) -> float:
        """Cuando empezo el ejercicio de la pizarra actual (la respuesta que la abrio de cero)."""
        board = [a for a in self.answers if a is not ans and a.editor and a.at < ans.at]
        fresh = [a for a in board if a.editor_fresh]
        return (fresh[-1] if fresh else board[0]).at if board else ans.at

    @staticmethod
    def _yo_speech_since(tr: Transcript, at: float) -> str:
        return " ".join(s.text for s in tr.segments if s.speaker == ME and s.start >= at)

    def _exercise_open(self, at: float) -> bool:
        return self.editor_llm is not None and bool(self._board_at(at))

    def _editor_previous(self, ans: Answer) -> str:
        return self._board_at(ans.at, ans)

    def _board_at(self, at: float, ans: Answer | None = None) -> str:
        """Todo lo escrito en la pizarra en este ejercicio (desde el que empezo
        de cero), si la ultima pizarra fue hace menos de editor_window_s."""
        board = [a for a in self.answers if a is not ans and a.editor and a.at < at]
        if not board or at - board[-1].at > self.editor_window_s:
            return ""
        if any(a.editor_left and board[-1].at < a.at < at for a in self.answers if a is not ans):
            return ""  # despues de la pizarra se cambio de tema: el ejercicio quedo cerrado
        start = max((i for i, a in enumerate(board) if a.editor_fresh), default=0)
        return "\n\n".join(a.editor for a in board[start:])

    def _start_editor(self, ans: Answer, tr: Transcript, forced: bool = False) -> bool:
        if self.editor_llm is None:
            return False
        previous = self._editor_previous(ans)
        new = needs_editor(ans.question)
        # Con un ejercicio en la pizarra, toda repregunta que no sea una historia
        # va al editor; el LLM decide si escribir, solo decir o NO_EDIT. Si no
        # es una repregunta obvia, la pestaña no se abre hasta que haya algo.
        cont = bool(previous) and (ans.clarify or (not is_story(ans.question) and not changes_topic(ans.question)))
        # La pizarra esperaba la respuesta a sus preguntas y el entrevistador concreta el ejercicio
        # ("Show me the actual class. It must disable root login..."): es la respuesta, se sigue.
        if cont and not ans.clarify and awaiting_answer(previous):
            ans.clarify = True
        ans.editor_left = bool(previous) and not cont and not new
        if not (forced or new or cont):
            if ans.editor_on and not ans.editor_done:  # la pregunta crecio y ya no pide pizarra
                self._editor_cancels.get(ans.id, threading.Event()).set()
                ans.editor_on = False
            ans.editor_pending = False
            return False
        # Con un ejercicio abierto, "write / show me / continue" sigue la MISMA pizarra (grabacion
        # 2026-10-17 19:15: cada turno empezaba de cero y cambiaba hasta el nombre de la clase). Si es
        # otro problema, el modelo empieza con "## Entender" y desde ahi cuenta como pizarra nueva.
        # La pestaña se abre ya solo si es seguro; una repregunta la abre cuando llega contenido (sin parpadeo).
        sure = forced or new or ans.clarify
        with self._lock:
            busy = (ans.editor_pending and ans.editor_visible) or ans.editor_check == "revisando"
            if busy and not forced:
                # Ya se esta leyendo: no se borra ni se rehace; lo nuevo va despues, como otro Cambio.
                ans.editor_regrow = True
                ans.board_only = ans.clarify or new or bool(ans.editor)
                return True
            old = self._editor_cancels.get(ans.id)
            if old is not None:
                old.set()
            cancel = threading.Event()
            self._editor_cancels[ans.id] = cancel
            if ans.editor_done and ans.editor_on and ans.editor and not forced:
                ans.editor_base = ans.editor  # terminada y vista: se queda; lo nuevo se anade debajo
            elif forced:
                ans.editor_base, ans.editor_qlen = "", 0
            base = ans.editor_base
            if not base:
                ans.editor_qlen = 0
            ans.editor, ans.editor_on, ans.editor_done = base, sure or bool(base), False
            ans.editor_check, ans.editor_run = "", ""
            if not base:
                ans.editor_changed = set()
                ans.editor_fresh = not previous
                ans.editor_before = previous
            ans.editor_pending, ans.editor_visible, ans.editor_regrow = True, False, False
            if not forced:  # se decide antes de lanzar el editor (si no, carrera con su final)
                ans.board_only = ans.clarify or new or bool(base)
        if sure or base:
            self.on_editor(ans)
        threading.Thread(target=self._generate_editor, args=(ans, tr, cancel, _join(previous, base)),
                         name="speak-copilot-editor", daemon=True).start()
        return True

    def _continue_regrow(self, ans: Answer) -> None:
        """La pregunta crecio mientras la pizarra se escribia o revisaba: ahora se sigue con lo nuevo."""
        if not ans.editor_regrow:
            return
        ans.editor_regrow = False
        try:
            self._start_editor(ans, self.snapshot())
        except Exception:
            log.exception("copiloto: pizarra (continuacion)")

    def _generate_editor(self, ans: Answer, tr: Transcript, cancel: threading.Event, previous: str) -> None:
        t0 = time.time()
        start = self._exercise_start(ans)
        progress = progress_note(previous, self._yo_speech_since(tr, start)) if previous else ""
        spec = self._spec_since(tr, start) if previous else ""
        base = ans.editor_base
        # Con algo ya mostrado en esta respuesta, al modelo solo le toca lo que el entrevistador anadio.
        question = (ans.question[ans.editor_qlen:].strip() if base else "") or ans.question
        ans.editor_qlen = len(ans.question)
        system, user = editor_prompt(question, render(tr)[-RECENT_CHARS:], previous, ans.instant,
                                     clarify=ans.clarify, progress=progress, spec=spec,
                                     code=clean_code(previous) if previous else "", glossary=self._glossary())
        acc = ""
        halt = threading.Event()  # corte duro propio: para la generacion sin cancelar la respuesta
        both = _AnyEvent(cancel, halt)
        try:
            for chunk in self.editor_llm.stream(system, user, both):
                if cancel.is_set():
                    return
                if halt.is_set():
                    continue  # el CLI se cierra en la siguiente linea; lo que llegue ya no cuenta
                acc += chunk
                if not previous and not ans.clarify:
                    cut = stop_point(acc)
                    if cut is not None:  # pregunto en el Entender: aqui se para, pase lo que pase
                        acc = acc[:cut]
                        halt.set()
                head = acc.strip()
                if NO_EDIT.startswith(head[:len(NO_EDIT)]) or not _is_script(acc):
                    continue  # quiza "NO_EDIT" o prosa: no se muestra nada todavia
                shown = prune_unchanged_narration(_said_for_reading(acc), previous)
                ans.editor, ans.editor_on, ans.editor_visible = _join(base, shown), True, True
                self.on_editor(ans)
        except Exception as exc:
            log.exception("copiloto: pizarra")
            ans.editor_pending = False
            self.on_status(f"pizarra: {exc}")
            self.on_editor(ans)
            self._al_vuelo_fallback(ans, tr)
            return
        if cancel.is_set():
            return
        ans.editor_pending = False
        part = ""
        if acc.strip().startswith(NO_EDIT) or not _is_script(acc):  # no era del ejercicio, o prosa sin guion
            ans.editor, ans.editor_on, ans.editor_done = base, bool(base), True
            # Una aclaracion o un "go ahead" sin nada que escribir NO cierra el ejercicio
            # (grabacion 2026-10-17 15:16: la repregunta siguiente se quedo sin pizarra).
            ans.editor_left = not base and not ans.clarify and not needs_editor(ans.question)
            if not base:
                self._al_vuelo_fallback(ans, tr)
        else:
            part = prune_unchanged_narration(_said_for_reading(acc), previous).strip()
            ans.editor, ans.editor_on, ans.editor_done = _join(base, part), True, True
            boxes = parse_editor(part)
            if previous and not base and boxes and boxes[0][0].lower().startswith("entender"):
                ans.editor_fresh = True  # el modelo vio otro problema: la pizarra empieza aqui
        log.info("copiloto: pizarra en %.1fs | %d lineas | %s", time.time() - t0, len(acc.splitlines()),
                 "sin cambios" if not ans.editor_on else "continua" if previous else "nueva")
        supervise = bool(part) and self.supervisor_llm is not None
        if supervise:
            ans.editor_check = "revisando"
        elif base:
            ans.editor_check = ans.editor_check or "ok"
        self.on_editor(ans)
        if supervise:
            threading.Thread(target=self._supervise, args=(ans, tr, cancel, previous, part),
                             name="speak-copilot-supervisor", daemon=True).start()
        else:
            self._continue_regrow(ans)

    def _supervisor_reply(self, system: str, user: str) -> str:
        try:
            return self.supervisor_llm.complete(system, user).strip()
        except Exception as exc:
            if self.supervisor_fallback_llm is None:
                raise
            log.warning("copiloto: supervisor no respondio (%s); reviso el respaldo", str(exc)[:160])
            return self.supervisor_fallback_llm.complete(system, user).strip()

    def _supervise(self, ans: Answer, tr: Transcript, cancel: threading.Event, previous: str,
                   part: str | None = None) -> None:
        try:
            self._supervise_part(ans, tr, cancel, previous, ans.editor if part is None else part)
        finally:
            if not cancel.is_set():
                self._continue_regrow(ans)

    def _supervise_part(self, ans: Answer, tr: Transcript, cancel: threading.Event, previous: str,
                        part: str) -> None:
        """Ejecuta lo escrito y deja que un modelo mas capaz corrija lo minimo, en el sitio.
        Dos pasadas como mucho: si su correccion aun falla al ejecutarse, se la devuelve."""
        t0 = time.time()
        base = ans.editor_base
        try:
            for attempt in range(2):
                code = typed_code(f"{previous}\n\n{part}" if previous else part)
                run, rc = None, 0
                if runnable_python(code):
                    rc, out = run_code(code)
                    run = f"exit code {rc}\n{out}"
                    ans.editor_run = run
                issues = narration_issues(part)
                if previous:
                    before, now = code_names(clean_code(previous)), code_names(clean_code(previous + "\n\n" + part))
                    gone = before - now
                    if gone and not ans.editor_fresh:
                        issues.append(f"renamed or dropped {sorted(gone)}: keep the existing names")
                    asked = [ok for ok, line in zip(said_progress(previous, self._yo_speech_since(
                        tr, self._exercise_start(ans))), _say_lines(previous)) if line.rstrip("”\"").endswith("?")]
                    if asked and not any(asked) and re.search(
                            r"\bmy (?:proposal|suggestion)\b|\bas I (?:proposed|suggested|said|asked)\b|\bI had asked\b",
                            part, re.I):
                        issues.append("says 'my proposal' / 'as I asked' but Yo never said the question aloud: "
                                      "state the decision instead")
                if run is not None and rc == 0:  # corre, pero ¿imprime lo que promete la Prueba?
                    issues += output_mismatches(typed_code(part), out)
                # Solo se edita con una senal concreta (investigacion 2026-10-17: un revisor sin senal
                # externa empeora lo que estaba bien). Python que corre limpio (con sus asserts) y sin
                # problemas de narracion: no se toca, ni se gasta la llamada.
                if run is not None and rc == 0 and not issues:
                    break
                system, user = supervisor_prompt(ans.question, render(tr)[-RECENT_CHARS:], previous, part, run,
                                                 issues)
                reply = self._supervisor_reply(system, user)
                if cancel.is_set() or ans.editor != _join(base, part) and attempt == 0:
                    return  # se reescribio la pizarra mientras revisaba
                if reply.upper().startswith("OK") or not _is_script(reply):
                    break
                fixed = prune_unchanged_narration(_said_for_reading(reply), previous).strip()
                if fixed == part:
                    break
                ans.editor_changed |= changed_lines(_join(base, part), _join(base, fixed))
                part = fixed
                ans.editor = _join(base, part)
                ans.editor_check = "corregido"
                self.on_editor(ans)
                if run is None:
                    break  # nada que volver a ejecutar
                # Solo se vuelve a preguntar al modelo si su correccion aun falla al ejecutarse
                # (la segunda consulta era casi la mitad del tiempo y casi nunca hacia falta).
                rc, out = run_code(typed_code(f"{previous}\n\n{part}" if previous else part))
                if rc == 0:
                    break
            if ans.editor_check != "corregido":
                ans.editor_check = "ok"
            if runnable_python(typed_code(f"{previous}\n\n{part}" if previous else part)):
                rc, out = run_code(typed_code(f"{previous}\n\n{part}" if previous else part))
                ans.editor_run = f"exit code {rc}\n{out}"
                if rc != 0:
                    ans.editor_check = "error"
        except Exception as exc:
            log.exception("copiloto: supervisor")
            # Nunca "revisado" si nadie reviso: ni el supervisor ni su respaldo respondieron.
            ans.editor_check = "corregido" if ans.editor_changed else "sin revisar"
            self.on_status(f"supervisor: {exc}")
        log.info("copiloto: supervisor en %.1fs | %s | %d lineas cambiadas", time.time() - t0, ans.editor_check,
                 len(ans.editor_changed))
        self.on_editor(ans)

    def _board_now(self, ans: Answer) -> str:
        """Lo que hay en la pizarra para que AL VUELO hable de ello."""
        return self._editor_previous(ans)

    def render_editor_log(self) -> str:
        return "\n\n---\n\n".join(f"**[{_fmt(a.at)}] Pregunta:** {a.question}\n\n{a.editor}"
                                  for a in self.answers if a.editor)

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
        system, user = answer_prompt(ans.question, self._brief(), sources, recent, self.mode, self._guide(), notes,
                                     followup=ans.followup, board=self._board_now(ans), clarify=ans.clarify,
                                     glossary=self._glossary(), used=self._used_prepared(tr),
                                     since_count=len(_SINCE_RE.findall(" ".join(
                                         s.text for s in tr.segments if s.speaker == ME))))
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
                ans.text = for_reading(acc)
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
        ans.text, ans.done = for_reading(acc).strip(), True
        if not ans.followup:
            ans.fact_flags = unsupported_facts(ans.text, self._notes_text())
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
            f"**[{_fmt(a.at)}] {'(forzada) ' if a.forced else ''}{'Dijo' if a.followup else 'Pregunta'}:** {a.question}\n\n"
            f"{self._final_text(a)}"
            for a in self.answers)
