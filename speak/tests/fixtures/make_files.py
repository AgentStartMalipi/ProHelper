"""Genera los fixtures que no son de Office (se corre una vez; quedan versionados).

    .venv-speak\\Scripts\\python.exe speak\\tests\\fixtures\\make_files.py

PDF con Qt (plataforma normal, no offscreen: sin fuentes el texto sale en cuadros).
"""

from __future__ import annotations

import base64
import urllib.parse
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pdfs() -> None:
    from PySide6.QtCore import QMarginsF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPageSize, QPainter, QPdfWriter
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841 - Qt necesita la app para fuentes

    w = QPdfWriter(str(HERE / "ficha_tecnica.pdf"))
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageMargins(QMarginsF(15, 15, 15, 15))
    p = QPainter(w)
    p.setFont(QFont("Arial", 11))
    pages = [
        "Ficha técnica: sensor de vapor SV-200\nRango de medición: 0 a 25 bar.\nPrecisión: ±0,5 %.\n"
        "Certificación: ATEX zona 2.",
        "Integración\nProtocolo Modbus TCP y MQTT.\nLa pasarela envía datos cada 30 segundos al tablero.",
        "Garantía y soporte\nGarantía de 24 meses.\nSoporte en español de lunes a viernes, 8 a 18 h (hora Colombia).",
    ]
    rect = QRectF(0, 0, w.width(), w.height())
    for i, text in enumerate(pages):
        if i:
            w.newPage()
        p.drawText(rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, text)
    p.end()

    # "Escaneado": solo una imagen con texto dibujado, sin capa de texto.
    img = QImage(1240, 1754, QImage.Format_RGB32)
    img.fill(QColor("white"))
    ip = QPainter(img)
    ip.setFont(QFont("Arial", 28))
    ip.drawText(80, 200, "Contrato firmado - escaneado")
    ip.end()
    w2 = QPdfWriter(str(HERE / "escaneado.pdf"))
    w2.setPageSize(QPageSize(QPageSize.A4))
    p2 = QPainter(w2)
    p2.drawImage(QRectF(0, 0, w2.width(), w2.height()), img)
    p2.end()


DRAWIO_MODEL = """<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="vpc" value="VPC prod" style="group" vertex="1" parent="1"/>
<mxCell id="api" value="API Gateway" vertex="1" parent="vpc"/>
<mxCell id="fn" value="Lambda &lt;b&gt;pagos&lt;/b&gt;" vertex="1" parent="vpc"/>
<mxCell id="db" value="Aurora&lt;br&gt;Postgres" vertex="1" parent="vpc"/>
<mxCell id="e1" edge="1" source="api" target="fn" parent="1"/>
<mxCell id="e1l" value="REST" style="edgeLabel" vertex="1" connectable="0" parent="e1"/>
<mxCell id="e2" value="SQL" edge="1" source="fn" target="db" parent="1"/>
</root></mxGraphModel>"""


def drawio() -> None:
    (HERE / "plano.drawio").write_text(
        f'<mxfile host="app.diagrams.net"><diagram id="a" name="Actual">{DRAWIO_MODEL}</diagram></mxfile>',
        encoding="utf-8")
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = comp.compress(urllib.parse.quote(DRAWIO_MODEL).encode()) + comp.flush()
    (HERE / "plano_comprimido.drawio").write_text(
        f'<mxfile host="drawio"><diagram id="b" name="Viejo">{base64.b64encode(packed).decode()}</diagram>'
        '</mxfile>', encoding="utf-8")


def text_files() -> None:
    # Excel en español guarda CSV con ";" y, con "UTF-8 (delimitado por comas)", con BOM.
    (HERE / "clientes_excel.csv").write_bytes(
        "﻿Cliente;Ciudad;Consumo vapor (t/mes)\nAcme;Bogotá;1.200\nCementos X;Cali;3.400\n".encode("utf-8"))
    # "CSV (delimitado por comas)" de Excel en Windows: cp1252, sin BOM.
    (HERE / "contactos_ansi.csv").write_bytes(
        "Nombre;Cargo\nMaría Gómez;Gerente de planta\nJosé Núñez;Director financiero\n".encode("cp1252"))
    # Bloc de notas "Unicode" = UTF-16 LE con BOM.
    (HERE / "notas_unicode.txt").write_bytes(
        "Reunión con Acme: quieren empezar en febrero. Decisor: María Gómez.".encode("utf-16"))
    (HERE / "infra.tf").write_text(
        'resource "aws_db_instance" "pagos" {\n  engine = "aurora-postgresql"\n  multi_az = true\n}\n',
        encoding="utf-8")
    (HERE / "flujo.mmd").write_text("graph LR\n  App-->API\n  API-->Pagos\n", encoding="utf-8")
    (HERE / "config.yaml").write_text("rpo_minutos: 15\nrto_minutos: 60\nregion: us-east-1\n", encoding="utf-8")
    (HERE / "esquema.sql").write_text("CREATE TABLE pagos (id bigint primary key, monto numeric);\n",
                                      encoding="utf-8")


if __name__ == "__main__":
    drawio()
    text_files()
    pdfs()
    print("ok")
