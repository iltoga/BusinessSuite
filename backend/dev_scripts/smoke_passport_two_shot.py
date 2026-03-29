"""
FILE_ROLE: Standalone development script for manual backend diagnostics.

KEY_COMPONENTS:
- main: Script entrypoint.

INTERACTIONS:
- Depends on: dev_scripts._bootstrap and the passport/OCR API flows exercised by the script.

AI_GUIDELINES:
- Keep the script focused on local diagnostics and avoid production application logic.
- Preserve the manual request/response flow because it is used for ad hoc backend checks.
"""

from __future__ import annotations

from _bootstrap import BACKEND_ROOT, bootstrap_django, output_path


def main() -> None:
    output_file = output_path("smoke_passport_two_shot.txt")
    with output_file.open("w") as f_out:
        try:
            bootstrap_django()

            from core.services.ai_passport_parser import AIPassportParser

            f_out.write("Django loaded.\n")

            parser = AIPassportParser(model="qwen/qwen3.5-flash-02-23", use_openrouter=True)
            f_out.write("Parser loaded.\n")

            with (BACKEND_ROOT / "tmp" / "passport.jpeg").open("rb") as f_img:
                img_data = f_img.read()

            f_out.write("Calling validate_passport_image_two_shot API...\n")
            res = parser.validate_passport_image_two_shot(img_data, "passport.jpeg")

            f_out.write(f"Success: {res.success}\n")
            f_out.write(f"Error: {res.error_message}\n")
        except Exception:
            import traceback

            f_out.write(traceback.format_exc())


if __name__ == "__main__":
    main()
