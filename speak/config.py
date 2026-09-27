"""Configuracion de SPEAK.

Se lee de `speak/.env` (ver `.env.example`) y luego de las variables de
entorno, que ganan. Ninguna API key vive en el codigo: si un proveedor la
necesita y no esta, falla con un mensaje claro al usarlo, no al importar.

Sin python-dotenv a proposito: el formato que usamos (CLAVE=valor, `#` para
comentarios) cabe en veinte lineas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
DATA_DIR = ROOT / "data"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass
class Config:
    # --- LLM -------------------------------------------------------------
    # claude_cli: reutiliza el login de Claude Code (sin API key), igual que
    # SCREEN. anthropic: SDK oficial con API_KEY. Ver llm_client.py.
    LLM_PROVIDER: str = "claude_cli"
    # Id completo: los alias cortos ("haiku") han colgado el CLI antes.
    LLM_MODEL: str = "claude-sonnet-5"
    LLM_EFFORT: str = "low"
    API_KEY: str = ""

    # --- Speech-to-text --------------------------------------------------
    STT_PROVIDER: str = "faster_whisper"  # faster_whisper | assemblyai
    # small: buen punto en CPU (sin GPU NVIDIA). base = mas rapido,
    # medium/large-v3 = mas preciso y mucho mas lento en CPU.
    STT_MODEL: str = "small"
    STT_LANGUAGE: str = "en"  # "" = autodetectar
    STT_DEVICE: str = "cpu"
    STT_COMPUTE_TYPE: str = "int8"
    # Notas en vivo: dos pistas a la vez en CPU. `small` no da abasto en una
    # laptop; `base` es ~2-3x mas rapido. La transcripcion final (al detener)
    # sigue con STT_MODEL.
    STT_LIVE_MODEL: str = "base"
    STT_THREADS: int = 0  # 0 = todos los nucleos
    ASSEMBLYAI_API_KEY: str = ""

    # --- Audio / turnos --------------------------------------------------
    MIC_DEVICE: str = ""  # "" = el predeterminado de Windows; si no, el indice
    SAMPLE_RATE: int = 16000
    CHUNK_MS: int = 30
    # Silencio (ms) para cerrar una pregunta completa (p. ej. tu aclaracion
    # "can I assume the array is sorted?").
    SILENCE_THRESHOLD: int = 900
    # Silencio (ms) para dar por terminada una RESPUESTA tuya. Alto a
    # proposito: al responder se hacen pausas para pensar. Tambien esta el
    # boton "Termine".
    ANSWER_SILENCE: int = 2500
    # Tope duro: pase lo que pase, con este silencio el turno se cierra.
    MAX_SILENCE: int = 6000
    # Energia minima (RMS 0..1) para considerar que hay voz. 0 = automatico.
    VAD_THRESHOLD: float = 0.0

    # --- Contexto --------------------------------------------------------
    # Intercambios recientes que viajan completos; los anteriores, resumidos.
    CONTEXT_WINDOW: int = 3
    CV_MAX_CHARS: int = 3000
    JD_MAX_CHARS: int = 2000

    # --- Voz del entrevistador (TTS de Windows) --------------------------
    TTS_ENABLED: bool = True
    TTS_RATE: int = 0  # -10..10

    # --- Notas de llamada ------------------------------------------------
    NOTES_LANGUAGE: str = "Spanish"  # idioma en que se escriben las notas
    # Idioma que HABLAN en la llamada (Whisper). "" = lo detecta en las
    # primeras frases de cada hablante y lo fija (medido: detectar en cada
    # frase es 2x mas lento y en frases cortas se equivoca; fijar "en" con una
    # llamada en espanol la TRADUCE al ingles, 109% de error). Aparte de
    # STT_LANGUAGE, que es el del simulador de entrevistas.
    NOTES_STT_LANGUAGE: str = ""
    # En vivo: cada cuantos segundos (si hubo habla nueva) Claude reescribe el
    # borrador de notas. 0 = en vivo solo transcripcion y preguntas, sin LLM.
    LIVE_NOTES_INTERVAL: int = 60

    # --- Copiloto ----------------------------------------------------------
    # Responde en vivo las preguntas del otro lado (venta, reunion, soporte,
    # llamada; nunca en entrevista) con tu brief y tus documentos.
    COPILOT_ENABLED: bool = True
    # Carpeta de conocimiento (PDF, Word, PowerPoint, Markdown, texto, CSV).
    # "" = speak/data/knowledge (no se sube a git: suele ser de clientes).
    KB_DIR: str = ""
    # Silencio (s) del otro para dar su pregunta por terminada.
    COPILOT_QUIET_S: float = 1.2
    # Exploracion ("¿que me falta?") en vivo: cada cuantos segundos se
    # reescribe si hubo conversacion nueva. 0 = solo con el boton (F9).
    DISCOVERY_INTERVAL: int = 90

    @property
    def kb_dir(self) -> Path:
        return Path(self.KB_DIR) if self.KB_DIR.strip() else DATA_DIR / "knowledge"

    extra: dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def mic_device(self) -> int | None:
        return int(self.MIC_DEVICE) if self.MIC_DEVICE.strip().isdigit() else None

    @classmethod
    def load(cls, env_file: Path = ENV_FILE) -> "Config":
        merged = _read_env_file(env_file)
        cfg = cls()
        for f in fields(cls):
            if f.name == "extra":
                continue
            raw = os.environ.get(f.name, merged.get(f.name))
            if raw is None:
                continue
            setattr(cfg, f.name, _coerce(raw, type(getattr(cfg, f.name))))
        return cfg

    def save(self, env_file: Path = ENV_FILE) -> None:
        """Guarda los ajustes editables desde la UI (nunca las API keys:
        esas se escriben a mano en .env y aqui se preservan tal cual)."""
        existing = _read_env_file(env_file)
        for f in fields(self):
            if f.name == "extra" or f.name.endswith("API_KEY"):
                continue
            value = getattr(self, f.name)
            existing[f.name] = str(value).lower() if isinstance(value, bool) else str(value)
        lines = [f"{k}={v}" for k, v in existing.items()]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _coerce(raw: str, kind: type):
    if kind is bool:
        return raw.strip().lower() in {"1", "true", "yes", "si", "on"}
    if kind is int:
        return int(float(raw))
    if kind is float:
        return float(raw)
    return raw
