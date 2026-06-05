import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from json_load import load_json, fetch_file, PROJECT_ROOT, DATA_DIR
from json_topKeys import print_top_keys, has_key
from json_clean import extract_report_saved_raw_data
from json_write import save_json, req_filename
from json_merger import merge, req_annotated_filename

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "descriptor_schema.json")


def main():
    print("Project root : {}".format(PROJECT_ROOT))
    print("Data folder  : {}".format(DATA_DIR))
    print("Schema       : {}".format(SCHEMA_PATH))

    if not os.path.exists(SCHEMA_PATH):
        print("\nERROR: descriptor_schema.json not found at:")
        print("{}".format(SCHEMA_PATH))
        print("Place it in the json_reduction/ folder.")
        sys.exit(1)

    json_path = fetch_file()

    try:
        data = load_json(json_path)
    except Exception as e:
        print("\nFailed to load JSON: {}".format(e))
        sys.exit(1)

    print_top_keys(data)

    try:
        reduced = extract_report_saved_raw_data(data)
        found_key = next(iter(reduced))
        section_count = len(next(iter(reduced.values())))
        print("\nExtracted '{}' with {} sections".format(found_key, section_count))
    except KeyError as e:
        print("\nExtraction failed: {}".format(e))
        sys.exit(1)

    output_filename = req_filename(source_filename=json_path)
    try:
        reduced_path = save_json(reduced, DATA_DIR, output_filename)
    except Exception as e:
        print("\nFailed to save: {}".format(e))
        sys.exit(1)
    
    try:
        annotated_filename = req_annotated_filename()
        annotated_path = merge(
            data_path=reduced_path,
            descriptor_path=SCHEMA_PATH,
            output_dir=DATA_DIR,
            output_filename=annotated_filename,
        )
    except Exception as e:
        print("\nFailed to merge: {}".format(e))
        sys.exit(1)
    
    print("Extracted data : {}".format(reduced_path))
    print("Annotated report : {}".format(annotated_path))


if __name__ == "__main__":
    main()