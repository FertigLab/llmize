"""Extraction step: turn a raw input JSON into a flat {section_name: payload} dict.

Unwraps MultiQC's raw-data wrapper key when present; otherwise falls back to treating
the whole input as already section-keyed, so non-MultiQC JSON is supported too.
"""

TARGET_KEYS = ["report_saved_raw_data", "report_raw_saved_data"]
IGNORE_KEYS = {
    "multiqc_samplesheet": {"data_directory", "expression_profile"},
}


def extract_report_saved_raw_data(data: dict) -> dict:
    """Return a flat {section_name: payload} dict. Unwraps MultiQC's raw-data key when
    present; otherwise falls back to treating `data` itself as the section dict."""
    for key in TARGET_KEYS:
        if key in data:
            return _strip_ignored_keys(data[key])
    print("[reduction] No MultiQC raw-data key found; treating input as generic section-keyed JSON.")
    return _strip_ignored_keys(data)


def _strip_ignored_keys(raw):
    result = {}
    for section, samples in raw.items():
        ignore = IGNORE_KEYS.get(section, set())
        if not ignore or not isinstance(samples, dict):
            result[section] = samples
            continue
        cleaned_samples = {}
        for sample_id, metrics in samples.items():
            if isinstance(metrics, dict):
                cleaned_samples[sample_id] = {k: v for k, v in metrics.items() if k not in ignore}
            else:
                cleaned_samples[sample_id] = metrics
        result[section] = cleaned_samples
    return result
