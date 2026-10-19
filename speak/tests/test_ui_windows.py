"""Pruebas de las ventanas (Qt offscreen): Notas de llamada, Preparar llamada,
simulador y ajustes. Todo lo externo es falso: grabadora, Whisper, Claude,
dialogos de archivos; y DATA_DIR / PREP_FILE / PROFILE_FILE apuntan a una
carpeta temporal, asi que nunca se tocan los datos reales del usuario."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
import wave  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import numpy as np  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import speak.notes.recorder as recorder_mod  # noqa: E402
import speak.ui.main_window as mw  # noqa: E402
import speak.ui.notes_window as nw  # noqa: E402
import speak.ui.prep_window as pw  # noqa: E402
from speak.config import Config  # noqa: E402
from speak.llm_client import LLMClient  # noqa: E402
from speak.notes.copilot import PRESETS, Answer  # noqa: E402
from speak.transcriber import Segment, SpeechToText  # noqa: E402

APP = QApplication.instance() or QApplication([])
SR = 16000


def pump(cond, timeout: float = 6.0) -> bool:
    """Procesa eventos de Qt hasta que `cond()` o se acabe el tiempo."""
    end = time.time() + timeout
    while time.time() < end:
        APP.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    APP.processEvents()
    return bool(cond())


def press(window, key, modifier=Qt.NoModifier, target=None) -> None:
    """Los atajos (F8, F9, Ctrl+Enter) solo saltan con la ventana activa."""
    window.activateWindow()
    window.raise_()
    pump(lambda: QApplication.activeWindow() is window, 2)
    QTest.keyClick(target or window, key, modifier)


def tone(seconds: float, amp: float) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def quiet(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), np.float32)


# --- dobles --------------------------------------------------------------------


class FakeSTT(SpeechToText):
    """En vivo: el texto sale del volumen de la frase. Archivos: segmentos fijos."""

    model_name = "fake"

    def __init__(self, by_amp=None, file_segments=None, fail_files=False):
        self.by_amp = by_amp or {0.2: "How much does the audit cost?", 0.4: "It depends on the plants."}
        self.file_segments = file_segments or {
            "me.wav": [Segment(3, 5, "It is twelve thousand dollars.")],
            "them.wav": [Segment(0, 2, "How much does the audit cost?")],
        }
        self.fail_files = fail_files

    def transcribe(self, audio, sample_rate, prompt=""):
        peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
        return min(self.by_amp.items(), key=lambda kv: abs(kv[0] - peak))[1]

    def transcribe_file(self, path):
        if self.fail_files:
            raise RuntimeError("whisper se cayo")
        return list(self.file_segments.get(Path(path).name, []))


class FakeLLM(LLMClient):
    """Responde segun que prompt le llega; puede ir lento o fallar."""

    def __init__(self, delay: float = 0.0, fail: bool = False):
        self.delay, self.fail = delay, fail
        self.calls: list[tuple[str, str]] = []
        self.images: list = []

    @staticmethod
    def reply_for(system: str, prompt: str) -> str:
        if "silent real-time assistant" in system:
            return "**Respuesta:** 12.000 USD por planta [precios.md]"
        if "run discovery" in system:
            return "**Veredicto:** falta el volumen\n### Pregunta ahora\n1. ¿Cuantas transacciones?"
        if "searchable text" in system:
            return "Componentes:\n- Kafka\n- Lambda"
        if "running notes" in system:
            return "# Resumen hasta ahora\n- auditoria"
        if "study-quality notes" in system:
            return "# Resumen\n- notas finales de la llamada"
        if "Write the brief" in prompt:
            return "# Brief de la llamada\n## Contexto y objetivo\nAcme quiere bajar vapor"
        return "¿Quien asiste a la reunion y que decide?"

    def stream(self, system, prompt, cancel=None, images=None):
        self.calls.append((system, prompt))
        self.images += list(images or [])
        if self.fail:
            raise RuntimeError("claude no responde")
        text = self.reply_for(system, prompt)
        for i in range(0, len(text), 6):
            if cancel is not None and cancel.is_set():
                return
            if self.delay:
                time.sleep(self.delay)
            yield text[i:i + 6]


def _silent_wav(path: Path, seconds: float = 1.0) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"\x00\x00" * int(SR * seconds))


class FakeRecorder:
    """Sustituye a DualRecorder: escribe dos pistas mudas y deja empujar audio
    al modo en vivo como lo haria el callback real."""

    instances: list["FakeRecorder"] = []
    fail = False
    open_delay = 0.0  # PyAudio real tarda 2-3 s en abrir el loopback

    def __init__(self, folder, mic_device=None, capture_system=True, on_audio=None):
        self.folder = Path(folder)
        self.on_audio = on_audio
        self.levels = {"me": 0.05, "them": 0.1}
        self.warnings: list[str] = []
        self._t0 = 0.0
        self.stopped = False
        FakeRecorder.instances.append(self)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0 if self._t0 else 0.0

    def start(self) -> None:
        if FakeRecorder.open_delay:
            time.sleep(FakeRecorder.open_delay)
        if FakeRecorder.fail:
            raise recorder_mod.RecorderError("no pude abrir el microfono: prueba")
        self.folder.mkdir(parents=True, exist_ok=True)
        _silent_wav(self.folder / "me.wav")
        _silent_wav(self.folder / "them.wav")
        self._t0 = time.monotonic()

    def push(self, who: str, audio: np.ndarray) -> None:
        if self.on_audio:
            for i in range(0, len(audio), 1600):
                self.on_audio(who, audio[i:i + 1600], SR)

    def stop(self) -> Path:
        self.stopped = True
        self._t0 = 0.0
        return self.folder


# --- base ---------------------------------------------------------------------


class UITestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="speak-ui-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        data = self.tmp / "data"
        self.stt = FakeSTT()
        self.llm = FakeLLM()
        FakeRecorder.instances = []
        FakeRecorder.fail = False
        patches = [
            mock.patch.object(nw, "DATA_DIR", data),
            mock.patch.object(pw, "PREP_FILE", data / "prep" / "current.json"),
            mock.patch.object(mw, "PROFILE_FILE", data / "profile.json"),
            mock.patch.object(nw, "make_stt", lambda cfg, for_files=False, model=None, language=None: self.stt),
            mock.patch.object(nw, "make_llm", lambda cfg, **kw: self.llm),
            mock.patch.object(pw, "make_llm", lambda cfg, **kw: self.llm),
            mock.patch.object(recorder_mod, "DualRecorder", FakeRecorder),
            mock.patch("os.startfile", create=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.cfg = Config()
        self.cfg.KB_DIR = str(self.tmp / "kb")
        self.cfg.LIVE_NOTES_INTERVAL = 3600  # el borrador solo cuando se pide
        self.cfg.DISCOVERY_INTERVAL = 0
        self.cfg.COPILOT_QUIET_S = 0.3
        self.cfg.save = lambda *a, **k: None  # nunca escribir el .env real
        self.cfg.COPILOT_HOTKEY = ""  # nunca registrar atajos globales reales en las pruebas

    def notes(self) -> nw.NotesWindow:
        w = nw.NotesWindow(self.cfg)
        w.show()
        self.addCleanup(self._close, w)
        return w

    @staticmethod
    def _close(w) -> None:
        w.close()
        APP.processEvents()

    def start_live_call(self, w: nw.NotesWindow, mode: str = "venta") -> FakeRecorder:
        w.mode.setCurrentText(mode)
        w.consent.setChecked(True)
        w.live.setChecked(True)
        QTest.mouseClick(w.btn_rec, Qt.LeftButton)
        self.assertTrue(w.recorder is not None and w.live_notes is not None, w.lbl_status.text())
        # El audio se abre en un hilo: esperar a que termine de arrancar.
        self.assertTrue(pump(lambda: w.btn_stop.isEnabled()), w.lbl_status.text())
        return FakeRecorder.instances[-1]


# --- Notas de llamada -----------------------------------------------------------


class NotesWindowTests(UITestCase):
    def test_slow_audio_open_keeps_window_responsive(self):
        FakeRecorder.open_delay = 1.5
        try:
            w = self.notes()
            w.consent.setChecked(True)
            w.live.setChecked(False)
            t0 = time.monotonic()
            QTest.mouseClick(w.btn_rec, Qt.LeftButton)
            self.assertLess(time.monotonic() - t0, 0.5)  # el clic no bloquea
            self.assertIn("Abriendo", w.lbl_status.text())
            self.assertFalse(w.btn_rec.isEnabled())
            self.assertFalse(w.btn_stop.isEnabled())
            self.assertTrue(pump(lambda: w.btn_stop.isEnabled(), timeout=5))
            self.assertIn("Grabando", w.lbl_status.text())
        finally:
            FakeRecorder.open_delay = 0.0

    def test_close_while_audio_is_opening_stops_it(self):
        FakeRecorder.open_delay = 1.0
        try:
            w = self.notes()
            w.consent.setChecked(True)
            w.live.setChecked(False)
            QTest.mouseClick(w.btn_rec, Qt.LeftButton)
            w.close()
            rec = FakeRecorder.instances[-1]
            self.assertTrue(pump(lambda: rec.stopped, timeout=5))
        finally:
            FakeRecorder.open_delay = 0.0

    def test_record_requires_consent(self):
        w = self.notes()
        QTest.mouseClick(w.btn_rec, Qt.LeftButton)
        self.assertIsNone(w.recorder)
        self.assertIn("aceptaron", w.lbl_status.text())
        self.assertIn("c0392b", w.lbl_status.styleSheet())

    def test_recorder_failure_leaves_window_usable(self):
        w = self.notes()
        FakeRecorder.fail = True
        w.consent.setChecked(True)
        QTest.mouseClick(w.btn_rec, Qt.LeftButton)
        self.assertTrue(pump(lambda: w.recorder is None))
        self.assertIsNone(w.live_notes)
        self.assertIsNone(w.copilot)
        self.assertIn("microfono", w.lbl_status.text())
        self.assertTrue(w.btn_rec.isEnabled())
        self.assertFalse(w.out_transcript.isReadOnly())

    def test_live_failure_does_not_leave_half_state(self):
        w = self.notes()
        with mock.patch.object(nw, "make_llm", side_effect=RuntimeError("falta API_KEY")):
            w.consent.setChecked(True)
            QTest.mouseClick(w.btn_rec, Qt.LeftButton)
        self.assertIsNone(w.recorder)
        self.assertIsNone(w.live_notes)
        self.assertIn("falta API_KEY", w.lbl_status.text())
        self.assertTrue(w.btn_rec.isEnabled())
        self.assertFalse(w.out_transcript.isReadOnly())

    def test_live_call_end_to_end(self):
        w = self.notes()
        rec = self.start_live_call(w, "venta")
        self.assertIn("Grabando en vivo", w.lbl_status.text())
        self.assertFalse(w.btn_rec.isEnabled())
        self.assertFalse(w.live.isEnabled())
        self.assertTrue(w.btn_answer.isEnabled())
        self.assertTrue(w.out_transcript.isReadOnly())
        self.assertEqual(w.btn_notes.text(), "✨ Actualizar notas")

        # El otro pregunta; el copiloto responde solo.
        rec.push("them", np.concatenate([quiet(0.3), tone(1.0, 0.2), quiet(0.8)]))
        self.assertTrue(pump(lambda: "audit cost" in w.out_transcript.toPlainText()))
        self.assertIn("Ellos", w.out_transcript.toPlainText())
        self.assertIn("SIN RESPUESTA", w.out_questions.toPlainText())
        self.assertTrue(pump(lambda: "12.000 USD" in w.out_copilot.toPlainText()))
        self.assertRegex(w.out_copilot.toPlainText(), r"\[00:0\d\]")

        # Yo respondo; el porcentaje aparece.
        rec.push("me", np.concatenate([quiet(0.2), tone(1.0, 0.4), quiet(0.8)]))
        self.assertTrue(pump(lambda: "Vas hablando" in w.out_questions.toPlainText()))

        # Actualizar notas pide el borrador ya.
        QTest.mouseClick(w.btn_notes, Qt.LeftButton)
        self.assertTrue(pump(lambda: "Borrador en vivo" in w.out_notes.toPlainText()))
        self.assertNotIn("*", w.out_notes.toPlainText().splitlines()[0])
        self.assertNotIn("_", w.out_notes.toPlainText().splitlines()[0])

        # F8 fuerza una respuesta aunque no haya pregunta nueva.
        press(w, Qt.Key_F8)
        self.assertTrue(pump(lambda: any(a.forced and a.done for a in w.copilot.answers)))

        # El atajo global (llega desde el hilo del listener) hace lo mismo que F8.
        with mock.patch.object(w.copilot, "answer_now") as answer_now:
            threading.Thread(target=w.live_sig.hotkey.emit).start()
            self.assertTrue(pump(lambda: answer_now.called))

        folder = w.folder
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(rec.stopped)
        self.assertIsNone(w.live_notes)
        self.assertIsNone(w.copilot)
        self.assertFalse(w.btn_answer.isEnabled())
        self.assertEqual(w.btn_notes.text(), "✨ Generar notas")
        self.assertTrue((folder / "transcript_live.md").exists())
        self.assertTrue((folder / "copilot.md").exists())
        self.assertIn("12.000 USD", (folder / "copilot.md").read_text(encoding="utf-8"))

        # La transcripcion en vivo queda como final: el audio NO se vuelve a subir.
        self.assertTrue(pump(lambda: (folder / "transcript.md").exists()))
        self.assertTrue(pump(lambda: w.btn_rec.isEnabled()))
        self.assertIn("audit cost", w.out_transcript.toPlainText())
        self.assertNotIn("twelve thousand", w.out_transcript.toPlainText())
        self.assertIn("no se volvio a subir", w.lbl_status.text())
        self.assertFalse(w.out_transcript.isReadOnly())

        # Si la quiero mas precisa, el boton sube la grabacion completa.
        self.assertTrue(w.btn_full.isEnabled())
        QTest.mouseClick(w.btn_full, Qt.LeftButton)
        self.assertTrue(pump(lambda: "twelve thousand" in w.out_transcript.toPlainText()))

        QTest.mouseClick(w.btn_notes, Qt.LeftButton)
        self.assertTrue(pump(lambda: (folder / "notes.md").exists()))
        self.assertIn("notas finales", w.out_notes.toPlainText())
        self.assertIn("notes.md", w.lbl_status.text())

    def test_second_recording_after_stop(self):
        w = self.notes()
        self.start_live_call(w)
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: w.btn_rec.isEnabled()))
        first = w.folder
        time.sleep(1.1)  # las carpetas llevan la hora al segundo
        self.start_live_call(w)
        self.assertNotEqual(first, w.folder)
        self.assertEqual(w.out_transcript.toPlainText(), "")  # empieza limpia
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: w.btn_rec.isEnabled()))

    def test_record_without_live(self):
        w = self.notes()
        w.consent.setChecked(True)
        w.live.setChecked(False)
        QTest.mouseClick(w.btn_rec, Qt.LeftButton)
        self.assertTrue(pump(lambda: w.btn_stop.isEnabled()))
        self.assertIsNotNone(w.recorder)
        self.assertIsNone(w.live_notes)
        self.assertIsNone(FakeRecorder.instances[-1].on_audio)
        self.assertFalse(w.btn_answer.isEnabled())
        press(w, Qt.Key_F8)
        self.assertIn("mientras grabas en vivo", w.lbl_status.text())
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: "twelve thousand" in w.out_transcript.toPlainText()))

    def test_final_transcription_failure_unblocks_buttons(self):
        w = self.notes()
        self.stt.fail_files = True
        self.start_live_call(w)
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: "whisper se cayo" in w.lbl_status.text()))
        self.assertTrue(pump(lambda: w.btn_rec.isEnabled()))

    def test_global_hotkey_registered_while_open(self):
        import helper.hotkey as hk

        started, stopped = [], []

        class FakeListener:
            def __init__(self, spec, on_press):
                self.spec, self.on_press = spec, on_press

            def start(self):
                started.append(self.spec)

            def stop(self):
                stopped.append(self.spec)

        self.cfg.COPILOT_HOTKEY = "alt+r"
        with mock.patch.object(hk, "HotkeyListener", FakeListener):
            w = self.notes()
            self.assertEqual(started, ["alt+r"])
            self.assertIn("Alt+R", w.btn_answer.text())
            self.assertIn("cualquier ventana", w.out_copilot.toPlainText())
            w.close()
            self.assertEqual(stopped, ["alt+r"])
            w.show()  # la ventana se reutiliza: vuelve a registrarlo
            self.assertEqual(started, ["alt+r", "alt+r"])

    def test_global_hotkey_taken_falls_back_to_window(self):
        import helper.hotkey as hk

        class TakenListener:
            def __init__(self, spec, on_press):
                pass

            def start(self):
                raise hk.HotkeyError("no se pudo registrar 'alt+r': otra aplicacion ya tiene ese atajo")

        self.cfg.COPILOT_HOTKEY = "alt+r"
        with mock.patch.object(hk, "HotkeyListener", TakenListener):
            w = self.notes()
        self.assertIsNone(w._hotkey)
        self.assertIn("solo funciona con esta ventana", w.lbl_status.text())
        self.assertIsNotNone(w._local_shortcut)

    def test_final_from_audio_option_keeps_old_behaviour(self):
        self.cfg.NOTES_FINAL_FROM_AUDIO = True
        w = self.notes()
        rec = self.start_live_call(w, "venta")
        rec.push("them", np.concatenate([quiet(0.3), tone(1.0, 0.2), quiet(0.8)]))
        self.assertTrue(pump(lambda: "audit cost" in w.out_transcript.toPlainText()))
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: "twelve thousand" in w.out_transcript.toPlainText()))

    def test_silence_warning_after_minutes_without_voice(self):
        self.cfg.NOTES_SILENCE_WARN_MIN = 5
        w = self.notes()
        rec = self.start_live_call(w)
        rec.levels = {"me": 0.0, "them": 0.0}  # silencio
        w._last_voice = time.monotonic() - 5 * 60 - 1  # 5 min sin que nadie hable
        with mock.patch.object(nw.QApplication, "alert") as alert:
            self.assertTrue(pump(lambda: "sin que nadie hable" in w.lbl_status.text()))
            self.assertTrue(alert.called)
        self.assertTrue(w._silence_warned)
        # Alguien vuelve a hablar: el aviso se quita.
        w._heard_voice()
        self.assertNotIn("sin que nadie hable", w.lbl_status.text())

    def test_no_silence_warning_when_disabled(self):
        self.cfg.NOTES_SILENCE_WARN_MIN = 0
        w = self.notes()
        rec = self.start_live_call(w)
        rec.levels = {"me": 0.0, "them": 0.0}
        w._last_voice = time.monotonic() - 3600
        pump(lambda: False, 0.6)
        self.assertNotIn("sin que nadie hable", w.lbl_status.text())

    def _record_and_stop(self, w: nw.NotesWindow) -> Path:
        w.consent.setChecked(True)
        w.live.setChecked(False)
        QTest.mouseClick(w.btn_rec, Qt.LeftButton)
        self.assertTrue(pump(lambda: w.btn_stop.isEnabled()))
        folder = w.folder
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: w.btn_rec.isEnabled()))
        return folder

    def test_audio_kept_by_default(self):
        folder = self._record_and_stop(self.notes())
        self.assertTrue((folder / "transcript.md").exists())
        self.assertTrue((folder / "me.wav").exists())
        self.assertTrue((folder / "them.wav").exists())

    def test_audio_discarded_after_transcription(self):
        self.cfg.NOTES_KEEP_AUDIO = False
        w = self.notes()
        folder = self._record_and_stop(w)
        self.assertTrue(pump(lambda: (folder / "transcript.md").exists()))
        self.assertIn("twelve thousand", w.out_transcript.toPlainText())
        self.assertFalse((folder / "me.wav").exists())
        self.assertFalse((folder / "them.wav").exists())

    def test_audio_kept_when_transcription_fails(self):
        self.cfg.NOTES_KEEP_AUDIO = False
        self.stt.fail_files = True
        w = self.notes()
        folder = self._record_and_stop(w)
        self.assertTrue(pump(lambda: "whisper se cayo" in w.lbl_status.text()))
        self.assertTrue((folder / "me.wav").exists())
        self.assertTrue((folder / "them.wav").exists())
        self.assertTrue(w.btn_audio.isEnabled())
        APP.processEvents()
        self.assertIn("c0392b", w.lbl_status.styleSheet())  # sigue en rojo

    def test_notes_llm_failure_is_reported_and_unblocks(self):
        w = self.notes()
        w.out_transcript.setPlainText("[00:01] Ellos: How much does it cost?\n[00:04] Yo: Twelve thousand.")
        self.llm.fail = True
        QTest.mouseClick(w.btn_notes, Qt.LeftButton)
        self.assertTrue(pump(lambda: "claude no responde" in w.lbl_status.text()))
        self.assertTrue(pump(lambda: w.btn_notes.isEnabled() and w.btn_rec.isEnabled()))
        self.assertIn("c0392b", w.lbl_status.styleSheet())

    def test_live_notes_disabled_tells_why(self):
        self.cfg.LIVE_NOTES_INTERVAL = 0
        w = self.notes()
        rec = self.start_live_call(w)
        self.assertIn("desactivadas", w.out_notes.toPlainText())
        rec.push("them", np.concatenate([quiet(0.3), tone(1.0, 0.2), quiet(0.8)]))
        self.assertTrue(pump(lambda: w.btn_notes.isEnabled()))
        QTest.mouseClick(w.btn_notes, Qt.LeftButton)
        self.assertIn("LIVE_NOTES_INTERVAL=0", w.lbl_status.text())

    def test_tab_follows_topic_editor_then_back_to_answers(self):
        from speak.notes.copilot import Answer
        w = self.notes()
        self.start_live_call(w, "llamada")
        code = Answer(1, 0.0, "Write a function...", editor_on=True, editor="## Código\n» Hi.\nx = 1")
        w.copilot.answers = [code]
        w._render_editor(code)
        self.assertIs(w.side.currentWidget(), w.editor_tab)  # pide codigo: se abre sola
        w.side.setCurrentWidget(w.cop_tab)
        w._render_editor(code)  # mas texto de la misma pizarra: no te la vuelve a poner
        self.assertIs(w.side.currentWidget(), w.cop_tab)
        w.side.setCurrentWidget(w.editor_tab)
        undecided = Answer(2, 30.0, "Why do you want to join?", editor_pending=True)
        w.copilot.answers.append(undecided)
        w._render_copilot(undecided)
        self.assertIs(w.side.currentWidget(), w.editor_tab)  # el editor aun decide: espera
        undecided.editor_pending = False  # NO_EDIT: otro tema
        w._render_editor(undecided)
        self.assertIs(w.side.currentWidget(), w.cop_tab)  # vuelve a Respuestas
        w.side.setCurrentWidget(w.editor_tab)
        w._render_copilot(undecided)  # una vez por pregunta: si vuelves a mirar, no te la quita
        self.assertIs(w.side.currentWidget(), w.editor_tab)
        w._stop_live()

    def test_mode_switch_mid_call_gates_copilot_and_discovery(self):
        w = self.notes()
        self.start_live_call(w, "arquitectura")
        self.assertTrue(w.copilot.enabled)
        w.mode.setCurrentText("entrevista")
        self.assertFalse(w.copilot.enabled)
        self.assertFalse(w.discovery.enabled)
        self.assertEqual(w.live_notes.mode, "entrevista")
        self.assertIn("entrevista", w.out_copilot.toPlainText())
        press(w, Qt.Key_F9)
        self.assertIn("apagada", w.lbl_status.text())
        w.mode.setCurrentText("soporte")
        self.assertTrue(w.copilot.enabled)
        self.assertEqual(w.prep.mode, "soporte")

    def test_discovery_without_call_and_no_duplicate_runs(self):
        self.llm.delay = 0.02
        w = self.notes()
        w.mode.setCurrentText("arquitectura")
        press(w, Qt.Key_F9)
        press(w, Qt.Key_F9)  # repetido mientras corre: no lanza otra
        self.assertEqual(w.side.currentIndex(), 1)
        self.assertTrue(pump(lambda: "Actualizado" in w.lbl_discovery.text()))
        self.assertIn("Veredicto", w.out_discovery.toPlainText())
        runs = [c for c in self.llm.calls if "run discovery" in c[0]]
        self.assertEqual(len(runs), 1)

    def test_discovery_during_call_via_button(self):
        w = self.notes()
        self.start_live_call(w, "arquitectura")
        QTest.mouseClick(w.btn_discovery, Qt.LeftButton)
        self.assertTrue(pump(lambda: "Veredicto" in w.out_discovery.toPlainText()))
        folder = w.folder
        QTest.mouseClick(w.btn_stop, Qt.LeftButton)
        self.assertTrue((folder / "exploracion.md").exists())

    def test_attach_documents_and_image_outside_and_during_call(self):
        doc = self.tmp / "precios.md"
        doc.write_text("La auditoria cuesta 12.000 USD por planta.", encoding="utf-8")
        img = self.tmp / "diagrama.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
        bad = self.tmp / "roto.pdf"
        bad.write_bytes(b"no es un pdf")
        w = self.notes()
        with mock.patch.object(nw.QFileDialog, "getOpenFileNames", return_value=([str(doc), str(img), str(bad)], "")):
            QTest.mouseClick(w.btn_attach, Qt.LeftButton)
        self.assertTrue(pump(lambda: "Anadido" in w.lbl_status.text(), timeout=20))
        self.assertIn("precios.md", w.lbl_status.text())
        self.assertIn("diagrama.png", w.lbl_status.text())
        self.assertIn("roto.pdf", w.lbl_status.text())  # el error se ve
        self.assertIn("2 de la llamada", w.lbl_docs.text())
        self.assertEqual(self.llm.images, [img])
        self.assertTrue(pw.PREP_FILE.exists())  # queda guardado
        self.assertIn("Kafka", w.kb.extra_texts()["diagrama.png"])

        # En plena llamada: pegar texto y que la exploracion se relance sola.
        self.start_live_call(w, "arquitectura")

        def fake_exec(dlg):
            dlg.name.setText("correo cliente")
            dlg.text.setPlainText("Procesan 200 transacciones por segundo.")
            return QDialog.Accepted

        with mock.patch.object(pw.PasteDialog, "exec", fake_exec):
            QTest.mouseClick(w.btn_paste, Qt.LeftButton)
        self.assertIn("3 de la llamada", w.lbl_docs.text())
        self.assertTrue(pump(lambda: "Veredicto" in w.out_discovery.toPlainText()))

    def test_paste_cancelled_or_empty_adds_nothing(self):
        w = self.notes()
        with mock.patch.object(pw.PasteDialog, "exec", lambda dlg: QDialog.Rejected):
            QTest.mouseClick(w.btn_paste, Qt.LeftButton)
        with mock.patch.object(pw.PasteDialog, "exec", lambda dlg: QDialog.Accepted):
            QTest.mouseClick(w.btn_paste, Qt.LeftButton)  # aceptado pero vacio
        self.assertEqual(w.kb.extra_names(), [])

    def test_real_dialog_exec_returns_comparable_code(self):
        # _paste compara exec() (int) con PasteDialog.Accepted (enum).
        self.assertTrue(1 == pw.PasteDialog.Accepted)
        self.assertTrue(0 != pw.PasteDialog.Accepted)

    def test_copilot_pane_times_and_history_cap(self):
        w = self.notes()
        w.copilot = mock.Mock()
        w.copilot.answers = [Answer(i, 59.7 + i * 30, f"pregunta {i}", "resp", done=True) for i in range(20)]
        w._render_copilot()
        text = w.out_copilot.toPlainText()
        self.assertNotIn(":60]", text)
        self.assertIn("[09:59] ❓ pregunta 18", text.replace("[10:29]", ""))  # 59.7+540
        self.assertIn("pregunta 19", text.splitlines()[0])  # la mas reciente arriba
        self.assertNotIn("pregunta 4 ", text + " ")  # solo las ultimas 15
        w.copilot = None

    def test_import_transcript_and_audio(self):
        vtt = self.tmp / "call.vtt"
        vtt.write_text("WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Ana>What is the budget?</v>\n",
                       encoding="utf-8")
        w = self.notes()
        with mock.patch.object(nw.QFileDialog, "getOpenFileName", return_value=(str(vtt), "")):
            QTest.mouseClick(w.btn_text, Qt.LeftButton)
        self.assertIn("Ana: What is the budget?", w.out_transcript.toPlainText())
        self.assertIn("Preguntas detectadas: 1", w.out_questions.toPlainText())
        self.assertTrue((w.folder / "transcript.md").exists())

        audio = self.tmp / "grabacion.wav"
        _silent_wav(audio)
        self.stt.file_segments = {"grabacion.wav": [Segment(0, 2, "Welcome to the call.")]}
        with mock.patch.object(nw.QFileDialog, "getOpenFileName", return_value=(str(audio), "")):
            QTest.mouseClick(w.btn_audio, Qt.LeftButton)
        self.assertTrue(pump(lambda: "Welcome to the call" in w.out_transcript.toPlainText()))

    def test_import_unreadable_transcript_reports_error(self):
        w = self.notes()
        with mock.patch.object(nw.QFileDialog, "getOpenFileName", return_value=(str(self.tmp / "no-existe.txt"), "")):
            QTest.mouseClick(w.btn_text, Qt.LeftButton)
        self.assertIn("no pude leer", w.lbl_status.text())

    def test_edited_transcript_wins_for_notes(self):
        w = self.notes()
        w.out_transcript.setPlainText("[00:01] Ana: What is the budget?\n[00:03] Yo: About 12k.")
        QTest.mouseClick(w.btn_notes, Qt.LeftButton)
        self.assertTrue(pump(lambda: "notas finales" in w.out_notes.toPlainText()))
        prompt = [c[1] for c in self.llm.calls if "study-quality" in c[0]][-1]
        self.assertIn("Ana: What is the budget?", prompt)

    def test_open_folder_and_on_top(self):
        w = self.notes()
        QTest.mouseClick(w.btn_open, Qt.LeftButton)
        os.startfile.assert_called()
        w.on_top.setChecked(True)
        self.assertTrue(w.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertTrue(w.isVisible())
        w.on_top.setChecked(False)
        self.assertFalse(w.windowFlags() & Qt.WindowStaysOnTopHint)

    def test_close_while_recording_saves_and_stops_everything(self):
        w = self.notes()
        rec = self.start_live_call(w)
        rec.push("them", np.concatenate([quiet(0.3), tone(1.0, 0.2), quiet(0.8)]))
        self.assertTrue(pump(lambda: "audit cost" in w.out_transcript.toPlainText()))
        copilot, live = w.copilot, w.live_notes
        folder = w.folder
        w._open_prep()
        prep = w.prep_window
        w.close()
        APP.processEvents()
        self.assertTrue(rec.stopped)
        self.assertTrue(copilot._stop.is_set())
        self.assertTrue(live._stopped.is_set())
        self.assertTrue((folder / "transcript_live.md").exists())
        self.assertFalse(prep.isVisible())  # tambien cierra Preparar llamada

    def test_close_while_llm_streaming(self):
        self.llm.delay = 0.05
        w = self.notes()
        w.out_transcript.setPlainText("[00:01] Ana: Hi?")
        QTest.mouseClick(w.btn_notes, Qt.LeftButton)
        w.close()
        # El hilo termina solo y sus señales llegan a una ventana cerrada sin romper nada.
        pump(lambda: False, timeout=1.5)
        self.assertFalse(w.isVisible())

    def test_idle_messages_reflect_prep(self):
        w = self.notes()
        w.mode.setCurrentText("venta")
        self.assertIn("sin brief", w.out_copilot.toPlainText())
        self.assertIn("sin guia", w.out_copilot.toPlainText())
        w.prep.brief = "Cliente Acme"
        w.prep.use_preset(PRESETS[0])
        w._copilot_idle()
        self.assertIn("con tu brief", w.out_copilot.toPlainText())
        self.assertIn(PRESETS[0]["nombre"], w.out_copilot.toPlainText())
        self.cfg.COPILOT_ENABLED = False
        w._copilot_idle()
        self.assertIn("desactivado", w.out_copilot.toPlainText())

    def test_live_transcript_keeps_scroll_when_reading_back(self):
        w = self.notes()
        self.start_live_call(w)
        from speak.notes.pipeline import Transcript

        many = Transcript([Segment(i * 3, i * 3 + 1, f"frase numero {i}", "Ellos") for i in range(200)], "t")
        w._live_transcript(many)
        bar = w.out_transcript.verticalScrollBar()
        self.assertEqual(bar.value(), bar.maximum())  # sigue el final
        bar.setValue(10)  # el usuario sube a leer
        more = Transcript(many.segments + [Segment(700, 701, "nueva", "Ellos")], "t")
        w._live_transcript(more)
        self.assertEqual(bar.value(), 10)  # no lo arrastra al final


# --- Preparar llamada -------------------------------------------------------------


class PrepWindowTests(UITestCase):
    def open_prep(self):
        w = self.notes()
        w._open_prep()
        p = w.prep_window
        return w, p

    def test_mode_sync_both_ways(self):
        w, p = self.open_prep()
        p.mode.setCurrentText("arquitectura")
        self.assertEqual(w.mode.currentText(), "arquitectura")
        self.assertEqual(w.prep.mode, "arquitectura")
        w.mode.setCurrentText("entrevista")
        self.assertEqual(p.mode.currentText(), "entrevista")
        self.assertIn("entrevista", p.lbl_copilot.text())

    def test_pick_folder_reindex(self):
        kb = self.tmp / "otra_kb"
        kb.mkdir()
        (kb / "portafolio.md").write_text("Auditorias de vapor.", encoding="utf-8")
        w, p = self.open_prep()
        saved = []
        self.cfg.save = lambda *a, **k: saved.append(self.cfg.KB_DIR)
        with mock.patch.object(pw.QFileDialog, "getExistingDirectory", return_value=str(kb)):
            p._pick_folder()
        self.assertTrue(pump(lambda: "Carpeta indexada" in p.lbl_status.text()))
        self.assertIn("1 documentos", p.lbl_folder.text())
        self.assertEqual(saved, [str(kb)])
        self.assertIn("portafolio.md", w.kb.sources())

    def test_attach_paste_remove(self):
        doc = self.tmp / "propuesta.md"
        doc.write_text("Precio 12.000 USD", encoding="utf-8")
        w, p = self.open_prep()
        with mock.patch.object(pw.QFileDialog, "getOpenFileNames", return_value=([str(doc)], "")):
            p._attach()
        self.assertTrue(pump(lambda: "Adjuntado" in p.lbl_status.text()))

        def fake_exec(dlg):
            dlg.text.setPlainText("Notas del cliente")
            return QDialog.Accepted

        with mock.patch.object(pw.PasteDialog, "exec", fake_exec):
            p._paste()
        names = [p.extra_list.item(i).text() for i in range(p.extra_list.count())]
        self.assertEqual(names, ["propuesta.md", "texto 2"])
        p.extra_list.setCurrentRow(0)
        p._remove()
        self.assertEqual(w.kb.extra_names(), ["texto 2"])

    def test_chat_and_cancel_mid_stream(self):
        w, p = self.open_prep()
        p.input.setPlainText("Reunion con Acme sobre vapor")
        QTest.mouseClick(p.btn_send, Qt.LeftButton)
        self.assertTrue(pump(lambda: not p._busy))
        self.assertEqual([r for r, _ in w.prep.messages], ["user", "assistant"])
        self.assertIn("Quien asiste", p.chat.toPlainText())

        self.llm.delay = 0.1
        p.input.setPlainText("Otra pregunta larga")
        QTest.mouseClick(p.btn_send, Qt.LeftButton)
        pump(lambda: False, timeout=0.15)
        self.assertIn("Otra pregunta larga", p.chat.toPlainText())  # se ve mientras llega
        self.assertTrue(p.btn_stop.isEnabled())
        self.assertFalse(p.btn_send.isEnabled())
        pump(lambda: False, timeout=0.2)
        QTest.mouseClick(p.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: not p._busy, timeout=3))
        self.assertTrue(p.btn_send.isEnabled())
        self.assertFalse(p.btn_stop.isEnabled())

    def test_ctrl_enter_sends(self):
        w, p = self.open_prep()
        p.input.setPlainText("Hola")
        p.input.setFocus()
        press(p, Qt.Key_Return, Qt.ControlModifier, target=p.input)
        self.assertTrue(pump(lambda: len(w.prep.messages) == 2))

    def test_brief_build_edit_and_cancel_keeps_previous(self):
        w, p = self.open_prep()
        QTest.mouseClick(p.btn_brief, Qt.LeftButton)
        self.assertTrue(p.brief.isReadOnly())  # no se escribe encima mientras llega
        self.assertTrue(pump(lambda: not p._busy))
        self.assertFalse(p.brief.isReadOnly())
        self.assertTrue(w.prep.brief.startswith("# Brief"))
        self.assertIn("Acme", p.brief.toPlainText())

        p.brief.setPlainText("Mi brief editado a mano")
        self.assertEqual(w.prep.brief, "Mi brief editado a mano")
        self.llm.delay = 0.1
        QTest.mouseClick(p.btn_brief, Qt.LeftButton)
        pump(lambda: False, timeout=0.3)
        QTest.mouseClick(p.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: not p._busy, timeout=3))
        self.assertEqual(w.prep.brief, "Mi brief editado a mano")
        self.assertEqual(p.brief.toPlainText(), "Mi brief editado a mano")
        self.assertIn("brief anterior", p.lbl_status.text())

    def test_brief_failure_restores_editor(self):
        w, p = self.open_prep()
        p.brief.setPlainText("brief bueno")
        self.llm.fail = True
        QTest.mouseClick(p.btn_brief, Qt.LeftButton)
        self.assertTrue(pump(lambda: not p._busy))
        self.assertIn("claude no responde", p.lbl_status.text())
        self.assertEqual(p.brief.toPlainText(), "brief bueno")
        self.assertFalse(p.brief.isReadOnly())

    def test_guide_presets_edit_and_label(self):
        w, p = self.open_prep()
        self.assertIn("Sin guia", p.lbl_guide.text())
        p._use_preset(1)
        self.assertEqual(w.prep.guide_name, PRESETS[0]["nombre"])
        self.assertIn("Plantilla", p.lbl_guide.text())
        self.assertEqual(p.presets.currentIndex(), 0)
        p.guide.appendPlainText("Menciona Cementos X.")
        self.assertIn("Guia propia", p.lbl_guide.text())
        self.assertIn("Cementos X", w.prep.guide)
        p._use_preset(0)  # "Plantillas..." no hace nada
        self.assertIn("Cementos X", w.prep.guide)

    def test_new_preparation_keeps_guide_and_refuses_while_busy(self):
        w, p = self.open_prep()
        p._use_preset(2)
        w.prep.messages.append(("user", "hola"))
        p.brief.setPlainText("brief")
        w.kb.add_text("nota", "x")
        self.llm.delay = 0.1
        p.input.setPlainText("algo")
        QTest.mouseClick(p.btn_send, Qt.LeftButton)
        p._new()  # ocupado: primero detiene
        self.assertIn("Deteniendo", p.lbl_status.text())
        self.assertTrue(pump(lambda: not p._busy, timeout=3))
        p._new()
        self.assertEqual(w.prep.messages, [])
        self.assertEqual(w.prep.brief, "")
        self.assertEqual(w.kb.extra_names(), [])
        self.assertEqual(w.prep.guide_name, PRESETS[1]["nombre"])

    def test_gaps_adds_to_chat_and_can_be_cancelled(self):
        w, p = self.open_prep()
        p.mode.setCurrentText("arquitectura")
        QTest.mouseClick(p.btn_gaps, Qt.LeftButton)
        self.assertTrue(pump(lambda: not p._busy))
        self.assertIn("Exploracion", w.prep.messages[-1][1])
        self.assertIn("Veredicto", p.chat.toPlainText())

        n = len(w.prep.messages)
        self.llm.delay = 0.1
        QTest.mouseClick(p.btn_gaps, Qt.LeftButton)
        pump(lambda: False, timeout=0.2)
        QTest.mouseClick(p.btn_stop, Qt.LeftButton)
        self.assertTrue(pump(lambda: not p._busy, timeout=3))
        self.assertEqual(len(w.prep.messages), n)  # detenida: no deja nada a medias

        p.mode.setCurrentText("entrevista")
        QTest.mouseClick(p.btn_gaps, Qt.LeftButton)
        self.assertIn("entrevista", p.lbl_status.text())

    def test_persistence_roundtrip(self):
        w, p = self.open_prep()
        p.mode.setCurrentText("arquitectura")
        p._use_preset(1)
        p.brief.setPlainText("Brief persistente")
        w.kb.add_text("correo", "Procesan 200 tps")
        w.prep.messages.append(("user", "contexto"))
        p.close()
        w2 = nw.NotesWindow(self.cfg)
        self.addCleanup(self._close, w2)
        self.assertEqual(w2.prep.brief, "Brief persistente")
        self.assertEqual(w2.prep.guide_name, PRESETS[0]["nombre"])
        self.assertEqual(w2.mode.currentText(), "arquitectura")
        self.assertEqual(w2.kb.extra_names(), ["correo"])
        self.assertEqual(w2.prep.messages, [("user", "contexto")])

    def test_close_prep_mid_task(self):
        w, p = self.open_prep()
        self.llm.delay = 0.05
        p.input.setPlainText("algo")
        QTest.mouseClick(p.btn_send, Qt.LeftButton)
        p.close()
        self.assertTrue(pump(lambda: not p._busy, timeout=5))
        self.assertTrue(pw.PREP_FILE.exists())


# --- simulador y ajustes -------------------------------------------------------------


class SimulatorWindowTests(UITestCase):
    def test_main_window_opens_and_basic_actions(self):
        from speak.simulator import Simulator

        class NoCapture:
            def __init__(self, on_event, **kwargs):
                self.running = False

            def start(self):
                self.running = True

            def stop(self):
                self.running = False

            def mute(self, m):
                pass

            def flush_now(self):
                pass

        class Voice:
            culture = "en-US"

            def speak(self, text, on_done=None):
                if on_done:
                    on_done()

            def stop(self):
                pass

        llm = FakeLLM()
        with mock.patch("speak.simulator.DATA_DIR", self.tmp / "data"):
            win = mw.MainWindow(self.cfg, lambda listener: Simulator(
                self.cfg, llm, FakeSTT(), listener, speaker=Voice(), capture_factory=NoCapture))
            win.show()
            win.in_role.setText("SDE II")
            QTest.mouseClick(win.btn_start, Qt.LeftButton)
            self.assertTrue(pump(lambda: win.lbl_phase.text() == "Escuchandote"), win.lbl_phase.text())
            self.assertTrue(win.btn_done.isEnabled())
            QTest.mouseClick(win.btn_pause, Qt.LeftButton)
            self.assertTrue(pump(lambda: win.lbl_phase.text() == "En pausa"))
            QTest.mouseClick(win.btn_clear, Qt.LeftButton)
            self.assertEqual(win.out_transcript.toPlainText(), "")
            QTest.mouseClick(win.btn_notes, Qt.LeftButton)
            self.assertTrue(win._notes_window.isVisible())
            win._notes_window.close()
            win.close()
        self.assertTrue((self.tmp / "data" / "profile.json").exists())

    def test_settings_dialog_saves_and_offers_only_16k_mics(self):
        from speak.ui.settings_dialog import SettingsDialog

        saved = []
        self.cfg.save = lambda *a, **k: saved.append(True)
        dlg = SettingsDialog(self.cfg)
        items = [dlg.mic.itemText(i) for i in range(dlg.mic.count())]
        self.assertEqual(items[0], "Predeterminado de Windows")
        # Ningun microfono aparece dos veces (antes: uno por cada API de audio).
        names = [t.split(": ", 1)[1] for t in items[1:]]
        self.assertEqual(len(names), len(set(names)), items)
        dlg.stt_model.setCurrentText("base")
        dlg.lang.setCurrentText("es")
        dlg._save()
        self.assertEqual(saved, [True])
        self.assertEqual(self.cfg.STT_MODEL, "base")
        self.assertEqual(self.cfg.STT_LANGUAGE, "es")


class AnswerBlockTests(unittest.TestCase):
    def test_what_to_say_is_quoted_and_the_rest_is_not(self):
        out = nw._answer_block("AL VUELO", "", "⚠ Auth method not in your sources.\nSure, it was Azure Key Vault.\n"
                               "The credentials lived in the vault.\nFuente: [prepared_answers]", "léela")
        lines = out.split("  \n")
        self.assertEqual(lines[1], "*⚠ Auth method not in your sources. — aviso para ti, no lo leas*")
        self.assertEqual(lines[2:5], ["“Sure, it was Azure *(á-shur)* Key Vault *(kíi volt)*.", "The credentials lived in the vault.”",
                                      "Fuente: [prepared_answers]"])
        self.assertIn("“One line.”", nw._answer_block("MEMORIA", "k", "One line.", "x"))
        self.assertIn("  \n…  \n", nw._answer_block("AL VUELO", "", "", "x"))  # aun sin texto: sin comillas


if __name__ == "__main__":
    unittest.main()
