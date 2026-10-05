# Wrapper para driver de input
"""Lectura del estado del teclado via GetAsyncKeyState.

Se consulta el estado de las teclas bajo demanda (polling) en vez de
registrar un atajo (RegisterHotKey) o instalar un hook (SetWindowsHookEx):
no queda nada registrado en el sistema y no hace falta un hilo con bucle de
mensajes.
"""

from __future__ import annotations

import ctypes
from typing import Iterable

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

# Virtual-key codes de los modificadores. Los genericos (VK_CONTROL, etc.)
# ya cubren tanto la tecla izquierda como la derecha.
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_MODIFIERS = {
    "ctrl": (VK_CONTROL,),
    "control": (VK_CONTROL,),
    "alt": (VK_MENU,),
    "shift": (VK_SHIFT,),
    "win": (VK_LWIN, VK_RWIN),
}

# Bit alto del resultado: la tecla esta abajo en este momento.
_KEY_DOWN = 0x8000


class InputDriver:
    def is_key_pressed(self, vk_code: int) -> bool:
        """True si la tecla `vk_code` esta presionada ahora mismo."""
        return bool(user32.GetAsyncKeyState(vk_code) & _KEY_DOWN)

    def check_modifiers(self, mods_list: Iterable[str]) -> bool:
        """True si todos los modificadores de `mods_list` estan presionados.

        Acepta "ctrl"/"control", "alt", "shift" y "win" (sin distinguir
        mayusculas). Una lista vacia devuelve True.
        """
        for mod in mods_list:
            name = mod.strip().lower()
            if name not in _MODIFIERS:
                raise ValueError(f"Modificador desconocido: {mod!r}")
            if not any(self.is_key_pressed(vk) for vk in _MODIFIERS[name]):
                return False
        return True

