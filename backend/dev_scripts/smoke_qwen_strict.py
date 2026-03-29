"""
FILE_ROLE: Standalone development script for manual backend diagnostics.

KEY_COMPONENTS:
- main: Script entrypoint.

INTERACTIONS:
- Depends on: dev_scripts._bootstrap and AI passport-processing smoke-test flows.

AI_GUIDELINES:
- Keep the script focused on local diagnostics and avoid production application logic.
- Preserve the manual request/response flow because it is used for ad hoc backend checks.
"""

from __future__ import annotations

from _bootstrap import REPO_ROOT, bootstrap_django


def main() -> None:
    bootstrap_django()

    from core.services.ai_passport_parser import AIPassportParser

    parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)
    client = parser.ai_client

    with (REPO_ROOT / "business_suite" / "files" / "media" / "tmpfiles" / "passport_big.jpg").open("rb") as f:
        img_data = f.read()

    messages = client.build_vision_message(
        prompt="test",
        image_bytes=img_data,
        filename="test.jpg",
        system_prompt="test",
    )

    try:
        print("Testing chat_completion_json directly with extra_body...")
        client.chat_completion_json(
            messages=messages,
            json_schema=parser.PASSPORT_SCHEMA,
            schema_name="passport_data",
        )
        print("Success!")
    except Exception as e:
        print(f"FAILED: {type(e).__name__} - {e}")
        if hasattr(e, "error_code"):
            print("ErrorCode:", e.error_code)


if __name__ == "__main__":
    main()
