"""El panel flotante: la ventanita que vive encima de todo."""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from .. import capture, dpi
from ..config import PROVIDERS
from . import theme
from .widgets import FlatButton, PrimaryButton, Spinner, make_draggable, separator

# "- " y "* " son vinetas; "1. " y "1) " son una lista ordenada y conservan el
# numero, que en una respuesta con pasos es justo lo que hay que leer.
_VINETA = re.compile(r"^[-*•]\s+")
_NUMERADA = re.compile(r"^(\d+)[.)]\s+")

# Tope de alto del area de respuesta: por encima de esto se rueda con la rueda
# del raton, en vez de que el panel ocupe media pantalla. Una respuesta con
# codigo necesita mas sitio: una funcion entera no baja de 20 lineas.
MAX_LINEAS = 18
MAX_LINEAS_CODE = 30

# `codigo` y **negrita** dentro de una linea.
_INLINE = re.compile(r"`(?P<code>[^`]+)`|\*\*(?P<bold>[^*]+)\*\*")

# Marca donde empieza la ultima respuesta. El alto del panel se calcula sobre
# ella sola: el historial vive arriba y se alcanza con la rueda, sin que una
# sesion larga deje el panel ocupando media pantalla.
ULTIMA = "ultima_respuesta"


class HelperPanel(tk.Tk):
    """Ventana sin bordes, siempre encima.

    Solo dibuja y avisa; las decisiones las toma `ui.app.App` por los
    callbacks que se le pasan aqui.
    """

    def __init__(
        self,
        *,
        on_new_session: Callable[[], None],
        on_end_session: Callable[[], None],
        on_settings: Callable[[], None],
        on_quit: Callable[[], None],
        on_ask: Callable[[str], None],
        on_edit_session: Callable[[], None],
        on_capture: Callable[[], None],
        on_provider: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__()

        # El proceso ya es DPI-aware (helper.dpi lo declara al arrancar), asi
        # que Tk trabaja en pixeles fisicos y nos toca escalar a nosotros.
        factor = dpi.scale_factor()
        theme.apply_scale(factor)
        self.tk.call("tk", "scaling", dpi.system_dpi() / 72.0)

        self._on_new_session = on_new_session
        self._on_end_session = on_end_session
        self._on_ask = on_ask
        self._on_edit_session = on_edit_session
        self._on_capture = on_capture
        self._on_provider = on_provider

        self.title("helper")
        self.overrideredirect(True)  # sin barra de titulo de Windows
        self.attributes("-topmost", True)
        self.configure(bg=theme.BORDER)
        # Alto minimo 0: si no, el panel no puede colapsar al encabezado.
        self.minsize(theme.WIDTH, 0)  # el ancho crece con el codigo, no baja de aqui

        # Un frame interior 1px adentro hace de borde: overrideredirect no
        # deja usar highlightthickness de forma confiable.
        outer = tk.Frame(self, bg=theme.BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        header = self._build_header(outer, on_settings, on_quit)
        separator(outer).pack(fill="x")
        self._build_body(outer)
        self._build_footer(outer)
        self._build_menu()

        self._flash_job: str | None = None
        self._entradas: list[tuple[str, str | None]] = []
        self._collapsed = False
        self._session_active = False
        self._con_codigo = False
        self.update_idletasks()
        self.header_height = header.winfo_reqheight() + 2
        self.show_idle()

    # ---------------------------------------------------------------- header

    def _build_header(
        self, parent: tk.Misc, on_settings: Callable[[], None], on_quit: Callable[[], None]
    ) -> tk.Frame:
        header = tk.Frame(parent, bg=theme.BG_HEADER)
        header.pack(fill="x")

        self.dot = tk.Label(
            header, text="●", bg=theme.BG_HEADER, fg=theme.FG_FAINT, font=theme.FONT
        )
        self.dot.pack(side="left", padx=(theme.PAD, 4), pady=6)

        title = tk.Label(
            header, text="helper", bg=theme.BG_HEADER, fg=theme.FG, font=theme.FONT_TITLE
        )
        title.pack(side="left")

        FlatButton(header, "✕", on_quit, padx=8, pady=6).pack(side="right")
        FlatButton(header, "⚙", on_settings, padx=8, pady=6).pack(side="right")
        FlatButton(header, "—", self.toggle_collapse, padx=8, pady=6).pack(side="right")

        # Arrastrar desde cualquier zona muerta del encabezado.
        for w in (header, title, self.dot):
            make_draggable(self, w)

        return header

    # ------------------------------------------------------------------ body

    def _build_body(self, parent: tk.Misc) -> None:
        self.body = tk.Frame(parent, bg=theme.BG)
        self.body.pack(fill="both", expand=True)

        self.status = tk.Label(
            self.body,
            text="",
            bg=theme.BG,
            fg=theme.FG_DIM,
            font=theme.FONT_SMALL,
            anchor="w",
            justify="left",
            wraplength=theme.WIDTH - 2 * theme.PAD,
        )
        self.status.pack(fill="x", padx=theme.PAD, pady=(8, 0))

        # Fila de espera: spinner + texto, oculta salvo mientras se consulta.
        self.busy = tk.Frame(self.body, bg=theme.BG)
        self.spinner = Spinner(self.busy)
        self.spinner.pack(side="left")
        self.busy_label = tk.Label(
            self.busy, text="", bg=theme.BG, fg=theme.FG_DIM, font=theme.FONT_SMALL
        )
        self.busy_label.pack(side="left", padx=6)

        self.answer = tk.Text(
            self.body,
            bg=theme.BG,
            fg=theme.FG,
            font=theme.FONT_BODY,
            wrap="word",
            width=1,   # el ancho lo fija _fit(), no el contenido
            height=6,
            relief="flat",
            padx=theme.PAD,
            pady=6,
            insertwidth=0,
            highlightthickness=0,
            selectbackground=theme.BG_HOVER,
            cursor="arrow",
        )
        self.answer.configure(state="disabled")
        self.answer.bind(
            "<MouseWheel>",
            lambda e: self.answer.yview_scroll(-1 if e.delta > 0 else 1, "units"),
        )
        self.answer.tag_configure("dim", foreground=theme.FG_DIM)
        self.answer.tag_configure("error", foreground=theme.ERROR)
        self.answer.tag_configure(
            "sep", foreground=theme.FG_FAINT, font=theme.FONT_SMALL,
            justify="center", spacing1=theme.PAD, spacing3=theme.PAD // 2,
        )

        # El aire entre bloques lo dan spacing1/spacing3, no lineas en blanco:
        # asi el alto se calcula sobre lo que de verdad ocupa el texto.
        pad = theme.PAD
        self.answer.tag_configure(
            "lead", font=theme.FONT_LEAD, foreground=theme.LEAD, spacing3=pad // 2
        )
        self.answer.tag_configure("body", spacing1=pad // 2)
        self.answer.tag_configure(
            "bullet", spacing1=pad // 4, lmargin1=pad, lmargin2=pad * 2
        )
        # Estos se declaran los ultimos a proposito: en Tk gana el tag creado
        # despues, y estos tienen que imponerse sobre lead/body/bullet.
        self.answer.tag_configure(
            "code",
            font=theme.FONT_CODE,
            foreground=theme.CODE,
            background=theme.BG_INPUT,
            lmargin1=pad,
            lmargin2=pad * 2 + 6,
            spacing1=pad // 2,
        )
        self.answer.tag_configure(
            "inline", font=theme.FONT_CODE, foreground=theme.CODE
        )
        self.answer.tag_configure("strong", font=theme.FONT_BODY_BOLD)

        self.start_button = PrimaryButton(self.body, "Nueva sesion", self._on_new_session)

        # La accion principal necesita un boton visible: el atajo no se ve, y
        # si algo lo bloquea (una ventana como administrador, por ejemplo) no
        # habria ninguna otra forma de capturar.
        self.capture_button = PrimaryButton(
            self.body, "Capturar ahora", self._on_capture
        )

        self.actions = tk.Frame(self.body, bg=theme.BG)
        self.copy_button = FlatButton(self.actions, "Copiar", self._copy, padx=8)
        self.copy_button.pack(side="left")
        FlatButton(self.actions, "Editar", self._on_edit_session, padx=8).pack(side="left")
        # Con una sesion abierta el boton grande de "Nueva sesion" ya no esta,
        # asi que sin este no habria forma de abrir una segunda.
        FlatButton(self.actions, "+ Sesion", self._on_new_session, padx=8).pack(
            side="left"
        )
        FlatButton(self.actions, "Cerrar sesion", self._on_end_session, padx=8).pack(
            side="right"
        )

    # ---------------------------------------------------------------- footer

    def _build_footer(self, parent: tk.Misc) -> None:
        self.footer = tk.Frame(parent, bg=theme.BG)
        self.footer.pack(fill="x", side="bottom")

        separator(self.footer).pack(fill="x")

        self.entry = tk.Entry(
            self.footer,
            bg=theme.BG_INPUT,
            fg=theme.FG,
            font=theme.FONT,
            relief="flat",
            insertbackground=theme.FG,
            highlightthickness=0,
        )
        self.entry.pack(fill="x", padx=theme.PAD, pady=(8, 4), ipady=4)
        self.entry.bind("<Return>", self._submit_entry)
        self._placeholder = "pregunta puntual (opcional)…"
        self._set_placeholder()
        self.entry.bind("<FocusIn>", self._clear_placeholder)
        self.entry.bind("<FocusOut>", self._set_placeholder)

        # Desmarcado: la captura va sola, sin re-enviar las anteriores (ahorra
        # tokens). Por defecto marcado, como siempre funciono.
        self.on_history_toggle: Callable[[bool], None] | None = None
        self.use_history = tk.BooleanVar(value=True)
        self.history_check = tk.Checkbutton(
            self.footer,
            text="Usar pasados (la IA ve las capturas anteriores)",
            variable=self.use_history,
            command=self._history_changed,
            bg=theme.BG,
            fg=theme.FG_FAINT,
            activebackground=theme.BG,
            activeforeground=theme.FG,
            selectcolor=theme.BG_INPUT,
            font=theme.FONT_SMALL,
            anchor="w",
            highlightthickness=0,
            bd=0,
        )
        self.history_check.pack(fill="x", padx=theme.PAD - 2, pady=(0, 2))

        self.hint = tk.Label(
            self.footer,
            text="",
            bg=theme.BG,
            fg=theme.FG_FAINT,
            font=theme.FONT_SMALL,
            anchor="w",
        )
        self.hint.pack(fill="x", padx=theme.PAD, pady=(0, 8))

    # ------------------------------------------------------ menu contextual

    def _build_menu(self) -> None:
        """Clic derecho en el panel: cambiar de IA sin cerrar la sesion."""
        self.provider = tk.StringVar(value="claude")
        self.menu = tk.Menu(
            self, tearoff=0, bg=theme.BG_INPUT, fg=theme.FG,
            activebackground=theme.BG_HOVER, activeforeground=theme.FG,
            font=theme.FONT_SMALL, bd=0,
        )
        self.menu.add_command(label="Modelo de IA", state="disabled")
        for key, etiqueta in PROVIDERS.items():
            self.menu.add_radiobutton(
                label=etiqueta, value=key, variable=self.provider,
                command=lambda k=key: self._provider_elegido(k),
            )
        self.bind_all("<Button-3>", self._popup_menu)

    def _popup_menu(self, event) -> None:
        # bind_all tambien recibe los clics de los dialogos: solo el panel.
        if event.widget.winfo_toplevel() is not self:
            return
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _provider_elegido(self, key: str) -> None:
        if self._on_provider is not None:
            self._on_provider(key)

    def set_provider(self, key: str) -> None:
        """Marca en el menu la IA de la sesion que se esta viendo."""
        self.provider.set(key)

    def _history_changed(self) -> None:
        if self.on_history_toggle is not None:
            self.on_history_toggle(bool(self.use_history.get()))

    def set_use_history(self, value: bool) -> None:
        """Al cambiar de sesion: la casilla muestra la de ESA sesion."""
        self.use_history.set(bool(value))

    def _fit_answer(self) -> None:
        """Ajusta el alto del area de respuesta a lo que ocupa el texto.

        Se mide en pixeles y no en lineas: el alto de un Text se fija en
        lineas, pero el espaciado entre bloques y el monospace del codigo no
        caben en esa cuenta, y contando lineas la respuesta salia recortada.
        """
        self.answer.update_idletasks()
        alto_linea = tkfont.Font(font=theme.FONT_BODY).metrics("linespace") or 16
        try:
            desde = ULTIMA if ULTIMA in self.answer.mark_names() else "1.0"
            pixeles = self.answer.count(desde, "end-1c", "ypixels")
        except tk.TclError:
            pixeles = None

        if pixeles and pixeles[0] > 0:
            # El relleno interno del propio Text no entra en la medida, y sin
            # sumarlo la ultima linea queda cortada por abajo.
            relleno = 2 * int(self.answer.cget("pady"))
            lineas = -(-(pixeles[0] + relleno) // alto_linea)  # hacia arriba
        else:
            lineas = 3
        self.answer.configure(height=max(2, min(int(lineas), self._tope_lineas)))

    @property
    def _ancho(self) -> int:
        return theme.WIDTH_CODE if self._con_codigo else theme.WIDTH

    @property
    def _tope_lineas(self) -> int:
        """Tope de alto, limitado por lo que de verdad cabe en la pantalla.

        Un numero fijo no sirve: 30 lineas son ~960px, y en una pantalla de
        1080 el panel se comeria el escritorio entero. Lo que no quepa se rueda
        con la rueda del raton.
        """
        base = MAX_LINEAS_CODE if self._con_codigo else MAX_LINEAS
        alto_linea = tkfont.Font(font=theme.FONT_BODY).metrics("linespace") or 16
        # Aparte del texto estan el encabezado, el estado, los botones y el pie.
        alrededor = self.header_height + 10 * theme.PAD
        cabe = (int(self.winfo_screenheight() * 0.72) - alrededor) // alto_linea
        return max(4, min(base, int(cabe)))

    def _fit(self) -> None:
        """Ancho segun el contenido, alto segun lo que este visible."""
        self.update_idletasks()
        ancho = self._ancho
        # Las etiquetas envuelven a mano: hay que reajustarlas al ancho nuevo.
        for etiqueta in (self.status, self.hint):
            etiqueta.configure(wraplength=ancho - 2 * theme.PAD)
        self.geometry(f"{ancho}x{self.winfo_reqheight()}")

    # --------------------------------------------------------------- estados

    def show_idle(self) -> None:
        """Sin sesion abierta."""
        self.dot.configure(fg=theme.FG_FAINT)
        self.status.configure(text="Sin sesion abierta.", fg=theme.FG_DIM)
        self.busy.pack_forget()
        self.answer.pack_forget()
        self.capture_button.pack_forget()
        self.actions.pack_forget()
        self.start_button.pack(fill="x", padx=theme.PAD, pady=(8, 10))
        self.footer.pack_forget()
        self._session_active = False
        self._fit()

    def show_session(self, status: str, hint: str) -> None:
        """Sesion abierta y lista para capturar."""
        self.dot.configure(fg=theme.OK)
        self.start_button.pack_forget()
        self.status.configure(text=status, fg=theme.FG_DIM)
        self.busy.pack_forget()
        self.answer.pack(fill="both", expand=True, pady=(6, 0))
        self.capture_button.pack(fill="x", padx=theme.PAD, pady=(6, 0))
        self.actions.pack(fill="x", padx=theme.PAD, pady=(4, 8))
        self.footer.pack(fill="x", side="bottom")
        self.hint.configure(text=hint)
        self._session_active = True
        self._fit()

    def show_busy(self, message: str) -> None:
        self.dot.configure(fg=theme.WARN)
        self.busy_label.configure(text=message)
        self.busy.pack(fill="x", padx=theme.PAD, pady=(6, 0), before=self.answer)
        self.spinner.start()
        self.copy_button.set_enabled(False)
        self.capture_button.set_enabled(False)
        self._fit()

    def hide_busy(self) -> None:
        self.spinner.stop()
        self.busy.pack_forget()
        self.dot.configure(fg=theme.OK)
        self.capture_button.set_enabled(True)
        self._fit()

    def set_answer(self, text: str, *, tag: str | None = None) -> None:
        """Deja el panel con una sola entrada, borrando lo que hubiera."""
        self.set_historial([(text, tag)])

    def add_answer(self, text: str, *, tag: str | None = None) -> None:
        """Añade una entrada debajo, conservando las anteriores."""
        self.set_historial(self._entradas + [(text, tag)])

    def set_historial(self, entradas: list[tuple[str, str | None]]) -> None:
        """Repinta el panel entero con las entradas de una sesion."""
        self._entradas = list(entradas) or [("", None)]
        texto, tag = self._entradas[-1]

        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self._con_codigo = any(
            not t and "```" in x for x, t in self._entradas
        )

        for i, (cuerpo, etiqueta) in enumerate(self._entradas):
            if i:
                # Una raya con el numero: al subir se sabe cual es cual.
                self.answer.insert("end", f"\n\u2500\u2500  {i + 1}  \u2500\u2500\n", "sep")
            if i == len(self._entradas) - 1:
                # Gravedad a la izquierda: la marca se queda donde empieza esta
                # entrada aunque se inserte texto justo detras.
                self.answer.mark_set(ULTIMA, "end-1c")
                self.answer.mark_gravity(ULTIMA, "left")
            if etiqueta:
                self.answer.insert("end", cuerpo, etiqueta)
            else:
                self._insert_with_code(cuerpo)

        self.answer.configure(state="disabled")
        # Primero al final y luego a la marca: asi la ultima respuesta queda a
        # la vista con el historial justo encima, listo para subir con la rueda.
        self.answer.see("end-1c")
        self.answer.see(ULTIMA)
        self.copy_button.set_enabled(bool(texto) and tag != "error")
        self._fit_answer()
        if not self._collapsed:
            self._fit()
        self._crecer_hasta_que_quepa()

    def _crecer_hasta_que_quepa(self) -> None:
        """Agranda el area de respuesta hasta que no quede texto cortado.

        Tiene que ir despues de `_fit`: hasta que la ventana no adopta el alto
        nuevo, `yview` describe la geometria anterior y la correccion se
        calcularia sobre datos viejos.
        """
        # Sin el area en pantalla no hay geometria que medir: `yview` devuelve
        # valores sin sentido y el bucle creceria hasta el tope a ciegas.
        if not self.answer.winfo_ismapped():
            return

        for _ in range(8):
            # update() y no update_idletasks(): hay que procesar tambien los
            # eventos de redimension, o `yview` describe el alto anterior.
            self.update()
            # Al cambiar el alto, Tk deja fija la linea de arriba, asi que hay
            # que recolocarse antes de medir: si no, se mide una ventana
            # asomada al historial y el area crece sin motivo. Queda el
            # principio de la ultima respuesta arriba, no su final.
            self.ir_a_ultima()
            alto = int(self.answer.cget("height"))
            if alto >= self._tope_lineas:
                return
            # Con historial encima, "cabe" no es que se vea el final del
            # widget, sino que se vea el PRINCIPIO de la ultima respuesta.
            visible = self.answer.yview()[1]
            entera = self.answer.bbox(ULTIMA) is not None
            if entera and visible >= 0.999:
                return
            falta = max(1, round(alto * (1 - visible))) if not entera else 1
            self.answer.configure(height=min(self._tope_lineas, alto + falta))
            if not self._collapsed:
                self._fit()

        self.ir_a_ultima()

    def _insert_with_code(self, text: str) -> None:
        """Pinta la respuesta con jerarquia en vez de volcarla en bruto.

        El modelo entrega la respuesta en la primera linea y el detalle debajo;
        aqui eso se convierte en titular, parrafos, vinetas y bloques de
        codigo. Los marcadores (```, `acentos`, **negrita**, "- ") se
        interpretan y desaparecen: son instrucciones de formato, no texto que
        el usuario deba leer.
        """
        bloques: list[tuple[str, str]] = []
        en_codigo = False
        hay_titular = False

        for cruda in text.strip().split("\n"):
            limpia = cruda.rstrip().strip()

            if limpia.startswith("```"):
                en_codigo = not en_codigo
                continue

            if en_codigo:
                bloques.append(("code", cruda.rstrip()))
                continue

            if not limpia:
                continue  # el aire lo ponen los tags, no las lineas vacias

            if not hay_titular:
                bloques.append(("lead", limpia))
                hay_titular = True
            elif _VINETA.match(limpia):
                bloques.append(("bullet", _VINETA.sub("• ", limpia, count=1)))
            elif (num := _NUMERADA.match(limpia)) is not None:
                bloques.append(
                    ("bullet", _NUMERADA.sub(f"{num.group(1)}. ", limpia, count=1))
                )
            else:
                bloques.append(("body", limpia))

        # Un titular solo destaca si hay algo debajo con lo que contrastar, y
        # deja de ser titular cuando ocupa un parrafo entero.
        if bloques and bloques[0][0] == "lead":
            if len(bloques) == 1 or len(bloques[0][1]) > 140:
                bloques[0] = ("body", bloques[0][1])

        for i, (estilo, contenido) in enumerate(bloques):
            if i:
                self.answer.insert("end", "\n")
            if estilo == "code":
                self.answer.insert("end", contenido, "code")
            else:
                self._insert_inline(contenido, estilo)

    def _insert_inline(self, linea: str, estilo: str) -> None:
        """Escribe una linea resolviendo `codigo` y **negrita** dentro."""
        pos = 0
        for m in _INLINE.finditer(linea):
            if m.start() > pos:
                self.answer.insert("end", linea[pos:m.start()], estilo)
            if m.group("code") is not None:
                self.answer.insert("end", m.group("code"), (estilo, "inline"))
            else:
                self.answer.insert("end", m.group("bold"), (estilo, "strong"))
            pos = m.end()
        if pos < len(linea):
            self.answer.insert("end", linea[pos:], estilo)

    def scroll_historial(self, unidades: int) -> None:
        """Sube o baja por las respuestas ya dadas en esta sesion."""
        self.answer.yview_scroll(unidades, "units")

    def ir_a_ultima(self) -> None:
        """Vuelve a dejar a la vista la ultima respuesta."""
        self.answer.see("end-1c")
        if ULTIMA in self.answer.mark_names():
            self.answer.see(ULTIMA)

    @property
    def hay_historial(self) -> bool:
        return len(self._entradas) > 1

    def set_status(self, text: str) -> None:
        self.status.configure(text=text, fg=theme.FG_DIM)

    def set_hint(self, text: str) -> None:
        self.hint.configure(text=text)

    def flash(self, message: str, color: str = theme.WARN, ms: int = 2200) -> None:
        """Mensaje temporal en la linea de estado, sin pisar la respuesta."""
        previous = self.status.cget("text")
        self.status.configure(text=message, fg=color)
        if self._flash_job is not None:
            self.after_cancel(self._flash_job)

        def restore() -> None:
            self.status.configure(text=previous, fg=theme.FG_DIM)
            self._flash_job = None

        self._flash_job = self.after(ms, restore)

    def toggle_collapse(self) -> None:
        """Colapsa a solo el encabezado.

        No se usa withdraw(): con overrideredirect no hay barra de tareas ni
        iconify, asi que una ventana escondida no habria como recuperarla.
        """
        self._collapsed = not getattr(self, "_collapsed", False)
        if self._collapsed:
            self.body.pack_forget()
            self.footer.pack_forget()
            self.geometry(f"{self._ancho}x{self.header_height}")
        else:
            self.body.pack(fill="both", expand=True)
            if self._session_active:
                self.footer.pack(fill="x", side="bottom")
            self._fit()

    def bring_to_front(self) -> None:
        """Lo pone encima de todo y desplegado, sin quitarle el foco a nadie.

        Ya es topmost, pero otra ventana topmost puede haber quedado encima:
        apagarlo y encenderlo lo vuelve a subir al tope de esa capa.
        """
        self.deiconify()
        self.attributes("-topmost", False)
        self.attributes("-topmost", True)
        self.lift()
        if self._collapsed:
            self.toggle_collapse()

    # ------------------------------------------------------------- posicion

    def _bounds(self, monitor_index: int | None = None) -> tuple[int, int, int, int]:
        """Area donde puede vivir el panel, en las coordenadas que usa Tk.

        Con `monitor_index` devuelve ese monitor; sin el, el escritorio
        completo. Hace falta convertir: mss reporta pixeles fisicos y Tk usa
        los suyos, que con escalado DPI no son los mismos (en una pantalla al
        125%, Windows le dice a Tk que mide 1536 y no 1920).

        La escala se recalcula en cada llamada a proposito, y es estable: lo
        que Tk reporta queda fijado al crear la ventana y ya no cambia, aunque
        despues mss vuelva el proceso DPI-aware al tomar la primera captura.
        """
        logical_w = self.winfo_screenwidth()
        try:
            monitors = capture.list_monitors()
        except Exception:
            monitors = []
        if not monitors:
            return 0, 0, logical_w, self.winfo_screenheight()

        primary = next((m for m in monitors if m.primary), monitors[0])
        scale = (primary.width / logical_w) if logical_w else 1.0

        chosen = next((m for m in monitors if m.index == monitor_index), None)
        if chosen is not None:
            left, top = chosen.left, chosen.top
            right, bottom = left + chosen.width, top + chosen.height
        else:
            left = min(m.left for m in monitors)
            top = min(m.top for m in monitors)
            right = max(m.left + m.width for m in monitors)
            bottom = max(m.top + m.height for m in monitors)

        return (
            int(left / scale),
            int(top / scale),
            int(right / scale),
            int(bottom / scale),
        )

    def nudge(self, dx: int, dy: int, monitor_index: int | None = None) -> None:
        """Desplaza el panel, sin dejar que se salga de la pantalla."""
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        left, top, right, bottom = self._bounds(monitor_index)
        x = max(left, min(self.winfo_x() + dx, right - w))
        y = max(top, min(self.winfo_y() + dy, bottom - h))
        self.geometry(f"+{x}+{y}")

    def set_move_mode(self, activo: bool) -> None:
        """Marca visualmente que las flechas estan moviendo el panel."""
        self._modo_mover = activo
        self.dot.configure(fg=theme.ACCENT if activo else
                           (theme.OK if self._session_active else theme.FG_FAINT))

    def place_at(
        self, x: int | None, y: int | None, monitor_index: int | None = None
    ) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        left, top, right, bottom = self._bounds(monitor_index)

        # Con un monitor fijado se ignora la posicion guardada: el punto es que
        # el panel aparezca ahi aunque lo hayas dejado en otra pantalla.
        if monitor_index is not None or x is None or y is None:
            x, y = right - w - 24, bottom - h - 64  # esquina inferior derecha

        # Si cambio la resolucion o se desconecto un monitor, se reencuadra.
        x = max(left, min(int(x), right - w))
        y = max(top, min(int(y), bottom - h))
        self.geometry(f"+{x}+{y}")

    # --------------------------------------------------------------- helpers

    def _copy(self) -> None:
        # Solo la ultima respuesta: copiar el historial entero casi nunca es lo
        # que quieres, y no habria forma de quedarse solo con lo de ahora.
        desde = ULTIMA if ULTIMA in self.answer.mark_names() else "1.0"
        text = self.answer.get(desde, "end").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.flash("Copiado", theme.OK, ms=1200)

    def _submit_entry(self, _=None) -> None:
        question = self.entry.get().strip()
        if question == self._placeholder:
            question = ""
        self.entry.delete(0, "end")
        self._on_ask(question)

    def take_question(self) -> str:
        """Lee y limpia la cajita de pregunta puntual."""
        question = self.entry.get().strip()
        if question == self._placeholder:
            return ""
        self.entry.delete(0, "end")
        self._set_placeholder()
        return question

    def _set_placeholder(self, _=None) -> None:
        if not self.entry.get():
            self.entry.insert(0, self._placeholder)
            self.entry.configure(fg=theme.FG_FAINT)

    def _clear_placeholder(self, _=None) -> None:
        if self.entry.get() == self._placeholder:
            self.entry.delete(0, "end")
            self.entry.configure(fg=theme.FG)
