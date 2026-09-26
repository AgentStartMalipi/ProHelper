"""Clientes de LLM con streaming y cancelacion.

Interfaz unica: `stream(system, prompt, cancel)` → iterador de trozos de
texto. La UI pinta cada trozo al llegar.

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

import json
import logging
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from typing import Iterator

log = logging.getLogger(__name__)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    @abstractmethod
    def stream(self, system: str, prompt: str,
               cancel: threading.Event | None = None) -> Iterator[str]:
        ...

    def complete(self, system: str, prompt: str) -> str:
        return "".join(self.stream(system, prompt))


class ClaudeCLIClient(LLMClient):
    def __init__(self, model: str, effort: str = "low", timeout: float = 180.0) -> None:
        self.model = model
        self.effort = effort
        self.timeout = timeout

    def _args(self, system: str) -> list[str]:
        cli = shutil.which("claude")
        if not cli:
            raise LLMError("no encuentro `claude` en el PATH (instala Claude Code o usa "
                           "LLM_PROVIDER=anthropic)")
        return [
            cli, "-p", "--verbose",
            "--output-format", "stream-json", "--include-partial-messages",
            "--model", self.model, "--effort", self.effort,
            # Sin herramientas, MCP ni settings: solo texto, y sin cargar el
            # harness completo (lo mismo que midio SCREEN: 15x mas barato).
            "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
            "--setting-sources", "", "--permission-mode", "dontAsk",
            "--no-session-persistence", "--system-prompt", system,
        ]

    def stream(self, system, prompt, cancel=None):
        proc = subprocess.Popen(
            self._args(system), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            creationflags=_NO_WINDOW,
        )
        timer = threading.Timer(self.timeout, proc.kill)
        timer.start()
        got_delta = False
        final_text = ""
        try:
            proc.stdin.write(prompt)
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
                err = (proc.stderr.read() or "").strip()[-400:]
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

    def stream(self, system, prompt, cancel=None):
        with self._client.messages.stream(
            model=self.model, max_tokens=self.max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
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

    def stream(self, system, prompt, cancel=None):
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
