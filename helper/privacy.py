"""Exclusion de la ventana de las capturas de pantalla (solo Windows).

El helper vive encima de lo que estas haciendo, asi que aparece en cualquier
screen sharing o grabacion: el panel, la respuesta de Claude y el pre-prompt
quedan a la vista de quien mira. Windows tiene una respuesta oficial para eso,
`SetWindowDisplayAffinity` con `WDA_EXCLUDEFROMCAPTURE`: la ventana se sigue
viendo en el monitor pero el compositor la deja fuera del contenido capturado.

No hay equivalente en macOS ni en Linux, asi que alli esto no hace nada y la
aplicacion funciona igual.
"""

from __future__ import annotations

import ctypes
import sys

from .log import log

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

GA_ROOT = 2

IS_WINDOWS = sys.platform == "win32"

_user32 = None


def _load_user32():
    """Carga user32 una sola vez. Devuelve None fuera de Windows."""
    global _user32
    if not IS_WINDOWS:
        return None
    if _user32 is None:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
        _user32 = user32
    return _user32


def _root_hwnd(user32, window) -> "ctypes.wintypes.HWND":
    """HWND de la ventana nativa de nivel superior que Tk creo para `window`.

    `winfo_id()` puede devolver un hijo; la afinidad de captura se aplica sobre
    la ventana raiz, que es la que el compositor dibuja.
    """
    from ctypes import wintypes

    window.update_idletasks()
    hwnd = wintypes.HWND(window.winfo_id())
    top_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
    return wintypes.HWND(top_hwnd) if top_hwnd else hwnd


def _set_affinity(window, affinity: int, que: str) -> bool:
    user32 = _load_user32()
    if user32 is None:
        return False
    try:
        hwnd = _root_hwnd(user32, window)
        ctypes.set_last_error(0)
        if user32.SetWindowDisplayAffinity(hwnd, affinity):
            return True
        log.warning("%s: Windows rechazo la llamada (error %d)",
                    que, ctypes.get_last_error())
    except Exception:
        # Es una mejora de privacidad, no algo sin lo que el helper no pueda
        # arrancar: si falla se deja constancia y la ventana sigue viva.
        log.exception("%s: fallo inesperado", que)
    return False


def exclude_window_from_capture(window) -> bool:
    """Saca la ventana de las capturas de pantalla compatibles.

    Llamar cuando Tk ya creo la ventana nativa (despues de `mainloop`, o via
    `after`), no durante la construccion del widget.
    """
    return _set_affinity(window, WDA_EXCLUDEFROMCAPTURE, "excluir de capturas")


def allow_window_capture(window) -> bool:
    """Deshace la exclusion: la ventana vuelve a salir en las capturas."""
    return _set_affinity(window, WDA_NONE, "permitir capturas")
