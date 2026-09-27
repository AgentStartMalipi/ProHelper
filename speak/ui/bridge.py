"""Puente hilos → Qt.

Los callbacks del simulador llegan desde hilos de audio, STT y LLM. Emitir
una Signal desde otro hilo hacia un QObject del hilo principal hace que Qt la
encole (AutoConnection), asi que los slots siempre corren en el hilo de la UI.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..simulator import Listener


class SimSignals(QObject):
    phase = Signal(str)
    turn_state = Signal(str)
    level = Signal(float, bool)
    interviewer = Signal(str, bool)
    question = Signal(str, str)
    transcript = Signal(str)
    clarification = Signal(str, str)
    evaluation = Signal(dict, bool)
    status = Signal(str)
    error = Signal(str)

    def listener(self) -> Listener:
        return Listener(
            phase=self.phase.emit,
            turn_state=self.turn_state.emit,
            level=self.level.emit,
            interviewer=self.interviewer.emit,
            question=self.question.emit,
            transcript=self.transcript.emit,
            clarification=self.clarification.emit,
            evaluation=self.evaluation.emit,
            status=self.status.emit,
            error=self.error.emit,
        )


class TaskSignals(QObject):
    """Para trabajos sueltos en segundo plano (Notas de llamada)."""

    progress = Signal(str)
    chunk = Signal(str)
    done = Signal(object)
    failed = Signal(str)


class LiveSignals(QObject):
    """Notas de llamada en vivo."""

    transcript = Signal(object)
    notes = Signal(str)
    status = Signal(str)
    answer = Signal(object)  # notes.copilot.Answer
    discovery = Signal(str, bool)  # markdown, terminado
    attached = Signal(str)  # aviso al terminar de anadir archivos
    recording = Signal(object)  # (grabadora, excepcion o None) al terminar de abrir el audio
