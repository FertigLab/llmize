# llmize

Interpret bioinformatics analysis/QC reports with a local LLM (via Ollama) — as JSON
 (section-keyed) or plain text/markdown reports. MultiQC is supported: its `*_data.json`
 exports and its `llms-full.txt` export both work out of the box. Any other section-keyed
 JSON or free text is interpreted generically.

Interpretation runs **entirely on your own machine** — the model and inference are
local, and nothing is sent to any external service.

There are two ways to run it:
- **Nextflow** — runs in a container with Ollama and Python deps
  already baked in; no local setup beyond Nextflow itself and a container engine.
- **Python** — useful for local development/debugging; needs a
  local Python environment and a locally running Ollama.

## Run with Nextflow

```bash
nextflow run main.nf --input data/multiqc_data.json
```

To steer the model with your own instruction, add `--prompt`:

```bash
nextflow run main.nf --input data/multiqc_data.json \
   --prompt "Summarize immune infiltration and flag any tumor-immune interactions."
```

By default this uses the `docker` profile (see `nextflow.config`), which pulls
`ghcr.io/fertiglab/llmize:latest` and boots Ollama inside the container — you
don't need Ollama or the Python dependencies installed on your host for this path.

### GPU (Slurm + Apptainer)

```bash
nextflow run main.nf \
   -profile <profile> \
   --input data.json \
   --slurm_account <your-account> \
   -w /usr/local/scratch/$USER/work \
   -resume
```

### Model cache

The Nextflow module uses an Ollama model cache directory via `OLLAMA_MODELS`.

- By default, the workflow uses a task-local cache at `$PWD/ollama/models` (inside the Nextflow work directory).
- To reuse models across runs (recommended on clusters), pass `--ollama_models_dir /path/to/persistent/models` so the container can bind-mount that directory.
- On the first run with an empty cache, the workflow auto-pulls the model; subsequent runs reuse the cached model when using a persistent `--ollama_models_dir`.

```bash
nextflow run main.nf \
   -profile <profile> \
   --input data/multiqc_data.json \
   --slurm_account <your-account> \
   --ollama_models_dir /path/to/persistent/models \
   -w /usr/local/scratch/$USER/work \
   -resume
```

### Native profile (no container)

`-profile native` runs `llmize.py` directly on the host instead of in a
container, so it needs the same local setup as "Run directly with Python" below
(Ollama installed and running, Python dependencies installed). Useful on Macs where
 Docker does not have access to GPU.

## Run directly with Python

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

### 3. Verify your setup

Confirm everything is in place — Python version, the `ollama` client, the
**local Ollama service running**, at least one pulled model, and the descriptor
schema:

```bash
python3 llmize.py --check
```

It prints a clear ✓/⚠/✗ report and exits non-zero if a required check fails.

### 4. Run it

```bash
python3 llmize.py --input multiqc_data.json --model gemma4
```

Common flags (see `python3 llmize.py --help` for the full list):

```bash
python3 llmize.py --input data.json \
   --prompt "Summarize immune infiltration and flag any tumor-immune interactions." \
   --review --output my_interpretation.md
```

Note that `llmize.py`'s own flags use hyphens and differ slightly from the
Nextflow parameter names below (e.g. `--whole-report`/`--no-synthesis` instead
of `--whole_report`/`--synthesis false`).

## JSON input

`llmize.py` accepts JSON reports with section-keyed data, such as MultiQC's `*_data.json` exports. The JSON is processed through the normal reduce/annotate/interpret pipeline, with MultiQC-specific enhancements applied automatically when relevant sections are detected.

When using JSON input, each key may be described in a separate descriptor file, which provides metadata and instructions for how that section should be interpreted (see `ingest/descriptor_schema.json`).


## Plain-text input

`llmize.py` also accepts plain text inputs — for example MultiQC's
`llms-full.txt` export, or any other free-text report. The mode is chosen purely
by file extension: `.json` goes through the reduce/annotate/interpret
pipeline; anything else (`.txt`, `.md`, no extension, ...) is treated as plain text and bypasses JSON extraction/annotation entirely (so
`--descriptor`, `--extracted-output`, `--annotated-output`, `--save-intermediates`,
and `--review` don't apply and are ignored, with a warning for the latter two).

```bash
python3 llmize.py --input llms-full.txt --model gemma4
```

By default (not `--whole-report`), the text is split into chunks and each is
interpreted separately before a final synthesis pass, same as JSON's
section-by-section mode:
- If the text has markdown headings (`#` .. `######`), each heading becomes a chunk.
- MultiQC's real `llms-full.txt` layout is auto-detected and split one chunk per `Tool:` 
block, with the matching description from the report's tool index attached automatically.
- If a chunk looks like a sample sheet (a table named "Sample Sheet"/"samplesheet"),
  it's pulled out of the individual chunk list and kept as shared context instead —
  its content, and any metadata column that usefully groups samples (e.g.
  responder/non-responder), is carried into every other chunk's analysis and into
  the final synthesis.

## Just run my prompt

`--whole-report` sends the entire text as a single call with no chunking.

`--as-is` omits any system prompt and assumes analysis prompt is included, like default
MultiQC's llms output does.

When combined, sends the entire report to the model without any automatic chunking or system prompt, giving you full control over the input and instructions.

```bash
python3 llmize.py --input llms-full.txt --model gemma4 --as-is --whole-report
```

`--as-is` only affects the system prompt/style, not chunking — `--whole-report` still
works the same way with or without it. This flag is currently `llmize.py`-only and
not yet exposed as a Nextflow parameter.

## Parameters

Parameters are passed on the Nextflow command line as `--<param> <value>`. Booleans
are set explicitly, e.g. `--think false` or `--review true`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — (required) | Path to a report file: JSON (MultiQC's `*_data.json`, or any section-keyed JSON) or plain text (e.g. MultiQC's `llms-full.txt`); mode is auto-detected by file extension. See [Plain-text input](#plain-text-input). |
| `--descriptor` | bundled schema | Descriptor schema JSON (JSON mode only), keyed by top-level section name; overlaid onto matching sections to tell the model what each field means. Copy `ingest/descriptor_schema.json` and edit it to describe your own report's sections, then pass the copy here. Sections with no matching entry pass through unannotated. |
| `--model` | `gemma4` | Ollama model name. |
| `--output` | (none) | Path to the output file; if not specified, defaults to `<input_stem>_interpretation_<timestamp>.md` in the current directory. |
| `--prompt` | (none) | Extra instruction appended to the model prompt. |
| `--num_ctx` | `32768` | Context window size. |
| `--temperature` | model default | Sampling temperature (`0` = deterministic). |
| `--top_p` | model default | Nucleus-sampling threshold. |
| `--top_k` | model default | Top-k sampling. |
| `--seed` | model default | RNG seed for reproducible output. |
| `--num_predict` | model default | Maximum number of tokens to generate. |
| `--think` | `true` | Model thinking mode; `--think false` disables it (faster). |
| `--whole_report` | `false` | Interpret the whole report in one call instead of section-by-section. |
| `--synthesis` | `true` | Produce the final executive-summary pass; `--synthesis false` skips it. |
| `--review` | `false` | Self-review pass flagging gene/cell-type names absent from the report. |
| `--review_passes` | `2` | Maximum review passes (used with `--review true`). |

