"""json_reduction: load, reduce, and annotate MultiQC JSON reports."""

from .reduction import (
    DATA_DIR,
    resolve_path,
    load_json,
    save_json,
    extract_report_saved_raw_data,
    extract_focal_labels,
    annotate,
)

__all__ = [
    "DATA_DIR",
    "resolve_path",
    "load_json",
    "save_json",
    "extract_report_saved_raw_data",
    "extract_focal_labels",
    "annotate",
]
