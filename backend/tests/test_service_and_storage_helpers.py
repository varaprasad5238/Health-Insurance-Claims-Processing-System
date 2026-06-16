from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import test_suite_utils
from backend.services import claim_api_service
from backend.services.document_preprocessor import UnsupportedFormatError, prepare_for_vision_call
from backend.storage import local


class AsyncUpload:
    def __init__(self, filename: str | None, content_type: str | None, payload: bytes):
        self.filename = filename
        self.content_type = content_type
        self.payload = payload

    async def read(self) -> bytes:
        return self.payload


def test_storage_sanitizes_paths_and_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "COMMON_ROOT", tmp_path)

    saved = local.save_uploaded_document(claim_id="CLM ../42", file_name="bad name!!.pdf", content=b"pdf", index=3)
    output = local.write_intermediate_output(
        claim_id="CLM ../42",
        stage_order=2,
        agent_name="vision reader",
        span_id="span/1",
        payload={"ok": True},
    )

    assert saved.name == "03_bad_name.pdf"
    assert saved.read_bytes() == b"pdf"
    assert output.name == "02_vision_reader_span_1.json"
    assert local.safe_path_part("...!!!") == ""


def test_document_preprocessor_handles_images_and_unsupported_formats(tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"image-bytes")

    assert prepare_for_vision_call(str(image_path), "image/png") == [b"image-bytes"]
    with pytest.raises(UnsupportedFormatError) as exc_info:
        prepare_for_vision_call(str(image_path), "text/plain")
    assert exc_info.value.mime_type == "text/plain"


def test_document_preprocessor_converts_pdf_with_fake_fitz(tmp_path, monkeypatch):
    pdf_path = tmp_path / "claim.pdf"
    pdf_path.write_bytes(b"pdf-bytes")
    closed = {"value": False}

    class FakePage:
        def __init__(self, index: int):
            self.index = index

        def get_pixmap(self, dpi: int):
            return SimpleNamespace(tobytes=lambda image_type: f"page-{self.index}-{dpi}-{image_type}".encode())

    class FakeDoc:
        def __iter__(self):
            return iter([FakePage(1), FakePage(2)])

        def close(self):
            closed["value"] = True

    monkeypatch.setitem(__import__("sys").modules, "fitz", SimpleNamespace(open=lambda path: FakeDoc()))

    assert prepare_for_vision_call(str(pdf_path), "application/pdf") == [b"page-1-200-png", b"page-2-200-png"]
    assert closed["value"] is True


def test_test_suite_utils_success_and_errors(tmp_path, monkeypatch):
    cases_path = tmp_path / "test_cases.json"
    suite_root = tmp_path / "suite"
    documents_dir = suite_root / "TC001" / "documents"
    documents_dir.mkdir(parents=True)
    (documents_dir / "bill.pdf").write_bytes(b"pdf")
    (suite_root / "TC001" / "input.json").write_text('{"test_context":{"mode":"demo"}}', encoding="utf-8")
    cases_path.write_text('{"test_cases":[{"case_id":"TC001","input":{"member_id":"EMP001"}}]}', encoding="utf-8")
    monkeypatch.setattr(test_suite_utils, "ASSIGNMENT_TEST_CASES_PATH", cases_path)
    monkeypatch.setattr(test_suite_utils, "TEST_SUITE_ROOT", suite_root)

    assert test_suite_utils.load_assignment_test_cases()[0]["case_id"] == "TC001"
    assert test_suite_utils.find_assignment_test_case("tc001")["input"]["member_id"] == "EMP001"
    assert test_suite_utils.suite_documents_for("tc001") == [documents_dir / "bill.pdf"]
    assert test_suite_utils.suite_manifest_for("tc001") == {"test_context": {"mode": "demo"}}
    assert test_suite_utils.content_type_for(Path("x.jpeg")) == "image/jpeg"
    assert test_suite_utils.content_type_for(Path("x.unknown")) == "application/octet-stream"
    assert test_suite_utils.none_or_str(123) == "123"
    assert test_suite_utils.none_or_str("") is None

    with pytest.raises(HTTPException) as missing_case:
        test_suite_utils.find_assignment_test_case("TC999")
    assert missing_case.value.status_code == 404

    monkeypatch.setattr(test_suite_utils, "ASSIGNMENT_TEST_CASES_PATH", tmp_path / "missing.json")
    with pytest.raises(HTTPException) as missing_assignment:
        test_suite_utils.load_assignment_test_cases()
    assert missing_assignment.value.status_code == 500


def test_claim_api_service_policy_options_and_case_listing(monkeypatch):
    monkeypatch.setattr(
        claim_api_service,
        "load_assignment_test_cases",
        lambda: [
            {
                "case_id": "TC001",
                "case_name": "Happy path",
                "description": "desc",
                "input": {"member_id": "EMP001", "claim_category": "CONSULTATION", "claimed_amount": 1000},
                "expected": {"decision": "APPROVED", "approved_amount": 900},
            }
        ],
    )
    monkeypatch.setattr(claim_api_service, "suite_manifest_for", lambda case_id: {"test_context": {"source": case_id}})
    monkeypatch.setattr(claim_api_service, "TEST_SUITE_ROOT", Path("/does/not/matter"))
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "iterdir", lambda self: iter([self / "documents" / "bill.png"]))
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    options = claim_api_service.get_policy_options()
    cases = claim_api_service.list_test_suite_cases()

    assert options["minimum_claim_amount"] == 500
    assert "CONSULTATION" in options["claim_categories"]
    assert cases["cases"][0]["expected_decision"] == "APPROVED"
    assert cases["cases"][0]["documents"] == ["documents/documents/bill.png"]


@pytest.mark.asyncio
async def test_prepare_uploaded_and_suite_document_payloads(monkeypatch, tmp_path):
    saved_paths = []

    def fake_save_uploaded_document(*, claim_id, file_name, content, index):
        target = tmp_path / f"{index}_{file_name}"
        target.write_bytes(content)
        saved_paths.append(target)
        return target

    monkeypatch.setattr(claim_api_service, "save_uploaded_document", fake_save_uploaded_document)
    monkeypatch.setattr(claim_api_service, "prepare_for_vision_call", lambda path, content_type: [b"page-one", b"page-two"] if content_type == "application/pdf" else [Path(path).read_bytes()])
    monkeypatch.setattr(claim_api_service, "suite_documents_for", lambda case_id: [tmp_path / "bill.pdf"])
    monkeypatch.setattr(claim_api_service, "content_type_for", lambda path: "application/pdf")
    (tmp_path / "bill.pdf").write_bytes(b"suite-pdf")

    uploaded = await claim_api_service.prepare_uploaded_document_payloads(
        claim_id="CLM-1",
        documents=[AsyncUpload("bill.pdf", "application/pdf", b"pdf"), AsyncUpload(None, None, b"raw")],
    )
    suite = claim_api_service.prepare_suite_document_payloads(claim_id="CLM-2", case_id="TC001")

    assert [payload["content_type"] for payload in uploaded[:2]] == ["image/png", "image/png"]
    assert uploaded[-1]["file_name"] == "document_2"
    assert suite[0]["suite_case_id"] == "TC001"
    assert len(saved_paths) == 3


def test_claim_api_parse_json_and_unexpected_error():
    assert claim_api_service.parse_json('{"a": 1}') == {"a": 1}
    assert claim_api_service.parse_json("plain") == "plain"
    assert claim_api_service.parse_json(None) is None

    error = __import__("backend.api.routes", fromlist=["unexpected_error"]).unexpected_error("Failed", RuntimeError("boom"))
    assert error.status_code == 500
    assert error.detail == "Failed: boom"
