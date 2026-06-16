import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException


ROOT_DIR = Path(__file__).resolve().parents[2]
ASSIGNMENT_TEST_CASES_PATH = ROOT_DIR / "assignment" / "test_cases.json"
TEST_SUITE_ROOT = ROOT_DIR / "test_suite"


def load_assignment_test_cases() -> list[dict[str, Any]]:
    try:
        payload = json.loads(ASSIGNMENT_TEST_CASES_PATH.read_text(encoding="utf-8"))
        return payload.get("test_cases", [])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="assignment/test_cases.json was not found") from exc


def find_assignment_test_case(case_id: str) -> dict[str, Any]:
    normalized = case_id.upper()
    for test_case in load_assignment_test_cases():
        if test_case.get("case_id", "").upper() == normalized:
            return test_case
    raise HTTPException(status_code=404, detail=f"Unknown test case: {case_id}")


def suite_documents_for(case_id: str) -> list[Path]:
    documents_dir = TEST_SUITE_ROOT / case_id.upper() / "documents"
    if not documents_dir.exists():
        raise HTTPException(status_code=404, detail=f"No documents folder found for {case_id.upper()}")
    documents = sorted(path for path in documents_dir.iterdir() if path.is_file())
    if not documents:
        raise HTTPException(status_code=404, detail=f"No document artifacts found for {case_id.upper()}")
    return documents


def suite_manifest_for(case_id: str) -> dict[str, Any] | None:
    manifest_path = TEST_SUITE_ROOT / case_id.upper() / "input.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".gif":
        return "image/gif"
    return "application/octet-stream"


def none_or_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)