"""Respaldo del CLI por la API, como en SCREEN: si `claude -p` falla (limite de la sesion,
sin login), la misma llamada va por la API y se queda alli un rato."""

import unittest

from speak.llm_client import FakeLLM, FallbackLLM, LLMClient, LLMError, fallback_api_key


class DeadCLI(LLMClient):
    def __init__(self):
        self.calls = 0

    def stream(self, system, prompt, cancel=None, images=None):
        self.calls += 1
        raise LLMError("claude termino con codigo 1: You've hit your limit")
        yield ""


class HalfCLI(LLMClient):
    def stream(self, system, prompt, cancel=None, images=None):
        yield "medio"
        raise LLMError("se corto")


class FallbackTests(unittest.TestCase):
    def test_cli_failure_goes_to_the_api_and_sticks(self):
        cli, api = DeadCLI(), FakeLLM("por la api")
        switched = []
        llm = FallbackLLM(cli, lambda: api, stick_s=600, on_switch=switched.append)
        self.assertEqual(llm.complete("s", "p"), "por la api")
        self.assertEqual(llm.complete("s", "p2"), "por la api")
        self.assertEqual(cli.calls, 1)  # la segunda ya no espera al CLI caido
        self.assertEqual(len(switched), 1)

    def test_back_to_the_cli_after_the_window(self):
        cli = DeadCLI()
        llm = FallbackLLM(cli, lambda: FakeLLM("api"), stick_s=0)
        llm.complete("s", "p")
        llm.complete("s", "p")
        self.assertEqual(cli.calls, 2)

    def test_healthy_cli_never_touches_the_api(self):
        def boom():
            raise AssertionError("no debia crear el respaldo")

        llm = FallbackLLM(FakeLLM("cli"), boom)
        self.assertEqual(llm.complete("s", "p"), "cli")

    def test_failure_after_text_is_not_repeated(self):
        llm = FallbackLLM(HalfCLI(), lambda: FakeLLM("api"))
        with self.assertRaises(LLMError):
            llm.complete("s", "p")

    def test_key_from_speak_or_project_env(self):
        import tempfile
        from pathlib import Path

        class Cfg:
            API_KEY = ""

        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text("OTHER=1\nANTHROPIC_API_KEY=sk-ant-test\n", encoding="utf-8")
            import os
            old = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                self.assertEqual(fallback_api_key(Cfg, env), "sk-ant-test")
                Cfg.API_KEY = "sk-ant-speak"
                self.assertEqual(fallback_api_key(Cfg, env), "sk-ant-speak")
            finally:
                if old is not None:
                    os.environ["ANTHROPIC_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
