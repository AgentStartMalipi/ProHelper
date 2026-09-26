"""Grabadora de dos pistas para Notas de llamada.

- `me.wav`: el microfono (16 kHz mono) → "Yo".
- `them.wav`: el audio del sistema por loopback WASAPI (lo que suena en tus
  audifonos: Zoom, Teams, Meet) → "Ellos".

Separar pistas resuelve "quien es quien" sin adivinar voces. Con parlantes en
vez de audifonos, el microfono tambien capta al otro; `pipeline.dedupe_echo`
limpia ese eco despues, pero con audifonos queda perfecto.

Detalle de WASAPI: el loopback NO entrega muestras mientras no suena nada.
Si solo se escribiera lo recibido, la pista "Ellos" se encogeria y sus tiempos
dejarian de cuadrar con los tuyos. Por eso se rellena con silencio segun el
reloj real.

`on_audio(pista, muestras, rate)`, si se pasa, recibe una copia de cada
bloque ("me" float32 a 16 kHz; "them" float32 mono a la frecuencia del
dispositivo) para Notas en vivo. Se llama desde el hilo de audio: tiene que
volver enseguida.

Solo graba cuando se lo pides, y la UI exige confirmar el consentimiento de
los participantes antes de empezar.
"""

from __future__ import annotations

import logging
import threading
import time
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


class RecorderError(RuntimeError):
    pass


class _WavSink:
    def __init__(self, path: Path, rate: int, channels: int) -> None:
        self.rate = rate
        self.channels = channels
        self.frames = 0
        self._lock = threading.Lock()
        self._w = wave.open(str(path), "wb")
        self._w.setnchannels(channels)
        self._w.setsampwidth(2)
        self._w.setframerate(rate)

    def write(self, pcm16: bytes) -> None:
        with self._lock:
            self._w.writeframes(pcm16)
            self.frames += len(pcm16) // (2 * self.channels)

    def pad_to(self, frames: int) -> None:
        with self._lock:
            missing = frames - self.frames
            if missing > 0:
                self._w.writeframes(b"\x00" * (missing * 2 * self.channels))
                self.frames += missing

    def close(self) -> None:
        with self._lock:
            self._w.close()


class DualRecorder:
    def __init__(self, folder: Path, mic_device=None, capture_system: bool = True,
                 on_audio=None) -> None:
        self.folder = Path(folder)
        self.on_audio = on_audio
        self.mic_device = mic_device
        self.capture_system = capture_system
        self._mic_stream = None
        self._pa = None
        self._lb_stream = None
        self._mic: _WavSink | None = None
        self._them: _WavSink | None = None
        self._t0 = 0.0
        self.levels = {"me": 0.0, "them": 0.0}
        self.warnings: list[str] = []

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0 if self._t0 else 0.0

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._t0 = time.monotonic()
        self._start_mic()
        if self.capture_system:
            try:
                self._start_loopback()
            except Exception as exc:
                self.warnings.append(f"sin audio del sistema (solo tu microfono): {exc}")
                log.warning("loopback no disponible: %s", exc)

    def _start_mic(self) -> None:
        import sounddevice as sd

        self._mic = _WavSink(self.folder / "me.wav", 16000, 1)

        def cb(indata, frames, t, status):
            self.levels["me"] = float(np.sqrt(np.mean(indata.astype(np.float64) ** 2)))
            pcm = np.clip(indata[:, 0] * 32767, -32768, 32767).astype("<i2").tobytes()
            self._mic.write(pcm)
            if self.on_audio:
                self.on_audio("me", indata[:, 0].copy(), 16000)

        try:
            self._mic_stream = sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                                              blocksize=1600, device=self.mic_device, callback=cb)
            self._mic_stream.start()
        except Exception as exc:
            raise RecorderError(f"no pude abrir el microfono: {exc}") from exc

    def _start_loopback(self) -> None:
        import pyaudiowpatch as pyaudio

        pa = pyaudio.PyAudio()
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError as exc:
            pa.terminate()
            raise RecorderError("WASAPI no disponible") from exc
        speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not speakers.get("isLoopbackDevice"):
            for lb in pa.get_loopback_device_info_generator():
                if speakers["name"] in lb["name"]:
                    speakers = lb
                    break
            else:
                pa.terminate()
                raise RecorderError("no encontre el loopback de la salida de audio por defecto")
        rate = int(speakers["defaultSampleRate"])
        channels = max(1, int(speakers["maxInputChannels"]))
        self._them = _WavSink(self.folder / "them.wav", rate, channels)
        t0 = self._t0

        def cb(in_data, frame_count, time_info, status):
            sink = self._them
            # Relleno de silencio: lo que "deberia" llevar grabado segun el
            # reloj, menos este bloque, si falta mas de 100 ms.
            expected = int((time.monotonic() - t0) * rate) - frame_count
            if expected - sink.frames > rate // 10:
                sink.pad_to(expected)
            sink.write(in_data)
            arr = np.frombuffer(in_data, dtype="<i2")
            if arr.size:
                self.levels["them"] = float(np.sqrt(np.mean((arr / 32768.0) ** 2)))
                if self.on_audio:
                    mono = arr.reshape(-1, channels).mean(axis=1) / 32768.0
                    self.on_audio("them", mono.astype(np.float32), rate)
            return (None, pyaudio.paContinue)

        self._pa = pa
        self._lb_stream = pa.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                                  input=True, input_device_index=speakers["index"],
                                  frames_per_buffer=1024, stream_callback=cb)
        self._lb_stream.start_stream()

    def stop(self) -> Path:
        duration = self.elapsed
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception as exc:
                log.warning("cerrando microfono: %s", exc)
            self._mic_stream = None
        if self._lb_stream is not None:
            try:
                self._lb_stream.stop_stream()
                self._lb_stream.close()
            except Exception as exc:
                log.warning("cerrando loopback: %s", exc)
            self._lb_stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None
        if self._them is not None:
            self._them.pad_to(int(duration * self._them.rate))  # misma duracion que "Yo"
            self._them.close()
        if self._mic is not None:
            self._mic.close()
        self._t0 = 0.0
        return self.folder
