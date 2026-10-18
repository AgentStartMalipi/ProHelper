"""Ventana de Notas de llamada (independiente del simulador).

Grabar exige marcar primero que los participantes aceptaron la grabacion.
Con "En vivo", mientras graba se ven la transcripcion, las preguntas y un
borrador de notas que se reescribe solo (`notes/live.py`). Al detener,
transcribe las dos pistas completas; luego "Generar notas" pasa la
transcripcion por el analizador. Tambien importa audios y transcripciones.

El panel **Copiloto** (derecha) responde en vivo lo que pregunta el otro
lado, con el brief de **Preparar llamada** y la carpeta de conocimiento
(`notes/copilot.py`). F8 o Alt+R = responder ahora. Su pestana **Exploracion** dice
que falta saber y que preguntar (F9), antes o durante la llamada. 📎 anade
documentos o diagramas en cualquier momento, tambien en plena llamada.
"""

from __future__ import annotations

import os
import re
from html import escape as _html_escape
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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
from ..knowledge import IMAGE_EXT, SUPPORTED, KnowledgeBase
from ..llm_client import make_llm
from ..notes.analyzer import MODES, generate_notes, heuristic_report, me_share
from ..notes.copilot import COPILOT_MODES, Copilot, Discovery, PrepSession, attach_file, split_warning
from ..notes.editor import clean_code, editor_html, said_progress
from ..notes.instant import PreparedIndex
from ..notes.pipeline import (ME, THEM, Transcript, _fmt, discard_recording_audio, load_any,
                              parse_transcript_text, render)
from ..transcriber import FasterWhisperSTT, make_stt
from .banner import ModeBanner
from .bridge import LiveSignals, TaskSignals
from .prep_window import PasteDialog, PrepWindow, active_label, load_prep, save_prep


def _reading_lines(text: str, reflow: bool = False) -> list[str]:
    """Una idea por linea, para leer en voz alta. Si ya viene en lineas (el LLM)
    se respetan; un parrafo se parte por frases. `reflow`: unir siempre y partir
    por frases (la preparada viene cortada a ~90 columnas, a mitad de frase)."""
    text = re.sub(r"\*\*Respuesta:\*\*\s*", "", text or "")
    lines = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if reflow or len(lines) <= 1:
        lines = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"(\[⚠])", " ".join(lines))
    return [part for ln in lines if ln.strip() for part in _split_long(ln.strip())]


_LONG_WORDS = 16  # practica 2026-10-17: con 20 aun se perdia a media frase
# Pausas naturales donde partir una linea larga (la pausa queda al final de la linea).
_PAUSE_RE = re.compile(r"(?<=;)\s+|\s+(?=— )|(?<=,)\s+(?=(?:so|but|which|since|then|and then|so that|"
                       r"rather than|not|pero|así que|entonces|porque|que)\b)", re.I)


def _split_long(line: str) -> list[str]:
    """Parte una linea de mas de ~20 palabras en su pausa natural mas centrada
    (sin cambiar palabras). Medido 2026-10-12: el LLM daba lineas de 30-40
    palabras aunque el prompt pide ~15."""
    words = line.split()
    if len(words) <= _LONG_WORDS:
        return [line]
    cuts = [m.start() for m in _PAUSE_RE.finditer(line)]
    if not cuts:
        return [line]
    mid = len(line) / 2
    cut = min(cuts, key=lambda c: abs(c - mid))
    head, tail = line[:cut].strip(), line[cut:].strip()
    if len(head.split()) < 4 or len(tail.split()) < 4:  # trozo demasiado corto: no compensa
        return [line]
    return _split_long(head) + _split_long(tail)


def _answer_block(title: str, key: str, text: str, purpose: str, reflow: bool = False) -> str:
    head = f"**{title}**" + (f" · `{key}`" if key else "")
    note, text = split_warning(text)
    if note:  # aviso para Yo, aparte: no es parte de lo que se lee
        head += f"  \n*{note} — aviso para ti, no lo leas*"
    lines = _reading_lines(text, reflow)
    said = [ln for ln in lines if not _SOURCE_RE.match(ln)]
    if said:  # entre comillas solo lo que se dice; la Fuente queda fuera
        lines = [ln for ln in lines if _SOURCE_RE.match(ln)]
        said[0] = f"“{said[0]}"
        said[-1] = f"{said[-1]}”"
        lines = said + lines
    lines = lines or ["…"]
    # "  \n" = salto de linea dentro del mismo bloque (sin parrafos)
    return f"{head}  \n" + "  \n".join(lines) + f"  \n*{purpose}*"


_SOURCE_RE = re.compile(r"^(?:Fuente|Source)s?:", re.I)


def _pretty_hotkey(spec: str) -> str:
    """'alt+r' -> 'Alt+R' (lo que se muestra y lo que entiende QKeySequence)."""
    return "+".join(p.strip().capitalize() if len(p.strip()) > 1 else p.strip().upper()
                    for p in (spec or "").split("+") if p.strip())


class NotesWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle("SPEAK · 📞 Llamadas")
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
        self._stt_lock = threading.Lock()
        self._one_off: threading.Thread | None = None
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
        self.live_sig.editor.connect(self._render_editor)
        self._editor_seen: set[int] = set()  # respuestas cuya pizarra ya abrio la pestaña
        self._editor_top: set[int] = set()  # trozos de pizarra que ya se mostraron arriba una vez
        self._back_seen: set[int] = set()  # respuestas que ya devolvieron la vista a Respuestas
        self.live_sig.discovery.connect(self._render_discovery)
        self.live_sig.attached.connect(self._attached)
        self.live_sig.recording.connect(self._recording_opened)
        self.live_sig.hotkey.connect(self._answer_now)
        self._hotkey = None  # listener global de COPILOT_HOTKEY mientras la ventana esta abierta
        self._last_voice = 0.0  # aviso de silencio: ultima vez que se oyo a alguien
        self._silence_warned = False
        self._live_segments = 0
        self._opening: threading.Thread | None = None
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
        self._refresh_banner()

    def _build(self) -> None:
        central = QWidget()
        lay = QVBoxLayout(central)
        self.banner = ModeBanner()
        lay.addWidget(self.banner)

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
        self.lbl_interview = QLabel()  # entrevista activa (data/library); vacio si no hay
        row.addWidget(self.lbl_interview)
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
        self.btn_full = QPushButton("🎧 Transcribir audio")
        self.btn_full.setToolTip("Vuelve a transcribir la grabacion completa (mas precisa que la de en vivo).\n"
                                 "Sube todo el audio a Deepgram: gasta creditos por cada minuto grabado.")
        self.btn_full.setEnabled(False)
        row2.addWidget(self.live)
        for b in (self.btn_rec, self.btn_stop, self.btn_audio, self.btn_text, self.btn_notes,
                  self.btn_full, self.btn_open):
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
        hk = _pretty_hotkey(self.cfg.COPILOT_HOTKEY)
        self.btn_answer = QPushButton(f"⚡ Responder ahora (F8 / {hk})" if hk else "⚡ Responder ahora (F8)")
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

        ed = QWidget()
        dl = QVBoxLayout(ed)
        dl.setContentsMargins(0, 0, 0, 0)
        dhead = QHBoxLayout()
        legend = QLabel('<span style="color:#c62828;"><i>» rojo: lo que dices</i></span> · '
                        '<span style="font-family:Consolas;">negro: lo que escribes</span> · '
                        '<br><span style="font-family:Consolas; color:#7b1fa2;">morado: escribe o cambia esto</span> · '
                        '<span style="font-family:Consolas; color:#9e9e9e;">gris: ya está escrito, no lo toques</span>')
        dhead.addWidget(legend)
        dhead.addStretch(1)
        self.btn_editor = QPushButton("✍️ Pizarra ahora (F7)")
        self.btn_editor.setToolTip("Guion de pizarra para la ultima pregunta, aunque no pareciera de codigo")
        self.btn_editor.setEnabled(False)
        dhead.addWidget(self.btn_editor)
        dl.addLayout(dhead)
        self.out_editor = QTextBrowser()
        self.out_editor.setStyleSheet("QTextBrowser { background: #ffffff; color: #111111; }")
        dl.addWidget(self.out_editor, 1)
        self.editor_tab = ed

        self.cop_tab = cop
        self.side.addTab(cop, "💬 Respuestas")
        self.side.addTab(ed, "✍️ Editor")
        code_tab = QWidget()  # solo el codigo del ejercicio, sin explicacion (sale de la pizarra: siempre cuadra)
        ql = QVBoxLayout(code_tab)
        ql.setContentsMargins(0, 0, 0, 0)
        qhead = QHBoxLayout()
        self.lbl_code = QLabel("<i>El código del ejercicio, limpio, aparece aquí.</i>")
        self.lbl_code.setStyleSheet("color: gray;")
        qhead.addWidget(self.lbl_code)
        qhead.addStretch(1)
        self.btn_copy_code = QPushButton("📋 Copiar")
        self.btn_copy_code.clicked.connect(lambda: QApplication.clipboard().setText(self.out_code.toPlainText()))
        qhead.addWidget(self.btn_copy_code)
        ql.addLayout(qhead)
        self.out_code = QPlainTextEdit()
        self.out_code.setReadOnly(True)
        self.out_code.setStyleSheet("QPlainTextEdit { font-family: Consolas, 'Courier New', monospace; "
                                    "font-size: 11pt; background: #ffffff; color: #111111; }")
        ql.addWidget(self.out_code, 1)
        self.side.addTab(code_tab, "🧾 Código")
        self.side.addTab(exp, "🔍 Exploracion")
        sl.addWidget(self.side, 1)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self.tabs)
        split.addWidget(side)
        split.setSizes([760, 640])
        lay.addWidget(split, 1)
        self.setCentralWidget(central)
        self._copilot_idle()
        self._editor_idle()
        self._discovery_idle()
        self._show_docs()
        self._show_interview()

        self.btn_rec.clicked.connect(self._record)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_audio.clicked.connect(self._import_audio)
        self.btn_text.clicked.connect(self._import_text)
        self.btn_notes.clicked.connect(self._generate)
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_full.clicked.connect(self._transcribe_full)
        self.btn_prep.clicked.connect(self._open_prep)
        self.btn_answer.clicked.connect(self._answer_now)
        self.on_top.toggled.connect(self._toggle_on_top)
        QShortcut(QKeySequence("F8"), self, activated=self._answer_now)
        QShortcut(QKeySequence("F9"), self, activated=self._discover_now)
        QShortcut(QKeySequence("F7"), self, activated=self._editor_now)
        self.btn_editor.clicked.connect(self._editor_now)
        self.btn_discovery.clicked.connect(self._discover_now)
        self.btn_attach.clicked.connect(self._attach)
        self.btn_paste.clicked.connect(self._paste)
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.live.toggled.connect(lambda _: self._refresh_banner())
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
        from ..notes.recorder import DualRecorder

        folder = self._new_folder()
        if self.live.isChecked():
            try:
                self._start_live()
            except Exception as exc:
                self._stop_live()
                self._status(f"⚠ no pude iniciar el modo en vivo: {exc}", error=True)
                return
        on_audio = self.live_notes.push if self.live_notes else None
        rec = self.recorder = DualRecorder(folder, mic_device=self.cfg.mic_device, on_audio=on_audio)
        # Abrir el audio del sistema (PyAudio) tarda 2-3 s: en un hilo, para que
        # la ventana no se congele. `_recording_opened` termina el arranque.
        self.btn_rec.setEnabled(False)
        self._refresh_banner()
        self.live.setEnabled(False)
        self._status("Abriendo microfono y audio del sistema...")

        def work():
            try:
                rec.start()
                self.live_sig.recording.emit((rec, None))
            except Exception as exc:
                self.live_sig.recording.emit((rec, exc))

        self._opening = threading.Thread(target=work, name="speak-rec-open", daemon=True)
        self._opening.start()

    def _recording_opened(self, payload) -> None:
        rec, exc = payload
        self._opening = None
        if rec is not self.recorder:  # se cerro la ventana mientras abria
            if exc is None:
                rec.stop()
            return
        if exc is not None:
            self.recorder = None
            self._stop_live()
            self.btn_rec.setEnabled(True)
            self.live.setEnabled(True)
            self._status(f"⚠ {exc}", error=True)
            return
        self.btn_stop.setEnabled(True)
        info = getattr(rec, "info", {}) or {}
        devices = []
        if info.get("mic", {}).get("name"):
            devices.append(f"Yo: {info['mic']['name']}")
        if info.get("them", {}).get("name"):
            devices.append(f"Ellos: {info['them']['name']}")
        warn = " · ".join(rec.warnings)
        self._status("● Grabando" + (" en vivo" if self.live_notes else "")
                     + (f" ({' · '.join(devices)})" if devices else "")
                     + (f" — ⚠ {warn}" if warn else ""), error=bool(warn))
        self._last_voice, self._silence_warned, self._live_segments = time.monotonic(), False, 0
        self.btn_full.setEnabled(False)
        self._tick.start()
        self._refresh_banner()

    # --- en vivo --------------------------------------------------------------

    def _start_live(self) -> None:
        from ..notes.live import LiveNotes, glossary_from

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
            on_status=self.live_sig.status.emit,
            # Nombres, siglas y productos del brief y los documentos de la
            # llamada: Whisper los escribe bien ("PCI", no "Peseí").
            glossary=glossary_from(self.prep.brief, self.prep.guide, *self.kb.extra_texts().values()))
        self.live_notes.start()
        if self.cfg.COPILOT_ENABLED:
            live = self.live_notes
            self.copilot = Copilot(
                make_llm(self.cfg, prewarm=self.cfg.COPILOT_PREWARM), self.kb, brief=lambda: self.prep.brief,
                snapshot=live.snapshot, now=live.now, pending=lambda: live.pending(THEM),
                speech=live.speech,
                mode=self.mode.currentText(), on_answer=self.live_sig.answer.emit,
                on_status=self.live_sig.status.emit, guide=lambda: self.prep.guide,
                quiet_s=self.cfg.COPILOT_QUIET_S, eager_s=self.cfg.COPILOT_EAGER_S,
                instant=self._instant_matcher() if self.cfg.COPILOT_INSTANT else None,
                live_timeout_s=self.cfg.COPILOT_LIVE_TIMEOUT_S,
                editor_llm=make_llm(self.cfg, effort=self.cfg.COPILOT_EDITOR_EFFORT) if self.cfg.COPILOT_EDITOR else None,
                supervisor_llm=(make_llm(self.cfg, model=self.cfg.COPILOT_SUPERVISOR_MODEL,
                                         effort=self.cfg.COPILOT_SUPERVISOR_EFFORT)
                                if self.cfg.COPILOT_EDITOR and self.cfg.COPILOT_SUPERVISOR_MODEL else None),
                supervisor_fallback_llm=(make_llm(self.cfg, model=self.cfg.COPILOT_SUPERVISOR_FALLBACK_MODEL,
                                                  effort=self.cfg.COPILOT_SUPERVISOR_EFFORT)
                                         if self.cfg.COPILOT_EDITOR and self.cfg.COPILOT_SUPERVISOR_FALLBACK_MODEL
                                         else None),
                on_editor=self.live_sig.editor.emit)
            self.copilot.start()
            self.btn_answer.setEnabled(True)
            self.btn_editor.setEnabled(self.cfg.COPILOT_EDITOR)
            self._editor_seen.clear()
            self._back_seen.clear()
            self._editor_idle()
            self._copilot_idle()
            self.discovery = self._make_discovery(live.snapshot, self.cfg.DISCOVERY_INTERVAL)
            self.discovery.start()

    def _stop_live(self) -> Transcript | None:
        live, self.live_notes = self.live_notes, None
        copilot, self.copilot = self.copilot, None
        discovery, self.discovery = self.discovery, None
        if discovery is not None:
            discovery.stop()
            if discovery.text:
                self._save("exploracion.md", discovery.text)
        self.btn_answer.setEnabled(False)
        self.btn_editor.setEnabled(False)
        if copilot is not None:
            copilot.stop()
            if copilot.answers:
                self._save("copilot.md", copilot.render_log())
            if any(a.editor for a in copilot.answers):
                self._save("editor.md", copilot.render_editor_log())
        self.out_transcript.setReadOnly(False)
        self.btn_notes.setText("✨ Generar notas")
        if live is None:
            return None
        tr = live.stop()
        if tr.segments:
            self._save("transcript_live.md", render(tr))
        if live.notes:
            self._save("notes_live.md", live.notes)
        return tr

    def _live_stt(self):
        """En vivo: Whisper local con el modelo liviano (STT_LIVE_MODEL)."""
        with self._stt_lock:
            if self._local_stt is None:
                self._local_stt = make_stt(self.cfg, model=self.cfg.STT_LIVE_MODEL or self.cfg.STT_MODEL,
                                           language=self.cfg.NOTES_STT_LANGUAGE)
            return self._local_stt

    def _preload_stt(self) -> None:
        try:
            self._live_stt().warmup()
        except Exception as exc:
            # Si cerraron la ventana (o la app) mientras cargaba, ya no hay a
            # quien avisar: la senal esta borrada y Python se esta apagando.
            try:
                self.live_sig.status.emit(f"modelo de voz: {exc}")
            except RuntimeError:
                pass

    def _mode_changed(self, mode: str) -> None:
        self.prep.mode = mode
        self._refresh_banner()
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
        if self._one_off is not None and self._one_off.is_alive():
            return  # ya hay una en curso
        tr = self.transcript
        one_off = self._make_discovery(lambda: tr, 0)
        self._one_off = threading.Thread(target=one_off.run_once, args=(tr,), name="speak-discovery-now",
                                         daemon=True)
        self._one_off.start()

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

    def _show_interview(self) -> None:
        label = active_label()
        self.lbl_interview.setText(f"Entrevista: <b>{label}</b>" if label else "")

    def _interview_changed(self) -> None:
        self._show_docs()
        self._show_interview()

    def _open_prep(self) -> None:
        if self.prep_window is None:
            self.prep_window = PrepWindow(self.cfg, self.prep, self.mode,
                                          on_interview_changed=self._interview_changed)
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
                   f"**F8**{self._hotkey_hint()} responde a lo ultimo que dijo.*")
        self.out_copilot.setMarkdown(msg)

    def _editor_now(self) -> None:
        if self.copilot and self.copilot.editor_llm is not None:
            if self.copilot.editor_now():
                self.side.setCurrentWidget(self.editor_tab)
        else:
            self._status("La pizarra funciona mientras grabas en vivo con el copiloto.", error=True)

    def _editor_idle(self) -> None:
        if not self.cfg.COPILOT_EDITOR:
            msg = "<i>Pizarra desactivada (COPILOT_EDITOR=false en speak/.env).</i>"
        else:
            msg = ("<i>Cuando te pidan escribir codigo, pseudocodigo o un diagrama, esta pestaña se abre sola "
                   "con el guion: <span style='color:#c62828;'>» en rojo lo que dices</span> mientras "
                   "escribes lo de negro. <b>F7</b> lo pide para la ultima pregunta.</i>")
        self.out_editor.setHtml(msg)

    def _render_editor(self, ans=None) -> None:
        if not self.copilot:
            return
        self._follow_topic(ans)
        bar = self.out_editor.verticalScrollBar()
        keep = bar.value()  # el scroll se queda donde lo dejaste (antes volvia arriba con cada trozo)
        newest = next((a for a in reversed(self.copilot.answers) if a.editor_on or a.editor), None)
        jump = newest is not None and newest.id not in self._editor_top
        if jump:
            self._editor_top.add(newest.id)  # trozo nuevo: arriba, una sola vez
        tr = self.live_notes.snapshot() if self.live_notes else None
        parts = []
        for a in reversed([a for a in self.copilot.answers if a.editor_on or a.editor][-6:]):
            state = "" if a.editor_done else " ⏳"
            q = a.question if len(a.question) < 220 else "…" + a.question[-220:]
            before = a.editor_before if not a.editor_fresh else None  # ejercicio nuevo: nada que comparar
            said = (said_progress(a.editor, " ".join(s.text for s in tr.segments
                                                     if s.speaker == ME and s.start >= a.at)) if tr else None)
            body = (editor_html(a.editor, a.editor_changed, before, said) if a.editor
                    else "<p><i>Preparando el guion…</i></p>")
            check = {"revisando": "🔎 revisando…", "ok": "✓ revisado", "corregido": "↻ corregido (amarillo)",
                     "error": "⚠ revisado: aún falla al ejecutar",
                     "sin revisar": "⚠ sin revisar (el supervisor no respondió)"}.get(a.editor_check, "")
            check = f' <span style="color:#888888; font-size:9pt;">· {check}</span>' if check else ""
            parts.append(f"<p><b>[{_fmt(a.at)}] ❓ {_html_escape(q)}</b>{state}{check}</p>{body}")
        self.out_editor.setHtml("<hr>".join(parts) if parts else "")
        bar.setValue(0 if jump else keep)
        if newest is not None:  # 🧾 Código: el codigo limpio del ejercicio actual
            code = clean_code(self.copilot._board_at(newest.at + 0.001))
            if code and code != self.out_code.toPlainText():
                cbar = self.out_code.verticalScrollBar()
                ckeep = cbar.value()
                self.out_code.setPlainText(code)
                cbar.setValue(ckeep)
                self.lbl_code.setText(f"<i>[{_fmt(newest.at)}] {len(code.splitlines())} líneas, versión actual</i>")

    def _instant_matcher(self):
        """Respuestas preparadas al instante, con los textos de la preparacion
        tal como esten al preguntar (si pegas uno a mitad de llamada, cuenta)."""
        def match(question: str):
            index = PreparedIndex(self.kb.extra_texts(), min_score=self.cfg.COPILOT_INSTANT_MIN_SCORE,
                                  min_precision=self.cfg.COPILOT_INSTANT_MIN_PRECISION)
            return index.match(question)
        return match

    def _follow_topic(self, ans) -> None:
        """La pestaña sigue el tema de la ultima pregunta: codigo -> ✍️ Editor;
        otra cosa (o el editor dijo NO_EDIT) -> de vuelta a 💬 Respuestas. Una vez
        por pregunta: si luego cambias de pestaña a mano, no se te quita."""
        if ans is None or not self.copilot or not self.copilot.answers or ans is not self.copilot.answers[-1]:
            return
        if ans.editor_on:
            if ans.id not in self._editor_seen:
                self._editor_seen.add(ans.id)
                self.side.setCurrentWidget(self.editor_tab)
        elif (not ans.editor_pending and ans.id not in self._back_seen
              and self.side.currentWidget() is self.editor_tab):
            self._back_seen.add(ans.id)
            self.side.setCurrentWidget(self.cop_tab)

    def _render_copilot(self, _answer=None) -> None:
        if not self.copilot:
            return
        self._follow_topic(_answer)
        parts = []
        for a in reversed(self.copilot.answers[-15:]):
            state = "" if a.done else " ⏳"
            # AL VUELO (la del LLM) siempre; MEMORIA (la preparada) encima, solo
            # si la pregunta coincide casi exactamente con un titulo preparado.
            if a.followup:  # el otro contesto tu pregunta: ideas para seguir el hilo
                blocks = [_answer_block("💬 SEGUIMIENTO", "", a.text,
                                        "si quieres seguir el hilo; si no, pasa a tu siguiente pregunta")]
            elif a.clarify:  # contesto tu pregunta de aclaracion en el ejercicio
                blocks = [_answer_block("📝 ACLARACIÓN", "", a.text,
                                        "di tu decisión y sigue con el código; el cambio está en ✍️ Editor")]
            else:
                blocks = [_answer_block("🎯 AL VUELO", "", a.text, "léela; cubre lo que la memoria no capta")]
                if a.fact_flags:  # posibles inventos: datos tuyos que no estan en tus notas
                    blocks.insert(0, "*⚠ No está en tus notas: " + ", ".join(a.fact_flags[:6])
                                  + " — compruébalo antes de decirlo*")
            if a.timed_out and not a.text:
                # El LLM no llego a tiempo: solo MEMORIA; sin ella, un aviso.
                blocks = [] if a.instant else ["*⌛ AL VUELO no llegó a tiempo. F8 para reintentar.*"]
            if a.board_only:  # ejercicio: todo en la pizarra, paso a paso
                blocks = ["*✍️ Ejercicio de código: síguelo en la pestaña **✍️ Editor** "
                          "(rojo = lo que dices, negro = lo que escribes).*"]
            elif a.editor_on:
                blocks.append("*✍️ Guion de pizarra (qué escribir) en la pestaña **✍️ Editor**.*")
            if a.instant:
                blocks.insert(0, _answer_block("🧠 MEMORIA", a.instant_key, a.instant,
                                               "para arrancar de memoria si la pregunta es idéntica",
                                               reflow=True))
            body = "\n\n&nbsp;\n\n".join(blocks)  # linea en blanco visible entre las dos
            parts.append(f"**[{_fmt(a.at)}] {'🗣️' if a.followup else '❓'} {a.question}**{state}\n\n{body}")
        self.out_copilot.setMarkdown("\n\n---\n\n".join(parts))
        self.out_copilot.verticalScrollBar().setValue(0)

    def _live_transcript(self, tr: Transcript) -> None:
        if not self.live_notes:
            return
        if len(tr.segments) > self._live_segments:  # alguien dijo algo nuevo
            self._live_segments = len(tr.segments)
            self._heard_voice()
            if self.side.currentWidget() is self.editor_tab:
                self._render_editor()  # las lineas que ya dijiste se marcan ✓
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
            self.out_notes.setMarkdown("*Borrador en vivo*\n\n" + md)

    def _refresh_banner(self) -> None:
        """La franja y el titulo dicen en que estas: lista, grabando con o sin
        copiloto, o procesando. Ver `banner.py` por los colores."""
        from ..notes.copilot import COPILOT_MODES

        if not hasattr(self, "banner"):
            return
        mode = self.mode.currentText()
        recording = self.recorder is not None or getattr(self, "_opening", None) is not None
        copilot_on = (self.cfg.COPILOT_ENABLED and self.live.isChecked() and mode in COPILOT_MODES)
        why_off = ("modo entrevista: el copiloto no sopla respuestas" if mode == "entrevista"
                   else "copiloto apagado" if not self.cfg.COPILOT_ENABLED
                   else "sin 'En vivo'" if not self.live.isChecked() else "")
        clock = ""
        if recording and self.recorder is not None:
            t = int(self.recorder.elapsed)
            clock = f"  ·  {t // 60:02d}:{t % 60:02d}"
        if recording and copilot_on:
            kind, text, title = ("live", f"● EN LLAMADA  ·  GRABANDO  ·  COPILOTO ACTIVO ({mode}){clock}",
                                 "● EN LLAMADA · copiloto")
        elif recording:
            kind, text, title = ("notes", f"● GRABANDO  ·  SOLO NOTAS, SIN COPILOTO ({why_off}){clock}",
                                 "● GRABANDO · solo notas")
        elif getattr(self, "_busy", False):
            kind, text, title = ("busy", "⏳ PROCESANDO — transcribiendo y armando las notas de la llamada",
                                 "procesando")
        else:
            state = ("el copiloto se activa al grabar" if copilot_on
                     else f"al grabar: solo notas ({why_off})")
            kind, text, title = ("idle", f"📞 LLAMADAS — sin grabar  ·  modo {mode}  ·  {state}", "Llamadas")
        self.banner.set_state(kind, text)
        self.setWindowTitle(f"SPEAK · 📞 {title}")

    def _update_rec(self) -> None:
        self._refresh_banner()
        if not self.recorder:
            return
        t = int(self.recorder.elapsed)
        self.lbl_time.setText(f"{t // 60:02d}:{t % 60:02d}")
        self.me_level.setValue(min(100, int(self.recorder.levels["me"] * 600)))
        self.them_level.setValue(min(100, int(self.recorder.levels["them"] * 600)))
        self._check_silence()

    # Nivel (RMS) que cuenta como voz para el aviso de silencio. "Ellos" pasa por
    # ganancia automatica (hasta x31): su ruido de fondo sube, por eso pide mas.
    VOICE_LEVEL = {"me": 0.03, "them": 0.06}

    def _check_silence(self) -> None:
        """Aviso si llevas NOTES_SILENCE_WARN_MIN minutos grabando sin que nadie
        hable (medido 2026-10-07: una practica quedo grabando 1 h 50 min y al
        detener se subieron 1,3 GB de silencio a Deepgram)."""
        now = time.monotonic()
        if not self._last_voice:
            self._last_voice = now
        if not self.live_notes:  # sin En vivo no hay transcripcion: solo los niveles
            if any(self.recorder.levels[w] > lvl for w, lvl in self.VOICE_LEVEL.items()):
                self._last_voice = now
        elif self.recorder.levels["me"] > self.VOICE_LEVEL["me"]:
            self._last_voice = now
        minutes = self.cfg.NOTES_SILENCE_WARN_MIN
        if minutes <= 0 or self._silence_warned or now - self._last_voice < minutes * 60:
            return
        self._silence_warned = True
        self._status(f"⚠ Llevas {minutes} min grabando sin que nadie hable. ¿Sigue la llamada? "
                     "Si ya termino, pulsa ■ Detener.", error=True)
        QApplication.alert(self)  # parpadea en la barra de tareas

    def _heard_voice(self) -> None:
        self._last_voice = time.monotonic()
        if self._silence_warned:
            self._silence_warned = False
            self.lbl_status.setText("● Grabando")
            self.lbl_status.setStyleSheet("")

    def _stop(self) -> None:
        if not self.recorder:
            return
        self._tick.stop()
        folder = self.recorder.stop()
        self.recorder = None
        live_tr = self._stop_live()
        self.btn_rec.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.live.setEnabled(True)
        self._refresh_banner()
        if live_tr is not None and live_tr.segments and not self.cfg.NOTES_FINAL_FROM_AUDIO:
            # La de en vivo ya es la transcripcion: no se vuelve a subir la
            # llamada entera (cada minuto grabado se pagaba dos veces).
            self._show_transcript(live_tr)
            if not self.cfg.NOTES_KEEP_AUDIO:
                discard_recording_audio(folder)
            self._status("Transcripcion final = la de en vivo (el audio no se volvio a subir). "
                         "Para mas precision: 🎧 Transcribir audio.")
            self._update_full_btn()
            return
        self._run(lambda: self._transcribe_recording(folder), "transcript")

    def _has_audio(self) -> bool:
        return bool(self.folder) and any((self.folder / n).exists() for n in ("me.wav", "them.wav"))

    def _update_full_btn(self) -> None:
        self.btn_full.setEnabled(not getattr(self, "_busy", False) and self.recorder is None and self._has_audio())

    def _transcribe_full(self) -> None:
        if self._has_audio() and not getattr(self, "_busy", False) and self.recorder is None:
            folder = self.folder
            self._run(lambda: self._transcribe_recording(folder), "transcript")

    def _transcribe_recording(self, folder: Path) -> Transcript:
        # Si la transcripcion falla, la excepcion sale antes de borrar: el audio se conserva.
        tr = load_any(folder, self._stt, self.sig.progress.emit)
        if not self.cfg.NOTES_KEEP_AUDIO:
            discard_recording_audio(folder)
        return tr

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
            try:
                self._show_transcript(load_any(Path(path), self._stt))
            except Exception as exc:
                self._status(f"⚠ no pude leer {Path(path).name}: {exc}", error=True)

    def _stt(self):
        stt = make_stt(self.cfg, for_files=True, language=self.cfg.NOTES_STT_LANGUAGE)
        live = self._local_stt
        if (isinstance(stt, FasterWhisperSTT) and live is not None
                and getattr(live, "model_name", None) == stt.model_name):
            return live  # el mismo modelo ya cargado, no otro en memoria
        return stt

    # --- notas ----------------------------------------------------------------

    def _generate(self) -> None:
        if self.live_notes:
            if self.live_notes.llm is None:
                self._status("Las notas en vivo estan apagadas (LIVE_NOTES_INTERVAL=0): "
                             "salen al detener, con Generar notas.", error=True)
                return
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
                self.sig.done.emit(("error", None))  # desbloquea los botones

        threading.Thread(target=work, name=f"speak-notes-{kind}", daemon=True).start()

    def _task_done(self, payload) -> None:
        kind, result = payload
        self._set_busy(False)
        if kind == "error":
            return
        if kind == "transcript":
            self._show_transcript(result)
        elif kind == "notes":
            self.out_notes.setMarkdown(result)
            if self._save("notes.md", result):
                self._status(f"Notas guardadas en {self.folder / 'notes.md'}")

    def _show_transcript(self, tr: Transcript) -> None:
        self.transcript = tr
        text = render(tr)
        self.out_transcript.setPlainText(text)
        report = heuristic_report(tr)
        if any(s.speaker == ME for s in tr.segments):
            report += f"\n\nHablaste el {me_share(tr):.0%} (por palabras)."
        self.out_questions.setPlainText(report)
        self._save("transcript.md", text)
        self._status(f"Transcripcion lista: {len(tr.segments)} segmentos, hablantes: "
                     f"{', '.join(tr.speakers()) or '—'}")
        self.tabs.setCurrentWidget(self.out_transcript)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_banner()
        for b in (self.btn_rec, self.btn_audio, self.btn_text, self.btn_notes):
            b.setEnabled(not busy)
        if not busy:
            self.btn_notes.setEnabled(bool(self.out_transcript.toPlainText().strip()))
        self._update_full_btn()

    def _save(self, name: str, text: str) -> bool:
        if not self.folder:
            return False
        try:
            (self.folder / name).write_text(text + "\n", encoding="utf-8")
            return True
        except OSError as exc:
            self._status(f"⚠ no pude guardar {name}: {exc}", error=True)
            return False

    def _status(self, msg: str, error: bool = False) -> None:
        if not msg and not error:
            return
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet("color: #c0392b;" if error else "")

    def _open_folder(self) -> None:
        target = self.folder or (DATA_DIR / "notes")
        target.mkdir(parents=True, exist_ok=True)
        os.startfile(str(target))

    # --- atajo global ----------------------------------------------------------

    def _hotkey_hint(self) -> str:
        hk = _pretty_hotkey(self.cfg.COPILOT_HOTKEY)
        if not hk:
            return ""
        return f" o **{hk}** (desde cualquier ventana)" if self._hotkey else f" o **{hk}**"

    def _start_hotkey(self) -> None:
        """COPILOT_HOTKEY global, con el mismo RegisterHotKey de SCREEN
        (helper/hotkey.py). Si Windows no lo da (otra app lo tiene), queda como
        atajo de esta ventana."""
        spec = (self.cfg.COPILOT_HOTKEY or "").strip()
        if not spec or self._hotkey is not None:
            return
        try:
            from helper.hotkey import HotkeyError, HotkeyListener

            listener = HotkeyListener(spec, self.live_sig.hotkey.emit)
            listener.start()
        except (ImportError, OSError, AttributeError) as exc:  # fuera de Windows o sin el modulo
            self._local_hotkey(spec, f"atajo global no disponible ({exc})")
            return
        except HotkeyError as exc:
            self._local_hotkey(spec, str(exc))
            return
        self._hotkey = listener
        if not self.copilot:
            self._copilot_idle()  # el aviso ya dice que funciona desde cualquier ventana

    def _local_hotkey(self, spec: str, why: str) -> None:
        if getattr(self, "_local_shortcut", None) is None:
            self._local_shortcut = QShortcut(QKeySequence(_pretty_hotkey(spec)), self, activated=self._answer_now)
        self._status(f"⚠ {_pretty_hotkey(spec)} solo funciona con esta ventana activa: {why}", error=True)

    def _stop_hotkey(self) -> None:
        listener, self._hotkey = self._hotkey, None
        if listener is not None:
            listener.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._start_hotkey()

    def closeEvent(self, event) -> None:
        self._stop_hotkey()
        if self._opening is not None:
            # Aun abriendo el audio: esperar a que termine para poder cerrarlo.
            self._opening.join(timeout=8)
            QApplication.processEvents()
        if self.recorder:
            self._stop()
        else:
            self._stop_live()
        if self.prep_window is not None:
            self.prep_window.close()
        super().closeEvent(event)
