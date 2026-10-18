import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speak.tests import cern2_focused as runner
from speak.llm_client import FakeLLM


class FocusedTests(unittest.TestCase):
    def test_dry_run_makes_no_client(self):
        with patch.object(sys, 'argv', ['eval']), patch.object(runner, 'CodexEvalClient') as client:
            runner.main()
            client.assert_not_called()

    def test_call_cap_and_preserve_results(self):
        class Client(FakeLLM):
            last_usage = {'input_tokens': 1}
            prompt_chars = 100
        llm = Client('I would count source IPs.\nFuente: [code_conn_log_top]')
        with tempfile.TemporaryDirectory() as folder:
            argv = ['eval', '--run', '--only', '36,43', '--max-calls', '2', '--out', folder]
            with patch.object(sys, 'argv', argv), patch.object(runner, 'CodexEvalClient', return_value=llm):
                runner.main()
                data = json.loads((Path(folder) / 'result.json').read_text(encoding='utf-8'))
                self.assertEqual(len(llm.calls), 2)
                self.assertEqual(len(data['rows']), 2)
                self.assertIn('I would count source IPs.', llm.calls[1][1])
                with self.assertRaises(SystemExit):
                    runner.main()
                self.assertEqual(len(llm.calls), 2)

    def test_reading_flags(self):
        self.assertIn('inline_citation', runner.flags('Answer. [notes]'))
        self.assertIn('inline_code', runner.flags('Read `id.orig_h`.'))
        self.assertIn('meta_speech', runner.flags('I haven’t confirmed that.'))

    def test_empty_response_stops_without_retry(self):
        class Empty(FakeLLM):
            last_usage = {}
            prompt_chars = 0
        llm = Empty('')
        with tempfile.TemporaryDirectory() as folder:
            argv = ['eval', '--run', '--only', '36,43', '--out', folder]
            with patch.object(sys, 'argv', argv), patch.object(runner, 'CodexEvalClient', return_value=llm):
                with self.assertRaises(SystemExit):
                    runner.main()
            self.assertEqual(len(llm.calls), 1)
            data = json.loads((Path(folder) / 'result.json').read_text(encoding='utf-8'))
            self.assertIn('empty', data['rows'][0]['flags'])


if __name__ == '__main__':
    unittest.main()
