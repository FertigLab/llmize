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
 
    data_path = os.path.join(DATA_DIR, user_input)
    return data_path

def load_json(filepath: str) -> dict:
    with open(filepath, "r") as f:
        return json.load(f)
    
def fetch_file() -> str:
    print(f"(JSON files should be placed in: {DATA_DIR})")
    while True:
        user_input = input("Enter JSON filename or path: ").strip()
        resolved = resolve_path(user_input)
 
        if os.path.exists(resolved):
            print(f"Loading: {resolved}")
            return resolved
 
        print(f"  File not found: '{resolved}'. Please try again.")