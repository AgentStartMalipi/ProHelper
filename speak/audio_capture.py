"""Captura continua del microfono, en chunks pequenos, sin bloquear la UI.

Tres piezas:

- `EnergyVAD`: decide voz/silencio por chunk con un piso de ruido adaptativo.
  Energia pura y no un modelo: corre en microsegundos y, para una sola voz
  cercana al micro con audifonos, basta. Si hiciera falta, se cambia por
  Silero sin tocar el resto.
- `UtteranceSegmenter`: agrupa chunks de voz en "frases" (se cortan en pausas
  cortas, ~350 ms) y emite eventos. Las frases van al transcriptor; los
  eventos de silencio van al detector de turnos, que es quien decide si la
  pausa es el final del turno o solo una pausa para respirar.
- `AudioCapture`: el stream de sounddevice. Su callback solo encola; un hilo
  aparte corre VAD + segmentador y llama a `on_event`.

El tiempo se mide en muestras, no en reloj de pared: es exacto y hace que el
segmentador sea deterministico en las pruebas.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)


class AudioError(RuntimeError):
    pass


# --- eventos -----------------------------------------------------------------


@dataclass
class SpeechStarted:
    t: float  # segundos desde que empezo la escucha


@dataclass
class Utterance:
    audio: np.ndarray  # float32 mono, SAMPLE_RATE
    start: float
    end: float


@dataclass
class SilenceTick:
    """Se emite en cada chunk de silencio mientras dura la pausa."""

    t: float
    silence_ms: int


@dataclass
class Level:
    """Nivel para el vumetro de la UI (se emite ~10 veces por segundo)."""

    rms: float
    speaking: bool


AudioEvent = SpeechStarted | Utterance | SilenceTick | Level


# --- VAD ---------------------------------------------------------------------


class EnergyVAD:
    """Voz si la energia supera `ratio` veces el piso de ruido (o el umbral
    fijo, si se configuro). El piso se aprende solo de los chunks de silencio,
    asi que no se "acostumbra" a la voz.

    `hangover_chunks`: tras la ultima voz, cuantos chunks mas se siguen
    considerando voz. Evita que las consonantes suaves corten la frase.
    """

    def __init__(
        self,
        threshold: float = 0.0,
        ratio: float = 3.0,
        min_floor: float = 0.002,
        hangover_chunks: int = 5,
    ) -> None:
        self.threshold = threshold
        self.ratio = ratio
        self.min_floor = min_floor
        self.floor = min_floor * 2
        self.hangover_chunks = hangover_chunks
        self._hang = 0

    def limit(self) -> float:
        if self.threshold > 0:
            return self.threshold
        return max(self.floor * self.ratio, self.min_floor * self.ratio)

    def is_speech(self, rms: float) -> bool:
        if rms > self.limit():
            self._hang = self.hangover_chunks
            return True
        # Silencio: el piso sigue lentamente al ruido ambiente.
        self.floor = max(self.min_floor, 0.95 * self.floor + 0.05 * rms)
        if self._hang > 0:
            self._hang -= 1
            return True
        return False


def rms_of(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))))


# --- segmentador -------------------------------------------------------------


class UtteranceSegmenter:
    def __init__(
        self,
        sample_rate: int,
        vad: EnergyVAD,
        on_event: Callable[[AudioEvent], None],
        gap_ms: int = 350,
        preroll_ms: int = 200,
        min_speech_ms: int = 250,
        max_utterance_s: float = 20.0,
    ) -> None:
        self.sr = sample_rate
        self.vad = vad
        self.on_event = on_event
        self.gap_ms = gap_ms
        self.preroll = int(sample_rate * preroll_ms / 1000)
        self.min_speech = int(sample_rate * min_speech_ms / 1000)
        self.max_len = int(sample_rate * max_utterance_s)
        self.reset()

    def reset(self) -> None:
        self.samples_seen = 0
        self._ring: list[np.ndarray] = []  # pre-roll de silencio
        self._ring_len = 0
        self._buf: list[np.ndarray] = []
        self._buf_len = 0
        self._speech_len = 0
        self._in_speech = False
        self._utt_start = 0
        self._silence_samples = 0
        self._level_acc = 0

    def feed(self, chunk: np.ndarray) -> None:
        n = len(chunk)
        rms = rms_of(chunk)
        speech = self.vad.is_speech(rms)
        t_end = (self.samples_seen + n) / self.sr

        self._level_acc += n
        if self._level_acc >= self.sr // 10:
            self._level_acc = 0
            self.on_event(Level(rms=rms, speaking=speech))

        if speech:
            if not self._in_speech and self._buf_len == 0:
                self._utt_start = self.samples_seen - self._ring_len
                self._buf = list(self._ring)
                self._buf_len = self._ring_len
                self.on_event(SpeechStarted(t=self.samples_seen / self.sr))
            self._in_speech = True
            self._silence_samples = 0
            self._buf.append(chunk)
            self._buf_len += n
            self._speech_len += n
            if self._buf_len >= self.max_len:
                self._flush()
        else:
            self._silence_samples += n
            if self._buf_len:
                # Dentro de una frase: el silencio corto se conserva (es parte
                # del habla); si pasa del gap, la frase se cierra.
                self._buf.append(chunk)
                self._buf_len += n
                if self._silence_samples * 1000 >= self.gap_ms * self.sr:
                    self._flush()
            self._in_speech = False
            self._push_ring(chunk)
            self.on_event(
                SilenceTick(t=t_end, silence_ms=int(self._silence_samples * 1000 / self.sr))
            )

        self.samples_seen += n

    def flush(self) -> None:
        """Cierra la frase en curso (al pausar/detener)."""
        if self._buf_len:
            self._flush()

    def _flush(self) -> None:
        if self._speech_len >= self.min_speech:
            audio = np.concatenate(self._buf).astype(np.float32, copy=False)
            start = self._utt_start / self.sr
            self.on_event(Utterance(audio=audio, start=start, end=start + len(audio) / self.sr))
        self._buf, self._buf_len, self._speech_len = [], 0, 0

    def _push_ring(self, chunk: np.ndarray) -> None:
        self._ring.append(chunk)
        self._ring_len += len(chunk)
        while self._ring and self._ring_len - len(self._ring[0]) >= self.preroll:
            self._ring_len -= len(self._ring.pop(0))


# --- stream ------------------------------------------------------------------

_FLUSH = np.zeros(0, dtype=np.float32)  # centinela: "cierra la frase ya"


class AudioCapture:
    """Microfono → VAD → segmentador → `on_event` (desde un hilo propio).

    `mute()` descarta el audio entrante sin cerrar el stream: se usa mientras
    el entrevistador (TTS) habla, para no transcribir su propia voz si no hay
    audifonos.
    """

    def __init__(
        self,
        on_event: Callable[[AudioEvent], None],
        sample_rate: int = 16000,
        chunk_ms: int = 30,
        vad_threshold: float = 0.0,
        device: int | str | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.blocksize = int(sample_rate * chunk_ms / 1000)
        self.device = device
        self.on_error = on_error or (lambda msg: log.error(msg))
        self.segmenter = UtteranceSegmenter(
            sample_rate, EnergyVAD(threshold=vad_threshold), on_event
        )
        self._q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=500)
        self._stream = None
        self._worker: threading.Thread | None = None
        self._muted = threading.Event()
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            try:
                import sounddevice as sd
            except Exception as exc:  # pragma: no cover - depende del sistema
                raise AudioError(f"no se pudo cargar sounddevice: {exc}") from exc
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=self.blocksize,
                    device=self.device,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as exc:
                self._stream = None
                raise AudioError(
                    "no pude abrir el microfono. Revisa que este conectado y que "
                    "Windows le de permiso a las apps de escritorio "
                    f"(Configuracion > Privacidad > Microfono). Detalle: {exc}"
                ) from exc
            self.segmenter.reset()
            self._worker = threading.Thread(target=self._run, name="speak-audio", daemon=True)
            self._worker.start()

    def stop(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as exc:  # el dispositivo pudo desaparecer
                    log.warning("error cerrando el stream: %s", exc)
            if self._worker is not None:
                self._q.put(None)
                self._worker.join(timeout=2)
                self._worker = None

    def flush_now(self) -> None:
        """Cierra la frase en curso desde el hilo de audio (sin carreras)."""
        self._q.put(_FLUSH)

    def mute(self, muted: bool) -> None:
        if muted:
            self._muted.set()
        else:
            self._muted.clear()

    def _callback(self, indata, frames, time_info, status) -> None:
        # Corre en el hilo de audio de PortAudio: nada de trabajo aqui.
        if status:
            log.debug("audio status: %s", status)
        if self._muted.is_set():
            return
        try:
            self._q.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass  # el consumidor va atrasado: se pierde un chunk, no se bloquea

    def _run(self) -> None:
        while True:
            chunk = self._q.get()
            if chunk is None:
                self.segmenter.flush()
                return
            if chunk is _FLUSH:
                self.segmenter.flush()
                continue
            try:
                self.segmenter.feed(chunk)
            except Exception as exc:  # no dejar morir el hilo en silencio
                log.exception("fallo procesando audio")
                self.on_error(f"error procesando audio: {exc}")


def list_input_devices() -> list[tuple[int, str]]:
    try:
        import sounddevice as sd

        return [
            (i, d["name"])
            for i, d in enumerate(sd.query_devices())
            if d.get("max_input_channels", 0) > 0
        ]
    except Exception:
        return []
