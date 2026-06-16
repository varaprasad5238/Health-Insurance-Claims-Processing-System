from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.api import routes
from backend.services import claim_api_service


class ScalarList:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values

    def first(self):
        return self.values[0] if self.values else None


class FakeResult:
    def __init__(self, values=None, scalar_value=None):
        self.values = values or []
        self.scalar_value = scalar_value

    def scalars(self):
        return ScalarList(self.values)

    def scalar_one(self):
        return self.scalar_value


class FakeDB:
    def __init__(self, results=None, gets=None):
        self.results = list(results or [])
        self.gets = gets or {}
        self.added = []
        self.committed = 0

    async def execute(self, query):
        return self.results.pop(0)

    async def get(self, model, key):
        return self.gets.get(key)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed += 1


def member(member_id="EMP001"):
    return SimpleNamespace(
        member_id=member_id,
        policy_id="PLUM_GHI_2024",
        name="Rajesh Kumar",
        relationship="SELF",
        primary_member_id=None,
        join_date="2024-04-01",
        annual_opd_limit="50000.00",
        ytd_claimed_amount="1000.00",
        remaining_opd_limit="49000.00",
    )


def policy():
    return SimpleNamespace(
        policy_id="PLUM_GHI_2024",
        policy_name="Plan",
        insurer="Insurer",
        company_name="Company",
        status="ACTIVE",
        full_pledged_amount="500000.00",
        annual_opd_limit="50000.00",
        remaining_opd_limit="49000.00",
        family_floater_limit="150000.00",
        family_floater_remaining="150000.00",
    )


@pytest.mark.asyncio
async def test_list_policies_members_and_metrics_summary():
    metrics = [
        SimpleNamespace(provider="stub", agent_name="vision_read_doc_1", status="SUCCESS", is_fallback="false", latency_ms=10, input_tokens=2, output_tokens=3, total_tokens=5, error_category=None),
        SimpleNamespace(provider="openai", agent_name="entity_extraction", status="ERROR", is_fallback="true", latency_ms=None, input_tokens=1, output_tokens=1, total_tokens=2, error_category="BAD"),
    ]
    db = FakeDB(results=[FakeResult([policy()]), FakeResult([member()]), FakeResult(metrics)])

    policies = await claim_api_service.list_policies_and_members(db)
    summary = await claim_api_service.get_llm_metrics_summary(db)

    assert policies["policies"][0]["members"][0]["name"] == "Rajesh Kumar"
    assert summary["total_calls"] == 2
    assert summary["fallback_calls"] == 1
    assert summary["by_agent"]["vision_reader"] == 1
    assert summary["tokens_by_provider"]["stub"]["total_tokens"] == 5


@pytest.mark.asyncio
async def test_recent_metrics_list_claims_and_status():
    metric = SimpleNamespace(
        metric_id="M1",
        claim_id="CLM-1",
        agent_name="vision_read_doc_1",
        provider="stub",
        model="stub-llm",
        is_fallback="false",
        primary_error=None,
        latency_ms=5,
        status="SUCCESS",
        error_category=None,
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        created_at="2024-01-01T00:00:00+00:00",
    )
    claim = SimpleNamespace(
        claim_id="CLM-1",
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION",
        claimed_amount="1000.00",
        status="DECIDED",
        current_stage=None,
        updated_at="2024-01-02T00:00:00+00:00",
        created_at="2024-01-01T00:00:00+00:00",
    )
    decision = SimpleNamespace(
        claim_id="CLM-1",
        decision="APPROVED",
        approved_amount="900.00",
        copay_deducted="100.00",
        network_discount_applied="0.00",
        rejection_reasons="[]",
        partial_items=None,
        member_message="approved",
        ops_summary="ok",
        confidence_score=0.9,
        manual_review_note=None,
    )
    span = SimpleNamespace(
        span_id="S1",
        agent_name="policy_engine",
        stage_order=6,
        status="SUCCESS",
        elapsed_ms=4,
        started_at="2024-01-01T00:00:00+00:00",
        ended_at="2024-01-01T00:00:01+00:00",
        input_summary='{"a":1}',
        output_summary='{"b":2}',
        confidence_delta=0.1,
        errors="[]",
        model_used="none",
    )
    gating_error = SimpleNamespace(error_code="MISSING_REQUIRED", human_message="missing", detail='{"missing":["BILL"]}')
    db = FakeDB(
        results=[
            FakeResult([metric]),
            FakeResult(scalar_value=1),
            FakeResult([claim]),
            FakeResult([decision]),
            FakeResult([member()]),
            FakeResult([policy()]),
            FakeResult([claim]),
            FakeResult([span]),
            FakeResult([decision]),
            FakeResult([gating_error]),
        ]
    )

    recent = await claim_api_service.get_recent_llm_metrics(db, limit=5)
    claims = await claim_api_service.list_claims(db=db, page=1, page_size=10, status="DECIDED", date=None, month=1, year=2024)
    status = await claim_api_service.get_claim_status(claim_id="CLM-1", db=db)

    assert recent["metrics"][0]["agent_name"] == "vision_reader"
    assert claims["total"] == 1
    assert claims["claims"][0]["decision"] == "APPROVED"
    assert status["spans"][0]["input_summary"] == {"a": 1}
    assert status["gating_error"]["detail"] == {"missing": ["BILL"]}


@pytest.mark.asyncio
async def test_submit_claim_and_run_suite_case(monkeypatch):
    added_tasks = []

    class FakeBackgroundTasks:
        def add_task(self, func, *args, **kwargs):
            added_tasks.append((func, args, kwargs))

    async def fake_prepare_uploaded_document_payloads(**kwargs):
        return [{"file_name": "rx.png"}]

    monkeypatch.setattr(claim_api_service, "prepare_uploaded_document_payloads", fake_prepare_uploaded_document_payloads)
    monkeypatch.setattr(claim_api_service, "prepare_suite_document_payloads", lambda **kwargs: [{"file_name": "suite.png"}])
    monkeypatch.setattr(claim_api_service, "find_assignment_test_case", lambda case_id: {
        "case_id": case_id,
        "input": {
            "member_id": "EMP001",
            "policy_id": "PLUM_GHI_2024",
            "claim_category": "CONSULTATION",
            "treatment_date": "2024-11-01",
            "claimed_amount": 1000,
            "claims_history": [1, 2],
        },
        "expected": {"decision": "APPROVED"},
    })
    monkeypatch.setattr(claim_api_service, "suite_manifest_for", lambda case_id: {"test_context": {"case": case_id}})
    db = FakeDB(gets={"EMP001": member(), "PLUM_GHI_2024": policy()})
    background_tasks = FakeBackgroundTasks()

    submitted = await claim_api_service.submit_claim(
        background_tasks=background_tasks,
        db=db,
        member_id="EMP001",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        claimed_amount="1000.00",
        ytd_claims_amount=None,
        hospital_name=None,
        documents=[],
    )
    suite = await claim_api_service.run_test_suite_case(case_id="TC001", background_tasks=background_tasks, db=db)

    assert submitted["status"] == "PROCESSING"
    assert suite["same_day_claim_count"] == 2
    assert db.committed == 2
    assert len(added_tasks) == 2


@pytest.mark.asyncio
async def test_service_errors_for_missing_records():
    db = FakeDB(results=[FakeResult([])], gets={})
    with pytest.raises(HTTPException) as missing_status:
        await claim_api_service.get_claim_status(claim_id="NOPE", db=db)
    assert missing_status.value.status_code == 404

    with pytest.raises(HTTPException) as unknown_member:
        await claim_api_service.submit_claim(
            background_tasks=BackgroundTasks(),
            db=db,
            member_id="UNKNOWN",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount="1000.00",
            ytd_claims_amount=None,
            hospital_name=None,
            documents=[],
        )
    assert unknown_member.value.status_code == 400


@pytest.mark.asyncio
async def test_routes_delegate_success_and_wrap_errors(monkeypatch):
    async def async_ok(*args, **kwargs):
        return {"ok": True}

    def sync_ok(*args, **kwargs):
        return {"ok": True}

    async def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes.claim_api_service, "list_policies_and_members", async_ok)
    monkeypatch.setattr(routes.claim_api_service, "get_policy_options", sync_ok)
    monkeypatch.setattr(routes.claim_api_service, "get_llm_metrics_summary", async_ok)
    monkeypatch.setattr(routes.claim_api_service, "get_recent_llm_metrics", async_ok)
    monkeypatch.setattr(routes.claim_api_service, "submit_claim", async_ok)
    monkeypatch.setattr(routes.claim_api_service, "list_test_suite_cases", sync_ok)
    monkeypatch.setattr(routes.claim_api_service, "run_test_suite_case", async_ok)
    monkeypatch.setattr(routes.claim_api_service, "list_claims", async_ok)
    monkeypatch.setattr(routes.claim_api_service, "get_claim_status", async_ok)

    assert await routes.list_policies_and_members(db=object()) == {"ok": True}
    assert await routes.get_policy_options() == {"ok": True}
    assert await routes.get_llm_metrics_summary(db=object()) == {"ok": True}
    assert await routes.get_recent_llm_metrics(db=object(), limit=5) == {"ok": True}
    assert await routes.submit_claim(BackgroundTasks(), "EMP001", "CONSULTATION", "2024-11-01", "1000", None, None, [], db=object()) == {"ok": True}
    assert await routes.list_test_suite_cases() == {"ok": True}
    assert await routes.run_test_suite_case("TC001", BackgroundTasks(), db=object()) == {"ok": True}
    assert await routes.list_claims(db=object(), page=1, page_size=10, status=None, date=None, month=None, year=None) == {"ok": True}
    assert await routes.get_claim_status("CLM-1", db=object()) == {"ok": True}

    monkeypatch.setattr(routes.claim_api_service, "get_policy_options", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(HTTPException) as wrapped:
        await routes.get_policy_options()
    assert wrapped.value.status_code == 500

    monkeypatch.setattr(routes.claim_api_service, "list_policies_and_members", broken)
    with pytest.raises(HTTPException) as wrapped_async:
        await routes.list_policies_and_members(db=object())
    assert wrapped_async.value.detail.startswith("Failed to list policies and members")
