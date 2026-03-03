"""
Django management command that sends an image+question to a Groq LLM and prints the
JSON‑formatted response.

Usage examples:

    python manage.py ask_image_ai \
        /absolute/path/to/image.jpg \
        "What fields do you see?" \
        "field1, field2, field3" \
        --model "meta-llama/llama-4-scout-17b-16e-instruct"

The command will base64‑encode the image in memory, construct the chat request with the
question text followed by the provided `predicted_output` text, insert the phrase
"use JSON output" separated by newlines, and then call Groq using the
`GROQ_API_KEY` environment variable.

The resulting JSON object returned by Groq is printed on stdout.
"""

from __future__ import annotations

import base64
import os
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

try:
    from groq import Groq
except ImportError:  # pragma: no cover - import failure means the command simply won't run
    Groq = None  # type: ignore


class Command(BaseCommand):
    help = "Send an image+question to a Groq LLM and print the JSON response."

    def add_arguments(self, parser: ArgumentParser) -> None:  # pragma: no cover - argparse definitions
        parser.add_argument(
            "image_path",
            type=str,
            help="Absolute path to the image file to send",
        )
        parser.add_argument(
            "question",
            type=str,
            help="Text of the question for the AI",
        )
        parser.add_argument(
            "predicted_output",
            type=str,
            help=(
                "Text containing the predicted output (e.g. list of field names). "
                "This will be inserted between the question and the fixed phrase "
                '"use JSON output" with a blank line before and after.'
            ),
        )
        parser.add_argument(
            "--model",
            type=str,
            default="meta-llama/llama-4-scout-17b-16e-instruct",
            help="LLM model name to use (defaults to the Scout 17b instruct model)",
        )

    def handle(self, *args: Any, **options: Any) -> None:  # pragma: no cover - manual invocation
        image_path: str = options.get("image_path")
        question: str = options.get("question")
        predicted_output: str = options.get("predicted_output")
        model: str = options.get("model")

        if not os.path.isabs(image_path):
            self.stderr.write(self.style.ERROR("image_path must be absolute"))
            return

        if not os.path.exists(image_path):
            self.stderr.write(self.style.ERROR(f"Image file {image_path} not found"))
            return

        if Groq is None:
            self.stderr.write(self.style.ERROR("groq library is not installed"))
            return

        def encode_image(path: str) -> str:
            with open(path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")

        base64_image = encode_image(image_path)

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            self.stderr.write(self.style.ERROR("GROQ_API_KEY environment variable not set"))
            return

        client = Groq(api_key=api_key)

        # build the prompt text with required separators
        prompt_text = f"{question}\n{predicted_output}\nuse JSON output\n"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                        },
                    },
                ],
            }
        ]

        try:
            chat_completion = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.3,
                max_completion_tokens=1024,
                top_p=1,
                stream=False,
                response_format={"type": "json_object"},
                stop=None,
            )
        except Exception as exc:  # pragma: no cover - external API errors
            self.stderr.write(self.style.ERROR(f"API call failed: {exc}"))
            return

        # Extract and print the returned content
        result_content = None
        try:
            result_content = chat_completion.choices[0].message.content
        except Exception:
            # fallback to string representation
            result_content = str(chat_completion)

        self.stdout.write(str(result_content))
