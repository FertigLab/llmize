# llmize

Reduce, annotate, and interpret MultiQC spatial-transcriptomics reports with a
local LLM (via Ollama).

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

### 3. Verify your setup

Confirm everything is in place — Python version, the `ollama` client, the
**local Ollama service running**, at least one pulled model, and the descriptor
schema:

```bash
python3 check_env.py
# or, equivalently:
python3 pipeline.py --check
```

It prints a clear ✓/⚠/✗ report and exits non-zero if a required check fails.

## Run the pipeline

Run the interpretation with Nextflow. A simple run only needs the input report:

```bash
nextflow run main.nf --input data/multiqc_data.json
```

To steer the model with your own instruction, add `--prompt`:

```bash
nextflow run main.nf --input data/multiqc_data.json \
   --prompt "Summarize immune infiltration and flag any tumor-immune interactions."
```

## Nextflow execution

The Nextflow module uses an Ollama model cache directory via `OLLAMA_MODELS`.

- By default, the workflow uses a task-local cache at `$PWD/ollama/models` (inside the Nextflow work directory).
- To reuse models across runs (recommended on clusters), pass `--ollama_models_dir /path/to/persistent/models` so the container can bind-mount that directory.
- On the first run with an empty cache, the workflow auto-pulls the model; subsequent runs reuse the cached model when using a persistent `--ollama_models_dir`.

### GPU (Slurm + Apptainer)

```bash
nextflow run main.nf \
   -profile igs \
   --input data/multiqc_data.json \
   --slurm_account <your-account> \
   -w /usr/local/scratch/$USER/work \
   -resume
```

### Override cache path (optional)

Use this if your cluster requires a different location:

```bash
nextflow run main.nf \
   -profile igs \
   --input data/multiqc_data.json \
   --slurm_account <your-account> \
   --ollama_models_dir /path/to/persistent/models \
   -w /usr/local/scratch/$USER/work \
   -resume
```

## Continuous integration

The GitHub Actions workflow (`.github/workflows/test.yml`) runs on every pull request
to `main`. Because CI runners have no Ollama server, the required checks are limited to installing
dependencies across Python 3.9 / 3.11 / 3.12.

## Parameters

Parameters are passed on the Nextflow command line as `--<param> <value>`. Booleans
are set explicitly, e.g. `--think false` or `--review true`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — (required) | Path to the MultiQC `*_data.json` report. |
| `--descriptor` | bundled schema | Descriptor schema JSON; override to use your own (see below). |
| `--model` | `gemma4` | Ollama model name. |
| `--outdir` | `results` | Directory for the output interpretation. |
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

Execution/infrastructure parameters (`--container`, `--ollama_models_dir`, profiles)
are covered under **Nextflow execution** above.

## Where to place your files

- **QC report** — your MultiQC `*_data.json`. Put it anywhere and point `--input` at
  it; the examples keep reports in `data/`.
- **Descriptor schema** — the default ships at `json_reduction/descriptor_schema.json`
  and is used automatically. To describe your own report sections, copy that file, edit
  the entries, and pass it with `--descriptor /path/to/your_schema.json`.
- **Output** — the interpretation `.md` is written to `results/` (or wherever
  `--outdir` points).
