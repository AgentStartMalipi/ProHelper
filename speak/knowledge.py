"""Base de conocimiento local para el copiloto (el "RAG").

- `read_document`: PDF, Word, PowerPoint, Excel, Markdown, texto, CSV, VTT,
  HTML y archivos tecnicos (YAML, Terraform, SQL, PlantUML, Mermaid, draw.io).
  Word, PowerPoint y Excel se leen directo de su XML (son zips): sin
  dependencias. De Word salen tablas, cuadros de texto, encabezados y pies;
  de PowerPoint, tablas y notas del orador. PDF usa `pypdf`; uno escaneado
  (sin texto) da un error claro en vez de indexarse vacio. El texto plano
  acepta UTF-8, UTF-16 del Bloc de notas y ANSI (CSV de Excel, con ";").
  De draw.io salen componentes y conexiones ("A → B").
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
import html
import io
import json
import logging
import math
import posixpath
import re
import threading
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
             ".json", ".xlsx"}


# --- lectura -----------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"

MAX_FILE_BYTES = 40_000_000  # mas que esto no es un documento de consulta: se salta con aviso


class DocumentError(RuntimeError):
    """El archivo no se puede usar; el mensaje se muestra tal cual al usuario."""


def decode_text(data: bytes) -> str:
    """Texto de Windows en cualquiera de sus formas: UTF-8 (con o sin BOM),
    UTF-16 del Bloc de notas ("Unicode") o ANSI/cp1252 (CSV de Excel)."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _w_text(node, out: list[str]) -> None:
    """Texto de un parrafo de Word sin entrar a cuadros de texto (van aparte)
    ni al Fallback VML (es una copia del mismo cuadro para Word viejo)."""
    for child in node:
        tag = child.tag
        if tag in (f"{_W}txbxContent", _MC_FALLBACK):
            continue
        if tag == f"{_W}t" and child.text:
            out.append(child.text)
        elif tag == f"{_W}tab":
            out.append("\t")
        elif tag in (f"{_W}br", f"{_W}cr"):
            out.append("\n")
        else:
            _w_text(child, out)


def _w_blocks(node, out: list[str]) -> None:
    for child in node:
        tag = child.tag
        if tag == _MC_FALLBACK:
            continue
        if tag == f"{_W}tbl":
            for tr in child.iter(f"{_W}tr"):
                cells = []
                for tc in tr.findall(f"{_W}tc"):
                    parts: list[str] = []
                    _w_blocks(tc, parts)
                    cells.append(" ".join(parts))
                if any(cells):
                    out.append(" | ".join(cells))
        elif tag == f"{_W}p":
            parts: list[str] = []
            _w_text(child, parts)
            text = "".join(parts).strip()
            if text:
                out.append(text)
            # Los cuadros de texto anclados a este parrafo, como parrafos propios.
            for box in child.iter(f"{_W}txbxContent"):
                if not _inside_fallback(child, box):
                    _w_blocks(box, out)
        else:
            _w_blocks(child, out)


def _inside_fallback(root, target) -> bool:
    parents = {c: p for p in root.iter() for c in p}
    node = target
    while node in parents:
        node = parents[node]
        if node.tag == _MC_FALLBACK:
            return True
    return False


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        body: list[str] = []
        _w_blocks(ET.fromstring(z.read("word/document.xml")), body)
        extra: list[str] = []
        for name in sorted(z.namelist()):
            if re.fullmatch(r"word/(header|footer)\d*\.xml|word/footnotes\.xml", name):
                parts: list[str] = []
                _w_blocks(ET.fromstring(z.read(name)), parts)
                extra += [p for p in parts if p not in extra and p not in body]
    if extra:
        body.append("[Encabezados, pies y notas]\n" + "\n".join(extra))
    return "\n\n".join(body)


def _a_blocks(node, out: list[str]) -> None:
    for child in node:
        if child.tag == f"{_A}tbl":
            for tr in child.iter(f"{_A}tr"):
                cells = [" ".join("".join(t.text or "" for t in p.iter(f"{_A}t")).strip()
                                  for p in tc.iter(f"{_A}p")).strip()
                         for tc in tr.findall(f"{_A}tc")]
                if any(cells):
                    out.append(" | ".join(cells))
        elif child.tag == f"{_A}p":
            line = "".join(t.text or "" for t in child.iter(f"{_A}t")).strip()
            if line:
                out.append(line)
        else:
            _a_blocks(child, out)


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    folder, name = part.rsplit("/", 1)
    rel_path = f"{folder}/_rels/{name}.rels"
    if rel_path not in z.namelist():
        return {}
    out = {}
    for rel in ET.fromstring(z.read(rel_path)).iter(_PKG_REL):
        target = rel.get("Target", "")
        out[rel.get("Id")] = target if target.startswith("/") else f"{folder}/{target}"
    return {k: posixpath.normpath(v).lstrip("/") for k, v in out.items()}


def _pptx_notes(z: zipfile.ZipFile, slide: str) -> str:
    for target in _rels(z, slide).values():
        if "notesSlide" in target and target in z.namelist():
            root = ET.fromstring(z.read(target))
            lines: list[str] = []
            for sp in root.iter(f"{_P}sp"):
                ph = sp.find(f".//{_P}ph")
                if ph is not None and ph.get("type") == "body":
                    _a_blocks(sp, lines)
            return "\n".join(lines)
    return ""


def _pptx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
        names.sort(key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)))
        slides = []
        for i, name in enumerate(names, 1):
            lines: list[str] = []
            _a_blocks(ET.fromstring(z.read(name)), lines)
            notes = _pptx_notes(z, name)
            if notes:
                lines.append(f"Notas del orador: {notes}")
            if lines:
                slides.append(f"[Diapositiva {i}]\n" + "\n".join(lines))
    return "\n\n".join(slides)


def _xlsx_text(path: Path) -> str:
    """Cada hoja como filas "encabezado: valor", igual que un CSV. Toma el
    valor calculado de las formulas (el que Excel guarda junto a la formula)."""
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_S}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{_S}t")))
        percent_styles = _xlsx_percent_styles(z)
        rels = _rels(z, "xl/workbook.xml")
        sheets = []
        for sheet in ET.fromstring(z.read("xl/workbook.xml")).iter(f"{_S}sheet"):
            target = rels.get(sheet.get(_REL), "")
            if target not in z.namelist():
                continue
            rows: list[list[str]] = []
            for row in ET.fromstring(z.read(target)).iter(f"{_S}row"):
                cells: dict[int, str] = {}
                for c in row.findall(f"{_S}c"):
                    col = _col_index(c.get("r", ""))
                    kind, v = c.get("t"), c.find(f"{_S}v")
                    if kind == "s" and v is not None:
                        value = shared[int(v.text)]
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in c.iter(f"{_S}t"))
                    elif kind in (None, "n") and v is not None and v.text:
                        value = _xlsx_number(v.text, c.get("s") in percent_styles)
                    else:
                        value = v.text if v is not None and v.text else ""
                    if value.strip():
                        cells[col] = value.strip()
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
            if rows:
                sheets.append(f"[Hoja {sheet.get('name')}]\n" + _rows_text(rows))
    return "\n\n".join(sheets)


def _xlsx_percent_styles(z: zipfile.ZipFile) -> set[str]:
    """Indices de estilo de celda con formato de porcentaje: Excel guarda
    "7%" como 0.07 y sin esto se leeria "0.07"."""
    if "xl/styles.xml" not in z.namelist():
        return set()
    root = ET.fromstring(z.read("xl/styles.xml"))
    custom = {f.get("numFmtId") for f in root.iter(f"{_S}numFmt") if "%" in (f.get("formatCode") or "")}
    xfs = root.find(f"{_S}cellXfs")
    if xfs is None:
        return set()
    return {str(i) for i, xf in enumerate(xfs.findall(f"{_S}xf"))
            if xf.get("numFmtId") in {"9", "10"} | custom}


def _xlsx_number(raw: str, percent: bool) -> str:
    try:
        x = float(raw)
    except ValueError:
        return raw
    if percent:
        return f"{x * 100:.10g}%"
    return f"{x:.12g}"


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]*", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return max(n - 1, 0)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentError("para leer PDF falta pypdf: pip install pypdf") from exc
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"[Pagina {i}]\n{text}")
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(f"no pude abrir el PDF (¿protegido o dañado?): {exc}") from exc
    if not pages:
        raise DocumentError("el PDF no tiene texto (parece escaneado o una imagen). Si es un diagrama o "
                            "una hoja escaneada, adjunta una captura como imagen y Claude la lee.")
    return "\n\n".join(pages)


def _rows_text(rows: list[list[str]]) -> str:
    head = rows[0]
    # Cada fila como "columna: valor", para que un trozo se entienda solo.
    if len(rows) == 1:
        return " | ".join(head)
    return "\n\n".join("; ".join(f"{h}: {v}" if h else v for h, v in zip(head, r) if v)
                       for r in rows[1:])


def _csv_text(raw: str) -> str:
    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        # Excel en español separa con ";": se elige el que mas aparece.
        delim = max(",;\t|", key=sample.count)
        dialect = type("D", (csv.excel,), {"delimiter": delim})
    rows = [r for r in csv.reader(io.StringIO(raw), dialect) if any(x.strip() for x in r)]
    return _rows_text(rows) if rows else ""


def _clean_label(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    return " ".join(urllib.parse.unquote(value).replace("&nbsp;", " ").split())


def _drawio_text(raw: str) -> str:
    """Componentes y conexiones de un .drawio. Las versiones viejas guardan
    cada pagina comprimida (base64 + deflate + urlencode). Las etiquetas de
    una flecha pueden ser celdas hijas de la flecha: se pegan a la conexion."""
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
        edges = {cid for cid, c in cells.items() if c.get("edge") == "1"}
        edge_labels: dict[str, list[str]] = {}
        for cid, c in cells.items():
            if c.get("parent") in edges and names.get(cid):
                edge_labels.setdefault(c.get("parent"), []).append(names[cid])
        comps, links = [], []
        for cid, c in cells.items():
            if cid in edges:
                a, b = names.get(c.get("source"), ""), names.get(c.get("target"), "")
                labels = [x for x in [names.get(cid)] + edge_labels.get(cid, []) if x]
                if a or b or labels:
                    label = f" ({', '.join(labels)})" if labels else ""
                    links.append(f"- {a or '?'} → {b or '?'}{label}")
            elif c.get("vertex") == "1" and names.get(cid) and c.get("parent") not in edges:
                parent = names.get(c.get("parent"), "")
                comps.append(f"- {names[cid]}" + (f" (dentro de {parent})" if parent else ""))
        title = diagram.get("name") or f"Pagina {n}"
        pages.append(f"[Diagrama: {title}]\nComponentes:\n" + "\n".join(comps or ["- —"])
                     + "\nConexiones:\n" + "\n".join(links or ["- —"]))
    return "\n\n".join(pages)


def read_document(path: Path) -> str:
    """Texto de un documento. Lanza `DocumentError` con un mensaje para el
    usuario si no se puede usar (formato desconocido, escaneado, vacio...)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise DocumentError(f"formato {ext or 'sin extension'} no soportado")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise DocumentError(f"muy grande ({size // 1_000_000} MB): parte el documento o quita imagenes")
    try:
        if ext == ".pdf":
            text = _pdf_text(path)
        elif ext == ".docx":
            text = _docx_text(path)
        elif ext == ".pptx":
            text = _pptx_text(path)
        elif ext == ".xlsx":
            text = _xlsx_text(path)
        else:
            raw = decode_text(path.read_bytes())
            if ext == ".drawio":
                text = _drawio_text(raw)
            elif ext == ".csv":
                text = _csv_text(raw)
            elif ext in {".html", ".htm"}:
                raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
                text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
            else:
                text = raw
    except DocumentError:
        raise
    except zipfile.BadZipFile as exc:
        raise DocumentError("no es un archivo de Office valido (¿esta dañado o protegido con clave?)") from exc
    except ET.ParseError as exc:
        raise DocumentError(f"XML invalido: {exc}") from exc
    except PermissionError as exc:
        raise DocumentError("esta bloqueado por otro programa: cierralo y vuelve a intentar") from exc
    if not text.strip():
        raise DocumentError("no tiene texto")
    return text


# --- trozos ------------------------------------------------------------------


_HEADING = re.compile(r"^#{1,6} \S.*$", re.M)


def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Trozos de ~`size` caracteres. Con encabezados markdown, se trocea por
    seccion y cada trozo empieza con el encabezado de la suya. Medido
    2026-10-12 (respuestas preparadas de CERN): 1 de 22 trozos lo llevaba, y
    el LLM movio una historia de AWS "at Amadeus" porque el trozo no decia de
    que seccion era."""
    heads = list(_HEADING.finditer(text))
    if not heads:
        return _chunk_plain(text, size, overlap)
    chunks = _chunk_plain(text[:heads[0].start()], size, overlap)
    for i, head in enumerate(heads):
        title = head.group(0).strip()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        for body in _chunk_plain(text[head.end():end], max(200, size - len(title) - 1), overlap):
            chunks.append(f"{title}\n{body}")
    return chunks


def _chunk_plain(text: str, size: int, overlap: int) -> list[str]:
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
        # Solo se recortan palabras: un codigo con digitos ("iso50001",
        # "sv200") recortado se confundiria con sus vecinos.
        out.append(w[:5] if len(w) > 5 and w.isalpha() else w)
    return out


# Pares ingles/espanol del vocabulario de una llamada comercial o tecnica. La
# busqueda es por palabras: sin esto "How much does the audit cost?" no
# encuentra "auditoria ... 12.000 USD" si solo comparten "audit". Medido con
# speak/tests/retrieval_eval.py (hit@3), en preguntas cruzadas escritas
# despues de armar la lista: 11/14 con ella, 5/14 sin ella; en el mismo idioma
# no cambia (12/12). Las parafrasis ("upfront payment" por "anticipo") siguen
# fallando: para eso haria falta busqueda por significado (embeddings).
_BILINGUAL = """
price prices pricing precio precios tarifa | cost costs cuesta cuestan costo costos valor
quote quotation cotizacion cotizar | discount descuento descuentos | payment pay pago pagos pagar
deposit advance anticipo | invoice factura | budget presupuesto
savings save saving ahorro ahorros ahorrar | payback roi return retorno recuperacion
investment inversion | guarantee guaranteed warranty garantia garantizada | refund devolucion devuelve devolver
timeline schedule deadline plazo plazos cronograma | delivery deliver entrega entregar entregan
week weeks semana semanas | month months mes meses | day days dia dias | hour hours hora horas | year years ano anos
team equipo | engineer engineers ingeniero ingenieros | technician technicians tecnico tecnicos
analyst analista | training train capacitacion entrenamiento | installation install installing instalacion instalar
support soporte | maintenance mantenimiento | contract contrato | proposal propuesta | scope alcance
deliverables entregables | report reports informe reporte | plant plants planta plantas | steam vapor
energy energia | consumption consumo | electricity electricidad | water agua | accuracy precision exactitud
range rango | battery bateria | certification certified certificate certificacion certificado
security seguridad | encryption encrypted encrypt cifrado cifran cifra encriptacion encriptados
data datos | retention retain stored store keep kept guardan guardar conservan almacenan retencion
availability uptime disponibilidad | backup respaldo | recovery recuperacion
integration integrate integrates integrar integra integracion | login sign-on sso sesion
authentication autenticacion | user users usuario usuarios | customer customers client clients cliente clientes
case caso | success exito | dashboard tablero | alarm alarms alert alerts alarma alarmas alerta alertas
cloud nube | server servidor | network red | latency latencia | scalability scale escalabilidad escalar
requirement requirements requisito requisitos | risk risks riesgo riesgos
compliance regulation regulatory cumplimiento regulacion normativa | license licencia | pilot trial piloto prueba
competitor competitors competencia | remote remotely remoto remota | operators operator operadores operador
failure failures falla fallas | outage caida | leak leaks fuga fugas | loss losses perdida perdidas
"""


def _bilingual_map() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for group in re.split(r"[|\n]", _BILINGUAL):
        stems = {w[:5] if len(w) > 5 else w for w in _TOKEN.findall(_fold(group))}
        for s in stems:
            out.setdefault(s, set()).update(stems - {s})
    return out


_SYNONYMS = _bilingual_map()


def expand_query(terms: set[str], weight: float = 0.6) -> dict[str, float]:
    """Terminos de la pregunta (peso 1) mas sus traducciones (peso menor)."""
    out = {t: 1.0 for t in terms}
    for t in terms:
        for s in _SYNONYMS.get(t, ()):
            out.setdefault(s, weight)
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
        terms = expand_query(set(tokenize(query)))
        scored = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t, weight in terms.items():
                f = tf.get(t)
                if f:
                    s += weight * self.idf[t] * f * (self.k1 + 1) / (
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
        # Dos indices: el de la carpeta se arma en `load_folder` (en segundo
        # plano: con 9.000 trozos tarda ~4 s, que no pueden caer en la primera
        # respuesta de la llamada) y el de los adjuntos, chico, se rearma al
        # vuelo. Se busca desde el hilo del copiloto mientras la UI adjunta:
        # cada cambio sube la version, y un indice armado con una version vieja
        # no se guarda (si no, un adjunto podia quedar fuera hasta el proximo).
        self._folder_index: BM25 = BM25([])
        self._extra_index: BM25 | None = None
        self._lock = threading.Lock()
        self._version = 0

    def _changed(self) -> None:
        with self._lock:
            self._version += 1
            self._extra_index = None

    # --- carga ---

    def load_folder(self, progress=lambda msg: None) -> int:
        """Indexa la carpeta. Devuelve cuantos documentos quedaron. Se puede
        buscar mientras corre (en otro hilo): el indice nuevo entra al final."""
        errors: list[str] = []
        chunks: list[Chunk] = []
        if not self.folder or not self.folder.is_dir():
            self._folder_chunks, self.errors, self._folder_index = [], [], BM25([])
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
                except Exception as exc:  # DocumentError trae un mensaje para el usuario
                    errors.append(f"{path.name}: {exc}")
                    log.warning("no pude leer %s: %s", path, exc)
                    continue
            fresh[key] = {"mtime": st.st_mtime, "size": st.st_size, "chunks": texts}
            rel = str(path.relative_to(self.folder))
            chunks += [Chunk(rel, t) for t in texts]
        self._write_cache(fresh)
        progress("Armando el indice...")
        index = BM25(chunks)
        self._folder_chunks, self.errors, self._folder_index = chunks, errors, index
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
        chunks = [Chunk(name, t) for t in chunk_text(text)]
        if not chunks:
            raise DocumentError(f"{name}: no tiene texto")
        self._extra = {**self._extra, name: chunks}
        self._extra_raw = {**self._extra_raw, name: text}
        self._changed()
        return len(chunks)

    def add_file(self, path: Path) -> int:
        return self.add_text(Path(path).name, read_document(Path(path)))

    def remove(self, name: str) -> None:
        self._extra = {k: v for k, v in self._extra.items() if k != name}
        self._extra_raw = {k: v for k, v in self._extra_raw.items() if k != name}
        self._changed()

    def clear_extra(self) -> None:
        self._extra, self._extra_raw = {}, {}
        self._changed()

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

    def _extra_idx(self) -> BM25:
        index = self._extra_index
        if index is None:
            version = self._version
            index = BM25([c for cs in self._extra.values() for c in cs])
            with self._lock:
                if version == self._version:
                    self._extra_index = index
        return index

    def search(self, query: str, k: int = 6, max_chars: int = 6000) -> list[Chunk]:
        folder, extra = self._folder_index, self._extra_idx()
        everything = folder.chunks + extra.chunks
        if sum(len(c.text) for c in everything) <= max_chars:
            # Cabe todo: va entero, lo mas relevante primero.
            ranked = [c for _, c in sorted(folder.search(query, len(folder.chunks))
                                           + extra.search(query, len(extra.chunks)), key=lambda x: -x[0])]
            seen = {id(c) for c in ranked}
            return ranked + [c for c in everything if id(c) not in seen]
        hits = sorted(folder.search(query, k) + extra.search(query, k), key=lambda x: -x[0])
        out, used = [], 0
        for _, chunk in hits[:k]:
            if used + len(chunk.text) > max_chars and out:
                break
            out.append(chunk)
            used += len(chunk.text)
        return out


def format_sources(chunks: list[Chunk]) -> str:
    if not chunks:
        return "(no relevant passages found)"
    return "\n\n".join(f"<source name=\"{c.source}\">\n{c.text}\n</source>" for c in chunks)
