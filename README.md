# llmize

Reduce, annotate, and interpret MultiQC spatial-transcriptomics reports with a
local LLM (via Ollama), optionally grounded with biomedical context from ToolUniverse.

Interpretation runs **entirely on your own machine** — the model and inference are
local, and nothing is sent to any external service.

## Setup

### 1. Prerequisites
- **Ollama (runs locally).** Install it from https://ollama.com/download
  (or `brew install ollama` on macOS). For a headless/CLI setup, start 
  it once with `ollama serve`.
  Then download a model **once** (this single step needs internet):
  ```bash
  ollama pull gemma4
  ```

### 2. Install Python dependencies
```bash
cd llmize
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

This installs `ollama` plus the optional enrich stack
(`tooluniverse`, `PyYAML`). Enrich is optional, the pipeline can run without
it but enrich gives more context.

### 3. Run the pipeline
```bash
python3 pipeline.py --input data/multiqc_data.json --model gemma4 --num_ctx 16384
```
Add `--enrich` to annotate genes via ToolUniverse, or `--whole-report` to interpret
the report in a single call instead of section by section.
If you pulled a model under a different name, pass it with `--model <name>`. A bare
name like `--model gemma4` will also resolve `gemma4:latest` automatically.


### 4. Verify your setup

Before running the pipeline, run the checks to confirm everything is in
place, Python version, the `ollama` client, the **local Ollama service running**, at
least one pulled model, optional ToolUniverse, and the descriptor schema:

```bash
python3 check_env.py
# or, equivalently:
python3 pipeline.py --check
```

It prints a clear ✓/⚠/✗ report and exits non-zero if a required check fails.
Optional features (e.g. ToolUniverse enrichment) only produce warnings, not failures.

## Continuous integration

The GitHub Actions workflow (`.github/workflows/test.yml`) runs on every pull request
to `main`. Because CI runners have no Ollama server, the required checks are limited to installing
dependencies across Python 3.9 / 3.11 / 3.12.

## Quick json_reduction Tutorial

This project processes JSON data and generates annotated reports with metadata. Follow these steps to run it:

### Prerequisites
- Your JSON data file (Or use already existing multiqc_data.json from data folder)

### Step-by-Step Instructions

1. **Place your JSON file in the data folder**

2. **Navigate to the json_reduction directory**
   ```bash
   cd llmize/json_reduction
   ```

3. **Run the main script**
   ```bash
   python3 main.py
   ```

4. **Follow the prompts**
   - When asked for the JSON filename, enter the name of your file (e.g., `multiqc_data.json`)
   - When asked for the extracted output filename, press Enter to use the default or type a custom name
   - When asked for the annotated report filename, press Enter to use the default or type a custom name
   - The script will create an annotated and broken-down version of your json

### One-step automated pipeline

You can run the entire JSON -> extracted JSON -> annotated report -> Ollama interpretation flow with a single command:

```bash
cd llmize
python3 pipeline.py --input data/multiqc_data.json --model gemma4
```

This will create:
- `data/extracted_multiqc_data.json`
- `data/annotated_report.json`
- `data/multiqc_data_interpretation_<timestamp>.md`

#### Section-by-section interpretation (default)

By default the interpretation runs **one Ollama call per major section** (`multiqc_squidpy_ligrec_interactions` and other sections are analyzed on its own), each grounded in its
descriptor metadata. The sample sheet (responder / non-responder labels) is folded
into the system prompt so it is shared context for every section. `multiqc_spatial_neighbors`
is sent as a single call carrying all of its focal cell types, so it works for any
number of focal types — not just the 6 in the example. The section responses are then
combined into one markdown report.

Use `--whole-report` to revert to a single call over the entire report.

#### Optional biological enrichment (ToolUniverse)

Add `--enrich` to look up gene annotations via
[ToolUniverse](https://github.com/mims-harvard/ToolUniverse) and prepend them to the
system prompt, giving the model grounding for genes like `CXCL14` / `MIF`:

```bash
pip install tooluniverse
python3 pipeline.py --input data/multiqc_data.json --model gemma4 --enrich
```

If `tooluniverse` is not installed or a lookup fails, the
pipeline continues without it. Successful lookups are cached in `data/enrichment_cache.json`.
You can also inspect what gets extracted without running Ollama:

```bash
python3 enrich.py --input data/annotated_report.json
```

### Troubleshooting

**File not found:**
- Ensure your JSON file is in the `llmize/data/` folder

**Schema not found:**
- Make sure `descriptor_schema.json` is in the `json_reduction/` folder

**JSON parsing error:**
- Verify your input JSON file is valid
