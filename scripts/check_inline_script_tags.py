#!/usr/bin/env python3
"""
Scan templates for inline <script> tags without a src attribute.
Exit code: 0 if none found, 1 if any inline script tags are present.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
pattern = re.compile(r'<script(?![^>]*src=)(?![^>]*type=(?:"|\')application/json(?:"|\'))[^>]*>', re.IGNORECASE)


def scan_templates(root: Path):
    matches = []
    for p in root.rglob("templates/**/*.html"):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in pattern.finditer(txt):
            # Expose the line where the tag occurs
            line_no = txt.count("\n", 0, m.start()) + 1
            snippet = txt[m.start() : m.end() + 100].split("\n")[0]
            matches.append((str(p), line_no, snippet.strip()))
    return matches


def main():
    matches = scan_templates(ROOT)
    if not matches:
        print("No inline script tags found in templates.")
        return 0
    print("Found inline script tags in templates:")
    for path, line, snippet in matches:
        print(f"- {path}:{line} -> {snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
