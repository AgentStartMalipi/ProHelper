"""Punto de entrada de SPEAK.

    python -m speak             pantalla de inicio (practicar o llamada real)
    python -m speak --practice  abre directo el simulador
    python -m speak --notes     abre directo Llamadas (copiloto y notas)
    python -m speak --check   revisa microfono, modelo de voz y LLM (sin UI)
    python -m speak --mics    prueba cada microfono con tu voz y dice cual usar
    python -m speak --mics --auto   lo mismo, sin pulsar Enter (cuenta regresiva)
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
    ok &= bool(devices)
    try:
        from .audio_capture import open_input_16k

        stream, info = open_input_16k(cfg.mic_device, lambda x, status: None)
        stream.close()
        print(f"Microfono: {info['name']} ({info['hostapi']}, abre a {info['opened_rate']} Hz"
              + (", remuestreado a 16 kHz" if info["resampled"] else "") + ")"
              + ("  [MIC_DEVICE=" + cfg.MIC_DEVICE + "]" if cfg.MIC_DEVICE else "  [el de Windows]"))
        print("  Para elegir otro: python -m speak --mics")
    except Exception as exc:
        ok = False
        print(f"Microfono: FALLA → {exc}")
    try:
        from .notes.recorder import list_outputs, pick_loopback

        default, outputs = list_outputs()
        chosen = pick_loopback([{"name": n} for n in outputs], default, cfg.LOOPBACK_DEVICE)
        want = cfg.LOOPBACK_DEVICE.strip()
        if not want:
            tag = "  [salida por defecto]"
        elif chosen and want.lower() in chosen["name"].lower():
            tag = f"  [LOOPBACK_DEVICE={want!r}]"
        else:
            tag = f"  [⚠ LOOPBACK_DEVICE={want!r} no existe: uso la salida por defecto]"
        print(f"Audio de la llamada (\"Ellos\"): se graba de {chosen['name'] if chosen else '—'}{tag}")
        print("  Salidas disponibles: " + " | ".join(outputs))
        print("  Si escuchas la llamada por otra (audifonos), pon en speak/.env LOOPBACK_DEVICE=<parte del nombre>")
        ok &= chosen is not None
    except Exception as exc:
        print(f"Audio de la llamada: FALLA → {exc}")
        ok = False
    t0 = time.time()
    try:
        stt = make_stt(cfg)
        stt.warmup()
        text = stt.transcribe(np.zeros(16000, dtype=np.float32), 16000)
        label = (f"Deepgram {cfg.DEEPGRAM_MODEL}" if cfg.STT_PROVIDER == "deepgram"
                 else f"Whisper '{cfg.STT_MODEL}'")
        print(f"Modelo de voz {label}: OK ({time.time() - t0:.1f}s; silencio → {text!r})")
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


BLOCKED, NO_VOICE, LOW, GOOD, CLIPPED = (
    "SIN SEÑAL (bloqueado o apagado)", "no se oyo voz (¿hablaste?)", "muy bajo", "bien", "saturado")


def _mic_verdict(peak: float, nonzero: int) -> str:
    """Medido: un microfono bloqueado entrega ceros exactos; uno que funciona,
    en una sala en silencio, pica por debajo de 0,001 (no es lo mismo)."""
    if nonzero == 0:
        return BLOCKED
    if peak < 0.005:
        return NO_VOICE
    if peak < 0.1:
        return LOW
    return GOOD if peak < 0.95 else CLIPPED


def recommend_mic(results: list[tuple[float, int, str, str]]) -> tuple[int, str, str] | None:
    """(pico, indice, nombre, veredicto) → el mejor: primero los "bien", y
    entre iguales el de pico mas alto. None si ninguno sirve."""
    rank = {GOOD: 3, LOW: 2, CLIPPED: 1}
    usable = [r for r in results if r[3] in rank]
    if not usable:
        return None
    best = max(usable, key=lambda r: (rank[r[3]], r[0]))
    return best[1], best[2], best[3]


def mics(cfg: Config, seconds: float = 5.0, auto: bool = False) -> int:
    """Graba unos segundos de cada microfono (tu hablando), mide el nivel y
    transcribe con Whisper. Al final recomienda el mejor y como fijarlo.

    `auto`: sin pulsar Enter (cuenta regresiva de 3 s por microfono), para
    correrlo desde otra herramienta o sin teclado."""
    import numpy as np
    import sounddevice as sd

    from .audio_capture import open_input_16k
    from .transcriber import make_stt

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Todo lo que se imprime queda tambien en data/mic_test.txt, para poder
    # revisarlo (o pasarselo a alguien) despues de cerrar la ventana.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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
    stt = make_stt(cfg, model=cfg.STT_LIVE_MODEL or None)
    stt.warmup()
    phrase = "Hola, esta es una prueba del microfono. How are you today?"
    results = []
    for i, d in devices:
        name = d["name"]
        if auto:
            print(f"\n[{i}] {name}\n    Di en voz normal: \"{phrase}\"")
            for left in range(3, 0, -1):
                print(f"    empieza en {left}...", end="\r", flush=True)
                time.sleep(1)
        else:
            try:
                input(f"\n[{i}] {name}\n    Pulsa Enter y di en voz normal: \"{phrase}\"")
            except EOFError:  # sin teclado (p. ej. lanzado desde otra herramienta)
                auto = True
        chunks: list[np.ndarray] = []
        try:
            # El mismo camino que usa SPEAK al grabar: si aqui abre, alla tambien.
            stream, info = open_input_16k(i, lambda x, status: chunks.append(x.copy()))
            with stream:
                for left in range(int(seconds), 0, -1):
                    print(f"    grabando... {left}  ", end="\r", flush=True)
                    time.sleep(1)
        except Exception as exc:
            print(f"    NO ABRE: {exc}")
            continue
        x = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
        if not x.size:
            print("    NO ENTREGO AUDIO")
            continue
        rms, peak = float(np.sqrt(np.mean(x ** 2))), float(np.abs(x).max())
        text = stt.transcribe(x, 16000) if peak > 0.001 else ""
        verdict = _mic_verdict(peak, int(np.count_nonzero(x)))
        print(f"    nivel: pico {peak:.2f}, rms {rms:.3f} → {verdict}"
              + (f"  (abierto a {info['opened_rate']} Hz)" if info.get("resampled") else ""))
        print(f"    Whisper entendio: {text!r}")
        results.append((peak, i, name, verdict))
    best = recommend_mic(results)
    if best is None:
        if any(r[3] == NO_VOICE for r in results):
            print("\nLos microfonos funcionan pero no se oyo voz. Vuelve a probar hablando en voz normal.")
        else:
            print("\nNingun microfono dio señal. Revisa Configuracion > Privacidad > Microfono: "
                  "'Permitir que las aplicaciones de escritorio accedan al microfono'.")
        return 1
    index, name, verdict = best
    print(f"\nRecomendado: {name} ({verdict}).")
    print(f"Para usarlo, pon en speak/.env:  MIC_DEVICE={index}")
    if verdict == LOW:
        print("Esta bajo: sube su volumen en Configuracion > Sistema > Sonido > Entrada.")
    print(f"(Resultado guardado en {report_file})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m speak")
    ap.add_argument("--notes", action="store_true", help="abrir Llamadas (copiloto y notas)")
    ap.add_argument("--practice", action="store_true", help="abrir el simulador de entrevistas")
    ap.add_argument("--check", action="store_true", help="diagnostico sin UI")
    ap.add_argument("--mics", action="store_true", help="probar cada microfono con tu voz")
    ap.add_argument("--auto", action="store_true", help="con --mics: sin pulsar Enter")
    args = ap.parse_args(argv)
    _setup_logging()
    cfg = Config.load()
    if args.check:
        return check(cfg)
    if args.mics:
        return mics(cfg, auto=args.auto)

    from PySide6.QtWidgets import QApplication

    from .llm_client import make_llm
    from .simulator import Simulator
    from .transcriber import make_stt

    app = QApplication(sys.argv)
    app.setApplicationName("SPEAK")
    from .ui.home_window import HomeWindow, open_calls, open_practice

    # El simulador se arma al abrirlo, no al arrancar: abrir solo Llamadas no
    # paga la carga del modelo de voz del simulador.
    def sim_factory(listener):
        return Simulator(cfg, make_llm(cfg), make_stt(cfg), listener)

    home = HomeWindow(cfg, sim_factory)
    if args.notes:
        open_calls(cfg)
    elif args.practice:
        open_practice(cfg)
    else:
        home.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
