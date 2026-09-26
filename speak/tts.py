"""Voz del entrevistador con el sintetizador de Windows (System.Speech).

Por PowerShell y no con pyttsx3: cero dependencias, no pelea con el hilo de
Qt, y detener = matar el proceso. El texto viaja por stdin (UTF-8), asi que
comillas, tildes o saltos de linea no rompen nada.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import threading
from typing import Callable

log = logging.getLogger(__name__)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_SCRIPT = r"""
[Console]::InputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoiceByHints('NotSet', 'NotSet', 0, [Globalization.CultureInfo]'__CULTURE__') } catch {}
$s.Rate = __RATE__
$text = [Console]::In.ReadToEnd()
$s.Speak($text)
"""


class Speaker:
    def __init__(self, enabled: bool = True, rate: int = 0, language: str = "en") -> None:
        self.enabled = enabled
        self.rate = max(-10, min(10, rate))
        self.culture = "es-ES" if language.lower().startswith("es") else "en-US"
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def speaking(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def speak(self, text: str, on_done: Callable[[], None] | None = None) -> None:
        """No bloquea. `on_done` se llama al terminar o al ser detenido."""
        self.stop()
        if not self.enabled or not text.strip():
            if on_done:
                on_done()
            return
        script = _SCRIPT.replace("__RATE__", str(self.rate)).replace("__CULTURE__", self.culture)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
            )
            proc.stdin.write(text.encode("utf-8"))
            proc.stdin.close()
        except Exception as exc:
            log.warning("TTS no disponible: %s", exc)
            if on_done:
                on_done()
            return
        with self._lock:
            self._proc = proc

        def wait() -> None:
            proc.wait()
            if on_done:
                on_done()

        threading.Thread(target=wait, name="speak-tts", daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            proc.kill()
