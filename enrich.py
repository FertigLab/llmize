"""ToolUniverse gene enrichment: extract entities, look up annotations, build a
reference block for the system prompt. Optional, cached, and fail-safe.

    python3 enrich.py --input data/annotated_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# cache ToolUniverse lookups
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "enrichment_cache.json")
DEFAULT_MAX_GENES = 25

# Candidate ToolUniverse tool names for gene lookup
GENE_TOOL_CANDIDATES = [
    "get_target_id_description_by_name",
    "get_target_synonyms_by_ensemblID",
]

# Argument name the gene tool expects.
GENE_TOOL_ARG = "targetName"

def _collect_cell_types(report: dict) -> set:
    """Gather cell-type names from the cell-type and spatial-neighbor sections."""
    cell_types: set = set()
    skip = {"unknown", "na"}

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
                if isinstance(focal, str) and focal.lower() not in skip:
                    cell_types.add(focal)
                for sample in sub.get("data", {}).values():
                    if isinstance(sample, dict):
                        cell_types.update(sample.keys())
        elif name.endswith("_ct") or "deconvolved" in name:
            for sample in data.values():
                if isinstance(sample, dict):
                    cell_types.update(sample.keys())

    return {c for c in cell_types if isinstance(c, str) and c.lower() not in skip}


def _collect_moran_genes(report: dict) -> list:
    section = report.get("multiqc_Moran_I_interactions")
    if not isinstance(section, dict):
        return []

    best: dict = {}
    for sample in section.get("data", {}).values():
        if not isinstance(sample, dict):
            continue
        for key, score in sample.items():
            gene = key[:-2] if key.endswith("-I") else key
            if isinstance(score, (int, float)):
                best[gene] = max(best.get(gene, float("-inf")), score)

    return [g for g, _ in sorted(best.items(), key=lambda kv: kv[1], reverse=True)]


def _parse_ligrec_key(key: str, cell_types: set) -> dict | None:
    remainder = key
    trailing = []
    for _ in range(2):
        match = None
        for ct in cell_types:
            suffix = "-" + ct
            if remainder.endswith(suffix) and (match is None or len(ct) > len(match)):
                match = ct
        if match is None:
            break
        trailing.insert(0, match)
        remainder = remainder[: -(len(match) + 1)]

    if len(trailing) < 2 or not remainder:
        return None

    return {
        "ligand_receptor": remainder,
        "sender": trailing[0],
        "receiver": trailing[1],
        "raw": key,
    }


def extract_entities(report: dict, max_genes: int = DEFAULT_MAX_GENES) -> dict:
    """Extract genes, cell types, and ligand-receptor pairs from an annotated report."""
    cell_types = _collect_cell_types(report)
    genes = _collect_moran_genes(report)

    ligrec = []
    section = report.get("multiqc_squidpy_ligrec_interactions")
    if isinstance(section, dict):
        seen = set()
        for sample in section.get("data", {}).values():
            if not isinstance(sample, dict):
                continue
            for key in sample:
                parsed = _parse_ligrec_key(key, cell_types)
                if parsed and parsed["ligand_receptor"] not in seen:
                    seen.add(parsed["ligand_receptor"])
                    ligrec.append(parsed)

    return {
        "genes": genes[:max_genes],
        "all_genes_count": len(genes),
        "cell_types": sorted(cell_types),
        "ligand_receptor_pairs": ligrec,
    }


# ToolUniverse lookups

def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


class EntityEnricher:

    def __init__(self):
        self._tu = None
        self._gene_tool = None
        self._gene_arg = GENE_TOOL_ARG
        self._cache = _load_cache()
        self._init_tooluniverse()

    @property
    def available(self) -> bool:
        return self._tu is not None and self._gene_tool is not None

    def _init_tooluniverse(self) -> None:
        try:
            from tooluniverse import ToolUniverse
        except Exception as exc:
            print(f"[enrich] tooluniverse not available ({exc}); skipping live enrichment.")
            return

        try:
            tu = ToolUniverse()
            tu.load_tools()
        except Exception as exc:
            print(f"[enrich] Could not initialise ToolUniverse ({exc}); skipping live enrichment.")
            return

        self._tu = tu
        self._gene_tool = self._select_gene_tool(tu)
        if self._gene_tool is None:
            print(
                "[enrich] No gene-lookup tool matched. Set LLMIZE_GENE_TOOL to a valid "
                "ToolUniverse tool name (find one with `tu list | grep -i gene`)."
            )

    @staticmethod
    def _known_tool_names(tu) -> set:
        names = set()
        tools = getattr(tu, "all_tools", None)
        if isinstance(tools, (list, tuple)):
            for t in tools:
                if isinstance(t, dict) and "name" in t:
                    names.add(t["name"])
                elif isinstance(t, str):
                    names.add(t)
        tool_dict = getattr(tu, "all_tool_dict", None)
        if isinstance(tool_dict, dict):
            names.update(tool_dict.keys())
        return names

    def _select_gene_tool(self, tu):
        known = self._known_tool_names(tu)
        env_choice = os.environ.get("LLMIZE_GENE_TOOL")
        candidates = ([env_choice] if env_choice else []) + GENE_TOOL_CANDIDATES
        self._gene_arg = os.environ.get("LLMIZE_GENE_ARG", GENE_TOOL_ARG)
        for name in candidates:
            if not known or name in known:
                return name
        return None

    def _run_tool(self, gene: str) -> str | None:
        spec = {"name": self._gene_tool, "arguments": {self._gene_arg: gene}}
        try:
            runner = getattr(self._tu, "run", None)
            if callable(runner):
                result = runner(spec)
            else:
                result = self._tu.run_tool(self._gene_tool, arguments={self._gene_arg: gene})
        except Exception as exc:
            print(f"[enrich]   lookup failed for {gene}: {exc}")
            return None
        return _extract_gene_description(result, gene) or _summarise_result(result)

    def enrich_genes(self, genes: list) -> dict:
        out: dict = {}
        dirty = False
        for gene in genes:
            cache_key = f"{self._gene_tool}:{gene}"
            if cache_key in self._cache:
                if self._cache[cache_key]:
                    out[gene] = self._cache[cache_key]
                continue
            if not self.available:
                continue
            text = self._run_tool(gene)
            self._cache[cache_key] = text or ""
            dirty = True
            if text:
                out[gene] = text
        if dirty:
            _save_cache(self._cache)
        return out


def _extract_gene_description(result, gene: str) -> str | None:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except Exception:
            return None
    if not isinstance(result, dict):
        return None

    hits = result.get("data", {}).get("search", {}).get("hits")
    if not isinstance(hits, list) or not hits:
        return None

    exact = next(
        (h for h in hits if isinstance(h, dict) and str(h.get("name", "")).upper() == gene.upper()),
        None,
    )
    hit = exact or hits[0]
    if not isinstance(hit, dict):
        return None
    desc = hit.get("description") or hit.get("name")
    return " ".join(str(desc).split()) if desc else None


def _summarise_result(result, limit: int = 280) -> str | None:
    """Reduce an arbitrary ToolUniverse result to a short text snippet."""
    if result is None:
        return None
    if isinstance(result, str):
        text = result
    elif isinstance(result, dict):
        for key in ("function", "description", "summary", "comment", "text"):
            if isinstance(result.get(key), str) and result[key].strip():
                text = result[key]
                break
        else:
            text = json.dumps(result, ensure_ascii=False)
    else:
        text = str(result)

    text = " ".join(text.split())
    if not text:
        return None
    return text[:limit] + ("..." if len(text) > limit else "")


# Reference block assembly

def build_reference_block(entities: dict, gene_annotations: dict) -> str:
    """Assemble the markdown reference block for the system prompt."""
    if not entities.get("genes") and not entities.get("cell_types"):
        return ""

    lines = ["\n\n--- BIOLOGICAL REFERENCE (auto-generated context) ---"]

    if gene_annotations:
        lines.append("Gene annotations (from ToolUniverse):")
        for gene, text in gene_annotations.items():
            lines.append(f"- {gene}: {text}")
    elif entities.get("genes"):
        top = ", ".join(entities["genes"])
        lines.append(
            f"Top spatially-variable genes (no external annotations available): {top}"
        )

    if entities.get("cell_types"):
        lines.append("Cell types present: " + ", ".join(entities["cell_types"]) + ".")

    lines.append(
        "Use these annotations to ground your interpretation; do not invent gene functions "
        "beyond what is stated here and your own established knowledge."
    )
    return "\n".join(lines)


def enrich_report(report: dict, max_genes: int = DEFAULT_MAX_GENES) -> str:
    """Top-level entry point: extract entities, look them up, return a reference block."""
    entities = extract_entities(report, max_genes=max_genes)
    genes = entities.get("genes", [])
    print(
        f"[enrich] Extracted {entities.get('all_genes_count', 0)} genes "
        f"(enriching top {len(genes)}), {len(entities.get('cell_types', []))} cell types, "
        f"{len(entities.get('ligand_receptor_pairs', []))} ligand-receptor pairs."
    )

    enricher = EntityEnricher()
    gene_annotations = enricher.enrich_genes(genes) if genes else {}
    if gene_annotations:
        print(f"[enrich] Retrieved annotations for {len(gene_annotations)} genes.")

    return build_reference_block(entities, gene_annotations)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract and enrich entities from an annotated report.")
    parser.add_argument("--input", "-i", required=True, help="Path to annotated_report.json")
    parser.add_argument("--max-genes", type=int, default=DEFAULT_MAX_GENES)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not os.path.exists(args.input):
        sys.exit(f"[enrich] Input not found: {args.input}")
    with open(args.input, encoding="utf-8") as f:
        report = json.load(f)

    entities = extract_entities(report, max_genes=args.max_genes)
    print(json.dumps(entities, indent=2))
    print("\n--- Reference block preview ---")
    print(enrich_report(report, max_genes=args.max_genes))


if __name__ == "__main__":
    main()
