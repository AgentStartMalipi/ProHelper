"""Punto de entrada de SPEAK.

    python -m speak           abre el simulador
    python -m speak --notes   abre directo Notas de llamada
    python -m speak --check   revisa microfono, modelo de voz y LLM (sin UI)
    python -m speak --mics    prueba cada microfono con tu voz y dice cual usar
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


def mics(cfg: Config, seconds: float = 5.0) -> int:
    """Graba unos segundos de cada microfono (tu hablando), mide el nivel y
    transcribe con Whisper. Al final recomienda el mejor y como fijarlo."""
    import numpy as np
    import sounddevice as sd

    from .notes.live import to_16k
    from .transcriber import make_stt

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Todo lo que se imprime queda tambien en data/mic_test.txt, para poder
    # revisarlo (o pasarselo a alguien) despues de cerrar la ventana.
    report_file = DATA_DIR / "mic_test.txt"
    lines: list[str] = []
    import builtins

    def print(*a, **k):  # noqa: A001 - sombra local a proposito
        builtins.print(*a, **k)
        if k.get("end") != "\r":  # la cuenta regresiva no va al archivo
            lines.append(" ".join(str(x) for x in a).strip("\n"))
            report_file.write_text(time.strftime("%Y-%m-%d %H:%M:%S\n") + "\n".join(lines) + "\n",
                                   encoding="utf-8")

    apis = {i: a["name"] for i, a in enumerate(sd.query_hostapis())}
    # WASAPI es lo que usa Windows hoy; MME repite los mismos con otro nombre.
    devices = [(i, d) for i, d in enumerate(sd.query_devices())
               if d["max_input_channels"] > 0 and apis[d["hostapi"]] == "Windows WASAPI"]
    if not devices:
        devices = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    print(f"{len(devices)} microfonos. Cargando el modelo de voz...")
    stt = make_stt(cfg)
    stt.warmup()
    phrase = "Hola, esta es una prueba del microfono. How are you today?"
    results = []
    for i, d in devices:
        name = d["name"]
        input(f"\n[{i}] {name}\n    Pulsa Enter y di en voz normal: \"{phrase}\"")
        sr = int(d["default_samplerate"])
        try:
            rec = sd.rec(int(sr * seconds), samplerate=sr, channels=1, device=i, dtype="float32")
            for left in range(int(seconds), 0, -1):
                print(f"    grabando... {left}", end="\r", flush=True)
                time.sleep(1)
            sd.wait()
        except Exception as exc:
            print(f"    NO ABRE: {exc}")
            continue
        x, _ = to_16k(rec[:, 0], sr)
        rms, peak = float(np.sqrt(np.mean(x ** 2))), float(np.abs(x).max())
        text = stt.transcribe(x, 16000) if peak > 0.001 else ""
        verdict = ("SIN SEÑAL (bloqueado o apagado)" if peak < 0.001 else
                   "muy bajo" if peak < 0.1 else "bien" if peak < 0.95 else "saturado")
        print(f"    nivel: pico {peak:.2f}, rms {rms:.3f} → {verdict}")
        print(f"    Whisper entendio: {text!r}")
        results.append((peak, i, name, verdict))
    usable = [r for r in results if r[3] in ("bien", "muy bajo")]
    if not usable:
        print("\nNingun microfono dio señal. Revisa Configuracion > Privacidad > Microfono: "
              "'Permitir que las aplicaciones de escritorio accedan al microfono'.")
        return 1
    best = max(usable, key=lambda r: (r[3] == "bien", r[0]))
    # SPEAK abre el microfono a 16 kHz: por WASAPI muchos dispositivos lo
    # rechazan; por MME Windows convierte solo. MME corta el nombre a 31
    # caracteres, asi que se busca por prefijo.
    index = best[1]
    for i, d in enumerate(sd.query_devices()):
        if (d["max_input_channels"] > 0 and apis[d["hostapi"]] == "MME"
                and best[2].startswith(d["name"].rstrip())):
            index = i
            break
    print(f"\nRecomendado: {best[2]} ({best[3]}).")
    print(f"Para usarlo, pon en speak/.env:  MIC_DEVICE={index}")
    if best[3] == "muy bajo":
        print("Esta bajo: sube su volumen en Configuracion > Sistema > Sonido > Entrada.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m speak")
    ap.add_argument("--notes", action="store_true", help="abrir Notas de llamada")
    ap.add_argument("--check", action="store_true", help="diagnostico sin UI")
    ap.add_argument("--mics", action="store_true", help="probar cada microfono con tu voz")
    args = ap.parse_args(argv)
    _setup_logging()
    cfg = Config.load()
    if args.check:
        return check(cfg)
    if args.mics:
        return mics(cfg)

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
