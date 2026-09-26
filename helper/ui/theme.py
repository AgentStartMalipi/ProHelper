"""Paleta y tipografias del widget.

Tema oscuro fijo: el widget vive encima de otras ventanas y un panel claro
molesta la vista cuando lo tienes todo el dia en una esquina.
"""

BG = "#16181d"
BG_HEADER = "#1e2128"
BG_INPUT = "#0f1115"
BG_HOVER = "#2a2e37"

FG = "#e6e8ec"
FG_DIM = "#8b919e"
FG_FAINT = "#5c6270"

ACCENT = "#c96442"
ACCENT_HOVER = "#d97757"
OK = "#4ea672"
WARN = "#d4a04a"
ERROR = "#d9534f"

CODE = "#9ecbff"
LEAD = "#ffffff"

BORDER = "#2c3038"

FONT = ("Segoe UI", 9)
FONT_SMALL = ("Segoe UI", 8)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 10, "bold")
FONT_BODY = ("Segoe UI", 10)
FONT_LEAD = ("Segoe UI", 11, "bold")   # la primera linea: la respuesta
FONT_BODY_BOLD = ("Segoe UI", 10, "bold")
FONT_CODE = ("Consolas", 10)

# Medidas en pixeles. Con el proceso DPI-aware nadie las escala por nosotros,
# asi que `apply_scale` las ajusta una vez al arrancar el panel.
_BASE_PAD = 10
_BASE_WIDTH = 380
# Una funcion entera no cabe en 380px: las lineas se parten por la mitad y se
# lee peor que en el editor. Con codigo el panel se ensancha.
_BASE_WIDTH_CODE = 560
_BASE_WRAP = 380

PAD = _BASE_PAD
WIDTH = _BASE_WIDTH
WIDTH_CODE = _BASE_WIDTH_CODE
WRAP = _BASE_WRAP


def apply_scale(factor: float) -> None:
    """Ajusta las medidas al DPI de la pantalla. Se llama una vez, al inicio.

    Las fuentes no entran aqui: van en puntos y las escala Tk via `tk scaling`.
    """
    global PAD, WIDTH, WIDTH_CODE, WRAP
    PAD = max(1, round(_BASE_PAD * factor))
    WIDTH = round(_BASE_WIDTH * factor)
    WIDTH_CODE = round(_BASE_WIDTH_CODE * factor)
    WRAP = round(_BASE_WRAP * factor)
