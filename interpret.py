from __future__ import annotations

import json
import os
import sys
import statistics
import subprocess
import time
from datetime import datetime

import ollama

from verify import deterministic_findings, extract_entities

SAMPLESHEET_KEY = "multiqc_samplesheet"

STYLE_GUIDE = """
Style and register (apply throughout):
- Write in the neutral, descriptive register of a peer-reviewed research paper.
  Report what the data shows; do not editorialize, rate, or pass judgement on it.
- Remove judgemental and evaluative language. Do NOT use words such as: striking,
  remarkable, overwhelming, dominant(ly), extreme, dramatic, impressive, crucial,
  notable(ly), interesting, surprising, concerning, alarming, poor, excellent, good,
  bad, or superlatives; and do not use exclamations.
- Lead with the data and tie every statement to specific values. Use hedged, precise
  verbs for any inference: "suggests", "is consistent with", "indicates", "may",
  "potentially". Prefer "associated with" over causal claims ("causes", "drives").
- Report negative or null results plainly (e.g. "no differential signal was detected").
- Present per-sample numbers in compact markdown tables rather than long inline lists.
- When presenting summaries, check that all relevant samples are included.
- Use plain formatting only: markdown headers, bold, and tables. Do NOT use LaTeX math
  ($...$, \\text{}, \\mathbf{}) or emoji.
- Be concise: do not restate the section name or descriptor, and do not repeat the same
  adjective across sentences.
- If a label or abbreviation's meaning is not provided, use it verbatim; do not infer or
  expand what it stands for.
"""

EVIDENCE_RULES = """
Evidence and interpretation rules:
- Tie every claim to numeric evidence. Do not infer causality; describe associations only.
- State a responder vs non-responder difference ONLY if it is consistent across at least
  2 samples per group, OR both the mean and the median support the same direction.
  Otherwise state plainly: "No consistent group-level difference detected."
- When you say a group is higher or lower, check that the direction matches the numbers
  (e.g. do not call the smaller mean "higher").
- Do not generalize a pattern driven by a single sample. If one sample drives a group's
  mean (an outlier), say so explicitly and treat that group-level claim as weak.
- Assess within-group variability as low / moderate / high. If variability is high or the
  trend is inconsistent, prefer a conservative interpretation or report no clear difference.
- Briefly note relevant limitations where they affect a conclusion (e.g. ~3 samples per
  group, high within-group variability, outlier influence) instead of implying certainty.
"""

SYSTEM_PROMPT = """You are an expert bioinformatician. You are given a report generated
by a bioinformatics workflow. The report incluced outputs from a number of bioinformatics
tools and include quality control metrics, as well as actual aggregated analysis results.
The report includes the samplesheet table that may contain important clinical metadata.
Different report sections may have different structures and different biological meaning,
and contains a short descriptor of the section's structure and meaning.Your task is to
analyse the data and give a concise summary.
""" + STYLE_GUIDE + EVIDENCE_RULES


def build_prompt(report: dict) -> str:
    report_str = json.dumps(report, indent=2)
    return (
        "Here is the annotated MultiQC spatial transcriptomics report.\n"
        "Please analyze it and provide a structured biological interpretation.\n\n"
        f"```json\n{report_str}\n```"
    )


def _split_descriptor(section_obj: dict) -> tuple:
    """Split a section into (descriptor, data)."""
    descriptor = {k: v for k, v in section_obj.items() if k != "data"}
    data = section_obj.get("data", {})
    return descriptor, data


def build_samplesheet_context(report: dict) -> str:
    """Sample sheet block for the shared system prompt."""
    samplesheet = report.get(SAMPLESHEET_KEY)
    if not isinstance(samplesheet, dict):
        return ""
    return (
        "\n\n--- SAMPLE SHEET (shared context for every section below) ---\n"
        f"```json\n{json.dumps(samplesheet, indent=2)}\n```\n"
        "Carry these per-sample labels (e.g. responder vs non-responder) into your "
        "interpretation of every section."
    )


GLOSSARY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "json_reduction", "cell_type_glossary.json"
)


def load_glossary(path: str = GLOSSARY_PATH) -> dict:
    """Load the local cell-type/abbreviation glossary, or {} if unavailable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _collect_report_labels(report: dict) -> set:
    """Collect cell-type labels that appear in the report's cell-type/spatial sections."""
    labels = set()
    for name, section in report.items():
        if not isinstance(section, dict):
            continue
        data = section.get("data", {})
        if not isinstance(data, dict):
            continue
        if name == "multiqc_spatial_neighbors":
            for sub in data.values():
                if not isinstance(sub, dict):
                    continue
                focal = sub.get("focal_cell_type")
                if isinstance(focal, str):
                    labels.add(focal)
                for sample in sub.get("data", {}).values():
                    if isinstance(sample, dict):
                        labels.update(sample.keys())
        elif name.endswith("_ct") or "deconvolved" in name:
            for sample in data.values():
                if isinstance(sample, dict):
                    labels.update(sample.keys())
    return {l for l in labels if isinstance(l, str)}


def build_glossary_context(report: dict, glossary: dict = None) -> str:
    """Glossary block defining the cell-type labels present; warns on undefined ones."""
    glossary = glossary if glossary is not None else load_glossary()
    if not glossary:
        return ""

    labels = _collect_report_labels(report)
    by_lower = {k.lower(): v for k, v in glossary.items()}

    defined = {}
    undefined = []
    for label in sorted(labels):
        definition = by_lower.get(label.lower())
        if definition:
            defined[label] = definition
        else:
            undefined.append(label)

    if undefined:
        print(f"[glossary] {len(undefined)} label(s) have no definition (add to "
              f"cell_type_glossary.json): {', '.join(undefined)}")

    if not defined:
        return ""

    lines = ["\n\n--- CELL-TYPE GLOSSARY (definitions for labels in this report) ---"]
    for label, definition in defined.items():
        lines.append(f"- {label}: {definition}")
    lines.append(
        "Use these definitions whenever a label appears. For any label NOT listed here, "
        "use it verbatim and do not infer or expand what it stands for."
    )
    return "\n".join(lines)


def _percentages(counts: dict) -> dict:
    """Return {key: percent-of-total} for a flat {key: count} mapping (1 d.p.)."""
    total = sum(v for v in counts.values() if isinstance(v, (int, float)))
    if total <= 0:
        return {}
    return {
        k: round(v / total * 100, 1)
        for k, v in counts.items()
        if isinstance(v, (int, float))
    }


def compute_percentages(section_name: str, data: dict) -> dict:
    """Percentage tables for count-based cell-type sections (spatial neighbors and *_ct)."""
    if not isinstance(data, dict):
        return {}

    if section_name == "multiqc_spatial_neighbors":
        out = {}
        for focal, sub in data.items():
            if isinstance(sub, dict) and isinstance(sub.get("data"), dict):
                per_sample = {
                    sample: _percentages(counts)
                    for sample, counts in sub["data"].items()
                    if isinstance(counts, dict)
                }
                if any(per_sample.values()):
                    out[focal] = {
                        "focal_cell_type": sub.get("focal_cell_type"),
                        "data_percent": per_sample,
                    }
        return out

    if section_name.endswith("_ct"):
        out = {
            group: _percentages(counts)
            for group, counts in data.items()
            if isinstance(counts, dict)
        }
        return {k: v for k, v in out.items() if v}

    return {}


def response_groups(report: dict) -> dict:
    """Map sample_id -> response label (e.g. 'responder') from the sample sheet."""
    samplesheet = report.get(SAMPLESHEET_KEY, {})
    data = samplesheet.get("data", {}) if isinstance(samplesheet, dict) else {}
    groups = {}
    for sample, meta in data.items():
        if isinstance(meta, dict):
            label = meta.get("responce") or meta.get("response")
            if label:
                groups[sample] = label
    return groups


def compute_group_stats(data: dict, groups: dict, max_metrics: int = 20) -> dict:
    """Per-group mean/median for sample-keyed numeric sections (bounded metric count)."""
    if not isinstance(data, dict) or not groups:
        return {}
    samples = [s for s in data if s in groups and isinstance(data[s], dict)]
    if len(samples) < 2:
        return {}

    metrics = []
    for s in samples:
        for k, v in data[s].items():
            if isinstance(v, (int, float)) and k not in metrics:
                metrics.append(k)
    if not metrics or len(metrics) > max_metrics:
        return {}

    by_group = {}
    for s in samples:
        by_group.setdefault(groups[s], []).append(s)

    out = {}
    for metric in metrics:
        per_group = {}
        for group, gsamples in by_group.items():
            vals = [data[s][metric] for s in gsamples if isinstance(data[s].get(metric), (int, float))]
            if vals:
                per_group[group] = {
                    "mean": round(statistics.mean(vals), 3),
                    "median": round(statistics.median(vals), 3),
                }
        if per_group:
            out[metric] = per_group
    return out


def _round_floats(obj, sig: int = 4):
    """Recursively round floats to `sig` significant figures to drop spurious precision.

    High-precision floats (e.g. 0.28376598223386557) add no information and can send
    small models into digit-echoing repetition loops; 4 significant figures is enough.
    """
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return float(f"{obj:.{sig}g}")
    if isinstance(obj, dict):
        return {k: _round_floats(v, sig) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, sig) for v in obj]
    return obj


def build_section_prompt(section_name: str, section_obj: dict, groups: dict = None) -> str:
    """Build the prompt analysing one MultiQC section."""
    descriptor, data = _split_descriptor(section_obj)
    analysis_instructions = descriptor.pop("analysis_instructions", None)

    prompt = (
        f"Analyze the MultiQC section `{section_name}` in isolation.\n\n"
        "Section descriptor (defines what each field/key/value means):\n"
        f"```json\n{json.dumps(descriptor, indent=2)}\n```\n\n"
        "Section data:\n"
        f"```json\n{json.dumps(_round_floats(data), indent=2)}\n```\n\n"
    )

    percentages = compute_percentages(section_name, data)
    if percentages:
        prompt += (
            "Derived percentages (each cell type as % of the group total — use THESE "
            "when describing composition or neighborhoods, do not re-estimate from counts):\n"
            f"```json\n{json.dumps(percentages, indent=2)}\n```\n\n"
        )

    group_stats = compute_group_stats(data, groups) if groups else {}
    if group_stats:
        prompt += (
            "Per-group summary statistics (mean and median by response group). Compare "
            "these group centers; do NOT infer a group difference from the min/max range "
            "alone, and explicitly flag any single-sample outlier that skews a group:\n"
            f"```json\n{json.dumps(_round_floats(group_stats), indent=2)}\n```\n\n"
        )

    prompt += (
        "Give a concise, analytical interpretation of THIS section only: the main "
        "patterns, notable or outlier values, differences between samples (relate them to "
        "the responder / non-responder labels from the sample sheet), and the biological "
        "meaning. Cite specific numbers/percentages. Do not speculate about sections you were not shown."
    )

    if analysis_instructions:
        prompt += f"\n\nFor this section specifically: {analysis_instructions}"
    return prompt


def iter_analysis_sections(report: dict):
    """Yield (name, section_obj) for each data-bearing section except the sample sheet."""
    for name, section_obj in report.items():
        if name == SAMPLESHEET_KEY:
            continue
        if isinstance(section_obj, dict) and "data" in section_obj:
            yield name, section_obj


SYNTHESIS_SYSTEM_PROMPT = """You are an expert bioinformatician. You are given
the per-section analyses of a spatial transcriptomics report.

Synthesize them into one concise executive summary of a few short paragraphs.
Cover:
- the overall picture and whether the pipeline appears to have run successfully,
- any notable patterns or outliers in the data and other data quality issues,
- the most important quantitative findings, citing key numbers and percentages,
- findings across the report sections that are consistent with each other, or 
  contradict each other,
- in case contrast analysis is present, provide a clear verdict on whether the 
  data supports difference across metadata groups,
- in case no metadata present, summary should focus on overall similarity patterns

Only surface findings that are well supported: consistent across at least 2
samples per group, or supported by both the mean and the median. Exclude weak,
single-sample-driven, or high-variability findings, or mention them only as not
robust. Do not combine several weak signals into a strong conclusion. Where the
data does not support a group difference, say so plainly.

Be decisive and readable. Do not repeat each section verbatim or list sections
one by one. Output only the summary prose — do NOT add your own title or markdown
heading.
""" + STYLE_GUIDE + EVIDENCE_RULES


def synthesize_sections(
    responses: list,
    model: str,
    num_ctx: int = 32768,
    samplesheet_context: str = "",
    think: bool = True,
    gen_options: dict = None,
) -> tuple:
    """Final call condensing the section analyses into a summary; returns (content, thinking)."""
    combined = "\n\n".join(f"### {name}\n{text.strip()}" for name, text in responses)
    prompt = (
        "Here are the per-section analyses of one MultiQC spatial transcriptomics report. "
        "Write the executive summary as instructed.\n\n"
        f"{combined}"
    )
    return chat_ollama(
        prompt,
        model=model,
        system=SYNTHESIS_SYSTEM_PROMPT + samplesheet_context,
        num_ctx=num_ctx,
        think=think,
        gen_options=gen_options,
    )


def _strip_leading_heading(text: str) -> str:
    """Drop a leading markdown heading line so it doesn't duplicate our own."""
    stripped = text.strip()
    if stripped.startswith("#"):
        lines = stripped.split("\n", 1)
        stripped = lines[1].strip() if len(lines) > 1 else ""
    return stripped


def combine_responses(responses: list, summary: str = None) -> str:
    """Combine section responses into one document, summary up front if given."""
    parts = ["# MultiQC Spatial Transcriptomics Interpretation\n"]
    if summary:
        parts.append(f"\n## Overview\n\n{_strip_leading_heading(summary)}\n")
        parts.append("\n---\n\n## Per-section detail\n")
    for name, text in responses:
        parts.append(f"\n## {name}\n\n{text.strip()}\n")
    return "\n".join(parts)


REVIEW_SYSTEM_PROMPT = """You are an expert bioinformatician reviewing a spatial transcriptomics interpretation for factual grounding and internal consistency. Correct statements that are not supported by the underlying report data, remove claims about genes, proteins, or cell types that do not appear in the data, and resolve contradictions between sections. Preserve the document's headings, tables, and structure. Do not add new findings and do not soften the removal of unsupported claims. Output only the corrected document, with no preamble.""" + STYLE_GUIDE + EVIDENCE_RULES


def build_review_prompt(text: str, findings: list) -> str:
    parts = [
        "Review the spatial transcriptomics interpretation below. Correct any statement "
        "that is not supported by the report data, and resolve any internal contradiction "
        "between sections. Do not introduce new claims, and do not invent gene or protein "
        "functions."
    ]
    if findings:
        max_listed = 50
        joined = ", ".join(findings[:max_listed])
        more = len(findings) - max_listed
        suffix = f" (and {more} more)" if more > 0 else ""
        parts.append(
            "These gene or cell-type symbols appear in the text but are absent from the "
            f"report data. Remove them or correct the surrounding claim: {joined}{suffix}."
        )
    parts.append("Return only the corrected interpretation, preserving its markdown structure.")
    parts.append("\n---\n\n" + text)
    return "\n\n".join(parts)


def review_interpretation(text, model, report, num_ctx=32768, passes=2,
                          think=True, gen_options=None):
    for i in range(max(1, passes)):
        findings = deterministic_findings(text, report)
        if i > 0 and not findings:
            break
        if findings:
            print(f"[review] pass {i + 1}: {len(findings)} unsupported symbol(s): {', '.join(findings)}")
        else:
            print(f"[review] pass {i + 1}: no unsupported symbols detected; evidence and consistency review")
        entities = extract_entities(report, max_genes=50)
        review_prompt = (
            "Deterministic entities extracted from the report (use these as the allowed symbol set):\n"
            f"```json\n{json.dumps(entities, indent=2)}\n```\n\n"
            + build_review_prompt(text, findings)
        )
        text, thinking = chat_ollama(
            review_prompt,
            model=model,
            system=REVIEW_SYSTEM_PROMPT,
            num_ctx=num_ctx,
            think=think,
            gen_options=gen_options,
        )
        print_thinking(f"Review pass {i + 1}", thinking)
    return text


def print_thinking(label: str, thinking: str) -> None:
    """Print the model's chain-of-thought to the terminal (it is not saved anywhere)."""
    if not thinking:
        return
    print(f"\n[think] ===== {label} =====")
    print(thinking.strip())
    print(f"[think] ===== end {label} =====\n")


def build_chunks(report: dict, whole_report: bool, groups: dict) -> list:
    """Return the (name, prompt) units to interpret. Whole-report mode is a single chunk."""
    if whole_report:
        return [("Whole report", build_prompt(report))]
    return [(name, build_section_prompt(name, obj, groups=groups))
            for name, obj in iter_analysis_sections(report)]


def interpret_report(
    report: dict,
    model: str,
    num_ctx: int = 32768,
    whole_report: bool = False,
    synthesize_final: bool = True,
    think: bool = True,
    gen_options: dict = None,
    user_instruction: str = "",
) -> str:
    """Interpret the report as one or more chunks; a single chunk is the whole report."""
    samplesheet_context = build_samplesheet_context(report)
    glossary_context = build_glossary_context(report)
    system = (SYSTEM_PROMPT + samplesheet_context + glossary_context
              + build_user_instruction(user_instruction))
    groups = response_groups(report)

    model = ensure_model(model)
    chunks = build_chunks(report, whole_report, groups)
    total = len(chunks)
    print(f"[interpret] Analyzing {total} chunk(s) with model '{model}'"
          f"{' (thinking)' if think else ''}.", flush=True)

    responses = []
    for idx, (name, prompt) in enumerate(chunks, 1):
        print(f"[interpret]   [{idx}/{total}] -> {name}", flush=True)
        started = time.monotonic()
        content, thinking = chat_ollama(
            prompt, model=model, system=system, num_ctx=num_ctx, think=think, gen_options=gen_options
        )
        print(f"[interpret]   [{idx}/{total}] {name} done in {time.monotonic() - started:.1f}s", flush=True)
        print_thinking(name, thinking)
        responses.append((name, content))

    if total == 1:
        return responses[0][1]

    summary = None
    if synthesize_final:
        print("[interpret] Synthesizing executive summary from per-section analyses...", flush=True)
        started = time.monotonic()
        summary, summary_thinking = synthesize_sections(
            responses, model, num_ctx, samplesheet_context, think=think, gen_options=gen_options
        )
        print(f"[interpret] Synthesis done in {time.monotonic() - started:.1f}s", flush=True)
        print_thinking("Overview (synthesis)", summary_thinking)

    return combine_responses(responses, summary)


def _available_models() -> list:
    """List locally available Ollama model names (robust across client versions)."""
    candidates = ["models", "list_models", "list"]
    for name in candidates:
        fn = getattr(ollama, name, None)
        if not callable(fn):
            continue
        try:
            res = fn()
        except Exception:
            continue

        if isinstance(res, dict) and "models" in res:
            items = res["models"]
        else:
            items = res

        out = []
        if isinstance(items, (list, tuple)):
            for it in items:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict):
                    if "name" in it:
                        out.append(it["name"])
                    elif "model" in it:
                        out.append(it["model"])
        if out:
            return out

    cli_cmds = [
        ["ollama", "list", "--json"],
        ["ollama", "models", "--json"],
        ["ollama", "list"],
    ]
    for cmd in cli_cmds:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            break
        out = proc.stdout.strip()
        if not out:
            continue
        try:
            parsed = json.loads(out)
            items = parsed if isinstance(parsed, (list, dict)) else None
            if isinstance(items, dict) and "models" in items:
                items = items["models"]
            names = []
            if isinstance(items, (list, tuple)):
                for it in items:
                    if isinstance(it, str):
                        names.append(it)
                    elif isinstance(it, dict):
                        if "name" in it:
                            names.append(it["name"])
                        elif "model" in it:
                            names.append(it["model"])
            if names:
                return names
        except Exception:
            lines = out.splitlines()
            names = []
            for line in lines:
                parts = line.strip().split()
                if not parts:
                    continue
                if any(h in line.lower() for h in ("name", "model", "---")):
                    continue
                names.append(parts[0])
            if names:
                return names

    return []


def ensure_model(model: str) -> str:
    """Resolve a usable Ollama model name, prompting the user if needed."""
    models = _available_models()
    if models and model not in models:
        lower_models = [m.lower() for m in models]
        if model.lower() in lower_models:
            return models[lower_models.index(model.lower())]

        tag_matches = [
            m for m in models
            if m.lower() == f"{model.lower()}:latest" or m.lower().startswith(f"{model.lower()}:")
        ]
        if len(tag_matches) == 1:
            print(f"[interpret] Resolved model '{model}' -> '{tag_matches[0]}'.")
            return tag_matches[0]

        suggestions = [m for m in models if model.lower() in m.lower()]
        print(f"[interpret] Model '{model}' not found locally.")
        if suggestions:
            print("Did you mean one of: {}".format(", ".join(suggestions)))
        print("Available models: {}".format(", ".join(models)))
        if not sys.stdin.isatty():
            sys.exit(
                "[interpret] Aborted: model not available and no interactive terminal "
                "to choose one. Re-run with an exact model name (e.g. --model {}).".format(
                    suggestions[0] if suggestions else models[0]
                )
            )
        choice = input("Enter alternative model name to try, type 'pull' to download a model, or press Enter to abort: ").strip()
        if not choice:
            sys.exit("[interpret] Aborted: requested model not available.")
        if choice.lower() == "pull":
            to_pull = input("Enter model name to pull (e.g. 'gemma8'): ").strip()
            if not to_pull:
                sys.exit("[interpret] Aborted: no model specified to pull.")
            print(f"[interpret] Pulling model '{to_pull}' via ollama CLI...")
            try:
                subprocess.check_call(["ollama", "pull", to_pull])
            except FileNotFoundError:
                print("ollama CLI not found in PATH. Please install Ollama or pull the model manually: ollama pull <model>")
                sys.exit(1)
            except subprocess.CalledProcessError as e:
                print(f"Failed to pull model: {e}")
                sys.exit(1)

            models = _available_models()
            if to_pull in models:
                return to_pull
            print("Model pull completed but model not listed by Ollama client. Proceeding to attempt chat anyway.")
            return to_pull
        return choice

    return model


def build_gen_options(
    temperature: float = None,
    top_p: float = None,
    top_k: int = None,
    seed: int = None,
    num_predict: int = None,
) -> dict:
    """Collect the set Ollama sampling options into a dict; unset ones use model defaults."""
    opts = {}
    if temperature is not None:
        opts["temperature"] = temperature
    if top_p is not None:
        opts["top_p"] = top_p
    if top_k is not None:
        opts["top_k"] = top_k
    if seed is not None:
        opts["seed"] = seed
    if num_predict is not None:
        opts["num_predict"] = num_predict
    return opts


def build_user_instruction(text: str) -> str:
    """Wrap a user-supplied instruction so it can be appended to the system prompt."""
    if not text:
        return ""
    return f"\n\n--- ADDITIONAL USER INSTRUCTIONS ---\n{text.strip()}"


def chat_ollama(
    prompt: str,
    model: str,
    system: str = SYSTEM_PROMPT,
    num_ctx: int = 32768,
    think: bool = True,
    gen_options: dict = None,
) -> tuple:
    """Send one prompt to a resolved model; returns (content, thinking)."""
    options = {"num_ctx": num_ctx}
    if gen_options:
        options.update(gen_options)
    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        options=options,
        think=think,
    )
    message = response["message"]
    return message.get("content", ""), (message.get("thinking") or "")


def _git_short_sha() -> str:
    """Return the short commit SHA (+'-dirty' if the tree has changes), or '' if unavailable."""
    root = os.path.dirname(os.path.abspath(__file__))
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=root, check=False,
        ).stdout.strip()
        if not sha:
            return ""
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=root, check=False,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return ""


def build_run_footer(
    model: str,
    num_ctx: int,
    think: bool,
    gen_options: dict = None,
    mode: str = "section-by-section",
    user_instruction: str = "",
    input_path: str = None,
) -> str:
    """Markdown footer recording run parameters so each output is reproducible."""
    gen = gen_options or {}

    def g(key):
        return gen[key] if key in gen and gen[key] is not None else "default"

    lines = [
        "\n\n---",
        "",
        "### Run parameters",
        "",
        f"- generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if input_path:
        lines.append(f"- input: {input_path}")
    lines.append(f"- model: {model}")
    lines.append(f"- mode: {mode} | thinking: {'on' if think else 'off'}")
    lines.append(
        f"- sampling: temperature={g('temperature')}, seed={g('seed')}, "
        f"top_p={g('top_p')}, top_k={g('top_k')}, num_predict={g('num_predict')}"
    )
    lines.append(f"- num_ctx: {num_ctx}")
    if user_instruction:
        lines.append(f"- custom prompt: {user_instruction!r}")
    sha = _git_short_sha()
    if sha:
        lines.append(f"- code: {sha}")
    return "\n".join(lines)


    main()