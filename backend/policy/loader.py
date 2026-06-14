import json
from pathlib import Path
from backend.models.policy import Policy

def load_policy(file_path: str) -> Policy:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Policy(**data)
