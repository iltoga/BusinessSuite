"""
FILE_ROLE: Standalone development script for manual backend diagnostics.

KEY_COMPONENTS:
- main: Script entrypoint.

INTERACTIONS:
- Depends on: dev_scripts._bootstrap and Qwen passport smoke-test flows.

AI_GUIDELINES:
- Keep the script focused on local diagnostics and avoid production application logic.
- Preserve the manual request/response flow because it is used for ad hoc backend checks.
"""

from __future__ import annotations

from _bootstrap import REPO_ROOT, bootstrap_django


def main() -> None:
    bootstrap_django()

    from core.services.ai_passport_parser import AIPassportParser

    print("Testing AIPassportParser._call_vision_api with qwen/qwen3.5-flash-02-23")
    parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)

    with (REPO_ROOT / "business_suite" / "files" / "media" / "tmpfiles" / "passport_big.jpg").open("rb") as f:
        img_data = f.read()

    try:
        res = parser._call_vision_api(
            img_data,
            "passport_big.jpg",
            parser._build_vision_prompt(),
        )
        print("Success:", res.success)
        if res.success:
            print("Data:", res.passport_data)
        else:
            print("Error:", res.error_message)
    except Exception as e:
        print("Exception thrown:", type(e), e)


if __name__ == "__main__":
    main()
