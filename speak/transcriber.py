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
import os
import queue
import re
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


class STTNetworkError(STTError):
    """No hubo red (DNS, conexion caida, timeout): vale la pena reintentar o
    caer a un respaldo local. Una llave mala o sin creditos NO es esto."""


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


_WORDS_RE = re.compile(r"[\wáéíóúñü']+", re.IGNORECASE)


def looks_like_noise(text: str, prompt: str, no_speech: float) -> bool:
    """Ruido que Whisper convirtio en texto. Medido con el micro de una webcam
    (voz baja): con la pista de contexto, una tos o el teclado salian como
    "Good morning. Good morning." (copia de lo ya dicho) con no_speech 0,43-0,85;
    la voz real no paso de 0,40. Se descarta si Whisper cree que no hay voz, o
    si lo duda y el texto solo repite la pista (contexto o glosario)."""
    if no_speech >= 0.6:
        return True
    if no_speech < 0.3 or not prompt:
        return False
    words = _WORDS_RE.findall(text.lower())
    seen = set(_WORDS_RE.findall(prompt.lower()))
    return bool(words) and sum(w in seen for w in words) / len(words) >= 0.9


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

    #: Idioma fijo; None = detectar. Los backends que no lo manejan, None.
    language: str | None = None

    def transcribe_lang(self, audio: np.ndarray, sample_rate: int, prompt: str = "",
                        language: str | None = None) -> tuple[str, str | None, float]:
        """Como `transcribe`, con el idioma elegido por quien llama (None =
        detectar) y devolviendo el idioma detectado y su probabilidad."""
        return self.transcribe(audio, sample_rate, prompt), None, 0.0


class FasterWhisperSTT(SpeechToText):
    name = "faster_whisper"

    def __init__(self, model: str = "small", device: str = "cpu",
                 compute_type: str = "int8", language: str = "en", cpu_threads: int = 0) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language or None
        # 0 = todos los nucleos. El default de CTranslate2 son 4: medido en una
        # laptop de 8 nucleos, 6 s de audio pasaban de 15 s a 38 s.
        self.cpu_threads = cpu_threads or os.cpu_count() or 4
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
                    self.model_name, device=self.device, compute_type=self.compute_type,
                    cpu_threads=self.cpu_threads,
                )
                log.info("modelo %s cargado en %.1fs", self.model_name, time.time() - t0)
            return self._model

    def transcribe(self, audio: np.ndarray, sample_rate: int, prompt: str = "") -> str:
        return self.transcribe_lang(audio, sample_rate, prompt, self.language)[0]

    def transcribe_lang(self, audio: np.ndarray, sample_rate: int, prompt: str = "",
                        language: str | None = None) -> tuple[str, str | None, float]:
        if sample_rate != 16000:
            raise STTError("faster-whisper espera audio a 16 kHz")
        duration = len(audio) / sample_rate
        segments, info = self._get().transcribe(
            audio,
            language=language,
            beam_size=1,  # en vivo pesa mas la latencia que el ultimo 1% de WER
            vad_filter=False,  # el segmentador ya corto la frase
            condition_on_previous_text=False,
            initial_prompt=prompt or None,  # continuidad con lo ya dicho
            # Lo que hacia que una frase de 1,4 s tardara 30 s: con ruido,
            # Whisper entra en bucle ("good morning, good morning...") hasta
            # 448 tokens, y si el resultado sale raro lo re-decodifica hasta 6
            # veces subiendo la temperatura. En vivo: una sola pasada, sin
            # marcas de tiempo, y un tope de tokens acorde a lo que dura la frase
            # (se habla a ~3-4 tokens/s).
            temperature=0.0,
            without_timestamps=True,
            max_new_tokens=int(duration * 8) + 16,
            no_repeat_ngram_size=4,
        )
        segments = list(segments)
        text = " ".join(s.text.strip() for s in segments).strip()
        no_speech = max((getattr(s, "no_speech_prob", 0.0) for s in segments), default=0.0)
        if looks_like_hallucination(text, duration) or looks_like_noise(text, prompt, no_speech):
            text = ""
        return text, getattr(info, "language", None), float(getattr(info, "language_probability", 0.0) or 0.0)

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


class DeepgramSTT(SpeechToText):
    """Deepgram Nova-3 por REST, frase a frase (en vivo) y archivos (notas).

    Frase a frase y no por websocket: el segmentador y el detector de turnos
    siguen igual, y solo cambia quien convierte la frase en texto. Una frase de
    2-3 s vuelve en ~0,3-0,6 s, contra 1,5-2 s de Whisper `small` en CPU.
    Una conexion HTTPS por hilo (Notas en vivo transcribe dos pistas a la vez)
    que se reutiliza: sin repetir el apreton TLS en cada frase.

    Idioma: "" o None → "multi" (espanol e ingles mezclados en la misma frase).
    """

    name = "deepgram"
    HOST = "api.deepgram.com"

    def __init__(self, api_key: str, model: str = "nova-3", language: str | None = None,
                 keyterms: list[str] | None = None, fallback_factory=None) -> None:
        if not api_key:
            raise STTError("falta DEEPGRAM_API_KEY en speak/.env (creala gratis en console.deepgram.com)")
        self.api_key = api_key
        self.model = model or "nova-3"
        self.language = language or None
        self.keyterms = [t.strip() for t in (keyterms or []) if t.strip()][:100]
        self._local = threading.local()
        # Si no hay red, la frase la transcribe Whisper local (se crea solo la
        # primera vez que hace falta). None = sin respaldo.
        self.fallback_factory = fallback_factory
        self._fallback: SpeechToText | None = None
        self._fallback_lock = threading.Lock()

    @property
    def detects_language_per_phrase(self) -> bool:
        """En "multi" Deepgram detecta el idioma en cada frase (y mezclas): el
        idioma no se fija por hablante. Fijarlo en "en" hacia que lo dicho en
        espanol saliera como ingles sin sentido."""
        return self.language is None

    def _conn(self):
        import http.client

        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = http.client.HTTPSConnection(self.HOST, timeout=30)
            self._local.conn = conn
        return conn

    # En vivo una frase vuelve en 0,3-2,5 s. Medido 2026-10-07: una peticion
    # colgada tardo 22 s y, con el timeout de 30 s, todo lo que venia detras
    # (y el copiloto) espero con ella. En vivo se corta antes y se reintenta
    # una vez con conexion nueva; si vuelve a fallar, esa frase va con Whisper.
    LIVE_TIMEOUT_S = 5.0
    LIVE_WAITS = (0.0, 0.3)
    # Archivos (la llamada entera al Detener): pueden ser 45 min de audio.
    FILE_TIMEOUT_S = 300.0

    def _request(self, method: str, path: str, body: bytes | None = None,
                 content_type: str = "audio/wav", timeout: float = 30.0,
                 waits: tuple[float, ...] = (0.0, 0.4, 1.2)) -> dict:
        headers = {"Authorization": f"Token {self.api_key}"}
        if body is not None:
            headers["Content-Type"] = content_type
        # Reintentos con espera: una conexion reutilizada puede estar cerrada, y
        # el DNS del Wi-Fi a veces falla un instante (medido 2026-09-30: un
        # "getaddrinfo failed" suelto en medio de una llamada que iba bien).
        for attempt, wait in enumerate(waits, 1):
            if wait:
                time.sleep(wait)
            conn = self._conn()
            conn.timeout = timeout  # para la proxima conexion
            if conn.sock is not None:
                conn.sock.settimeout(timeout)  # y para la que ya esta abierta
            try:
                conn.request(method, path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                break
            except (OSError, ConnectionError, TimeoutError) as exc:
                conn.close()
                self._local.conn = None
                if attempt == len(waits):
                    raise STTNetworkError(f"no pude conectar con Deepgram: {exc}") from exc
        if resp.status == 401:
            raise STTError("Deepgram rechazo la llave (401): revisa DEEPGRAM_API_KEY en speak/.env")
        if resp.status == 402:
            raise STTError("Deepgram: se acabaron los creditos (402)")
        if resp.status >= 400:
            raise STTError(f"Deepgram {resp.status}: {data[:300].decode('utf-8', 'replace')}")
        return json.loads(data.decode("utf-8"))

    def _query(self, language: str | None, **extra) -> str:
        from urllib.parse import urlencode

        params = [("model", self.model), ("language", language or "multi"),
                  ("smart_format", "true"), ("punctuate", "true"), *extra.items()]
        params += [("keyterm", t) for t in self.keyterms]
        return "/v1/listen?" + urlencode(params)

    def warmup(self) -> None:
        # Valida la llave al arrancar (y no a mitad de la primera respuesta).
        self._request("GET", "/v1/projects")

    def transcribe(self, audio: np.ndarray, sample_rate: int, prompt: str = "") -> str:
        return self.transcribe_lang(audio, sample_rate, prompt, self.language)[0]

    def transcribe_lang(self, audio: np.ndarray, sample_rate: int, prompt: str = "",
                        language: str | None = None) -> tuple[str, str | None, float]:
        body = _wav_bytes(audio, sample_rate)
        try:
            res = self._request("POST", self._query(language), body,
                                timeout=self.LIVE_TIMEOUT_S, waits=self.LIVE_WAITS)
        except STTNetworkError as exc:
            fb = self._get_fallback()
            if fb is None:
                raise
            log.warning("Deepgram sin red (%s): esta frase va con Whisper local", exc)
            return fb.transcribe_lang(audio, sample_rate, prompt, language)
        alt = res["results"]["channels"][0]["alternatives"][0]
        text = (alt.get("transcript") or "").strip()
        if looks_like_hallucination(text, len(audio) / sample_rate):
            text = ""
        langs = alt.get("languages") or []
        return text, (langs[0] if langs else language), float(alt.get("confidence") or 0.0)

    def _get_fallback(self) -> SpeechToText | None:
        if self.fallback_factory is None:
            return None
        with self._fallback_lock:
            if self._fallback is None:
                self._fallback = self.fallback_factory()
            return self._fallback

    def transcribe_file(self, path: Path) -> list[Segment]:
        path = Path(path)
        ctype = "audio/wav" if path.suffix.lower() == ".wav" else "application/octet-stream"
        res = self._request("POST", self._query(self.language, diarize="true", utterances="true"),
                            path.read_bytes(), ctype, timeout=self.FILE_TIMEOUT_S)
        utts = res.get("results", {}).get("utterances") or []
        speakers = {u.get("speaker") for u in utts}
        return [
            Segment(start=u["start"], end=u["end"], text=u["transcript"].strip(),
                    speaker=chr(ord("A") + int(u["speaker"])) if len(speakers) > 1 else "")
            for u in utts if u.get("transcript", "").strip()
        ]


def _wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    import io
    import wave

    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def make_stt(cfg, for_files: bool = False, model: str | None = None,
             language: str | None = None) -> SpeechToText:
    """El modo en vivo siempre usa el local; los archivos pueden ir a la API.
    `model` cambia el tamano (Notas en vivo usa STT_LIVE_MODEL, mas liviano).
    `language` reemplaza a STT_LANGUAGE ("" = detectar; Notas de llamada usa
    NOTES_STT_LANGUAGE)."""
    lang = cfg.STT_LANGUAGE if language is None else language
    if cfg.STT_PROVIDER == "deepgram":
        return DeepgramSTT(getattr(cfg, "DEEPGRAM_API_KEY", ""),
                           getattr(cfg, "DEEPGRAM_MODEL", "nova-3"), lang,
                           getattr(cfg, "DEEPGRAM_KEYTERMS", "").split(","),
                           fallback_factory=lambda: FasterWhisperSTT(
                               cfg.STT_LIVE_MODEL or "base", cfg.STT_DEVICE, cfg.STT_COMPUTE_TYPE,
                               lang or None, cfg.STT_THREADS))
    if for_files and cfg.STT_PROVIDER == "assemblyai":
        return AssemblyAISTT(cfg.ASSEMBLYAI_API_KEY, lang)
    return FasterWhisperSTT(model or cfg.STT_MODEL, cfg.STT_DEVICE, cfg.STT_COMPUTE_TYPE,
                            lang, cfg.STT_THREADS)


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
