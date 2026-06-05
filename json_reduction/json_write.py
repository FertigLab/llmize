import json
import os

def save_json(data: dict, data_dir: str, filename: str, indent: int = 2) -> str:
    bare_name = os.path.basename(filename)
    output_path = os.path.join(data_dir, bare_name)
    os.makedirs(data_dir, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=indent)

    abs_path = os.path.abspath(output_path)
    print(f"\nFile saved successfully.")
    print(f"Location : {abs_path}")

    return abs_path

def req_filename(source_filename: str) -> str:
    default = "extracted_" + os.path.basename(source_filename)
    user_input = input(f"\nEnter output filename (*Enter* = {default}): ").strip()
    return user_input if user_input else default