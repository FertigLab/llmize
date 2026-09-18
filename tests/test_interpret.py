from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import interpret


class TestInterpretTextReport(unittest.TestCase):
    @patch("interpret.ensure_model", return_value="test-model")
    @patch("interpret.chat_ollama")
    def test_text_synthesis_uses_text_specific_prompt(self, chat_ollama, _ensure_model):
        chat_ollama.side_effect = [
            ("section one", ""),
            ("section two", ""),
            ("summary", ""),
        ]

        interpret.interpret_text_report(
            "## Section One\nbody one\n## Section Two\nbody two\n",
            "test-model",
            synthesize_final=True,
            think=False,
        )

        self.assertEqual(chat_ollama.call_count, 3)
        self.assertEqual(
            chat_ollama.call_args_list[-1].kwargs["system"],
            interpret.TEXT_SYNTHESIS_SYSTEM_PROMPT,
        )

    @patch("interpret.ensure_model", return_value="test-model")
    @patch("interpret.chat_ollama")
    def test_text_synthesis_uses_as_is_prompt_without_style_rules(self, chat_ollama, _ensure_model):
        chat_ollama.side_effect = [
            ("section one", ""),
            ("section two", ""),
            ("summary", ""),
        ]

        interpret.interpret_text_report(
            "## Section One\nbody one\n## Section Two\nbody two\n",
            "test-model",
            synthesize_final=True,
            think=False,
            as_is=True,
        )

        self.assertEqual(chat_ollama.call_count, 3)
        self.assertEqual(
            chat_ollama.call_args_list[-1].kwargs["system"],
            interpret.TEXT_AS_IS_SYNTHESIS_SYSTEM_PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
