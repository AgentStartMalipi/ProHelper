"""Cliente del CLI de Claude Code en modo headless.

Se invoca `claude -p` como subproceso, lo que reutiliza el login existente:
no hace falta API key ni facturacion aparte.

La imagen viaja como bloque de contenido base64 por stdin (`--input-format
stream-json`), no como ruta para que Claude la abra con la herramienta Read.
Medido en el spike inicial: un turno en vez de dos, ~15% menos latencia, ~35%
menos costo, y permite correr sin ninguna herramienta habilitada.

Tambien se reemplaza el system prompt por uno minimo y se apagan skills, MCP y
settings. Sin eso el CLI carga el harness completo de Claude Code: la misma
pregunta costaba $0.51 en vez de $0.03.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

# Evita que parpadee una ventana de consola en cada captura.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ClaudeError(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    cost_usd: float
    duration_ms: int
    session_id: str
    # El modelo que respondio de verdad, para el log y el pie del panel. Con
    # Groq puede no ser el elegido (las capturas van al de vision).
    model: str = ""

    @property
    def cost_label(self) -> str:
        return f"${self.cost_usd:.3f}"


def find_cli() -> str:
    path = shutil.which("claude")
    if not path:
        raise ClaudeError(
            "no encuentro el comando `claude` en el PATH. Instala Claude Code "
            "o abre el helper desde una terminal donde `claude` funcione."
        )
    return path


def new_session_id() -> str:
    return str(uuid.uuid4())


def _image_block(path: Path) -> dict:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": data},
    }


def _user_message(
    text: str,
    image_path: Path | None,
    extra_images: list[tuple[str, Path]] | None = None,
) -> str:
    """`extra_images`: capturas anteriores pedidas de vuelta, (etiqueta, ruta).

    Van primero, cada una precedida de su etiqueta, y la actual al final: asi
    "la ultima imagen" es siempre la pantalla de ahora.
    """
    content: list[dict] = []
    for label, path in extra_images or []:
        content.append({"type": "text", "text": label})
        content.append(_image_block(path))
    if image_path is not None:
        content.append(_image_block(image_path))
    content.append({"type": "text", "text": text})
    return json.dumps({"type": "user", "message": {"role": "user", "content": content}})


def _parse(stdout: str) -> dict:
    """Saca el evento `result` del stream JSONL."""
    result = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # ruido que no es JSON: se ignora
        if event.get("type") == "result":
            result = event
    if result is None:
        raise ClaudeError("Claude no devolvio un resultado")
    if result.get("is_error"):
        raise ClaudeError(result.get("result") or "Claude devolvio un error")
    return result


class ClaudeClient:
    def __init__(self, config) -> None:
        self.config = config

    def _args(
        self,
        session_id: str,
        resume: bool,
        system_prompt: str,
        model: str | None = None,
        effort: str | None = None,
    ) -> list[str]:
        # La plantilla puede pedir su propio modelo/effort; si no, los globales.
        args = [
            find_cli(),
            "-p",
            "--verbose",  # el CLI lo exige junto a --output-format stream-json
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--model",
            model or self.config["model"],
            "--effort",
            effort or self.config["effort"],
            # Sin herramientas: solo mira la imagen y responde. Nada puede
            # tocar el disco ni la red desde aqui.
            "--tools",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--setting-sources",
            "",
            "--permission-mode",
            "dontAsk",  # nadie puede responder un prompt de permiso
        ]
        if resume:
            args += ["--resume", session_id]
        else:
            # El system prompt se fija al abrir la sesion y persiste al resumir.
            args += ["--session-id", session_id, "--system-prompt", system_prompt]
        return args

    def send(
        self,
        session_id: str,
        question: str,
        image_path: Path | None = None,
        resume: bool = False,
        system_prompt: str = "",
        timeout: float = 120.0,
        model: str | None = None,
        effort: str | None = None,
        extra_images: list[tuple[str, Path]] | None = None,
    ) -> Reply:
        model = model or self.config["model"]
        args = self._args(session_id, resume, system_prompt, model, effort)
        payload = _user_message(question, image_path, extra_images) + "\n"

        try:
            proc = subprocess.run(
                args,
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            raise ClaudeError(
                f"Claude no respondio en {int(timeout)}s. Reintenta."
            ) from None

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise ClaudeError(detail[0] if detail else f"claude salio con {proc.returncode}")

        result = _parse(proc.stdout)
        return Reply(
            text=(result.get("result") or "").strip(),
            cost_usd=float(result.get("total_cost_usd") or 0.0),
            duration_ms=int(result.get("duration_ms") or 0),
            session_id=result.get("session_id") or session_id,
            model=model,
        )
