"""Ventana del simulador.

Izquierda: tu perfil (tipo de entrevista, puesto, CV, descripcion del
puesto) y la opcion de practicar una pregunta propia.
Derecha, de arriba a abajo: lo que dice el entrevistador y el tipo de
pregunta, tu respuesta transcrita en vivo, y (solo despues de responder) el
feedback, el QUICK ANSWER y el DETAILED ANSWER.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR, Config
from ..simulator import Phase, Simulator
from .banner import ModeBanner
from .bridge import SimSignals
from .settings_dialog import SettingsDialog

PROFILE_FILE = DATA_DIR / "profile.json"

_PHASE_LABEL = {
    "IDLE": "Detenido",
    "LOADING": "Cargando...",
    "ASKING": "Entrevistador hablando",
    "LISTENING": "Escuchandote",
    "CLARIFYING": "Aclarando",
    "EVALUATING": "Evaluando",
    "REVIEW": "Revision",
    "PAUSED": "En pausa",
}


def _box(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(6, 6, 6, 6)
    lay.addWidget(widget)
    return box


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, sim_factory) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SPEAK · 🎓 Práctica de entrevista")
        self.resize(1280, 860)
        self.signals = SimSignals()
        self.sim: Simulator = sim_factory(self.signals.listener())
        self._notes_window = None
        self._pending_eval: tuple[dict, bool] | None = None
        self._build()
        self._wire()
        self._load_profile()
        self._on_phase("IDLE")

    # --- construccion ---------------------------------------------------------

    def _build(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        self.banner = ModeBanner()
        root.addWidget(self.banner)

        bar = QHBoxLayout()
        self.btn_start = QPushButton("▶ Start Listening")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_done = QPushButton("✔ Terminé (F9)")
        self.btn_next = QPushButton("→ Siguiente pregunta")
        self.btn_follow = QPushButton("↳ Repregunta")
        self.btn_regen = QPushButton("⟳ Regenerate")
        self.btn_clear = QPushButton("🗑 Clear Context")
        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_notes = QPushButton("📞 Ir a Llamadas")
        for b in (self.btn_start, self.btn_pause, self.btn_done, self.btn_next, self.btn_follow,
                  self.btn_regen, self.btn_clear, self.btn_settings):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.btn_notes)
        root.addLayout(bar)

        status = QHBoxLayout()
        self.lbl_phase = QLabel()
        self.lbl_phase.setStyleSheet("font-weight: bold;")
        self.lbl_turn = QLabel("")
        self.lbl_turn.setStyleSheet("color: gray;")
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedWidth(160)
        self.level.setFixedHeight(10)
        self.lbl_status = QLabel("")
        status.addWidget(self.lbl_phase)
        status.addWidget(self.lbl_turn)
        status.addWidget(QLabel("Mic:"))
        status.addWidget(self.level)
        status.addWidget(self.lbl_status, 1)
        root.addLayout(status)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._profile_panel())
        split.addWidget(self._session_panel())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)
        self.setCentralWidget(central)

    def _interview_box(self) -> QGroupBox:
        """Tu .md de entrevista: el entrevistador y el evaluador lo usan, y se
        relee solo cuando lo editas."""
        box = QGroupBox("Tu perfil de entrevista")
        lay = QVBoxLayout(box)
        self.lbl_iv = QLabel("")
        self.lbl_iv.setWordWrap(True)
        lay.addWidget(self.lbl_iv)
        row = QHBoxLayout()
        pick = QPushButton("Elegir .md...")
        pick.clicked.connect(self._pick_interview_file)
        open_btn = QPushButton("Abrir")
        open_btn.clicked.connect(self._open_interview_file)
        row.addWidget(pick)
        row.addWidget(open_btn)
        lay.addLayout(row)
        form = QFormLayout()
        self.in_target = QComboBox()
        self.in_target.currentTextChanged.connect(self._target_changed)
        form.addRow("Vacante", self.in_target)
        lay.addLayout(form)
        return box

    def _profile_panel(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._interview_box())
        form = QFormLayout()
        self.in_type = QComboBox()
        self.in_type.addItems(["Mixta", "Behavioral", "Coding", "System design", "Technical"])
        self.in_lang = QComboBox()
        self.in_lang.addItems(["en", "es"])
        self.in_role = QLineEdit()
        self.in_role.setPlaceholderText("p. ej. SDE II")
        self.in_company = QLineEdit()
        self.in_company.setPlaceholderText("p. ej. Amazon")
        self.in_seniority = QLineEdit()
        form.addRow("Tipo", self.in_type)
        form.addRow("Idioma", self.in_lang)
        form.addRow("Puesto", self.in_role)
        form.addRow("Empresa", self.in_company)
        form.addRow("Seniority", self.in_seniority)
        lay.addLayout(form)

        self.in_notes = QPlainTextEdit()
        self.in_notes.setPlaceholderText("Sobre ti: stack, proyectos clave, que quieres reforzar...")
        self.in_notes.setMaximumHeight(80)
        lay.addWidget(QLabel("Notas del candidato"))
        lay.addWidget(self.in_notes)

        cv_row = QHBoxLayout()
        cv_row.addWidget(QLabel("CV"))
        btn_cv = QPushButton("Cargar .txt/.md...")
        btn_cv.clicked.connect(self._load_cv)
        cv_row.addStretch(1)
        cv_row.addWidget(btn_cv)
        lay.addLayout(cv_row)
        self.in_cv = QPlainTextEdit()
        self.in_cv.setPlaceholderText("Pega aqui tu CV (texto)")
        lay.addWidget(self.in_cv, 2)
        lay.addWidget(QLabel("Descripcion del puesto"))
        self.in_jd = QPlainTextEdit()
        self.in_jd.setPlaceholderText("Pega aqui la descripcion del puesto")
        lay.addWidget(self.in_jd, 2)

        own = QGroupBox("Practicar una pregunta propia")
        own_lay = QVBoxLayout(own)
        self.in_own = QLineEdit()
        self.in_own.setPlaceholderText("Escribe una pregunta y pulsa Usar")
        self.in_own.returnPressed.connect(self._use_own_question)
        btn_own = QPushButton("Usar esta pregunta")
        btn_own.clicked.connect(self._use_own_question)
        own_lay.addWidget(self.in_own)
        own_lay.addWidget(btn_own)
        lay.addWidget(own)
        return w

    def _session_panel(self) -> QWidget:
        split = QSplitter(Qt.Vertical)
        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0)
        self.out_interviewer = QTextBrowser()
        self.out_interviewer.setStyleSheet("font-size: 15px;")
        self.lbl_qtype = QLabel("Question type: —")
        self.lbl_qtype.setStyleSheet("font-weight: bold;")
        top_lay.addWidget(_box("Interviewer", self.out_interviewer))
        top_lay.addWidget(self.lbl_qtype)
        split.addWidget(top)

        self.out_transcript = QPlainTextEdit()
        self.out_transcript.setReadOnly(True)
        split.addWidget(_box("Tu respuesta (live transcript)", self.out_transcript))

        self.out_feedback = QTextBrowser()
        self.out_quick = QTextBrowser()
        self.out_detailed = QTextBrowser()
        self.out_detailed.setOpenExternalLinks(True)
        row = QSplitter(Qt.Horizontal)
        row.addWidget(_box("Feedback", self.out_feedback))
        row.addWidget(_box("Suggested approach (QUICK ANSWER)", self.out_quick))
        split.addWidget(row)
        split.addWidget(_box("Detailed answer", self.out_detailed))
        split.setSizes([150, 120, 200, 320])
        return split

    def _wire(self) -> None:
        s = self.signals
        s.phase.connect(self._on_phase)
        s.turn_state.connect(lambda st: self.lbl_turn.setText(f"[{st}]"))
        s.level.connect(self._on_level)
        s.interviewer.connect(self._on_interviewer)
        s.question.connect(lambda text, qtype: self.lbl_qtype.setText(f"Question type: {qtype}"))
        s.transcript.connect(self._on_transcript)
        s.clarification.connect(self._on_clarification)
        s.evaluation.connect(self._queue_eval)
        s.status.connect(self.lbl_status.setText)
        s.error.connect(self._on_error)

        self.btn_start.clicked.connect(self._start)
        self.btn_pause.clicked.connect(self._toggle_pause)
        self.btn_done.clicked.connect(self.sim.done_answering)
        self.btn_next.clicked.connect(self._next)
        self.btn_follow.clicked.connect(self.sim.follow_up)
        self.btn_regen.clicked.connect(self.sim.regenerate)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_settings.clicked.connect(self._settings)
        self.btn_notes.clicked.connect(self._open_notes)
        QShortcut(QKeySequence("F9"), self, activated=self.sim.done_answering)

        # El streaming llega token a token; se repinta a ~15 fps como mucho.
        self._eval_timer = QTimer(self)
        self._eval_timer.setInterval(66)
        self._eval_timer.timeout.connect(self._flush_eval)
        self._eval_timer.start()

    # --- perfil ---------------------------------------------------------------

    def _sync_profile(self) -> None:
        p = self.sim.ctx.profile
        p.interview_type = self.in_type.currentText()
        p.language = self.in_lang.currentText()
        p.role = self.in_role.text().strip()
        p.company = self.in_company.text().strip()
        p.seniority = self.in_seniority.text().strip()
        p.candidate_info = self.in_notes.toPlainText().strip()
        p.cv = self.in_cv.toPlainText().strip()
        p.job_description = self.in_jd.toPlainText().strip()
        self.sim.speaker.culture = "es-ES" if p.language == "es" else "en-US"
        try:
            self.sim.ctx.save_profile(PROFILE_FILE)
        except OSError:
            pass

    def _load_profile(self) -> None:
        self.sim.ctx.load_profile(PROFILE_FILE)
        p = self.sim.ctx.profile
        self.in_type.setCurrentText(p.interview_type)
        self.in_lang.setCurrentText(p.language or "en")
        self.in_role.setText(p.role)
        self.in_company.setText(p.company)
        self.in_seniority.setText(p.seniority)
        self.in_notes.setPlainText(p.candidate_info)
        self.in_cv.setPlainText(p.cv)
        self.in_jd.setPlainText(p.job_description)
        self._attach_interview(self.cfg.INTERVIEW_PROFILE)

    # --- perfil de entrevista (.md) -------------------------------------------

    def _attach_interview(self, path: str) -> None:
        from ..interview_profile import load

        self.sim.ctx.interview = load(path) if path else None
        self._fill_targets()
        # Lo editas mientras practicas: se revisa cada pocos segundos y, si
        # cambio, se actualizan las vacantes (el texto se relee en cada pregunta).
        if not hasattr(self, "_iv_timer"):
            self._iv_timer = QTimer(self)
            self._iv_timer.setInterval(4000)
            self._iv_timer.timeout.connect(self._check_interview_file)
            self._iv_timer.start()

    def _check_interview_file(self) -> None:
        iv = self.sim.ctx.interview
        if iv is not None and iv.refresh():
            self._fill_targets()

    def _fill_targets(self) -> None:
        iv = self.sim.ctx.interview
        keep = self.sim.ctx.profile.target
        self.in_target.blockSignals(True)
        self.in_target.clear()
        self.in_target.addItem("(general: el entrevistador elige)")
        if iv is not None and iv.loaded:
            self.in_target.addItems([t.label for t in iv.targets])
            self.lbl_iv.setText(f"✔ {iv.path.name} · {len(iv.text):,} caracteres · "
                                f"{len(iv.targets)} vacantes. Se relee al editarlo.")
            self.lbl_iv.setStyleSheet("")
        else:
            missing = iv is not None and iv.path is not None
            self.lbl_iv.setText("⚠ No encuentro el archivo." if missing else
                                "Sin perfil: elige tu .md con hechos, reglas e historias STAR.")
            self.lbl_iv.setStyleSheet("color: #e67e22;" if missing else "color: gray;")
        i = self.in_target.findText(keep) if keep else 0
        self.in_target.setCurrentIndex(max(0, i))
        self.in_target.blockSignals(False)

    def _target_changed(self, label: str) -> None:
        iv = self.sim.ctx.interview
        t = iv.target(label) if iv is not None else None
        self.sim.ctx.profile.target = t.label if t else ""
        if t:
            self.in_company.setText(t.label.split(" — ")[0])
            self.in_role.setText(t.role)

    def _pick_interview_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Tu perfil de entrevista", "", "Markdown (*.md *.txt)")
        if path:
            from ..config import set_env_value

            self.cfg.INTERVIEW_PROFILE = path
            set_env_value("INTERVIEW_PROFILE", path)
            self._attach_interview(path)

    def _open_interview_file(self) -> None:
        iv = self.sim.ctx.interview
        if iv is not None and iv.path is not None and iv.path.exists():
            os.startfile(str(iv.path))

    def _load_cv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "CV en texto", "", "Texto (*.txt *.md)")
        if path:
            self.in_cv.setPlainText(Path(path).read_text(encoding="utf-8", errors="replace"))

    # --- acciones -------------------------------------------------------------

    def _start(self) -> None:
        self._sync_profile()
        if self.sim.phase == Phase.PAUSED:
            self.sim.resume()
        else:
            self.sim.start()

    def _next(self) -> None:
        self._sync_profile()
        if self.sim.phase == Phase.IDLE:
            self.sim.start()
        else:
            self.sim.next_question()

    def _use_own_question(self) -> None:
        q = self.in_own.text().strip()
        if not q:
            return
        self._sync_profile()
        if self.sim.phase == Phase.IDLE:
            QMessageBox.information(self, "SPEAK", "Pulsa primero Start Listening.")
            return
        self.sim.next_question(q)
        self.in_own.clear()

    def _toggle_pause(self) -> None:
        if self.sim.phase == Phase.PAUSED:
            self.sim.resume()
        else:
            self.sim.pause()

    def _clear(self) -> None:
        self.sim.clear_context()
        for w in (self.out_interviewer, self.out_feedback, self.out_quick, self.out_detailed):
            w.clear()
        self.out_transcript.clear()
        self.lbl_qtype.setText("Question type: —")

    def _settings(self) -> None:
        SettingsDialog(self.cfg, self).exec()

    def _open_notes(self) -> None:
        # La misma ventana que abre la pantalla de inicio: nunca dos Llamadas.
        from .home_window import open_calls

        self._notes_window = open_calls(self.cfg)

    # --- slots ----------------------------------------------------------------

    def _on_phase(self, phase: str) -> None:
        self.lbl_phase.setText(_PHASE_LABEL.get(phase, phase))
        self.banner.set_state(
            "practice", "🎓 PRÁCTICA DE ENTREVISTA — la app es el entrevistador; nada de esto es una "
            f"llamada real  ·  {_PHASE_LABEL.get(phase, phase)}")
        idle = phase == "IDLE"
        self.btn_start.setEnabled(phase in ("IDLE", "PAUSED"))
        self.btn_start.setText("▶ Reanudar" if phase == "PAUSED" else "▶ Start Listening")
        self.btn_pause.setEnabled(not idle and phase != "LOADING")
        self.btn_pause.setText("▶ Reanudar" if phase == "PAUSED" else "⏸ Pause")
        self.btn_done.setEnabled(phase == "LISTENING")
        self.btn_next.setEnabled(phase not in ("LOADING",))
        self.btn_follow.setEnabled(phase == "REVIEW")
        self.btn_regen.setEnabled(phase in ("REVIEW", "EVALUATING"))

    def _on_level(self, rms: float, speaking: bool) -> None:
        self.level.setValue(min(100, int(rms * 600)))

    def _on_interviewer(self, text: str, final: bool) -> None:
        if not final and not text:
            self.out_interviewer.clear()
            return
        self.out_interviewer.setPlainText(text)

    def _on_transcript(self, text: str) -> None:
        self.out_transcript.setPlainText(text)
        self.out_transcript.verticalScrollBar().setValue(
            self.out_transcript.verticalScrollBar().maximum())

    def _on_clarification(self, asked: str, reply: str) -> None:
        self.out_interviewer.append(f"\n— Tú: {asked}\n— Entrevistador: {reply}")

    def _queue_eval(self, sections: dict, final: bool) -> None:
        self._pending_eval = (sections, final)
        if final or not sections:
            self._flush_eval()

    def _flush_eval(self) -> None:
        if self._pending_eval is None:
            return
        sections, _ = self._pending_eval
        self._pending_eval = None
        self.out_feedback.setMarkdown(sections.get("FEEDBACK", ""))
        self.out_quick.setMarkdown(sections.get("QUICK ANSWER", ""))
        self.out_detailed.setMarkdown(sections.get("DETAILED ANSWER", ""))

    def _on_error(self, msg: str) -> None:
        self.lbl_status.setText(f"⚠ {msg}")
        self.lbl_status.setStyleSheet("color: #c0392b;")
        QTimer.singleShot(8000, lambda: self.lbl_status.setStyleSheet(""))

    def closeEvent(self, event) -> None:
        try:
            self._sync_profile()
        finally:
            self.sim.shutdown()
        super().closeEvent(event)
