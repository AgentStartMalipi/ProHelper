"""Ejecuta lo que Maria escribiria en el editor (las lineas negras de la pizarra) tal cual.

    python -m speak.tests.board_runner <editor.md o .txt> [--block N]

Junta las lineas escritas de cada guion (un guion por "**[mm:ss] Pregunta:**" en editor.md)
en un .py, lo ejecuta con un limite de tiempo en una carpeta temporal y compara los
"# -> esperado" de la Prueba con lo que imprime de verdad. No modifica nada.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from speak.notes.editor import typed_code  # noqa: F401  (usado por otras pruebas)


def expected_outputs(code: str) -> list[str]:
    """Los '# -> ...' que el guion promete justo despues de un print/llamada."""
    return [m.group(1).strip() for m in re.finditer(r"#\s*->\s*(.+)", code)]


def run(code: str, timeout: float = 10.0) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        path = Path(d) / "board.py"
        path.write_text(code, encoding="utf-8")
        try:
            p = subprocess.run([sys.executable, "-I", str(path)], cwd=d, capture_output=True, text=True,
                               timeout=timeout)
            return p.returncode, (p.stdout + p.stderr).strip()
        except subprocess.TimeoutExpired:
            return -1, f"(se colgo: mas de {timeout:.0f} s)"


def blocks(text: str) -> list[tuple[str, str]]:
    """editor.md -> [(pregunta, guion)]; un .txt suelto es un solo guion."""
    parts = re.split(r"\*\*\[(\d+:\d+)\] Pregunta:\*\*\s*(.*)\n", text)
    if len(parts) == 1:
        return [("(guion)", text)]
    return [(f"[{parts[i]}] {parts[i + 1][:80]}", parts[i + 2].split("\n---\n")[0]) for i in range(1, len(parts), 3)]


def main(argv: list[str]) -> None:
    text = Path(argv[0]).read_text(encoding="utf-8")
    items = blocks(text)
    if "--block" in argv:
        items = [items[int(argv[argv.index("--block") + 1])]]
    for q, script in items:
        code = typed_code(script)
        if not code.strip():
            continue
        rc, out = run(code)
        print(f"\n===== {q}\n--- codigo escrito ({len(code.splitlines())} lineas)\n{code}\n--- ejecucion: "
              f"{'OK' if rc == 0 else 'ERROR'}\n{out or '(sin salida)'}")
        promised = expected_outputs(code)
        if promised:
            print("--- prometido en la Prueba: " + " | ".join(promised))


if __name__ == "__main__":
    main(sys.argv[1:])
