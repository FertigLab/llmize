# Copilot instructions for llmize

## Build, test, and validation commands

### Environment setup
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### Validation commands (CI-style checks)
```bash
python3 -m compileall llmize.py interpret.py check_env.py ingest
python3 -m unittest discover tests
```

### Inference commands (basic running of the pipeline)
```bash
python3 llmize.py --input data/multiqc_data.json --model gemma4 --num_ctx 16384
```

There is no lint configuration in this repository. CI currently installs dependencies, runs `python3 -m compileall ...`, `python3 -m unittest discover tests`, and runs `python3 check_env.py` in informational mode. `tests/` uses stdlib `unittest` (no extra dependency) and currently covers `ingest`'s extract/annotate MultiQC-unwrap and generic-JSON-passthrough behavior.

## High-level architecture

- `llmize.py` is the main non-interactive entrypoint. It resolves the input JSON, extracts a flat section-keyed payload (unwrapping MultiQC's raw-data key when present, else treating the input as already section-keyed), saves the reduced JSON into `data/` when requested, merges descriptor metadata into an annotated report, and then calls the local Ollama-based interpretation step.
- `ingest/` is the preprocessing layer, split by concern:
  - `io_utils.py` holds `resolve_path()` (relative paths resolve against the current working directory first, then `data/`), `load_json()`, and `save_json()` — plain file I/O, no report-format assumptions.
  - `extract.py`'s `extract_report_saved_raw_data()` unwraps `report_saved_raw_data` / `report_raw_saved_data` and strips noisy sample-sheet keys when present; otherwise it falls back to treating the whole input JSON as the flat section dict, so non-MultiQC JSON is supported too.
  - `annotate.py`'s `annotate()` overlays `descriptor_schema.json` onto each section (descriptor is optional; unmatched sections pass through with just their `data`) and rewrites raw `multiqc_spatial_neighbors*` sections into one `multiqc_spatial_neighbors` parent with numbered child sections plus recovered `focal_cell_type` labels — this MultiQC-specific merging is opportunistic and only triggers when those section names are present. `extract_focal_labels()` also lives here.
  - `__init__.py` re-exports the combined public API (`DATA_DIR`, `resolve_path`, `load_json`, `save_json`, `extract_report_saved_raw_data`, `extract_focal_labels`, `annotate`) so callers don't need to know the internal module split.
- `interpret.py` builds the actual LLM prompts and talks to Ollama locally. In the default mode it analyzes each data-bearing section separately, injects shared sample-sheet context, adds derived percentages for cell-type count sections, computes responder/non-responder summary statistics for small numeric sample-keyed sections, and optionally performs a final synthesis pass.
- `check_env.py` is the environment doctor used both locally and by CI-style validation. It checks Python, the Ollama Python client, the local Ollama service, locally pulled models, the (optional) descriptor schema, and write access to `data/`.

## Key conventions

- Keep inference local-first. The repository is built around a locally running Ollama service, and the README explicitly treats interpretation as an on-device workflow.
- Preserve the `data/`-centric workflow. New scripts should follow the existing path-resolution and default-output behavior instead of inventing separate output locations.
- Optional context providers are fail-soft. The descriptor schema is optional — missing it means sections pass through unannotated, not a crash.
- Preserve the annotated report shape expected by `interpret.py`: each analysis section is a dict containing descriptor metadata (when available) plus a `data` payload, and the sample sheet stays under `multiqc_samplesheet` when present.
- The sample-sheet response label may appear as `responce` or `response`; existing code intentionally supports both spellings.
- MultiQC-specific transforms (spatial-neighbors renumbering/merging, co-occurrence merging, focal-label recovery, cell-type percentage derivation, `verify.py`'s gene/cell-type/ligand-receptor extraction) are opportunistic: they trigger only when matching section names are present, and are no-ops on generic JSON that lacks them. Keep new MultiQC-specific logic in this same opportunistic, fail-soft style rather than making it a hard requirement.
- Interpretation prompts are intentionally conservative: they emphasize numeric evidence, markdown-only output, and avoiding overstated group-level claims. Keep prompt changes aligned with that style in both per-section and synthesis flows.
- CI does not have a usable Ollama inference environment. Keep CI-safe checks limited to dependency installation, syntax/compile validation, and non-failing environment diagnostics unless the workflow is intentionally expanded.
