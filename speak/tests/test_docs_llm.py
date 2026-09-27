"""Cliente de Claude (sin red), imagenes, preparacion y CLI de notas."""

from __future__ import annotations

import base64
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from speak.knowledge import KnowledgeBase
from speak.llm_client import ClaudeCLIClient, image_block, user_message_json


class CliArgsTests(unittest.TestCase):
    def setUp(self):
        self.which = mock.patch("speak.llm_client.shutil.which", return_value="claude.exe")
        self.which.start()

    def tearDown(self):
        self.which.stop()

    def test_short_system_prompt_goes_inline_without_tools(self):
        args = ClaudeCLIClient("claude-sonnet-5")._args("hola")
        self.assertEqual(args[args.index("--system-prompt") + 1], "hola")
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertNotIn("--input-format", args)

    def test_long_system_prompt_goes_by_file_and_is_deleted(self):
        seen = {}

        class FakeProc:
            def __init__(self, args, **kw):
                i = args.index("--system-prompt-file")
                seen["file"] = Path(args[i + 1])
                seen["content"] = seen["file"].read_text(encoding="utf-8")
                self.stdin = io.StringIO()
                self.stdout = iter([json.dumps({"type": "stream_event", "event": {
                    "type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}}}) + "\n"])
                self.stderr = iter([])
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

            def poll(self):
                return 0

            def kill(self):
                pass

        system = "x" * 20_000
        with mock.patch("speak.llm_client.subprocess.Popen", FakeProc):
            out = "".join(ClaudeCLIClient("m").stream(system, "p"))
        self.assertEqual(out, "ok")
        self.assertEqual(seen["content"], system)
        self.assertFalse(seen["file"].exists())  # se borra al terminar

    def test_images_switch_to_json_input(self):
        args = ClaudeCLIClient("m")._args("s", json_input=True)
        self.assertEqual(args[args.index("--input-format") + 1], "stream-json")


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_media_types(self):
        for ext, media in ((".png", "image/png"), (".JPG", "image/jpeg"), (".webp", "image/webp")):
            p = self.tmp / f"a{ext}"
            p.write_bytes(b"data")
            self.assertEqual(image_block(p)["source"]["media_type"], media)

    def test_huge_screenshot_is_shrunk_to_jpeg(self):
        import numpy as np
        from PySide6.QtGui import QImage

        noise = np.random.default_rng(0).integers(0, 255, (1800, 3200, 4), dtype=np.uint8)
        img = QImage(noise.data, 3200, 1800, QImage.Format_RGB32)
        path = self.tmp / "captura_4k.png"
        self.assertTrue(img.save(str(path)))
        self.assertGreater(path.stat().st_size, 3_500_000)
        block = image_block(path)
        self.assertEqual(block["source"]["media_type"], "image/jpeg")
        self.assertLess(len(base64.b64decode(block["source"]["data"])), 3_500_000)

    def test_message_json_order(self):
        p = self.tmp / "d.png"
        p.write_bytes(b"x")
        content = json.loads(user_message_json("describe", [p]))["message"]["content"]
        self.assertEqual([c["type"] for c in content], ["image", "text"])


class RecordingLLM:
    def __init__(self, reply="ok"):
        self.reply, self.calls = reply, []

    def stream(self, system, prompt, cancel=None, images=None):
        self.calls.append((system, prompt, images))
        yield self.reply

    def complete(self, system, prompt, images=None):
        return "".join(self.stream(system, prompt, images=images))


class PrepPromptTests(unittest.TestCase):
    def test_prompts_have_no_duplicated_articles_in_any_mode(self):
        from speak.notes.analyzer import MODES
        from speak.notes.copilot import DESCRIBE_SYSTEM, PrepSession, answer_prompt, discovery_prompt

        for mode in MODES:
            texts = [answer_prompt("q", "", "", "", mode)[0], discovery_prompt(None, "", "", mode)[0],
                     PrepSession(KnowledgeBase(), mode=mode).chat_prompt("hola")[0],
                     DESCRIBE_SYSTEM.format(what=MODES[mode], language="Spanish")]
            for t in texts:
                self.assertNotRegex(t, r"\b(a|an) (a|an) ", mode)
                self.assertNotRegex(t, r"\{(what|language|guide)\}", mode)  # sin plantillas sin llenar

    def test_brief_prompt_lists_documents_and_mode_sections(self):
        from speak.notes.copilot import PrepSession

        kb = KnowledgeBase()
        kb.add_text("propuesta_acme.docx", "Precio 12.000 USD por planta")
        prep = PrepSession(kb, mode="arquitectura")
        _, user = prep.brief_prompt()
        self.assertIn("- propuesta_acme.docx", user)
        self.assertIn('<source name="propuesta_acme.docx">', user)
        self.assertIn("¿Alcanza la información?", user)

    def test_failed_chat_keeps_history_consistent(self):
        from speak.notes.copilot import PrepSession

        class Boom:
            def stream(self, *a, **k):
                raise RuntimeError("sin red")
                yield ""

        prep = PrepSession(KnowledgeBase())
        with self.assertRaises(RuntimeError):
            prep.chat(Boom(), "hola")
        self.assertEqual(prep.messages, [])  # sin un "Yo" colgado sin respuesta

    def test_attach_file_document_error_is_readable(self):
        from speak.knowledge import DocumentError
        from speak.notes.copilot import attach_file

        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "vacio.md").write_text("", encoding="utf-8")
            with self.assertRaises(DocumentError) as ctx:
                attach_file(KnowledgeBase(), tmp / "vacio.md")
            self.assertIn("no tiene texto", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class NotesCliTests(unittest.TestCase):
    def test_analyze_utf16_vtt_without_llm(self):
        from speak.notes.__main__ import main

        tmp = Path(tempfile.mkdtemp())
        try:
            vtt = ("WEBVTT\r\n\r\n1\r\n00:00:01.000 --> 00:00:04.000\r\n<v Ana Pérez>¿Cuál es el plazo?</v>\r\n\r\n"
                   "2\r\n00:00:05.000 --> 00:00:07.000\r\n<v Yo>Ocho semanas.</v>\r\n")
            src = tmp / "teams.vtt"
            src.write_bytes(vtt.encode("utf-16"))
            buf = io.StringIO()
            with mock.patch("speak.notes.__main__.DATA_DIR", tmp), redirect_stdout(buf):
                code = main(["analyze", str(src), "--no-llm"])
            self.assertEqual(code, 0)
            out_dir = next(p for p in (tmp / "notes").iterdir() if p.is_dir())
            transcript = (out_dir / "transcript.md").read_text(encoding="utf-8")
            self.assertIn("Ana Pérez: ¿Cuál es el plazo?", transcript)
            self.assertIn("Preguntas detectadas: 1", buf.getvalue())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cli_passes_notes_language(self):
        from speak.notes import __main__ as cli

        llm = RecordingLLM("# Resumen")
        tmp = Path(tempfile.mkdtemp())
        try:
            src = tmp / "t.txt"
            src.write_text("Ana: What is the timeline?\nYo: Eight weeks.", encoding="utf-8")
            with mock.patch.object(cli, "make_llm", return_value=llm), \
                    mock.patch.object(cli, "DATA_DIR", tmp), \
                    mock.patch.object(cli.Config, "load", return_value=_cfg(NOTES_LANGUAGE="English")), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["analyze", str(src), "--mode", "venta"]), 0)
            self.assertIn("Write in English", llm.calls[0][0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _cfg(**kw):
    from speak.config import Config

    cfg = Config()
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


if __name__ == "__main__":
    unittest.main()
