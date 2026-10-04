"""Motor del simulador de entrevistas (sin Qt).

Flujo de una pregunta:

    ASKING      el LLM genera la pregunta (streaming) y el TTS la lee; el
                microfono va silenciado para no transcribir al entrevistador.
    LISTENING   respondes. Audio → frases → STT → detector de turnos.
                - Si tu turno es una pregunta corta ("can I assume it's
                  sorted?") → CLARIFYING: el entrevistador aclara y vuelves a
                  LISTENING.
                - Si es tu respuesta (o pulsas "Termine") → EVALUATING.
    EVALUATING  el evaluador escribe FEEDBACK / QUICK / DETAILED en streaming.
                Si retomas la palabra enseguida (turno reabierto), se cancela
                y se vuelve a LISTENING con tu respuesta completa.
    REVIEW      esperas: siguiente pregunta, repregunta o regenerar.

Concurrencia: toda entrada (eventos de audio, texto del STT, botones, fin de
un stream) entra a `_inbox` y la procesa un unico hilo. El detector y el
contexto solo se tocan desde ahi. Los streams del LLM corren en hilos propios
y llaman a los callbacks de la UI directamente con cada trozo.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from . import audio_capture as ac
from .answer_generator import AnswerGenerator, extract_score, split_sections
from .config import DATA_DIR, Config
from .context_manager import ContextManager
from .llm_client import LLMClient
from .question_classifier import QType, classify
from .transcriber import IncrementalTranscriber, SpeechToText, TranscriptEvent
from .tts import Speaker
from .turn_detector import (
    StateChanged,
    TurnComplete,
    TurnConfig,
    TurnDetector,
    TurnReopened,
    is_question_sentence,
    sentences,
)

log = logging.getLogger(__name__)


class Phase(str, Enum):
    IDLE = "IDLE"
    LOADING = "LOADING"
    ASKING = "ASKING"
    LISTENING = "LISTENING"
    CLARIFYING = "CLARIFYING"
    EVALUATING = "EVALUATING"
    REVIEW = "REVIEW"
    PAUSED = "PAUSED"


@dataclass
class Listener:
    """Callbacks hacia la UI. Pueden llegar desde cualquier hilo."""

    phase: Callable[[str], None] = lambda p: None
    turn_state: Callable[[str], None] = lambda s: None
    level: Callable[[float, bool], None] = lambda rms, speaking: None
    interviewer: Callable[[str, bool], None] = lambda text, final: None  # texto acumulado
    question: Callable[[str, str], None] = lambda text, qtype: None
    transcript: Callable[[str], None] = lambda text: None  # tu respuesta en curso
    clarification: Callable[[str, str], None] = lambda asked, reply: None
    evaluation: Callable[[dict, bool], None] = lambda sections, final: None
    status: Callable[[str], None] = lambda msg: None
    error: Callable[[str], None] = lambda msg: None


# mensajes internos del inbox
@dataclass
class _Cmd:
    name: str
    arg: object = None


class Simulator:
    def __init__(
        self,
        cfg: Config,
        llm: LLMClient,
        stt: SpeechToText,
        listener: Listener,
        ctx: ContextManager | None = None,
        speaker: Speaker | None = None,
        capture_factory: Callable[..., object] | None = None,
    ) -> None:
        self.cfg = cfg
        self.llm = llm
        self.stt = stt
        self.ui = listener
        self.ctx = ctx or ContextManager(cfg.CONTEXT_WINDOW, cfg.CV_MAX_CHARS, cfg.JD_MAX_CHARS)
        self.gen = AnswerGenerator(llm, self.ctx)
        self.speaker = speaker or Speaker(cfg.TTS_ENABLED, cfg.TTS_RATE, cfg.STT_LANGUAGE or "en")
        self.detector = TurnDetector(self._turn_config())
        self.phase = Phase.IDLE
        self._before_pause = Phase.IDLE
        self._inbox: queue.Queue = queue.Queue()
        self._cancel: threading.Event | None = None
        self._stream_id = 0
        self._audio_t = 0.0
        self._live: list[str] = []  # frases del turno en curso, para la UI
        self._answer_before_commit = ""
        self._eval_qtype = QType.GENERAL
        self._force_close = False
        self._session_file = DATA_DIR / "sessions" / time.strftime("%Y%m%d-%H%M%S.json")
        self._transcriber = IncrementalTranscriber(
            stt, cfg.SAMPLE_RATE, on_text=lambda ev: self._post("text", ev),
            on_error=listener.error,
        )
        factory = capture_factory or ac.AudioCapture
        self.capture = factory(
            on_event=lambda ev: self._post("audio", ev), sample_rate=cfg.SAMPLE_RATE,
            chunk_ms=cfg.CHUNK_MS, vad_threshold=cfg.VAD_THRESHOLD, device=cfg.mic_device,
            on_error=listener.error,
        )
        self._thread = threading.Thread(target=self._loop, name="speak-sim", daemon=True)
        self._thread.start()

    def _turn_config(self) -> TurnConfig:
        return TurnConfig(
            silence_threshold_ms=self.cfg.ANSWER_SILENCE,
            question_silence_ms=self.cfg.SILENCE_THRESHOLD,
            max_silence_ms=self.cfg.MAX_SILENCE,
            merge_window_ms=3000,
        )

    # --- API publica (cualquier hilo) ----------------------------------------

    def start(self) -> None:
        self._post("start")

    def pause(self) -> None:
        self._post("pause")

    def resume(self) -> None:
        self._post("resume")

    def done_answering(self) -> None:
        self._post("done")

    def next_question(self, custom: str | None = None) -> None:
        self._post("next", custom)

    def follow_up(self) -> None:
        self._post("follow_up")

    def regenerate(self) -> None:
        self._post("regenerate")

    def clear_context(self) -> None:
        self._post("clear")

    def shutdown(self) -> None:
        self._post("shutdown")
        self._thread.join(timeout=3)

    def _post(self, name: str, arg: object = None) -> None:
        self._inbox.put(_Cmd(name, arg))

    # --- bucle ---------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            cmd: _Cmd = self._inbox.get()
            try:
                if cmd.name == "shutdown":
                    self._cancel_stream()
                    self.speaker.stop()
                    self._stop_capture()
                    self._transcriber.close()
                    return
                getattr(self, f"_on_{cmd.name}")(cmd.arg)
            except Exception as exc:
                log.exception("error en el simulador (%s)", cmd.name)
                self.ui.error(f"{cmd.name}: {exc}")

    def _set_phase(self, phase: Phase) -> None:
        if phase != self.phase:
            self.phase = phase
            self.ui.phase(phase.value)

    # --- comandos ------------------------------------------------------------

    def _on_start(self, _):
        if self.phase not in (Phase.IDLE, Phase.REVIEW):
            return
        self._set_phase(Phase.LOADING)
        self.ui.status("Cargando el modelo de voz (la primera vez lo descarga)...")

        def warm():
            try:
                self.stt.warmup()
                self._post("warm_ok")
            except Exception as exc:
                self._post("warm_fail", str(exc))

        threading.Thread(target=warm, name="speak-warmup", daemon=True).start()

    def _on_warm_ok(self, _):
        try:
            self.capture.start()
        except ac.AudioError as exc:
            self._set_phase(Phase.IDLE)
            self.ui.error(str(exc))
            return
        self.capture.mute(True)
        self.ui.status("Microfono listo.")
        self._on_next(None)

    def _on_warm_fail(self, msg):
        self._set_phase(Phase.IDLE)
        self.ui.error(f"No se pudo cargar el modelo de voz: {msg}")

    def _on_pause(self, _):
        if self.phase in (Phase.PAUSED, Phase.IDLE):
            return
        self._before_pause = self.phase
        self.speaker.stop()
        self.capture.mute(True)
        self._set_phase(Phase.PAUSED)
        self.ui.status("En pausa.")

    def _on_resume(self, _):
        if self.phase != Phase.PAUSED:
            return
        back = self._before_pause
        if back == Phase.ASKING:
            # Se corto la lectura: se da la pregunta por leida.
            back = Phase.LISTENING
        self._set_phase(back)
        if back == Phase.LISTENING:
            self._start_listening(reset=False)
        self.ui.status("")

    def _on_next(self, custom):
        self._cancel_stream()
        self.speaker.stop()
        self.capture.mute(True)
        self._set_phase(Phase.ASKING)
        if custom:
            self._question_ready(str(custom), classify(str(custom)).qtype)
            return
        self.ui.interviewer("", False)
        self._run_stream(self.gen.next_question, on_chunk=lambda acc: self.ui.interviewer(acc, False),
                         on_done="question_text")

    def _on_follow_up(self, _):
        if not self.ctx.current:
            return self._on_next(None)
        self._cancel_stream()
        self.speaker.stop()
        self.capture.mute(True)
        self._set_phase(Phase.ASKING)
        self.ui.interviewer("", False)
        self._run_stream(self.gen.follow_up, on_chunk=lambda acc: self.ui.interviewer(acc, False),
                         on_done="followup_text")

    def _on_question_text(self, text):
        self._question_ready(text, classify(text).qtype)

    def _on_followup_text(self, text):
        self._question_ready(text, QType.FOLLOW_UP)

    def _question_ready(self, text: str, qtype: QType) -> None:
        text = text.strip()
        self.ctx.start_exchange(text, qtype.value)
        self._transcriber.reset_context()
        self.ui.interviewer(text, True)
        self.ui.question(text, qtype.value)
        self.ui.transcript("")
        self.ui.evaluation({}, False)
        self.speaker.speak(text, on_done=lambda: self._post("spoken"))

    def _on_spoken(self, _):
        if self.phase in (Phase.ASKING, Phase.CLARIFYING):
            # Lo ya respondido vive en el contexto; el detector arranca limpio.
            self._set_phase(Phase.LISTENING)
            self._start_listening(reset=True)

    def _start_listening(self, reset: bool = True) -> None:
        if reset:
            self.detector.reset()
            self._live = []
        # Un respiro para que la cola del TTS no entre por el microfono.
        threading.Timer(0.3, lambda: self.capture.mute(False)).start()
        self.ui.status("Te escucho. Responde en voz alta (o pulsa Termine).")

    def _on_done(self, _):
        if self.phase != Phase.LISTENING:
            return
        self._force_close = True
        self.capture.flush_now()
        self._post("try_force")

    def _on_try_force(self, _):
        # Espera a que el STT entregue lo pendiente antes de cerrar.
        if not self._force_close:
            return
        if self.detector.pending() > 0 or self._transcriber.pending() > 0:
            threading.Timer(0.15, lambda: self._post("try_force")).start()
            return
        self._force_close = False
        self._handle_turn_events(self.detector.force(self._audio_t))

    def _on_regenerate(self, _):
        if self.ctx.current and self.phase in (Phase.REVIEW, Phase.EVALUATING):
            self._evaluate(self._eval_qtype)

    def _on_clear(self, _):
        self._cancel_stream()
        self.speaker.stop()
        self.capture.mute(True)
        self.ctx.clear()
        self.detector.reset()
        self._live = []
        self._session_file = DATA_DIR / "sessions" / time.strftime("%Y%m%d-%H%M%S.json")
        self._set_phase(Phase.REVIEW if self.capture.running else Phase.IDLE)
        self.ui.status("Contexto borrado (el perfil se conserva).")

    # --- audio y texto -------------------------------------------------------

    def _on_audio(self, ev):
        if isinstance(ev, ac.Level):
            self.ui.level(ev.rms, ev.speaking)
            return
        if self.phase not in (Phase.LISTENING, Phase.EVALUATING):
            return
        if isinstance(ev, ac.SpeechStarted):
            self._audio_t = ev.t
            self._handle_turn_events(self.detector.speech_started(ev.t))
        elif isinstance(ev, ac.Utterance):
            self._audio_t = ev.end
            self._transcriber.submit(ev.audio, ev.start, ev.end)
            self._handle_turn_events(self.detector.utterance_ended(ev.end))
        elif isinstance(ev, ac.SilenceTick):
            self._audio_t = ev.t
            self._handle_turn_events(self.detector.silence(ev.t, ev.silence_ms))

    def _on_text(self, ev: TranscriptEvent):
        if self.phase not in (Phase.LISTENING, Phase.EVALUATING):
            self.detector.text_arrived_without_audio()
            return
        self._live.append(ev.text)
        self.ui.transcript(" ".join(self._live))
        self._handle_turn_events(self.detector.add_text(ev.text, ev.start, ev.end, self._audio_t))
        if self._force_close:
            self._post("try_force")

    def _handle_turn_events(self, events) -> None:
        for ev in events:
            if isinstance(ev, StateChanged):
                self.ui.turn_state(ev.state.value)
            elif isinstance(ev, TurnReopened):
                if self.phase == Phase.EVALUATING:
                    self._cancel_stream()
                    if self.ctx.current:
                        self.ctx.current.answer = self._answer_before_commit
                    self._set_phase(Phase.LISTENING)
                    self.ui.evaluation({}, False)
                    self.ui.status("Seguiste hablando: sigo escuchando.")
            elif isinstance(ev, TurnComplete):
                self._on_turn_complete(ev)

    def _on_turn_complete(self, turn: TurnComplete) -> None:
        if self.phase != Phase.LISTENING:
            return
        sents = sentences(turn.text)
        last = sents[-1] if sents else turn.text
        # Aclaracion = el turno TERMINA en una pregunta y es corto. Una
        # pregunta retorica en medio de la respuesta ("so what did I do? I
        # rallied the team") no cuenta, porque la ultima frase no lo es.
        is_clarification = (
            turn.reason != "cierre manual"
            and len(turn.text.split()) <= 40
            and is_question_sentence(last)
            and (last.rstrip().endswith("?")
                 or classify(last, from_candidate=True).qtype == QType.CLARIFICATION)
        )
        if is_clarification:
            before = [s for s in sents[:-1]]
            if before:
                self.ctx.record_answer(" ".join(before))
            self._clarify(last)
            return
        self._answer_before_commit = self.ctx.current.answer if self.ctx.current else ""
        self.ctx.record_answer(turn.text)
        self._live = []
        cur = self.ctx.current
        qtype = QType(cur.qtype) if cur else QType.GENERAL
        self._evaluate(qtype)

    # --- LLM -----------------------------------------------------------------

    def _clarify(self, asked: str) -> None:
        self._set_phase(Phase.CLARIFYING)
        self.capture.mute(True)
        self._live = []
        self.ui.status("Aclarando...")
        self._run_stream(lambda cancel: self.gen.clarify(asked, cancel),
                         on_chunk=lambda acc: None, on_done="clarified", extra=asked)

    def _on_clarified(self, payload):
        asked, reply = payload
        self.ctx.record_clarification(asked, reply)
        self.ui.clarification(asked, reply)
        self.detector.reset()
        self.speaker.speak(reply, on_done=lambda: self._post("spoken"))

    def _evaluate(self, qtype: QType) -> None:
        self._eval_qtype = qtype
        self._set_phase(Phase.EVALUATING)
        self.detector.mark_generating()
        self.ui.status("Evaluando tu respuesta...")
        # Palabras que tu perfil prohibe: se marcan al instante, sin esperar al
        # LLM, y quedan al inicio del feedback.
        self._eval_prefix = ""
        iv = self.ctx.interview
        if iv is not None and self.ctx.current:
            iv.refresh()
            from .interview_profile import banned_hits

            hits = banned_hits(self.ctx.current.answer, iv.banned_words)
            if hits:
                self._eval_prefix = "⚠ **Palabras a evitar (tu perfil):** " + ", ".join(hits) + "\n\n"
        if self._eval_prefix:
            self.ui.evaluation(split_sections(self._eval_prefix), False)
        self._run_stream(lambda cancel: self.gen.evaluate(qtype, cancel),
                         on_chunk=lambda acc: self.ui.evaluation(split_sections(self._eval_prefix + acc), False),
                         on_done="evaluated")

    def _on_evaluated(self, markdown):
        markdown = getattr(self, "_eval_prefix", "") + markdown
        sections = split_sections(markdown)
        self.ctx.record_feedback(
            sections["FEEDBACK"],
            f"QUICK ANSWER\n{sections['QUICK ANSWER']}\n\nDETAILED ANSWER\n{sections['DETAILED ANSWER']}",
            extract_score(sections["FEEDBACK"]),
        )
        self.ui.evaluation(sections, True)
        self.capture.mute(True)
        self._set_phase(Phase.REVIEW)
        self.ui.status("Listo. Siguiente pregunta, repregunta o regenerar.")
        try:
            self.ctx.save(self._session_file)
        except OSError as exc:
            log.warning("no se pudo guardar la sesion: %s", exc)

    def _run_stream(self, factory, on_chunk, on_done: str, extra=None) -> None:
        """Corre un stream del LLM en un hilo. Al terminar postea `on_done`
        con el texto completo (salvo que lo hayan cancelado)."""
        self._cancel_stream()
        cancel = threading.Event()
        self._cancel = cancel
        self._stream_id += 1

        def work():
            acc = ""
            try:
                for chunk in factory(cancel):
                    if cancel.is_set():
                        return
                    acc += chunk
                    on_chunk(acc)
            except Exception as exc:
                if not cancel.is_set():
                    self.ui.error(f"LLM: {exc}")
                    self._post("stream_failed")
                return
            if not cancel.is_set():
                self._post(on_done, (extra, acc.strip()) if extra is not None else acc.strip())

        threading.Thread(target=work, name="speak-llm", daemon=True).start()

    def _on_stream_failed(self, _):
        self._set_phase(Phase.REVIEW)

    def _cancel_stream(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
            self._cancel = None

    def _stop_capture(self) -> None:
        try:
            self.capture.stop()
        except Exception:
            pass
