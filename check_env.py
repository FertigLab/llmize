from __future__ import annotations

import importlib.util
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

OK, WARN, FAIL = "ok", "warn", "fail"
_SYMBOL = {OK: "✓", WARN: "⚠", FAIL: "✗"}


class Check:
    def __init__(self, name: str, status: str, message: str, required: bool):
        self.name = name
        self.status = status
        self.message = message
        self.required = required


def _python_version() -> Check:
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}"
    if (major, minor) >= (3, 9):
        return Check("Python version", OK, f"Python {version}", required=True)
    return Check(
        "Python version", WARN,
        f"Python {version} detected; 3.9+ recommended (and 3.10+ unlocks newer ToolUniverse).",
        required=True,
    )


def _ollama_package() -> Check:
    if importlib.util.find_spec("ollama") is None:
        return Check(
            "ollama (Python client)", FAIL,
            "Not installed. Run: python3 -m pip install -r requirements.txt",
            required=True,
        )
    return Check("ollama (Python client)", OK, "installed", required=True)


def _ollama_server_and_models() -> list:
    if importlib.util.find_spec("ollama") is None:
        return [Check("Ollama (local service)", FAIL, "skipped — ollama client not installed", required=True)]

    import ollama

    try:
        ollama.list()
    except Exception as exc:
        return [Check(
            "Ollama (local service)", FAIL,
            f"local Ollama service not running ({type(exc).__name__}). Install Ollama from "
            "https://ollama.com and start it (launch the app, or run `ollama serve`). "
            "It runs on localhost and performs inference on-device.",
            required=True,
        )]

    server_ok = Check("Ollama (local service)", OK, "running on localhost", required=True)

    from interpret import _available_models
    models = _available_models()
    if models:
        shown = ", ".join(models[:6]) + (" ..." if len(models) > 6 else "")
        model_check = Check("Ollama models", OK, f"{len(models)} available: {shown}", required=False)
    else:
        model_check = Check(
            "Ollama models", WARN,
            "no models pulled. Pull one before running, e.g.: ollama pull gemma2",
            required=False,
        )
    return [server_ok, model_check]


def _tooluniverse() -> Check:
    if importlib.util.find_spec("tooluniverse") is None:
        return Check(
            "ToolUniverse (optional, --enrich)", WARN,
            "not installed; gene enrichment will be skipped. "
            "Install with: python3 -m pip install tooluniverse PyYAML",
            required=False,
        )
    try:
        from enrich import EntityEnricher
        enricher = EntityEnricher()
    except Exception as exc:
        return Check(
            "ToolUniverse (optional, --enrich)", WARN,
            f"installed but failed to initialise ({type(exc).__name__}); enrichment will be skipped.",
            required=False,
        )
    if enricher.available:
        return Check("ToolUniverse (optional, --enrich)", OK, "ready (gene-lookup tool resolved)", required=False)
    return Check(
        "ToolUniverse (optional, --enrich)", WARN,
        "installed but no gene-lookup tool matched. Set LLMIZE_GENE_TOOL to a valid tool name.",
        required=False,
    )


def _descriptor_schema() -> Check:
    path = os.path.join(PROJECT_ROOT, "json_reduction", "descriptor_schema.json")
    if os.path.exists(path):
        return Check("Descriptor schema", OK, "json_reduction/descriptor_schema.json present", required=True)
    return Check(
        "Descriptor schema", FAIL,
        "json_reduction/descriptor_schema.json is missing — annotation will fail.",
        required=True,
    )


def _data_dir_writable() -> Check:
    data_dir = os.path.join(PROJECT_ROOT, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
        probe = os.path.join(data_dir, ".write_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except Exception as exc:
        return Check("data/ writable", FAIL, f"cannot write to data/ ({exc}).", required=True)
    return Check("data/ writable", OK, "data/ is writable", required=True)


def run_checks() -> list:
    checks = [_python_version(), _ollama_package()]
    checks += _ollama_server_and_models()
    checks.append(_tooluniverse())
    checks.append(_descriptor_schema())
    checks.append(_data_dir_writable())
    return checks


def report(checks: list) -> bool:
    print("llmize environment check\n" + "=" * 40)
    for c in checks:
        tag = "(required)" if c.required else "(optional)"
        print(f"  {_SYMBOL[c.status]} {c.name:<32} {tag}  {c.message}")

    required_failed = [c for c in checks if c.required and c.status == FAIL]
    warnings = [c for c in checks if c.status == WARN]
    print("=" * 40)
    if required_failed:
        print(f"RESULT: NOT READY — {len(required_failed)} required check(s) failed. See messages above.")
        return False
    if warnings:
        print(f"RESULT: READY (with {len(warnings)} warning(s) — optional features may be limited).")
    else:
        print("RESULT: READY — all checks passed.")
    return True


def main() -> None:
    ok = report(run_checks())
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
