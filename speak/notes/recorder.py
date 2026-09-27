"""Grabadora de dos pistas para Notas de llamada.

- `me.wav`: el microfono (16 kHz mono) → "Yo".
- `them.wav`: el audio del sistema por loopback WASAPI (lo que suena en tus
  audifonos: Zoom, Teams, Meet) → "Ellos".

Separar pistas resuelve "quien es quien" sin adivinar voces. Con parlantes en
vez de audifonos, el microfono tambien capta al otro; `pipeline.dedupe_echo`
limpia ese eco despues, pero con audifonos queda perfecto.

Las dos pistas se alinean con el reloj real, porque ninguna de las dos
entrega muestras de forma continua:

- el loopback WASAPI NO entrega nada mientras no suena nada;
- el microfono pierde bloques cuando algo retiene el interprete (medido: al
  iniciar PyAudio despues del microfono se perdian ~1,6 s, y la voz quedaba
  1,6 s antes en `me.wav` que en `them.wav`).

Por eso cada pista se rellena con silencio segun el reloj, el loopback se
prepara ANTES de arrancar el reloj, y al detener las dos quedan igual de
largas.

Otras dos cosas medidas en esta maquina:

- Muchos microfonos rechazan 16 kHz por WASAPI: se abren a su frecuencia
  nativa y se remuestrean (`audio_capture.open_input_16k`).
- El loopback llega DESPUES del volumen de Windows: con el volumen bajo, una
  voz que en el archivo pica 0,92 llego a 0,013 (-37 dB). Para `on_audio`
  (Notas en vivo) la pista "Ellos" pasa por un control automatico de
  ganancia; si no, el detector de voz no la oye y el copiloto nunca salta.
  `them.wav` se guarda tal cual.

`on_audio(pista, muestras, rate)`, si se pasa, recibe una copia de cada
bloque ("me" float32 a 16 kHz; "them" float32 mono a la frecuencia del
dispositivo, ya con ganancia) para Notas en vivo. Se llama desde el hilo de
audio: tiene que volver enseguida.

`info` dice que dispositivos se abrieron (tambien va al log).

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
        self.padded = 0  # frames de silencio agregados por el reloj
        self._lock = threading.Lock()
        self._w = wave.open(str(path), "wb")
        self._w.setnchannels(channels)
        self._w.setsampwidth(2)
        self._w.setframerate(rate)

    def write(self, pcm16: bytes) -> None:
        with self._lock:
            self._w.writeframes(pcm16)
            self.frames += len(pcm16) // (2 * self.channels)

    def pad_to(self, frames: int) -> int:
        with self._lock:
            missing = frames - self.frames
            if missing > 0:
                self._w.writeframes(b"\x00" * (missing * 2 * self.channels))
                self.frames += missing
                self.padded += missing
                return missing
            return 0

    def fill_gap(self, elapsed_s: float, incoming: int, tolerance_s: float = 0.1) -> int:
        """Si la pista va atrasada respecto del reloj (menos lo que esta por
        escribirse) en mas de `tolerance_s`, rellena con silencio."""
        expected = int(elapsed_s * self.rate) - incoming
        if expected - self.frames > int(self.rate * tolerance_s):
            return self.pad_to(expected)
        return 0

    def close(self) -> None:
        with self._lock:
            self._w.close()


class AutoGain:
    """Ganancia automatica lenta para la pista "Ellos" en vivo.

    Sigue la envolvente de pico (sube al instante, baja con `release_s`) y
    lleva ese pico a `target`, con ganancia entre 1 y `max_gain`. No sube el
    silencio digital (el loopback entrega ceros exactos) y no baja lo que ya
    suena fuerte."""

    # 100x = +40 dB: medido, con el volumen de Windows bajo el loopback llego
    # 37 dB por debajo del original. El loopback no tiene ruido de fondo
    # (silencio = ceros exactos), asi que subir tanto no levanta soplido.
    def __init__(self, target: float = 0.3, max_gain: float = 100.0, release_s: float = 4.0,
                 floor: float = 2e-4) -> None:
        self.target, self.max_gain, self.release_s, self.floor = target, max_gain, release_s, floor
        self.envelope = 0.0

    @property
    def gain(self) -> float:
        if self.envelope <= self.floor:
            return 1.0
        return float(min(self.max_gain, max(1.0, self.target / self.envelope)))

    def __call__(self, x: np.ndarray, rate: int) -> np.ndarray:
        if x.size:
            peak = float(np.abs(x).max())
            if peak >= self.envelope:
                self.envelope = peak
            else:
                decay = 0.5 ** (len(x) / rate / self.release_s)
                self.envelope = max(peak, self.envelope * decay)
        return np.clip(x * self.gain, -1.0, 1.0).astype(np.float32)


def pick_loopback(loopbacks: list[dict], default_output: str, want: str = "") -> dict | None:
    """Elige el dispositivo de loopback. `want` (parte del nombre, sin
    distinguir mayusculas) manda; si no, el de la salida por defecto. Si
    `want` no coincide con ninguno, tambien cae a la salida por defecto."""
    want = (want or "").strip().lower()
    if want:
        for d in loopbacks:
            if want in d["name"].lower():
                return d
    for d in loopbacks:
        if default_output and default_output in d["name"]:
            return d
    return None


def list_outputs() -> tuple[str, list[str]]:
    """(salida por defecto, nombres de los loopback disponibles)."""
    import pyaudiowpatch as pyaudio

    pa = pyaudio.PyAudio()
    try:
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])["name"]
        names = [d["name"].replace(" [Loopback]", "") for d in pa.get_loopback_device_info_generator()]
        return default, names
    finally:
        pa.terminate()


class DualRecorder:
    def __init__(self, folder: Path, mic_device=None, capture_system: bool = True,
                 on_audio=None, loopback_device: str | None = None) -> None:
        self.folder = Path(folder)
        self.on_audio = on_audio
        self.mic_device = mic_device
        self.capture_system = capture_system
        if loopback_device is None:
            # La UI no lo pasa: se lee de speak/.env (LOOPBACK_DEVICE).
            try:
                from ..config import Config

                loopback_device = Config.load().LOOPBACK_DEVICE
            except Exception:
                loopback_device = ""
        self.loopback_device = loopback_device
        self._mic_stream = None
        self._pa = None
        self._lb_stream = None
        self._mic: _WavSink | None = None
        self._them: _WavSink | None = None
        self._t0 = 0.0
        self.levels = {"me": 0.0, "them": 0.0}
        self.warnings: list[str] = []
        self.info: dict = {}
        self.overflows = 0
        self.gain = AutoGain()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0 if self._t0 else 0.0

    def start(self) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        # Primero se prepara todo lo lento (PyAudio tarda ~1 s en iniciar) y
        # recien despues arranca el reloj y los dos streams, juntos.
        if self.capture_system:
            try:
                self._open_loopback()
            except Exception as exc:
                self.warnings.append(f"sin audio del sistema (solo tu microfono): {exc}")
                log.warning("loopback no disponible: %s", exc)
                self._close_loopback()
        try:
            self._open_mic()
        except Exception:
            self._close_loopback()
            raise
        self._t0 = time.monotonic()
        try:
            self._mic_stream.start()
        except Exception as exc:
            self._close_loopback()
            raise RecorderError(f"no pude abrir el microfono: {exc}") from exc
        if self._lb_stream is not None:
            try:
                self._lb_stream.start_stream()
            except Exception as exc:
                self.warnings.append(f"sin audio del sistema (solo tu microfono): {exc}")
                log.warning("loopback no arranco: %s", exc)
                self._close_loopback()
        log.info("grabando: %s", self.info)

    # --- microfono ---

    def _open_mic(self) -> None:
        from ..audio_capture import AudioError, open_input_16k

        self._mic = _WavSink(self.folder / "me.wav", 16000, 1)

        def on_block(x: np.ndarray, status) -> None:
            if status and getattr(status, "input_overflow", False):
                self.overflows += 1
            sink = self._mic
            sink.fill_gap(time.monotonic() - self._t0, len(x))
            if x.size:
                self.levels["me"] = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
            sink.write(np.clip(x * 32767, -32768, 32767).astype("<i2").tobytes())
            if self.on_audio:
                self.on_audio("me", x.copy(), 16000)

        try:
            self._mic_stream, mic_info = open_input_16k(self.mic_device, on_block, block_ms=100)
        except AudioError as exc:
            raise RecorderError(str(exc)) from exc
        except Exception as exc:
            raise RecorderError(f"no pude abrir el microfono: {exc}") from exc
        self.info["mic"] = mic_info

    # --- loopback ---

    def _open_loopback(self) -> None:
        import pyaudiowpatch as pyaudio

        pa = pyaudio.PyAudio()
        self._pa = pa
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        except OSError as exc:
            raise RecorderError("WASAPI no disponible") from exc
        default = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        loopbacks = list(pa.get_loopback_device_info_generator())
        dev = pick_loopback(loopbacks, default["name"], self.loopback_device)
        if dev is None:
            raise RecorderError(f"no encontre el loopback de {default['name']!r}")
        if self.loopback_device and self.loopback_device.lower() not in dev["name"].lower():
            self.warnings.append(f"LOOPBACK_DEVICE={self.loopback_device!r} no existe; uso {dev['name']}")
        rate = int(dev["defaultSampleRate"])
        channels = max(1, int(dev["maxInputChannels"]))
        self._them = _WavSink(self.folder / "them.wav", rate, channels)
        self.info["them"] = {"name": dev["name"].replace(" [Loopback]", ""), "rate": rate,
                             "channels": channels, "default_output": default["name"]}

        def cb(in_data, frame_count, time_info, status):
            sink = self._them
            sink.fill_gap(time.monotonic() - self._t0, frame_count)
            sink.write(in_data)
            arr = np.frombuffer(in_data, dtype="<i2")
            if arr.size:
                mono = arr.reshape(-1, channels).mean(axis=1).astype(np.float32) / 32768.0
                boosted = self.gain(mono, rate)
                # El vumetro muestra lo que oye el detector de voz (con ganancia).
                self.levels["them"] = float(np.sqrt(np.mean(boosted.astype(np.float64) ** 2)))
                if self.on_audio:
                    self.on_audio("them", boosted, rate)
            return (None, pyaudio.paContinue)

        self._lb_stream = pa.open(format=pyaudio.paInt16, channels=channels, rate=rate,
                                  input=True, input_device_index=dev["index"],
                                  frames_per_buffer=1024, stream_callback=cb, start=False)

    def _close_loopback(self) -> None:
        if self._lb_stream is not None:
            try:
                if self._lb_stream.is_active():
                    self._lb_stream.stop_stream()
                self._lb_stream.close()
            except Exception as exc:
                log.warning("cerrando loopback: %s", exc)
            self._lb_stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    # --- detener ---

    def stop(self) -> Path:
        duration = self.elapsed
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception as exc:
                log.warning("cerrando microfono: %s", exc)
            self._mic_stream = None
        self._close_loopback()
        # Las dos pistas, igual de largas que la grabacion.
        for sink in (self._mic, self._them):
            if sink is not None:
                sink.pad_to(int(duration * sink.rate))
                sink.close()
        if self._mic is not None:
            log.info("grabacion: %.1fs; microfono: %.1fs rellenados con silencio, %d desbordes; "
                     "ganancia final de Ellos x%.1f", duration, self._mic.padded / 16000,
                     self.overflows, self.gain.gain)
        self._t0 = 0.0
        return self.folder
