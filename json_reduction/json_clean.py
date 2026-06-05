TARGET_KEYS = ["report_saved_raw_data", "report_raw_saved_data"]
IGNORE_KEYS = {
    "multiqc_samplesheet": {"data_directory", "expression_profile"},
}

def extract_report_saved_raw_data(data : dict) -> dict:
    for key in TARGET_KEYS:
        if key in data:
            cleaned = _strip_ignored_keys(data[key])
            return {key: cleaned}
 
    raise KeyError(
        "Neither {} found in JSON. Available keys: {}".format(
            TARGET_KEYS, list(data.keys())
        )
    )

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
                cleaned_samples[sample_id] = {
                    k: v for k, v in metrics.items() if k not in ignore
                }
            else:
                cleaned_samples[sample_id] = metrics
        result[section] = cleaned_samples
 
    return result