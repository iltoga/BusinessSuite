"""Tests for the image-AI ask command workflow."""

import io
import os
import tempfile
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import SimpleTestCase


class AskImageAICommandTests(SimpleTestCase):
    def setUp(self):
        # ensure GROQ_API_KEY is set for the command
        os.environ.setdefault("GROQ_API_KEY", "test-key")

    def tearDown(self):
        os.environ.pop("GROQ_API_KEY", None)

    def test_non_absolute_path_is_rejected(self):
        out = io.StringIO()
        err = io.StringIO()
        call_command(
            "ask_image_ai",
            "relative/path.jpg",
            "ques",
            "pred",
            stdout=out,
            stderr=err,
        )
        self.assertIn("image_path must be absolute", err.getvalue())

    def test_missing_file_reports_error(self):
        out = io.StringIO()
        err = io.StringIO()
        call_command(
            "ask_image_ai",
            "/nonexistent/file.jpg",
            "ques",
            "pred",
            stdout=out,
            stderr=err,
        )
        self.assertIn("Image file /nonexistent/file.jpg not found", err.getvalue())

    def test_successful_api_call_prints_content(self):
        # create temporary image file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(b"fakeimagebytes")
            tmp_path = tmp.name
        try:
            # prepare fake groq client
            fake_resp = MagicMock()
            fake_choice = MagicMock()
            fake_choice.message.content = '{"foo":"bar"}'
            fake_resp.choices = [fake_choice]
            fake_client = MagicMock()
            fake_client.chat.completions.create.return_value = fake_resp

            with patch("core.management.commands.ask_image_ai.Groq", return_value=fake_client) as groq_ctor:
                out = io.StringIO()
                # call the command with defaults
                call_command(
                    "ask_image_ai",
                    tmp_path,
                    "What is this image?",
                    "foo,bar",
                    stdout=out,
                )
                output = out.getvalue().strip()
                # should have printed the JSON string
                self.assertEqual(output, '{"foo":"bar"}')
                # ensure Groq was constructed with API key
                groq_ctor.assert_called_with(api_key="test-key")
                # verify the call parameters include our prompt pieces
                called_kwargs = fake_client.chat.completions.create.call_args.kwargs
                self.assertIn("messages", called_kwargs)
                messages = called_kwargs["messages"]
                self.assertIsInstance(messages, list)
                # verify prompt text composition
                text_block = messages[0]["content"][0]
                self.assertIn("What is this image?", text_block["text"])
                self.assertIn("foo,bar", text_block["text"])
                self.assertIn("use JSON output", text_block["text"])
        finally:
            os.unlink(tmp_path)
