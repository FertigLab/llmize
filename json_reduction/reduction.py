"""Load, reduce, and annotate MultiQC JSON reports.

Public API: DATA_DIR, resolve_path, load_json, save_json,
extract_report_saved_raw_data, extract_focal_labels, annotate.
"""

import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

TARGET_KEYS = ["report_saved_raw_data", "report_raw_saved_data"]
IGNORE_KEYS = {
    "multiqc_samplesheet": {"data_directory", "expression_profile"},
}


def resolve_path(user_input: str) -> str:
    if os.path.isabs(user_input):
        return user_input
    cwd_path = os.path.join(os.getcwd(), user_input)
    if os.path.exists(cwd_path):
        return cwd_path
    return os.path.join(DATA_DIR, user_input)


def load_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, data_dir: str, filename: str, indent: int = 2) -> str:
    output_path = os.path.join(data_dir, os.path.basename(filename))
    os.makedirs(data_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)
    abs_path = os.path.abspath(output_path)
    print(f"[reduction] Saved: {abs_path}")
    return abs_path


def extract_report_saved_raw_data(data: dict) -> dict:
    for key in TARGET_KEYS:
        if key in data:
            return {key: _strip_ignored_keys(data[key])}
    raise KeyError(
        "Neither {} found in JSON. Available keys: {}".format(TARGET_KEYS, list(data.keys()))
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
                cleaned_samples[sample_id] = {k: v for k, v in metrics.items() if k not in ignore}
            else:
                cleaned_samples[sample_id] = metrics
        result[section] = cleaned_samples
    return result


def _section_index(section_name):
    """Numeric index of a spatial-neighbors section: '...neighbors' -> 0, '..._1' -> 1, etc."""
    suffix = section_name.split("multiqc_spatial_neighbors")[-1]
    if suffix.startswith("_") and suffix[1:].isdigit():
        return int(suffix[1:])
    return 0


def extract_focal_labels(full_data):
    """Recover ordered focal cell-type names from the spatial-neighbors plot metadata."""
    plot_data = full_data.get("report_plot_data", {})
    if not isinstance(plot_data, dict):
        return []

    plot = next(
        (v for k, v in plot_data.items()
         if "spatial_neighbor" in k.lower() and isinstance(v, dict)),
        None,
    )
    if not plot:
        return []

    names = []
    for item in plot.get("pconfig", {}).get("data_labels", []) or []:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and (item.get("name") or item.get("label")):
            names.append(item.get("name") or item.get("label"))
    if names:
        return names

    for ds in plot.get("datasets", []) or []:
        if isinstance(ds, dict) and ds.get("label"):
            names.append(ds["label"])
    return names


def _get_focal_cell_types(data, focal_labels=None):
    """Map each spatial-neighbors section to its focal cell type; unlabeled if unknown."""
    focal_labels = focal_labels or []
    focal_types = {}
    spatial_sections = sorted(
        [k for k in data.keys() if "spatial_neighbors" in k],
        key=_section_index,
    )
    for idx, section in enumerate(spatial_sections):
        if idx < len(focal_labels):
            label = focal_labels[idx]
        else:
            label = f"focal cell type {idx + 1} (unlabeled)"
        focal_types[section] = {"index": idx, "focal_cell_type": label}
    return focal_types


def annotate(reduced: dict, descriptor: dict, focal_labels=None) -> dict:
    """Overlay descriptor metadata onto the reduced report; return the annotated report dict."""
    top_key = next((k for k in reduced if "saved" in k and "raw" in k), None)
    if top_key is None:
        raise KeyError(
            "Could not find report_saved_raw_data. Available keys: {}".format(list(reduced.keys()))
        )

    raw = reduced[top_key]
    focal_cell_types = _get_focal_cell_types(raw, focal_labels=focal_labels)
    annotated = {}
    spatial_neighbors_parent = None
    spatial_children = {}

    for section, samples in raw.items():
        is_spatial = "spatial_neighbors" in section

        if is_spatial and section in focal_cell_types:
            if spatial_neighbors_parent is None:
                section_schema = dict(descriptor.get("multiqc_spatial_neighbors", {}))
                spatial_neighbors_parent = {}
                for k, v in section_schema.items():
                    if not isinstance(v, dict) or k != "sections":
                        spatial_neighbors_parent[k] = v

            if section == "multiqc_spatial_neighbors":
                child_key = "multiqc_spatial_neighbors_1"
            else:
                suffix = section.split("multiqc_spatial_neighbors")[-1]
                if suffix.startswith("_"):
                    num = int(suffix[1:]) + 1
                    child_key = f"multiqc_spatial_neighbors_{num}"
                else:
                    child_key = "multiqc_spatial_neighbors_1"

            spatial_children[child_key] = {
                "focal_cell_type": focal_cell_types[section]["focal_cell_type"],
                "data": samples,
            }
        else:
            section_schema = descriptor.get(section, {})
            entry = {}
            for k, v in section_schema.items():
                if isinstance(v, dict) and k == "sections":
                    continue
                entry[k] = v
            entry["data"] = samples
            annotated[section] = entry

    if spatial_neighbors_parent is not None:
        spatial_neighbors_parent["data"] = spatial_children
        annotated["multiqc_spatial_neighbors"] = spatial_neighbors_parent

    return annotated
