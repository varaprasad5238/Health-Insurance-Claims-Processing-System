import json
import os
import re
from pathlib import Path
from typing import Any


def default_common_root() -> Path:
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/claims")
    return Path(__file__).resolve().parents[1] / "common" / "claims"


COMMON_ROOT = Path(os.getenv("CLAIMS_STORAGE_ROOT", str(default_common_root())))


def claim_root(claim_id: str) -> Path:
    root = COMMON_ROOT / safe_path_part(claim_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def uploaded_documents_dir(claim_id: str) -> Path:
    path = claim_root(claim_id) / "uploaded_documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def intermediate_outputs_dir(claim_id: str) -> Path:
    path = claim_root(claim_id) / "intermediate_outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_uploaded_document(*, claim_id: str, file_name: str, content: bytes, index: int) -> Path:
    suffix = Path(file_name).suffix
    base_name = safe_path_part(Path(file_name).stem) or f"document_{index}"
    target_name = f"{index:02d}_{base_name}{suffix}"
    target_path = uploaded_documents_dir(claim_id) / target_name
    target_path.write_bytes(content)
    return target_path


def write_intermediate_output(
    *,
    claim_id: str,
    stage_order: int,
    agent_name: str,
    span_id: str,
    payload: dict[str, Any],
) -> Path:
    file_name = f"{stage_order:02d}_{safe_path_part(agent_name)}_{safe_path_part(span_id)}.json"
    target_path = intermediate_outputs_dir(claim_id) / file_name
    target_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return target_path


def safe_path_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")