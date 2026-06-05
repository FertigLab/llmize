def print_top_keys (data : dict) -> None:
    print("\nTop Level Keys Found: ")
    for key in data.keys():
        print(f"  - {key}")


def has_key(data : dict, key: str) -> bool:
    return key in data