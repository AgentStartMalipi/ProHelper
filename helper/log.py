"""Registro a archivo.

El helper corre con `pythonw`, que no tiene consola: sin esto, cuando algo no
pasa no queda ni rastro de si el atajo llego, si fallo la captura o si Claude
devolvio un error. El archivo vive junto a la configuracion.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import config_dir

log = logging.getLogger("helper")


def log_path():
    return config_dir() / "helper.log"


def setup(level: int = logging.INFO) -> None:
    if log.handlers:  # ya configurado
        return

    log.setLevel(level)
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=256_000, backupCount=1, encoding="utf-8"
        )
    except OSError:
        return  # sin log se puede vivir; sin arrancar no

    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S")
    )
    log.addHandler(handler)

    # Una excepcion no capturada en pythonw desaparece en silencio.
    def on_uncaught(exc_type, exc, tb):
        log.error("fallo sin capturar", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = on_uncaught
