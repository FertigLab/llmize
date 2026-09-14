"""Annotation step: overlay descriptor metadata onto a flat, already-extracted report.

Also opportunistically merges MultiQC's spatial-neighbors/co-occurrence sections (by
name pattern) when present; it's a no-op on generic JSON that lacks them.
"""


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


def _curve_points(curve):
    """Well-formed [distance, ratio] points of a co-occurrence curve, sorted by distance."""
    points = [p for p in curve if isinstance(p, (list, tuple)) and len(p) >= 2]
    return sorted(points, key=lambda p: p[0])


def _cooccurrence_focal(section):
    """Focal cell type of a co-occurrence section: the target with the highest ratio at
    the smallest distance bin. A cell type self-co-occurs most strongly at short range, so
    this recovers the section's focal type from the data alone (no plot metadata needed)."""
    best, best_ratio = None, None
    for target, curve in section.items():
        if not (isinstance(curve, list) and curve):
            continue
        points = _curve_points(curve)
        if not points:
            continue
        ratio = points[0][1]
        if best_ratio is None or ratio > best_ratio:
            best, best_ratio = target, ratio
    return best


def _downsample_curve(curve, max_points=8):
    """Reduce a co-occurrence curve to at most `max_points` evenly-spaced points (keeping
    the first and last). Collapsing all focal types into one section makes the full 49-bin
    curves too large for the model; a few points still convey the short/long-range trend."""
    points = _curve_points(curve)
    n = len(points)
    if n <= max_points:
        return [list(p) for p in points]
    idxs = sorted({round(i * (n - 1) / (max_points - 1)) for i in range(max_points)})
    return [list(points[i]) for i in idxs]


def annotate(reduced: dict, descriptor: dict = None, focal_labels=None) -> dict:
    """Overlay descriptor metadata onto the reduced report; return the annotated report dict.
    `reduced` is a flat {section_name: payload} dict (MultiQC or generic). `descriptor` is
    optional; sections with no matching entry pass through with just their `data`."""
    descriptor = descriptor or {}
    raw = reduced
    focal_cell_types = _get_focal_cell_types(raw, focal_labels=focal_labels)
    annotated = {}
    spatial_neighbors_parent = None
    spatial_children = {}
    cooccurrence_parent = None
    cooccurrence_children = {}

    for section, samples in raw.items():
        is_spatial = "spatial_neighbors" in section
        is_cooccurrence = "co_occurrence" in section

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
        elif is_cooccurrence:
            if cooccurrence_parent is None:
                section_schema = dict(descriptor.get("multiqc_co_occurrence", {}))
                cooccurrence_parent = {
                    k: v for k, v in section_schema.items()
                    if not (isinstance(v, dict) and k == "sections")
                }
            focal = _cooccurrence_focal(samples) or f"focal cell type {len(cooccurrence_children) + 1} (unlabeled)"
            child_key = focal
            dup = 2
            while child_key in cooccurrence_children:
                child_key = f"{focal} ({dup})"
                dup += 1
            cooccurrence_children[child_key] = {
                "focal_cell_type": focal,
                "data": {t: _downsample_curve(c) for t, c in samples.items()
                         if isinstance(c, list)},
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

    if cooccurrence_parent is not None:
        cooccurrence_parent["data"] = cooccurrence_children
        annotated["multiqc_co_occurrence"] = cooccurrence_parent

    return annotated
