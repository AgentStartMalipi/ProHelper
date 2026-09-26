"""Punto de entrada de SPEAK.

    python -m speak           abre el simulador
    python -m speak --notes   abre directo Notas de llamada
    python -m speak --check   revisa microfono, modelo de voz y LLM (sin UI)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import DATA_DIR, Config


def _setup_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(DATA_DIR / "speak.log", encoding="utf-8")],
    )


def check(cfg: Config) -> int:
    """Diagnostico rapido de cada pieza, por consola."""
    import numpy as np

    from .audio_capture import list_input_devices
    from .llm_client import make_llm
    from .transcriber import make_stt

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ok = True
    devices = list_input_devices()
    print(f"Microfonos: {len(devices)} encontrados" + (f" (p. ej. {devices[0][1]})" if devices else ""))
    ok &= bool(devices)
    t0 = time.time()
    try:
        stt = make_stt(cfg)
        stt.warmup()
        text = stt.transcribe(np.zeros(16000, dtype=np.float32), 16000)
        print(f"Modelo de voz '{cfg.STT_MODEL}': OK ({time.time() - t0:.1f}s; silencio → {text!r})")
    except Exception as exc:
        ok = False
        print(f"Modelo de voz: FALLA → {exc}")
    t0 = time.time()
    try:
        reply = make_llm(cfg).complete("Reply with exactly: ok", "ping")
        print(f"LLM {cfg.LLM_PROVIDER}/{cfg.LLM_MODEL}: {reply.strip()!r} ({time.time() - t0:.1f}s)")
    except Exception as exc:
        ok = False
        print(f"LLM: FALLA → {exc}")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m speak")
    ap.add_argument("--notes", action="store_true", help="abrir Notas de llamada")
    ap.add_argument("--check", action="store_true", help="diagnostico sin UI")
    args = ap.parse_args(argv)
    _setup_logging()
    cfg = Config.load()
    if args.check:
        return check(cfg)

    from PySide6.QtWidgets import QApplication

    from .llm_client import make_llm
    from .simulator import Simulator
    from .transcriber import make_stt

    app = QApplication(sys.argv)
    app.setApplicationName("SPEAK")
    if args.notes:
        from .ui.notes_window import NotesWindow

        win = NotesWindow(cfg)
    else:
        from .ui.main_window import MainWindow

        llm, stt = make_llm(cfg), make_stt(cfg)
        win = MainWindow(cfg, lambda listener: Simulator(cfg, llm, stt, listener))
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
