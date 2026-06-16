from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api import dtos
from backend.database.connection import AsyncSessionLocal
from backend.services import claim_api_service

router = APIRouter(prefix="/api/claims", tags=["claims"])


def unexpected_error(message: str, exc: Exception) -> HTTPException:
    return HTTPException(status_code=500, detail=f"{message}: {exc}")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


@router.get("/policies/members", response_model=dtos.PoliciesMembersResponse)
async def list_policies_and_members(db: AsyncSession = Depends(get_db)):
    """Return seeded policies and their member rosters for claim submission forms."""
    try:
        return await claim_api_service.list_policies_and_members(db)
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to list policies and members", exc) from exc


@router.get("/policy-options", response_model=dtos.PolicyOptionsResponse)
async def get_policy_options():
    """Return policy-driven dropdown options and validation limits."""
    try:
        return claim_api_service.get_policy_options()
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to load policy options", exc) from exc


@router.get("/llm-metrics/summary", response_model=dtos.LLMMetricSummaryResponse)
async def get_llm_metrics_summary(db: AsyncSession = Depends(get_db)):
    """Return aggregate LLM usage, latency, fallback, and error metrics."""
    try:
        return await claim_api_service.get_llm_metrics_summary(db)
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to load LLM metrics summary", exc) from exc


@router.get("/llm-metrics/recent", response_model=dtos.LLMMetricRecentResponse)
async def get_recent_llm_metrics(db: AsyncSession = Depends(get_db), limit: int = Query(25, ge=1, le=100)):
    """Return recent LLM call metrics for operational inspection."""
    try:
        return await claim_api_service.get_recent_llm_metrics(db, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to load recent LLM metrics", exc) from exc


@router.post("/", response_model=dtos.SubmitClaimResponse)
async def submit_claim(
    background_tasks: BackgroundTasks,
    member_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: str = Form(...),
    ytd_claims_amount: str | None = Form(None),
    hospital_name: str | None = Form(None),
    documents: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Create a claim from uploaded documents and enqueue asynchronous ingestion."""
    try:
        return await claim_api_service.submit_claim(
            background_tasks=background_tasks,
            db=db,
            member_id=member_id,
            claim_category=claim_category,
            treatment_date=treatment_date,
            claimed_amount=claimed_amount,
            ytd_claims_amount=ytd_claims_amount,
            hospital_name=hospital_name,
            documents=documents,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to submit claim", exc) from exc


@router.get("/test-suite", response_model=dtos.TestSuiteCasesResponse)
async def list_test_suite_cases():
    """Return assignment test cases available for API-mode demo execution."""
    try:
        return claim_api_service.list_test_suite_cases()
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to list test suite cases", exc) from exc


@router.post("/test-suite/{case_id}/run", response_model=dtos.RunTestSuiteCaseResponse)
async def run_test_suite_case(
    case_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Create a real claim from one test-suite case and enqueue ingestion."""
    try:
        return await claim_api_service.run_test_suite_case(case_id=case_id, background_tasks=background_tasks, db=db)
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error(f"Failed to run test suite case {case_id}", exc) from exc


@router.get("/", response_model=dtos.ClaimsListResponse)
async def list_claims(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: str | None = None,
    date: str | None = None,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
):
    """Return paginated claim summaries with optional status and date filters."""
    try:
        return await claim_api_service.list_claims(
            db=db,
            page=page,
            page_size=page_size,
            status=status,
            date=date,
            month=month,
            year=year,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error("Failed to list claims", exc) from exc


@router.get("/{claim_id}/status", response_model=dtos.ClaimStatusResponse)
async def get_claim_status(claim_id: str, db: AsyncSession = Depends(get_db)):
    """Return claim status, decision, gating result, and trace spans."""
    try:
        return await claim_api_service.get_claim_status(claim_id=claim_id, db=db)
    except HTTPException:
        raise
    except Exception as exc:
        raise unexpected_error(f"Failed to load claim status for {claim_id}", exc) from exc
