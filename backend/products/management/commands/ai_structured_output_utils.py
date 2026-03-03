import json
import re

from products.models.document_type import DocumentType

# Helper function to generate JSON-serializable structured output.
# It analyses the validation_rule_ai_positive field and uses the document's name
# and description to craft a list of fields that the AI should extract.
#
# The algorithm is intentionally heuristic and best-effort: it looks for common
# indicator phrases such as "Look for:", "Required visible elements:", etc. It
# then splits the captured text into individual field descriptions using commas,
# conjunctions, semicolons, newlines and bullet dashes. If nothing can be found,
# it falls back to using the document name and description themselves.
#
# Returned value is a Python list of dicts with keys "field_name" and
# "description"; callers may ``json.dumps`` the result for storage.


def generate_ai_structured_output(document_type: DocumentType) -> list:
    """Return a list of field definitions derived from the document type.

    ``document_type`` is expected to be an instance of
    ``products.models.document_type.DocumentType``. The returned list may be
    empty if no clues could be extracted.
    """

    text = document_type.validation_rule_ai_positive or ""
    # we also include name/description for context when building field
    # descriptions later (not for parsing itself)

    # common prefixes that introduce a list of visible elements.
    patterns = [
        r"Look for:(.*)",
        r"Required visible elements:(.*)",
        r"Required signals:(.*)",
        r"Expect(?:ed)?:?(.*)",
        r"Analyze the document to confirm.*?\.(.*)",
    ]

    fields = []

    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if match:
            segment = match.group(1)
            # split into potential field strings
            for part in re.split(r",| and |;|\n|-", segment):
                part = part.strip()
                # ignore obvious throwaway words
                if not part or part.lower() in ("the document", "this", "a valid"):
                    continue
                # strip trailing periods
                if part.endswith("."):
                    part = part[:-1]
                fields.append(part)
    # if we didn't find anything, fall back to name/description
    if not fields:
        if document_type.name:
            fields.append(document_type.name)
        if document_type.description:
            fields.append(document_type.description)

    # build normalized output list
    output = []
    for phrase in fields:
        # safety check
        if not phrase:
            continue
        description = phrase
        if document_type.description:
            description = f"{document_type.description}. {phrase}"
        # convert phrase to snake_case-like field_name
        field_name = re.sub(r"[^0-9a-zA-Z]+", "_", phrase.lower()).strip("_")
        output.append({"field_name": field_name, "description": description})
    return output


# helper for pretty printing; not exported


def format_output(output: list) -> str:
    return json.dumps(output, indent=2, ensure_ascii=False)
