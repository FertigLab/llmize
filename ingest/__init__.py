"""ingest: load, reduce, and annotate MultiQC JSON reports."""

from .io_utils import DATA_DIR, resolve_path, load_json, save_json, read_text
from .extract import extract_report_saved_raw_data
from .annotate import extract_focal_labels, annotate
from .text_ingest import (
    split_text_sections,
    looks_like_multiqc_llms_full,
    split_multiqc_llms_full,
    parse_markdown_table,
    extract_samplesheet_chunk,
)

__all__ = [
    "DATA_DIR",
    "resolve_path",
    "load_json",
    "save_json",
    "read_text",
    "extract_report_saved_raw_data",
    "extract_focal_labels",
    "annotate",
    "split_text_sections",
    "looks_like_multiqc_llms_full",
    "split_multiqc_llms_full",
    "parse_markdown_table",
    "extract_samplesheet_chunk",
]
