"""Splitting of arbitrary text reports (e.g. MultiQC's llms-full.txt) into sections.

Independent of the JSON extract/annotate pipeline: no descriptor overlay, no
MultiQC-specific merging. Sections are keyed by markdown heading text and each
holds a plain-text `data` string, so they can be iterated the same way as the
JSON pipeline's section dicts.
"""

import html
import re

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _add_unique(result: dict, name: str, body: str) -> None:
    """Insert body under name into result, suffixing " (2)", " (3)", ... on collision."""
    unique_name = name
    suffix = 2
    while unique_name in result:
        unique_name = f"{name} ({suffix})"
        suffix += 1
    result[unique_name] = {"data": body}


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
    preamble = "\n".join(preamble_lines).strip()
    if preamble:
        _add_unique(result, "Preamble", preamble)
    for name, body in sections:
        _add_unique(result, name, body)
    return result


_SEPARATOR_RE = re.compile(r"(?m)^-{10,}\s*$")
_TOOL_BLOCK_RE = re.compile(r"(?m)^Tool:\s*(.+)$")
_SECTION_LINE_RE = re.compile(r"(?m)^Section:[ \t]*(.*)$")
_INDEX_ENTRY_RE = re.compile(r"^\d+\.\s+(.+?)\s*\nDescription:\s*(.*)", re.MULTILINE | re.DOTALL)


def looks_like_multiqc_llms_full(text: str) -> bool:
    """Sniff for MultiQC's real llms-full.txt layout: 'Tool:'/'Section:'/'Title:' blocks."""
    return bool(re.search(r"(?m)^Tool: .+\nSection: .*\nTitle: .+$", text))


def _clean_description(raw: str) -> str:
    """Strip HTML tags/entities from a MultiQC tool Description value."""
    return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def split_multiqc_llms_full(text: str) -> tuple:
    """Split MultiQC's real llms-full.txt layout into per-Tool chunks.

    Returns ({chunk_name: {"data": body}}, leading_instructions_text). The leading
    instructions block is MultiQC's own prompt for its LLM-summary tool; the caller
    decides whether to use it (only relevant for --as-is). Each numbered index entry's
    Description is attached (best-effort, exact name match) to its matching Tool block.
    """
    blocks = [b.strip() for b in _SEPARATOR_RE.split(text)]
    blocks = [b for b in blocks if b]
    if not blocks:
        return {}, ""

    leading_instructions = blocks[0]
    descriptions = {}
    tool_blocks = []
    for block in blocks[1:]:
        match = _INDEX_ENTRY_RE.search(block)
        if match:
            descriptions[match.group(1).strip()] = _clean_description(match.group(2))
            continue
        if _TOOL_BLOCK_RE.match(block):
            tool_blocks.append(block)

    result = {}
    for block in tool_blocks:
        tool_name = _TOOL_BLOCK_RE.match(block).group(1).strip()
        section_match = _SECTION_LINE_RE.search(block)
        section_name = section_match.group(1).strip() if section_match else ""
        chunk_name = f"{tool_name} \u2014 {section_name}" if section_name else tool_name

        description = descriptions.get(tool_name)
        body = f"Description: {description}\n\n{block}" if description else block
        _add_unique(result, chunk_name, body)

    return result, leading_instructions


_TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")
_SAMPLESHEET_ALIASES = {"sample sheet", "samplesheet", "sample_sheet"}


def _split_row_cells(line: str) -> list:
    return [cell.strip() for cell in line.strip()[1:-1].split("|")]


def parse_markdown_table(text: str) -> dict:
    """Parse the first markdown table found in text into {first_col_value: {col: val}}.

    Scans for a header row, a '|---|---|...' separator row, then consecutive data
    rows; ignores any surrounding prose. Returns {} if no valid table (header +
    separator + at least one data row) is found.
    """
    lines = text.splitlines()
    for i in range(len(lines) - 1):
        header_match = _TABLE_ROW_RE.match(lines[i].strip())
        if not header_match:
            continue
        if not _TABLE_SEPARATOR_RE.match(lines[i + 1].strip()):
            continue
        header = _split_row_cells(lines[i])
        if len(header) < 2:
            continue

        rows = {}
        for line in lines[i + 2:]:
            row_match = _TABLE_ROW_RE.match(line.strip())
            if not row_match:
                break
            cells = _split_row_cells(line)
            row_id = cells[0]
            if not row_id:
                continue
            rows[row_id] = {
                col: cells[j] for j, col in enumerate(header[1:], start=1) if j < len(cells)
            }
        if rows:
            return rows
    return {}


def extract_samplesheet_chunk(sections: dict) -> tuple:
    """Pop a sample-sheet-like chunk out of sections, returning (remaining, parsed_dict).

    Matches a chunk name against a small alias set (case-insensitive, ignoring any
    " — <section>" suffix). If matched and its body parses into a table with at least
    two rows, the chunk is removed and the parsed {sample_id: {col: val}} dict is
    returned. Otherwise sections is returned unchanged with None (fail-soft).
    """
    for name, obj in sections.items():
        bare_name = name.split(" \u2014 ", 1)[0].strip().lower()
        if bare_name not in _SAMPLESHEET_ALIASES:
            continue
        parsed = parse_markdown_table(obj.get("data", ""))
        if len(parsed) >= 2:
            remaining = {k: v for k, v in sections.items() if k != name}
            return remaining, parsed
    return sections, None

