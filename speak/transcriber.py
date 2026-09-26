"""Speech-to-text con backends intercambiables.

- `SpeechToText`: la interfaz. Dos metodos: `transcribe` (una frase en
  memoria, para el modo en vivo) y `transcribe_file` (un archivo completo,
  para Notas de llamada).
- `FasterWhisperSTT`: local, gratis, sin internet. Es el de serie: en una
  laptop sin GPU NVIDIA, `small` con int8 transcribe una frase de 5 s en ~1 s.
- `AssemblyAISTT`: API (solo archivos). Mejor diarizacion cuando en una pista
  hay varias voces, p. ej. un panel de entrevistadores.
- `IncrementalTranscriber`: hilo que recibe frases del segmentador y va
  emitiendo texto, sin bloquear ni la captura ni la UI.

Whisper puro (openai-whisper) no se incluye: faster-whisper es el mismo
modelo, ~4x mas rapido en CPU y con menos memoria. Para anadir otro backend
basta con implementar `SpeechToText` y registrarlo en `make_stt`.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)


class STTError(RuntimeError):
    pass


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str = ""  # lo llenan los backends con diarizacion


# Frases que Whisper "alucina" sobre silencio o ruido. Si una frase corta es
# exactamente una de estas, casi siempre es ruido y no habla real.
_HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching!", "thanks for watching.",
    "you", "bye.", "gracias.", "subtitulos realizados por la comunidad de amara.org",
    "¡gracias!", ".", "...",
}


def looks_like_hallucination(text: str, duration_s: float) -> bool:
    t = text.strip().lower()
    return not t or (duration_s < 2.5 and t in _HALLUCINATIONS)


def _split_on_gaps(seg, gap_s: float) -> list[Segment]:
    """Parte un segmento de faster-whisper (con .words) en los silencios."""
    words = getattr(seg, "words", None) or []
    if not words:
        return [Segment(seg.start, seg.end, seg.text.strip())]
    out: list[Segment] = []
    cur = [words[0]]
    for prev, w in zip(words, words[1:]):
        if w.start - prev.end > gap_s:
            out.append(Segment(cur[0].start, cur[-1].end, "".join(x.word for x in cur).strip()))
            cur = []
        cur.append(w)
    out.append(Segment(cur[0].start, cur[-1].end, "".join(x.word for x in cur).strip()))
    return [s for s in out if s.text]


class SpeechToText(ABC):
    name = "base"

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int, prompt: str = "") -> str:
        """Una frase corta en memoria → texto."""

    @abstractmethod
    def transcribe_file(self, path: Path) -> list[Segment]:
        """Un archivo completo → segmentos con tiempos."""

    def warmup(self) -> None:
        """Carga perezosa del modelo; la UI la llama en segundo plano."""


class FasterWhisperSTT(SpeechToText):
    name = "faster_whisper"

    def __init__(self, model: str = "small", device: str = "cpu",
                 compute_type: str = "int8", language: str = "en") -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language or None
        self._model = None
        self._lock = threading.Lock()

    def warmup(self) -> None:
        self._get()

    def _get(self):
        with self._lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise STTError("falta faster-whisper: pip install faster-whisper") from exc
                t0 = time.time()
                # La primera vez descarga el modelo (small ~ 480 MB) a la cache
                # de Hugging Face; despues carga en segundos.
                self._model = WhisperModel(
                    self.model_name, device=self.device, compute_type=self.compute_type
                )
                log.info("modelo %s cargado en %.1fs", self.model_name, time.time() - t0)
            return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int, prompt: str = "") -> str:
        if sample_rate != 16000:
            raise STTError("faster-whisper espera audio a 16 kHz")
        segments, _ = self._get().transcribe(
            audio,
            language=self.language,
            beam_size=1,  # en vivo pesa mas la latencia que el ultimo 1% de WER
            vad_filter=False,  # el segmentador ya corto la frase
            condition_on_previous_text=False,
            initial_prompt=prompt or None,  # continuidad con lo ya dicho
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return "" if looks_like_hallucination(text, len(audio) / sample_rate) else text

    def transcribe_file(self, path: Path, split_gap_s: float = 0.8) -> list[Segment]:
        # Con vad_filter, Whisper junta en un segmento trozos de habla separados
        # por silencios largos: en una pista donde el otro solo habla a ratos,
        # "Interesting." quedaba pegado a la pregunta de 20 s antes. Con tiempos
        # por palabra se parte el segmento en cada hueco > split_gap_s.
        segments, _ = self._get().transcribe(
            str(path), language=self.language, beam_size=5, vad_filter=True,
            word_timestamps=True,
        )
        out = []
        for s in segments:
            for sub in _split_on_gaps(s, split_gap_s):
                if not looks_like_hallucination(sub.text, sub.end - sub.start):
                    out.append(sub)
        return out


class AssemblyAISTT(SpeechToText):
    """REST de AssemblyAI con urllib (sin SDK). Solo archivos: subir →
    crear transcripcion con `speaker_labels` → sondear hasta que termine."""

    name = "assemblyai"
    BASE = "https://api.assemblyai.com/v2"

    def __init__(self, api_key: str, language: str = "en", speakers_expected: int | None = None):
        if not api_key:
            raise STTError("falta ASSEMBLYAI_API_KEY en speak/.env")
        self.api_key = api_key
        self.language = language
        self.speakers_expected = speakers_expected

    def transcribe(self, audio: np.ndarray, sample_rate: int, prompt: str = "") -> str:
        raise STTError("AssemblyAI se usa solo para archivos (Notas de llamada)")

    def _req(self, url: str, data: bytes | None = None, content_type: str = "application/json"):
        req = urllib.request.Request(url, data=data, headers={
            "authorization": self.api_key, "content-type": content_type,
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def transcribe_file(self, path: Path) -> list[Segment]:
        upload = self._req(f"{self.BASE}/upload", Path(path).read_bytes(),
                           "application/octet-stream")
        body: dict = {"audio_url": upload["upload_url"], "speaker_labels": True}
        if self.language:
            body["language_code"] = self.language
        else:
            body["language_detection"] = True
        if self.speakers_expected:
            body["speakers_expected"] = self.speakers_expected
        job = self._req(f"{self.BASE}/transcript", json.dumps(body).encode("utf-8"))
        while True:
            job = self._req(f"{self.BASE}/transcript/{job['id']}")
            if job["status"] == "completed":
                break
            if job["status"] == "error":
                raise STTError(f"AssemblyAI: {job.get('error')}")
            time.sleep(3)
        return [
            Segment(start=u["start"] / 1000, end=u["end"] / 1000, text=u["text"],
                    speaker=str(u.get("speaker", "")))
            for u in job.get("utterances") or []
        ]


def make_stt(cfg, for_files: bool = False) -> SpeechToText:
    """El modo en vivo siempre usa el local; los archivos pueden ir a la API."""
    if for_files and cfg.STT_PROVIDER == "assemblyai":
        return AssemblyAISTT(cfg.ASSEMBLYAI_API_KEY, cfg.STT_LANGUAGE)
    return FasterWhisperSTT(cfg.STT_MODEL, cfg.STT_DEVICE, cfg.STT_COMPUTE_TYPE,
                            cfg.STT_LANGUAGE)


# --- en vivo -----------------------------------------------------------------


@dataclass
class TranscriptEvent:
    text: str
    start: float
    end: float
    latency_s: float


class IncrementalTranscriber:
    """Cola de frases → texto, en un hilo. Pasa como `prompt` el final de lo
    ya transcrito: Whisper acierta mas nombres y terminos con contexto."""

    def __init__(self, stt: SpeechToText, sample_rate: int,
                 on_text: Callable[[TranscriptEvent], None],
                 on_error: Callable[[str], None] | None = None) -> None:
        self.stt = stt
        self.sample_rate = sample_rate
        self.on_text = on_text
        self.on_error = on_error or (lambda m: log.error(m))
        self._q: queue.Queue = queue.Queue()
        self._context = ""
        # Enviadas y aun sin texto, incluida la que se esta transcribiendo:
        # qsize() sola no la cuenta y el que espera "no queda nada" se adelanta.
        self._outstanding = 0
        self._count_lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="speak-stt", daemon=True)
        self._thread.start()

    def submit(self, audio: np.ndarray, start: float, end: float) -> None:
        with self._count_lock:
            self._outstanding += 1
        self._q.put((audio, start, end))

    def reset_context(self) -> None:
        self._context = ""

    def pending(self) -> int:
        return self._outstanding

    def close(self, discard: bool = False) -> None:
        """`discard`: tira las frases aun sin transcribir (al detener Notas en
        vivo no vale la pena gastar CPU en ellas: viene la pasada final)."""
        if discard:
            try:
                while True:
                    if self._q.get_nowait() is not None:
                        with self._count_lock:
                            self._outstanding -= 1
            except queue.Empty:
                pass
        self._q.put(None)

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            audio, start, end = item
            t0 = time.time()
            try:
                text = self.stt.transcribe(audio, self.sample_rate, self._context[-200:])
            except Exception as exc:
                log.exception("fallo la transcripcion")
                self.on_error(f"error transcribiendo: {exc}")
                text = ""
            try:
                if text:
                    self._context = (self._context + " " + text).strip()
                    self.on_text(TranscriptEvent(text, start, end, time.time() - t0))
            finally:
                with self._count_lock:
                    self._outstanding -= 1
