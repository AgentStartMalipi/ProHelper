"""De grabacion (o archivo) a transcripcion con hablantes.

Tres entradas posibles:

1. Una grabacion de dos pistas (`me.wav` + `them.wav`): cada pista se
   transcribe por separado y se intercala por tiempo. Si la pista "Ellos"
   pasa por AssemblyAI, sus hablantes se separan (Ellos A, Ellos B...).
2. Un audio mezclado cualquiera (una grabacion de Zoom, un .mp3): con
   AssemblyAI sale diarizado; con Whisper local queda un solo hablante.
3. Una transcripcion ya hecha: VTT de Teams/Zoom, o texto "Nombre: frase",
   con o sin marcas de tiempo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..transcriber import AssemblyAISTT, Segment, SpeechToText

ME, THEM = "Yo", "Ellos"


@dataclass
class Transcript:
    segments: list[Segment]
    source: str
    has_timing: bool = True

    def speakers(self) -> list[str]:
        seen: list[str] = []
        for s in self.segments:
            if s.speaker not in seen:
                seen.append(s.speaker)
        return seen


def _fmt(t: float) -> str:
    t = int(t)
    return f"{t // 3600:d}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def render(tr: Transcript, merge_gap_s: float = 1.5) -> str:
    """Una linea por turno: frases seguidas del mismo hablante (con pausas
    menores a `merge_gap_s`) se juntan, con la marca de tiempo de la primera."""
    lines: list[list] = []  # [inicio, hablante, texto, fin]
    for s in tr.segments:
        last = lines[-1] if lines else None
        if last and last[1] == s.speaker and (not tr.has_timing or s.start - last[3] <= merge_gap_s):
            last[2] += " " + s.text
            last[3] = s.end
        else:
            lines.append([s.start, s.speaker, s.text, s.end])
    return "\n".join(
        (f"[{_fmt(start)}] " if tr.has_timing else "") + f"{speaker}: {text}"
        for start, speaker, text, _ in lines
    )


# --- eco ---------------------------------------------------------------------

_WORDS = re.compile(r"[\wáéíóúñü']+", re.IGNORECASE)


def _jaccard(a: str, b: str) -> float:
    wa, wb = set(_WORDS.findall(a.lower())), set(_WORDS.findall(b.lower()))
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def _contained(a: str, b: str) -> float:
    """Fraccion de las palabras de `a` que aparecen en `b`."""
    wa, wb = set(_WORDS.findall(a.lower())), set(_WORDS.findall(b.lower()))
    return len(wa & wb) / len(wa) if wa else 0.0


def dedupe_echo(me: list[Segment], them: list[Segment], threshold: float = 0.5) -> list[Segment]:
    """Quita de "Yo" lo que en realidad es la voz del otro colandose por el
    microfono (parlantes): se solapa en el tiempo con un segmento de "Ellos"
    y comparte la mayoria de las palabras. El eco a veces llega a trozos
    ("How long would the..." de una pregunta de 12 palabras): tambien cuenta
    si casi todas sus palabras (>= 80%, al menos 3) estan dentro de lo de Ellos."""
    kept = []
    for m in me:
        n_words = len(_WORDS.findall(m.text))
        echo = any(
            t.start - 1.0 <= m.end and m.start <= t.end + 1.0
            and (_jaccard(m.text, t.text) >= threshold
                 or (n_words >= 3 and _contained(m.text, t.text) >= 0.8))
            for t in them
        )
        if not echo:
            kept.append(m)
    return kept


# --- entradas ----------------------------------------------------------------


def transcribe_recording(folder: Path, stt: SpeechToText, progress=lambda msg: None) -> Transcript:
    folder = Path(folder)
    me_path, them_path = folder / "me.wav", folder / "them.wav"
    progress("Transcribiendo tu microfono...")
    me = [Segment(s.start, s.end, s.text, ME) for s in stt.transcribe_file(me_path)] if me_path.exists() else []
    them: list[Segment] = []
    if them_path.exists() and them_path.stat().st_size > 44:
        progress("Transcribiendo el audio de la llamada...")
        raw = stt.transcribe_file(them_path)
        labels = {s.speaker for s in raw if s.speaker}
        for s in raw:
            who = f"{THEM} {s.speaker}" if len(labels) > 1 else THEM
            them.append(Segment(s.start, s.end, s.text, who))
    me = dedupe_echo(me, them)
    segments = sorted(me + them, key=lambda s: (s.start, s.speaker))
    return Transcript(segments, source=str(folder))


def transcribe_audio_file(path: Path, stt: SpeechToText, progress=lambda msg: None) -> Transcript:
    progress("Transcribiendo el archivo...")
    raw = stt.transcribe_file(Path(path))
    diarized = isinstance(stt, AssemblyAISTT)
    segs = [Segment(s.start, s.end, s.text, f"Hablante {s.speaker}" if diarized and s.speaker else "Hablante")
            for s in raw]
    return Transcript(segs, source=str(path))


_VTT_TIME = re.compile(r"(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+")
_VTT_VOICE = re.compile(r"<v\s+([^>]+)>(.*?)(?:</v>|$)", re.DOTALL)
_STAMP = re.compile(r"^\s*[\[(]?((?:\d{1,2}:)?\d{1,2}:\d{2})(?:[.,]\d+)?[\])]?\s*[-–]?\s*")
_SPEAKER = re.compile(r"^([^:\n]{1,40}?):\s+(.+)$")


def _to_seconds(stamp: str) -> float:
    parts = [float(p) for p in stamp.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def parse_transcript_text(text: str, source: str = "texto") -> Transcript:
    """VTT (Teams/Zoom) o lineas "Nombre: frase" con "[mm:ss]" opcional.
    Las lineas sin hablante se pegan a la anterior."""
    segments: list[Segment] = []
    if text.lstrip().startswith("WEBVTT"):
        current_t = 0.0
        for block in re.split(r"\n\s*\n", text):
            m = _VTT_TIME.search(block)
            if m:
                h = int((m.group(1) or "0:")[:-1])
                current_t = h * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
            body = "\n".join(l for l in block.splitlines() if "-->" not in l and not l.strip().isdigit()
                             and l.strip() != "WEBVTT")
            v = _VTT_VOICE.search(body)
            if v:
                segments.append(Segment(current_t, current_t, " ".join(v.group(2).split()), v.group(1).strip()))
            elif body.strip():
                sm = _SPEAKER.match(" ".join(body.split()))
                who, said = (sm.group(1), sm.group(2)) if sm else ("Hablante", " ".join(body.split()))
                segments.append(Segment(current_t, current_t, said, who))
        return Transcript(_merge_same(segments), source, has_timing=True)

    has_timing = False
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        t = float(i)
        sm = _STAMP.match(line)
        if sm:
            t = _to_seconds(sm.group(1))
            has_timing = True
            line = line[sm.end():]
        m = _SPEAKER.match(line)
        if m and not m.group(1).strip().startswith("http"):
            segments.append(Segment(t, t, m.group(2).strip(), m.group(1).strip()))
        elif segments:
            segments[-1].text += " " + line
        else:
            segments.append(Segment(t, t, line, "Hablante"))
    return Transcript(segments, source, has_timing=has_timing)


def _merge_same(segs: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for s in segs:
        if out and out[-1].speaker == s.speaker:
            out[-1].text += " " + s.text
            out[-1].end = s.end
        else:
            out.append(s)
    return out


AUDIO_EXT = {".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".webm", ".flac", ".aac", ".mkv"}


def discard_recording_audio(folder: Path) -> list[str]:
    """Borra me.wav y them.wav de una carpeta de grabacion (NOTES_KEEP_AUDIO=false).
    Devuelve los nombres borrados; si uno esta bloqueado por otro programa, se queda."""
    removed = []
    for name in ("me.wav", "them.wav"):
        try:
            (Path(folder) / name).unlink()
            removed.append(name)
        except OSError:
            pass
    return removed


def load_any(path: Path, stt_factory, progress=lambda msg: None) -> Transcript:
    """Carpeta de grabacion, archivo de audio o transcripcion de texto."""
    path = Path(path)
    if path.is_dir():
        return transcribe_recording(path, stt_factory(), progress)
    if path.suffix.lower() in AUDIO_EXT:
        return transcribe_audio_file(path, stt_factory(), progress)
    # Transcripciones exportadas de Teams/Zoom o guardadas con el Bloc de
    # notas: UTF-8, UTF-16 o ANSI (ver knowledge.decode_text).
    from ..knowledge import decode_text

    return parse_transcript_text(decode_text(path.read_bytes()), str(path))
