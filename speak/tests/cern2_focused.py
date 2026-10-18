"""Bounded real-model evaluation. Defaults to a dry run; --run spends calls.

python -m speak.tests.cern2_focused --run --out cern2_review/pilot
No automatic judge or retry. Each answer is saved before starting the next.
Uses the actual Copilot pipeline, including retrieval and spoken formatting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from helper.codex_client import CodexClient
from speak.llm_client import LLMClient
from speak.notes.copilot import Copilot, split_warning
from speak.notes.pipeline import ME, THEM, Transcript
from speak.tests.copilot_eval import _SOURCE, load_library
from speak.tests.cern2_scenarios import CHAINS
from speak.transcriber import Segment

# Preparation, unsupported personal claims, large files, version handling.
FOCUSED = [0, 36, 43, 58, 70, 73]


class CodexEvalClient(LLMClient):
    def __init__(self, model: str, effort: str):
        self.client = CodexClient({'codex_model': model, 'codex_effort': effort})
        self.last_usage = {}
        self.prompt_chars = 0

    def stream(self, system, prompt, cancel=None, images=None):
        self.last_usage = {}
        if cancel is not None and cancel.is_set():
            return
        self.prompt_chars = len(system) + len(prompt)
        # New client conversation every time: Copilot supplies its own context.
        self.client._historial.clear()
        reply = self.client.send('eval', prompt, system_prompt=system, timeout=90,
                                 extra_images=[('', p) for p in images or []])
        self.last_usage = dict(self.client.last_usage)
        if cancel is None or not cancel.is_set():
            yield reply.text


def flags(text):
    return [label for label, bad in (
        ('empty', not text.strip()), ('long', len(text.split()) > 110),
        ('code_block', '```' in text), ('contraction', "I'd" in text or 'I’d' in text),
        ('inline_citation', bool(re.search(r'\[[^\]]+\]', text))),
        ('inline_code', '`' in text),
        ('meta_speech', bool(re.search(r'not documented|haven.t confirmed|in my sources', text, re.I))),
        ('wrong_warning_symbol', text.lstrip().startswith('⚨')),
    ) if bad]


def save(out, rows, metadata):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'result.json').write_text(json.dumps({'run': metadata, 'rows': rows},
                                               ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# CERN2 — respuestas reales de Codex',
             'Comprobaciones automáticas de formato; calidad pendiente de revisión humana.',
             f"Modelo: {metadata['model']}. Llamadas: {len(rows)}. Sin juez ni reintentos."]
    for r in rows:
        lines += [f"\n## {r['chain']}:{r['turn']} — {r['q']}", r['said'],
                  f"\nAviso: {r['note'] or 'ninguno'} | {r['secs']} s | Formato: {r['flags']}"]
        if r.get('error'):
            lines.append('ERROR: ' + r['error'])
    (out / 'report.md').write_text('\n\n'.join(lines), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--only', help='Chain IDs, comma separated; see dry-run output')
    ap.add_argument('--max-calls', type=int, default=10)
    ap.add_argument('--model', default='gpt-6-luna')
    ap.add_argument('--effort', default='low')
    ap.add_argument('--continuous', action='store_true', help='Keep conversation across chains')
    ap.add_argument('--out', type=Path, default=Path('cern2_review/pilot'))
    args = ap.parse_args()
    ids = [int(x) for x in args.only.split(',')] if args.only else FOCUSED
    if args.max_calls < 1 or any(i < 0 or i >= len(CHAINS) for i in ids):
        ap.error('Invalid call cap or chain ID')
    cases = [(i, j, q) for i in ids for j, q in enumerate(CHAINS[i])]
    cases = cases[:args.max_calls]
    for i, j, q in cases:
        print(f'{i}:{j} {q}', flush=True)
    print(f'Maximum {len(cases)} calls; no judge, no retries.', flush=True)
    if not args.run:
        return
    if (args.out / 'result.json').exists():
        ap.error('Output already exists. Choose another --out to preserve results.')
    kb, brief, guide, notes = load_library('cern2')
    llm = CodexEvalClient(args.model, args.effort)
    rows, segs, previous = [], [], None
    metadata = {'model': args.model, 'effort': args.effort, 'max_calls': args.max_calls,
                'continuous': args.continuous,
                'library_sha256': hashlib.sha256(notes.encode()).hexdigest()}
    save(args.out, rows, metadata)
    for i, j, q in cases:
        if i != previous and not args.continuous:
            segs = []
        previous = i
        t = float(len(segs) * 25)
        segs.append(Segment(t, t + 4, q, THEM))
        tr = Transcript(list(segs), 'eval')
        errors = []
        cop = Copilot(llm, kb, brief, snapshot=lambda: tr, now=lambda: t + 5,
                      guide=guide, mode='llamada', on_status=errors.append)
        start = time.monotonic()
        ans = cop._answer(cop.pending_question(tr), tr)
        while not ans.done and not errors and time.monotonic() - start < 100:
            time.sleep(.05)
        if not ans.done:
            cop._cancel.set()
        note, text = split_warning(ans.text)
        said = _SOURCE.sub('', text).strip()
        row = {'chain': i, 'turn': j, 'q': q, 'said': said, 'note': note,
               'raw': ans.text, 'secs': round(time.monotonic() - start, 2),
               'usage': llm.last_usage, 'prompt_chars': llm.prompt_chars,
               'flags': flags(said), 'error': '; '.join(errors)}
        if not ans.done and not errors:
            row['error'] = 'Timed out; stopped without retry'
        rows.append(row)
        save(args.out, rows, metadata)
        print(f"Saved {len(rows)}/{len(cases)}: {row['secs']}s {row['flags']}", flush=True)
        if row['error'] or not said:
            raise SystemExit('Stopped on failure: ' + row['error'])
        segs.append(Segment(t + 5, t + 24, said, ME))


if __name__ == '__main__':
    main()
