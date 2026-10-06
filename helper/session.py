"""Estado de una sesion del helper.

Una sesion = un UUID de conversacion + un pre-prompt + un target de captura.
Todas las capturas de la sesion van a la misma conversacion, asi que Claude ve
las anteriores y no hay que re-explicarle el contexto cada vez.

El pre-prompt se fija al abrir y no cambia: una sesion tiene un solo juego de
instrucciones de principio a fin. Para otro prompt, otra sesion. Asi ninguna
sesion arrastra las instrucciones de otra.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import claude_client
from .memoria import Entry


# Largo del titulo de una sesion. Da para reconocerla de un vistazo sin comerse
# la linea de estado, que ademas lleva el target, las capturas y el costo.
TITULO_MAX = 28


def titulo_desde_prompt(texto: str) -> str:
    """Un titulo corto a partir del pre-prompt escrito a mano.

    Corta por palabra entera: partir a media palabra se lee peor que quedarse
    un poco mas corto.
    """
    limpio = " ".join(texto.split())
    if not limpio:
        return "Sin pre-prompt"
    if len(limpio) <= TITULO_MAX:
        return limpio
    recorte = limpio[:TITULO_MAX].rsplit(" ", 1)[0] or limpio[:TITULO_MAX]
    return recorte + "\u2026"


@dataclass
class Session:
    preprompt: str = ""
    # Como se llama esta sesion en el panel: el nombre de la plantilla si usaste
    # una, o las primeras palabras de lo que escribieras.
    title: str = ""
    capture_mode: str = "active_monitor"
    monitor_index: int = 1
    # Modelo/effort propios de la sesion, si la plantilla los fijo. None = usa
    # los de la configuracion global.
    model: str | None = None
    effort: str | None = None
    # Que IA responde en esta sesion ("claude" o "groq"). Se puede cambiar a
    # mitad desde el menu del panel.
    provider: str = "claude"
    session_id: str = field(default_factory=claude_client.new_session_id)
    started_at: float = field(default_factory=time.time)
    captures: int = 0
    total_cost_usd: float = 0.0
    # Todo lo que el panel ha enseñado de esta sesion, en orden: (texto, tag).
    # Se guarda entero y no solo lo ultimo por dos razones: el panel es uno solo
    # para todas las sesiones, asi que al cambiar hay que poder repintarlo; y
    # dentro de una sesion quiero poder subir a releer lo anterior.
    historial: list[tuple[str, str | None]] = field(default_factory=list)
    last_hint: str = ""
    # "Usar pasados": si esta marcado, cada captura sigue la conversacion de la
    # sesion y Claude ve las anteriores. Si no, la captura va sola (pre-prompt
    # + esta imagen) en una conversacion nueva: mucho mas barato, porque
    # reanudar re-envia todas las capturas previas en cada turno.
    use_history: bool = True
    # Turnos enviados a la conversacion PRINCIPAL. No es `captures`: las sueltas
    # no la tocan, y al volver a marcar "Usar pasados" se sigue donde iba.
    history_turns: int = 0
    # De esos, los que fueron a Claude. Solo Claude guarda la conversacion de
    # su lado: si la sesion empezo con Groq, el primer turno con Claude tiene
    # que abrirla, no reanudar una que no existe.
    claude_turns: int = 0
    # Memoria por resumen (ver memoria.py): una nota por captura con pasados.
    # Solo se llena con history_mode "resumen"; en "imagenes" manda --resume.
    memoria: list[Entry] = field(default_factory=list)
    _shots_dir: Path | None = field(default=None, repr=False)

    @property
    def shots_dir(self) -> Path:
        """Carpeta temporal propia; se borra entera al cerrar la sesion."""
        if self._shots_dir is None:
            self._shots_dir = Path(tempfile.mkdtemp(prefix="helper-shots-"))
        return self._shots_dir

    def next_shot_path(self) -> Path:
        return self.shot_path(self.captures + 1)

    def shot_path(self, n: int) -> Path:
        """La captura numero `n` de la sesion (para pedirla de vuelta)."""
        return self.shots_dir / f"shot-{n:03d}.png"

    @property
    def started(self) -> bool:
        """True si la conversacion principal ya existe en Claude (toca --resume)."""
        return self.claude_turns > 0

    def conversation_for_next(self) -> tuple[str, bool]:
        """(id de conversacion, resume) para la proxima captura."""
        if self.use_history:
            return self.session_id, self.started
        return claude_client.new_session_id(), False

    def record(self, cost_usd: float, in_history: bool = True,
               provider: str = "claude") -> None:
        """`in_history`: el turno fue a la conversacion principal (no suelto)."""
        self.captures += 1
        self.total_cost_usd += cost_usd
        if in_history:
            self.history_turns += 1
            if provider == "claude":
                self.claude_turns += 1

    def remember(
        self,
        answer: str,
        tag: str | None = None,
        hint: str = "",
        reemplaza: bool = False,
    ) -> None:
        """Añade al historial lo que el panel esta enseñando de esta sesion.

        `reemplaza` es para los avisos de apertura: son un marcador de posicion,
        no una respuesta que merezca quedarse en el historial.
        """
        if reemplaza or not self.historial:
            self.historial = [(answer, tag)]
        else:
            self.historial.append((answer, tag))
        if hint:
            self.last_hint = hint

    @property
    def last_answer(self) -> str:
        return self.historial[-1][0] if self.historial else ""

    @property
    def last_answer_tag(self) -> str | None:
        return self.historial[-1][1] if self.historial else None

    @property
    def elapsed_label(self) -> str:
        secs = int(time.time() - self.started_at)
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m"

    @property
    def label(self) -> str:
        """El titulo, calculado del pre-prompt si nadie fijo uno.

        Tambien se acorta el nombre de la plantilla: algunos no caben en la
        linea de estado, que ademas lleva target, capturas y costo.
        """
        return titulo_desde_prompt(self.title or self.preprompt)

    @property
    def status_label(self) -> str:
        n = self.captures
        plural = "captura" if n == 1 else "capturas"
        return f"{n} {plural} · ${self.total_cost_usd:.2f} · {self.elapsed_label}"

    def close(self) -> None:
        if self._shots_dir is not None:
            shutil.rmtree(self._shots_dir, ignore_errors=True)
            self._shots_dir = None
