"""Splitting of arbitrary text reports (e.g. MultiQC's llms-full.txt) into sections.

Independent of the JSON extract/annotate pipeline: no descriptor overlay, no
MultiQC-specific merging. Sections are keyed by markdown heading text and each
holds a plain-text `data` string, so they can be iterated the same way as the
JSON pipeline's section dicts.
"""

import re

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def split_text_sections(text: str) -> dict:
    """Split text into {heading: {"data": body}} on markdown headings (# .. ######).

    Content before the first heading becomes a "Preamble" section (if non-blank).
    If no headings are found at all, the whole text is returned as one
    "Full report" section (or {} if the text is blank).
    """
    sections = []
    current_name = None
    current_lines = []
    preamble_lines = []

    def flush():
        if current_name is None:
            return
        sections.append((current_name, "\n".join(current_lines).strip()))

    for line in text.splitlines():
        match = _HEADER_RE.match(line)
        if match:
            if current_name is None:
                preamble_lines = current_lines
            else:
                flush()
            current_name = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()

    if not sections:
        stripped = text.strip()
        return {"Full report": {"data": stripped}} if stripped else {}

    result = {}

    def add_section(name: str, body: str):
        unique_name = name
        suffix = 2
        while unique_name in result:
            unique_name = f"{name} ({suffix})"
            suffix += 1
        result[unique_name] = {"data": body}

    preamble = "\n".join(preamble_lines).strip()
    if preamble:
        add_section("Preamble", preamble)
    for name, body in sections:
        add_section(name, body)
    return result
