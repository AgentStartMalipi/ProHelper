"""Lectura de documentos reales y busqueda.

Los fixtures de Word/PowerPoint/Excel los genero Office de verdad
(`fixtures/make_office.ps1`), y los PDF Qt (`fixtures/make_files.py`): asi se
prueba contra lo que produce el software de siempre, no contra XML armado a
mano. Sin red, sin Claude.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from speak.knowledge import (
    SUPPORTED,
    Chunk,
    DocumentError,
    KnowledgeBase,
    decode_text,
    read_document,
)

FX = Path(__file__).resolve().parent / "fixtures"


class RealOfficeFilesTests(unittest.TestCase):
    def test_word_tables_textbox_header_footer(self):
        text = read_document(FX / "propuesta_acme.docx")
        self.assertIn("Propuesta de auditoría energética para Acme", text)
        self.assertIn("Bogotá | 12.000 | 8 semanas", text)  # la tabla conserva sus filas
        self.assertEqual(text.count("Nota destacada: anticipo del 30 por ciento"), 1)  # sin duplicar
        self.assertNotIn("valor.Nota", text)  # el cuadro no se pega al parrafo
        self.assertIn("Ecoeffy - Propuesta confidencial", text)  # encabezado
        self.assertIn("ventas@ecoeffy.test", text)  # pie

    def test_powerpoint_tables_groups_and_speaker_notes(self):
        text = read_document(FX / "caso_cementos.pptx")
        self.assertIn("[Diapositiva 1]\nCaso de éxito Cementos X", text)
        self.assertIn("Retorno | 14 meses", text)
        self.assertIn("Red de vapor", text)  # forma dentro de un grupo
        self.assertIn("Notas del orador: Nota del orador: el cliente pidió", text)
        self.assertLess(text.index("[Diapositiva 2]"), text.index("[Diapositiva 10]"))  # orden numerico

    def test_excel_sheets_formulas_and_percent(self):
        text = read_document(FX / "precios.xlsx")
        self.assertIn("[Hoja Precios]", text)
        self.assertIn("Servicio: Auditoría de vapor; Precio USD: 12000; Unidad: planta", text)
        self.assertIn("Precio USD: 12450", text)  # valor calculado de =B2+B3
        self.assertIn("Descuento: 7%", text)
        self.assertIn("[Hoja Descuentos]", text)


class PdfTests(unittest.TestCase):
    def test_multipage_pdf(self):
        text = read_document(FX / "ficha_tecnica.pdf")
        self.assertIn("[Pagina 3]", text)
        self.assertIn("ATEX zona 2", text)

    def test_scanned_pdf_says_so(self):
        with self.assertRaises(DocumentError) as ctx:
            read_document(FX / "escaneado.pdf")
        self.assertIn("escaneado", str(ctx.exception))


class TextEncodingTests(unittest.TestCase):
    def test_excel_csv_semicolon_with_bom(self):
        text = read_document(FX / "clientes_excel.csv")
        self.assertTrue(text.startswith("Cliente: Acme; Ciudad: Bogotá"))
        self.assertNotIn("﻿", text)

    def test_ansi_csv(self):
        self.assertIn("Nombre: María Gómez; Cargo: Gerente de planta", read_document(FX / "contactos_ansi.csv"))

    def test_notepad_unicode_txt(self):
        self.assertEqual(read_document(FX / "notas_unicode.txt"),
                         "Reunión con Acme: quieren empezar en febrero. Decisor: María Gómez.")

    def test_decode_text_variants(self):
        s = "Año de ejecución"
        for data in (s.encode("utf-8"), b"\xef\xbb\xbf" + s.encode("utf-8"), s.encode("utf-16"),
                     s.encode("utf-16-be").join([b"\xfe\xff", b""]), s.encode("cp1252")):
            self.assertEqual(decode_text(data), s)

    def test_technical_files(self):
        self.assertIn("multi_az = true", read_document(FX / "infra.tf"))
        self.assertIn("rpo_minutos: 15", read_document(FX / "config.yaml"))
        self.assertIn("API-->Pagos", read_document(FX / "flujo.mmd"))
        self.assertIn("CREATE TABLE pagos", read_document(FX / "esquema.sql"))

    def test_html_entities(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "p.html").write_text("<p>Precio &amp; plazo: 8&nbsp;semanas</p><script>x()</script>",
                                        encoding="utf-8")
            text = read_document(tmp / "p.html")
            self.assertIn("Precio & plazo: 8", text)
            self.assertNotIn("x()", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class DrawioTests(unittest.TestCase):
    def test_plain_and_compressed_with_edge_label_cells(self):
        for name in ("plano.drawio", "plano_comprimido.drawio"):
            text = read_document(FX / name)
            self.assertIn("- API Gateway → Lambda pagos (REST)", text)  # etiqueta como celda hija
            self.assertIn("- Lambda pagos → Aurora Postgres (SQL)", text)
            self.assertNotIn("- REST", text)  # la etiqueta no es un componente
            self.assertIn("- Aurora Postgres (dentro de VPC prod)", text)


class ErrorsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unsupported_empty_and_corrupt(self):
        (self.tmp / "a.exe").write_bytes(b"MZ")
        (self.tmp / "vacio.txt").write_text("   \n", encoding="utf-8")
        (self.tmp / "roto.docx").write_bytes(b"no soy un zip")
        for name, words in (("a.exe", "no soportado"), ("vacio.txt", "no tiene texto"),
                            ("roto.docx", "Office valido")):
            with self.assertRaises(DocumentError) as ctx:
                read_document(self.tmp / name)
            self.assertIn(words, str(ctx.exception))

    def test_folder_reports_errors_skips_office_temp_files_and_uses_cache(self):
        for name in ("propuesta_acme.docx", "escaneado.pdf", "precios.xlsx"):
            shutil.copy2(FX / name, self.tmp / name)
        (self.tmp / "~$propuesta_acme.docx").write_bytes(b"\x00lock")
        kb = KnowledgeBase(self.tmp, self.tmp / "cache.json")
        self.assertEqual(kb.load_folder(), 2)
        self.assertEqual(len(kb.errors), 1)
        self.assertIn("escaneado.pdf", kb.errors[0])
        self.assertEqual(set(kb.sources()), {"propuesta_acme.docx", "precios.xlsx"})
        # Cache: la segunda carga solo reintenta el que fallo; los buenos no se releen.
        import speak.knowledge as k

        original, reread = k.read_document, []
        k.read_document = lambda p: (reread.append(Path(p).name), original(p))[1]
        try:
            kb2 = KnowledgeBase(self.tmp, self.tmp / "cache.json")
            kb2.load_folder()
        finally:
            k.read_document = original
        self.assertEqual(reread, ["escaneado.pdf"])
        self.assertEqual(set(kb2.sources()), {"propuesta_acme.docx", "precios.xlsx"})
        # Si un archivo cambia, se relee.
        time.sleep(0.05)
        (self.tmp / "nuevo.md").write_text("Plazo: 6 semanas", encoding="utf-8")
        kb3 = KnowledgeBase(self.tmp, self.tmp / "cache.json")
        self.assertEqual(kb3.load_folder(), 3)
        self.assertIn("nuevo.md", kb3.sources())

    def test_empty_attachment_is_an_error_not_a_ghost(self):
        kb = KnowledgeBase()
        with self.assertRaises(DocumentError):
            kb.add_text("vacio", "  ")
        self.assertEqual(kb.extra_names(), [])

    def test_supported_includes_excel(self):
        self.assertIn(".xlsx", SUPPORTED)


class SearchTests(unittest.TestCase):
    def test_cross_lingual_retrieval_quality(self):
        from speak.tests import retrieval_eval as ev

        for questions, minimum in ((ev.QUESTIONS, 22), (ev.HELD_OUT, 10)):
            results, _ = ev.evaluate(questions=questions)
            hits = sum(h for h, _ in results.values())
            self.assertGreaterEqual(hits, minimum, results)

    def test_folder_index_is_ready_after_loading(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            text = "\n\n".join(f"Seccion {i}: presion y caudal de vapor medidos por MQTT." for i in range(3000))
            (tmp / "manual.txt").write_text(text, encoding="utf-8")
            kb = KnowledgeBase(tmp)
            kb.load_folder()
            t0 = time.time()
            kb.search("caudal de vapor")
            self.assertLess(time.time() - t0, 0.5)  # no arma el indice en la primera pregunta
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_attachment_added_during_search_is_never_lost(self):
        kb = KnowledgeBase()
        for i in range(200):
            kb.add_text(f"doc{i}", f"documento numero {i} sobre calderas " * 20)
        stop = threading.Event()

        def searcher():
            while not stop.is_set():
                kb.search("calderas")

        t = threading.Thread(target=searcher)
        t.start()
        try:
            for i in range(30):
                kb.add_text(f"nuevo{i}", f"ficha especial zeppelin{i} del cliente")
                time.sleep(0.002)
        finally:
            stop.set()
            t.join()
        for i in range(30):
            self.assertEqual(kb.search(f"zeppelin{i}", max_chars=100)[0].source, f"nuevo{i}")

    def test_model_codes_are_not_truncated(self):
        kb = KnowledgeBase()
        kb.add_text("sv200.md", "El SV200 mide hasta 25 bar. " * 30)
        kb.add_text("sv300.md", "El SV300 mide hasta 40 bar. " * 30)
        self.assertEqual(kb.search("rango del SV300", max_chars=100)[0].source, "sv300.md")

    def test_small_kb_returns_everything_ranked(self):
        kb = KnowledgeBase()
        kb.add_text("a", "calderas y vapor")
        kb.add_text("b", "precio de la auditoria")
        out = kb.search("precio")
        self.assertEqual([c.source for c in out], ["b", "a"])
        self.assertIsInstance(out[0], Chunk)


if __name__ == "__main__":
    unittest.main()
