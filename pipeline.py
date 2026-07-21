from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from json_reduction import (
    resolve_path,
    load_json,
    save_json,
    DATA_DIR,
    extract_report_saved_raw_data,
    extract_focal_labels,
    annotate,
)
from interpret import (
    interpret_report,
    build_gen_options,
    build_run_footer,
    review_interpretation,
)

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
        default=os.environ.get("LLMIZE_MODEL", "gemma4"),
        help="Ollama model name to use. Defaults to $LLMIZE_MODEL, else gemma4. "
             "In the Docker image, boot pulls the same $LLMIZE_MODEL, so setting the env "
             "var alone keeps boot and the pipeline in sync.",
    )
    parser.add_argument(
        "--descriptor",
        default=DEFAULT_DESCRIPTOR,
        help="Path to the descriptor schema JSON file.",
    )
    parser.add_argument(
        "--save-intermediates",
        action="store_true",
        help="Write the reduced and annotated JSON to data/ (off by default; run is in-memory).",
    )
    parser.add_argument(
        "--extracted-output",
        default=None,
        help="Filename for the extracted intermediate JSON (only with --save-intermediates).",
    )
    parser.add_argument(
        "--annotated-output",
        default=None,
        help="Filename for the annotated report JSON (only with --save-intermediates).",
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
        "--no-synthesis",
        action="store_true",
        help="Skip the final executive-summary synthesis pass (section-by-section mode only).",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Run a capped self-review of the interpretation, driven by a deterministic "
             "check for gene/cell-type symbols that do not appear in the report data.",
    )
    parser.add_argument(
        "--review-passes",
        type=int,
        default=2,
        help="Maximum number of review passes when --review is set (default: 2).",
    )
    parser.add_argument(
        "--think",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use the model's native thinking mode; reasoning is printed to the terminal "
             "(not saved) and kept out of the interpretation. On by default; --no-think disables it (faster).",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Extra instruction appended to the system prompt for every section.",
    )
    parser.add_argument("--temperature", type=float, default=None,
                        help="Sampling temperature (model default if unset; gemma4 defaults to 1).")
    parser.add_argument("--top_p", type=float, default=None, help="Nucleus sampling top_p.")
    parser.add_argument("--top_k", type=int, default=None, help="Top-k sampling.")
    parser.add_argument("--seed", type=int, default=None,
                        help="Sampling seed for reproducible runs.")
    parser.add_argument("--num_predict", type=int, default=None,
                        help="Max tokens to generate per call (model default if unset).")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run environment preflight checks (Ollama, models, schema) and exit.",
    )
    return parser.parse_args()


def resolve_input_path(path: str) -> str:
    resolved = resolve_path(path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Input file not found: {resolved}")
    return resolved


def default_output_name(input_path: str, prefix: str) -> str:
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return f"{prefix}{stem}"


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
    synthesize_final: bool = True,
    think: bool = True,
    gen_options: dict = None,
    user_instruction: str = "",
    review: bool = False,
    review_passes: int = 2,
    save_intermediates: bool = False,
) -> str:
    input_path = resolve_input_path(input_json)
    print(f"[pipeline] Loading raw JSON: {input_path}")

    data = load_json(input_path)
    reduced = extract_report_saved_raw_data(data)
    # Recover real focal cell types from the raw report's plot metadata.
    focal_labels = extract_focal_labels(data)
    if focal_labels:
        print(f"[pipeline] Recovered spatial-neighbors focal cell types: {focal_labels}")
    descriptor = load_json(descriptor_path)
    report = annotate(reduced, descriptor, focal_labels=focal_labels)
    print(f"[pipeline] Reduced and annotated {len(report)} sections in memory.")

    if save_intermediates:
        save_json(reduced, DATA_DIR, extracted_filename or default_output_name(input_path, prefix="extracted_"))
        save_json(report, DATA_DIR, annotated_filename or "annotated_report.json")

    mode = "whole report" if whole_report else "section-by-section"
    print(f"[pipeline] Calling Ollama model '{model}' ({mode})...")
    response = interpret_report(
        report,
        model=model,
        num_ctx=num_ctx,
        whole_report=whole_report,
        synthesize_final=synthesize_final,
        think=think,
        gen_options=gen_options,
        user_instruction=user_instruction,
    )

    if review:
        print(f"[pipeline] Reviewing interpretation (up to {review_passes} pass(es))...")
        response = review_interpretation(
            response, model=model, report=report, num_ctx=num_ctx,
            passes=review_passes, think=think, gen_options=gen_options,
        )

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = os.path.splitext(os.path.basename(input_path))[0]
        output_filename = f"{stem}_interpretation_{timestamp}.md"
        output_path = os.path.join(DATA_DIR, output_filename)

    footer = build_run_footer(
        model=model, num_ctx=num_ctx, think=think, gen_options=gen_options,
        mode="whole-report" if whole_report else "section-by-section",
        user_instruction=user_instruction, input_path=input_path,
    )
    save_text(response + footer, output_path)
    return output_path


def main() -> None:
    if "--check" in sys.argv:
        from check_env import main as check_main
        check_main()
        return

    args = parse_args()
    gen_options = build_gen_options(
        temperature=args.temperature, top_p=args.top_p, top_k=args.top_k,
        seed=args.seed, num_predict=args.num_predict,
    )
    final_path = run_pipeline(
        input_json=args.input,
        descriptor_path=args.descriptor,
        model=args.model,
        extracted_filename=args.extracted_output,
        annotated_filename=args.annotated_output,
        output_path=args.output,
        num_ctx=args.num_ctx,
        whole_report=args.whole_report,
        synthesize_final=not args.no_synthesis,
        think=args.think,
        gen_options=gen_options,
        user_instruction=args.prompt,
        review=args.review,
        review_passes=args.review_passes,
        save_intermediates=args.save_intermediates,
    )
    print(f"[pipeline] Completed. Final report: {final_path}")


if __name__ == "__main__":
    main()
