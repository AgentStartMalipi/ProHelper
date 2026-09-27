"""Ventana de Notas de llamada (independiente del simulador).

Grabar exige marcar primero que los participantes aceptaron la grabacion.
Con "En vivo", mientras graba se ven la transcripcion, las preguntas y un
borrador de notas que se reescribe solo (`notes/live.py`). Al detener,
transcribe las dos pistas completas; luego "Generar notas" pasa la
transcripcion por el analizador. Tambien importa audios y transcripciones.

El panel **Copiloto** (derecha) responde en vivo lo que pregunta el otro
lado, con el brief de **Preparar llamada** y la carpeta de conocimiento
(`notes/copilot.py`). F8 = responder ahora. Su pestana **Exploracion** dice
que falta saber y que preguntar (F9), antes o durante la llamada. 📎 anade
documentos o diagramas en cualquier momento, tambien en plena llamada.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR, Config
from ..knowledge import KnowledgeBase
from ..llm_client import make_llm
from ..notes.analyzer import MODES, generate_notes, heuristic_report, me_share
from ..knowledge import IMAGE_EXT, SUPPORTED
from ..notes.copilot import COPILOT_MODES, Copilot, Discovery, PrepSession, attach_file
from ..notes.pipeline import ME, THEM, Transcript, load_any, parse_transcript_text, render
from ..transcriber import FasterWhisperSTT, make_stt
from .bridge import LiveSignals, TaskSignals
from .prep_window import PasteDialog, PrepWindow, load_prep, save_prep


class NotesWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SPEAK — Notas de llamada")
        self.resize(1400, 820)
        self.recorder = None
        self.live_notes = None
        self.copilot: Copilot | None = None
        self.discovery: Discovery | None = None
        self.prep_window: PrepWindow | None = None
        self.kb = KnowledgeBase(cfg.kb_dir, DATA_DIR / "kb_cache.json")
        self.prep = PrepSession(self.kb, language=cfg.NOTES_LANGUAGE)
        load_prep(self.prep)
        self._local_stt = None
        self.folder: Path | None = None
        self.transcript: Transcript | None = None
        self._cancel: threading.Event | None = None
        self.sig = TaskSignals()
        self.sig.progress.connect(self._status)
        self.sig.chunk.connect(lambda md: self.out_notes.setMarkdown(md))
        self.sig.done.connect(self._task_done)
        self.sig.failed.connect(lambda m: self._status(f"⚠ {m}", error=True))
        self.live_sig = LiveSignals()
        self.live_sig.transcript.connect(self._live_transcript)
        self.live_sig.notes.connect(self._live_notes)
        self.live_sig.status.connect(lambda m: self._status(f"⚠ {m}", error=True))
        self.live_sig.answer.connect(self._render_copilot)
        self.live_sig.discovery.connect(self._render_discovery)
        self.live_sig.attached.connect(self._attached)
        self._build()
        if self.prep.mode in MODES:
            self.mode.setCurrentText(self.prep.mode)
        # La carpeta se indexa y el modelo de voz se carga de fondo: al pulsar
        # Grabar ya estan listos (antes eran ~10 s de espera al empezar).
        threading.Thread(target=self._load_kb, name="speak-kb", daemon=True).start()
        threading.Thread(target=self._preload_stt, name="speak-stt-preload", daemon=True).start()
        self._tick = QTimer(self)
        self._tick.setInterval(200)
        self._tick.timeout.connect(self._update_rec)

    def _build(self) -> None:
        central = QWidget()
        lay = QVBoxLayout(central)

        row = QHBoxLayout()
        row.addWidget(QLabel("Tipo:"))
        self.mode = QComboBox()
        self.mode.addItems(list(MODES))
        row.addWidget(self.mode)
        self.consent = QCheckBox("Todos los participantes saben y aceptaron que se grabe")
        row.addWidget(self.consent)
        row.addStretch(1)
        self.btn_prep = QPushButton("🧭 Preparar llamada")
        self.btn_prep.setToolTip("Mini chat previo: de que va la reunion, que estudiar, y un brief para el copiloto")
        self.on_top = QCheckBox("📌 Siempre visible")
        row.addWidget(self.btn_prep)
        row.addWidget(self.on_top)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_rec = QPushButton("● Grabar")
        self.live = QCheckBox("En vivo")
        self.live.setChecked(True)
        self.live.setToolTip(
            "Mientras grabas: transcripcion y preguntas al momento, y un borrador de notas\n"
            f"que se reescribe cada ~{self.cfg.LIVE_NOTES_INTERVAL} s. Al detener sale la version final.")
        self.btn_stop = QPushButton("■ Detener")
        self.btn_stop.setEnabled(False)
        self.btn_audio = QPushButton("Importar audio...")
        self.btn_text = QPushButton("Importar transcripcion...")
        self.btn_notes = QPushButton("✨ Generar notas")
        self.btn_notes.setEnabled(False)
        self.btn_open = QPushButton("Abrir carpeta")
        row2.addWidget(self.live)
        for b in (self.btn_rec, self.btn_stop, self.btn_audio, self.btn_text, self.btn_notes,
                  self.btn_open):
            row2.addWidget(b)
        row2.addStretch(1)
        lay.addLayout(row2)

        meters = QHBoxLayout()
        self.lbl_time = QLabel("00:00")
        self.me_level = QProgressBar()
        self.them_level = QProgressBar()
        for bar in (self.me_level, self.them_level):
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
        meters.addWidget(self.lbl_time)
        meters.addWidget(QLabel("Yo"))
        meters.addWidget(self.me_level)
        meters.addWidget(QLabel("Ellos"))
        meters.addWidget(self.them_level)
        lay.addLayout(meters)

        self.lbl_status = QLabel("Consejo: usa audifonos; asi tu microfono no capta al otro.")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        self.tabs = QTabWidget()
        self.out_transcript = QPlainTextEdit()
        self.out_transcript.setPlaceholderText(
            "La transcripcion aparece aqui. Tambien puedes pegar una (Nombre: texto) y "
            "pulsar Generar notas.")
        self.out_questions = QPlainTextEdit()
        self.out_questions.setReadOnly(True)
        self.out_notes = QTextBrowser()
        self.tabs.addTab(self.out_transcript, "Transcripcion")
        self.tabs.addTab(self.out_questions, "Preguntas detectadas")
        self.tabs.addTab(self.out_notes, "Notas")

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        files = QHBoxLayout()
        files.addWidget(QLabel("<b>Copiloto</b>"))
        files.addStretch(1)
        self.lbl_docs = QLabel()
        self.lbl_docs.setStyleSheet("color: gray;")
        files.addWidget(self.lbl_docs)
        self.btn_attach = QPushButton("📎 Adjuntar...")
        self.btn_attach.setToolTip("Documentos, archivos tecnicos o imagenes de diagramas; tambien en plena llamada")
        self.btn_paste = QPushButton("📋 Pegar...")
        files.addWidget(self.btn_attach)
        files.addWidget(self.btn_paste)
        sl.addLayout(files)
        self.side = QTabWidget()

        cop = QWidget()
        cl = QVBoxLayout(cop)
        cl.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addStretch(1)
        self.btn_answer = QPushButton("⚡ Responder ahora (F8)")
        self.btn_answer.setToolTip("Responde a lo ultimo que dijo el otro, aunque no parezca pregunta")
        self.btn_answer.setEnabled(False)
        head.addWidget(self.btn_answer)
        cl.addLayout(head)
        self.out_copilot = QTextBrowser()
        cl.addWidget(self.out_copilot, 1)

        exp = QWidget()
        el = QVBoxLayout(exp)
        el.setContentsMargins(0, 0, 0, 0)
        ehead = QHBoxLayout()
        self.lbl_discovery = QLabel()
        self.lbl_discovery.setStyleSheet("color: gray;")
        ehead.addWidget(self.lbl_discovery)
        ehead.addStretch(1)
        self.btn_discovery = QPushButton("🔍 ¿Que me falta? (F9)")
        self.btn_discovery.setToolTip("Que se sabe, que falta y las 3 proximas preguntas. Funciona antes y "
                                      "durante la llamada.")
        ehead.addWidget(self.btn_discovery)
        el.addLayout(ehead)
        self.out_discovery = QTextBrowser()
        el.addWidget(self.out_discovery, 1)

        self.side.addTab(cop, "💬 Respuestas")
        self.side.addTab(exp, "🔍 Exploracion")
        sl.addWidget(self.side, 1)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tabs)
        split.addWidget(side)
        split.setSizes([760, 640])
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self._copilot_idle()
        self._discovery_idle()
        self._show_docs()

        self.btn_rec.clicked.connect(self._record)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_audio.clicked.connect(self._import_audio)
        self.btn_text.clicked.connect(self._import_text)
        self.btn_notes.clicked.connect(self._generate)
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_prep.clicked.connect(self._open_prep)
        self.btn_answer.clicked.connect(self._answer_now)
        self.on_top.toggled.connect(self._toggle_on_top)
        QShortcut(QKeySequence("F8"), self, activated=self._answer_now)
        QShortcut(QKeySequence("F9"), self, activated=self._discover_now)
        self.btn_discovery.clicked.connect(self._discover_now)
        self.btn_attach.clicked.connect(self._attach)
        self.btn_paste.clicked.connect(self._paste)
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.out_transcript.textChanged.connect(
            lambda: self.btn_notes.setEnabled(bool(self.out_transcript.toPlainText().strip())))

    # --- grabar ---------------------------------------------------------------

    def _new_folder(self) -> Path:
        self.folder = DATA_DIR / "notes" / time.strftime("%Y%m%d-%H%M%S")
        self.folder.mkdir(parents=True, exist_ok=True)
        return self.folder

    def _record(self) -> None:
        if not self.consent.isChecked():
            self._status("Marca primero que los participantes aceptaron la grabacion.", error=True)
            return
        from ..notes.recorder import DualRecorder, RecorderError

        folder = self._new_folder()
        if self.live.isChecked():
            self._start_live()
        on_audio = self.live_notes.push if self.live_notes else None
        self.recorder = DualRecorder(folder, mic_device=self.cfg.mic_device, on_audio=on_audio)
        try:
            self.recorder.start()
        except RecorderError as exc:
            self.recorder = None
            self._stop_live()
            self._status(str(exc), error=True)
            return
        self.btn_rec.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.live.setEnabled(False)
        warn = " · ".join(self.recorder.warnings)
        self._status("● Grabando" + (" en vivo" if self.live_notes else "") + (f" — {warn}" if warn else ""))
        self._tick.start()

    # --- en vivo --------------------------------------------------------------

    def _start_live(self) -> None:
        from ..notes.live import LiveNotes

        llm = make_llm(self.cfg) if self.cfg.LIVE_NOTES_INTERVAL > 0 else None
        self.transcript = None
        self.out_transcript.clear()
        self.out_transcript.setReadOnly(True)
        self.out_questions.clear()
        self.out_notes.setMarkdown(
            "*Borrador en vivo: aparece cuando haya algo de conversacion y se reescribe cada "
            f"~{self.cfg.LIVE_NOTES_INTERVAL} s. **✨ Actualizar notas** lo pide ya.*"
            if llm else "*Notas en vivo desactivadas (LIVE_NOTES_INTERVAL=0).*")
        self.btn_notes.setText("✨ Actualizar notas")
        self.live_notes = LiveNotes(
            self._live_stt(), llm, self.mode.currentText(), self.cfg.NOTES_LANGUAGE,
            refresh_s=self.cfg.LIVE_NOTES_INTERVAL,
            on_transcript=self.live_sig.transcript.emit, on_notes=self.live_sig.notes.emit,
            on_status=self.live_sig.status.emit)
        self.live_notes.start()
        if self.cfg.COPILOT_ENABLED:
            live = self.live_notes
            self.copilot = Copilot(
                make_llm(self.cfg), self.kb, brief=lambda: self.prep.brief,
                snapshot=live.snapshot, now=live.now, pending=lambda: live.pending(THEM),
                me_spoke_since=lambda t: live.spoke_since(ME, t),
                mode=self.mode.currentText(), on_answer=self.live_sig.answer.emit,
                on_status=self.live_sig.status.emit, guide=lambda: self.prep.guide,
                quiet_s=self.cfg.COPILOT_QUIET_S)
            self.copilot.start()
            self.btn_answer.setEnabled(True)
            self._copilot_idle()
            self.discovery = self._make_discovery(live.snapshot, self.cfg.DISCOVERY_INTERVAL)
            self.discovery.start()

    def _stop_live(self) -> None:
        live, self.live_notes = self.live_notes, None
        copilot, self.copilot = self.copilot, None
        discovery, self.discovery = self.discovery, None
        if discovery is not None:
            discovery.stop()
            if self.folder and discovery.text:
                (self.folder / "exploracion.md").write_text(discovery.text + "\n", encoding="utf-8")
        self.btn_answer.setEnabled(False)
        if copilot is not None:
            copilot.stop()
            if self.folder and copilot.answers:
                (self.folder / "copilot.md").write_text(copilot.render_log() + "\n", encoding="utf-8")
        self.out_transcript.setReadOnly(False)
        self.btn_notes.setText("✨ Generar notas")
        if live is None:
            return
        tr = live.stop()
        if self.folder:
            if tr.segments:
                (self.folder / "transcript_live.md").write_text(render(tr) + "\n", encoding="utf-8")
            if live.notes:
                (self.folder / "notes_live.md").write_text(live.notes + "\n", encoding="utf-8")

    def _live_stt(self):
        """En vivo: Whisper local con el modelo liviano (STT_LIVE_MODEL)."""
        if self._local_stt is None:
            self._local_stt = make_stt(self.cfg, model=self.cfg.STT_LIVE_MODEL or self.cfg.STT_MODEL)
        return self._local_stt

    def _preload_stt(self) -> None:
        try:
            self._live_stt().warmup()
        except Exception as exc:
            self.live_sig.status.emit(f"modelo de voz: {exc}")

    def _mode_changed(self, mode: str) -> None:
        self.prep.mode = mode
        if self.live_notes:
            self.live_notes.mode = mode
        if self.copilot:
            self.copilot.mode = mode
        if self.discovery:
            self.discovery.mode = mode
        if not (self.copilot and self.copilot.answers):
            self._copilot_idle()
        if not (self.discovery and self.discovery.text):
            self._discovery_idle()

    # --- copiloto -------------------------------------------------------------

    def _load_kb(self) -> None:
        try:
            self.kb.load_folder()
        except Exception as exc:
            self.live_sig.status.emit(f"carpeta de conocimiento: {exc}")

    # --- exploracion y archivos -------------------------------------------------

    def _make_discovery(self, snapshot, interval: float) -> Discovery:
        return Discovery(
            make_llm(self.cfg), self.kb, brief=lambda: self.prep.brief, snapshot=snapshot,
            mode=self.mode.currentText(), language=self.cfg.NOTES_LANGUAGE,
            guide=lambda: self.prep.guide, interval_s=interval,
            on_update=self.live_sig.discovery.emit, on_status=self.live_sig.status.emit)

    def _discover_now(self) -> None:
        if self.mode.currentText() not in COPILOT_MODES:
            self._status("En modo entrevista la exploracion en vivo esta apagada.", error=True)
            return
        self.side.setCurrentIndex(1)
        self.lbl_discovery.setText("Analizando...")
        if self.discovery:  # en llamada: el hilo en vivo la corre ya
            self.discovery.run_now()
            return
        # Sin llamada en vivo: con la transcripcion cargada, si hay, o solo con
        # el brief y los documentos (¿alcanza lo que me dieron?).
        tr = self.transcript
        one_off = self._make_discovery(lambda: tr, 0)
        threading.Thread(target=one_off.run_once, args=(tr,), name="speak-discovery-now",
                         daemon=True).start()

    def _discovery_idle(self) -> None:
        mode = self.mode.currentText()
        if mode not in COPILOT_MODES:
            msg = "*En modo **entrevista** la exploracion en vivo esta apagada.*"
        else:
            auto = (f"se actualiza sola cada ~{self.cfg.DISCOVERY_INTERVAL} s"
                    if self.cfg.DISCOVERY_INTERVAL > 0 else "se actualiza con el boton")
            msg = ("**🔍 ¿Que me falta?** *revisa lo que se sabe (conversacion, brief y documentos), "
                   "dice si alcanza y te da las 3 proximas preguntas. Antes de la llamada sirve para ver si "
                   f"el contexto que te dieron es suficiente; grabando en vivo {auto}.*")
        self.out_discovery.setMarkdown(msg)
        self.lbl_discovery.setText("")

    def _render_discovery(self, md: str, done: bool) -> None:
        self.out_discovery.setMarkdown(md)
        self.lbl_discovery.setText(time.strftime("Actualizado %H:%M:%S") if done else "Escribiendo...")

    def _show_docs(self) -> None:
        extra = self.kb.extra_names()
        self.lbl_docs.setText(f"{len(extra)} de la llamada · {len(self.kb.sources()) - len(extra)} de la carpeta")
        self.lbl_docs.setToolTip("\n".join(extra))

    def _attach(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED | IMAGE_EXT))
        paths, _ = QFileDialog.getOpenFileNames(self, "Adjuntar a esta llamada", "", f"Documentos ({exts})")
        if not paths:
            return
        mode, lang = self.mode.currentText(), self.cfg.NOTES_LANGUAGE
        slow = any(Path(p).suffix.lower() in IMAGE_EXT for p in paths)
        self._status("Leyendo archivos" + (" (las imagenes las describe Claude, ~10 s)..." if slow else "..."))

        def work():
            done, errors = [], []
            for p in paths:
                try:
                    done.append(attach_file(self.kb, Path(p), lambda: make_llm(self.cfg), mode, lang))
                except Exception as exc:
                    errors.append(f"{Path(p).name}: {exc}")
            msg = ("📎 Anadido: " + ", ".join(done)) if done else ""
            if errors:
                msg += (" · " if msg else "") + "⚠ " + " · ".join(errors)
            self.live_sig.attached.emit(msg)

        threading.Thread(target=work, name="speak-attach", daemon=True).start()

    def _paste(self) -> None:
        dlg = PasteDialog(self)
        if dlg.exec() != PasteDialog.Accepted or not dlg.text.toPlainText().strip():
            return
        name = dlg.name.text().strip() or f"texto {len(self.kb.extra_names()) + 1}"
        self.kb.add_text(name, dlg.text.toPlainText())
        self._attached(f"📋 Anadido: {name}")

    def _attached(self, msg: str) -> None:
        save_prep(self.prep)
        self._show_docs()
        self._status(msg, error="⚠" in msg)
        if self.prep_window:
            self.prep_window._refresh_sources()
        if self.discovery and "Anadido" in msg:
            self.discovery.run_now()  # informacion nueva: ¿que cambia?

    def _open_prep(self) -> None:
        if self.prep_window is None:
            self.prep_window = PrepWindow(self.cfg, self.prep, self.mode)
        self.prep_window.show()
        self.prep_window.raise_()
        self.prep_window.activateWindow()

    def _toggle_on_top(self, on: bool) -> None:
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        self.show()

    def _answer_now(self) -> None:
        if self.copilot:
            self.copilot.answer_now()
        else:
            self._status("El copiloto funciona mientras grabas en vivo.", error=True)

    def _copilot_idle(self) -> None:
        mode = self.mode.currentText()
        if not self.cfg.COPILOT_ENABLED:
            msg = "*Copiloto desactivado (COPILOT_ENABLED=false en speak/.env).*"
        elif mode not in COPILOT_MODES:
            msg = ("*En modo **entrevista** el copiloto no responde en vivo: seria soplarte en una "
                   "evaluacion. Para practicar esta el simulador.*")
        else:
            brief = "con tu brief" if self.prep.brief.strip() else "sin brief (🧭 Preparar llamada)"
            n = len(self.kb.sources())
            guide = self.prep.guide_name or ("guia propia" if self.prep.guide.strip() else "sin guia")
            msg = (f"*Cuando el otro lado haga una pregunta, aqui aparece que responder, {brief} y "
                   f"{n} documentos. Guia: **{guide}**. Funciona grabando **En vivo**. "
                   f"**F8** responde a lo ultimo que dijo.*")
        self.out_copilot.setMarkdown(msg)

    def _render_copilot(self, _answer=None) -> None:
        if not self.copilot:
            return
        parts = []
        for a in reversed(self.copilot.answers[-15:]):
            state = "" if a.done else " ⏳"
            parts.append(f"**[{a.at // 60:02.0f}:{a.at % 60:02.0f}] ❓ {a.question}**{state}\n\n"
                         f"{a.text or '…'}")
        self.out_copilot.setMarkdown("\n\n---\n\n".join(parts))
        self.out_copilot.verticalScrollBar().setValue(0)

    def _live_transcript(self, tr: Transcript) -> None:
        if not self.live_notes:
            return
        bar = self.out_transcript.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        keep = bar.value()
        self.out_transcript.setPlainText(render(tr))
        bar.setValue(bar.maximum() if at_end else keep)
        report = heuristic_report(tr)
        if any(s.speaker == ME for s in tr.segments):
            report += f"\n\nVas hablando el {me_share(tr):.0%} (por palabras)."
        self.out_questions.setPlainText(report)

    def _live_notes(self, md: str) -> None:
        if self.live_notes:
            self.out_notes.setMarkdown("*Borrador en vivo_\n\n" + md)

    def _update_rec(self) -> None:
        if not self.recorder:
            return
        t = int(self.recorder.elapsed)
        self.lbl_time.setText(f"{t // 60:02d}:{t % 60:02d}")
        self.me_level.setValue(min(100, int(self.recorder.levels["me"] * 600)))
        self.them_level.setValue(min(100, int(self.recorder.levels["them"] * 600)))

    def _stop(self) -> None:
        if not self.recorder:
            return
        self._tick.stop()
        folder = self.recorder.stop()
        self.recorder = None
        self._stop_live()
        self.btn_rec.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.live.setEnabled(True)
        self._run(lambda: load_any(folder, self._stt, self.sig.progress.emit), "transcript")

    # --- importar -------------------------------------------------------------

    def _import_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Audio de la llamada", "", "Audio (*.wav *.mp3 *.m4a *.mp4 *.ogg *.webm *.flac)")
        if path:
            self._new_folder()
            self._run(lambda: load_any(Path(path), self._stt, self.sig.progress.emit), "transcript")

    def _import_text(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Transcripcion", "", "Transcripcion (*.txt *.md *.vtt)")
        if path:
            self._new_folder()
            self._show_transcript(load_any(Path(path), self._stt))

    def _stt(self):
        stt = make_stt(self.cfg, for_files=True)
        live = self._local_stt
        if (isinstance(stt, FasterWhisperSTT) and live is not None
                and getattr(live, "model_name", None) == stt.model_name):
            return live  # el mismo modelo ya cargado, no otro en memoria
        return stt

    # --- notas ----------------------------------------------------------------

    def _generate(self) -> None:
        if self.live_notes:
            self.live_notes.refresh_now()
            self.tabs.setCurrentWidget(self.out_notes)
            return
        text = self.out_transcript.toPlainText().strip()
        if not text:
            return
        # Lo que este en el cuadro manda (pudiste corregir nombres a mano).
        tr = parse_transcript_text(text, source="editor")
        if self.transcript and render(self.transcript) == text:
            tr = self.transcript
        if self.folder is None:
            self._new_folder()
        mode = self.mode.currentText()
        self.tabs.setCurrentWidget(self.out_notes)
        self.out_notes.clear()
        llm = make_llm(self.cfg)
        self._run(lambda: generate_notes(llm, tr, mode, self.cfg.NOTES_LANGUAGE,
                                         on_chunk=self.sig.chunk.emit), "notes")

    # --- tareas ---------------------------------------------------------------

    def _run(self, fn, kind: str) -> None:
        self._set_busy(True)

        def work():
            try:
                self.sig.done.emit((kind, fn()))
            except Exception as exc:
                self.sig.failed.emit(str(exc))
            finally:
                self.sig.progress.emit("")

        threading.Thread(target=work, name=f"speak-notes-{kind}", daemon=True).start()

    def _task_done(self, payload) -> None:
        kind, result = payload
        self._set_busy(False)
        if kind == "transcript":
            self._show_transcript(result)
        elif kind == "notes":
            self.out_notes.setMarkdown(result)
            if self.folder:
                (self.folder / "notes.md").write_text(result + "\n", encoding="utf-8")
                self._status(f"Notas guardadas en {self.folder / 'notes.md'}")

    def _show_transcript(self, tr: Transcript) -> None:
        self.transcript = tr
        text = render(tr)
        self.out_transcript.setPlainText(text)
        report = heuristic_report(tr)
        if any(s.speaker == ME for s in tr.segments):
            report += f"\n\nHablaste el {me_share(tr):.0%} (por palabras)."
        self.out_questions.setPlainText(report)
        if self.folder:
            (self.folder / "transcript.md").write_text(text + "\n", encoding="utf-8")
        self._status(f"Transcripcion lista: {len(tr.segments)} segmentos, hablantes: "
                     f"{', '.join(tr.speakers()) or '—'}")
        self.tabs.setCurrentWidget(self.out_transcript)

    def _set_busy(self, busy: bool) -> None:
        for b in (self.btn_rec, self.btn_audio, self.btn_text, self.btn_notes):
            b.setEnabled(not busy)
        if not busy:
            self.btn_notes.setEnabled(bool(self.out_transcript.toPlainText().strip()))

    def _status(self, msg: str, error: bool = False) -> None:
        if msg or error:
            self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #c0392b;" if error else "")

    def _open_folder(self) -> None:
        target = self.folder or (DATA_DIR / "notes")
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))

    def closeEvent(self, event) -> None:
        if self.recorder:
            self._stop()
        super().closeEvent(event)
