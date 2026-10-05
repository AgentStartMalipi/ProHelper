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
import time
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


# Virtual-key codes que corresponden a cada bit MOD_*. Win tiene dos teclas.
_MOD_VKS = {
    MOD_CONTROL: (0x11,),
    MOD_ALT: (0x12,),
    MOD_SHIFT: (0x10,),
    MOD_WIN: (0x5B, 0x5C),
}


class PollingHotkeyListener:
    """Misma interfaz que HotkeyListener, pero consultando GetAsyncKeyState.

    Para sistemas donde RegisterHotKey falla. Diferencias con el modo normal:
    - no reserva el atajo, asi que nunca choca con otra aplicacion, pero
      tampoco se lo come: la tecla tambien le llega a la ventana activa;
    - gasta un poco de CPU revisando el teclado cada `interval` segundos.

    Como RegisterHotKey, exige los modificadores exactos: ctrl+shift+c no
    dispara con ctrl+shift+alt+c.
    """

    # Con norepeat=False, cada cuanto vuelve a disparar si sigue apretado.
    REPEAT_DELAY = 0.4
    REPEAT_RATE = 0.05

    def __init__(
        self,
        spec: str,
        on_press: Callable[[], None],
        allow_bare: bool = False,
        norepeat: bool = True,
        interval: float = 0.02,
    ) -> None:
        self.spec = spec
        self._on_press = on_press
        self._allow_bare = allow_bare
        self._norepeat = norepeat
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            raise HotkeyError("el listener ya esta corriendo")

        mods, key = parse(self.spec, self._allow_bare, self._norepeat)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(mods, key), name="hotkey-poll", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def _run(self, mods: int, key: int) -> None:
        from .input_driver import InputDriver

        driver = InputDriver()
        wanted = {bit for bit in _MOD_VKS if mods & bit}

        def combo_down() -> bool:
            if not driver.is_key_pressed(key):
                return False
            for bit, vks in _MOD_VKS.items():
                down = any(driver.is_key_pressed(vk) for vk in vks)
                if down != (bit in wanted):
                    return False
            return True

        was_down = False
        next_fire = 0.0
        while not self._stop.wait(self._interval):
            down = combo_down()
            now = time.monotonic()
            if down and not was_down:
                fire = True
                next_fire = now + self.REPEAT_DELAY
            elif down and not self._norepeat and now >= next_fire:
                fire = True
                next_fire = now + self.REPEAT_RATE
            else:
                fire = False
            was_down = down

            if fire:
                try:
                    self._on_press()
                except Exception:  # el listener nunca muere por el callback
                    import traceback

                    traceback.print_exc()


# Estructuras de SendInput. El INPUT lleva la union completa (mouse incluido)
# aunque solo se use el teclado: SendInput valida cbSize contra el tamano real.
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC = 0

# Teclas que en el teclado fisico viven en el bloque extendido.
_EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E,
                 0x5B, 0x5C, 0xA3, 0xA5}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wt.WORD),
        ("wScan", wt.WORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wt.LONG),
        ("dy", wt.LONG),
        ("mouseData", wt.DWORD),
        ("dwFlags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
user32.SendInput.restype = wt.UINT


def _key_input(vk_code: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk_code in _EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk_code, MAPVK_VK_TO_VSC)
    inp = _INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = _KEYBDINPUT(wVk=vk_code, wScan=scan, dwFlags=flags)
    return inp


class HotkeyManager:
    """Varios atajos a la vez, cada uno con su accion y su listener.

    RegisterHotKey registra por hilo, asi que un listener por combinacion es lo
    natural: si una falla (porque otra aplicacion ya la tiene) las demas siguen
    funcionando.

    Con `use_polling=True` cada atajo usa PollingHotkeyListener en vez de
    RegisterHotKey, para sistemas donde el registro falla.
    """

    def __init__(
        self,
        acciones: dict[str, Callable[[str], None]],
        use_polling: bool = False,
    ) -> None:
        self.acciones = dict(acciones)
        self.use_polling = use_polling
        self.listeners: list[HotkeyListener | PollingHotkeyListener] = []
        self.activos: list[str] = []
        self.fallidos: list[tuple[str, str]] = []

    def start(self) -> None:
        cls = PollingHotkeyListener if self.use_polling else HotkeyListener
        for spec, accion in self.acciones.items():
            listener = cls(spec, lambda s=spec, a=accion: a(s))
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

    def send_key(self, vk_code: int) -> None:
        """Manda al sistema una pulsacion completa (abajo + arriba) de `vk_code`.

        Le llega a la ventana que tenga el foco, como si fuera del teclado.
        """
        inputs = (_INPUT * 2)(_key_input(vk_code, False), _key_input(vk_code, True))
        sent = user32.SendInput(2, inputs, ctypes.sizeof(_INPUT))
        if sent != 2:
            # 0 suele ser UIPI: la ventana activa corre con mas privilegios.
            raise HotkeyError(
                f"SendInput no pudo enviar la tecla 0x{vk_code:02X}: "
                f"error {ctypes.get_last_error()} de Windows"
            )
