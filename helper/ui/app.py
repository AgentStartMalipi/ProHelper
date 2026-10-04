"""Controlador: conecta atajo, captura, Claude y panel.

Tkinter no es thread-safe, asi que nada toca la UI fuera del hilo principal.
El listener del atajo y el worker que habla con Claude solo publican eventos
en una cola que el hilo de Tk drena con `after`.
"""

from __future__ import annotations

import dataclasses
import queue
import threading
import traceback
from pathlib import Path

from .. import capture, lang, memoria, privacy
from ..claude_client import ClaudeClient, ClaudeError, new_session_id
from ..config import DEFAULT_QUESTION, Config
from ..hotkey import HotkeyError, HotkeyListener, HotkeyManager
from ..log import log
from ..session import Session
from . import theme
from .dialogs import EditSessionDialog, SessionDialog, SettingsDialog
from .panel import HelperPanel

# Cuanto esperar tras esconder el panel para que Windows repinte lo que
# quedaba debajo. Por debajo de ~60ms el propio widget sale en su foto.
HIDE_MS = 90

POLL_MS = 40

# Cuanto mueve cada pulsacion de flecha, y a los cuantos segundos sin tocar
# nada se apaga el modo mover solo. El apagado automatico no es un adorno:
# mientras el modo esta activo las flechas no funcionan en el resto de Windows.
PASO_PX = 24
MOVER_TIMEOUT_MS = 15_000

# Cuantas sesiones pueden estar abiertas a la vez. El tope no es tecnico: cada
# sesion abierta solo mantiene su carpeta de capturas. Es para que rotar con las
# flechas siga siendo util; pasado cierto punto das mas vueltas de las que
# ahorras, y el titulo de cada sesion es lo que evita perderse.
MAX_SESIONES = 6

_FLECHAS = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


def _bonito(spec: str) -> str:
    """'ctrl+shift+c' -> 'Ctrl+Shift+C'."""
    return "+".join(p.capitalize() if len(p) > 1 else p.upper()
                    for p in spec.split("+"))


class App:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client = ClaudeClient(cfg)
        # Varias sesiones abiertas a la vez, una activa. Son conversaciones
        # independientes: cada una con su pre-prompt, su target y su costo.
        self.sessions: list[Session] = []
        self.indice = 0
        self.busy = False
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()

        self.panel = HelperPanel(
            on_new_session=self.new_session,
            on_end_session=self.end_session,
            on_settings=self.open_settings,
            on_quit=self.quit,
            on_ask=self.request_capture,
            on_edit_session=self.edit_session,
            on_capture=self.request_capture,
        )
        self.panel.on_history_toggle = self._history_toggled
        self.panel.place_at(
            cfg["window"]["x"], cfg["window"]["y"], cfg["panel_monitor"]
        )
        # El panel se ve en tu monitor pero no en lo que grabe o comparta otra
        # app. Va con `after` a proposito: hasta que Tk no termina de crear la
        # ventana nativa no hay HWND al que aplicarselo.
        self.panel.after(100, lambda: privacy.exclude_window_from_capture(self.panel))

        self.hotkeys: HotkeyManager | None = None
        # Modo activo con las flechas tomadas: "mover", "cambiar" o ninguno.
        self.modo: str | None = None
        self._flechas: list[HotkeyListener] = []
        self._mover_timeout: str | None = None
        self._start_hotkey()
        self._drain_job: str | None = self.panel.after(POLL_MS, self._drain)

    # ---------------------------------------------------------------- atajo

    def _start_hotkey(self) -> None:
        acciones: dict[str, object] = {
            spec: self._on_hotkey for spec in self.cfg["hotkeys"]
        }
        mover = self.cfg["move_hotkey"]
        if mover:
            acciones[mover] = self._on_move
        cambiar = self.cfg["switch_hotkey"]
        if cambiar:
            acciones[cambiar] = self._on_switch
        colapsar = self.cfg["collapse_hotkey"]
        if colapsar:
            acciones[colapsar] = self._on_collapse
        scroll = self.cfg["scroll_hotkey"]
        if scroll:
            acciones[scroll] = self._on_scroll
        manager = HotkeyManager(acciones)
        manager.start()
        self.hotkeys = manager

        for spec, motivo in manager.fallidos:
            log.warning("no se pudo registrar el atajo %r: %s", spec, motivo)
        if manager.activos:
            log.info("atajos registrados: %s", ", ".join(manager.activos))

        if not manager.alguno_activo:
            # Sin atajos el helper todavia sirve: esta el boton "Capturar ahora".
            self.panel.flash(
                "Ningun atajo disponible. Usa el boton Capturar.",
                theme.ERROR,
                ms=8000,
            )
        elif manager.fallidos:
            # Los que si entraron siguen sirviendo; solo se avisa de los otros.
            perdidos = ", ".join(_bonito(s) for s, _ in manager.fallidos)
            self.panel.flash(f"Ocupado por otra app: {perdidos}", theme.WARN, ms=6000)

    def _on_hotkey(self, spec: str) -> None:
        """Corre en el hilo del listener: solo deja constancia y encola."""
        log.info("atajo recibido: %s", spec)
        self.events.put(("hotkey", None))

    def _on_move(self, spec: str) -> None:
        log.info("atajo de mover recibido: %s", spec)
        self.events.put(("mover", None))

    def _on_switch(self, spec: str) -> None:
        log.info("atajo de cambiar sesion recibido: %s", spec)
        self.events.put(("cambiar", None))

    def _on_scroll(self, spec: str) -> None:
        log.info("atajo de scroll recibido: %s", spec)
        self.events.put(("scroll", None))

    def _on_collapse(self, spec: str) -> None:
        log.info("atajo de colapsar recibido: %s", spec)
        self.events.put(("colapsar", None))

    def _on_flecha(self, spec: str) -> None:
        self.events.put(("flecha", spec))

    def _on_salir_modo(self) -> None:
        self.events.put(("salir_modo", None))

    @property
    def hotkey_hint(self) -> str:
        activos = [
            s for s in (self.hotkeys.activos if self.hotkeys else [])
            if s in self.cfg["hotkeys"]
        ]
        if not activos:
            return "Atajos no disponibles — usa el boton Capturar"
        return " o ".join(_bonito(s) for s in activos)

    # ------------------------------------------------- modos con las flechas

    def _tomar_flechas(self, teclas: tuple[str, ...]) -> bool:
        """Registra esas flechas y Esc como atajos globales, o ninguna.

        Se hace con atajos globales, no con foco: asi no le quita el teclado a
        lo que estes haciendo. La contrapartida es que esas teclas dejan de
        funcionar en el resto de Windows mientras dure, por eso hay que poder
        apagarlo (mismo atajo, Esc) y un apagado automatico por si te olvidas.
        """
        for tecla in teclas:
            listener = HotkeyListener(
                tecla, lambda s=tecla: self._on_flecha(s), allow_bare=True,
                norepeat=False,
            )
            try:
                listener.start()
            except HotkeyError as exc:
                # Si una flecha ya la tiene otra app, se deshace lo hecho y no
                # se entra en un modo a medias.
                log.warning("no pude tomar %s: %s", tecla, exc)
                self._soltar_flechas()
                return False
            self._flechas.append(listener)

        # Esc tambien apaga, ademas del atajo del modo.
        esc = HotkeyListener("esc", lambda _s: self._on_salir_modo(), allow_bare=True)
        try:
            esc.start()
            self._flechas.append(esc)
        except HotkeyError:
            pass  # sin Esc se puede vivir: queda el atajo del modo
        return True

    def _soltar_flechas(self) -> None:
        for listener in self._flechas:
            listener.stop()
        self._flechas.clear()

    def _stop_modo(self) -> None:
        """Apaga el modo que este activo y devuelve las flechas a Windows."""
        if self.modo is None:
            return
        anterior, self.modo = self.modo, None
        self._soltar_flechas()
        if self._mover_timeout is not None:
            self.panel.after_cancel(self._mover_timeout)
            self._mover_timeout = None
        self.panel.set_move_mode(False)
        if anterior == "scroll":
            # Salir del modo te devuelve a lo ultimo: es lo que estabas
            # haciendo antes de subir a releer.
            self.panel.ir_a_ultima()
        avisos = {
            "mover": "Panel fijado",
            "cambiar": "Sesion fijada",
            "scroll": "De vuelta a la ultima respuesta",
        }
        self.panel.flash(avisos[anterior], theme.OK, ms=1200)
        log.info("modo %s desactivado", anterior)

    def _reset_move_timeout(self) -> None:
        if self._mover_timeout is not None:
            self.panel.after_cancel(self._mover_timeout)
        self._mover_timeout = self.panel.after(MOVER_TIMEOUT_MS, self._stop_modo)

    # ----------------------------------------------------------- modo mover

    def _toggle_move_mode(self) -> None:
        if self.modo == "mover":
            self._stop_modo()
            return
        self._stop_modo()  # los dos modos se pelean por las mismas flechas
        if not self._tomar_flechas(tuple(_FLECHAS)):
            self.panel.flash("No pude activar el modo mover", theme.WARN)
            return
        self.modo = "mover"
        self.panel.set_move_mode(True)
        salir = _bonito(self.cfg["move_hotkey"]) if self.cfg["move_hotkey"] else "Esc"
        self.panel.flash(f"Mover: flechas · {salir} o Esc para salir",
                         theme.ACCENT, ms=3000)
        log.info("modo mover activado")
        self._reset_move_timeout()

    def _mover_con_flecha(self, tecla: str) -> None:
        dx, dy = _FLECHAS[tecla]
        self.panel.nudge(dx * PASO_PX, dy * PASO_PX, self.cfg["panel_monitor"])

    # -------------------------------------------------------- modo cambiar

    def _toggle_switch_mode(self) -> None:
        """Toma izquierda/derecha para rotar entre las sesiones abiertas."""
        if self.modo == "cambiar":
            self._stop_modo()
            return
        if len(self.sessions) < 2:
            self.panel.flash("Solo hay una sesion abierta", theme.WARN)
            return
        if self.busy:
            # Cambiar con una consulta en vuelo dejaria la respuesta llegando a
            # una sesion que ya no estas mirando.
            self.panel.flash("Espera a que termine la consulta", theme.WARN)
            return
        self._stop_modo()
        if not self._tomar_flechas(("left", "right")):
            self.panel.flash("No pude activar el cambio de sesion", theme.WARN)
            return
        self.modo = "cambiar"
        self.panel.set_move_mode(True)
        salir = _bonito(self.cfg["switch_hotkey"]) if self.cfg["switch_hotkey"] else "Esc"
        self.panel.flash(f"Cambiar sesion: ← → · {salir} o Esc para salir",
                         theme.ACCENT, ms=3000)
        log.info("modo cambiar activado (%d sesiones)", len(self.sessions))
        self._reset_move_timeout()

    def _toggle_scroll_mode(self) -> None:
        """Toma arriba/abajo para releer las respuestas anteriores."""
        if self.modo == "scroll":
            self._stop_modo()
            return
        if not self.panel.hay_historial:
            self.panel.flash("Todavia no hay nada que releer", theme.WARN)
            return
        self._stop_modo()
        if not self._tomar_flechas(("up", "down")):
            self.panel.flash("No pude activar el scroll", theme.WARN)
            return
        self.modo = "scroll"
        self.panel.set_move_mode(True)
        salir = (_bonito(self.cfg["scroll_hotkey"])
                 if self.cfg["scroll_hotkey"] else "Esc")
        self.panel.flash(f"Releer: \u2191 \u2193 \u00b7 {salir} o Esc para volver",
                         theme.ACCENT, ms=3000)
        log.info("modo scroll activado")
        self._reset_move_timeout()

    def _cambiar_sesion(self, delta: int) -> None:
        if len(self.sessions) < 2:
            return
        self.indice = (self.indice + delta) % len(self.sessions)
        sesion = self.sessions[self.indice]
        log.info("sesion activa: %d/%d (%s)", self.indice + 1,
                 len(self.sessions), sesion.label)
        self._mostrar_sesion_activa()
        # El nombre, grande y por encima del estado: rotando a ciegas el
        # numero solo no te dice a cual acabas de llegar.
        self.panel.flash(
            f"{self.indice + 1}/{len(self.sessions)} · {sesion.label}",
            theme.ACCENT, ms=2500,
        )

    def _con_flecha(self, tecla: str) -> None:
        """Reparte la flecha segun el modo que este activo."""
        if tecla not in _FLECHAS:
            return
        if self.modo == "mover":
            self._mover_con_flecha(tecla)
        elif self.modo == "cambiar":
            self._cambiar_sesion(-1 if tecla == "left" else 1)
        elif self.modo == "scroll":
            self.panel.scroll_historial(-3 if tecla == "up" else 3)
        else:
            return
        self._reset_move_timeout()  # cada pulsacion reinicia la cuenta atras

    # -------------------------------------------------------------- sesiones

    @property
    def session(self) -> Session | None:
        """La sesion activa: la que capturan los atajos y muestra el panel."""
        if not self.sessions:
            return None
        return self.sessions[min(self.indice, len(self.sessions) - 1)]

    @session.setter
    def session(self, value: Session | None) -> None:
        """Reemplaza la sesion activa. None cierra todas."""
        if value is None:
            self.sessions.clear()
            self.indice = 0
        elif self.sessions:
            self.sessions[self.indice] = value
        else:
            self.sessions.append(value)
            self.indice = 0

    def new_session(self) -> None:
        if self.busy:
            self.panel.flash("Espera a que termine la consulta", theme.WARN)
            return
        if len(self.sessions) >= MAX_SESIONES:
            self.panel.flash(
                f"Ya hay {MAX_SESIONES} sesiones abiertas; cierra una",
                theme.WARN, ms=4000,
            )
            return

        result = SessionDialog(self.panel, self.cfg).show(self.panel)
        if result is None:
            return

        # Se añade, no reemplaza: las que ya estaban siguen vivas con su
        # conversacion intacta, y la nueva pasa a ser la activa.
        sesion = Session(
            preprompt=result["preprompt"],
            title=result.get("preset") or "",
            capture_mode=result["mode"],
            monitor_index=result["monitor_index"],
            model=result.get("model"),
            effort=result.get("effort"),
        )
        self.sessions.append(sesion)
        self.indice = len(self.sessions) - 1

        self.cfg["capture"] = {
            "mode": result["mode"],
            "monitor_index": result["monitor_index"],
        }
        self.cfg.save()

        salto = chr(10) + chr(10)
        aviso = "Sesion lista. Captura cuando quieras."
        if sesion.model:
            aviso += f"{salto}Modelo de esta sesion: {sesion.model}."
        if len(self.sessions) > 1:
            aviso += f"{salto}{self._pista_cambio()}"
        sesion.remember(aviso, "dim", reemplaza=True)
        self._mostrar_sesion_activa()

    def _pista_cambio(self) -> str:
        """Como rotar entre sesiones, con el atajo que este configurado."""
        atajo = self.cfg["switch_hotkey"]
        if not atajo:
            return f"{len(self.sessions)} sesiones abiertas."
        return (
            f"{len(self.sessions)} sesiones abiertas: {_bonito(atajo)} y las "
            f"flechas para cambiar."
        )

    def _mostrar_sesion_activa(self) -> None:
        """Devuelve el panel al estado de la sesion activa.

        El panel es uno solo para todas, asi que al cambiar hay que repintar lo
        que esa sesion tenia: su respuesta y su pie. Sin esto, cambiar de sesion
        dejaria a la vista la respuesta de la anterior.
        """
        sesion = self.session
        if sesion is None:
            self.panel.show_idle()
            return
        self.panel.show_session(self._status(), sesion.last_hint or self.hotkey_hint)
        self.panel.set_historial(sesion.historial)
        self.panel.set_use_history(sesion.use_history)

    def _history_toggled(self, value: bool) -> None:
        if self.session is not None:
            self.session.use_history = value

    def edit_session(self) -> None:
        """Cambia que se captura. El pre-prompt de la sesion no se toca.

        Queda fijo desde que se abre: una sesion tiene un solo juego de
        instrucciones. Para otro prompt, otra sesion.
        """
        if self.session is None:
            return
        if self.busy:
            self.panel.flash("Espera a que termine la consulta", theme.WARN)
            return

        result = EditSessionDialog(self.panel, self.cfg, self.session).show(self.panel)
        if result is None:
            return

        self.session.capture_mode = result["mode"]
        self.session.monitor_index = result["monitor_index"]
        self.cfg["capture"] = dict(result)
        self.cfg.save()
        self.panel.set_status(self._status())
        self.panel.flash("Sesion actualizada", theme.OK)

    def end_session(self) -> None:
        """Cierra solo la sesion activa; las demas siguen abiertas."""
        if self.session is None:
            return
        if self.busy:
            self.panel.flash("Espera a que termine la consulta", theme.WARN)
            return

        self.sessions.pop(self.indice).close()
        self.indice = max(0, min(self.indice, len(self.sessions) - 1))
        if not self.sessions:
            self._stop_modo()  # sin sesiones que rotar, el modo no pinta nada
            self.panel.show_idle()
            return
        self._mostrar_sesion_activa()
        self.panel.flash(f"Sesion cerrada · quedan {len(self.sessions)}", theme.OK)

    def _status(self) -> str:
        assert self.session is not None
        label = capture.MODE_LABELS[self.session.capture_mode]
        if self.session.capture_mode == "monitor":
            label = f"Monitor {self.session.monitor_index}"
        base = f"{self.session.label} · {label} · {self.session.status_label}"
        if len(self.sessions) > 1:
            # Con varias abiertas hay que ver de un vistazo en cual estas.
            return f"[{self.indice + 1}/{len(self.sessions)}] {base}"
        return base

    # -------------------------------------------------------------- capturas

    def request_capture(self, question: str = "") -> None:
        if self.session is None:
            log.info("captura pedida sin sesion abierta")
            self.panel.flash("Abre una sesion primero", theme.WARN)
            return
        if self.busy:
            log.info("captura pedida con otra consulta en curso")
            # Se descarta en vez de encolar: encolar mandaria una captura de
            # una pantalla que ya cambio.
            self.panel.flash("Ya hay una consulta en curso", theme.WARN)
            return

        # El pre-prompt ya viaja en el system prompt de la sesion; repetirlo
        # como pregunta solo gasta tokens.
        question = question or self.panel.take_question() or DEFAULT_QUESTION
        question = self._con_idioma(question)

        self.busy = True
        self.panel.show_busy("capturando…")
        self.panel.withdraw()
        self.panel.after(HIDE_MS, lambda: self._grab_and_send(question))

    def _con_idioma(self, question: str) -> str:
        """Fija el idioma en el propio mensaje cuando tu escribes la pregunta.

        El system prompt se decide al abrir la sesion, asi que una pregunta
        escrita en otro idioma a mitad de sesion no lo cambiaria.
        """
        if self.cfg["language"] != "auto" or question == DEFAULT_QUESTION:
            return question
        detectado = lang.detect(question)
        if detectado is None:
            return question
        aviso = (
            "(Responde en espanol.)"
            if detectado == lang.ESPANOL
            else "(Answer in English.)"
        )
        return f"{question}\n\n{aviso}"

    def _grab_and_send(self, question: str) -> None:
        assert self.session is not None
        try:
            shot = capture.capture_to_file(
                self.session.next_shot_path(),
                mode=self.session.capture_mode,
                monitor_index=self.session.monitor_index,
                max_edge=self.cfg["max_image_edge"],
            )
        except Exception as exc:
            log.exception("fallo la captura")
            self.panel.deiconify()
            self._finish_error(f"No pude capturar: {exc}")
            return

        log.info("captura hecha: %s (%s)", shot.name, self.session.capture_mode)

        self.panel.deiconify()
        self.panel.attributes("-topmost", True)
        self.panel.show_busy("preguntando a Claude…")

        threading.Thread(
            target=self._worker,
            args=(self.session, question, shot),
            name="claude",
            daemon=True,
        ).start()

    def _worker(self, session: Session, question: str, shot: Path) -> None:
        """Corre fuera del hilo de Tk: solo publica en la cola."""
        if session.use_history and self.cfg["history_mode"] == "resumen":
            self._worker_memoria(session, question, shot)
            return
        conv_id, resume = session.conversation_for_next()
        try:
            reply = self.client.send(
                session_id=conv_id,
                question=question,
                image_path=shot,
                resume=resume,
                system_prompt=self.cfg.full_system_prompt(session.preprompt),
                model=session.model,    # la plantilla puede pedir uno mas rapido
                effort=session.effort,
            )
            log.info("respuesta en %dms, $%.3f (%s)", reply.duration_ms, reply.cost_usd,
                     "con pasados" if conv_id == session.session_id else "suelta")
            self.events.put(("reply", (session.session_id, reply, conv_id == session.session_id)))
        except ClaudeError as exc:
            log.error("claude fallo: %s", exc)
            self.events.put(("error", str(exc)))
        except Exception:
            log.exception("fallo inesperado hablando con Claude")
            traceback.print_exc()
            self.events.put(("error", "Fallo inesperado; mira la consola."))

    def _worker_memoria(self, session: Session, question: str, shot: Path) -> None:
        """Pasados por resumen: la imagen actual y notas de texto de las demas.

        Cada captura es una conversacion nueva, asi que el costo no crece con
        la sesion. Si Claude pide ver una anterior (`NEED: 3`), se le re-envia
        esa sola y responde ya con ella.
        """
        n = session.captures + 1
        entries = list(session.memoria)  # copia: la lista vive en el hilo de Tk
        comun = dict(
            image_path=shot,
            resume=False,
            system_prompt=self.cfg.full_system_prompt(session.preprompt),
            model=session.model,
            effort=session.effort,
        )
        try:
            reply = self.client.send(
                session_id=new_session_id(),
                question=memoria.build_prompt(entries, question, n),
                **comun,
            )
            cost, ms = reply.cost_usd, reply.duration_ms
            pedidas = [k for k in memoria.needs(reply.text, n)
                       if session.shot_path(k).exists()]
            if pedidas:
                log.info("pide de vuelta las capturas %s", pedidas)
                reply = self.client.send(
                    session_id=new_session_id(),
                    question=memoria.build_prompt(entries, question, n, fetched=pedidas),
                    extra_images=[(f"Earlier screenshot #{k}:", session.shot_path(k))
                                  for k in pedidas],
                    **comun,
                )
                cost += reply.cost_usd
                ms += reply.duration_ms
            texto, memo = memoria.parse(reply.text)
            reply = dataclasses.replace(reply, text=texto, cost_usd=cost, duration_ms=ms)
            tuya = "" if question.startswith(DEFAULT_QUESTION) else question
            entry = memoria.Entry(n=n, memo=memo, answer=texto, question=tuya)
            log.info("respuesta en %dms, $%.3f (resumen, %d notas%s%s)", ms, cost,
                     len(entries), f", +#{pedidas}" if pedidas else "",
                     "" if memo else ", SIN memo")
            self.events.put(("reply", (session.session_id, reply, False, entry)))
        except ClaudeError as exc:
            log.error("claude fallo: %s", exc)
            self.events.put(("error", str(exc)))
        except Exception:
            log.exception("fallo inesperado hablando con Claude")
            traceback.print_exc()
            self.events.put(("error", "Fallo inesperado; mira la consola."))

    # ----------------------------------------------------------------- cola

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "hotkey":
                    self.request_capture()
                elif kind == "mover":
                    self._toggle_move_mode()
                elif kind == "cambiar":
                    self._toggle_switch_mode()
                elif kind == "colapsar":
                    self.panel.toggle_collapse()
                elif kind == "scroll":
                    self._toggle_scroll_mode()
                elif kind == "salir_modo":
                    self._stop_modo()
                elif kind == "flecha":
                    self._con_flecha(str(payload))
                elif kind == "reply":
                    self._on_reply(*payload)  # type: ignore[misc]
                elif kind == "error":
                    self._finish_error(str(payload))
        except queue.Empty:
            pass
        self._drain_job = self.panel.after(POLL_MS, self._drain)

    def _on_reply(self, session_id: str, reply, in_history: bool = True,
                  entry: memoria.Entry | None = None) -> None:
        self.busy = False
        self.panel.hide_busy()

        # La respuesta se guarda en SU sesion, no en la que este activa: con
        # varias abiertas la activa puede ser otra, y la sesion pudo cerrarse
        # mientras Claude respondia.
        destino = next(
            (s for s in self.sessions if s.session_id == session_id), None
        )
        if destino is None:
            return

        destino.record(reply.cost_usd, in_history)
        if entry is not None:
            destino.memoria.append(entry)
        pie = (
            f"{reply.duration_ms / 1000:.1f}s · {reply.cost_label} · "
            f"{self.hotkey_hint}"
        )
        destino.remember(reply.text, None, pie)

        if destino is not self.session:
            self.panel.flash("Respuesta lista en otra sesion", theme.OK, ms=3000)
            return

        self.panel.add_answer(reply.text)
        self.panel.set_status(self._status())
        self.panel.set_hint(pie)

        limit = self.cfg["warn_after_captures"]
        # Con memoria por resumen el costo no crece: no hay nada que avisar.
        if limit and destino.captures == limit and self.cfg["history_mode"] != "resumen":
            # Cada turno reenvia las capturas anteriores, asi que el costo por
            # pregunta sube segun crece la sesion.
            self.panel.flash(
                f"{limit} capturas en esta sesion: cierrala para abaratar",
                theme.WARN,
                ms=6000,
            )

    def _finish_error(self, message: str) -> None:
        self.busy = False
        self.panel.hide_busy()
        if self.session is not None:
            self.session.remember(message, "error")
            self.panel.add_answer(message, tag="error")
        else:
            self.panel.set_answer(message, tag="error")

    # ----------------------------------------------------------------- otros

    def open_settings(self) -> None:
        result = SettingsDialog(self.panel, self.cfg).show(self.panel)
        if result is None:
            return

        hotkey_changed = (
            result["hotkeys"] != self.cfg["hotkeys"]
            or result.get("move_hotkey") != self.cfg["move_hotkey"]
            or result.get("switch_hotkey") != self.cfg["switch_hotkey"]
            or result.get("collapse_hotkey") != self.cfg["collapse_hotkey"]
            or result.get("scroll_hotkey") != self.cfg["scroll_hotkey"]
        )
        monitor_changed = (
            "panel_monitor" in result
            and result["panel_monitor"] != self.cfg["panel_monitor"]
        )
        for key, value in result.items():
            self.cfg[key] = value
        self.cfg.save()

        if monitor_changed:
            # Moverlo ya: si no, elegir la pantalla no parece haber hecho nada.
            self.panel.place_at(None, None, self.cfg["panel_monitor"])

        if hotkey_changed:
            self._stop_modo()  # las flechas viejas cuelgan del manager anterior
            if self.hotkeys is not None:
                self.hotkeys.stop()
                self.hotkeys = None
            self._start_hotkey()

        if self.session is not None:
            self.panel.set_hint(self.hotkey_hint)
        self.panel.flash("Configuracion guardada", theme.OK)

    def quit(self) -> None:
        # Sin cancelarlo, el bucle de la cola se vuelve a disparar sobre una
        # ventana ya destruida y Tk protesta con "invalid command name".
        if self._drain_job is not None:
            self.panel.after_cancel(self._drain_job)
            self._drain_job = None

        self._stop_modo()

        self.cfg["window"] = {"x": self.panel.winfo_x(), "y": self.panel.winfo_y()}
        self.cfg.save()
        if self.hotkeys is not None:
            self.hotkeys.stop()
        for sesion in self.sessions:
            sesion.close()
        self.sessions.clear()
        self.panel.destroy()

    def run(self) -> int:
        self.panel.mainloop()
        return 0


def run_app(cfg: Config) -> int:
    return App(cfg).run()
