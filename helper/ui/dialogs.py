"""Dialogos de nueva sesion y de configuracion.

Van juntos porque comparten el mismo modal base y el mismo selector de target
de captura; separarlos obligaria a exportar esas piezas sin necesidad.
"""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any, Callable

from .. import capture, privacy
from ..config import LANGUAGE_LABELS, PROVIDERS, Config, normalize_hotkeys
from . import theme
from .widgets import FlatButton, PrimaryButton, make_draggable, separator


class Modal(tk.Toplevel):
    """Ventana modal sin bordes, centrada sobre el panel."""

    def __init__(self, parent: tk.Misc, title: str, width: int = 420) -> None:
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=theme.BORDER)
        self.result: Any = None
        self._width = width

        outer = tk.Frame(self, bg=theme.BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        header = tk.Frame(outer, bg=theme.BG_HEADER)
        header.pack(fill="x")
        label = tk.Label(
            header, text=title, bg=theme.BG_HEADER, fg=theme.FG, font=theme.FONT_TITLE
        )
        label.pack(side="left", padx=theme.PAD, pady=8)
        FlatButton(header, "✕", self.cancel, padx=10, pady=8).pack(side="right")
        for w in (header, label):
            make_draggable(self, w)
        separator(outer).pack(fill="x")

        self.content = tk.Frame(outer, bg=theme.BG)
        self.content.pack(fill="both", expand=True, padx=theme.PAD * 2, pady=theme.PAD)

        self.buttons = tk.Frame(outer, bg=theme.BG)
        self.buttons.pack(fill="x", padx=theme.PAD * 2, pady=(0, theme.PAD * 1.5))

        self.bind("<Escape>", lambda _: self.cancel())

    def center_on(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(parent.winfo_x() + parent.winfo_width() // 2 - w // 2, sw - w))
        y = max(0, min(parent.winfo_y() + parent.winfo_height() // 2 - h // 2, sh - h))
        self.geometry(f"+{x}+{y}")

    def show(self, parent: tk.Misc) -> Any:
        self.center_on(parent)
        # Los dialogos ensenan el pre-prompt y la configuracion: se excluyen de
        # las capturas igual que el panel. Aqui la ventana nativa ya existe
        # (center_on hace update_idletasks), asi que no hace falta esperar.
        privacy.exclude_window_from_capture(self)
        self.grab_set()
        self.wait_window()
        return self.result

    def cancel(self) -> None:
        self.result = None
        self.destroy()


def field_label(parent: tk.Misc, text: str) -> tk.Label:
    label = tk.Label(
        parent, text=text, bg=theme.BG, fg=theme.FG_DIM, font=theme.FONT_SMALL, anchor="w"
    )
    label.pack(fill="x", pady=(10, 3))
    return label


def hint_label(parent: tk.Misc, text: str) -> tk.Label:
    label = tk.Label(
        parent,
        text=text,
        bg=theme.BG,
        fg=theme.FG_FAINT,
        font=theme.FONT_SMALL,
        anchor="w",
        justify="left",
        wraplength=theme.WRAP,
    )
    label.pack(fill="x", pady=(3, 0))
    return label


def entry(parent: tk.Misc, value: str = "") -> tk.Entry:
    e = tk.Entry(
        parent,
        bg=theme.BG_INPUT,
        fg=theme.FG,
        font=theme.FONT,
        relief="flat",
        insertbackground=theme.FG,
        highlightthickness=0,
    )
    e.insert(0, value)
    e.pack(fill="x", ipady=5)
    return e


def textarea(parent: tk.Misc, value: str = "", height: int = 4) -> tk.Text:
    t = tk.Text(
        parent,
        bg=theme.BG_INPUT,
        fg=theme.FG,
        font=theme.FONT,
        height=height,
        wrap="word",
        relief="flat",
        insertbackground=theme.FG,
        highlightthickness=0,
        padx=6,
        pady=5,
    )
    t.insert("1.0", value)
    t.pack(fill="both", expand=True)
    return t


class OptionRow(tk.Frame):
    """Lista de opciones excluyentes en filas clicables (radio sin ttk)."""

    def __init__(
        self,
        parent: tk.Misc,
        options: list[tuple[str, str]],
        value: str,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, bg=theme.BG)
        self._value = value
        self._on_change = on_change
        self._rows: dict[str, tk.Label] = {}

        for key, label in options:
            row = tk.Label(
                self,
                text=f"  {label}",
                bg=theme.BG,
                fg=theme.FG,
                font=theme.FONT,
                anchor="w",
                padx=8,
                pady=5,
                cursor="hand2",
            )
            row.pack(fill="x", pady=1)
            row.bind("<Button-1>", lambda _, k=key: self.set(k))
            self._rows[key] = row

        self._refresh()

    def _refresh(self) -> None:
        for key, row in self._rows.items():
            selected = key == self._value
            text = row.cget("text").lstrip("✓ ").lstrip()
            row.configure(
                text=("✓ " if selected else "  ") + text,
                bg=theme.BG_HOVER if selected else theme.BG,
                fg=theme.FG if selected else theme.FG_DIM,
            )

    def set(self, key: str) -> None:
        self._value = key
        self._refresh()
        if self._on_change:
            self._on_change(key)

    def get(self) -> str:
        return self._value


class CaptureTargetPicker(tk.Frame):
    """Modo de captura + selector de monitor cuando el modo lo necesita."""

    def __init__(self, parent: tk.Misc, mode: str, monitor_index: int) -> None:
        super().__init__(parent, bg=theme.BG)
        self.monitors = capture.list_monitors()

        options = [(m, capture.MODE_LABELS[m]) for m in capture.MODES]
        if len(self.monitors) < 2:
            # Con un solo monitor, "un monitor especifico" y "todos" no
            # significan nada distinto de "el activo".
            options = [o for o in options if o[0] in ("active_monitor", "active_window")]
            if mode not in ("active_monitor", "active_window"):
                mode = "active_monitor"

        self.modes = OptionRow(self, options, mode, self._on_mode)
        self.modes.pack(fill="x")

        self.monitor_box = tk.Frame(self, bg=theme.BG)
        # La lista queda debajo de todos los modos, no anidada bajo el suyo;
        # sin este rotulo no se ve a que opcion pertenece.
        tk.Label(
            self.monitor_box,
            text="Cual:",
            bg=theme.BG,
            fg=theme.FG_DIM,
            font=theme.FONT_SMALL,
            anchor="w",
        ).pack(fill="x", padx=(16, 0), pady=(2, 2))
        valid = [str(m.index) for m in self.monitors]
        chosen = str(monitor_index) if str(monitor_index) in valid else valid[0]
        self.monitor_rows = OptionRow(
            self.monitor_box, [(str(m.index), m.label) for m in self.monitors], chosen
        )
        self.monitor_rows.pack(fill="x", padx=(16, 0))

        self._on_mode(self.modes.get())

    def _on_mode(self, mode: str) -> None:
        if mode == "monitor":
            self.monitor_box.pack(fill="x", pady=(4, 0))
        else:
            self.monitor_box.pack_forget()

    def get(self) -> dict[str, Any]:
        return {
            "mode": self.modes.get(),
            "monitor_index": int(self.monitor_rows.get()),
        }


class SessionDialog(Modal):
    """Abre una sesion: pre-prompt + target de captura."""

    def __init__(self, parent: tk.Misc, cfg: Config) -> None:
        super().__init__(parent, "Nueva sesion")
        self.cfg = cfg

        # Primero, que IA responde: arranca en la ultima que elegiste.
        field_label(self.content, "Modelo de IA")
        self.provider = OptionRow(
            self.content, list(PROVIDERS.items()), cfg["provider"], self._on_provider
        )
        self.provider.pack(fill="x")
        # Solo aparece si eliges Groq y todavia no hay key guardada.
        self.key_box = tk.Frame(self.content, bg=theme.BG)
        field_label(self.key_box, "API key de Groq")
        self.groq_key = entry(self.key_box)
        self.groq_key.configure(show="•")
        self.key_error = hint_label(
            self.key_box,
            "Mejor en GROQ_API_KEY del archivo .env del proyecto. Si la pegas "
            "aqui, se guarda en tu config.json.",
        )
        self._key_anchor = tk.Frame(self.content, bg=theme.BG)
        self._key_anchor.pack(fill="x")
        self._on_provider(self.provider.get())

        hint_label(
            self.content,
            "El pre-prompt es el contexto que la IA mantiene durante toda la "
            "sesion. Cada captura entra en la misma conversacion, asi que ve "
            "las anteriores. Puedes dejarlo vacio.",
        )

        field_label(self.content, "Pre-prompt")
        # Siempre vacia: si arrastrara el de la sesion anterior, una sesion
        # nueva heredaria instrucciones sin que te dieras cuenta.
        self.preprompt = textarea(self.content, "", height=4)

        # Modelo/effort que fije la plantilla elegida. Vacio = usa los globales.
        self._model: str | None = None
        self._effort: str | None = None
        self._preset: str | None = None
        self._preset_texto: str = ""

        field_label(self.content, "Plantillas")
        presets = tk.Frame(self.content, bg=theme.BG)
        presets.pack(fill="x")
        for preset in cfg["presets"]:
            # El boton muestra el nombre, no el texto: hay plantillas de varios
            # parrafos que como etiqueta no se podrian leer.
            etiqueta = preset["nombre"]
            lineas = preset["texto"].count("\n") + 1
            if lineas > 1:
                etiqueta += f"   ({lineas} lineas)"
            FlatButton(
                presets,
                etiqueta,
                lambda p=preset: self._use_preset(p),
                bg=theme.BG_INPUT,
                fg=theme.FG_DIM,
                font=theme.FONT_SMALL,
                padx=8,
                pady=4,
                anchor="w",
            ).pack(fill="x", pady=1)

        field_label(self.content, "Que capturar")
        self.target = CaptureTargetPicker(
            self.content, cfg["capture"]["mode"], cfg["capture"]["monitor_index"]
        )
        self.target.pack(fill="x")

        FlatButton(self.buttons, "Cancelar", self.cancel, padx=12, pady=6).pack(
            side="right"
        )
        PrimaryButton(self.buttons, "Iniciar sesion", self._accept, padx=16).pack(
            side="right", padx=(0, 6)
        )

        self.preprompt.focus_set()

    def _hace_falta_key(self) -> bool:
        return not (self.cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY"))

    def _on_provider(self, key: str) -> None:
        if key == "groq" and self._hace_falta_key():
            self.key_box.pack(fill="x", after=self._key_anchor)
        else:
            self.key_box.pack_forget()

    def _use_preset(self, preset: dict) -> None:
        self.preprompt.delete("1.0", "end")
        self.preprompt.insert("1.0", preset["texto"])
        # El nombre de la plantilla titula la sesion: su texto son parrafos
        # enteros, que como titulo no dirian nada.
        self._preset = preset["nombre"]
        self._preset_texto = preset["texto"].strip()
        # La plantilla puede traer su propio modelo/effort (p.ej. la de opcion
        # multiple usa uno rapido). Si no, la sesion usa los globales.
        self._model = preset.get("model")
        self._effort = preset.get("effort")

    def _accept(self) -> None:
        escrito = self.preprompt.get("1.0", "end").strip()
        # Si tocaste el texto de la plantilla, su nombre ya no lo describe.
        preset = self._preset if escrito == self._preset_texto else None
        provider = self.provider.get()
        key = self.groq_key.get().strip()
        if provider == "groq" and self._hace_falta_key() and not key:
            self.key_error.configure(
                text="Sin API key Groq no puede responder. Pegala aqui.",
                fg=theme.ERROR,
            )
            self.groq_key.focus_set()
            return
        self.result = {
            "provider": provider,
            "groq_api_key": key,
            "preprompt": escrito,
            "preset": preset,
            "model": self._model,
            "effort": self._effort,
            **self.target.get(),
        }
        self.destroy()


class EditSessionDialog(Modal):
    """Cambia que se captura. El pre-prompt se mira, no se toca.

    El pre-prompt queda fijo al abrir la sesion: una sesion tiene un solo juego
    de instrucciones de principio a fin. Poder cambiarlo a mitad dejaria la
    conversacion con dos prompts encima.
    """

    def __init__(self, parent: tk.Misc, cfg: Config, session) -> None:
        super().__init__(parent, "Editar sesion")
        self.session = session

        field_label(self.content, "Pre-prompt de esta sesion")
        actual = session.preprompt.strip() or "(sin pre-prompt)"
        vista = textarea(self.content, actual, height=3)
        # Solo lectura: se ve para saber con que estas trabajando.
        vista.configure(state="disabled", fg=theme.FG_DIM, bg=theme.BG)
        hint_label(
            self.content,
            "El pre-prompt no se cambia a mitad de sesion. Para usar otro, "
            "cierra esta y abre una nueva: asi ninguna sesion arrastra las "
            "instrucciones de otra.",
        )

        field_label(self.content, "Que capturar")
        self.target = CaptureTargetPicker(
            self.content, session.capture_mode, session.monitor_index
        )
        self.target.pack(fill="x")

        FlatButton(self.buttons, "Cancelar", self.cancel, padx=12, pady=6).pack(
            side="right"
        )
        PrimaryButton(self.buttons, "Guardar", self._accept, padx=16).pack(
            side="right", padx=(0, 6)
        )

    def _accept(self) -> None:
        self.result = self.target.get()
        self.destroy()


class SettingsDialog(Modal):
    def __init__(self, parent: tk.Misc, cfg: Config) -> None:
        super().__init__(parent, "Configuracion")
        self.cfg = cfg

        field_label(self.content, "Atajos globales")
        self.hotkey = entry(self.content, ", ".join(cfg["hotkeys"]))
        hint_label(
            self.content,
            "Separa varios con comas. Cada uno necesita al menos un "
            "modificador (ctrl, alt, shift, win): una tecla sola secuestraria "
            "esa tecla en todo Windows. Se aplican al guardar.",
        )

        field_label(self.content, "Atajo para mover el panel")
        self.move_hotkey = entry(self.content, cfg["move_hotkey"])
        hint_label(
            self.content,
            "Rota el panel entre las cuatro esquinas. Con un atajo no pierdes "
            "el foco de lo que estes haciendo; haciendole clic si.",
        )

        field_label(self.content, "Atajo para cambiar de sesion")
        self.switch_hotkey = entry(self.content, cfg["switch_hotkey"])
        hint_label(
            self.content,
            "Con varias sesiones abiertas, este atajo toma las flechas "
            "izquierda y derecha para rotar entre ellas. Se apaga con el mismo "
            "atajo, con Esc, o solo a los pocos segundos.",
        )

        field_label(self.content, "Atajo para encoger el panel")
        self.collapse_hotkey = entry(self.content, cfg["collapse_hotkey"])
        hint_label(
            self.content,
            "Deja solo el encabezado a la vista y lo vuelve a desplegar, sin "
            "cerrar la sesion ni perder la respuesta.",
        )

        field_label(self.content, "Atajo para traer el panel al frente")
        self.front_hotkey = entry(self.content, cfg["front_hotkey"])
        hint_label(
            self.content,
            "Lo pone encima de las demas ventanas y lo despliega si estaba "
            "encogido, sin hacer una captura.",
        )

        field_label(self.content, "Atajo para releer respuestas")
        self.scroll_hotkey = entry(self.content, cfg["scroll_hotkey"])
        hint_label(
            self.content,
            "Toma las flechas arriba y abajo para subir por las respuestas "
            "anteriores de la sesion. Al salir vuelve solo a la ultima.",
        )

        field_label(self.content, "Idioma de las respuestas")
        self.language = OptionRow(
            self.content,
            [(k, LANGUAGE_LABELS[k]) for k in ("auto", "es", "en")],
            cfg["language"],
        )
        self.language.pack(fill="x")
        hint_label(
            self.content,
            "En automatico responde en el idioma en que escribas el "
            "pre-prompt o la pregunta. Si no escribes nada, responde en "
            "espanol.",
        )

        field_label(self.content, "Modelo de Claude")
        self.model = OptionRow(
            self.content,
            [
                ("claude-opus-5", "Opus 5 — el mas capaz"),
                ("claude-sonnet-5", "Sonnet 5 — mas barato"),
            ],
            cfg["model"],
        )
        self.model.pack(fill="x")

        field_label(self.content, "API key de Groq")
        self.groq_key = entry(self.content, cfg["groq_api_key"])
        self.groq_key.configure(show="•")
        field_label(self.content, "Modelo de Groq")
        self.groq_model = entry(self.content, cfg["groq_model"])
        field_label(self.content, "Modelo de Groq para las capturas")
        self.groq_vision_model = entry(self.content, cfg["groq_vision_model"])
        hint_label(
            self.content,
            "Si el modelo de Groq no ve imagenes, las preguntas con captura van "
            "al modelo de capturas. Vacio = solo se manda el texto. "
            "La IA de cada sesion se elige al abrirla, o con clic derecho en "
            "el panel.",
        )

        field_label(self.content, "Modelo de ChatGPT")
        self.codex_model = OptionRow(
            self.content,
            [
                ("gpt-6-luna", "gpt-6-luna — el rapido"),
                ("gpt-6-astra", "gpt-6-astra — el mas capaz"),
            ],
            cfg["codex_model"],
        )
        self.codex_model.pack(fill="x")
        hint_label(
            self.content,
            "ChatGPT va por el CLI de Codex con tu login de ChatGPT (codex "
            "login), sin API key.",
        )

        field_label(self.content, "Profundidad de razonamiento")
        self.effort = OptionRow(
            self.content,
            [
                ("low", "Baja — la mas rapida, ideal para mirar y responder"),
                ("medium", "Media"),
                ("high", "Alta — mas lenta y cara"),
            ],
            cfg["effort"],
        )
        self.effort.pack(fill="x")

        field_label(self.content, "Como recuerda \"Usar pasados\"")
        self.history_mode = OptionRow(
            self.content,
            [
                ("resumen", "Resumen — notas de las anteriores; cuesta lo mismo siempre"),
                ("imagenes", "Imagenes — re-envia todas; cada captura cuesta mas"),
            ],
            cfg["history_mode"],
        )
        self.history_mode.pack(fill="x")
        hint_label(
            self.content,
            "Con resumen, Claude ve la captura actual y sus notas de las "
            "anteriores, y si le hace falta pide ver alguna de nuevo.",
        )

        field_label(self.content, "Target de captura por defecto")
        self.target = CaptureTargetPicker(
            self.content, cfg["capture"]["mode"], cfg["capture"]["monitor_index"]
        )
        self.target.pack(fill="x")

        monitors = capture.list_monitors()
        if len(monitors) > 1:
            # Con varias pantallas tiene sentido capturar una y leer en otra.
            field_label(self.content, "Mostrar el panel en")
            opciones = [("", "Donde lo deje")]
            opciones += [(str(m.index), m.label) for m in monitors]
            actual = cfg["panel_monitor"]
            self.panel_monitor = OptionRow(
                self.content, opciones, "" if actual is None else str(actual)
            )
            self.panel_monitor.pack(fill="x")
        else:
            self.panel_monitor = None

        field_label(self.content, "Reglas de concision")
        self.concision = textarea(self.content, cfg["concision"], height=3)

        FlatButton(self.buttons, "Cancelar", self.cancel, padx=12, pady=6).pack(
            side="right"
        )
        PrimaryButton(self.buttons, "Guardar", self._accept, padx=16).pack(
            side="right", padx=(0, 6)
        )

    def _accept(self) -> None:
        self.result = {
            "hotkeys": normalize_hotkeys(self.hotkey.get().split(",")),
            "move_hotkey": self.move_hotkey.get().strip().lower(),
            "switch_hotkey": self.switch_hotkey.get().strip().lower(),
            "collapse_hotkey": self.collapse_hotkey.get().strip().lower(),
            "front_hotkey": self.front_hotkey.get().strip().lower(),
            "scroll_hotkey": self.scroll_hotkey.get().strip().lower(),
            "language": self.language.get(),
            "model": self.model.get(),
            "effort": self.effort.get(),
            "groq_api_key": self.groq_key.get().strip(),
            "groq_model": self.groq_model.get().strip() or "qwen/qwen3.8-27b",
            "groq_vision_model": self.groq_vision_model.get().strip(),
            "codex_model": self.codex_model.get(),
            "history_mode": self.history_mode.get(),
            "capture": self.target.get(),
            "concision": self.concision.get("1.0", "end").strip(),
        }
        if self.panel_monitor is not None:
            elegido = self.panel_monitor.get()
            self.result["panel_monitor"] = int(elegido) if elegido else None
        self.destroy()
