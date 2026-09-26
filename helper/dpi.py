"""Escalado DPI, fijado a proposito antes de que exista la ventana.

Sin esto el comportamiento depende del orden de los imports, que es una trampa
silenciosa: `mss` vuelve el proceso DPI-aware la primera vez que se instancia.
Si eso pasa **despues** de crear la ventana de Tk, Tk se queda con el tamano de
pantalla virtualizado (1536 en una pantalla de 1920 al 125%) pero sus
coordenadas pasan a caer en pixeles fisicos. El resultado es un panel un 20%
mas pequeno y a 400px de la esquina a la que apuntaba.

La solucion es declarar la conciencia de DPI al arrancar, antes de Tk: a partir
de ahi Tk reporta y coloca en pixeles fisicos, todo en la misma unidad. A cambio
hay que escalar la interfaz a mano, que es lo que hace `scale_factor`.
"""

from __future__ import annotations

import ctypes

PER_MONITOR_AWARE = 2


def enable_awareness() -> None:
    """Declara el proceso DPI-aware. Llamar antes de crear la ventana de Tk."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(PER_MONITOR_AWARE)
        return
    except (AttributeError, OSError):
        pass
    try:  # Windows anteriores a 8.1
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass  # sin escalado: la interfaz se vera algo pequena, pero funciona


def system_dpi() -> int:
    try:
        return int(ctypes.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError):
        return 96


def scale_factor() -> float:
    """1.0 al 100%, 1.25 al 125%, etc."""
    return system_dpi() / 96.0
