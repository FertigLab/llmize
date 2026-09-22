# Plan: Plain-text report input (MultiQC llms-full.txt support)

## Decisions (confirmed with user)
- Detection: by file extension only. `.json` -> existing JSON pipeline. Anything else
  (`.txt`, `.md`, no extension) -> new text pipeline. No new CLI flag needed for mode
  selection.
- Chunking: respects existing `--whole-report` flag.
  - Not whole-report (default): split text into sections on markdown headings
    (`#`..`######`), interpret each section separately, then synthesize (same shape as
    JSON section-by-section mode).
  - `--whole-report`: treat entire text as a single blob, one interpretation call.
- Descriptor/annotation (descriptor_schema.json, MultiQC-specific merges): NOT applied
  to text mode. Skipped entirely.
- Sample grouping (samplesheet-derived group stats/percentages): NOT applied to text
  mode. Skipped entirely — generic summarization only.
- Output structure: mirrors JSON mode (per-section markdown + optional synthesis
  executive summary), using the same `combine_responses` shape but a generic title
  (not "MultiQC Spatial Transcriptomics Interpretation").
- `--as-is` flag (text mode only): when set, the system prompt drops `STYLE_GUIDE` and
  `EVIDENCE_RULES` entirely, on the assumption that the input text already carries its
  own analysis instructions (this is literally what MultiQC's `llms-full.txt` is for).
  It does NOT change chunking — `--whole-report` vs. heading-split chunks still apply
  the same way with `--as-is` on or off. Silently ignored when input is `.json`.
- `--review`: unavailable in text mode (verify.py's deterministic_findings/extract_entities
  assume a JSON report dict of genes/cell types). If `--review` is passed with a
  non-JSON input, print a warning and skip review (do not error).
- `--save-intermediates`: no-op in text mode (nothing to extract/annotate). Print a
  warning and ignore if passed.
- Other JSON-only flags (`--descriptor`, `--extracted-output`, `--annotated-output`):
  silently ignored in text mode (no warning needed).
- Oversized whole-report text exceeding num_ctx: no special handling/guard; let Ollama
  behave as it normally would (truncate/error). Out of scope.
- Add unittest coverage for the new text-splitting function (header splitting, preamble
  capture, duplicate-heading suffixing, no-heading fallback to a single "Full report"
  section, empty-input edge case).

## Steps

1. `ingest/io_utils.py`: add `read_text(filepath) -> str` (plain UTF-8 read), alongside
   existing `load_json`.
2. New `ingest/text_ingest.py`: add `split_text_sections(text) -> dict` that:
   - Regex-matches markdown headings (`^#{1,6}\s+(.+)$`) line by line.
   - Content before the first heading becomes a `"Preamble"` section if non-blank.
   - Each heading's body becomes `{heading_text: {"data": body}}`; duplicate heading
     names get a `" (2)"`, `" (3)"`, ... suffix.
   - If no headings found at all, returns `{"Full report": {"data": text.strip()}}`
     (or `{}` if text is blank).
3. `ingest/__init__.py`: export `read_text` and `split_text_sections`.
4. `interpret.py` changes (*depends on 1-3*):
   - Add `TEXT_SYSTEM_PROMPT` (reuses `STYLE_GUIDE` + `EVIDENCE_RULES`, but describes a
     schema-less plain-text report instead of JSON sections/descriptors/samplesheet).
   - Add `TEXT_AS_IS_SYSTEM_PROMPT`, a minimal variant with no `STYLE_GUIDE` /
     `EVIDENCE_RULES` appended — just a short framing sentence noting the text carries
     its own instructions to follow. Used only when `--as-is` is set.
   - Add `build_prompt_text(text)` (whole-report text prompt) and
     `build_text_section_prompt(section_name, body)` (per-section text prompt) —
     analogous to existing `build_prompt`/`build_section_prompt` but without JSON
     fencing, descriptors, percentages, or group stats.
   - Refactor the model-calling loop out of `interpret_report` into a shared
     `_run_chunks(chunks, model, system, num_ctx, synthesize_final, think, gen_options,
     samplesheet_context="", title=None)` helper (same logic currently inlined in
     `interpret_report`, just parametrized with `title` passed through to
     `combine_responses`).
   - `combine_responses` gains a `title: str = None` param (defaults to current hardcoded
     MultiQC title) so text mode can pass "Report Interpretation".
   - Add `interpret_text_report(text, model, num_ctx=32768, whole_report=False,
     synthesize_final=True, think=True, gen_options=None, user_instruction="",
     as_is=False) -> str`: builds chunks via `split_text_sections` (or a single
     whole-report chunk) exactly as before regardless of `as_is`; picks
     `TEXT_AS_IS_SYSTEM_PROMPT` when `as_is` else `TEXT_SYSTEM_PROMPT`; calls
     `_run_chunks`.
5. `llmize.py` changes (*depends on 4*):
   - Add `is_json_input(path)` helper (extension check, case-insensitive `.json`).
   - In `main()`, resolve the input path once, branch: `.json` -> existing `run_pipeline`
     (unchanged); else -> new `run_text_pipeline(...)`.
   - Add `--as-is` argparse flag (`store_true`) with help text explaining it drops the
     style guide/evidence rules for plain-text input, assuming the text already embeds
     its own instructions (e.g. MultiQC's `llms-full.txt`).
   - New `run_text_pipeline(input_path, model, output_path, num_ctx, whole_report,
     synthesize_final, think, gen_options, user_instruction, as_is)`: reads text via
     `read_text`, calls `interpret_text_report(..., as_is=as_is)`, builds default output
     filename the same way as `run_pipeline` (timestamped, based on input stem), builds
     the footer via the existing `build_run_footer` with `mode="text whole-report"` or
     `"text section-by-section"` (plus an `as-is` note when set), saves via existing
     `save_text`.
   - In `main()`, if `.txt`-mode is selected and `args.review` is set, print a warning
     and skip review; if `args.save_intermediates` is set, print a warning and ignore.
     `--descriptor`/`--extracted-output`/`--annotated-output` are simply unused in this
     branch (no warning).
6. `tests/test_ingest.py` (*depends on 2*): add tests for `split_text_sections` covering
   heading splitting, preamble capture, duplicate-heading suffixing, no-heading
   fallback, and empty input.

## Addendum: special-case chunker for MultiQC's `llms-full.txt` layout

Real `llms-full.txt` exports don't use markdown headings at all, so the generic
`split_text_sections` falls back to one giant "Full report" chunk. The actual layout is:

```
<free-form instructions for MultiQC's own LLM-summary tool>
----------------------
Tools used in the report:

1. Sample Sheet
Description: <p>...</p>
----------------------
2. Atlas Summary
Description: <p>...</p>
----------------------
... (one numbered index entry per tool)
----------------------
----------------------
Tool: Sample Sheet
Section: 
Title: Sample Sheet

Plot type: violin plot
...
|table|...|
----------------------
Tool: Atlas Summary
Section: 
Title: Atlas Summary
...
----------------------
... (one block per tool, this is the actual data)
```

### Decisions
- Detection: sniff for this layout using structural markers rather than filename —
  looks_like_multiqc_llms_full(text) returns True when the text contains the
  `Tool:` / `Section:` / `Title:` line triad together with `----------------------`
  separator lines (e.g. at least one regex match of
  `^Tool: .+\nSection: .*\nTitle: .+$` in MULTILINE mode). This is checked before
  falling back to the generic markdown-heading splitter.
- Chunk granularity: one chunk per `Tool: X` block. `Section:` is blank in every
  observed sample, so `Tool` name alone is used as the chunk name; if a future file has
  a non-blank `Section:`, append it (`"X — Section"`) and still run duplicate-name
  suffixing (reusing the same dedup helper as `split_text_sections`).
- Numbered tool-description index (`N. Tool Name` / `Description: <p>...</p>` blocks
  before the data): parsed into a `{tool_name: description}` map and attached as extra
  context to the matching `Tool: X` chunk (HTML-stripped plain text), mirroring how
  `descriptor_schema.json` enriches JSON sections. Exact-string match on tool name;
  fail-soft (no match -> chunk gets no extra description, same as an unmatched section
  in the JSON pipeline today). The index itself is not turned into its own chunk.
- Leading free-form instructions block (before the tools index): dropped by default.
  When `--as-is` is set AND this special-case layout is detected, this block is used
  verbatim as the system prompt instead of `TEXT_AS_IS_SYSTEM_PROMPT` (it already tells
  the model exactly how MultiQC wants its output formatted — bullet count, markdown
  directives, etc.). Otherwise (no `--as-is`), it is discarded and `TEXT_SYSTEM_PROMPT`
  (or `TEXT_AS_IS_SYSTEM_PROMPT`, if `--as-is` but a different plain-text file that
  doesn't match this layout) is used as normal.
- `--whole-report` interaction: no special-casing. `--whole-report` still sends the
  full raw text as a single call regardless of this detection; detection only changes
  the per-section chunking path.

### New pieces
- `ingest/text_ingest.py`:
  - `looks_like_multiqc_llms_full(text) -> bool` — structural sniff described above.
  - `split_multiqc_llms_full(text) -> tuple[dict, str]` — returns
    `({chunk_name: {"data": body}}, leading_instructions_text)`. Parses the tool
    description index first (building the `{tool_name: description}` map), then splits
    the rest on `----------------------` separators, keeping only blocks that start with
    `Tool: `, prepending the matched description (if any) to that block's body.
- `interpret.py` / `interpret_text_report`: when building chunks (non-whole-report
  path), try `looks_like_multiqc_llms_full` first; if it matches, use
  `split_multiqc_llms_full` instead of `split_text_sections`, and — only when
  `as_is=True` — use the returned leading instructions text as the system prompt in
  place of `TEXT_AS_IS_SYSTEM_PROMPT`.
- `tests/test_ingest.py`: new tests for `split_multiqc_llms_full` using a small
  synthetic snippet in this exact layout (index + 2-3 `Tool:` blocks, one with a
  matching description, one without), plus a `looks_like_multiqc_llms_full` positive/
  negative case.

## Relevant files
- `ingest/io_utils.py` — add `read_text`.
- `ingest/text_ingest.py` (new) — `split_text_sections`, `looks_like_multiqc_llms_full`,
  `split_multiqc_llms_full`.
- `ingest/__init__.py` — export additions.
- `interpret.py` — `TEXT_SYSTEM_PROMPT`, `TEXT_AS_IS_SYSTEM_PROMPT`, `build_prompt_text`,
  `build_text_section_prompt`, `_run_chunks` refactor, `interpret_text_report(..., as_is)`
  (now also dispatching to the MultiQC-specific splitter when detected),
  `combine_responses(title=...)`.
- `llmize.py` — `is_json_input`, `--as-is` flag, `run_text_pipeline`, dispatch in
  `main()`, warnings for `--review`/`--save-intermediates` in text mode.
- `tests/test_ingest.py` — tests for `split_text_sections` and the new
  `split_multiqc_llms_full`/`looks_like_multiqc_llms_full`.

## Verification
1. `python3 -m compileall llmize.py interpret.py check_env.py ingest`
2. `python3 -m unittest discover tests` (new split_text_sections tests pass)
3. Manual: run `python3 llmize.py --input some_report.txt --model gemma4 --num_ctx 16384`
   against a sample MultiQC `llms-full.txt`-style file and confirm per-section +
   synthesis output; repeat with `--whole-report`.
4. Manual: confirm `.json` inputs still go through the unchanged JSON pipeline
   (no regression).
5. Manual: run against `data/llms-full.txt` (default section-by-section mode) and
   confirm chunks are now one-per-`Tool:` block instead of a single "Full report"
   blob; check descriptions are attached where the index has a matching entry.
6. Manual: run `data/llms-full.txt` with `--as-is` and confirm the leading
   instructions block is used as the system prompt.

