"""Clientes de LLM con streaming y cancelacion.

Interfaz unica: `stream(system, prompt, cancel, images)` → iterador de trozos
de texto. La UI pinta cada trozo al llegar. `images` (rutas) es para los
diagramas que adjuntas al copiloto: viajan en base64 dentro del mensaje, como
en SCREEN, no como ruta para que Claude las abra con una herramienta.

- `ClaudeCLIClient` (de serie): `claude -p` con `--include-partial-messages`,
  que emite `text_delta` token a token. Reutiliza tu login de Claude Code,
  sin API key, igual que SCREEN. Arranque ~1-2 s por llamada.
- `AnthropicClient`: SDK oficial (`pip install anthropic`) con API_KEY. Menos
  latencia de arranque; se paga por token aparte de tu plan.
- `FakeLLM`: para pruebas, sin red ni costo.

Cancelar mata el subproceso o cierra el stream: "Regenerar" o un turno
reabierto no esperan a que termine la respuesta vieja.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LLMError(RuntimeError):
    pass


_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
          ".webp": "image/webp"}
_MAX_IMAGE_BYTES = 3_500_000  # la API rechaza imagenes de mas de ~5 MB en base64


def image_block(path: Path) -> dict:
    """Bloque de imagen para la API. Las muy pesadas (capturas 4K) se reducen
    con Qt (ya es dependencia de SPEAK) a JPEG de 2000 px de lado."""
    path = Path(path)
    data, media = path.read_bytes(), _MEDIA.get(path.suffix.lower(), "image/png")
    if len(data) > _MAX_IMAGE_BYTES:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        from PySide6.QtGui import QImage

        img = QImage(str(path))
        if img.isNull():
            raise LLMError(f"no pude abrir la imagen {path.name}")
        img = img.scaled(2000, 2000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        buf = QByteArray()
        io = QBuffer(buf)
        io.open(QIODevice.WriteOnly)
        img.save(io, "JPEG", 85)
        data, media = bytes(buf), "image/jpeg"
    return {"type": "image",
            "source": {"type": "base64", "media_type": media, "data": base64.b64encode(data).decode("ascii")}}


def user_message_json(text: str, images: list[Path]) -> str:
    """Mensaje para `claude -p --input-format stream-json` (una linea)."""
    content = [image_block(p) for p in images] + [{"type": "text", "text": text}]
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}})


class LLMClient(ABC):
    @abstractmethod
    def stream(self, system: str, prompt: str, cancel: threading.Event | None = None,
               images: list[Path] | None = None) -> Iterator[str]:
        ...

    def complete(self, system: str, prompt: str, images: list[Path] | None = None) -> str:
        return "".join(self.stream(system, prompt, images=images))


class ClaudeCLIClient(LLMClient):
    def __init__(self, model: str, effort: str = "low", timeout: float = 180.0) -> None:
        self.model = model
        self.effort = effort
        self.timeout = timeout

    # Windows corta la linea de comandos en 32.767 caracteres: un prompt de
    # sistema largo (una guia con un documento pegado) va por archivo.
    MAX_ARG_SYSTEM = 8000

    def _args(self, system: str, json_input: bool = False, system_file: str | None = None) -> list[str]:
        cli = shutil.which("claude")
        if not cli:
            raise LLMError("no encuentro `claude` en el PATH (instala Claude Code o usa "
                           "LLM_PROVIDER=anthropic)")
        system_args = ["--system-prompt-file", system_file] if system_file else ["--system-prompt", system]
        return [
            cli, "-p", "--verbose",
            "--output-format", "stream-json", "--include-partial-messages",
            "--model", self.model, "--effort", self.effort,
            # Sin herramientas, MCP ni settings: solo texto, y sin cargar el
            # harness completo (lo mismo que midio SCREEN: 15x mas barato).
            "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
            "--setting-sources", "", "--permission-mode", "dontAsk",
            "--no-session-persistence", *system_args,
        ] + (["--input-format", "stream-json"] if json_input else [])

    def stream(self, system, prompt, cancel=None, images=None):
        payload = user_message_json(prompt, images) + "\n" if images else prompt
        system_file = None
        if len(system) > self.MAX_ARG_SYSTEM:
            import tempfile

            fd, system_file = tempfile.mkstemp(prefix="speak-system-", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(system)
        try:
            yield from self._stream(system, payload, bool(images), system_file, cancel)
        finally:
            if system_file:
                try:
                    os.unlink(system_file)
                except OSError:
                    pass

    def _stream(self, system, payload, json_input, system_file, cancel):
        proc = subprocess.Popen(
            self._args(system, json_input=json_input, system_file=system_file), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            creationflags=_NO_WINDOW,
        )
        # stderr se vacia en otro hilo: si se llenara el buffer del pipe (unos
        # KB en Windows) el CLI se quedaria bloqueado escribiendo y aqui
        # esperariamos stdout para siempre.
        err_lines: list[str] = []
        drain = threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True)
        drain.start()
        timer = threading.Timer(self.timeout, proc.kill)
        timer.start()
        got_delta = False
        final_text = ""
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
            for line in proc.stdout:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    return
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("type")
                if kind == "stream_event":
                    inner = ev.get("event", {})
                    delta = inner.get("delta", {})
                    if inner.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                        got_delta = True
                        yield delta.get("text", "")
                elif kind == "assistant" and not got_delta:
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            final_text += block.get("text", "")
                elif kind == "result":
                    if ev.get("is_error"):
                        raise LLMError(ev.get("result") or "Claude devolvio un error")
            proc.wait(timeout=10)
            if not got_delta and final_text:
                yield final_text  # CLI viejo sin parciales: todo de una
            elif not got_delta and proc.returncode not in (0, None):
                drain.join(timeout=2)
                err = "".join(err_lines).strip()[-400:]
                raise LLMError(f"claude termino con codigo {proc.returncode}: {err}")
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()


class AnthropicClient(LLMClient):
    def __init__(self, model: str, api_key: str, max_tokens: int = 2000) -> None:
        if not api_key:
            raise LLMError("LLM_PROVIDER=anthropic necesita API_KEY en speak/.env")
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("falta el SDK: pip install anthropic") from exc
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def stream(self, system, prompt, cancel=None, images=None):
        content = ([image_block(p) for p in images] + [{"type": "text", "text": prompt}]) if images else prompt
        with self._client.messages.stream(
            model=self.model, max_tokens=self.max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
        ) as s:
            for text in s.text_stream:
                if cancel is not None and cancel.is_set():
                    return
                yield text


class FakeLLM(LLMClient):
    """Devuelve una respuesta fija en trozos. Guarda las llamadas."""

    def __init__(self, reply: str = "## FEEDBACK\nok\n## QUICK ANSWER\n- a\n## DETAILED ANSWER\nb"):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def stream(self, system, prompt, cancel=None, images=None):
        self.calls.append((system, prompt))
        for i in range(0, len(self.reply), 7):
            if cancel is not None and cancel.is_set():
                return
            yield self.reply[i:i + 7]


def make_llm(cfg) -> LLMClient:
    provider = cfg.LLM_PROVIDER.strip().lower()
    if provider == "claude_cli":
        return ClaudeCLIClient(cfg.LLM_MODEL, cfg.LLM_EFFORT)
    if provider == "anthropic":
        return AnthropicClient(cfg.LLM_MODEL, cfg.API_KEY)
    if provider == "fake":
        return FakeLLM()
    raise LLMError(f"LLM_PROVIDER desconocido: {cfg.LLM_PROVIDER}")
