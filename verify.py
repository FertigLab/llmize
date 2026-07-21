from __future__ import annotations

import re

DEFAULT_MAX_GENES = 25


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


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]{1,14}")
_SPLIT = re.compile(r"[^A-Za-z0-9]+")

_STOPWORDS = {
    "NA", "QC", "DNA", "RNA", "MRNA", "CDNA", "RRNA", "TRNA", "NCRNA",
    "JSON", "HTML", "CSV", "TSV", "PNG", "PDF", "YAML", "URL", "API",
    "MULTIQC", "AI", "LLM", "ID", "IDS", "PCA", "UMAP", "TSNE", "HVG",
    "HVGS", "DEG", "DEGS", "FDR", "PVAL", "IQR", "SD", "SEM", "CI",
    "AND", "THE", "FOR", "WITH", "NOT", "ARE", "WAS", "HAS", "PER",
    "ALL", "ANY", "MAY", "CAN", "USE", "SEE", "BUT", "ITS", "OUR",
    "GENE", "GENES", "CELL", "CELLS", "TYPE", "TYPES", "DATA", "PLOT",
    "SAMPLE", "SAMPLES", "SECTION", "REPORT", "SCORE", "SCORES",
    "MORAN", "SPATIAL", "TOTAL", "MEAN", "HIGH", "LOW", "NONE",
}


def _looks_like_symbol(token: str) -> bool:
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    if has_digit and has_alpha:
        return True
    if token.isalpha() and token.isupper() and len(token) >= 3:
        return True
    return False


def report_vocabulary(report: dict) -> set:
    entities = extract_entities(report, max_genes=10 ** 9)
    vocab: set = set()

    for gene in entities.get("genes", []):
        for part in _SPLIT.split(gene):
            if part:
                vocab.add(part.upper())
        vocab.add(gene.upper())

    for cell_type in entities.get("cell_types", []):
        for part in _SPLIT.split(cell_type):
            if part:
                vocab.add(part.upper())

    for pair in entities.get("ligand_receptor_pairs", []):
        for part in _SPLIT.split(pair.get("ligand_receptor", "")):
            if part:
                vocab.add(part.upper())

    for section in report.values():
        if not isinstance(section, dict):
            continue
        data = section.get("data", {})
        if not isinstance(data, dict):
            continue
        for sample_id in data.keys():
            for part in _SPLIT.split(sample_id):
                if part:
                    vocab.add(part.upper())

    return vocab


def unsupported_entities(text: str, vocab: set) -> list:
    found: dict = {}
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        upper = token.upper()
        if upper in vocab or upper in _STOPWORDS:
            continue
        if not _looks_like_symbol(token):
            continue
        found.setdefault(upper, token)
    return sorted(found.values())


def deterministic_findings(text: str, report: dict) -> list:
    return unsupported_entities(text, report_vocabulary(report))
