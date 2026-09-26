"""Preparar llamada: fuentes, mini chat y brief.

Izquierda: la carpeta de conocimiento y los documentos de ESTA llamada
(adjuntos o texto pegado). Centro: el chat, donde le cuentas de que va la
reunion y que debe estudiar. Derecha: la guia (como el pre-prompt de SCREEN,
con plantillas) y el brief, editable a mano; los dos viajan en cada
respuesta en vivo del copiloto.

La guia NO se borra con "Nueva preparacion": suele ser quien eres y como
trabajas, y sirve para la siguiente llamada. Esta siempre a la vista.

Todo se guarda en `data/prep/current.json`: si cierras y vuelves, sigue ahi.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR, Config
from ..knowledge import SUPPORTED, KnowledgeBase
from ..llm_client import make_llm
from ..notes.analyzer import MODES
from ..notes.copilot import COPILOT_MODES, PRESETS, PrepSession
from .bridge import TaskSignals

PREP_FILE = DATA_DIR / "prep" / "current.json"


class PasteDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pegar texto para esta llamada")
        self.resize(640, 480)
        lay = QVBoxLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nombre (p. ej. notas del cliente, correo de Juan, propuesta v2)")
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText("Pega aqui: correos, notas, la propuesta, el alcance...")
        lay.addWidget(self.name)
        lay.addWidget(self.text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


def save_prep(prep: PrepSession) -> None:
    PREP_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = prep.to_dict() | {"extra": prep.kb.extra_texts()}
    PREP_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_prep(prep: PrepSession) -> None:
    if not PREP_FILE.exists():
        return
    try:
        data = json.loads(PREP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    prep.load_dict(data)
    for name, text in data.get("extra", {}).items():
        prep.kb.add_text(name, text)


class PrepWindow(QMainWindow):
    def __init__(self, cfg: Config, prep: PrepSession, mode_box: QComboBox) -> None:
        super().__init__()
        self.cfg = cfg
        self.prep = prep
        self.kb: KnowledgeBase = prep.kb
        self.mode_box = mode_box  # el de la ventana de notas: un solo "Tipo"
        self.setWindowTitle("SPEAK — Preparar llamada")
        self.resize(1250, 780)
        self._busy = False
        self._streaming = ""
        self.sig = TaskSignals()
        self.sig.chunk.connect(self._on_chunk)
        self.sig.done.connect(self._on_done)
        self.sig.failed.connect(lambda m: self._set_status(f"⚠ {m}", error=True))
        self.sig.progress.connect(lambda m: m and self._set_status(m))
        self._build()
        self._refresh_sources()
        self._render_chat()
        self.brief.setPlainText(prep.brief)

    # --- interfaz -------------------------------------------------------------

    def _build(self) -> None:
        split = QSplitter(Qt.Horizontal)

        # Fuentes
        left = QWidget()
        ll = QVBoxLayout(left)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tipo:"))
        self.mode = QComboBox()
        self.mode.addItems(list(MODES))
        self.mode.setCurrentText(self.mode_box.currentText())
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.mode_box.currentTextChanged.connect(
            lambda m: self.mode.currentText() != m and self.mode.setCurrentText(m))
        row.addWidget(self.mode, 1)
        ll.addLayout(row)
        self.lbl_copilot = QLabel()
        self.lbl_copilot.setWordWrap(True)
        ll.addWidget(self.lbl_copilot)

        kb_box = QGroupBox("Carpeta de conocimiento (siempre disponible)")
        kl = QVBoxLayout(kb_box)
        self.lbl_folder = QLabel()
        self.lbl_folder.setWordWrap(True)
        self.lbl_folder.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kl.addWidget(self.lbl_folder)
        krow = QHBoxLayout()
        b_pick = QPushButton("Elegir carpeta...")
        b_reindex = QPushButton("Reindexar")
        b_openkb = QPushButton("Abrir")
        for b in (b_pick, b_reindex, b_openkb):
            krow.addWidget(b)
        kl.addLayout(krow)
        ll.addWidget(kb_box)

        call_box = QGroupBox("Documentos de esta llamada")
        cl = QVBoxLayout(call_box)
        self.extra_list = QListWidget()
        cl.addWidget(self.extra_list, 1)
        crow = QHBoxLayout()
        b_attach = QPushButton("Adjuntar...")
        b_paste = QPushButton("Pegar texto...")
        b_remove = QPushButton("Quitar")
        for b in (b_attach, b_paste, b_remove):
            crow.addWidget(b)
        cl.addLayout(crow)
        ll.addWidget(call_box, 1)
        b_new = QPushButton("🗑 Nueva preparacion")
        ll.addWidget(b_new)

        # Chat
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.addWidget(QLabel("<b>Chat de preparacion</b> — cuentale de que va la llamada y que debe estudiar"))
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        ml.addWidget(self.chat, 1)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(
            "Ej.: Mañana reunion con el gerente de planta de Acme. Quieren bajar consumo de vapor. "
            "Estudia la propuesta v2 y el caso de Cementos X. ¿Que me van a preguntar?  (Ctrl+Enter envia)")
        self.input.setMaximumHeight(110)
        ml.addWidget(self.input)
        irow = QHBoxLayout()
        self.btn_send = QPushButton("Enviar")
        self.btn_stop = QPushButton("Detener")
        self.btn_stop.setEnabled(False)
        irow.addStretch(1)
        irow.addWidget(self.btn_stop)
        irow.addWidget(self.btn_send)
        ml.addLayout(irow)

        # Guia + brief
        right = QWidget()
        rl = QVBoxLayout(right)
        grow = QHBoxLayout()
        grow.addWidget(QLabel("<b>Guia del copiloto</b>"))
        grow.addStretch(1)
        self.presets = QComboBox()
        self.presets.addItem("Plantillas...")
        for preset in PRESETS:
            lines = preset["texto"].count("\n") + 1
            self.presets.addItem(preset["nombre"] + (f"   ({lines} lineas)" if lines > 1 else ""))
        grow.addWidget(self.presets)
        rl.addLayout(grow)
        self.guide = QPlainTextEdit()
        self.guide.setPlaceholderText(
            "Quien eres y como quieres que responda. Ej.: Soy director comercial de Ecoeffy. "
            "Responde en tono cercano, con una cifra y una pregunta de vuelta. "
            "Pesa mas que el formato de serie; lo que no cambia es que no invente datos.")
        self.guide.setMaximumHeight(140)
        self.guide.setPlainText(self.prep.guide)
        rl.addWidget(self.guide)
        self.lbl_guide = QLabel()
        self.lbl_guide.setStyleSheet("color: gray;")
        rl.addWidget(self.lbl_guide)
        rl.addWidget(QLabel("<b>Brief</b> — el copiloto lo usa en cada respuesta. Puedes editarlo."))
        self.brief = QPlainTextEdit()
        self.brief.setPlaceholderText("Pulsa ✨ Armar brief cuando el chat tenga lo necesario "
                                      "(o directamente, a partir de los documentos).")
        rl.addWidget(self.brief, 1)
        brow = QHBoxLayout()
        self.btn_brief = QPushButton("✨ Armar brief")
        brow.addStretch(1)
        brow.addWidget(self.btn_brief)
        rl.addLayout(brow)

        split.addWidget(left)
        split.addWidget(mid)
        split.addWidget(right)
        split.setSizes([300, 500, 450])

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(split, 1)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        self.setCentralWidget(central)

        b_pick.clicked.connect(self._pick_folder)
        b_reindex.clicked.connect(self.reindex)
        b_openkb.clicked.connect(self._open_kb)
        b_attach.clicked.connect(self._attach)
        b_paste.clicked.connect(self._paste)
        b_remove.clicked.connect(self._remove)
        b_new.clicked.connect(self._new)
        self.btn_send.clicked.connect(self._send)
        self.btn_stop.clicked.connect(self._cancel_task)
        self.btn_brief.clicked.connect(self._build_brief)
        self.brief.textChanged.connect(self._brief_edited)
        self.guide.textChanged.connect(self._guide_edited)
        self.presets.activated.connect(self._use_preset)
        self._show_guide_name()
        QShortcut(QKeySequence("Ctrl+Return"), self.input, activated=self._send)
        self._mode_changed(self.mode.currentText())

    # --- fuentes --------------------------------------------------------------

    def _refresh_sources(self) -> None:
        folder = self.kb.folder
        n_docs = len([s for s in self.kb.sources() if s not in self.kb.extra_names()])
        self.lbl_folder.setText(f"{folder}\n{n_docs} documentos indexados"
                                + (f" · {len(self.kb.errors)} con error" if self.kb.errors else ""))
        self.lbl_folder.setToolTip("\n".join(self.kb.errors))
        self.extra_list.clear()
        self.extra_list.addItems(self.kb.extra_names())

    def reindex(self) -> None:
        def work():
            n = self.kb.load_folder(self.sig.progress.emit)
            return ("indexed", n)
        self._run(work)

    def _pick_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Carpeta de conocimiento", str(self.kb.folder or ""))
        if not path:
            return
        self.cfg.KB_DIR = path
        self.cfg.save()
        self.kb.folder = Path(path)
        self.reindex()

    def _open_kb(self) -> None:
        import os

        folder = self.kb.folder or self.cfg.kb_dir
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def _attach(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED))
        paths, _ = QFileDialog.getOpenFileNames(self, "Documentos para esta llamada", "",
                                                f"Documentos ({exts})")
        if not paths:
            return

        def work():
            errors = []
            for p in paths:
                self.sig.progress.emit(f"Leyendo {Path(p).name}...")
                try:
                    self.kb.add_file(Path(p))
                except Exception as exc:
                    errors.append(f"{Path(p).name}: {exc}")
            return ("attached", errors)
        self._run(work)

    def _paste(self) -> None:
        dlg = PasteDialog(self)
        if dlg.exec() != QDialog.Accepted or not dlg.text.toPlainText().strip():
            return
        name = dlg.name.text().strip() or f"texto {len(self.kb.extra_names()) + 1}"
        self.kb.add_text(name, dlg.text.toPlainText())
        save_prep(self.prep)
        self._refresh_sources()

    def _remove(self) -> None:
        item = self.extra_list.currentItem()
        if item:
            self.kb.remove(item.text())
            save_prep(self.prep)
            self._refresh_sources()

    def _new(self) -> None:
        self._cancel_task()
        self.prep.messages.clear()
        self.prep.brief = ""
        self.kb.clear_extra()
        self.brief.setPlainText("")
        save_prep(self.prep)
        self._refresh_sources()
        self._render_chat()
        self._set_status("Preparacion nueva.")

    # --- chat y brief ---------------------------------------------------------

    def _mode_changed(self, mode: str) -> None:
        self.prep.mode = mode
        if self.mode_box.currentText() != mode:
            self.mode_box.setCurrentText(mode)
        if mode in COPILOT_MODES:
            self.lbl_copilot.setText("En vivo, el copiloto respondera con este brief y tus documentos.")
        else:
            self.lbl_copilot.setText("En modo entrevista el copiloto no responde en vivo (seria soplarte "
                                     "en una evaluacion). Prepararte aqui antes si vale.")

    def _render_chat(self) -> None:
        parts = []
        for role, text in self.prep.messages:
            who = "🧑 **Tu**" if role == "user" else "🤖 **Asistente**"
            parts.append(f"{who}\n\n{text}")
        if self._streaming:
            parts.append(f"🤖 **Asistente**\n\n{self._streaming}")
        if not parts:
            parts.append("_Cuentale de que va la llamada: con quien, para que, que documentos importan. "
                         "Te hara preguntas, detectara huecos y propondra lo que te pueden preguntar._")
        self.chat.setMarkdown("\n\n---\n\n".join(parts))
        bar = self.chat.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _send(self) -> None:
        msg = self.input.toPlainText().strip()
        if not msg or self._busy:
            return
        self.input.clear()
        llm = make_llm(self.cfg)
        self._streaming = "…"
        self.prep.messages.append(("user", msg))  # para verlo ya; chat() lo vuelve a anadir
        self._render_chat()
        self.prep.messages.pop()

        def work():
            return ("chat", self.prep.chat(llm, msg, on_chunk=self.sig.chunk.emit, cancel=self._cancel))
        self._run(work)

    def _build_brief(self) -> None:
        if self._busy:
            return
        self.prep.brief = self.brief.toPlainText()
        llm = make_llm(self.cfg)
        self._brief_stream = True

        def work():
            return ("brief", self.prep.build_brief(llm, on_chunk=self.sig.chunk.emit, cancel=self._cancel))
        self._run(work)

    def _use_preset(self, index: int) -> None:
        if index <= 0:
            return
        preset = PRESETS[index - 1]
        self.prep.use_preset(preset)
        self.guide.blockSignals(True)
        self.guide.setPlainText(preset["texto"])
        self.guide.blockSignals(False)
        self.presets.setCurrentIndex(0)
        self._show_guide_name()
        save_prep(self.prep)

    def _guide_edited(self) -> None:
        self.prep.set_guide(self.guide.toPlainText())
        self._show_guide_name()

    def _show_guide_name(self) -> None:
        if not self.prep.guide.strip():
            text = "Sin guia: responde con el formato de serie."
        elif self.prep.guide_name:
            text = f"Plantilla: {self.prep.guide_name}. Se aplica ya, tambien a mitad de llamada."
        else:
            text = "Guia propia. Se aplica ya, tambien a mitad de llamada."
        self.lbl_guide.setText(text)

    def _brief_edited(self) -> None:
        if not self._busy:
            self.prep.brief = self.brief.toPlainText()

    def _on_chunk(self, acc: str) -> None:
        if getattr(self, "_brief_stream", False):
            self.brief.blockSignals(True)
            self.brief.setPlainText(acc)
            self.brief.blockSignals(False)
        else:
            self._streaming = acc
            self._render_chat()

    # --- tareas ---------------------------------------------------------------

    def _run(self, fn) -> None:
        self._busy = True
        self._cancel = threading.Event()
        for b in (self.btn_send, self.btn_brief):
            b.setEnabled(False)
        self.btn_stop.setEnabled(True)

        def work():
            try:
                self.sig.done.emit(fn())
            except Exception as exc:
                self.sig.failed.emit(str(exc))
                self.sig.done.emit(("error", None))

        threading.Thread(target=work, name="speak-prep", daemon=True).start()

    def _cancel_task(self) -> None:
        if self._busy and getattr(self, "_cancel", None):
            self._cancel.set()

    def _on_done(self, payload) -> None:
        kind, result = payload
        self._busy = False
        self._streaming = ""
        self._brief_stream = False
        for b in (self.btn_send, self.btn_brief):
            b.setEnabled(True)
        self.btn_stop.setEnabled(False)
        if kind == "indexed":
            self._set_status(f"Carpeta indexada: {result} documentos.")
        elif kind == "attached":
            self._set_status("Adjuntado." if not result else "⚠ " + " · ".join(result), error=bool(result))
        elif kind == "brief":
            self.brief.blockSignals(True)
            self.brief.setPlainText(self.prep.brief)
            self.brief.blockSignals(False)
            self._set_status("Brief listo. El copiloto lo usara en la llamada.")
        elif kind == "chat":
            self._set_status("")
        self._refresh_sources()
        self._render_chat()
        save_prep(self.prep)

    def _set_status(self, msg: str, error: bool = False) -> None:
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #c0392b;" if error else "")

    def closeEvent(self, event) -> None:
        self.prep.brief = self.brief.toPlainText()
        self.prep.set_guide(self.guide.toPlainText())
        save_prep(self.prep)
        super().closeEvent(event)
