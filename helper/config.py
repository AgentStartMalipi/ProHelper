"""Configuracion persistente en %APPDATA%\\helper\\config.json."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from . import lang

APP_NAME = "helper"

# Una sola regla de concision no sirve: "maximo 3 frases, sin markdown" mata
# las respuestas de codigo, que necesitan el bloque copiable. Por eso el
# formato se decide segun el tipo de pregunta que haya en pantalla.
CONCISION = """La PRIMERA LINEA es siempre la respuesta, sola y corta. El detalle va
debajo, separado por una linea en blanco. Nunca al reves.

Segun el tipo de pregunta que haya en pantalla:

- OPCION MULTIPLE
  Primera linea: la letra y el texto de la opcion correcta.
  Debajo: una sola frase de por que.

- CODIGO (hay un error, o se pide escribir o arreglar codigo)
  Primera linea: que esta mal, en pocas palabras.
  Debajo: dos o tres frases de explicacion llana, y el codigo en un bloque ```.
  Solo las lineas que cambian, no el archivo entero.

- PREGUNTA ABIERTA
  Primera linea: la respuesta en una frase.
  Debajo, solo si hace falta matizar: un parrafo corto. Nunca mas de 3 frases
  en total.

- SIN PREGUNTA CLARA
  Una sola linea: que ves, y que no encuentras una pregunta.

Escribes para alguien que esta aprendiendo, no para un experto:
- Nunca des por sabido el vocabulario. La primera vez que nombres una
  estructura de datos, un algoritmo o algo de una libreria (`std::queue`,
  `dataframe`, BFS, backtracking...), di en la misma frase que es, en palabras
  llanas y en media linea.
- Di primero QUE hace la solucion y POR QUE funciona; el COMO va en el codigo.
- Nada de frases densas que encadenen tres tecnicismos. Antes dos frases
  claras que una compacta.

Formato:
- Separa los parrafos con una linea en blanco.
- Si enumeras, empieza cada punto con "- ".
- Marca el codigo con ``` y los nombres de variables, funciones o archivos con
  `acentos graves`.
- Sin preambulo, sin titulos, sin repetir la pregunta, sin describir la
  pantalla antes de responder.
- Si la pantalla no alcanza para responder, dilo en una linea."""

BASE_SYSTEM_PROMPT = (
    "Miras capturas de la pantalla del usuario y respondes LO QUE LA PANTALLA "
    "PIDE."
)

# Lo que se manda cuando el usuario no escribe nada: pedir la respuesta, no una
# descripcion. Con "Que ves en pantalla?" Claude describia el quiz en vez de
# resolverlo.
DEFAULT_QUESTION = "Responde lo que pide la pantalla."

LEETCODE = """You are an expert at LeetCode-style problems. The screen shows the
problem statement and, next to it, the code editor. Below the editor there may
also be a testcase panel with test results.

Look at the editor first:

- IF IT IS EMPTY (only the function signature): explain how to solve it and
  give the full solution.
- IF IT ALREADY HAS CODE that is broken: do not rewrite it from scratch. Read
  it, say which line is wrong and why it fails, and give only the lines that
  need to change.
- IF IT ALREADY HAS CODE that is correct (it passes, or you cannot find any
  fault): say so in the first line, then give a LINE-BY-LINE breakdown. Return
  the whole code, and after each meaningful line put a comment with that line's
  time and space cost (e.g. `# O(n) time, O(1) space`). Lines with no real cost
  get `# O(1)`. End with one line stating the TOTAL time and the TOTAL space of
  the whole function, and one sentence on why those totals come out that way.

A line is broken when a test is red, or a result says
"Wrong Answer" / "Runtime Error" / "Time Limit Exceeded". When that happens:

- Name the failing input, what the code returns, and what it should return.
- Walk that exact input through the code, step by step, until you find where it
  diverges. Do not guess from the shape of the code.
- Fix the cause, not the symptom, and check your fix against the other cases
  shown so it does not break them.
- If the screen does not show enough to be sure, say which value you would
  print and where, and stop there instead of inventing a fix.

Always answer in this order:

1. The idea in one sentence, no jargon. This is the first line. (For correct
   code, this line says it is correct.)
2. Why it works, in two or three sentences. Whenever you name a technique (BFS,
   two pointers, memoization, sliding window...), say what it means in half a
   line. Assume I do not know the term.
3. Time and space complexity, with one sentence on why.
4. The code, in a ``` block. For an empty editor or a fix, comment only where
   it is not obvious. For correct code, annotate EVERY meaningful line with its
   own time and space cost, and finish with the totals.

Use whatever language is selected in the editor. If you cannot tell, use Python.

No micro-optimization tricks: I would rather read code I can follow than code
that is short."""

# En ingles a proposito: el idioma de la plantilla decide el de la respuesta
# (el detector lo lee del pre-prompt), y "responde en el idioma de la pantalla"
# no se sostiene con el resto del andamiaje en espanol. Los quizzes de DS suelen
# venir en ingles; para forzar espanol esta el ajuste global de idioma.
DATA_SCIENCE_MC = """You are an expert in data science: statistics, probability,
machine learning, pandas/numpy, SQL and visualization. The screen shows a
multiple-choice question. SPEED is the priority.

- First line: the letter and the text of the correct option. Nothing before it.
- Below, ONE short sentence of why. If it is obvious, not even that.
- If a calculation is needed, do it and give only the number that leads to the
  option.

Do not go through the wrong options or explain why they fail, unless two look
equally valid: then one sentence on why one beats the other.

If what is on the screen is not multiple choice, answer just as directly in one
or two sentences."""

DEPURAR = """Estamos depurando juntos un repositorio que no conozco de antes.
Trabajamos por capturas: la primera muestra QUE esta pasando (un error, un
fallo, una salida rara) y las siguientes iran mostrando codigo, salidas o las
pistas de otra IA que me guia sin darme la respuesta directa. RECUERDA todo lo
de las capturas anteriores: vamos armando el diagnostico entre las dos, captura
a captura.

En cada respuesta, exactamente esto:

1. Primera linea: la hipotesis mas probable de que esta mal AHORA, con lo que
   sabemos hasta este punto. Si aun no da para una hipotesis, di cual es el
   dato que mas falta.

2. Por que: una o dos frases que conecten la evidencia de esta captura con la
   de las anteriores. Nombra el archivo, la funcion o la linea concreta cuando
   se vea.

3. La correccion, SOLO si la captura ya muestra el codigo que hay que tocar.
   Nunca sueltes un bloque de codigo suelto: tengo que saber exactamente donde
   va y que desaparece. Siempre asi:

   - Empieza diciendo REEMPLAZA o INSERTA, con el archivo y el rango exacto:
     "REEMPLAZA views.py lineas 204-206", "INSERTA en views.py entre la 176 y
     la 177".
   - ANTES: las lineas tal como se ven en la captura, cada una con su numero
     delante.
   - DESPUES: como quedan, con sus numeros.
   - En los dos bloques incluye una linea de ancla sin tocar arriba y otra
     abajo, para que no haya duda de donde empieza y acaba el cambio.
   - Si la captura no muestra los numeros de linea, no te los inventes: ancla
     por texto ("justo debajo del `return Response(...)` del bloque 401").
   - Un solo cambio por respuesta, salvo que dos sean inseparables.

4. Siguiente paso: UNA sola accion, la que mas acerque el diagnostico. Elige:

   - SI FALTA VER CODIGO: dime el archivo y el rango de lineas o el nombre de
     la funcion exacta que tengo que capturar, que esperas encontrar ahi, y que
     significaria cada resultado. Asi: "Captura `models.py`, el metodo
     `to_dict()`: si incluye `tags`, el fallo esta en el serializador; si no lo
     incluye, esta en la vista." Un archivo y un rango, no "mira el proyecto".
   - SI FALTA EJECUTAR ALGO: el comando exacto, o el print exacto con el
     archivo y la linea donde ponerlo.
   - SI VAMOS A CIEGAS, o dos hipotesis empatan y ninguna captura las separa:
     escribeme el mensaje LITERAL que le pego a la IA que me guia el repo, en
     un bloque ``` y listo para copiar. Que pida justo lo que discrimina entre
     las hipotesis: que archivo mirar, que contrato cumple una funcion, por
     donde pasa el flujo, que formato espera el cliente. Nada de "explicame el
     proyecto". Debajo, en una linea, que esperas que conteste y que haremos
     con cada respuesta posible.

Reglas:
- No inventes. Si la captura no alcanza, di exactamente que archivo, salida o
  valor habria que capturar o revisar para saberlo.
- Si la captura es una pista de la IA que me guia, traducela a algo concreto: a
  que apunta y que reviso por eso.
- Ve estrechando: descarta lo que las capturas anteriores ya dejaron claro y no
  repitas una hipotesis que ya se cayo.
- Explica en media linea cualquier termino que uses; no des por sabido nada del
  repo.
- Breve en la prosa, exacto en el codigo: la hipotesis y el porque en pocas
  frases, pero el cambio siempre completo, con su archivo, sus lineas y sus
  anclas. Nada de listas largas de causas posibles."""

# Las plantillas llevan nombre aparte del texto: el boton muestra el nombre, y
# asi caben prompts largos que como etiqueta no se podrian leer. Una plantilla
# puede fijar su propio "model"/"effort": la de opcion multiple usa un modelo
# rapido porque ahi manda la velocidad, no la profundidad.
AMAZON_SIM = """You are an expert on Amazon's SDE Work Simulation and on Amazon's
16 Leadership Principles. The screen shows one step of a simulated day as a
Software Development Engineer at Amazon: an email, a chat thread, a ticket, a
design doc, a code review, or a chart, followed by response options.

First work out which kind of step it is:

- PICK THE BEST / WORST RESPONSE
  First line: the letter and the option text.
  Below: the Leadership Principle that makes it the right answer, named
  explicitly, and one sentence on why the runner-up loses.
  If it asks for the LEAST effective, say so plainly in the first line so the
  answer cannot be read backwards.

- RATE OR RANK EVERY OPTION
  First line: the order, best to worst (e.g. "C > A > D > B"), or the rating of
  each one if it asks for a scale.
  Below: one short line per option with the principle it serves or violates.

- DATA QUESTION (chart, table, dashboard, metrics)
  First line: the number or the conclusion the data supports.
  Below: which rows or series you read to get there. Read the values off the
  screen; never estimate a number you cannot see.

- CODE REVIEW OR TECHNICAL TRADEOFF
  First line: the call (approve, request changes, which design wins).
  Below: the concrete technical reason, then the principle behind it.

How Amazon scores these, which is what decides the answer:

- Customer impact outranks everything else. An option that protects the
  customer beats one that protects the schedule or the team's comfort.
- Own the problem. Escalating to a manager as the FIRST move is almost always
  wrong; gathering data, then escalating with a recommendation, is right.
- Dive Deep. Options that act on a guess lose to options that check logs,
  metrics or the root cause first.
- Bias for Action, but not recklessness. Prefer the reversible, fast move over
  waiting for perfect information; prefer a rollback over a rushed hotfix in
  production.
- Earn Trust and Have Backbone. Silently complying with a decision you think is
  wrong is a losing option; so is going around a colleague. Say the concern
  with data, then commit.
- Invent and Simplify / Frugality. The over-engineered option that solves a
  problem nobody has is wrong.
- Deliver Results. Cutting scope with the stakeholder informed beats missing
  the date silently.

Rules:
- Name Leadership Principles by their real names, and only when they actually
  apply. Do not sprinkle them.
- If two options are close, say which one you would pick and what single detail
  separates them.
- If the screen does not show all the options, say what is missing instead of
  guessing.
- Answer in English: the assessment is in English."""


APTITUDE = """You are an expert at the aptitude tests banks and consulting firms
use (SHL, Cubiks, Talent Q, Saville, Aon/cut-e and similar): numerical, verbal,
logical/abstract reasoning and situational judgement.

The screen shows one question. Answer at once, no greeting or filler, in this
format:

ANSWER: [the letter or the exact option]
CONFIDENCE: [high / medium / low]
WHY: [2-4 lines with the key calculation or reasoning]
SHORTCUT: [the rule or trick that solves it faster next time]

If the image is hard to read or something is missing (an axis, a footnote, a
cut-off option), say so in one line and what you need to see. If you can still
give the most likely answer, give it with low confidence.

Rules by question type:

1. Numerical
- Read the question first, then pull only the data it needs from the table or
  chart. Check units, scales (thousands, millions), footnotes and years.
- Tell percentage change apart from percentage points.
- % change = (new - old) / old. Compound growth = initial x (1 + r)^n.
- Weighted averages: weight by each group's size; never average percentages
  directly.
- Currency conversion: check the direction of the rate (USD->EUR vs EUR->USD).
- If the options are far apart, estimate; if they are close, calculate exactly.

2. Verbal (True / False / Cannot Say)
- Use only the passage; ignore all outside knowledge.
- True: the passage states it or it follows necessarily. False: the passage
  contradicts it. Cannot Say: not enough information to affirm or deny it.
- Watch absolute or limiting words (all, some, only, always, never, most,
  may): a change of scope usually turns the answer into False or Cannot Say.

3. Logical / abstract
- Check patterns in this order: number of elements, shape, position/movement,
  rotation, colour/fill, alternation between steps.
- Two or three rules can hold at once; the answer must satisfy all of them.
- Eliminate options that break any rule before choosing.

4. Situational judgement (banking context)
- Priorities: integrity and regulatory compliance, owning your own mistakes,
  client focus, teamwork, and escalating in time to the right person.
- The best option takes initiative within your own authority, fixes the
  problem and communicates. The worst ignores the problem, hides mistakes,
  breaks rules, or escalates everything without trying anything.
- If it asks for most AND least effective, give both and keep them consistent.

5. Time
- If a question would take more than ~90 seconds, give the best estimate and
  say so.
- Never leave a question unanswered.

Answer in English."""


WHAT_IF = """You are an expert at LeetCode-style problems. The screen shows the
problem statement and, next to it, the code editor.

Somewhere in the editor there is a comment that starts with "what if" — it may
be written as `# what if ...`, `// what if ...` or inside a block comment, and
it may sit anywhere in the file. That comment is MINE, not part of the original
problem: it is an amendment to the statement, and it is the actual question.
Find it first and read it as an extra constraint or a changed requirement.

Treat the problem as: the original statement PLUS that amendment.

Start by deciding the one thing that matters:

- IF THE CODE ON SCREEN STILL WORKS under the amendment: say so in the first
  line, then explain in two or three sentences WHY it survives — which property
  of the approach makes the new constraint harmless. Then give the code, with
  any small adjustment it needs.
- IF IT BREAKS: say so in the first line. Then name a concrete input allowed by
  the amendment where the current code gives the wrong answer, too slow, or
  crashes, and say what it returns versus what it should return. A named input
  beats any amount of hand-waving.

Then give the solution for the amended problem:

- Say what has to change and why the old idea cannot be patched into it, when
  that is the case. If the old idea CAN be patched, patch it: do not rewrite a
  working solution to show off a different technique.
- Whenever you name a technique (prefix sums, monotonic stack, binary search on
  the answer, union-find, heap...), say what it means in half a line. Assume I
  do not know the term.
- State the complexity BEFORE and AFTER, as "was O(...) time / O(...) space,
  now O(...) / O(...)", and one sentence on what caused the change. If it did
  not change, say that.

If there are several "what if" comments, answer them in the order they appear,
each with its own heading line. If one of them contradicts another, say so
instead of picking one silently.

If you cannot find any "what if" comment on screen, do not invent one: solve the
problem as written, and say in the first line that you found no amendment.

REMEMBER EVERY EARLIER SCREENSHOT IN THIS CONVERSATION. You have seen them all,
and I am counting on that:

- Keep track of every approach you have already given me for this problem, and
  of every amendment I have already made.
- IF THIS SCREENSHOT IS THE SAME AS THE PREVIOUS ONE — same statement, same
  code, same "what if", nothing added or edited — I am not asking again by
  mistake. I am asking for ANOTHER WAY to solve it. Do not repeat the answer you
  already gave.
- Another way means a genuinely different idea: a different data structure, a
  different paradigm (iterative instead of recursive, sorting instead of
  hashing, two passes instead of one, in-place instead of a copy). Renaming
  variables, reordering lines or restyling the same algorithm is NOT another
  way, and offering one as if it were wastes my turn.
- Open with which alternative this is and what makes it different: "Second
  approach: sort first, then two pointers — trades O(n) memory for O(n log n)
  time."
- Then compare it with the ones you already gave: what it costs, what it buys,
  and which one you would actually ship. Be concrete about the tradeoff.
- When you genuinely run out of distinct approaches that fit the amendment, say
  exactly that in the first line and explain what constrains the problem to the
  ones already covered. Do not manufacture a fake variation to fill the turn.

If the screenshot DID change — a new "what if", edited code, a different
problem — ignore the rule above and treat it as a fresh amendment.

Always answer in this order (for a repeated screenshot, read "the amendment" as
"the request for another way"):

1. Does the current code survive the amendment? One line, yes or no, plus the
   new idea in the same breath. If I am asking for another way, this line names
   the new approach and how it differs from the previous one.
2. What breaks, with the concrete input — or why nothing breaks.
3. The approach for the amended problem, in plain words.
4. Complexity before and after.
5. The code, in a ``` block. Comment only the lines the amendment made
   necessary, so I can see exactly what the change bought.

Use whatever language is selected in the editor. If you cannot tell, use Python.

No micro-optimization tricks: I would rather read code I can follow than code
that is short."""


PRESETS = [
    {
        "nombre": "Resolver lo que hay en pantalla",
        "texto": "Responde la pregunta que veas en pantalla.",
    },
    {"nombre": "LeetCode / ejercicios de codigo", "texto": LEETCODE},
    {
        "nombre": "LeetCode: what if... (con memoria)",
        "texto": WHAT_IF,
    },
    {
        "nombre": "Amazon SDE: work simulation",
        "texto": AMAZON_SIM,
    },
    # Sin "model" propio: medido, Opus (el global) es el mas rapido con
    # imagenes; Haiku, pese a ser el "modelo rapido", es el mas lento aqui.
    {
        "nombre": "Data science: opcion multiple (rapido)",
        "texto": DATA_SCIENCE_MC,
    },
    {
        "nombre": "Aptitud SHL / Cubiks / Saville (banca)",
        "texto": APTITUDE,
    },
    {
        "nombre": "Depurar repo desconocido (con memoria)",
        "texto": DEPURAR,
    },
    {
        "nombre": "Explicar sin jerga",
        "texto": (
            "Explicamelo como si no supiera el vocabulario tecnico. Cada vez "
            "que uses un termino, di que significa en media linea."
        ),
    },
    {
        "nombre": "Solo el enfoque, sin codigo",
        "texto": (
            "Dame el enfoque y la complejidad, y nada mas. No me des el "
            "codigo: quiero escribirlo yo."
        ),
    },
    {
        "nombre": "Encontrar el error",
        "texto": "Que error hay en pantalla y como lo arreglo?",
    },
    {
        "nombre": "Traducir al espanol",
        "texto": "Traduce al espanol el texto que veas.",
    },
]

LANGUAGE_LABELS = {
    "auto": "Automatico — el idioma en que le escribas",
    "es": "Siempre en espanol",
    "en": "Siempre en ingles",
}

# El idioma iba fijado en el system prompt ("Hablas espanol"), asi que
# respondia en espanol aunque le escribieras en ingles.
#
# Cada regla va escrita EN su propio idioma y cierra el prompt. Describirla en
# espanol no bastaba: el resto de instrucciones es un bloque largo en espanol y
# arrastraba la respuesta a espanol pasara lo que pasara.
LANGUAGE_RULES = {
    "es": (
        "IDIOMA — manda sobre todo lo anterior:\n"
        "Responde SIEMPRE en espanol, sea cual sea el idioma de la pantalla."
    ),
    "en": (
        "LANGUAGE — this overrides everything above:\n"
        "The instructions above are written in Spanish, but that does NOT set "
        "the language of your reply. Write your entire answer in ENGLISH, "
        "whatever language the screen is in."
    ),
}

# Cuando no escribes nada no hay idioma que detectar. Se probo pedirle que
# siguiera el de la pantalla y no se sostiene: con el resto del prompt en
# espanol responde en espanol igual. Mejor un default predecible que una
# promesa que no se cumple.
IDIOMA_POR_DEFECTO = "es"


DEFAULTS: dict[str, Any] = {
    "hotkeys": ["ctrl+shift+c", "alt+3"],
    # Rota el panel entre las esquinas sin tener que hacerle clic: un atajo
    # global no le quita el foco a lo que estes haciendo, un clic si.
    "move_hotkey": "alt+4",
    # Cambia de sesion cuando hay varias abiertas: el atajo entra en el modo y
    # las flechas izquierda/derecha rotan entre ellas.
    "switch_hotkey": "alt+2",
    # Encoge el panel a solo el encabezado y lo vuelve a desplegar. Es lo mismo
    # que el boton "—", pero sin tener que buscarlo con el raton.
    "collapse_hotkey": "alt+e",
    # Sube y baja por las respuestas anteriores de la sesion con las flechas.
    # Al salir del modo el panel vuelve solo a la ultima respuesta.
    "scroll_hotkey": "alt+5",
    "model": "claude-opus-5",
    "effort": "low",
    # Lado largo maximo de la imagen enviada. Por encima de ~1568px el modelo
    # no gana detalle util y la captura cuesta bastante mas.
    "max_image_edge": 1568,
    "capture": {"mode": "active_monitor", "monitor_index": 1},
    "language": "auto",
    "concision": CONCISION,
    "system_prompt": BASE_SYSTEM_PROMPT,
    # Se avisa cuando una sesion acumula muchas capturas: cada turno reenvia
    # todas las imagenes anteriores, asi que el costo sube con la sesion.
    "warn_after_captures": 10,
    # Como recuerda "Usar pasados" las capturas anteriores:
    #   "resumen"  — solo la imagen actual + notas de texto de las anteriores
    #                (memoria.py); el costo por captura no crece.
    #   "imagenes" — reanuda la conversacion: re-envia todas las imagenes en
    #                cada turno. Lo mas fiel, y cada vez mas caro.
    "history_mode": "resumen",
    "presets": PRESETS,
    "window": {"x": None, "y": None},
    # En que monitor aparece el panel. None = donde lo dejes. Sirve para
    # capturar una pantalla y leer la respuesta en la otra.
    "panel_monitor": None,
}


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


# Huellas de valores por defecto que ya han quedado atras. Si lo guardado
# coincide con una de estas es que el usuario nunca lo edito, solo se quedo
# congelado al guardarse: se descarta para que entre el default actual.
#
# Sin esto las mejoras al prompt no llegaban nunca a quien ya tuviera un
# config.json, que es justo lo que paso con las reglas de formato.
_SUPERADOS: dict[str, set[str]] = {
    "concision": {
        # Reglas de formato anteriores a las de tipo de pregunta.
        "127584f624b3bf651a16d8fded20f53a471c5464361f95f001bc45511786d1a1",
    },
    "presets": {
        # Plantillas anteriores a las de explicacion llana.
        "14ace956913f1d8c733030ab8043e8105269e114e9da23b8f79aa055f15d9a17",
        # Anteriores a la plantilla del work simulation de Amazon.
        "c79b019b40f81e0ffd0a84c22b81f46318a9e7f9b1cadd35b7569cd763f7f93c",
        # Anteriores a la plantilla de variantes "what if".
        "5f46ace3e3ad0ad4ab5d712b50af5271191d5da44a38a988482100cd45b62f9b",
        # Anteriores a que esa plantilla recordara las vias ya propuestas.
        "670f1eab5c663586a031a48408d247dca719d72c711b13cfc86ef4e056d00d85",
        # Anteriores a que depurar diera el cambio con archivo, lineas y anclas.
        "6f2d09cb850a23c1ea5ccac4b150497d29cd3408ebec4e4b673599268bb5695e",
        # Anteriores a la plantilla de pruebas de aptitud (SHL y similares).
        "a68b364f9f01b26b1b83c15a70280a8ec9bb08592a49038a74b0f1bc00dfda3d",
    },
    "system_prompt": {
        # Version que llevaba "Hablas espanol." fijado dentro.
        "8450a57fcf977f6cb72d572f48a0f420fb76616661b4a521e03d220cffb54544",
    },
}


def _huella(value: Any) -> str:
    """Identifica un valor de config, sea texto, lista o diccionario."""
    crudo = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def normalize_hotkeys(value: Any) -> list[str]:
    """Acepta un atajo suelto o una lista, y quita duplicados."""
    if isinstance(value, str):
        value = [value]
    salida: list[str] = []
    for item in value or []:
        spec = str(item).strip().lower()
        if spec and spec not in salida:
            salida.append(spec)
    return salida


def normalize_presets(value: Any) -> list[dict[str, str]]:
    """Acepta el formato viejo (lista de cadenas) y el nuevo (nombre + texto).

    Antes una plantilla era solo su texto, que hacia de etiqueta del boton. Con
    prompts largos eso no se puede leer, asi que ahora llevan nombre aparte.
    """
    salida: list[dict[str, str]] = []
    for item in value or []:
        if isinstance(item, str) and item.strip():
            salida.append({"nombre": item.strip(), "texto": item.strip()})
        elif isinstance(item, dict) and str(item.get("texto", "")).strip():
            texto = str(item["texto"]).strip()
            entrada = {
                "nombre": str(item.get("nombre") or texto).strip(),
                "texto": texto,
            }
            # Modelo/effort propios de la plantilla, si los trae. Vacio = usa
            # los globales.
            if item.get("model"):
                entrada["model"] = str(item["model"]).strip()
            if item.get("effort"):
                entrada["effort"] = str(item["effort"]).strip()
            salida.append(entrada)
    return salida or list(PRESETS)


def _es_default_viejo(key: str, value: Any) -> bool:
    return key in _SUPERADOS and _huella(value) in _SUPERADOS[key]


def _merge(defaults: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """Une lo guardado sobre los defaults, un nivel de anidamiento adentro.

    Asi una config vieja sigue sirviendo cuando se agregan claves nuevas.
    """
    out = dict(defaults)
    for key, value in stored.items():
        if key not in defaults:
            continue  # clave obsoleta o basura: se ignora
        if _es_default_viejo(key, value):
            continue  # no lo edito el usuario: que mande el default nuevo
        if isinstance(defaults[key], dict) and isinstance(value, dict):
            out[key] = {**defaults[key], **value}
        else:
            out[key] = value

    # Antes solo habia un atajo, guardado en "hotkey".
    if "hotkey" in stored and "hotkeys" not in stored:
        out["hotkeys"] = normalize_hotkeys(stored["hotkey"])

    out["hotkeys"] = normalize_hotkeys(out.get("hotkeys")) or list(DEFAULTS["hotkeys"])
    out["presets"] = normalize_presets(out.get("presets"))
    return out


class Config:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = _merge(DEFAULTS, data or {})

    @classmethod
    def load(cls) -> "Config":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            return cls(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            # Config corrupta no debe impedir arrancar; se vuelve a defaults.
            return cls()

    def save(self) -> None:
        """Guarda solo lo que difiere de los valores por defecto.

        Congelar un default en disco lo deja clavado para siempre: cuando el
        default mejora, el archivo lo sigue pisando. Escribiendo unicamente lo
        que el usuario cambio, las mejoras llegan solas.
        """
        propio = {k: v for k, v in self.data.items() if v != DEFAULTS.get(k)}

        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(propio, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(path)  # atomico: nunca deja un json a medio escribir

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def language_rule(self, texto_usuario: str = "") -> str:
        """Regla de idioma ya resuelta, lista para meter en el prompt.

        En automatico el idioma se detecta aqui, en Python, en vez de pedirle
        al modelo que lo deduzca: la orden escrita EN el idioma destino
        funciona, y describirsela en espanol hacia que respondiera en espanol
        igualmente.
        """
        elegido = self.data.get("language", "auto")
        if elegido in LANGUAGE_RULES and elegido != "auto":
            return LANGUAGE_RULES[elegido]
        detectado = lang.detect(texto_usuario)
        return LANGUAGE_RULES[detectado or IDIOMA_POR_DEFECTO]

    def full_system_prompt(self, preprompt: str = "") -> str:
        parts = [self.data["system_prompt"], self.data["concision"]]
        # Tu pre-prompt va DESPUES de las reglas genericas: si una plantilla
        # pide otra estructura (la de LeetCode, por ejemplo), tiene que ganar
        # ella y no el default.
        if preprompt.strip():
            parts.append(preprompt.strip())
        # La regla de idioma cierra el prompt a proposito: ver LANGUAGE_RULES.
        parts.append(self.language_rule(preprompt))
        return "\n\n".join(parts)
