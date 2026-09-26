"""Ventana de Notas de llamada (independiente del simulador).

Grabar exige marcar primero que los participantes aceptaron la grabacion.
Con "En vivo", mientras graba se ven la transcripcion, las preguntas y un
borrador de notas que se reescribe solo (`notes/live.py`). Al detener,
transcribe las dos pistas completas; luego "Generar notas" pasa la
transcripcion por el analizador. Tambien importa audios y transcripciones.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from PySide6.QtCore import QTimer
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
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..config import DATA_DIR, Config
from ..llm_client import make_llm
from ..notes.analyzer import MODES, generate_notes, heuristic_report, me_share
from ..notes.pipeline import ME, Transcript, load_any, parse_transcript_text, render
from ..transcriber import FasterWhisperSTT, make_stt
from .bridge import LiveSignals, TaskSignals


class NotesWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SPEAK — Notas de llamada")
        self.resize(1000, 780)
        self.recorder = None
        self.live_notes = None
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
        self._build()
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
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.btn_rec.clicked.connect(self._record)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_audio.clicked.connect(self._import_audio)
        self.btn_text.clicked.connect(self._import_text)
        self.btn_notes.clicked.connect(self._generate)
        self.btn_open.clicked.connect(self._open_folder)
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
            "_Borrador en vivo: aparece cuando haya algo de conversacion y se reescribe cada "
            f"~{self.cfg.LIVE_NOTES_INTERVAL} s. **✨ Actualizar notas** lo pide ya._"
            if llm else "_Notas en vivo desactivadas (LIVE_NOTES_INTERVAL=0)._")
        self.btn_notes.setText("✨ Actualizar notas")
        self.live_notes = LiveNotes(
            self._live_stt(), llm, self.mode.currentText(), self.cfg.NOTES_LANGUAGE,
            refresh_s=self.cfg.LIVE_NOTES_INTERVAL,
            on_transcript=self.live_sig.transcript.emit, on_notes=self.live_sig.notes.emit,
            on_status=self.live_sig.status.emit)
        self.live_notes.start()

    def _stop_live(self) -> None:
        live, self.live_notes = self.live_notes, None
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
        """En vivo siempre Whisper local; se reutiliza para la pasada final."""
        if self._local_stt is None:
            self._local_stt = make_stt(self.cfg)
        return self._local_stt

    def _mode_changed(self, mode: str) -> None:
        if self.live_notes:
            self.live_notes.mode = mode

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
            self.out_notes.setMarkdown("_Borrador en vivo_\n\n" + md)

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
        if isinstance(stt, FasterWhisperSTT):
            return self._live_stt()  # el mismo modelo ya cargado, no otro en memoria
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
