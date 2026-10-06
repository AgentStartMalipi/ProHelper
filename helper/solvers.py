"""Ejercicios que se resuelven mejor en Python que con el modelo.

Number Box (Optiver Zap-N): cuatro fichas y un objetivo; hay que usarlas
TODAS, cada una una vez, con + - x /. Los modelos fallan aqui: medido, el de
Groq probaba con dos numeros y daba la cuenta por buena. Leer los numeros de
la captura si lo hacen bien, asi que el reparto es ese: la plantilla le pide
al modelo solo una linea `NUMBER BOX: a b c d -> objetivo`, y la busqueda
exhaustiva se hace aqui, exacta (fracciones, sin redondeos).

La solucion se da en PASOS, como se juega: ficha, operador, ficha, y el
resultado pasa a ser una ficha nueva. Una expresion como `(6 + 10) − 1 × 10`
es correcta, pero leida de izquierda a derecha parece imposible.
"""

from __future__ import annotations

import re
from fractions import Fraction
from itertools import combinations

# `NUMBER BOX: 3 8 2 5 -> 24` (tolera = en vez de ->, comas, corchetes).
_LINEA = re.compile(
    # Solo numeros separados por espacios o comas: "10 - 6 - 1" no es una
    # lista de fichas, es una cuenta que el modelo hizo por su cuenta.
    r"\[?\s*NUMBER\s*BOX\s*:\s*(\d+(?:\.\d+)?(?:[\s,]+\d+(?:\.\d+)?)+)"
    r"\s*(?:->|→|=)\s*(-?\d+(?:\.\d+)?)\s*\]?",
    re.IGNORECASE,
)

# Con mas numeros la busqueda crece demasiado para responder al instante.
MAX_NUMEROS = 6

# Un paso: (a, operador, b, resultado).
Paso = tuple[Fraction, str, Fraction, Fraction]


def _bonito(f: Fraction) -> str:
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def resolver(numeros: list[Fraction], objetivo: Fraction) -> list[Paso] | None:
    """Los pasos que usan todas las fichas y dejan el objetivo, o None.

    Primero busca una solucion "limpia" (cada resultado un entero no
    negativo), que es la que se juega sin pensar; solo si no la hay, cualquiera.
    """
    return _resolver(numeros, objetivo, limpio=True) or _resolver(
        numeros, objetivo, limpio=False)


def _resolver(numeros: list[Fraction], objetivo: Fraction,
              limpio: bool) -> list[Paso] | None:
    vistos: set[tuple] = set()

    def buscar(fichas: list[Fraction]) -> list[Paso] | None:
        if len(fichas) == 1:
            return [] if fichas[0] == objetivo else None
        clave = tuple(sorted(fichas))
        if clave in vistos:
            return None  # este juego de fichas ya se probo y no llega
        vistos.add(clave)
        for i, j in combinations(range(len(fichas)), 2):
            a, b = fichas[i], fichas[j]
            resto = [fichas[k] for k in range(len(fichas)) if k not in (i, j)]
            # El mayor primero en la resta y la division: asi se juega.
            grande, chico = (a, b) if a >= b else (b, a)
            opciones: list[Paso] = [
                (a, "+", b, a + b),
                (a, "×", b, a * b),
                (grande, "−", chico, grande - chico),
                (chico, "−", grande, chico - grande),
            ]
            if chico != 0:
                opciones.append((grande, "÷", chico, grande / chico))
            if grande != 0:
                opciones.append((chico, "÷", grande, chico / grande))
            for paso in opciones:
                valor = paso[3]
                if limpio and (valor < 0 or valor.denominator != 1):
                    continue
                siguientes = buscar(resto + [valor])
                if siguientes is not None:
                    return [paso] + siguientes
        return None

    return buscar(list(numeros))


def texto_pasos(pasos: list[Paso]) -> str:
    return " → ".join(
        f"{_bonito(a)} {op} {_bonito(b)} = {_bonito(r)}" for a, op, b, r in pasos
    )


def number_box_sin_linea(texto: str) -> bool:
    """El modelo hablo de un Number Box pero no dio la linea para resolverlo.

    Visto con qwen en Groq: a veces se salta el formato y hace la cuenta el
    mismo, mal ("10 - 6 × 1 -> 6", sin usar todas las fichas). Esa respuesta
    no sirve; la app la pide de nuevo a Claude, que si sigue el formato.
    """
    return "number box" in texto.lower() and not _LINEA.search(texto)


def _leer_linea(m: re.Match) -> tuple[list[Fraction], Fraction] | None:
    crudos = [t for t in re.split(r"[\s,]+", m.group(1).strip()) if t]
    try:
        return [Fraction(t) for t in crudos], Fraction(m.group(2))
    except (ValueError, ZeroDivisionError):
        return None


def number_box_mal_leido(texto: str) -> bool:
    """Hay una linea de Number Box, pero con esos numeros no hay solucion.

    Los juegos siempre tienen solucion, asi que casi seguro el modelo leyo mal
    un numero (visto con qwen en Groq: el 0 tachado como 8 o 9). La app pide
    entonces la misma captura a Claude, que lee bien la pantalla entera.
    """
    for m in _LINEA.finditer(texto):
        leido = _leer_linea(m)
        if leido is None:
            continue
        numeros, objetivo = leido
        if 2 <= len(numeros) <= MAX_NUMEROS and resolver(numeros, objetivo) is None:
            return True
    return False


def aplicar(texto: str) -> str:
    """Reemplaza cada linea `NUMBER BOX: ...` por la solucion calculada."""

    def sustituir(m: re.Match) -> str:
        crudos = [t for t in re.split(r"[\s,]+", m.group(1).strip()) if t]
        try:
            numeros = [Fraction(t) for t in crudos]
            objetivo = Fraction(m.group(2))
        except (ValueError, ZeroDivisionError):
            return m.group(0)
        leidos = " ".join(crudos)
        if not 2 <= len(numeros) <= MAX_NUMEROS:
            return f"[Number Box: lei {leidos} -> {m.group(2)}; revisa los numeros]"
        pasos = resolver(numeros, objetivo)
        if pasos is None:
            # Casi siempre es un numero mal leido: que se vea cuales leyo.
            return (f"[Number Box: sin solucion con {leidos} -> {m.group(2)}; "
                    f"revisa si lei bien los numeros]")
        return f"[Number Box: {texto_pasos(pasos)}]"

    return _LINEA.sub(sustituir, texto)
