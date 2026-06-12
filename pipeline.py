#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from json_reduction.json_load import resolve_path, load_json, DATA_DIR
from json_reduction.json_clean import extract_report_saved_raw_data
from json_reduction.json_write import save_json
from json_reduction.json_merger import merge
from interpret import build_prompt, call_ollama, interpret_per_section, SYSTEM_PROMPT

DEFAULT_DESCRIPTOR = os.path.join(PROJECT_ROOT, "json_reduction", "descriptor_schema.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate JSON reduction, annotation, and Ollama interpretation."
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the raw MultiQC JSON input file.",
    )
    parser.add_argument(
        "--model", "-m",
        default="gemma4",
        help="Ollama model name to use (default: gemma4).",
    )
    parser.add_argument(
        "--descriptor",
        default=DEFAULT_DESCRIPTOR,
        help="Path to the descriptor schema JSON file.",
    )
    parser.add_argument(
        "--extracted-output",
        default=None,
        help="Filename for the extracted intermediate JSON saved in data/.",
    )
    parser.add_argument(
        "--annotated-output",
        default=None,
        help="Filename for the annotated report JSON saved in data/.",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to save the final interpreted report text. Defaults to data/<input_stem>_interpretation_<timestamp>.txt.",
    )
    parser.add_argument(
        "--num_ctx",
        type=int,
        default=32768,
        help="Context window size for Ollama (default: 32768).",
    )
    parser.add_argument(
        "--whole-report",
        action="store_true",
        help="Interpret the whole report in one call instead of section-by-section.",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Enrich the system prompt with ToolUniverse gene annotations (requires 'tooluniverse').",
    )
    parser.add_argument(
        "--no-synthesis",
        action="store_true",
        help="Skip the final executive-summary synthesis pass (section-by-section mode only).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run environment preflight checks (Ollama, models, ToolUniverse, schema) and exit.",
    )
    return parser.parse_args()


def _build_enrichment_context(report: dict, enabled: bool) -> str:
    """Return a ToolUniverse reference block for the system prompt, or '' if disabled/unavailable."""
    if not enabled:
        return ""
    try:
        from enrich import enrich_report
    except Exception as exc:
        print(f"[pipeline] Enrichment unavailable ({exc}); continuing without it.")
        return ""
    return enrich_report(report)


def resolve_input_path(path: str) -> str:
    resolved = resolve_path(path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Input file not found: {resolved}")
    return resolved


def default_output_name(input_path: str, prefix: str, suffix: str = "") -> str:
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return f"{prefix}{stem}{suffix}"


def save_text(text: str, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[pipeline] Saved final interpretation: {path}")


def run_pipeline(
    input_json: str,
    descriptor_path: str,
    model: str,
    extracted_filename: str | None,
    annotated_filename: str | None,
    output_path: str | None,
    num_ctx: int,
    whole_report: bool = False,
    enrich: bool = False,
    synthesize_final: bool = True,
) -> str:
    input_path = resolve_input_path(input_json)
    print(f"[pipeline] Loading raw JSON: {input_path}")

    data = load_json(input_path)
    reduced = extract_report_saved_raw_data(data)

    if extracted_filename is None:
        extracted_filename = default_output_name(input_path, prefix="extracted_")
    extracted_path = save_json(reduced, DATA_DIR, extracted_filename)
    print(f"[pipeline] Extracted JSON saved: {extracted_path}")

    if annotated_filename is None:
        annotated_filename = "annotated_report.json"
    annotated_path = merge(
        data_path=extracted_path,
        descriptor_path=descriptor_path,
        output_dir=DATA_DIR,
        output_filename=annotated_filename,
    )
    print(f"[pipeline] Annotated report saved: {annotated_path}")

    report = load_json(annotated_path)
    enrichment = _build_enrichment_context(report, enrich)

    if whole_report:
        prompt = build_prompt(report)
        print(f"[pipeline] Calling Ollama model '{model}' (whole report)...")
        response = call_ollama(
            prompt, model=model, system=SYSTEM_PROMPT + enrichment, num_ctx=num_ctx
        )
    else:
        print(f"[pipeline] Calling Ollama model '{model}' (section-by-section)...")
        response = interpret_per_section(
            report,
            model=model,
            num_ctx=num_ctx,
            extra_system_context=enrichment,
            synthesize_final=synthesize_final,
        )

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{stem}_interpretation_{timestamp}.md"
        output_path = os.path.join(DATA_DIR, output_filename)

    save_text(response, output_path)
    return output_path


def main() -> None:
    if "--check" in sys.argv:
        from check_env import main as check_main
        check_main()
        return

    args = parse_args()
    final_path = run_pipeline(
        input_json=args.input,
        descriptor_path=args.descriptor,
        model=args.model,
        extracted_filename=args.extracted_output,
        annotated_filename=args.annotated_output,
        output_path=args.output,
        num_ctx=args.num_ctx,
        whole_report=args.whole_report,
        enrich=args.enrich,
        synthesize_final=not args.no_synthesis,
    )
    print(f"[pipeline] Completed. Final report: {final_path}")


if __name__ == "__main__":
    main()
