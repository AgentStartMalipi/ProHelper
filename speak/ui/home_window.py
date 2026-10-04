"""Pantalla de inicio: elegir entre practicar y una llamada real.

Cada ventana se crea una sola vez y se reutiliza (`open_practice`,
`open_calls`), y el simulador abre Llamadas por aqui tambien: nunca hay dos
ventanas de Llamadas grabando a la vez.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from ..config import Config
from .banner import COLORS

_windows: dict[str, QMainWindow] = {}
_factories: dict[str, object] = {}


def _show(win: QMainWindow) -> QMainWindow:
    win.show()
    win.raise_()
    win.activateWindow()
    return win


def open_calls(cfg: Config) -> QMainWindow:
    from .notes_window import NotesWindow

    if "calls" not in _windows:
        _windows["calls"] = NotesWindow(cfg)
    return _show(_windows["calls"])


def open_practice(cfg: Config) -> QMainWindow:
    if "practice" not in _windows:
        from .main_window import MainWindow

        _windows["practice"] = MainWindow(cfg, _factories["simulator"])
    return _show(_windows["practice"])


def _card(title: str, detail: str, color: str) -> QPushButton:
    b = QPushButton(f"{title}\n{detail}")
    b.setMinimumHeight(110)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(
        f"QPushButton {{ background: {color}; color: white; font-size: 15px; text-align: left;"
        " padding: 14px 18px; border-radius: 10px; }"
        " QPushButton:hover { border: 2px solid white; }")
    return b


class HomeWindow(QMainWindow):
    def __init__(self, cfg: Config, sim_factory) -> None:
        super().__init__()
        self.cfg = cfg
        _factories["simulator"] = sim_factory
        self.setWindowTitle("SPEAK · Inicio")
        self.resize(560, 380)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setSpacing(14)
        head = QLabel("¿Qué vas a hacer?")
        head.setStyleSheet("font-size: 20px; font-weight: bold;")
        lay.addWidget(head)

        practice = _card(
            "🎓  Practicar una entrevista",
            "La app es el entrevistador: te pregunta, respondes en voz alta y te da feedback.",
            COLORS["practice"])
        calls = _card(
            "📞  Llamada real (copiloto y notas)",
            "Grabas una llamada con un cliente: copiloto en vivo y notas al terminar.\n"
            "También importar un audio o una transcripción.",
            COLORS["live"])
        practice.clicked.connect(lambda: open_practice(cfg))
        calls.clicked.connect(lambda: open_calls(cfg))
        lay.addWidget(practice)
        lay.addWidget(calls)
        hint = QLabel("Cada ventana tiene una franja de color arriba que dice dónde estás: "
                      "morada = práctica · roja = en llamada con copiloto · "
                      "naranja = grabando solo notas · gris = sin grabar.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        lay.addWidget(hint)
        lay.addStretch(1)
        self.setCentralWidget(central)
