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
