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
python3 -m compileall pipeline.py interpret.py enrich.py check_env.py json_reduction
```

### Inference commands (basic running of the pipeline)
```bash
python3 pipeline.py --input data/multiqc_data.json --model gemma4 --num_ctx 16384
```

### Run only the json reduction step (for debugging)
```bash
python3 json_reduction/main.py
```

### Run the enrichment with ToolUniverse (experimental, optional)
```bash
python3 enrich.py --input data/annotated_report.json
```

There is no dedicated unit-test runner or lint configuration in this repository. CI currently installs dependencies, runs `python3 -m compileall ...`, and runs `python3 check_env.py` in informational mode. For targeted validation, run the smallest relevant script directly rather than looking for a nonexistent single-test selector.

## High-level architecture

- `pipeline.py` is the main non-interactive entrypoint. It resolves the input JSON, extracts the raw MultiQC payload, saves the reduced JSON into `data/`, merges descriptor metadata into an annotated report, and then calls the local Ollama-based interpretation step.
- `json_reduction/` is the preprocessing layer:
  - `json_clean.py` extracts `report_saved_raw_data` / `report_raw_saved_data` and strips noisy sample-sheet keys.
  - `json_merger.py` overlays `descriptor_schema.json` onto each section and rewrites raw `multiqc_spatial_neighbors*` sections into one `multiqc_spatial_neighbors` parent with numbered child sections plus recovered `focal_cell_type` labels.
  - `json_load.py` resolves relative paths against the current working directory first, then `data/`.
  - `main.py` is the older interactive reduction/annotation flow; `pipeline.py` is the automation-oriented entrypoint.
- `interpret.py` builds the actual LLM prompts and talks to Ollama locally. In the default mode it analyzes each data-bearing section separately, injects shared sample-sheet and glossary context, adds derived percentages for cell-type count sections, computes responder/non-responder summary statistics for small numeric sample-keyed sections, and optionally performs a final synthesis pass.
- `enrich.py` is optional prompt enrichment. It extracts genes, cell types, and ligand-receptor pairs from the annotated report, queries ToolUniverse when available, caches successful lookups in `data/enrichment_cache.json`, and returns a markdown reference block appended to the interpretation system prompt.
- `check_env.py` is the environment doctor used both locally and by CI-style validation. It checks Python, the Ollama Python client, the local Ollama service, locally pulled models, optional ToolUniverse availability, the descriptor schema, and write access to `data/`.

## Key conventions

- Keep inference local-first. The repository is built around a locally running Ollama service, and the README explicitly treats interpretation as an on-device workflow.
- Preserve the `data/`-centric workflow. New scripts should follow the existing path-resolution and default-output behavior instead of inventing separate output locations.
- Optional context providers are fail-soft. Both glossary lookup and ToolUniverse enrichment warn and continue when unavailable; do not turn those paths into hard failures unless the feature is explicitly required.
- Preserve the annotated report shape expected by `interpret.py`: each analysis section is a dict containing descriptor metadata plus a `data` payload, and the sample sheet stays under `multiqc_samplesheet`.
- The sample-sheet response label may appear as `responce` or `response`; existing code intentionally supports both spellings.
- Spatial-neighbor handling is coupled across files: `json_merger.py` renumbers sections and injects `focal_cell_type`, while `interpret.py` and `enrich.py` consume that normalized structure. Keep those pieces in sync when changing neighborhood logic.
- Interpretation prompts are intentionally conservative: they emphasize numeric evidence, markdown-only output, and avoiding overstated group-level claims. Keep prompt changes aligned with that style in both per-section and synthesis flows.
- CI does not have a usable Ollama inference environment. Keep CI-safe checks limited to dependency installation, syntax/compile validation, and non-failing environment diagnostics unless the workflow is intentionally expanded.
