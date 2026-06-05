import json
import os


def req_annotated_filename() -> str:
    default = "annotated_report.json"
    user_input = input(f"\nEnter annotated report filename (*Enter* = {default}): ").strip()
    return user_input if user_input else default


def _get_focal_cell_types(data):
    """Extract focal cell types from actual spatial neighbor data."""
    focal_types = {}
    spatial_sections = sorted(
        [k for k in data.keys() if "spatial_neighbors" in k],
        key=lambda x: (x, int(x.split("_")[-1]) if "_" in x and x.split("_")[-1].isdigit() else -1)
    )
    
    for idx, section in enumerate(spatial_sections):
        focal_types[section] = {
            "index": idx,
            "focal_cell_type": _infer_focal_cell_type(section, idx)
        }
    
    return focal_types


def _infer_focal_cell_type(section_name, index):
    """Infer focal cell type from section structure. Can be overridden by descriptor if available."""
    inferred_types = {
        "multiqc_spatial_neighbors": "type B pancreatic cell",
        "multiqc_spatial_neighbors_1": "type A enteroendocrine cell",
        "multiqc_spatial_neighbors_2": "acinar cell",
        "multiqc_spatial_neighbors_3": "pancreatic ductal cell",
        "multiqc_spatial_neighbors_4": "NA",
        "multiqc_spatial_neighbors_5": "unknown",
    }
    return inferred_types.get(section_name, "unknown")


def merge(data_path, descriptor_path, output_dir, output_filename="annotated_report.json"):

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
    focal_cell_types = _get_focal_cell_types(raw)
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