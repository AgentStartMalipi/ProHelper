"""Base de conocimiento local para el copiloto (el "RAG").

- `read_document`: PDF, Word, PowerPoint, Markdown, texto, CSV, VTT, HTML y
  archivos tecnicos (YAML, Terraform, SQL, PlantUML, Mermaid, draw.io).
  Word y PowerPoint se leen directo de su XML (son zips): sin dependencias.
  PDF usa `pypdf`. De draw.io salen componentes y conexiones ("A → B").
  Las imagenes (diagramas) no se leen aqui: necesitan a Claude, ver
  `notes/copilot.attach_file`.
- `chunk_text`: trozos de ~900 caracteres por parrafos, con solape.
- `BM25`: busqueda lexica. Sin modelos ni descargas, en milisegundos: en vivo
  cada segundo cuenta. Normaliza tildes y recorta las palabras a 5 letras,
  asi "cotizacion" encuentra "cotizaciones" y "audit" encuentra "auditoria".
- Si todo lo cargado cabe en el presupuesto de contexto, `search` lo devuelve
  entero (lo mas relevante primero): con pocos documentos no hay nada que la
  busqueda pueda perderse.
- `KnowledgeBase`: la carpeta (indexada una vez; `data/kb_cache.json`
  recuerda los archivos que no cambiaron) mas los documentos de ESTA llamada
  (adjuntos y texto pegado en Preparar llamada).

Si algun dia la busqueda lexica se queda corta (preguntas en ingles sobre
documentos en espanol), el reemplazo natural es un indice de embeddings con
la misma interfaz `search`.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import math
import re
import unicodedata
import urllib.parse
import zipfile
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
SUPPORTED = {".txt", ".md", ".markdown", ".pdf", ".docx", ".pptx", ".csv", ".vtt", ".html", ".htm",
             ".yaml", ".yml", ".tf", ".sql", ".xml", ".puml", ".plantuml", ".mmd", ".drawio",
             ".json"}


# --- lectura -----------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
        text = "".join(parts).strip()
        if text:
            paras.append(text)
    return "\n\n".join(paras)


def _pptx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        slides = []
        for i, name in enumerate(names, 1):
            root = ET.fromstring(z.read(name))
            lines = []
            for p in root.iter(f"{_A}p"):
                line = "".join(t.text or "" for t in p.iter(f"{_A}t")).strip()
                if line:
                    lines.append(line)
            if lines:
                slides.append(f"[Diapositiva {i}]\n" + "\n".join(lines))
    return "\n\n".join(slides)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("para leer PDF falta pypdf: pip install pypdf") from exc
    pages = []
    for i, page in enumerate(PdfReader(str(path)).pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"[Pagina {i}]\n{text}")
    return "\n\n".join(pages)


def _csv_text(raw: str) -> str:
    rows = list(csv.reader(io.StringIO(raw)))
    if not rows:
        return ""
    head = rows[0]
    # Cada fila como "columna: valor", para que un trozo se entienda solo.
    return "\n\n".join("; ".join(f"{h}: {v}" for h, v in zip(head, r) if v) for r in rows[1:])


def _clean_label(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(urllib.parse.unquote(value).replace("&nbsp;", " ").split())


def _drawio_text(raw: str) -> str:
    """Componentes y conexiones de un .drawio. Las versiones viejas guardan
    cada pagina comprimida (base64 + deflate + urlencode)."""
    root = ET.fromstring(raw)
    pages = []
    diagrams = root.findall(".//diagram") or [root]
    for n, diagram in enumerate(diagrams, 1):
        model = diagram.find(".//mxGraphModel")
        if model is None and (diagram.text or "").strip():
            try:
                inflated = zlib.decompress(base64.b64decode(diagram.text.strip()), -15)
                model = ET.fromstring(urllib.parse.unquote(inflated.decode("utf-8")))
            except Exception:
                continue
        if model is None:
            continue
        cells = {c.get("id"): c for c in model.iter("mxCell")}
        names = {cid: _clean_label(c.get("value", "")) for cid, c in cells.items()}
        comps, links = [], []
        for cid, c in cells.items():
            if c.get("edge") == "1":
                a, b = names.get(c.get("source"), ""), names.get(c.get("target"), "")
                if a or b:
                    label = f" ({names[cid]})" if names.get(cid) else ""
                    links.append(f"- {a or '?'} → {b or '?'}{label}")
            elif c.get("vertex") == "1" and names.get(cid):
                parent = names.get(c.get("parent"), "")
                comps.append(f"- {names[cid]}" + (f" (dentro de {parent})" if parent else ""))
        title = diagram.get("name") or f"Pagina {n}"
        pages.append(f"[Diagrama: {title}]\nComponentes:\n" + "\n".join(comps or ["- —"])
                     + "\nConexiones:\n" + "\n".join(links or ["- —"]))
    return "\n\n".join(pages)


def read_document(path: Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(path)
    if ext == ".docx":
        return _docx_text(path)
    if ext == ".pptx":
        return _pptx_text(path)
    raw = path.read_text(encoding="utf-8", errors="replace")
    if ext == ".drawio":
        return _drawio_text(raw)
    if ext == ".csv":
        return _csv_text(raw)
    if ext in {".html", ".htm"}:
        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return raw


# --- trozos ------------------------------------------------------------------


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paras:  # un parrafo gigante (PDF sin saltos) se parte por frases
        while len(p) > size:
            cut = max(p.rfind(". ", 0, size), p.rfind("\n", 0, size))
            cut = cut + 1 if cut > size // 3 else size
            pieces.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            pieces.append(p)
    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        if cur and len(cur) + len(piece) + 2 > size:
            chunks.append(cur)
            tail = cur[-overlap:]
            cur = tail[tail.find(" ") + 1:] if " " in tail else ""
        cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return chunks


# --- busqueda ----------------------------------------------------------------

_STOP = set("""
a al algo ante asi como con cual de del desde donde el ella ellos en entre era es esa ese eso esta este
esto fue ha hay la las le les lo los mas me mi muy no nos o para pero por que se si sin sobre su sus
tambien te tiene tu un una uno unos y ya yo
an and are as at be but by can could do does for from had has have how i if in into is it its me my
not of on or our so that the their them then there they this to was we were what when where which who
why will with would you your
""".split())

_TOKEN = re.compile(r"[a-z0-9]+")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    out = []
    for w in _TOKEN.findall(_fold(text)):
        if w in _STOP or (len(w) < 2 and not w.isdigit()):
            continue
        out.append(w[:5] if len(w) > 5 and not w.isdigit() else w)
    return out


@dataclass
class Chunk:
    source: str
    text: str


class BM25:
    def __init__(self, chunks: list[Chunk], k1: float = 1.4, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        self.tf = [Counter(tokenize(c.source + " " + c.text)) for c in chunks]
        self.len = [sum(tf.values()) for tf in self.tf]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 1.0
        df: Counter = Counter()
        for tf in self.tf:
            df.update(tf.keys())
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int = 6) -> list[tuple[float, Chunk]]:
        terms = set(tokenize(query))
        scored = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t in terms:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            if s > 0:
                scored.append((s, self.chunks[i]))
        scored.sort(key=lambda x: -x[0])
        return scored[:k]


class KnowledgeBase:
    def __init__(self, folder: Path | None = None, cache_file: Path | None = None) -> None:
        self.folder = Path(folder) if folder else None
        self.cache_file = cache_file
        self._folder_chunks: list[Chunk] = []
        self._extra: dict[str, list[Chunk]] = {}
        self._extra_raw: dict[str, str] = {}
        self.errors: list[str] = []
        self._index: BM25 | None = None

    # --- carga ---

    def load_folder(self, progress=lambda msg: None) -> int:
        """Indexa la carpeta. Devuelve cuantos documentos quedaron. Se puede
        buscar mientras corre (en otro hilo): el indice nuevo entra al final."""
        errors: list[str] = []
        chunks: list[Chunk] = []
        if not self.folder or not self.folder.is_dir():
            self._folder_chunks, self.errors, self._index = [], [], None
            return 0
        cache = self._read_cache()
        fresh: dict = {}
        files = sorted(p for p in self.folder.rglob("*")
                       if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith("~$")
                       and p != self.cache_file)
        for i, path in enumerate(files, 1):
            key = str(path)
            st = path.stat()
            hit = cache.get(key)
            if hit and hit["mtime"] == st.st_mtime and hit["size"] == st.st_size:
                texts = hit["chunks"]
            else:
                progress(f"Leyendo {path.name} ({i}/{len(files)})...")
                try:
                    texts = chunk_text(read_document(path))
                except Exception as exc:
                    errors.append(f"{path.name}: {exc}")
                    log.warning("no pude leer %s: %s", path, exc)
                    continue
            fresh[key] = {"mtime": st.st_mtime, "size": st.st_size, "chunks": texts}
            rel = str(path.relative_to(self.folder))
            chunks += [Chunk(rel, t) for t in texts]
        self._write_cache(fresh)
        self._folder_chunks, self.errors, self._index = chunks, errors, None
        return len(fresh)

    def _read_cache(self) -> dict:
        if not self.cache_file or not self.cache_file.exists():
            return {}
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cache(self, data: dict) -> None:
        if self.cache_file:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def add_text(self, name: str, text: str) -> int:
        """Un documento solo para esta llamada (adjunto o texto pegado)."""
        self._extra[name] = [Chunk(name, t) for t in chunk_text(text)]
        self._extra_raw[name] = text
        self._index = None
        return len(self._extra[name])

    def add_file(self, path: Path) -> int:
        return self.add_text(Path(path).name, read_document(Path(path)))

    def remove(self, name: str) -> None:
        self._extra.pop(name, None)
        self._extra_raw.pop(name, None)
        self._index = None

    def clear_extra(self) -> None:
        self._extra, self._extra_raw, self._index = {}, {}, None

    def extra_texts(self) -> dict[str, str]:
        return dict(self._extra_raw)

    # --- consulta ---

    @property
    def chunks(self) -> list[Chunk]:
        return self._folder_chunks + [c for cs in self._extra.values() for c in cs]

    def sources(self) -> list[str]:
        seen: list[str] = []
        for c in self.chunks:
            if c.source not in seen:
                seen.append(c.source)
        return seen

    def extra_names(self) -> list[str]:
        return list(self._extra)

    def search(self, query: str, k: int = 6, max_chars: int = 6000) -> list[Chunk]:
        index = self._index
        if index is None:
            index = self._index = BM25(self.chunks)
        if sum(len(c.text) for c in index.chunks) <= max_chars:
            ranked = [c for _, c in index.search(query, len(index.chunks))]
            return ranked + [c for c in index.chunks if c not in ranked]
        out, used = [], 0
        for _, chunk in index.search(query, k):
            if used + len(chunk.text) > max_chars and out:
                break
            out.append(chunk)
            used += len(chunk.text)
        return out


def format_sources(chunks: list[Chunk]) -> str:
    if not chunks:
        return "(no relevant passages found)"
    return "\n\n".join(f"<source name=\"{c.source}\">\n{c.text}\n</source>" for c in chunks)
