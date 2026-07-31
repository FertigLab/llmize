from __future__ import annotations

import re

from enrich import extract_entities

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
