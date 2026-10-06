"""Punto de entrada: `python -m helper [opciones]`."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from . import capture, dpi, log as logmod
from .claude_client import ClaudeClient, ClaudeError
from .config import Config, load_env
from .session import Session


def cmd_monitors() -> int:
    for mon in capture.list_monitors():
        print(f"  {mon.label}  en ({mon.left}, {mon.top})  [{mon.name}]")
    return 0


def cmd_capture_test(cfg: Config) -> int:
    out = Path(os.environ.get("TEMP", ".")) / "helper-capture-test"
    out.mkdir(parents=True, exist_ok=True)

    targets: list[tuple[str, dict]] = [
        ("active_monitor", {"mode": "active_monitor"}),
        ("active_window", {"mode": "active_window"}),
        ("all", {"mode": "all"}),
    ]
    targets += [
        (f"monitor_{m.index}", {"mode": "monitor", "monitor_index": m.index})
        for m in capture.list_monitors()
    ]

    for name, kwargs in targets:
        path = out / f"{name}.png"
        try:
            capture.capture_to_file(path, max_edge=cfg["max_image_edge"], **kwargs)
            from PIL import Image

            with Image.open(path) as img:
                size = img.size
            print(f"  ok   {name:16} {size[0]}x{size[1]}  {path.stat().st_size // 1024} KB")
        except Exception as exc:
            print(f"  FALLO {name:16} {exc}")

    print(f"\nCapturas en: {out}")
    subprocess.Popen(["explorer", str(out)])
    return 0


def cmd_selftest(cfg: Config, question: str, turns: int) -> int:
    client = ClaudeClient(cfg)
    sess = Session(
        capture_mode=cfg["capture"]["mode"],
        monitor_index=cfg["capture"]["monitor_index"],
    )
    print(f"sesion {sess.session_id}")
    print(f"modelo {cfg['model']} | effort {cfg['effort']}\n")

    try:
        for turn in range(1, turns + 1):
            shot = sess.next_shot_path()
            t0 = time.time()
            capture.capture_to_file(
                shot,
                mode=sess.capture_mode,
                monitor_index=sess.monitor_index,
                max_edge=cfg["max_image_edge"],
            )
            grab_ms = int((time.time() - t0) * 1000)

            t0 = time.time()
            reply = client.send(
                session_id=sess.session_id,
                question=question,
                image_path=shot,
                resume=sess.started,
                system_prompt=cfg.full_system_prompt(sess.preprompt),
            )
            total_ms = int((time.time() - t0) * 1000)
            sess.record(reply.cost_usd)

            print(f"--- turno {turn} ---")
            print(reply.text)
            print(
                f"[captura {grab_ms}ms | claude {total_ms}ms | {reply.cost_label}]\n"
            )
            if turn < turns:
                question = "Sin volver a mirar: que te mande antes?"
    except ClaudeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        sess.close()

    print(f"total sesion: ${sess.total_cost_usd:.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Antes de tocar Tk o mss: fija el modo DPI para que no dependa del orden
    # en que se importen las cosas.
    dpi.enable_awareness()
    logmod.setup()

    parser = argparse.ArgumentParser(prog="helper", description="Helper visual de pantalla")
    parser.add_argument("--monitors", action="store_true", help="lista los monitores")
    parser.add_argument(
        "--capture-test", action="store_true", help="guarda un PNG por cada target"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="captura y pregunta a Claude sin GUI"
    )
    parser.add_argument("--question", default="Que ves en pantalla?")
    parser.add_argument(
        "--turns", type=int, default=1, help="turnos del selftest (prueba el contexto)"
    )
    args = parser.parse_args(argv)

    load_env()  # GROQ_API_KEY y demas claves del .env del proyecto
    cfg = Config.load()

    if args.monitors:
        return cmd_monitors()
    if args.capture_test:
        return cmd_capture_test(cfg)
    if args.selftest:
        return cmd_selftest(cfg, args.question, max(1, args.turns))

    from .ui.app import run_app  # se importa solo si de verdad hay GUI

    logmod.log.info("--- helper arranca ---")
    try:
        return run_app(cfg)
    finally:
        logmod.log.info("--- helper termina ---")


if __name__ == "__main__":
    sys.exit(main())
