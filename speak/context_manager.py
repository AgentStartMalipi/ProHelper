"""Contexto compacto para el LLM.

Nunca se manda la conversacion entera. Cada llamada recibe:

- el perfil (tipo de entrevista, puesto, candidato; CV y descripcion del
  puesto recortados),
- los ultimos `window` intercambios completos,
- los anteriores en una linea cada uno (pregunta + nota),
- los temas tecnicos que ya salieron, para no repetir y para que las
  repreguntas se apoyen en ellos.

Asi el prompt crece poco aunque la sesion dure una hora.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_TECH_TERMS = re.compile(
    r"\b(?:hash ?maps?|arrays?|linked lists?|binary (?:search|trees?)|bst|graphs?|heaps?|"
    r"stacks?|queues?|tries?|dynamic programming|recursion|two pointers|sliding window|"
    r"bfs|dfs|dijkstra|sorting|big-?o|caching|caches?|redis|kafka|sql|nosql|postgres|"
    r"mysql|dynamodb|mongodb|sharding|replication|load balanc\w+|microservices?|"
    r"rest|grpc|graphql|kubernetes|docker|aws|lambda|s3|ec2|rate limit\w*|"
    r"consistency|cap theorem|indexes|indexing|transactions?|concurrency|threads?|"
    r"deadlocks?|mutex|oauth|jwt|ci/cd|terraform|spark|airflow|pandas|machine learning|"
    r"regression|classification|overfitting|a/b test\w*|python|java|typescript|react)\b",
    re.IGNORECASE,
)


@dataclass
class Profile:
    interview_type: str = "Mixta"  # Behavioral | Coding | System design | Mixta
    role: str = ""
    company: str = ""
    seniority: str = ""
    candidate_info: str = ""
    job_description: str = ""
    cv: str = ""
    language: str = "en"


@dataclass
class Exchange:
    question: str
    qtype: str
    answer: str = ""
    clarifications: list[tuple[str, str]] = field(default_factory=list)
    feedback: str = ""  # la evaluacion completa (markdown)
    model_answer: str = ""  # QUICK + DETAILED, para que un FOLLOW_UP lo modifique
    score: str = ""
    at: float = field(default_factory=time.time)

    def one_liner(self) -> str:
        q = self.question if len(self.question) <= 110 else self.question[:107] + "..."
        return f"[{self.qtype}] {q}" + (f" → nota {self.score}" if self.score else "")


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " [...]"


class ContextManager:
    def __init__(self, window: int = 3, cv_max: int = 3000, jd_max: int = 2000) -> None:
        self.window = window
        self.cv_max = cv_max
        self.jd_max = jd_max
        self.profile = Profile()
        self.history: list[Exchange] = []
        self.topics: dict[str, int] = {}

    # -- mutacion --

    def start_exchange(self, question: str, qtype: str) -> Exchange:
        ex = Exchange(question=question, qtype=qtype)
        self.history.append(ex)
        self._add_topics(question)
        return ex

    @property
    def current(self) -> Exchange | None:
        return self.history[-1] if self.history else None

    def record_answer(self, text: str) -> None:
        if self.current:
            self.current.answer = (self.current.answer + " " + text).strip()
            self._add_topics(text)

    def record_clarification(self, asked: str, reply: str) -> None:
        if self.current:
            self.current.clarifications.append((asked, reply))

    def record_feedback(self, feedback: str, model_answer: str, score: str) -> None:
        if self.current:
            self.current.feedback = feedback
            self.current.model_answer = model_answer
            self.current.score = score

    def clear(self) -> None:
        """Borra la conversacion; el perfil (CV, puesto) se conserva."""
        self.history.clear()
        self.topics.clear()

    def _add_topics(self, text: str) -> None:
        for m in _TECH_TERMS.findall(text):
            key = m.lower()
            self.topics[key] = self.topics.get(key, 0) + 1

    # -- lectura --

    def asked_questions(self) -> list[str]:
        return [ex.question for ex in self.history]

    def profile_block(self) -> str:
        p = self.profile
        lines = [f"Interview type: {p.interview_type}"]
        if p.role or p.company:
            lines.append(f"Role: {p.role or '?'}" + (f" at {p.company}" if p.company else ""))
        if p.seniority:
            lines.append(f"Seniority: {p.seniority}")
        if p.candidate_info:
            lines.append(f"Candidate notes: {_clip(p.candidate_info, 600)}")
        if p.job_description:
            lines.append(f"Job description (excerpt):\n{_clip(p.job_description, self.jd_max)}")
        if p.cv:
            lines.append(f"Candidate CV (excerpt):\n{_clip(p.cv, self.cv_max)}")
        return "\n".join(lines)

    def build(self, include_current: bool = True) -> str:
        """El bloque de contexto que acompana cada llamada al LLM."""
        parts = ["## Candidate profile", self.profile_block()]
        past = self.history if include_current else self.history[:-1]
        older, recent = past[:-self.window] if self.window else past, past[-self.window:] if self.window else []
        if older:
            parts.append("## Earlier in this session (summary)")
            parts += [f"- {ex.one_liner()}" for ex in older]
        if recent:
            parts.append("## Recent exchanges")
            for ex in recent:
                parts.append(f"Q [{ex.qtype}]: {ex.question}")
                for asked, reply in ex.clarifications:
                    parts.append(f"  Candidate asked: {asked}\n  Interviewer: {reply}")
                if ex.answer:
                    parts.append(f"A (candidate, transcribed): {_clip(ex.answer, 1500)}")
                if ex.score:
                    parts.append(f"Score: {ex.score}")
        if self.topics:
            top = sorted(self.topics, key=self.topics.get, reverse=True)[:15]
            parts.append("## Topics already covered: " + ", ".join(top))
        return "\n".join(parts)

    # -- persistencia --

    def to_json(self) -> str:
        return json.dumps({
            "profile": asdict(self.profile),
            "history": [asdict(ex) for ex in self.history],
            "topics": self.topics,
        }, ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    def load_profile(self, path: Path) -> None:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.profile = Profile(**{k: v for k, v in data.get("profile", data).items()
                                      if k in Profile.__dataclass_fields__})

    def save_profile(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"profile": asdict(self.profile)}, ensure_ascii=False,
                                   indent=2), encoding="utf-8")
