"""Franja de color arriba de cada ventana: dice DONDE estas y QUE esta pasando.

Un color por situacion, siempre el mismo, para reconocerla de un vistazo:

    practice  morado   simulador: la app es el entrevistador
    idle      gris     llamadas: listo, sin grabar
    live      rojo     grabando una llamada CON copiloto
    notes     naranja  grabando SOLO notas (sin copiloto)
    busy      azul     procesando (transcripcion final, notas)
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

COLORS = {
    "practice": "#5b3fd1",
    "idle": "#3d434d",
    "live": "#c62828",
    "notes": "#d35400",
    "busy": "#1565c0",
}


class ModeBanner(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWordWrap(True)
        self.kind = ""
        self.set_state("idle", "")

    def set_state(self, kind: str, text: str) -> None:
        self.kind = kind
        self.setText(text)
        self.setStyleSheet(
            f"background: {COLORS.get(kind, COLORS['idle'])}; color: white; font-size: 14px;"
            "font-weight: bold; padding: 8px 12px; border-radius: 6px;")
