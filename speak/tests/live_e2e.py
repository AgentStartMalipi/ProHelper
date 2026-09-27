"""Arnes de punta a punta de Notas en vivo + copiloto, sin microfono.

Sintetiza una llamada de dos partes con las voces de Windows (SAPI), la
alimenta en tiempo real a `LiveNotes` como lo haria `DualRecorder`:

- "Ellos": float32 mono a 48 kHz en bloques de 1024 (el loopback), y SIN
  bloques mientras hay silencio, igual que WASAPI (asi se prueba el relleno
  por reloj).
- "Yo": float32 a 16 kHz en bloques de 1600 (el microfono), continuo.

Con Whisper real y un `Copilot` (LLM real o doble) mide: exactitud de la
transcripcion, atraso por frase, cuanto tarda el copiloto desde que termina
la pregunta, disparos falsos y preguntas perdidas.

    python -m speak.tests.live_e2e --model base [--real-llm] [--language en]

Lo usa `test_live_e2e.py` cuando SPEAK_E2E=1.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

THEM_VOICE = "Microsoft Zira Desktop"
ME_VOICE = "Microsoft David Desktop"
CACHE = Path(tempfile.gettempdir()) / "speak_e2e_audio"


@dataclass
class Line:
    id: str
    who: str  # "them" | "me"
    text: str
    gap_before: float = 1.0  # silencio antes de empezar esta linea
    expect: str = ""  # "answer" | "no" | "rewrite" (continua la anterior) | ""


# El guion. `expect` marca que debe hacer el copiloto al terminar la linea.
SCRIPT = [
    Line("t01", "them", "Hi, thanks for joining the call today.", 0.8, "no"),
    Line("m01", "me", "Thanks for having me, happy to help.", 1.0),
    Line("t02", "them", "We already work with another provider for energy audits.", 1.0, "no"),
    Line("t03", "them", "How long would the audit take, and what savings can we expect?", 1.2, "answer"),
    Line("m02", "me", "Great question, let me walk you through it.", 3.5),
    Line("t04", "them", "And what would the price be for", 2.0, ""),
    Line("t05", "them", "all three plants in Bogota and Medellin?", 2.6, "rewrite"),
    Line("m03", "me", "Sure, I can break that down.", 4.0),
    Line("m04", "me", "How many plants do you run today in total?", 1.0),
    Line("t06", "them", "We run five plants, three of them in Colombia.", 1.2, "no"),
    Line("m05", "me", "Understood.", 1.0),
    Line("t07", "them", "Today we process about two hundred transactions per second at peak, "
                        "and last December our database went down.", 1.5, "no"),
    Line("t08", "them", "Do you think Aurora can handle ten times that load?", 0.9, "answer"),
    Line("m06", "me", "It depends on a few things, let me ask you about your write patterns.", 0.7),
    Line("t09", "them", "Can you tell me about your experience with PCI compliance?", 1.5, "answer"),
    Line("m07", "me", "Absolutely.", 4.0),
]

KB_TEXT = ("Auditoria energetica de vapor para 3 plantas. Precio: 12.000 USD por planta, 30% anticipo. "
           "Plazo: 8 semanas desde el anticipo. Ahorro esperado 8-15% en consumo de vapor segun casos previos "
           "(Cementos X: 11%). Experiencia: 4 proyectos PCI DSS nivel 1 en fintech.")


def synthesize(lines: list[Line], cache: Path = CACHE) -> dict[str, np.ndarray]:
    cache.mkdir(parents=True, exist_ok=True)
    todo = [{"id": ln.id, "voice": THEM_VOICE if ln.who == "them" else ME_VOICE, "text": ln.text}
            for ln in lines if not (cache / f"{ln.id}.wav").exists()]
    if todo:
        spec = cache / "todo.json"
        spec.write_text(json.dumps(todo), encoding="utf-8")
        ps1 = cache / "synth.ps1"
        ps1.write_text(_PS1, encoding="utf-8")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1),
                        str(spec), str(cache)], check=True, capture_output=True, timeout=300)
    out = {}
    for ln in lines:
        with wave.open(str(cache / f"{ln.id}.wav")) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
        out[ln.id] = x
    return out


_PS1 = r"""param([string]$JsonPath, [string]$OutDir)
Add-Type -AssemblyName System.Speech
$items = Get-Content -Raw -Encoding UTF8 $JsonPath | ConvertFrom-Json
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($it in $items) {
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $s.SelectVoice($it.voice)
    $s.SetOutputToWaveFile((Join-Path $OutDir ($it.id + ".wav")), $fmt)
    $s.Speak($it.text)
    $s.Dispose()
}
"""


@dataclass
class Timeline:
    them: np.ndarray  # 16 kHz
    me: np.ndarray  # 16 kHz
    spans: dict[str, tuple[float, float]] = field(default_factory=dict)


def build_timeline(lines: list[Line], audio: dict[str, np.ndarray], sr: int = 16000,
                   them_gain: float = 0.5, me_gain: float = 0.5, noise: float = 0.0015) -> Timeline:
    t = 0.0
    spans = {}
    for ln in lines:
        t += ln.gap_before
        dur = len(audio[ln.id]) / sr
        spans[ln.id] = (t, t + dur)
        t += dur
    total = int((t + 3.0) * sr)
    them = np.zeros(total, np.float32)
    rng = np.random.default_rng(1)
    me = (rng.normal(0, noise, total)).astype(np.float32)  # el microfono siempre tiene algo de ruido
    for ln in lines:
        a, b = spans[ln.id]
        i = int(a * sr)
        x = audio[ln.id]
        if ln.who == "them":
            them[i:i + len(x)] += x * them_gain
        else:
            me[i:i + len(x)] += x * me_gain
    return Timeline(them, me, spans)


# --- metricas -------------------------------------------------------------------

_W = re.compile(r"[a-z0-9']+")


def words(text: str) -> list[str]:
    return _W.findall(text.lower().replace("-", " "))


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


@dataclass
class Result:
    model: str
    wer_them: float
    wer_me: float
    lag: list[float]
    answers: list[dict]
    expected: list[str]
    hits: list[str]
    missed: list[str]
    false: list[str]
    rewrite_ok: bool
    transcript: str
    discovery: str = ""

    def summary(self) -> str:
        lag = np.array(self.lag) if self.lag else np.array([0.0])
        first = [a["first_text_after_end"] for a in self.answers if a.get("first_text_after_end") is not None]
        trig = [a["trigger_after_end"] for a in self.answers if a.get("trigger_after_end") is not None]
        return (f"[{self.model}] WER ellos {self.wer_them:.0%} yo {self.wer_me:.0%} | atraso frase "
                f"med {np.median(lag):.1f}s max {lag.max():.1f}s | disparos {len(self.answers)} "
                f"(aciertos {len(self.hits)}/{len(self.expected)}, falsos {self.false}, perdidas {self.missed}, "
                f"reescritura {'ok' if self.rewrite_ok else 'MAL'}) | dispara tras fin de pregunta "
                f"{_fmt_list(trig)} | primer texto {_fmt_list(first)}")


def _fmt_list(xs):
    return "[" + ", ".join(f"{x:.1f}s" for x in xs) + "]" if xs else "[]"


# --- corrida -----------------------------------------------------------------------


def run(model: str = "base", language: str | None = "en", real_llm: bool = False, speed: float = 1.0,
        lines: list[Line] = SCRIPT, discovery: bool = False, quiet: bool = False, threads: int = 0) -> Result:
    from speak.knowledge import KnowledgeBase
    from speak.llm_client import FakeLLM, make_llm
    from speak.config import Config
    from speak.notes.copilot import Copilot, Discovery
    from speak.notes.live import LiveNotes
    from speak.notes.pipeline import ME, THEM
    from speak.transcriber import FasterWhisperSTT

    audio = synthesize(lines)
    tl = build_timeline(lines, audio)
    stt = FasterWhisperSTT(model, language=language or "", cpu_threads=threads)
    stt.warmup()
    stt.transcribe(np.zeros(16000, np.float32), 16000)

    t_start = [0.0]

    def clock():
        return (time.monotonic() - t_start[0]) * speed

    lags: list[float] = []
    live = LiveNotes(stt, None, mode="venta", clock=clock)
    orig_on_text = live._on_text

    def on_text(who, ev):
        lags.append(clock() - ev.end)
        orig_on_text(who, ev)
    live._on_text = on_text

    llm = make_llm(Config.load(), prewarm=True) if real_llm else FakeLLM("**Respuesta:** ok")
    kb = KnowledgeBase()
    kb.add_text("propuesta_acme.md", KB_TEXT)
    events: list[dict] = []
    first_text: dict[int, float] = {}

    def on_answer(a):
        if a.text and a.id not in first_text:
            first_text[a.id] = clock()

    cop = Copilot(llm, kb, "Cliente Acme: auditoria de vapor y plataforma de pagos.", snapshot=live.snapshot,
                  now=live.now, pending=lambda: live.pending(THEM), mode="venta", on_answer=on_answer,
                  speech=live.speech)
    orig_answer = cop._answer

    def traced(q, tr, forced=False):
        at = clock()
        prev = cop.answers[-1].id if cop.answers and cop.answers[-1].at == q.start else None
        if prev is not None:
            first_text.pop(prev, None)  # reescritura: se mide de nuevo
        ans = orig_answer(q, tr, forced)
        events.append({"id": ans.id, "at": at, "q_start": q.start, "q_end": q.end, "question": q.text,
                       "forced": forced})
        return ans
    cop._answer = traced

    disc = None
    if discovery:
        disc = Discovery(llm, kb, brief=lambda: "Cliente fintech: 10x trafico y PCI DSS.", snapshot=live.snapshot,
                         mode="arquitectura", interval_s=20, min_new_words=15)

    live.start()
    t_start[0] = time.monotonic()
    live._t0 = t_start[0]
    cop.start()
    if disc:
        disc.start()

    # Alimentacion en tiempo real (o acelerada con `speed`).
    them48 = np.repeat(tl.them, 3)
    n_them, n_me = 1024, 1600
    i_them = i_me = 0
    total_s = len(tl.me) / 16000
    while True:
        now = clock()
        if now >= total_s:
            break
        while i_me + n_me <= len(tl.me) and (i_me + n_me) / 16000 <= now:
            live.push("me", tl.me[i_me:i_me + n_me].copy(), 16000, (i_me + n_me) / 16000)
            i_me += n_me
        while i_them + n_them <= len(them48) and (i_them + n_them) / 48000 <= now:
            block = them48[i_them:i_them + n_them]
            if np.any(block):  # WASAPI no entrega nada mientras no suena nada
                live.push("them", block.copy(), 48000, (i_them + n_them) / 48000)
            i_them += n_them
        time.sleep(0.01)
    # Dejar que termine lo pendiente.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and (live.pending(ME) or live.pending(THEM)):
        time.sleep(0.1)
    time.sleep(3.0 / speed)
    if disc:
        disc.run_now()
        t0 = time.monotonic()
        while time.monotonic() - t0 < 60 and not disc.text:
            time.sleep(0.2)
        time.sleep(1)
    cop.stop()
    if disc:
        disc.stop()
    tr = live.stop(wait=True)

    ref_them = " ".join(ln.text for ln in lines if ln.who == "them")
    ref_me = " ".join(ln.text for ln in lines if ln.who == "me")
    hyp_them = " ".join(s.text for s in tr.segments if s.speaker == THEM)
    hyp_me = " ".join(s.text for s in tr.segments if s.speaker == ME)

    # Emparejar disparos con lineas del guion por tiempo.
    answers = []
    expected = [ln.id for ln in lines if ln.expect in ("answer", "rewrite")]
    hits, false = [], []
    by_id = {ln.id: ln for ln in lines}
    last_event_of = {ev["id"]: k for k, ev in enumerate(events)}
    premature = []
    for k, ev in enumerate(events):
        # La linea "de Ellos" cuyo fin esta mas cerca (antes) del final de la pregunta disparada.
        cands = [ln for ln in lines if ln.who == "them" and abs(tl.spans[ln.id][1] - ev["q_end"]) < 3.0]
        line = min(cands, key=lambda ln: abs(tl.spans[ln.id][1] - ev["q_end"])) if cands else None
        end = tl.spans[line.id][1] if line else ev["q_end"]
        final = last_event_of[ev["id"]] == k
        rec = dict(ev, line=line.id if line else None, trigger_after_end=ev["at"] - end,
                   first_text_after_end=(first_text[ev["id"]] - end) if final and ev["id"] in first_text
                   else None)
        answers.append(rec)
        if ev["forced"]:
            continue
        if line and by_id[line.id].expect in ("answer", "rewrite"):
            hits.append(line.id)
        elif not final:
            premature.append(line.id if line else ev["question"][:40])  # respondio un trozo, luego rehizo
        else:
            false.append(line.id if line else ev["question"][:40])
    false += [f"prematura:{p}" for p in premature]
    missed = [e for e in expected if e not in hits]
    # t04+t05 deben quedar en UNA respuesta (reescrita), no en dos.
    ids_rewrite = {a["id"] for a in answers if a.get("line") in ("t04", "t05")}
    rewrite_ok = len(ids_rewrite) == 1 and any(a.get("line") == "t05" for a in answers)
    from speak.notes.pipeline import render
    return Result(model, wer(ref_them, hyp_them), wer(ref_me, hyp_me), lags, answers, expected,
                  sorted(set(hits)), missed, false, rewrite_ok, render(tr), disc.text if disc else "")


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base")
    ap.add_argument("--language", default="en")
    ap.add_argument("--real-llm", action="store_true")
    ap.add_argument("--discovery", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    if args.verbose:
        import logging

        logging.basicConfig(level=logging.WARNING, format="%(relativeCreated)7.0f %(name)s: %(message)s")
        logging.getLogger("speak").setLevel(logging.INFO)
    res = run(args.model, args.language or None, args.real_llm, args.speed, discovery=args.discovery,
              threads=args.threads)
    print(res.summary())
    if args.show:
        print(res.transcript)
        for a in res.answers:
            print(json.dumps({k: (round(v, 2) if isinstance(v, float) else v) for k, v in a.items()},
                             ensure_ascii=False))
        if res.discovery:
            print(res.discovery)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
