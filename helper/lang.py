"""Deteccion de idioma para lo que escribe el usuario.

Pedirle al modelo "responde en el idioma del usuario" no basta: el resto de las
instrucciones son un bloque largo en espanol y eso arrastra la respuesta a
espanol pase lo que pase. Lo que si funciona es darle la orden escrita EN el
idioma destino, y para eso hay que saber cual es antes de armar el prompt.

No hace falta un detector serio: los textos son cortos (un pre-prompt, una
pregunta) y solo hay que distinguir dos idiomas.
"""

from __future__ import annotations

import re

ESPANOL = "es"
INGLES = "en"

# Letras y signos que en la practica solo aparecen en espanol.
_SIGNOS_ES = re.compile(r"[áéíóúüñ¿¡]", re.IGNORECASE)

_PALABRAS_ES = {
    "que", "qué", "como", "cómo", "por", "para", "el", "la", "los", "las",
    "un", "una", "esto", "esta", "este", "cual", "cuál", "dime", "explica",
    "explicame", "explícame", "codigo", "código", "pantalla", "respuesta",
    "responde", "pregunta", "hay", "del", "con", "sin", "mas", "más", "no",
    "me", "mi", "y", "es", "son", "esta", "está", "muy", "aqui", "aquí",
}

_PALABRAS_EN = {
    "the", "what", "what's", "how", "why", "is", "are", "this", "that",
    "explain", "answer", "code", "screen", "give", "me", "please", "of",
    "in", "on", "with", "without", "and", "or", "to", "for", "it", "does",
    "do", "can", "should", "which", "where", "when", "a", "an", "be",
}

# "me" esta en las dos listas: no debe desempatar por si sola.
_AMBIGUAS = _PALABRAS_ES & _PALABRAS_EN


def detect(text: str) -> str | None:
    """Devuelve 'es', 'en', o None si no hay senales suficientes."""
    if not text or not text.strip():
        return None

    if _SIGNOS_ES.search(text):
        return ESPANOL

    palabras = re.findall(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ']+", text.lower())
    if not palabras:
        return None

    es = sum(1 for p in palabras if p in _PALABRAS_ES and p not in _AMBIGUAS)
    en = sum(1 for p in palabras if p in _PALABRAS_EN and p not in _AMBIGUAS)

    if es > en:
        return ESPANOL
    if en > es:
        return INGLES
    return None
