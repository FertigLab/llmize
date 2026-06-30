import json
import os


def req_annotated_filename() -> str:
    default = "annotated_report.json"
    user_input = input(f"\nEnter annotated report filename (*Enter* = {default}): ").strip()
    return user_input if user_input else default


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

    # Fallback: dataset-level labels.
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


def merge(data_path, descriptor_path, output_dir, output_filename="annotated_report.json",
          focal_labels=None):

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    with open(descriptor_path, encoding="utf-8") as f:
        descriptor = json.load(f)

    top_key = next(
        (k for k in data if "saved" in k and "raw" in k),
        None
    )
    if top_key is None:
        raise KeyError(
            "Could not find report_saved_raw_data in data file. "
            "Available keys: {}".format(list(data.keys()))
        )

    raw = data[top_key]
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
                "data": samples
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

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(annotated, f, indent=2)

    abs_path = os.path.abspath(output_path)
    print("Annotated report saved.")
    print("Location : {}".format(abs_path))
    return abs_path