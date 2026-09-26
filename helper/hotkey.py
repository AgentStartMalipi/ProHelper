"""Atajo global de Windows via RegisterHotKey.

Se usa la API nativa en vez de un hook de teclado de bajo nivel (tipo la
libreria `keyboard`): RegisterHotKey registra una sola combinacion con el
sistema y no ve ninguna otra tecla, asi que no dispara alertas de antivirus.

RegisterHotKey y GetMessage tienen que correr en el mismo hilo, por eso el
listener se queda con un hilo propio y avisa al resto por callback.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}

# Solo los virtual-key codes que tiene sentido usar como disparador.
_KEYS = {
    **{c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    "SPACE": 0x20,
    "INSERT": 0x2D,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    **{f"F{i}": 0x6F + i for i in range(1, 13)},
}


class HotkeyError(RuntimeError):
    pass


def parse(
    spec: str, allow_bare: bool = False, norepeat: bool = True
) -> tuple[int, int]:
    """'ctrl+shift+c' -> (modificadores, virtual-key code).

    `allow_bare` permite registrar una tecla sin modificador. Solo lo usa el
    modo mover, que toma las flechas mientras esta activo y las suelta al
    salir; para los atajos normales sigue siendo un error.
    """
    parts = [p.strip().lower() for p in spec.split("+") if p.strip()]
    if not parts:
        raise HotkeyError(f"atajo vacio: {spec!r}")

    mods = 0
    key = None
    for part in parts:
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        elif part.upper() in _KEYS:
            if key is not None:
                raise HotkeyError(f"{spec!r} tiene mas de una tecla principal")
            key = _KEYS[part.upper()]
        else:
            raise HotkeyError(f"tecla desconocida en {spec!r}: {part!r}")

    if key is None:
        raise HotkeyError(f"{spec!r} no tiene tecla principal (solo modificadores)")
    if not mods and not allow_bare:
        raise HotkeyError(
            f"{spec!r} no tiene modificador; una tecla sola secuestraria esa "
            "tecla en todo Windows"
        )
    # NOREPEAT evita una rafaga de disparos si dejas el atajo apretado. El modo
    # mover lo quiere al reves: manteniendo la flecha el panel sigue andando.
    return (mods | MOD_NOREPEAT) if norepeat else mods, key


class HotkeyListener:
    """Escucha una combinacion global y llama `on_press` cuando se activa.

    El callback corre en el hilo del listener, no en el de Tk: quien lo reciba
    tiene que reenviarlo a la UI por cola.
    """

    def __init__(
        self,
        spec: str,
        on_press: Callable[[], None],
        allow_bare: bool = False,
        norepeat: bool = True,
    ) -> None:
        self.spec = spec
        self._on_press = on_press
        self._allow_bare = allow_bare
        self._norepeat = norepeat
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self._error: Exception | None = None

    def start(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            raise HotkeyError("el listener ya esta corriendo")

        # valida antes de abrir el hilo
        mods, key = parse(self.spec, self._allow_bare, self._norepeat)
        self._thread = threading.Thread(
            target=self._run, args=(mods, key), name="hotkey", daemon=True
        )
        self._thread.start()

        if not self._ready.wait(timeout):
            raise HotkeyError("el listener no arranco a tiempo")
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = None

    def _run(self, mods: int, key: int) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        hotkey_id = 1

        if not user32.RegisterHotKey(None, hotkey_id, mods, key):
            err = ctypes.get_last_error()
            # 1409 = ERROR_HOTKEY_ALREADY_REGISTERED
            detail = (
                "otra aplicacion ya tiene ese atajo"
                if err == 1409
                else f"error {err} de Windows"
            )
            self._error = HotkeyError(f"no se pudo registrar {self.spec!r}: {detail}")
            self._ready.set()
            return

        self._ready.set()
        try:
            msg = wt.MSG()
            # GetMessage devuelve 0 en WM_QUIT y -1 si algo falla.
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self._on_press()
                    except Exception:  # el listener nunca muere por el callback
                        import traceback

                        traceback.print_exc()
        finally:
            user32.UnregisterHotKey(None, hotkey_id)


class HotkeyManager:
    """Varios atajos a la vez, cada uno con su accion y su listener.

    RegisterHotKey registra por hilo, asi que un listener por combinacion es lo
    natural: si una falla (porque otra aplicacion ya la tiene) las demas siguen
    funcionando.
    """

    def __init__(self, acciones: dict[str, Callable[[str], None]]) -> None:
        self.acciones = dict(acciones)
        self.listeners: list[HotkeyListener] = []
        self.activos: list[str] = []
        self.fallidos: list[tuple[str, str]] = []

    def start(self) -> None:
        for spec, accion in self.acciones.items():
            listener = HotkeyListener(spec, lambda s=spec, a=accion: a(s))
            try:
                listener.start()
            except HotkeyError as exc:
                self.fallidos.append((spec, str(exc)))
                continue
            self.listeners.append(listener)
            self.activos.append(spec)

    def stop(self) -> None:
        for listener in self.listeners:
            listener.stop()
        self.listeners.clear()
        self.activos.clear()
        self.fallidos.clear()

    @property
    def alguno_activo(self) -> bool:
        return bool(self.activos)
