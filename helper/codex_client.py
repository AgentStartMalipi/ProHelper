"""Cliente de ChatGPT por el CLI de Codex, en modo headless.

Igual que con Claude: se invoca `codex exec` como subproceso y reutiliza tu
login de ChatGPT, asi que no hace falta API key ni facturacion aparte.

Codex trae un harness de agente entero (shell, busqueda web, skills, AGENTS.md):
medido, ~16k tokens de entrada por captura. Aqui se reemplazan sus
instrucciones por el system prompt del helper y se apaga todo lo demas; la
entrada baja a la mitad. Sin herramientas y en sandbox de solo lectura: nada
puede tocar el disco ni la red desde aqui.

Dos detalles medidos:
- Codex tarda ~1s en salir despues de terminar el turno. Se lee el stream y se
  corta en cuanto llega `turn.completed`; por eso la respuesta se saca del
  evento `agent_message` y no de `-o`, que se escribe al salir.
- Con una cuenta de ChatGPT solo sirven algunos modelos (gpt-6-luna y
  gpt-6-astra si; gpt-6.1-sol y gpt-5.4-mini dan 400).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .claude_client import ClaudeError, Reply

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Lo que se apaga del harness de Codex. Cada clave esta en la referencia de
# config de Codex; sin ellas la misma captura mandaba el doble de tokens.
_LIGERO = [
    "--ignore-user-config",
    "--ignore-rules",
    "-c", "features.shell_tool=false",
    "-c", 'web_search="disabled"',
    "-c", "tools.view_image=false",
    "-c", "features.unified_exec=false",
    "-c", "features.multi_agent=false",
    "-c", "features.memories=false",
    "-c", "features.hooks=false",
    "-c", "project_doc_max_bytes=0",
    "-c", 'model_reasoning_summary="none"',
    "-c", "skills.max_context_tokens=1",
]

# Turnos que se guardan por conversacion para "Usar pasados" en modo imagenes.
MAX_TURNS = 12

PREVIOUS = "CONVERSACION ANTERIOR DE ESTA SESION (las capturas viejas ya no las ves):"


class CodexError(ClaudeError):
    """Hereda de ClaudeError para que la app los trate igual."""


def find_cli() -> str:
    path = shutil.which("codex")
    if not path:
        raise CodexError(
            "no encuentro el comando `codex` en el PATH. Instala Codex CLI "
            "(npm install -g @openai/codex) y entra con `codex login`."
        )
    return path


class CodexClient:
    def __init__(self, config) -> None:
        self.config = config
        # id de conversacion -> [(pregunta, respuesta)]. Codex en modo
        # efimero no guarda sesiones, asi que el historial se lleva aqui.
        self._historial: dict[str, list[tuple[str, str]]] = {}
        self._cwd_vacio: Path | None = None

    @property
    def _cwd(self) -> Path:
        """Carpeta vacia de trabajo: que no lea ningun AGENTS.md del proyecto.

        Se crea al primer uso, no al arrancar: quien no use ChatGPT no deja
        carpetas sueltas en el temporal.
        """
        if self._cwd_vacio is None:
            self._cwd_vacio = Path(tempfile.mkdtemp(prefix="helper-codex-"))
        return self._cwd_vacio

    def _args(self, modelo: str, effort: str, instrucciones: Path,
              imagenes: list[Path]) -> list[str]:
        args = [
            find_cli(), "exec",
            "--skip-git-repo-check",
            "--ephemeral",  # no deja sesiones en ~/.codex
            "-s", "read-only",
            "-C", str(self._cwd),
            "--json",
            "-m", modelo,
            "-c", f'model_reasoning_effort="{effort}"',
            # Reemplaza las instrucciones de agente por las del helper.
            "-c", f'model_instructions_file="{instrucciones.as_posix()}"',
            *_LIGERO,
        ]
        for img in imagenes:
            args += ["-i", str(img)]
        return args + ["-"]  # el prompt va por stdin

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
        # `model`/`effort` de la sesion vienen de plantillas pensadas para
        # Claude: aqui mandan los de la configuracion de ChatGPT.
        del model, effort, resume
        modelo = self.config["codex_model"]
        effort = self.config["codex_effort"]

        imagenes = [p for _, p in extra_images or []]
        partes: list[str] = []
        previos = self._historial.get(session_id, [])
        if previos:
            lineas = [PREVIOUS]
            for q, a in previos:
                lineas += [f"Yo: {q}", f"Tu: {a}"]
            partes.append("\n".join(lineas))
        if extra_images:
            etiquetas = ", ".join(label.rstrip(":") for label, _ in extra_images)
            partes.append(f"Imagenes adjuntas, en orden: {etiquetas}; la ultima "
                          f"es la pantalla actual.")
        if image_path is not None:
            imagenes.append(image_path)
        partes.append(question)
        prompt = "\n\n".join(partes)

        tmp = Path(tempfile.mkdtemp(prefix="helper-codex-turno-"))
        instrucciones = tmp / "instrucciones.md"
        instrucciones.write_text(system_prompt or "Responde.", encoding="utf-8")
        try:
            texto, ms = self._run(
                self._args(modelo, effort, instrucciones, imagenes), prompt, timeout,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        self._historial[session_id] = (previos + [(question, texto)])[-MAX_TURNS:]
        return Reply(
            text=texto,
            cost_usd=0.0,  # va contra la suscripcion de ChatGPT
            duration_ms=ms,
            session_id=session_id,
            model=modelo,
        )

    def _run(self, args: list[str], prompt: str, timeout: float) -> tuple[str, int]:
        t0 = time.time()
        # stderr a un archivo: si fuera un pipe sin leer, podria llenarse y
        # dejar a codex bloqueado mientras aqui se lee stdout.
        errores = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errores,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_NO_WINDOW,
        )
        # El timeout se vigila aparte: leer el stream bloquea.
        vencido = threading.Timer(timeout, _matar, args=(proc,))
        vencido.start()
        error = ""
        mensajes: list[str] = []
        terminado = False
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for linea in proc.stdout:
                try:
                    evento = json.loads(linea)
                except json.JSONDecodeError:
                    continue  # ruido que no es JSON
                tipo = evento.get("type")
                item = evento.get("item") or {}
                if tipo == "item.completed" and item.get("type") == "agent_message":
                    mensajes.append(item.get("text") or "")
                elif tipo == "error":
                    error = _mensaje(evento.get("message", ""))
                elif tipo == "turn.failed":
                    error = error or _mensaje(str(evento.get("error", "")))
                    break
                elif tipo == "turn.completed":
                    terminado = True
                    break
        finally:
            vencido.cancel()
            if proc.poll() is None:
                # Ya tenemos la respuesta: no hace falta esperar a que salga.
                _matar(proc)
            proc.wait()
            errores.seek(0)
            stderr = errores.read()
            errores.close()
        ms = int((time.time() - t0) * 1000)

        if not terminado:
            if error:
                raise CodexError(f"ChatGPT: {error}")
            if ms >= timeout * 1000:
                raise CodexError(f"ChatGPT no respondio en {int(timeout)}s. Reintenta.")
            detalle = stderr.strip().splitlines()
            raise CodexError(detalle[-1] if detalle else "codex termino sin respuesta")

        # Si hubo varios mensajes en el turno, el ultimo es la respuesta.
        texto = mensajes[-1].strip() if mensajes else ""
        if not texto:
            raise CodexError("ChatGPT no devolvio una respuesta")
        return texto, ms


def _matar(proc: subprocess.Popen) -> None:
    """Mata codex y lo que haya lanzado.

    `codex` en Windows es un .cmd que arranca node, y este el binario: matar
    solo el primero dejaria a los otros vivos.
    """
    if proc.poll() is not None:
        return
    if _NO_WINDOW:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True, creationflags=_NO_WINDOW,
        )
    else:
        proc.kill()


def _mensaje(crudo: str) -> str:
    """Los errores de la API llegan como JSON dentro del mensaje."""
    try:
        return json.loads(crudo)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return crudo.strip()[:300]
