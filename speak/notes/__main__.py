"""Notas de llamada por consola.

    python -m speak.notes record [--mode entrevista]     graba hasta Enter y analiza
    python -m speak.notes analyze RUTA [--mode reunion]  carpeta, audio o transcripcion
    python -m speak.notes analyze RUTA --no-llm          solo transcripcion + preguntas

Todo queda en speak/data/notes/<fecha>/ (transcript.md, notes.md, audio).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from ..config import DATA_DIR, Config
from ..llm_client import make_llm
from ..transcriber import make_stt
from .analyzer import MODES, generate_notes, heuristic_report, me_share
from .pipeline import load_any, render


def _out_dir() -> Path:
    d = DATA_DIR / "notes" / time.strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _process(path: Path, out: Path, cfg: Config, mode: str, use_llm: bool) -> None:
    tr = load_any(path, lambda: make_stt(cfg, for_files=True), progress=lambda m: print(m))
    text = render(tr)
    (out / "transcript.md").write_text(text + "\n", encoding="utf-8")
    print(f"\nTranscripcion: {len(tr.segments)} segmentos → {out / 'transcript.md'}")
    print(heuristic_report(tr))
    if any(s.speaker == "Yo" for s in tr.segments):
        print(f"Hablaste el {me_share(tr):.0%} del tiempo (por palabras).")
    if not use_llm:
        return
    print("\nGenerando notas...\n")
    notes = generate_notes(make_llm(cfg), tr, mode,
                           on_chunk=None)
    (out / "notes.md").write_text(notes + "\n", encoding="utf-8")
    print(notes)
    print(f"\nNotas → {out / 'notes.md'}")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m speak.notes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="graba microfono + audio del sistema")
    rec.add_argument("--mode", choices=list(MODES), default="entrevista")
    rec.add_argument("--no-llm", action="store_true")
    an = sub.add_parser("analyze", help="analiza una carpeta, un audio o una transcripcion")
    an.add_argument("path", type=Path)
    an.add_argument("--mode", choices=list(MODES), default="entrevista")
    an.add_argument("--no-llm", action="store_true")
    args = ap.parse_args(argv)
    cfg = Config.load()

    if args.cmd == "record":
        from .recorder import DualRecorder

        answer = input("¿Todos los participantes saben y aceptaron que se grabe? (s/n): ")
        if answer.strip().lower() not in {"s", "si", "sí", "y", "yes"}:
            print("Sin consentimiento no se graba.")
            return 1
        out = _out_dir()
        recorder = DualRecorder(out)
        recorder.start()
        for w in recorder.warnings:
            print("Aviso:", w)
        input("Grabando. Pulsa Enter para detener...")
        recorder.stop()
        print(f"Grabado en {out}")
        _process(out, out, cfg, args.mode, not args.no_llm)
        return 0

    path = args.path.resolve()
    if not path.exists():
        print(f"No existe: {path}")
        return 1
    out = path if path.is_dir() else _out_dir()
    if path.is_file() and path.suffix.lower() in {".txt", ".md", ".vtt"}:
        shutil.copy2(path, out / f"original{path.suffix}")
    _process(path, out, cfg, args.mode, not args.no_llm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
