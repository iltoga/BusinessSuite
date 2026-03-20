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
