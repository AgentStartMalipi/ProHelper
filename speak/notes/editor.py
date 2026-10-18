"""Pestaña ✍️ Editor: cuando piden escribir codigo, pseudocodigo o un
diagrama, un guion de pizarra como los recuadros "EDITOR DE LA CANDIDATA" de
la guia del matching engine: lo que Yo dice mientras teclea (rojo, lineas
"» ...") y lo que escribe en el editor compartido (negro, monoespaciado).

Formato del LLM (y de lo guardado):

    ## Titulo del recuadro
    » what Yo says out loud while typing the next lines
    # what Yo types (notes, example, code, ASCII diagram)
"""

from __future__ import annotations

import difflib
import html
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Pedir algo para escribir sin dudas: pseudocodigo, one-liner, pizarra, dibujo...
_STRONG = re.compile(
    r"\bpseudo[- ]?code|\bone[- ]?liner|\blive[- ]coding|\bwhiteboard|\bshared editor|\bin code\b"
    r"|\bin (?:python|bash|shell|sql|java|go|rust|c\+\+)\b|\bregex|\bregular expression"
    r"|\b(?:draw|sketch|plot)\b|\bpizarra|\bpseudoc[oó]digo|\bdib[uú]ja|\bcode (?:it|this|that|up)\b"
    # "Return every connection whose...": una frase que empieza con la orden del ejercicio.
    r"|(?:^|[.?!]\s+)(?:now,?\s+|and\s+)?(?:return|print|parse|compute|extract)\b|\bwrite (?:me )?one\b", re.I)
# ...o un verbo de producir + algo que se escribe ("write a function", "implement the parser").
# "code" no es verbo aqui: "device code", "code review", "infrastructure as code" no piden escribir;
# "give me" tampoco ("give me one setting you'd check").
# Sin "walk me through" ("walk me through your reasoning") ni "implementa\w*" (atrapaba "implementation").
_VERB = re.compile(r"\b(?:write|implement|build|create|design|show me|show us|give me|give us|fix|rewrite|debug"
                   r"|escrib\w*|implementa(?:r|lo|la|las|los)?|programa(?:r|lo)?|arregla\w*|haz(?:me)?)\b", re.I)
# "code" no cuenta en "device code", "code flow", "error code", "code review", "infrastructure as code"...
_THING = re.compile(r"\b(?:(?<!device )(?<!verification )(?<!authentication )(?<!error )(?<!exit )(?<!status )"
                    r"(?<!as )(?<!one-time )(?<!QR )code(?!\s+(?:flow|phishing|review|of conduct|authentication|"
                    r"sign[- ]?in|grant|login))"
                    r"|function|script|program|algorithm|class|method|query|loop|parser|solution|small tool"
                    # "check" solo como sustantivo ("a port check"), no "a setting you'd check"
                    r"|scanner|checker|(?:port|health|simple|minimal|small|quick|header|security|a) check"
                    r"|policy|policies|manifest|yaml|rule|command|pipeline"
                    r"|diagram|graph|chart|test|funci[oó]n|c[oó]digo|gr[aá]fic\w*|diagrama|consulta)s?\b", re.I)
# Enunciado de ejercicio: "Given a conn.log, print the top ten...", tambien tras "Let's do a bit of code."
_GIVEN = re.compile(r"(?:^|[.?!]\s+)(?:\w+[,.]?\s+)?(?:given|dado|dada)\b.*\b(?:print|return|find|count|output|flag"
                    r"|detect|compute|list|report|decide|devuelve|imprime|encuentra|cuenta)\b", re.I | re.S)
# Una historia ("Tell me about a time you wrote code") no se escribe en la pizarra.
_STORY = re.compile(r"\btell me about\b|\ba time (?:you|when)\b|\bdescribe a (?:time|situation)\b"
                    r"|\bcu[eé]ntame (?:de|sobre) una vez\b", re.I)
# Repregunta sobre el codigo que ya esta en la pizarra.
_CONTINUE = re.compile(
    r"\bwhat if\b|\bwhat changes\b|\bhow would you (?:change|modify|extend|test|scale|optimi[sz]e|speed)"
    r"|\bedge cases?\b|\bcomplexity\b|\bbig[- ]?o\b|\bfaster\b|\bmemory\b|\bhuge\b|\bbigger\b|\bterabytes?\b"
    r"|\bmillions?\b|\bbillions?\b|\bfalse positives?\b|\benforce\b|\binstead\b|\bjitter\b|\bthreads?\b"
    r"|\bin parallel\b|\bat scale\b|\bthousands?\b|\band for\b|\bqu[eé] pasa si\b|\by si\b", re.I)


# "I'll write that up cleanly", "We'll cover coding in Python", "Let me show you...": no piden nada a Yo.
_SELF = re.compile(r"^\s*(?:\w+,\s*)?(?:I|I'll|I'm|I will|I'd|I've|we|we'll|we're|we will|we've|let me|"
                   r"here'?s|it'?s|this is)\b", re.I)


def needs_editor(question: str) -> bool:
    """La pregunta pide escribir algo (codigo, pseudocodigo, una grafica). Por frase, y solo
    en frases que piden algo a Yo (pregunta u orden): "I'll write that up" o "We'll cover
    coding in Python" son del entrevistador sobre si mismo (practicas del 2026-10-17)."""
    from ..turn_detector import sentences

    q = question or ""
    if _STORY.search(q):
        return False
    for sent in sentences(q) or [q]:
        if _SELF.match(sent):
            continue  # el entrevistador habla de si mismo, no pide nada
        if _STRONG.search(sent) or (_VERB.search(sent) and _THING.search(sent)) or _GIVEN.search(sent):
            return True
    return False


def continues_editor(question: str) -> bool:
    """Repregunta que cambia lo que ya esta escrito ("the file is 1.2 TB, what changes?")."""
    q = question or ""
    return not _STORY.search(q) and bool(_CONTINUE.search(q))


def is_story(question: str) -> bool:
    return bool(_STORY.search(question or ""))


# "OK, let's move on", "Different topic", "You said your incidents are operational...": se cierra el ejercicio.
_SWITCH = re.compile(r"\blet'?s (?:move on|switch|change|talk about|go back)\b|\bmoving on\b|\bdifferent topic\b"
                     r"|\banother topic\b|\bswitch(?:ing)? (?:topics?|gears)\b|\bchange of topic\b"
                     r"|\byou (?:said|mentioned) (?:your|that you|you)\b|\bcambiando de tema\b|\botro tema\b", re.I)


# "Good. Go ahead." / "Yeah. Keep going.": solo dan paso, no piden nada nuevo.
_GO_ON = re.compile(r"^(?:(?:yes|yeah|yep|ok(?:ay)?|good|great|sure|right|fine|perfect|alright|all right|mhm+|"
                    r"sounds good|that'?s fine|that works|go ahead|go on|keep going|continue|carry on|please|"
                    r"thanks?|thank you)[\s.,!]*)+$", re.I)


def is_go_ahead(text: str) -> bool:
    return bool(_GO_ON.match((text or "").strip()))


def changes_topic(question: str) -> bool:
    """El entrevistador cierra el ejercicio: la pizarra no se consulta (salvo que pida codigo nuevo)."""
    return bool(_SWITCH.search(question or ""))


NO_EDIT = "NO_EDIT"


EDITOR_SYSTEM = """You prepare the shared-editor script for Yo, a junior candidate in a live technical interview. The
interviewer asked Yo to write something: code, pseudocode, a shell one-liner, a query, or a diagram or graph.
Yo will type in a shared editor while talking, so the interviewer sees the reasoning grow on screen.

WHO SPEAKS: every » line is said by Yo, out loud, TO the interviewer, in the first person. Yo reads it live, so a
line that talks about the interviewer in the third person, or about something Yo never said, sounds wrong in the room.
Right: "» I will keep the two settings you asked for as parameters." / "» I will assume a fixed format."
Wrong: "» The two lines the interviewer asked for." / "» I will go with my proposal." (when it was never said aloud)
SCOPE: when the work asked for is done, stop. Do not add sections, features or extra tests that were not asked for;
if something more is worth it, mention it in one » line in the Cierre.

OUTPUT FORMAT (plain text, nothing else, no markdown fences, no bold):
## <box title, 1-4 words, in Spanish>
» <what Yo says out loud WHILE typing the next lines: English, one short sentence, max ~15 words>
<what Yo types: English. Notes as comments (# ...), a tiny example, code, or an ASCII diagram>
» <next spoken line>
<next typed lines>

Yo narrates EVERYTHING she types, so the interviewer always hears what is appearing on screen:
- Notes, example, plan (comment lines): one » line before EACH typed line, or each pair of short lines. No
  comment line is ever typed in silence: "# Input: ..." and "# Output: ..." each get their own » line.
  The » line says that content naturally, in spoken words, as Yo types it: "There's one instrument." before
  "# - one instrument"; "If an IP has five fails in a minute, it's suspicious." before the example line.
- QUESTIONS are only SAID, never typed: at most 2 clarifying questions, usually 1, only what really changes the
  code. Each is ONE » line with her proposal that ends with "?": "» One question: should I edit just that one line,
  or manage the whole file, I would propose the line?" Never a second line like "Does that work for you?", and no
  "# Q:" line in black: typing the question adds nothing. The ANSWER is what gets typed, later, in a Respuesta box.
- If the interviewer says "just write it" or "show me the code", do not ask: say the assumption aloud instead
  ("» I will assume the core file resource, no extra modules.") and log it as "# Assumption: ... [assumed]".
- Code: one » line before every 1-4 lines of code, saying what those lines do and why, in plain words
  ("I group the timestamps by IP, so each IP is checked on its own." before the grouping loop). Never read the
  syntax or symbols aloud ("I validate before touching state", not "if x is not None").
- A box never has a single » line followed by a long block: if a box has 6 typed lines, it has about 3-6 » lines.
- Hard limit: never more than 4 typed lines of code in a row without a » line (split loops: e.g. sort the
  times / shrink the window / check the count). Only a block of test data literals may be longer.
Example of the rhythm:
## Entender
» So we get a list of log events, each with a time, an IP and the event type.
# Input: logs = [(timestamp, ip, event)], failed SSH logins only
» And we return the IPs that look like brute force.
# Output: set of IPs with >= 5 failures in any 60 s window
» One question first: is the window sliding, so any 60 seconds, or fixed minutes, I would propose sliding?
## Código
» I start with the function, taking the logs, the threshold and the window.
def suspicious_ips(logs, threshold=5, window=60):
    times = defaultdict(list)
» First I collect the failure times for each IP.
    for ts, ip, event in logs:
        if event == "ssh_failed":
            times[ip].append(ts)
» Then for each IP I sort its times, so I can slide a window over them.
    flagged = set()
    for ip, ts_list in times.items():
        ts_list.sort()
        left = 0
» The right edge moves forward, and the left edge catches up when the window is too wide.
        for right in range(len(ts_list)):
            while ts_list[right] - ts_list[left] >= window:
                left += 1
» If the window holds five or more failures, that IP is flagged.
            if right - left + 1 >= threshold:
                flagged.add(ip)
                break
    return flagged

FIRST DECIDE THE KIND OF ASK:
(a) A concrete, fully specified "write X" (a config, a Puppet manifest or class, a policy, a query, a one-liner, a
    small function whose behaviour the interviewer already described): go STRAIGHT. One » line saying what you will
    write ("» I will write a class with the config file, validated, and the service that reloads on change."), then
    "## Código" narrated as usual, then a short "## Cierre" (how to check it works, one edge case). No Entender, no
    Input/Output lines, no Ejemplo, no Plan, no questions. Never write "Input: none".
(b) A problem with data in and data out (parse, count, detect, find...) or something genuinely unclear: the full
    flow below.
Use the simplest idiomatic solution an expert would write (for Puppet, validate_cmd on the file resource; not a
staged copy plus an exec).

BOXES for (b), in this order (merge or skip for small asks; a one-liner needs only 2-3 boxes):
1. Entender: restate inputs, output and constraints as comments; then at most 2 clarifying questions, said aloud
   only (see QUESTIONS). Ask only what changes the code.
   THE CONVERSATION IS LIVE: if the Entender box asks a question (a » line ending with "?"), STOP right after the
   Entender box. Write
   nothing else, no Ejemplo, no Plan, no Código: the interviewer answers first, and the next boxes are written after
   the answer. Only when nothing needs clarifying (or the interviewer said "just write it"), continue with all the
   boxes below in one go.
2. Ejemplo: a tiny input with the expected output, computed by hand (it becomes the first test).
3. Plan: the approach in 2-5 comment lines, the data structure and why, and the cost (Big-O, memory).
4. Código: the solution, built in small chunks (signature first, then the core loop, then the edge cases).
   Correct, minimal, readable, standard library only unless asked. Every import goes at the top of the first code
   chunk (from collections import defaultdict, import re ...), before any code that uses it.
   "Write a script" or "a tool" means Python too; Bash only when the interviewer says shell, bash or one-liner.
   The core function takes data (a string, a list of lines, a dict), not a file path or sys.argv. Reading the real
   file or the command line is a thin wrapper you only mention in a » line or a comment: never type an
   if __name__ == "__main__" block that reads sys.argv, it breaks when the code is run as typed. Write Python unless the interviewer asks for
   another language, pseudocode, or a shell one-liner. If Yo's prepared answer names an approach (a Counter, a
   set, a regex), use that same approach. For pseudocode, write clean pseudocode. For a shell one-liner, the
   pipeline plus one comment line per step (awk -F'	' for tab-separated logs).
   For a diagram or graph, draw it in ASCII (boxes and arrows, axes with labels) with short labels.
5. Prueba: in Python, the tests are 2-3 assert lines with the expected value, traced by hand first:
   "assert parse_line("2024-01-01 alice login") == ("2024-01-01", "alice", "login")", one for the example and one
   for an edge case, then print("all tests pass"). The » lines say the expected result in words. The test must
   run as typed, with nothing else: literal data in the code, never sys.argv, real files, the network or packages
   outside the standard library (unless the interviewer asked for them). If the function reads a file or a
   stream, give it a few literal lines (a list of strings, or io.StringIO) instead. Copying every typed line into
   one .py file must run and print "all tests pass".
6. Cierre: complexity, the edge cases handled, and what changes at scale or in production.

Keep it short enough for a 30-minute panel: at most ~60 typed lines in total.
Code must be correct: no invented library functions, no wrong flags, no dead or unused lines. Prefer a simple correct
version over a clever one. Write each piece right the first time: never type a wrong or odd line and fix it in a
later chunk, no tricks like "a if False else b". Test data as plain literals, not computed expressions.
CHECK BEFORE WRITING: trace the example and every test through YOUR code step by step; the expected output you write
must be exactly what the code prints. When a change adds state (a cancelled flag, a new index), update every place
that reads it (the matching loop, the best-price query, the cleanup) and show those changed lines; never leave a
comment saying "we skip it" without the code that skips it. Initialise every new attribute in the constructor.
If a change applies to both sides (bids and asks, buy and sell), show both. When an object is re-inserted (modify,
replace), create a NEW object: an old entry still sitting in a heap or queue must stay dead, never revive it.
Keep every index in sync on every path (fill, cancel, modify): a fully filled order leaves the id map too.
Every name the code uses is defined or imported; a "Cambio" box shows any new import it needs.
If a follow-up breaks an assumption of the code on screen (events in order, data fits in memory, unique ids),
say it in a » line and handle it in the code, or ask it aloud in one » line ending with "?". Never contradict
yourself.
Decision log (like the guide's "Q&A log"): questions are not typed. When an answer arrives, the Respuesta box types
ONE short line per decision: "# Format: fixed, space separated [confirmed] => plain split()". Never "[confirmed]" in
a new script or a "Cambio" box: they are written before the interviewer answers.
If there is no concrete task to write yet (an introduction, how the interview will go, a plan of topics), output
exactly NO_EDIT. Never answer with prose or explanations to the user of this prompt.
Spoken lines are said TO the interviewer: "the two lines you asked for", never "the interviewer asked for" or
any third person about them, and never "Yo".
Never claim facts about Yo's past work. Spoken lines are what a calm candidate would say, not a lecture: every »
line max ~15 words, also in "Solo decir"; say ideas, not identifiers ("the matching step", not "_match").
In spoken lines write "I would" and "I will" in full, never "I'd" or "I'll".
"""

_CONTINUE_TASK = """The editor ALREADY contains the script below (Yo typed it before, in this exercise). The interviewer
now asked a follow-up. Decide which case it is, like a strong candidate in a live coding round:
- If a question on the editor (a » line ending with "?") was asked but never answered, the first » line of your
  output closes it aloud ("For the file question, I will go with the single line.") and types one decision line
  "# File: single line [assumed] => file_line".
- A new requirement, a variant, a bug, a change at scale, or anything worth writing down (a new rule, a plan for the
  time left, recovery steps, a trade-off table): output ONLY the new boxes, in this order, so Yo can follow a
  single thread while the interviewer watches:
  1. "## Qué cambia": the plan of the change, said and logged. If the interviewer's LAST sentence is a question,
     the first » line answers it. Then one » line per change, in the order the interviewer listed them ("First,
     a regex instead of split, so the quoted request stays whole."), each followed by ONE typed note line
     "# New: <what changes> => <design impact>". Notes (# lines) go only here, never inside code.
  2. "## Cambio: <1-4 words>": the code. When the CODE changes, write the WHOLE updated function, class or manifest
     (unchanged lines included, same names): Yo sees the lines already typed in gray and only the new or changed
     ones in purple, and the clean code tab shows it as one piece. Here the » lines go BEFORE each function or
     block (1-3 lines saying what changes in it and why), never between two lines of the same function: Yo is
     editing code that is already on screen, not typing it from scratch. No test data or asserts in this box.
  3. "## Prueba": the updated asserts (see Prueba below), then print("all tests pass").
  4. "## Cierre" only if something is left worth one or two » lines.
  Do not repeat notes already typed.
- A question answered by talking (why does it hold, why this choice, what is the trade-off, would a test catch it):
  output one box "## Solo decir" with 2-5 » lines and no typed lines, pointing at what is already on screen.
- Short follow-ups ("And for domains?", "What about IPv6?", "And for ten thousand sites?") are about the exercise:
  never NO_EDIT for them. If the screen already answers it, use a "Solo decir" box that points at what is
  already there ("The second function already handles domains: ...").
- A general question that does not point at the code on screen (what is X, why use Kafka, how would you detect Y,
  how do you find servers in an hour) is NOT about the exercise, even in the same topic: NO_EDIT. "Solo decir" is
  only for why/how questions about the code or design on screen.
- The interviewer asks to write, show or continue THIS exercise ("Now write the actual class", "Continue the
  class", "Show me the code"): continue the same script from where it is, same names, same class, same function;
  never restart it, never rename what is already typed. Add only what is missing. If nothing is missing, answer
  with a "Solo decir" box that walks through where each requested part already is on screen; never NO_EDIT for it.
- The interviewer asks for a DIFFERENT problem: start a fresh script with "## Entender" for the new problem.
- Not about this exercise (a behavioral question, a question about Yo's experience or past work, or a general
  security question that does not ask to change or explain the code on screen): output exactly NO_EDIT and
  nothing else. Do not bend an unrelated question into a "Cambio" box.

<editor_so_far>
{previous}
</editor_so_far>"""


_CLARIFY_TASK = """The editor ALREADY contains the script below, and Yo already typed it. Yo asked the interviewer a
clarifying question, and the interviewer just answered it (or told Yo to decide, or said nothing and Yo goes on).
1. First a box "## Respuesta: <topic, 1-3 words, Spanish>":
» <acknowledge and state the decision, one short line: "Okay, so I will consider the format fixed, space separated.">
# <topic>: <the answer, short> [confirmed] => <design impact>   (or [assumed] when Yo decides or nobody answered)
[confirmed] only when the interviewer's own words give the value or rule; [assumed] when Yo decides.
If the interviewer answered several questions, each decision line gets its own » line right before it.
The interviewer's message may also restate the task or add requirements: include them in the next boxes.
Read the answer carefully: it may differ from Yo's proposal (e.g. "timestamp space user space action" means plain
space-separated fields, not "user=" markers). The rest of the script follows the ANSWER, not the proposal.
2. If the editor has other questions (» lines ending with "?") that were never answered, close each one aloud
before going on: » "And for the other question, I will go with the single line." then "# File: ... [assumed]".
3. Then CONTINUE THE SCRIPT FROM WHERE IT STOPPED, without repeating anything already typed:
- If the editor has no code yet, write the next boxes now (Ejemplo, Plan, Código, Prueba, Cierre), built on the answer.
  If a new question really changes the code, you may ask it aloud and stop again, but avoid it if you can.
- If the code is already there and the answer changes it, show » lines and ONLY the code lines that change.
- If the code is already there and matches the answer, one » line saying it stays as it is.
If what the interviewer said is not about the exercise, output exactly NO_EDIT.

<editor_so_far>
{previous}
</editor_so_far>"""


_CODE_TITLE = re.compile(r"^(?:c[oó]digo|code|cambio|prueba)", re.I)


def awaiting_answer(script: str) -> bool:
    """La pizarra se paro en una pregunta de aclaracion (una linea dicha que acaba en "?", o un
    "# Q:" de antes) y aun no hay codigo."""
    boxes = parse_editor(script)
    asks = any((kind == "say" and line.rstrip().rstrip("”\"").endswith("?"))
               or (kind == "type" and line.lstrip().startswith("# Q:"))
               for _, lines in boxes for kind, line in lines)
    return asks and not any(_CODE_TITLE.match(title) for title, _ in boxes)


_WORDS = re.compile(r"[A-Za-z][A-Za-z']{2,}")
_STOP = {"the", "and", "that", "this", "with", "for", "will", "would", "have", "from", "into", "then", "just", "also",
         "which", "what", "about", "should", "there", "are", "was", "but", "not", "you", "your", "our", "can", "one",
         "its", "it's", "i'll", "i'm", "let", "so", "okay", "first", "now"}


def _content(text: str) -> set[str]:
    return {w.lower() for w in _WORDS.findall(text or "")} - _STOP


def said_progress(script: str, speech: str) -> list[bool]:
    """Por cada linea roja del guion, en orden: si Yo ya la dijo (con el reconocimiento de voz, aprox.)."""
    spoken = _content(speech)
    flags = []
    for _, lines in parse_editor(script):
        for kind, line in lines:
            if kind == "say":
                words = _content(line)
                flags.append(bool(words) and len(words & spoken) / len(words) >= 0.6)
    return flags


def progress_note(script: str, speech: str) -> str:
    """Para la pizarra: que lineas rojas dijo Yo y cuales no (preguntas incluidas)."""
    flags = iter(said_progress(script, speech))
    out, last_say = [], None
    for _, lines in parse_editor(script):
        for kind, line in lines:
            if kind == "say":
                last_say = (line, next(flags))
                out.append(f"- {'SAID' if last_say[1] else 'NOT SAID'}: {line}")
                if not last_say[1] and line.rstrip().endswith("?"):
                    out.append("  (so this question was NEVER ASKED aloud)")
            elif line.lstrip().startswith("# Q:") and last_say and not last_say[1]:
                out.append(f"  (so this question was NEVER ASKED aloud: {line.strip()})")
    return "\n".join(out)


_PROGRESS = """## How far Yo got (her speech compared with the red lines; speech recognition is approximate)
{note}
Continue from the last SAID line. A question marked NEVER ASKED was not asked: never treat it as answered and
never say "nothing came back" or "since we didn't settle it". If it still matters, either ask it now in one red
line, or turn it into a short assumption in red ("I will assume the common four settings.") with [assumed].
For something Yo never said aloud, never call it "my proposal" or "as I proposed": just state the decision."""


def editor_prompt(question: str, recent: str, previous: str = "", prepared: str = "",
                  clarify: bool = False, progress: str = "", spec: str = "", code: str = "",
                  glossary: str = "") -> tuple[str, str]:
    parts = []
    if previous and (spec or code):
        # Los modelos se pierden en conversaciones de varios turnos (arXiv 2505.06120): en cada turno se
        # les da junto lo pedido hasta ahora y el codigo oficial, en vez de confiar en el historial.
        if spec:
            parts.append(f"## Everything the interviewer asked in this exercise, in order\n{spec}")
        if code:
            parts.append("## The official current code (already typed by Yo; keep these exact names; when it "
                         f"changes, give back each changed function, class or block whole)\n<code>\n{code}\n</code>")
    if glossary:
        parts.append(f"## Terms of this interview (the transcript is speech recognition: a similar-sounding word "
                     f"means the term when the context fits)\n{glossary}")
    parts.append(f"## Recent conversation\n<conversation>\n{recent}\n</conversation>")
    if previous and progress:
        parts.append(_PROGRESS.format(note=progress))
    if prepared:
        parts.append("## Yo's prepared spoken answer for this (keep the same approach)\n"
                     f"<prepared>\n{prepared}\n</prepared>")
    if previous:
        parts.append((_CLARIFY_TASK if clarify else _CONTINUE_TASK).format(previous=previous))
    said = "The interviewer just said" if clarify else "The interviewer asked"
    parts.append(f"## {said}\n<question>\n{question}\n</question>")
    return EDITOR_SYSTEM, "\n\n".join(parts)


_FENCE = re.compile(r"^\s*```")


def parse_editor(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(titulo, [("say"|"type", linea)])]. Tolera texto antes del primer
    titulo (va a un recuadro sin titulo) y vallas de markdown (se quitan)."""
    boxes: list[tuple[str, list[tuple[str, str]]]] = []
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if _FENCE.match(line):
            continue
        m = re.match(r"^\s*##\s+(.+)$", line)
        if m:
            boxes.append((m.group(1).strip(), []))
            continue
        if not boxes:
            if not line.strip():
                continue
            boxes.append(("", []))
        s = re.match(r"^\s*»\s*(.*)$", line)
        if s:
            boxes[-1][1].append(("say", s.group(1).strip().strip("“”\"")))
        else:
            boxes[-1][1].append(("type", line))
    # Sin lineas en blanco sobrantes al final de cada recuadro.
    for _, lines in boxes:
        while lines and lines[-1] == ("type", ""):
            lines.pop()
    return [b for b in boxes if b[1] or b[0]]


# Colores de la guia: cabecera pizarra, fondo claro, rojo para lo que se dice.
_HEAD_BG, _BODY_BG, _RED, _INK = "#3b4252", "#f8f9fb", "#c62828", "#111111"


_CHANGED_BG = "#fff3c4"  # amarillo suave: linea que el supervisor corrigio


_NEW = "#7b1fa2"  # morado: linea escrita que no estaba en la pizarra anterior
_SAID = "#e8a0a0"  # rojo suave: linea roja que Yo ya dijo
_DONE = "#9e9e9e"  # gris: linea que ya esta escrita en el editor (no se vuelve a teclear)


def new_typed_lines(before: str) -> set[str]:
    """Lo ya escrito en el ejercicio (lineas negras, sin espacios a los lados), para marcar lo nuevo."""
    return {_norm_ws(line) for _, lines in parse_editor(before) for kind, line in lines if kind == "type"}


def _norm_ws(line: str) -> str:
    """Sin espacios de alineacion: "ensure    => running" y "ensure => running" son la misma linea."""
    return " ".join(line.split())


def editor_html(text: str, changed: set[int] | None = None, before: str | None = None,
                said: list[bool] | None = None) -> str:
    """Los recuadros "✎ EDITOR" en HTML para un QTextBrowser. `changed`: numeros de
    linea (0 = primera de `text`) que el supervisor corrigio: fondo suave y ↻.
    `before`: lo que ya estaba escrito en el ejercicio; las lineas negras que no estaban
    salen en morado (lo que hay que anadir o cambiar)."""
    changed = changed or set()
    seen = new_typed_lines(before) if before else None
    said_iter = iter(said or [])
    marks = _line_marks(text, changed)
    out = []
    typed_here: set[str] = set()  # lo escrito en recuadros anteriores de este mismo texto
    for n, (title, lines) in enumerate(parse_editor(text)):
        # En un Cambio (o en la continuacion de un ejercicio): gris = ya escrito, no se toca;
        # morado = escribir o cambiar. En una pizarra nueva todo es negro: todo se escribe.
        ref = (seen or set()) | typed_here if seen is not None or (typed_here and title.lower().startswith("cambio")) else None
        head = "✎ EDITOR · lo que escribes mientras hablas" + (f" — {html.escape(title)}" if title else "")
        rows = []
        for m, (kind, line) in enumerate(lines):
            fixed = (n, m) in marks
            style = f" background-color:{_CHANGED_BG};" if fixed else ""
            tick = " ↻" if fixed else ""
            if kind == "say":
                done = next(said_iter, False)  # ya lo dijo: rojo suave con ✓, para ver por donde va
                color = _SAID if done else _RED
                mark = "✓ " if done else "» "
                rows.append(f'<span style="color:{color}; font-style:italic; font-family:\'Segoe UI\', sans-serif;'
                            f'{style}">{mark}“{html.escape(line)}”{tick}</span>')
            else:
                if ref is None or not line.strip():
                    ink = _INK
                else:
                    ink = _DONE if _norm_ws(line) in ref else _NEW
                rows.append(f'<span style="color:{ink};{style}">{html.escape(line) or " "}{tick}</span>')
        typed_here |= {_norm_ws(line) for kind, line in lines if kind == "type" and line.strip()}
        body = "\n".join(rows) or " "
        out.append(
            f'<table width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:10px;">'
            f'<tr><td bgcolor="{_HEAD_BG}" style="padding:4px 8px; color:#ffffff; font-weight:bold; '
            f'font-size:9pt;">{head}</td></tr>'
            f'<tr><td bgcolor="{_BODY_BG}" style="padding:6px 8px; border:1px solid {_HEAD_BG};">'
            f'<pre style="margin:0; white-space:pre-wrap; font-family:Consolas, \'Courier New\', monospace; font-size:10pt;">'
            f"{body}</pre></td></tr></table>")
    return "\n".join(out)


def _line_marks(text: str, changed: set[int]) -> set[tuple[int, int]]:
    """Linea del texto -> (recuadro, linea dentro del recuadro), como las numera parse_editor."""
    if not changed:
        return set()
    marks, box, idx = set(), -1, 0
    seen_box = False
    for i, raw in enumerate((text or "").splitlines()):
        line = raw.rstrip()
        if _FENCE.match(line):
            continue
        if re.match(r"^\s*##\s+(.+)$", line):
            box, idx, seen_box = box + 1, 0, True
            continue
        if not seen_box:
            if not line.strip():
                continue
            box, idx, seen_box = 0, 0, True
        if i in changed:
            marks.add((box, idx))
        idx += 1
    return marks


def changed_lines(old: str, new: str) -> set[int]:
    """Numeros de linea de `new` que no estaban igual en `old` (lo que el supervisor toco)."""
    a, b = (old or "").splitlines(), (new or "").splitlines()
    out: set[int] = set()
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.update(range(j1, j2))
    return out


# --- ejecutar lo que Yo escribiria (las lineas negras) ---

def typed_code(script: str) -> str:
    """Solo lo que se escribe (negro), en orden."""
    return "\n".join(line for _, lines in parse_editor(script) for kind, line in lines if kind == "type")


_PY = re.compile(r"^\s*(?:def |class |import |from \w[\w.]* import |print\()", re.M)
_SHELL = re.compile(r"^\s*(?:#!/bin/|set -e|\$ |kubectl |grep |awk |sed |find |ss |ps )", re.M)
# Nada que toque la red, lance procesos o borre/escriba fuera: eso no se ejecuta solo.
_UNSAFE = re.compile(r"\b(?:socket|requests|urllib|http\.client|subprocess|shutil|ctypes|multiprocessing|"
                     r"os\.(?:system|popen|remove|unlink|rmdir|kill|exec\w*|spawn\w*|fork)|"
                     r"pathlib\.Path\([^)]*\)\.(?:unlink|rmdir|write_\w+)|__import__|eval\(|exec\(|"
                     r"input\(|sys\.stdin)\b")


# Puppet ("class x {", "=>"), Bash y otros no son Python aunque tengan "class".
_NOT_PY = re.compile(r"^\s*class \w+(?:::\w+)* *\{|=>|^\s*\w+ \{ *'", re.M)


_CODE_BOX = re.compile(r"^(?:c[oó]digo|code|cambio)", re.I)


_HEAD_RE = re.compile(r"^(?:async\s+)?def\s+(\w+)|^class\s+([\w:]+)|^(?:define|node)\s+([\w:']+)"
                      r"|^([a-z_][\w:]*)\s*\{\s*['\"]([^'\"]+)['\"]")


def _chunks(code: str) -> list[tuple[str, list[str]]]:
    """Codigo -> bloques de primer nivel (Python o Puppet), cada uno con su clave: "def parse",
    "class sshd_hardening", "file:/etc/ssh/sshd_config", o el texto si es una sentencia suelta."""
    out: list[tuple[str, list[str]]] = []
    pending: list[str] = []  # decoradores y comentarios que van con el bloque siguiente
    for line in code.splitlines():
        top = line[:1] not in (" ", "\t", "")
        closing = line.strip()[:1] in ("}", ")", "]") and top
        if top and not closing and not line.startswith("@") and not line.lstrip().startswith("#"):
            m = _HEAD_RE.match(line)
            if m:
                name = next(g for g in m.groups()[:3] if g) if any(m.groups()[:3]) else None
                if name:
                    kind = "def" if line.lstrip().startswith(("def", "async")) else line.split()[0]
                    key = f"{kind} {name}"
                else:
                    key = f"{m.group(4)}:{m.group(5)}"
            else:
                key = "text:" + " ".join(line.split())
            out.append((key, pending + [line]))
            pending = []
        elif out and not top or closing:
            if out:
                out[-1][1].append(line)
        elif line.startswith("@") or line.lstrip().startswith("#"):
            pending.append(line)
        elif not line.strip():
            if out:
                out[-1][1].append(line)
    if pending and out:
        out[-1][1].extend(pending)
    return out


def merge_code(old: str, new: str) -> str:
    """Codigo oficial + cambio: cada bloque del cambio sustituye al de mismo nombre; los nuevos se
    anaden (los import, arriba). Como el "replace by symbol" de los editores con IA."""
    if not old.strip():
        return new
    old_c, new_c = _chunks(old), _chunks(new)
    if not new_c:
        return old
    keys = [k for k, _ in old_c]
    result = [list(c) for c in old_c]
    for key, lines in new_c:
        if key in keys:
            result[keys.index(key)][1] = lines
        elif key.startswith("text:import ") or key.startswith("text:from "):
            last_imp = max((i for i, (k, _) in enumerate(result)
                            if k.startswith(("text:import ", "text:from "))), default=-1)
            result.insert(last_imp + 1, [key, lines])
            keys.insert(last_imp + 1, key)
        else:
            result.append([key, lines])
            keys.append(key)
    out: list[str] = []
    for i, (key, lines) in enumerate(result):
        block = "\n".join(lines).rstrip()
        if i and (key.split(" ", 1)[0] in ("def", "class", "define") or
                  result[i - 1][0].split(" ", 1)[0] in ("def", "class", "define")):
            out.append("")  # una linea en blanco entre funciones y clases
        out.append(block)
    return "\n".join(out)


def code_names(code: str) -> set[str]:
    """Funciones y clases definidas (para ver si el modelo cambio un nombre)."""
    return {k for k, _ in _chunks(code) if k.split(" ", 1)[0] in ("def", "class", "define")}


def clean_code(board: str) -> str:
    """Solo el codigo del ejercicio (pestaña 🧾 Código): las lineas negras del ULTIMO recuadro de
    codigo (Código o Cambio con codigo), que trae la version entera y actual; sin notas ni frases."""
    official = ""
    for title, lines in parse_editor(board):
        if not _CODE_BOX.match(title):
            continue
        typed = [line for kind, line in lines if kind == "type"]
        if not any(line.strip() and not line.lstrip().startswith(("#", "//")) for line in typed):
            continue
        while typed and (not typed[0].strip() or typed[0].lstrip().startswith("#")):
            typed.pop(0)
        while typed and (not typed[-1].strip() or typed[-1].lstrip().startswith("#")):
            typed.pop()
        official = merge_code(official, "\n".join(typed))
    return official


_NOTE_BOX_SKIP = re.compile(r"^(?:c[oó]digo|code|cambio|prueba)", re.I)


def narration_issues(script: str) -> list[str]:
    """Lo que se puede medir sin modelo: notas escritas en silencio, codigo largo sin frase,
    preguntas escritas en negro y frases que hablan del entrevistador en tercera persona."""
    issues = []
    for title, lines in parse_editor(script):
        notes = code = 0
        is_code = bool(_NOTE_BOX_SKIP.match(title))
        for kind, line in lines:
            if kind == "say":
                notes = code = 0
                if re.search(r"\bthe interviewer\b", line, re.I):
                    issues.append(f'third person about the interviewer: "{line[:60]}"')
                continue
            s = line.strip()
            if not s:
                continue
            if s.startswith("# Q:") and "[" not in s:
                issues.append(f'a question is typed in black (it should only be said): "{s[:60]}"')
            if s.startswith("#") and not is_code:
                notes += 1
                if notes == 3:
                    issues.append(f'three note lines in a row without a » line in "{title}"')
            elif is_code and not title.lower().startswith(("prueba", "cambio")):  # un Cambio se narra por bloque
                code += 1
                if code == 7:
                    issues.append(f'more than 6 code lines in a row without a » line in "{title}"')
    return issues


def runnable_python(code: str) -> bool:
    return (bool(_PY.search(code)) and not _SHELL.search(code) and not _NOT_PY.search(code)
            and not _UNSAFE.search(code))


def run_code(code: str, timeout: float = 8.0) -> tuple[int, str]:
    """Ejecuta en una carpeta temporal, aislado (-I), con limite de tiempo."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        path = Path(d) / "board.py"
        path.write_text(code, encoding="utf-8")
        try:
            p = subprocess.run([sys.executable, "-I", str(path)], cwd=d, capture_output=True, text=True,
                               timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return p.returncode, (p.stdout + p.stderr).strip()[-3000:]
        except subprocess.TimeoutExpired:
            return -1, f"(timed out after {timeout:.0f} s)"


SUPERVISOR_SYSTEM = """You are a senior engineer quietly supervising a shared-editor script that a junior candidate (Yo)
is reading and typing live in a technical interview. Lines "» ..." are what Yo says (red); other lines are what Yo
types (black). Boxes start with "## title". A faster model wrote the NEW PART; you check it and fix it in place.

Check, against the interviewer's question, the conversation and what is already on the editor:
- the code is correct and complete (imports, names, edge cases it claims to handle, correct commands and flags);
- every expected output written in the test ("# -> ...", "# expected ...", comments after a print) is exactly what
  the code prints; the EXECUTION RESULT below is the ground truth when present;
- the spoken lines say true things about the code; nothing contradicts the interviewer's answers or earlier boxes;
- pseudocode is consistent and complete;
- spoken lines talk TO the interviewer ("you asked for"), never about "the interviewer" in third person;
- the new part continues what is already on the editor (same names, same class or function), it does not restart
  or rename it; when it changes code, it contains the WHOLE updated function, class or manifest, not a fragment;
- a concrete "write X" ask goes straight to the code: no "Input: none", no Entender or Plan boxes for it;
- NARRATION: no comment line is typed in silence (each "# ..." note has a » line right before it, at most every
  two lines), code has a » line at least every 4 lines, and every clarifying question is ONE » line ending with
  "?" and is NOT typed as a "# Q:" line (only answers are typed, as one decision line). If narration is missing, ADD the missing » lines (short, natural, true to
  the typed line). Adding » lines is allowed; do not reword existing lines that are fine.

If everything is right, reply with exactly: OK
If something is wrong or narration is missing, reply with the WHOLE NEW PART corrected, same format, making the
SMALLEST possible edits:
keep every correct line byte-identical, same boxes, same order, same narration. Fix the wrong token, not the
paragraph ("1 + 1 = 3" becomes "1 + 1 = 2", or the code changes if the code is what is wrong). Do not add boxes,
do not restyle, do not shorten, no commentary, no markdown fences. Never write "[confirmed]" for something the
interviewer did not say."""


def supervisor_prompt(question: str, recent: str, before: str, part: str, run: str | None,
                      issues: list[str] | None = None) -> tuple[str, str]:
    parts = [f"## Conversation\n<conversation>\n{recent}\n</conversation>",
             f"## The interviewer's question\n<question>\n{question}\n</question>"]
    if before:
        parts.append(f"## Already on the editor (already typed, do not repeat it)\n<before>\n{before}\n</before>")
    parts.append(f"## NEW PART to check\n<new_part>\n{part}\n</new_part>")
    if issues:
        parts.append("## Problems already measured (fix exactly these, change nothing else)\n"
                     + "\n".join(f"- {i}" for i in issues))
    if run is not None:
        parts.append("## EXECUTION RESULT of all typed lines so far (before + new part) run as one Python file\n"
                     f"<run>\n{run or '(no output)'}\n</run>")
    return SUPERVISOR_SYSTEM, "\n\n".join(parts)


_PROMISE = re.compile(r"#\s*(?:->|=>\s*prints?|expected:?|prints:?)\s*(.+)$", re.I)


def _norm_out(text: str) -> str:
    return re.sub(r"\s+", "", text).replace('"', "'").lower()


def output_mismatches(code: str, output: str) -> list[str]:
    """Salidas prometidas en la Prueba ("# -> 3") que el codigo no imprime de verdad."""
    printed = _norm_out(output)
    issues = []
    for line in code.splitlines():
        m = _PROMISE.search(line)
        if not m:
            continue
        want = m.group(1).strip().rstrip(".")
        if want and _norm_out(want) not in printed:
            issues.append(f'the test promises "{want[:60]}" but the code prints: {output.strip()[:120]!r}')
    return issues


def stop_point(script: str) -> int | None:
    """Corte duro (en vez de confiar en "STOP" del prompt): en un ejercicio nuevo, la pizarra
    termina justo despues de la pregunta en rojo del Entender. Devuelve donde cortar, o None."""
    pos = 0
    first_box = None
    for raw in script.splitlines(keepends=True):
        line = raw.strip()
        pos += len(raw)
        if line.startswith("##"):
            if first_box is not None:
                return None  # ya paso del primer recuadro sin preguntar
            first_box = line
            continue
        if line and not line.startswith(("»", "#")):
            return None  # ya hay codigo escrito: no es una pregunta antes de empezar
        if line.startswith("»") and line.rstrip("”\"").endswith("?") and raw.endswith("\n"):
            return pos
    return None


def prune_unchanged_narration(script: str, before: str) -> str:
    """En un recuadro "Cambio", las frases rojas que solo van antes de lineas ya escritas (grises) se quitan:
    el rojo queda justo donde hay que editar (grabacion 2026-10-17 21:56: "Same loop as before" entre lineas
    que no cambiaban, y no se sabia que teclear). La primera frase del recuadro se queda siempre."""
    seen = new_typed_lines(before) if before else set()
    out: list[str] = []
    lines = (script or "").splitlines()
    in_cambio, first_say = False, False
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if s.startswith("##"):
            in_cambio, first_say = s.lstrip("# ").lower().startswith("cambio"), True
            out.append(raw)
            i += 1
            continue
        if in_cambio and s.startswith("»"):
            j = i + 1
            group = []
            while j < len(lines) and not lines[j].strip().startswith(("»", "##")):
                group.append(lines[j])
                j += 1
            closed = j < len(lines)  # sigue otra frase o recuadro: el grupo esta completo
            typed = [_norm_ws(g) for g in group if g.strip()]
            if not first_say and closed and typed and all(t in seen for t in typed):
                out.extend(group)  # la frase sobra: no hay nada que cambiar debajo
                i = j
                continue
            first_say = False
        elif s and not s.startswith("»"):
            seen.add(_norm_ws(raw))  # lo de recuadros anteriores de este mismo texto cuenta como escrito
        out.append(raw)
        i += 1
    return "\n".join(out)
