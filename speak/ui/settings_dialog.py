"""Ajustes → speak/.env. Las API keys no se editan aqui (van a mano en .env)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from ..audio_capture import list_input_devices
from ..config import Config

STT_MODELS = ["tiny", "base", "small", "medium", "distil-large-v3", "large-v3"]


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajustes de SPEAK")
        self.cfg = cfg
        form = QFormLayout(self)

        self.provider = QComboBox()
        self.provider.addItems(["claude_cli", "anthropic"])
        self.provider.setCurrentText(cfg.LLM_PROVIDER)
        form.addRow("Proveedor LLM", self.provider)
        self.model = QLineEdit(cfg.LLM_MODEL)
        form.addRow("Modelo LLM (id completo)", self.model)
        self.effort = QComboBox()
        self.effort.addItems(["low", "medium", "high"])
        self.effort.setCurrentText(cfg.LLM_EFFORT)
        form.addRow("Esfuerzo", self.effort)

        self.stt_model = QComboBox()
        self.stt_model.addItems(STT_MODELS)
        self.stt_model.setCurrentText(cfg.STT_MODEL)
        form.addRow("Modelo de voz (Whisper)", self.stt_model)
        self.stt_provider = QComboBox()
        self.stt_provider.addItems(["faster_whisper", "assemblyai"])
        self.stt_provider.setCurrentText(cfg.STT_PROVIDER)
        form.addRow("STT para Notas de llamada", self.stt_provider)
        self.lang = QComboBox()
        self.lang.addItems(["en", "es", ""])
        self.lang.setCurrentText(cfg.STT_LANGUAGE)
        form.addRow("Idioma (vacio = auto)", self.lang)

        self.mic = QComboBox()
        self.mic.addItem("Predeterminado de Windows", "")
        for idx, name in list_input_devices():
            self.mic.addItem(f"{idx}: {name}", str(idx))
        i = self.mic.findData(cfg.MIC_DEVICE)
        self.mic.setCurrentIndex(max(0, i))
        form.addRow("Microfono", self.mic)

        self.silence = self._spin(cfg.SILENCE_THRESHOLD, 300, 3000, 100)
        form.addRow("Silencio para cerrar pregunta (ms)", self.silence)
        self.answer_silence = self._spin(cfg.ANSWER_SILENCE, 800, 8000, 100)
        form.addRow("Silencio para cerrar respuesta (ms)", self.answer_silence)
        self.max_silence = self._spin(cfg.MAX_SILENCE, 2000, 15000, 500)
        form.addRow("Silencio maximo (ms)", self.max_silence)
        self.window = self._spin(cfg.CONTEXT_WINDOW, 0, 10, 1)
        form.addRow("Intercambios completos en contexto", self.window)

        self.tts = QCheckBox("Leer las preguntas en voz alta")
        self.tts.setChecked(cfg.TTS_ENABLED)
        form.addRow(self.tts)
        self.tts_rate = self._spin(cfg.TTS_RATE, -10, 10, 1)
        form.addRow("Velocidad de la voz", self.tts_rate)

        note = QLabel("Los cambios se guardan en speak/.env y aplican al reiniciar SPEAK.")
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @staticmethod
    def _spin(value, lo, hi, step) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(int(value))
        return s

    def _save(self) -> None:
        c = self.cfg
        c.LLM_PROVIDER = self.provider.currentText()
        c.LLM_MODEL = self.model.text().strip() or c.LLM_MODEL
        c.LLM_EFFORT = self.effort.currentText()
        c.STT_MODEL = self.stt_model.currentText()
        c.STT_PROVIDER = self.stt_provider.currentText()
        c.STT_LANGUAGE = self.lang.currentText()
        c.MIC_DEVICE = self.mic.currentData() or ""
        c.SILENCE_THRESHOLD = self.silence.value()
        c.ANSWER_SILENCE = self.answer_silence.value()
        c.MAX_SILENCE = self.max_silence.value()
        c.CONTEXT_WINDOW = self.window.value()
        c.TTS_ENABLED = self.tts.isChecked()
        c.TTS_RATE = self.tts_rate.value()
        c.save()
        self.accept()
