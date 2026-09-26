"""Captura de pantalla segun el target configurado."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from dataclasses import dataclass
from pathlib import Path

import mss
from PIL import Image

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

# Bordes reales de la ventana. GetWindowRect incluye la sombra invisible que
# dibuja el compositor, asi que recorta con varios pixeles de mas por lado.
DWMWA_EXTENDED_FRAME_BOUNDS = 9

MODES = ("active_monitor", "monitor", "active_window", "all")

MODE_LABELS = {
    "active_monitor": "Monitor donde esta el cursor",
    "monitor": "Un monitor especifico",
    "active_window": "Solo la ventana activa",
    "all": "Todos los monitores",
}


class CaptureError(RuntimeError):
    pass


@dataclass
class Monitor:
    index: int
    left: int
    top: int
    width: int
    height: int
    name: str
    primary: bool

    @property
    def label(self) -> str:
        tag = " (principal)" if self.primary else ""
        return f"Monitor {self.index}: {self.width}x{self.height}{tag}"


def list_monitors() -> list[Monitor]:
    with mss.MSS() as sct:
        # monitors[0] es el rectangulo que abarca todo; los reales van desde 1.
        return [
            Monitor(
                index=i,
                left=m["left"],
                top=m["top"],
                width=m["width"],
                height=m["height"],
                name=m.get("name", f"Monitor {i}"),
                primary=bool(m.get("is_primary")),
            )
            for i, m in enumerate(sct.monitors[1:], start=1)
        ]


def _cursor_pos() -> tuple[int, int]:
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _active_window_rect() -> dict[str, int]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        raise CaptureError("no hay ventana activa")

    rect = wt.RECT()
    ok = dwmapi.DwmGetWindowAttribute(
        wt.HWND(hwnd),
        ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if ok != 0:  # ventanas viejas sin composicion: se usa el rect clasico
        user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect))

    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        raise CaptureError("la ventana activa esta minimizada o no tiene tamano")
    return {"left": rect.left, "top": rect.top, "width": width, "height": height}


def _region(sct: "mss.MSS", mode: str, monitor_index: int) -> dict[str, int]:
    if mode == "all":
        return sct.monitors[0]

    if mode == "active_window":
        return _active_window_rect()

    if mode == "monitor":
        if not 1 <= monitor_index < len(sct.monitors):
            raise CaptureError(
                f"el monitor {monitor_index} ya no existe "
                f"(hay {len(sct.monitors) - 1}); revisa la configuracion"
            )
        return sct.monitors[monitor_index]

    if mode == "active_monitor":
        x, y = _cursor_pos()
        for mon in sct.monitors[1:]:
            if (
                mon["left"] <= x < mon["left"] + mon["width"]
                and mon["top"] <= y < mon["top"] + mon["height"]
            ):
                return mon
        return sct.monitors[1]  # cursor fuera de todo: cae al principal

    raise CaptureError(f"modo de captura desconocido: {mode!r}")


def grab(mode: str = "active_monitor", monitor_index: int = 1) -> Image.Image:
    with mss.MSS() as sct:
        region = _region(sct, mode, monitor_index)
        shot = sct.grab(region)
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def save(img: Image.Image, path: str | Path, max_edge: int = 1568) -> Path:
    """Reescala si hace falta y guarda como PNG."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if max(img.size) > max_edge:
        img = img.copy()
        img.thumbnail((max_edge, max_edge), Image.LANCZOS)
    img.save(path, format="PNG", optimize=True)
    return path


def capture_to_file(
    path: str | Path,
    mode: str = "active_monitor",
    monitor_index: int = 1,
    max_edge: int = 1568,
) -> Path:
    return save(grab(mode, monitor_index), path, max_edge)
