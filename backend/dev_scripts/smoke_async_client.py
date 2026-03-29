"""
FILE_ROLE: Standalone development script for manual backend diagnostics.

KEY_COMPONENTS:
- main: Script entrypoint.

INTERACTIONS:
- Depends on: dev_scripts._bootstrap and asynchronous client smoke-test flows.

AI_GUIDELINES:
- Keep the script focused on local diagnostics and avoid production application logic.
- Preserve the manual request/response flow because it is used for ad hoc backend checks.
"""

from __future__ import annotations

from _bootstrap import bootstrap_django


def main() -> None:
    bootstrap_django()

    from django.test import AsyncClient

    client = AsyncClient()
    print("AsyncClient available in Django test framework")
    print(f"Client type: {type(client).__name__}")


if __name__ == "__main__":
    main()
