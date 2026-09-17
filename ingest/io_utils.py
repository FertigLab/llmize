"""Path resolution and JSON file I/O, independent of any report format."""

import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


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
