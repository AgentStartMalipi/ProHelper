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
    _shots_dir: Path | None = field(default=None, repr=False)

    @property
    def shots_dir(self) -> Path:
        """Carpeta temporal propia; se borra entera al cerrar la sesion."""
        if self._shots_dir is None:
            self._shots_dir = Path(tempfile.mkdtemp(prefix="helper-shots-"))
        return self._shots_dir

    def next_shot_path(self) -> Path:
        return self.shots_dir / f"shot-{self.captures + 1:03d}.png"

    @property
    def started(self) -> bool:
        """True si ya hubo un turno, o sea si toca --resume en vez de abrir."""
        return self.captures > 0

    def record(self, cost_usd: float) -> None:
        self.captures += 1
        self.total_cost_usd += cost_usd

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
