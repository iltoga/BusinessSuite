"""
AI Client Base Module
Provides a reusable AI client for OpenRouter/OpenAI API access.
All AI-powered services should use this base client for consistency.
"""

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Optional, Union

import openai
from core.services.ai_usage_service import AIUsageFeature, AIUsageService
from core.services.logger_service import Logger
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from openai import OpenAI

logger = Logger.get_logger(__name__)


GENERIC_AI_PROVIDER_ERROR = "AI provider error"
GENERIC_AI_SLOW_RESPONSE = "AI slow response"


class AIConnectionError(Exception):
    """Exception raised when a connection/provider error occurs with the AI provider."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "provider_error",
        is_timeout: bool = False,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.is_timeout = is_timeout


def is_ai_timeout_exception(exc: BaseException) -> bool:
    """Return True when an exception represents an AI timeout."""
    return isinstance(exc, AIConnectionError) and bool(getattr(exc, "is_timeout", False))


def get_ai_user_message(exc: BaseException) -> str:
    """Map provider exceptions to safe user-facing messages."""
    if is_ai_timeout_exception(exc):
        return GENERIC_AI_SLOW_RESPONSE
    if isinstance(exc, AIConnectionError):
        return str(exc) or GENERIC_AI_PROVIDER_ERROR
    return GENERIC_AI_PROVIDER_ERROR


class AIClient:
    """
    Base AI client for OpenRouter/OpenAI API.
    Provides common functionality for all AI-powered services.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_openrouter: Optional[bool] = None,
        timeout: Optional[float] = None,
        feature_name: Optional[str] = None,
    ):
        """
        Initialize the AI client.

        Args:
            api_key: API key (defaults to settings based on provider)
            model: Model to use (defaults to settings.LLM_DEFAULT_MODEL)
            use_openrouter: Whether to use OpenRouter (defaults to settings.LLM_PROVIDER)
            timeout: Request timeout in seconds (defaults to settings)
            feature_name: Logical AI feature tag used for usage accounting
        """
        self.feature_name = feature_name or AIUsageFeature.UNKNOWN

        # Determine provider
        if use_openrouter is None:
            llm_provider = getattr(settings, "LLM_PROVIDER", "openrouter")
            self.use_openrouter = llm_provider == "openrouter"
        else:
            self.use_openrouter = use_openrouter

        if self.use_openrouter:
            self._init_openrouter(api_key, model, timeout)
        else:
            self._init_openai(api_key, model, timeout)

    def _init_openrouter(
        self,
        api_key: Optional[str],
        model: Optional[str],
        timeout: Optional[float],
    ):
        """Initialize OpenRouter client."""
        self.api_key = api_key or getattr(settings, "OPENROUTER_API_KEY", None)
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured. Set OPENROUTER_API_KEY in settings or .env file.")

        configured_default_model = getattr(settings, "LLM_DEFAULT_MODEL", None)
        deprecated_default_models = {"google/gemini-2.0-flash-001"}
        effective_default_model = (
            "google/gemini-2.5-flash-lite"
            if not configured_default_model or configured_default_model in deprecated_default_models
            else configured_default_model
        )
        self.model = model or effective_default_model

        base_url = getattr(settings, "OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1")
        self.timeout = timeout or getattr(settings, "OPENROUTER_TIMEOUT", 120.0)

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=self.timeout,
        )

        self.provider_name = "OpenRouter"
        logger.info(f"Initialized AI client with OpenRouter (model: {self.model}, timeout: {self.timeout}s)")

    def _init_openai(
        self,
        api_key: Optional[str],
        model: Optional[str],
        timeout: Optional[float],
    ):
        """Initialize OpenAI client."""
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        if not self.api_key:
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in settings or .env file.")

        self.model = model or getattr(settings, "LLM_DEFAULT_MODEL", "gpt-4o-mini")
        self.timeout = timeout or getattr(settings, "OPENAI_TIMEOUT", 120.0)

        self.client = OpenAI(
            api_key=self.api_key,
            timeout=self.timeout,
        )

        self.provider_name = "OpenAI"
        logger.info(f"Initialized AI client with OpenAI (model: {self.model}, timeout: {self.timeout}s)")

    def chat_completion(
        self,
        messages: list,
        temperature: float = 0.1,
        response_format: Optional[dict] = None,
        **kwargs,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-2)
            response_format: Optional response format (e.g., json_schema)
            **kwargs: Additional arguments passed to the API

        Returns:
            Response text content
        """
        request_kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }

        if response_format:
            request_kwargs["response_format"] = response_format

        feature_name = kwargs.pop("feature_name", None) or self.feature_name or AIUsageFeature.UNKNOWN
        started_at = time.perf_counter()

        try:
            response = self.client.chat.completions.create(**request_kwargs)
            self._record_usage(
                feature_name=feature_name,
                response=response,
                success=True,
                error_type="",
                started_at=started_at,
            )
            return response.choices[0].message.content
        except openai.APITimeoutError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="APITimeoutError",
                started_at=started_at,
            )
            logger.error(
                "%s timeout after %.1fs. details=%s",
                self.provider_name,
                self.timeout,
                str(e),
            )
            raise AIConnectionError(
                GENERIC_AI_SLOW_RESPONSE,
                error_code="timeout",
                is_timeout=True,
            ) from e
        except openai.APIConnectionError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="APIConnectionError",
                started_at=started_at,
            )
            logger.error(
                "%s connection error: %s (cause=%s)",
                self.provider_name,
                str(e),
                str(e.__cause__) if e.__cause__ else "",
            )
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="connection_error") from e
        except openai.RateLimitError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="RateLimitError",
                started_at=started_at,
            )
            logger.error("%s rate limit error: %s", self.provider_name, str(e))
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="rate_limit") from e
        except openai.AuthenticationError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="AuthenticationError",
                started_at=started_at,
            )
            logger.error("%s authentication error: %s", self.provider_name, str(e))
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="auth_error") from e
        except openai.BadRequestError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="BadRequestError",
                started_at=started_at,
            )
            logger.error("%s bad request error: %s", self.provider_name, str(e))
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="bad_request") from e
        except openai.NotFoundError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="NotFoundError",
                started_at=started_at,
            )
            logger.error("%s not found error: %s", self.provider_name, str(e))
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="not_found") from e
        except openai.InternalServerError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="InternalServerError",
                started_at=started_at,
            )
            logger.error("%s internal server error: %s", self.provider_name, str(e))
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="internal_server") from e
        except openai.APIStatusError as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type="APIStatusError",
                started_at=started_at,
            )
            logger.error(
                "%s API status error http=%s details=%s",
                self.provider_name,
                getattr(e, "status_code", "unknown"),
                str(e),
            )
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="status_error") from e
        except Exception as e:
            self._record_usage(
                feature_name=feature_name,
                response=None,
                success=False,
                error_type=type(e).__name__,
                started_at=started_at,
            )
            logger.error("Unexpected %s client error: %s", self.provider_name, str(e), exc_info=True)
            raise AIConnectionError(GENERIC_AI_PROVIDER_ERROR, error_code="unexpected_error") from e

    def _record_usage(
        self,
        *,
        feature_name: str,
        response: Any,
        success: bool,
        error_type: str,
        started_at: float,
    ) -> None:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        AIUsageService.enqueue_request_capture(
            feature=feature_name or self.feature_name or AIUsageFeature.UNKNOWN,
            provider=self.provider_name.lower(),
            model=self.model,
            response=response,
            success=success,
            error_type=error_type,
            latency_ms=elapsed_ms,
        )

    def chat_completion_json(
        self,
        messages: list,
        json_schema: dict,
        schema_name: str = "response",
        temperature: float = 0.1,
        strict: bool = True,
        retry_on_invalid_json: bool = True,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request with structured JSON output.

        Both OpenRouter and OpenAI support json_schema with strict mode.
        See: https://openrouter.ai/docs/guides/features/structured-outputs

        Args:
            messages: List of message dicts
            json_schema: JSON schema for the response
            schema_name: Name for the schema
            temperature: Sampling temperature
            strict: Whether to enforce strict schema adherence
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response as dict
        """
        logger.debug(f"Using json_schema mode for model: {self.model} (strict={strict})")

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": strict,
                "schema": json_schema,
            },
        }

        return self._request_json_with_retry(
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            retry_on_invalid_json=retry_on_invalid_json,
            **kwargs,
        )

    def chat_completion_simple_json(
        self,
        messages: list,
        temperature: float = 0.3,
        retry_on_invalid_json: bool = True,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request expecting simple JSON object response.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            **kwargs: Additional arguments

        Returns:
            Parsed JSON response as dict
        """
        return self._request_json_with_retry(
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            retry_on_invalid_json=retry_on_invalid_json,
            **kwargs,
        )

    def _request_json_with_retry(
        self,
        messages: list,
        temperature: float,
        response_format: dict,
        retry_on_invalid_json: bool = True,
        **kwargs,
    ) -> dict:
        """
        Request JSON output with one automatic retry when the model emits invalid JSON.

        Some models occasionally return malformed JSON despite response_format hints.
        We attempt local repair first, then retry once with a corrective prompt.
        """
        response_text = self.chat_completion(
            messages=messages,
            temperature=temperature,
            response_format=response_format,
            **kwargs,
        )
        try:
            return self._parse_json_dict(response_text)
        except ValueError as first_exc:
            if not retry_on_invalid_json:
                raise ValueError(
                    f"Invalid JSON response from {self.provider_name}: {first_exc}"
                ) from first_exc
            logger.warning(
                "Received malformed JSON from %s. Retrying once with corrective prompt. Error: %s",
                self.provider_name,
                str(first_exc),
            )

            retry_messages = list(messages) + [
                {
                    "role": "user",
                    "content": (
                        "Your previous answer was not valid JSON. "
                        "Return ONLY a valid JSON object. "
                        "Do not use markdown code fences."
                    ),
                }
            ]

            retry_text = self.chat_completion(
                messages=retry_messages,
                temperature=0.0,
                response_format=response_format,
                **kwargs,
            )
            try:
                return self._parse_json_dict(retry_text)
            except ValueError as retry_exc:
                raise ValueError(
                    f"Invalid JSON response from {self.provider_name} after retry: {retry_exc}"
                ) from retry_exc

    @classmethod
    def _parse_json_dict(cls, response_text: Any) -> dict:
        """Parse a response into a JSON object with lightweight repair heuristics."""
        if isinstance(response_text, dict):
            return response_text

        if response_text is None:
            raise ValueError("AI response was empty.")

        if not isinstance(response_text, str):
            raise ValueError(f"AI response is not text (got {type(response_text).__name__}).")

        parse_errors: list[str] = []
        for candidate in cls._extract_json_candidates(response_text):
            tried: list[str] = [candidate]
            repaired = cls._repair_common_json_issues(candidate)
            if repaired != candidate:
                tried.append(repaired)

            for current in tried:
                try:
                    parsed = json.loads(current)
                except json.JSONDecodeError as exc:
                    parse_errors.append(str(exc))
                    continue

                if not isinstance(parsed, dict):
                    raise ValueError("AI response JSON must be an object.")
                return parsed

        if parse_errors:
            raise ValueError(parse_errors[-1])
        raise ValueError("No JSON object found in AI response.")

    @classmethod
    def _extract_json_candidates(cls, response_text: str) -> list[str]:
        """
        Build parse candidates from plain text and markdown-fenced JSON blocks.
        """
        candidates: list[str] = []
        seen: set[str] = set()

        def add(value: Optional[str]) -> None:
            if not value:
                return
            candidate = value.strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            candidates.append(candidate)

        add(response_text)

        for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", response_text, flags=re.IGNORECASE | re.DOTALL):
            add(match.group(1))

        add(cls._extract_first_json_block(response_text))
        return candidates

    @staticmethod
    def _extract_first_json_block(text: str) -> Optional[str]:
        """Extract the first balanced JSON object/array block from arbitrary text."""
        start_obj = text.find("{")
        start_arr = text.find("[")

        starts = [pos for pos in (start_obj, start_arr) if pos >= 0]
        if not starts:
            return None

        start_index = min(starts)
        stack: list[str] = []
        in_string = False
        escaped = False

        for index in range(start_index, len(text)):
            ch = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in ("}", "]"):
                if not stack or ch != stack[-1]:
                    return None
                stack.pop()
                if not stack:
                    return text[start_index : index + 1]

        return text[start_index:] if stack else None

    @staticmethod
    def _repair_common_json_issues(text: str) -> str:
        """
        Repair common malformed JSON patterns seen in model outputs.
        """
        src = text.strip()
        src = re.sub(r",\s*([}\]])", r"\1", src)

        repaired_chars: list[str] = []
        in_string = False
        escaped = False

        for i, ch in enumerate(src):
            if in_string:
                if escaped:
                    repaired_chars.append(ch)
                    escaped = False
                    continue

                if ch == "\\":
                    repaired_chars.append(ch)
                    escaped = True
                    continue

                if ch == '"':
                    next_non_space = None
                    for j in range(i + 1, len(src)):
                        if not src[j].isspace():
                            next_non_space = src[j]
                            break

                    # If next token is not a valid string terminator context, treat quote as unescaped content.
                    if next_non_space in (None, ":", ",", "}", "]"):
                        in_string = False
                        repaired_chars.append(ch)
                    else:
                        repaired_chars.append('\\"')
                    continue

                if ch == "\n":
                    repaired_chars.append("\\n")
                    continue
                if ch == "\r":
                    repaired_chars.append("\\r")
                    continue
                if ch == "\t":
                    repaired_chars.append("\\t")
                    continue
                if ord(ch) < 0x20:
                    repaired_chars.append(f"\\u{ord(ch):04x}")
                    continue

                repaired_chars.append(ch)
                continue

            if ch == '"':
                in_string = True
            repaired_chars.append(ch)

        if in_string:
            repaired_chars.append('"')

        repaired = "".join(repaired_chars)
        return re.sub(r",\s*([}\]])", r"\1", repaired)

    @staticmethod
    def read_file_bytes(file_content: Union[bytes, UploadedFile]) -> tuple[bytes, str]:
        """
        Read file bytes from various input types.

        Args:
            file_content: File bytes or Django UploadedFile

        Returns:
            Tuple of (file_bytes, filename)
        """
        if isinstance(file_content, UploadedFile):
            file_content.seek(0)
            file_bytes = file_content.read()
            filename = file_content.name or ""
        else:
            file_bytes = file_content
            filename = ""

        return file_bytes, filename

    @staticmethod
    def encode_image_base64(image_bytes: bytes) -> str:
        """
        Encode image bytes to base64 string.

        Args:
            image_bytes: Raw image bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def get_mime_type(filename: str, default: str = "image/jpeg") -> str:
        """
        Get MIME type from filename extension.

        Args:
            filename: Filename with extension
            default: Default MIME type if extension not recognized

        Returns:
            MIME type string
        """
        if not filename:
            return default

        ext = Path(filename).suffix.lower().lstrip(".")

        mime_types = {
            # Images
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            # Documents
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

        return mime_types.get(ext, default)

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """
        Get file extension from filename.

        Args:
            filename: Filename with extension

        Returns:
            Lowercase extension without dot
        """
        if not filename:
            return ""
        return Path(filename).suffix.lower().lstrip(".")

    def build_vision_message(
        self,
        prompt: str,
        image_bytes: bytes,
        filename: str = "",
        system_prompt: Optional[str] = None,
    ) -> list:
        """
        Build messages list for vision API request.

        Args:
            prompt: User prompt text
            image_bytes: Image bytes to analyze
            filename: Optional filename for MIME type detection
            system_prompt: Optional system prompt

        Returns:
            List of message dicts for API request
        """
        base64_image = self.encode_image_base64(image_bytes)
        mime_type = self.get_mime_type(filename)

        messages = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{base64_image}"},
                    },
                ],
            }
        )

        return messages
