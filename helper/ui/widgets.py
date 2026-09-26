"""Controles basicos reutilizables.

Tkinter no trae botones planos decentes en Windows (el ttk nativo impone el
tema del sistema), asi que se arman sobre Label/Frame.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from . import theme


class FlatButton(tk.Label):
    """Boton plano con hover, sobre un Label."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        bg: str = theme.BG_HEADER,
        hover: str = theme.BG_HOVER,
        fg: str = theme.FG,
        font=theme.FONT,
        padx: int = 10,
        pady: int = 4,
        anchor: str = "center",
    ) -> None:
        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=fg,
            font=font,
            padx=padx,
            pady=pady,
            anchor=anchor,
            cursor="hand2",
        )
        self._bg, self._hover, self._command = bg, hover, command
        self._fg = fg
        self._enabled = True
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, _=None) -> None:
        if self._enabled:
            self.configure(bg=self._hover)

    def _on_leave(self, _=None) -> None:
        self.configure(bg=self._bg)

    def _on_click(self, _=None) -> None:
        if self._enabled:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(
            fg=self._fg if enabled else theme.FG_FAINT,
            cursor="hand2" if enabled else "arrow",
        )
        if not enabled:
            self.configure(bg=self._bg)


class PrimaryButton(FlatButton):
    def __init__(self, master: tk.Misc, text: str, command: Callable[[], None], **kw):
        kw.setdefault("bg", theme.ACCENT)
        kw.setdefault("hover", theme.ACCENT_HOVER)
        kw.setdefault("fg", "#ffffff")
        kw.setdefault("font", theme.FONT_BOLD)
        kw.setdefault("pady", 6)
        super().__init__(master, text, command, **kw)


class Spinner(tk.Label):
    """Indicador de espera en texto. Se anima solo mientras esta visible."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, master: tk.Misc, **kw) -> None:
        kw.setdefault("bg", theme.BG)
        kw.setdefault("fg", theme.ACCENT)
        kw.setdefault("font", ("Consolas", 11))
        super().__init__(master, text=self.FRAMES[0], **kw)
        self._i = 0
        self._job: str | None = None

    def start(self) -> None:
        if self._job is None:
            self._tick()

    def stop(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self) -> None:
        self._i = (self._i + 1) % len(self.FRAMES)
        self.configure(text=self.FRAMES[self._i])
        self._job = self.after(80, self._tick)


def separator(master: tk.Misc) -> tk.Frame:
    return tk.Frame(master, bg=theme.BORDER, height=1)


def make_draggable(window: tk.Toplevel | tk.Tk, handle: tk.Misc) -> None:
    """Permite arrastrar una ventana sin bordes tomandola por `handle`."""
    state = {"x": 0, "y": 0}

    def press(event: tk.Event) -> None:
        state["x"], state["y"] = event.x_root, event.y_root

    def drag(event: tk.Event) -> None:
        dx = event.x_root - state["x"]
        dy = event.y_root - state["y"]
        state["x"], state["y"] = event.x_root, event.y_root
        window.geometry(f"+{window.winfo_x() + dx}+{window.winfo_y() + dy}")

    handle.bind("<Button-1>", press, add="+")
    handle.bind("<B1-Motion>", drag, add="+")
