import json
from pathlib import Path
from functools import lru_cache
from backend.models.policy import Policy

def load_policy(file_path: str) -> Policy:
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Policy(**data)


@lru_cache(maxsize=1)
def get_policy() -> Policy:
    policy_path = Path(__file__).resolve().parents[2] / "assignment" / "policy_terms.json"
    return load_policy(str(policy_path))
