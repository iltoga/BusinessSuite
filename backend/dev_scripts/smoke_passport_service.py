"""
FILE_ROLE: Standalone development script for manual backend diagnostics.

KEY_COMPONENTS:
- main: Script entrypoint.

INTERACTIONS:
- Depends on: dev_scripts._bootstrap and passport service helpers.

AI_GUIDELINES:
- Keep the script focused on local diagnostics and avoid production application logic.
- Preserve the manual request/response flow because it is used for ad hoc backend checks.
"""

from __future__ import annotations

from _bootstrap import BACKEND_ROOT, bootstrap_django, output_path


def main() -> None:
    output_file = output_path("smoke_passport_service.txt")
    with output_file.open("w") as f_out:
        try:
            bootstrap_django()

            from core.services.passport_uploadability_service import PassportUploadabilityService

            f_out.write("Django loaded.\n")

            with (BACKEND_ROOT / "tmp" / "passport.jpeg").open("rb") as f_img:
                img_data = f_img.read()

            f_out.write("Running service...\n")
            service = PassportUploadabilityService()
            res = service.check_passport(img_data, method="hybrid")

            f_out.write(f"Success: {res.is_valid}\n")
            f_out.write(f"Method: {res.method_used}\n")
        except Exception:
            import traceback

            f_out.write(traceback.format_exc())


if __name__ == "__main__":
    main()
