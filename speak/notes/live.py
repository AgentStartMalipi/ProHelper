"""Notas de llamada en vivo.

Mientras `DualRecorder` graba, cada pista (microfono → "Yo", loopback →
"Ellos") pasa tambien por aqui:

    audio ─► _LiveTrack (a 16 kHz, VAD + segmentador) ─► LiveTranscriber (1 hilo, Ellos primero)
                                                               │
                        transcripcion en vivo (Yo/Ellos) ◄─────┘
                                   │ cada ~LIVE_NOTES_INTERVAL s con texto nuevo
                                   ▼
                             LLM → borrador de notas

Es un borrador: Whisper va con beam 1 y frase a frase. Al detener, la
grabacion pasa igual por la transcripcion completa (`pipeline`) y de ahi
salen las notas finales.

El loopback de WASAPI no entrega nada mientras no suena nada; sin relleno, la
ultima frase de "Ellos" se quedaria abierta hasta que volviera a sonar algo.
Por eso cada pista se rellena con silencio segun el reloj. Ojo: el hueco se
mide con la hora en que LLEGO cada bloque, no con la hora en que se procesa;
con la CPU ocupada el hilo se atrasa y, si se usara la hora actual, metia
silencio falso antes de audio que ya estaba en cola (partia frases).
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from collections import Counter
from typing import Callable

import numpy as np

from ..audio_capture import EnergyVAD, UtteranceSegmenter, Utterance
from ..llm_client import LLMClient
from ..transcriber import Segment, SpeechToText, TranscriptEvent
from .analyzer import live_notes_prompt
from .pipeline import ME, THEM, Transcript, dedupe_echo

log = logging.getLogger(__name__)

SR = 16000
_BLOCK = SR * 30 // 1000  # 30 ms, lo mismo que el simulador


def to_16k(x: np.ndarray, rate: int, carry: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Remuestrea a 16 kHz. Si `rate` es multiplo (48k, 32k) promedia de a
    grupos, que ademas filtra lo que no cabe en 16 kHz; `carry` guarda las
    muestras que sobran para el siguiente bloque. Si no, interpolacion lineal."""
    x = x.astype(np.float32, copy=False)
    if rate == SR:
        return x, np.zeros(0, np.float32)
    if rate % SR == 0:
        k = rate // SR
        if carry is not None and carry.size:
            x = np.concatenate([carry, x])
        n = len(x) // k
        return x[:n * k].reshape(n, k).mean(axis=1), x[n * k:]
    n = int(round(len(x) * SR / rate))
    if n <= 0:
        return np.zeros(0, np.float32), np.zeros(0, np.float32)
    out = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    return out.astype(np.float32), np.zeros(0, np.float32)


_TERM = re.compile(r"\b(?:[A-Z][A-Za-z0-9]*[A-Z0-9][A-Za-z0-9]*|[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,})\b")
_COMMON = {
    # Mayusculas que no son terminos: inicio de frase, dias, meses, titulos.
    "The", "This", "That", "What", "How", "When", "We", "Our", "They", "You", "It", "If", "And", "For",
    "El", "La", "Los", "Las", "Un", "Una", "En", "De", "Del", "Con", "Para", "Por", "Que", "Qué", "Cómo",
    "Cuál", "Nosotros", "Ellos", "Yo", "Hoy", "Si", "No", "Es", "Son", "Hay", "Pero", "Como", "Cuando",
    "Contexto", "Objetivo", "Resumen", "Datos", "Preguntas", "Mensajes", "Objeciones", "Riesgos", "Brief",
    "Lunes", "Martes", "Enero", "Febrero", "Diciembre", "Precio", "Plazo", "Cliente", "Respuesta",
}


def glossary_from(*texts: str, max_chars: int = 180) -> str:
    """Terminos para darle a Whisper como pista (nombres, siglas, productos).

    Medido: con "Glosario: PCI DSS, AWS, API Gateway, Aurora..." la frase
    "¿Que experiencia tienen con PCI y con el API Gateway de AWS?" pasa de
    "Peseí ... apigate Huawei de Auedo Lese" a bien escrita; error en espanol
    26% -> 12% (base) y 18% -> 3% (small), sin empeorar el ingles."""
    counts: Counter = Counter()
    for text in texts:
        for sentence in re.split(r"(?<=[.!?:])\s+|\n+", text or ""):
            sentence = sentence.lstrip("#-*> 0123456789.")  # markdown: "## Titulo", "- dato"
            for i, m in enumerate(_TERM.finditer(sentence)):
                term = m.group(0)
                if term in _COMMON or (i == 0 and m.start() == 0 and not any(c.isupper() for c in term[1:])):
                    continue  # palabra comun con mayuscula por empezar la frase
                counts[term] += 1
    out, used = [], len("Glosario: ")
    for term, _ in counts.most_common():
        if used + len(term) + 2 > max_chars:
            break
        out.append(term)
        used += len(term) + 2
    return ("Glosario: " + ", ".join(out) + ".") if out else ""


class _LiveTrack:
    """Una pista: cola → 16 kHz → bloques de 30 ms → segmentador → frases."""

    def __init__(self, speaker: str, on_utterance: Callable[[str, Utterance], None],
                 clock: Callable[[], float]) -> None:
        self.speaker = speaker
        self.clock = clock
        self._on_utterance = on_utterance
        self._seg = UtteranceSegmenter(SR, EnergyVAD(), self._event)
        self._q: queue.Queue = queue.Queue(maxsize=2000)
        self._carry = np.zeros(0, np.float32)
        self._pending = np.zeros(0, np.float32)
        self.fed = 0
        self._thread = threading.Thread(target=self._run, name=f"speak-live-{speaker}", daemon=True)
        self._thread.start()

    def push(self, audio: np.ndarray, rate: int, t: float | None = None) -> None:
        # Llega desde el callback de audio: solo encolar, con la hora de
        # llegada (`t`: fin del bloque en segundos de llamada).
        try:
            self._q.put_nowait((audio, rate, self.clock() if t is None else t))
        except queue.Full:
            pass

    def close(self, timeout: float | None = None) -> None:
        self._q.put(None)
        self._thread.join(timeout)

    def open_since(self) -> float | None:
        """Inicio de la frase que se esta diciendo ahora (VAD), o None."""
        seg = self._seg
        return seg._utt_start / SR if seg._buf_len else None

    def _event(self, ev) -> None:
        if isinstance(ev, Utterance):
            self._on_utterance(self.speaker, ev)

    def _feed(self, x: np.ndarray) -> None:
        self._pending = np.concatenate([self._pending, x]) if self._pending.size else x
        n = len(self._pending) // _BLOCK * _BLOCK
        for i in range(0, n, _BLOCK):
            self._seg.feed(self._pending[i:i + _BLOCK])
        self._pending = self._pending[n:]
        self.fed += n

    def _pad_to(self, t: float, incoming: int) -> None:
        """Rellena con silencio hasta que lo recibido cuadre con `t`."""
        missing = int(t * SR) - incoming - self.fed - len(self._pending)
        if missing > SR // 10:
            self._feed(np.zeros(missing, np.float32))

    def _run(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=0.1)
            except queue.Empty:
                item = ()
            if item is None:
                self._seg.flush()
                return
            try:
                if item:
                    audio, rate, t = item
                    x, self._carry = to_16k(audio, rate, self._carry)
                    self._pad_to(t, len(x))
                    self._feed(x)
                else:
                    # Cola vacia: ahora si, la hora actual es la buena.
                    self._pad_to(self.clock(), 0)
            except Exception:
                log.exception("fallo procesando audio en vivo (%s)", self.speaker)


class LiveTranscriber:
    """Un solo hilo de Whisper para las dos pistas, con prioridad y lotes.

    Medido en una laptop de 4 nucleos con la CPU ocupada (como en una llamada
    de Teams): Whisper cuesta casi lo mismo por llamada sea cual sea el largo
    (1 s de silencio: 1,5-3 s), porque el codificador siempre procesa una
    ventana de 30 s. Con dos transcriptores sueltos, frase a frase, el atraso
    crecia sin techo (106 s en una llamada de 90 s). Por eso:

    - **Prioridad**: primero "Ellos" (el copiloto depende de eso); "Yo" espera.
    - **Lotes**: las frases en cola del mismo hablante que forman un turno
      (huecos de hasta `join_gap_s`) van en UNA llamada, hasta `max_batch_s`.
      6 frases (27 s de audio): 12 s por separado, 3 s juntas.
    - **Idioma fijo por hablante** (si el STT no trae uno): se detecta en las
      primeras frases y se fija; cada `recheck_every` frases se vuelve a
      mirar por si la llamada cambio de idioma. Medido con Whisper base:
      detectar en cada frase es 2x mas lento y en frases cortas se equivoca
      ("Quanto questa..."); un idioma fijo equivocado traduce en vez de
      transcribir.
    """

    def __init__(self, stt: SpeechToText, on_text: Callable[[str, TranscriptEvent], None],
                 on_error: Callable[[str], None] = lambda m: None, priority: tuple[str, ...] = (THEM, ME),
                 max_batch_s: float = 24.0, join_gap_s: float = 2.5, recheck_every: int = 10,
                 glossary: str = "") -> None:
        self.stt = stt
        self.on_text = on_text
        self.on_error = on_error
        self.priority = priority
        self.max_batch_s = max_batch_s
        self.join_gap_s = join_gap_s
        self._qs: dict[str, list[tuple[np.ndarray, float, float]]] = {w: [] for w in priority}
        self._inflight: dict[str, int] = {w: 0 for w in priority}
        self._ctx: dict[str, str] = {w: "" for w in priority}
        self.recheck_every = recheck_every
        self.glossary = glossary  # pista fija para Whisper (terminos del brief y los documentos)
        self.language: dict[str, str | None] = {w: None for w in priority}  # fijado por hablante
        self._votes: dict[str, list[str]] = {w: [] for w in priority}
        self._since_check: dict[str, int] = {w: 0 for w in priority}
        self._cv = threading.Condition()
        self._closed = False
        self.calls = 0
        self._thread = threading.Thread(target=self._run, name="speak-live-stt", daemon=True)
        self._thread.start()

    def submit(self, who: str, audio: np.ndarray, start: float, end: float) -> None:
        with self._cv:
            self._qs[who].append((audio, start, end))
            self._cv.notify()

    def pending(self, who: str) -> int:
        """Frases de `who` en cola o transcribiendose ahora mismo."""
        with self._cv:
            return len(self._qs[who]) + self._inflight[who]

    def close(self, discard: bool = False) -> None:
        with self._cv:
            if discard:
                for q in self._qs.values():
                    q.clear()
            self._closed = True
            self._cv.notify()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _take(self) -> tuple[str, list] | None:
        with self._cv:
            while not self._closed and not any(self._qs.values()):
                self._cv.wait()
            for who in self.priority:
                q = self._qs[who]
                if not q:
                    continue
                batch = [q.pop(0)]
                total = batch[0][2] - batch[0][1]
                while q and q[0][1] - batch[-1][2] <= self.join_gap_s \
                        and total + (q[0][2] - q[0][1]) <= self.max_batch_s:
                    item = q.pop(0)
                    total += item[2] - item[1]
                    batch.append(item)
                self._inflight[who] = len(batch)
                return who, batch
            return None  # cerrado y vacio

    def _language_for(self, who: str, duration: float) -> str | None:
        """Idioma con el que transcribir esta frase; None = que Whisper lo detecte."""
        fixed = getattr(self.stt, "language", None)
        if fixed:
            return fixed  # lo fijo el usuario
        if getattr(self.stt, "detects_language_per_phrase", False):
            return None  # Deepgram "multi": cada frase en su idioma, sin fijar
        mine = self.language[who]
        other = next((lang for w, lang in self.language.items() if w != who and lang), None)
        if mine:
            self._since_check[who] += 1
            if self._since_check[who] >= self.recheck_every and duration >= 2.0:
                self._since_check[who] = 0
                return None  # revisar de vez en cuando (y solo con frases largas)
            return mine
        if duration < 1.5 and other:
            return other  # frase corta: detectar aqui falla; lo mas probable es el del otro
        return None

    def _learn_language(self, who: str, found: str | None, prob: float, duration: float) -> None:
        if not found or prob < 0.5 or duration < 1.0:
            return
        votes = self._votes[who]
        votes.append(found)
        del votes[:-3]
        current = self.language[who]
        if current is None:
            # Se fija con dos frases que coinciden, o una larga y muy segura.
            if votes.count(found) >= 2 or (prob >= 0.9 and duration >= 2.0):
                self.language[who] = found
                log.info("en vivo %s: idioma %s (%.0f%%)", who, found, prob * 100)
        elif found != current and votes[-2:] == [found, found] and prob >= 0.7:
            self.language[who] = found  # la llamada cambio de idioma
            log.info("en vivo %s: cambio de idioma a %s", who, found)

    def _run(self) -> None:
        gap = np.zeros(SR * 3 // 10, np.float32)
        while True:
            taken = self._take()
            if taken is None:
                return
            who, batch = taken
            parts = []
            for audio, _, _ in batch:
                parts += [audio, gap]
            t0 = time.time()
            try:
                audio = np.concatenate(parts[:-1])
                lang = self._language_for(who, len(audio) / SR)
                prompt = f"{self.glossary} {self._ctx[who][-200:]}".strip()
                text, found, prob = self.stt.transcribe_lang(audio, SR, prompt, lang)
                if lang is None or lang != found:
                    self._learn_language(who, found, prob, len(audio) / SR)
                self.calls += 1
                if text:
                    self._ctx[who] = (self._ctx[who] + " " + text).strip()
                    self.on_text(who, TranscriptEvent(text, batch[0][1], batch[-1][2], time.time() - t0))
            except Exception as exc:
                log.exception("fallo la transcripcion en vivo")
                self.on_error(f"error transcribiendo: {exc}")
            finally:
                with self._cv:
                    self._inflight[who] = 0


class LiveNotes:
    """Transcripcion en vivo de dos pistas + borrador de notas periodico.

    Callbacks (desde hilos propios; la UI los pasa por Signals):
    - `on_transcript(Transcript)`: cada vez que entra una frase nueva.
    - `on_notes(str)`: el borrador de notas, en streaming.
    - `on_status(str)`: avisos y errores.
    """

    def __init__(self, stt: SpeechToText, llm: LLMClient | None, mode: str = "llamada",
                 language: str = "Spanish", refresh_s: float = 60.0, min_new_words: int = 25,
                 on_transcript: Callable[[Transcript], None] = lambda tr: None,
                 on_notes: Callable[[str], None] = lambda md: None,
                 on_status: Callable[[str], None] = lambda msg: None,
                 clock: Callable[[], float] | None = None, glossary: str = "") -> None:
        self.stt = stt
        self.glossary = glossary
        self.llm = llm
        self.mode = mode
        self.language = language
        self.refresh_s = refresh_s
        self.min_new_words = min_new_words
        self.on_transcript = on_transcript
        self.on_notes = on_notes
        self.on_status = on_status
        self.notes = ""
        self._t0 = 0.0
        self._clock = clock or (lambda: time.monotonic() - self._t0)
        self._segs: dict[str, list[Segment]] = {ME: [], THEM: []}
        self._lock = threading.Lock()
        self._words = 0
        self._words_at_refresh = 0
        self._last_refresh = 0.0
        self._refresh_now = threading.Event()
        self._stopped = threading.Event()
        self._cancel = threading.Event()
        self._tracks: dict[str, _LiveTrack] = {}
        self._stt_worker: LiveTranscriber | None = None
        # Cuando hablo cada uno segun el VAD (no Whisper): el copiloto sabe al
        # instante que empezaste a responder, aunque tu texto llegue despues.
        self._spoke: dict[str, list[tuple[float, float]]] = {ME: [], THEM: []}
        self._notes_thread: threading.Thread | None = None

    # --- ciclo de vida --------------------------------------------------------

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._last_refresh = time.monotonic()
        self._stt_worker = LiveTranscriber(self.stt, self._on_text, self.on_status, glossary=self.glossary)
        for who in (ME, THEM):
            self._tracks[who] = _LiveTrack(who, self._on_utterance, self._clock)
        if self.llm is not None and self.refresh_s > 0:
            self._notes_thread = threading.Thread(target=self._notes_loop, name="speak-live-notes",
                                                  daemon=True)
            self._notes_thread.start()
        # Cargar Whisper ya, no con la primera frase.
        threading.Thread(target=self._warmup, name="speak-live-warmup", daemon=True).start()

    def _warmup(self) -> None:
        try:
            self.stt.warmup()
        except Exception as exc:
            self.on_status(f"modelo de voz: {exc}")

    def stop(self, wait: bool = False) -> Transcript:
        """Cierra las pistas. `wait=False` (la UI) descarta lo que falte por
        transcribir; `wait=True` (pruebas, consola) lo termina."""
        self._stopped.set()
        self._cancel.set()
        for track in self._tracks.values():
            track.close(timeout=2)
        if self._stt_worker is not None:
            self._stt_worker.close(discard=not wait)
            if wait:
                self._stt_worker.join()
        return self.snapshot()

    # --- entrada --------------------------------------------------------------

    def push(self, speaker: str, audio: np.ndarray, rate: int, t: float | None = None) -> None:
        """`speaker`: "me" o "them" (asi los nombra DualRecorder). `t`: fin del
        bloque en segundos de llamada; si no se da, la hora de llegada."""
        track = self._tracks.get(ME if speaker == "me" else THEM)
        if track is not None:
            track.push(audio, rate, t)

    def _on_utterance(self, who: str, utt: Utterance) -> None:
        with self._lock:
            self._spoke[who].append((utt.start, utt.end))
            del self._spoke[who][:-50]
        self._stt_worker.submit(who, utt.audio, utt.start, utt.end)

    def speech(self, speaker: str) -> list[tuple[float, float]]:
        """Cuando hablo `speaker` segun el VAD: [(inicio, fin)] de sus ultimas
        frases, y la que esta diciendo ahora como (inicio, ahora). Llega al
        instante, sin esperar a Whisper."""
        with self._lock:
            out = list(self._spoke[speaker])
        track = self._tracks.get(speaker)
        since = track.open_since() if track else None
        if since is not None:
            out.append((since, self._clock()))
        return out

    def _on_text(self, who: str, ev: TranscriptEvent) -> None:
        # Atraso = cuanto despues de que termino la frase aparece su texto.
        lag = self._clock() - ev.end
        log.info("en vivo %s: %.1fs de audio en %.1fs, atraso %.1fs, en cola %d",
                 who, ev.end - ev.start, ev.latency_s, lag, self.pending(who))
        if lag > 15 and time.monotonic() - getattr(self, "_lag_warned", 0) > 60:
            self._lag_warned = time.monotonic()
            if getattr(self.stt, "name", "") == "deepgram":
                hint = "Deepgram tardo en responder (red lenta o caida un momento); se recupera solo"
            else:
                hint = "prueba STT_LIVE_MODEL=tiny en speak/.env"
            self.on_status(f"la transcripcion en vivo va {lag:.0f} s atrasada: {hint}")
        with self._lock:
            self._segs[who].append(Segment(ev.start, ev.end, ev.text, who))
            self._words += len(ev.text.split())
        self.on_transcript(self.snapshot())

    # --- salida ---------------------------------------------------------------

    def now(self) -> float:
        """Segundos desde que empezo la llamada (el mismo reloj de los segmentos)."""
        return self._clock()

    def pending(self, speaker: str = THEM) -> int:
        """Frases de `speaker` esperando a Whisper."""
        return self._stt_worker.pending(speaker) if self._stt_worker else 0

    def snapshot(self) -> Transcript:
        with self._lock:
            me, them = list(self._segs[ME]), list(self._segs[THEM])
        me = dedupe_echo(me, them)
        return Transcript(sorted(me + them, key=lambda s: (s.start, s.speaker)), source="en vivo")

    def refresh_now(self) -> None:
        self._refresh_now.set()

    def _notes_loop(self) -> None:
        while not self._stopped.is_set():
            forced = self._refresh_now.wait(timeout=1.0)
            if self._stopped.is_set():
                return
            new_words = self._words - self._words_at_refresh
            due = time.monotonic() - self._last_refresh >= self.refresh_s
            if not (forced and self._words) and not (due and new_words >= self.min_new_words):
                continue
            self._refresh_now.clear()
            self._words_at_refresh = self._words
            self._last_refresh = time.monotonic()
            self._write_notes()

    def _write_notes(self) -> None:
        tr = self.snapshot()
        if not tr.segments:
            return
        system, user = live_notes_prompt(tr, self.mode, self.language)
        acc = ""
        try:
            for chunk in self.llm.stream(system, user, self._cancel):
                acc += chunk
                self.on_notes(acc)
        except Exception as exc:
            log.exception("notas en vivo")
            self.on_status(f"notas en vivo: {exc}")
            return
        if acc.strip() and not self._cancel.is_set():
            self.notes = acc.strip()
