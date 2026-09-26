"""Deteccion de fin de turno y de preguntas.

No basta con buscar "?": Whisper no siempre lo pone, y muchas "preguntas" de
entrevista son imperativas ("Tell me about a time..."). La decision combina:

1. **Silencio**: nada se cierra antes de ~700 ms de silencio, y siempre se
   cierra al llegar a MAX_SILENCE.
2. **Estructura**: cuanto silencio hace falta depende de como termina el
   texto. Una frase colgada ("...find the maximum", "...and", "...whose") pide
   mucho mas silencio que una pregunta redonda.
3. **Interrogativos y peticiones**: what/how/why..., "tell me", "walk me
   through", "design", "cuentame"... marcan que el turno pide respuesta.
4. **Contexto**: con una pregunta previa, un turno corto que empieza por
   "and / what about / why" es un FOLLOW_UP de esa pregunta.
5. **Varias frases**: el turno acumula todo lo dicho hasta el cierre. Y si,
   pese a todo, el turno se cerro y la persona retoma en menos de
   `merge_window_ms`, se REABRE: el consumidor recibe `TurnReopened`, cancela
   lo que estuviera generando y espera el turno completo.

El mismo analisis de texto se usa sin audio en Notas de llamada
(`segment_turns`) para marcar preguntas en una transcripcion ya hecha.

Todo el tiempo se inyecta (segundos), sin reloj propio: es deterministico y
se prueba sin microfono.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class TurnState(str, Enum):
    LISTENING = "LISTENING"
    SPEAKER_TALKING = "SPEAKER_TALKING"
    POSSIBLE_END = "POSSIBLE_END"
    QUESTION_COMPLETE = "QUESTION_COMPLETE"
    GENERATING_RESPONSE = "GENERATING_RESPONSE"


# --- analisis linguistico ----------------------------------------------------

_INTERROGATIVES = {
    # en
    "what", "why", "how", "when", "where", "which", "who", "whose", "whom",
    "is", "are", "was", "were", "do", "does", "did", "can", "could", "would",
    "will", "should", "have", "has", "had", "shall", "may", "might",
    # es
    # Solo con tilde: sin ella ("como te decia", "que bueno") suelen ser
    # afirmaciones, y Whisper tilda las interrogativas.
    "qué", "cómo", "cuándo", "dónde", "cuál", "cuáles", "quién", "quiénes",
    "cuánto", "cuántos", "puedes", "podrías", "podrias", "sabes", "tienes",
}

_WH = {"what", "why", "how", "when", "where", "which", "who"}
_SUBJECTS = {"i", "we", "they", "he", "she", "it", "you", "my", "our", "yo", "nosotros"}


def _interrogative_start(words: list[str], sentence: str) -> bool:
    if not words or words[0] not in _INTERROGATIVES or len(words) < 3:
        return False
    # "What I did was..." / "How we solved it was...": clausula relativa que
    # abre una afirmacion, no una pregunta.
    if words[0] in _WH and words[1] in _SUBJECTS and not sentence.rstrip().endswith("?"):
        return False
    return True

_REQUEST_PATTERNS = [
    r"tell me", r"describe", r"walk me through", r"walk us through", r"explain",
    r"give me", r"talk (?:me |us )?(?:about|through)", r"share", r"design",
    r"implement", r"write", r"find", r"return", r"compute", r"calculate", r"build",
    r"how would you", r"what would you", r"i'?d like (?:you|to hear)", r"i want you to",
    r"can you", r"could you", r"would you", r"let'?s say", r"suppose", r"imagine",
    r"i'?m (?:curious|wondering)", r"i was wondering", r"i'?d love to hear",
    r"please", r"go ahead and", r"what'?s your", r"let'?s (?:design|build|talk|discuss)",
    r"given (?:an?|the|two|a list|a string|an array)",
    # es
    r"cu[eé]ntame", r"descr[ií]be", r"expl[ií]ca", r"dise[nñ]a", r"implementa",
    r"escribe", r"dime", r"h[aá]blame", r"me gustar[ií]a (?:saber|que)", r"supongamos",
    r"imagina", r"por favor", r"d[aá]me un ejemplo",
]
_REQUEST_RE = re.compile(r"^(?:" + "|".join(_REQUEST_PATTERNS) + r")\b")

_TAG_QUESTION_RE = re.compile(
    r"(?:,\s*(?:right|correct|yeah|ok(?:ay)?|no|verdad|cierto|s[ií])\s*\??)$"
)

# Palabras con las que una frase NO puede terminar si esta completa.
_DANGLING = {
    # conjunciones / preposiciones / articulos / relativos (en)
    "and", "or", "but", "so", "because", "if", "then", "than", "the", "a", "an",
    "of", "to", "in", "on", "at", "for", "with", "from", "by", "into", "about",
    "whose", "while", "whether", "is", "are", "was", "were", "be", "your", "my",
    "their", "our", "its", "some", "any", "each", "every", "such", "as",
    # modificadores que piden sustantivo ("find the maximum ... subarray").
    # Fuera quedan los que tambien cierran frase como pronombre (that, this,
    # which, all, first...): mejor cerrar y reabrir que esperar de mas siempre.
    "maximum", "minimum", "max", "min", "longest", "shortest", "largest",
    "smallest", "biggest", "total", "kth", "nth", "distinct",
    # es
    "y", "o", "pero", "porque", "si", "el", "la", "los", "las", "un", "una",
    "de", "del", "a", "en", "con", "para", "por", "sobre", "cuyo", "cuya",
    "máximo", "maximo", "mínimo", "minimo", "mayor", "menor", "tu", "su",
}

_FILLERS_END = re.compile(
    r"(?:\b(?:um+|uh+|hmm+|erm|mm+|eh+|este|pues|bueno|o sea|like|you know|i mean|"
    r"let me (?:think|see)|let'?s see|so|basically|actually|anyway)\s*[.,…-]*)$"
)
_ONLY_FILLERS = re.compile(r"^(?:\s*\b(?:um+|uh+|hmm+|erm|mm+|eh+|ah+|oh+)\b[\s.,…-]*)+$")

_BEHAVIORAL_OPENER = re.compile(
    r"^(?:tell me about a time|describe a (?:time|situation)|give me an example of|"
    r"talk (?:me )?(?:about|through) a time|have you ever|cu[eé]ntame (?:de )?una vez|"
    r"describe una situaci[oó]n)"
)

_FOLLOW_UP_START = re.compile(
    r"^(?:and|but|so|also|what about|how about|what if|why|then|okay so|ok so|"
    r"could you (?:elaborate|expand|go deeper)|can you (?:elaborate|expand|go deeper)|"
    r"tell me more|go deeper|what would you do differently|what was the (?:result|outcome|impact)|"
    r"how did (?:that|it|you)|why did you|what did you learn|"
    r"y |pero |entonces |y si|por qu[eé]|qu[eé] pas[oó]|profundiza)"
)
_WORD_RE = re.compile(r"[\wáéíóúñü']+", re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!¿¡])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _strip_leading(s: str) -> str:
    # "Okay, so, tell me..." → "tell me..."; "¿Qué...?" → "qué...?"
    s = s.lstrip("¿¡\"' ")
    return re.sub(r"^(?:(?:okay|ok|alright|great|so|well|now|bueno|vale|listo|perfecto|y)[,\s]+)+", "", s)


def is_question_sentence(sentence: str) -> bool:
    s = _norm(sentence)
    if not s:
        return False
    if s.endswith("?") or s.startswith("¿") or _TAG_QUESTION_RE.search(s):
        return True
    s = _strip_leading(s)
    words = _WORD_RE.findall(s)
    if not words:
        return False
    if _interrogative_start(words, s):
        return True
    return bool(_REQUEST_RE.match(s))


def question_kind(text: str) -> str:
    """'question' (interrogativa), 'request' (imperativa que pide respuesta)
    o 'statement'. Basta con que UNA frase del turno pida respuesta."""
    kind = "statement"
    for sent in sentences(text):
        s = _strip_leading(_norm(sent))
        if s.endswith("?") or _TAG_QUESTION_RE.search(s):
            return "question"
        words = _WORD_RE.findall(s)
        if _interrogative_start(words, s):
            return "question"
        if _REQUEST_RE.match(s):
            kind = "request"
    return kind


def ends_incomplete(text: str) -> bool:
    """El texto termina "colgado": falta algo para que la idea cierre."""
    t = _norm(text)
    if not t:
        return False
    if t.endswith("?") and not t.endswith(("...?", "…?")):
        return False
    if t.endswith(("...", "…", ",", ";", ":", "-", "—")):
        return True
    words = _WORD_RE.findall(t)
    if not words:
        return False
    if words[-1] in _DANGLING:
        return True
    # "Given an array of integers." sin la tarea todavia: falta el verbo.
    last = _strip_leading(_norm(sentences(text)[-1]))
    if re.match(r"^(?:given|dado|dada|dados|dadas)\b", last) and not re.search(
        r"\b(?:find|return|compute|write|determine|count|check|implement|design|"
        r"encuentra|devuelve|calcula|escribe|determina|cuenta)\b", last
    ):
        return True
    return False


def ends_with_filler(text: str) -> bool:
    return bool(_FILLERS_END.search(_norm(text)))


def only_fillers(text: str) -> bool:
    return bool(_ONLY_FILLERS.match(_norm(text))) or not _WORD_RE.findall(text)


def is_follow_up(text: str, previous_question: str | None) -> bool:
    if not previous_question:
        return False
    s = _strip_leading(_norm(text))
    words = _WORD_RE.findall(s)
    if not words or len(words) > 25:
        return False
    if _FOLLOW_UP_START.match(s):
        return True
    # Muy corto y apoyado en la pregunta anterior: "Why?", "And the result?"
    return len(words) <= 5 and question_kind(text) != "statement"


# --- detector en vivo --------------------------------------------------------


@dataclass
class TurnConfig:
    silence_threshold_ms: int = 900
    # Silencio para cerrar una pregunta redonda. None = 0.8 x umbral. El
    # simulador lo separa: tus respuestas esperan mucho (pausas para pensar),
    # tus preguntas de aclaracion se cierran rapido.
    question_silence_ms: int | None = None
    min_silence_ms: int = 700
    max_silence_ms: int = 3000
    possible_end_ms: int = 300
    # Tras un cierre, si la persona vuelve a hablar antes de esto, se reabre.
    merge_window_ms: int = 1500


@dataclass
class TurnComplete:
    text: str
    kind: str  # question | request | statement
    is_question: bool
    is_follow_up: bool
    reason: str
    silence_ms: int
    start: float
    end: float


@dataclass
class TurnReopened:
    """La persona siguio hablando justo despues de un cierre."""

    previous_text: str


@dataclass
class StateChanged:
    state: TurnState


TurnEvent = TurnComplete | TurnReopened | StateChanged


@dataclass
class _Turn:
    parts: list[str] = field(default_factory=list)
    start: float | None = None
    end: float = 0.0

    @property
    def text(self) -> str:
        return " ".join(self.parts).strip()


class TurnDetector:
    """Alimentalo con los eventos de audio y de transcripcion:

    - `speech_started(t)`: empieza voz.
    - `utterance_ended(t)`: el segmentador cerro una frase y la mando a STT.
    - `add_text(text, start, end, t)`: llego el texto de esa frase.
    - `silence(t, silence_ms)`: tick de silencio.

    Cada metodo devuelve la lista de eventos que produjo. El turno nunca se
    cierra con transcripciones pendientes: el silencio puede ser suficiente,
    pero sin el texto no sabemos si la frase quedo colgada.
    """

    def __init__(self, config: TurnConfig | None = None) -> None:
        self.cfg = config or TurnConfig()
        self.state = TurnState.LISTENING
        self.previous_question: str | None = None
        self._turn = _Turn()
        self._pending = 0
        self._silence_ms = 0
        self._last_complete_at: float | None = None
        self._last_complete_text = ""
        self._turn_start_prev: float | None = None

    # -- entradas --

    def speech_started(self, t: float) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        self._silence_ms = 0
        if (
            self.state in (TurnState.QUESTION_COMPLETE, TurnState.GENERATING_RESPONSE)
            and self._last_complete_at is not None
            and (t - self._last_complete_at) * 1000 <= self.cfg.merge_window_ms
        ):
            # Retomo enseguida: era una pausa, no el final. Se reabre el turno
            # con lo que ya se habia dicho.
            self._turn = _Turn(parts=[self._last_complete_text], start=self._turn_start_prev)
            events.append(TurnReopened(previous_text=self._last_complete_text))
            self._last_complete_at = None
        elif self.state in (TurnState.QUESTION_COMPLETE, TurnState.GENERATING_RESPONSE):
            # Turno nuevo despues de uno cerrado: lo de antes ya no se reabre.
            self._last_complete_at = None
        events += self._set(TurnState.SPEAKER_TALKING)
        return events

    def utterance_ended(self, t: float) -> list[TurnEvent]:
        self._pending += 1
        return []

    def add_text(self, text: str, start: float, end: float, t: float) -> list[TurnEvent]:
        self._pending = max(0, self._pending - 1)
        text = text.strip()
        if text:
            if self._turn.start is None:
                self._turn.start = start
            self._turn.parts.append(text)
            self._turn.end = end
        return self._evaluate(t)

    def silence(self, t: float, silence_ms: int) -> list[TurnEvent]:
        self._silence_ms = silence_ms
        return self._evaluate(t)

    def text_arrived_without_audio(self) -> None:
        """Por si la frase se descarto (alucinacion): libera el pendiente."""
        self._pending = max(0, self._pending - 1)

    # -- control externo --

    def mark_generating(self) -> list[TurnEvent]:
        return self._set(TurnState.GENERATING_RESPONSE)

    def pending(self) -> int:
        return self._pending

    def force(self, t: float) -> list[TurnEvent]:
        """Cierra el turno ya (boton "Termine"), con el texto que haya."""
        text = self._turn.text
        if not text:
            return self.reset()
        kind = question_kind(text)
        follow = is_follow_up(text, self.previous_question)
        event = TurnComplete(
            text=text, kind=kind, is_question=kind != "statement" or follow,
            is_follow_up=follow, reason="cierre manual", silence_ms=self._silence_ms,
            start=self._turn.start or 0.0, end=self._turn.end,
        )
        self._turn = _Turn()
        self._pending = 0
        self._last_complete_at = None  # manual: no se reabre
        return [event] + self._set(TurnState.QUESTION_COMPLETE)

    def reset(self) -> list[TurnEvent]:
        self._turn = _Turn()
        self._pending = 0
        self._silence_ms = 0
        self._last_complete_at = None
        return self._set(TurnState.LISTENING)

    # -- decision --

    def required_silence_ms(self, text: str) -> tuple[int, str]:
        c = self.cfg
        if ends_incomplete(text):
            return c.max_silence_ms, "frase incompleta"
        if ends_with_filler(text):
            return min(c.max_silence_ms, int(c.silence_threshold_ms * 2)), "pensando en voz alta"
        sents = sentences(text)
        if len(sents) == 1 and _BEHAVIORAL_OPENER.match(_strip_leading(_norm(sents[0]))):
            # "Tell me about a time X." suele seguir con "What happened...?"
            return min(c.max_silence_ms, int(c.silence_threshold_ms * 1.4)), "apertura conductual"
        if sents and is_question_sentence(sents[-1]):
            q = c.question_silence_ms or int(c.silence_threshold_ms * 0.8)
            return max(c.min_silence_ms, q), "pregunta completa"
        return c.silence_threshold_ms, "frase completa"

    def _evaluate(self, t: float) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        if self.state not in (TurnState.SPEAKER_TALKING, TurnState.POSSIBLE_END):
            return events
        text = self._turn.text
        if self._silence_ms >= self.cfg.possible_end_ms and self.state == TurnState.SPEAKER_TALKING:
            events += self._set(TurnState.POSSIBLE_END)
        if self._pending > 0 or self.state != TurnState.POSSIBLE_END:
            return events
        if not text or only_fillers(text):
            if self._silence_ms >= self.cfg.max_silence_ms:
                events += self.reset()  # solo "umm": nada que responder
            return events
        need, reason = self.required_silence_ms(text)
        if self._silence_ms < need:
            return events
        kind = question_kind(text)
        follow = is_follow_up(text, self.previous_question)
        is_q = kind != "statement" or follow
        events.append(TurnComplete(
            text=text, kind=kind, is_question=is_q, is_follow_up=follow,
            reason=f"{reason}, {self._silence_ms} ms de silencio",
            silence_ms=self._silence_ms, start=self._turn.start or 0.0, end=self._turn.end,
        ))
        if is_q:
            self.previous_question = text
        self._last_complete_at = t
        self._last_complete_text = text
        self._turn_start_prev = self._turn.start
        self._turn = _Turn()
        events += self._set(TurnState.QUESTION_COMPLETE)
        return events

    def _set(self, state: TurnState) -> list[TurnEvent]:
        if state == self.state:
            return []
        self.state = state
        return [StateChanged(state)]


# --- modo offline (Notas de llamada) ----------------------------------------


@dataclass
class OfflineTurn:
    speaker: str
    start: float
    end: float
    text: str
    kind: str = "statement"
    is_follow_up: bool = False

    @property
    def is_question(self) -> bool:
        return self.kind != "statement" or self.is_follow_up


def segment_turns(segments, gap_s: float = 1.5) -> list[OfflineTurn]:
    """Une segmentos consecutivos del mismo hablante (con pausas menores a
    `gap_s`) en turnos, y marca cuales son preguntas o peticiones.

    `segments`: objetos con .speaker, .start, .end, .text, ordenados por tiempo.
    """
    turns: list[OfflineTurn] = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        last = turns[-1] if turns else None
        if last and last.speaker == seg.speaker and seg.start - last.end <= gap_s:
            last.text = f"{last.text} {text}"
            last.end = seg.end
        else:
            turns.append(OfflineTurn(seg.speaker, seg.start, seg.end, text))
    last_q_by: dict[str, str] = {}
    for turn in turns:
        turn.kind = question_kind(turn.text)
        # El follow-up es respecto a la ultima pregunta DEL MISMO hablante.
        turn.is_follow_up = is_follow_up(turn.text, last_q_by.get(turn.speaker))
        if turn.is_question:
            last_q_by[turn.speaker] = turn.text
    return turns
