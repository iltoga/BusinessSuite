from __future__ import annotations

import logging
import sys

from _bootstrap import REPO_ROOT, bootstrap_django

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)


def main() -> None:
    bootstrap_django()

    from core.services.ai_passport_parser import AIPassportParser

    try:
        print("Testing parser...")
        parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)
        with (REPO_ROOT / "business_suite" / "files" / "media" / "tmpfiles" / "passport_big.jpg").open("rb") as f:
            img_data = f.read()

        print("Calling vision API...")
        res = parser._call_vision_api(img_data, "passport_big.jpg", parser._build_vision_prompt())
        print("RES SUCCESS:", res.success)
        print("RES ERROR:", res.error_message)
    except Exception as e:
        print("CAUGHT EXCEPTION:", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
