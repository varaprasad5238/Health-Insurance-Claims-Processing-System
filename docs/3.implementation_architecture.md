# Implementation Architecture

## Plum Health Insurance - AI-Powered Claims Processing System

**Version:** 2.1  
**Date:** June 15, 2026  
**Status:** Implementation-Aligned Architecture

---

## 1. Executive Summary

This system automates OPD health insurance claim review for Plum. It accepts member claim submissions, stores uploaded documents locally, converts PDFs into page images, reads documents with a vision-capable LLM, gates invalid uploads early, extracts structured claim data, reconciles amounts, evaluates deterministic policy rules from `policy_terms.json`, synthesizes a member-facing decision, and records a full trace for audit and review.

The implementation follows a multi-agent pipeline. Each major stage owns a small responsibility, writes a trace span, and can fail independently. The policy decision itself is deterministic Python code; LLMs are used only for document understanding and final explanation wording.

---

## 2. Core Principles

**Traceability over convenience.**  
Every meaningful stage writes a row in `trace_spans`. The UI and eval report can reconstruct what happened by reading spans in order. Completed spans also write local JSON artifacts under the claim folder.

**Policy rules are code, not prompts.**  
Waiting periods, exclusions, limits, discounts, copay, and pre-auth checks are deterministic. The policy engine loads `policy_terms.json` through a cached Pydantic DTO and applies rules in Python.

**Failure is visible state.**  
Component failures become `ERROR`, `PARTIAL`, `GATING_FAILED`, or `MANUAL_REVIEW` states. The pipeline does not silently continue with unsafe assumptions.

**Use the right tool for the job.**  
Vision models read documents. Text models extract structured fields or write messages. Arithmetic and policy decisions are plain Python.

---

## 3. Runtime Architecture

```text
Next.js frontend
  -> FastAPI API gateway
  -> SQLite claims database
  -> local claim artifact storage
  -> background ingestion task

Ingestion task:
  1. VisionReaderStage          LLM vision call, parallel per uploaded page/image
  2. DocumentGatingStage        deterministic document-quality gate
  3. EntityExtractionStage      text LLM over transcripts
  4. AmountReconciliationStage  deterministic amount checks
  5. ClaimMergeStage            merge + confidence rollup
  6. PolicyEngine               deterministic policy decision
  7. DecisionSynthesisStage     LLM message wording with template fallback
  8. Final span + decision persistence
```

Uploads are handled by FastAPI. Each submitted file is saved under local storage. If the file is a PDF, PyMuPDF renders each page to PNG before vision processing. This means the LLM provider receives images, not raw PDF bytes.

---

## 4. Frontend

The frontend is **Next.js + TypeScript**.

Implemented screens:

- `/` dashboard: recent claims and entry points.
- `/submit`: OPD claim submission form.
- `/claims`: paginated claim history with status/date/month/year filters.
- `/claims/[id]`: live claim detail page with pipeline progress, decision, and trace spans.

Frontend validation:

- Claimed amount must be between `500` and `5000`.
- Maximum `4` files per claim.
- Maximum `3 MB` per file.
- Maximum `8 MB` total upload size.
- One PDF may contain multiple logical claim documents.

The frontend polls `GET /api/claims/{claim_id}/status` every 1.5 seconds until the claim reaches `DECIDED`, `MANUAL_REVIEW`, or `GATING_FAILED`.

---

## 5. Backend API

Implemented API endpoints:

```text
POST /api/claims/
GET  /api/claims/
GET  /api/claims/{claim_id}/status
GET  /api/claims/policies/members
GET  /health
```

`POST /api/claims/`:

- validates member and policy exist in seeded DB tables
- saves uploaded files locally
- converts PDFs into page images
- creates a claim row
- starts `run_claim_ingestion` as a FastAPI background task

`GET /api/claims/` supports pagination and filters: `page`, `page_size`, `status`, `date`, `month`, `year`.

---

## 6. Database Design

The implementation uses **SQLite + SQLAlchemy async**.

SQLite pragmas:

```text
PRAGMA journal_mode=WAL
PRAGMA foreign_keys=ON
PRAGMA busy_timeout=5000
```

Implemented tables:

```text
policies
members
claims
trace_spans
claim_decisions
gating_errors
```

Policy/member seeding:

- `policy_terms.json` is loaded at startup.
- One policy row is seeded into `policies`.
- Members and dependents are seeded into `members`.
- Dependents use `primary_member_id`; there is no separate dependents table.
- Policy and member rows include annual/full pledged amounts and remaining OPD amounts.

Claims reference:

```text
claims.member_id -> members.member_id
claims.policy_id -> policies.policy_id
```

---

## 7. Local Artifact Storage

Uploaded documents and intermediate outputs are stored locally under:

```text
backend/common/claims/{claim_id}/
  uploaded_documents/
  intermediate_outputs/
```

When a span finishes, the same trace data is written as JSON under `intermediate_outputs`. If a vision response fails schema validation, the raw model output is preserved in the span artifact for debugging.

`backend/common/` is ignored by git.

---

## 8. LLM Platform

LLM calls go through `backend/ai_platform`.

Primary concepts:

- `get_llm_response(...)` returns raw model text plus metadata.
- Workflow stages parse/validate raw output into their own Pydantic contracts.
- Provider fallback and circuit breaker live in `ai_platform`, not inside individual stages.

Supported providers:

- OpenAI
- Gemini
- Stub client for tests/local no-key execution

Example runtime configuration:

```env
LLM_PROVIDER=openai
VISION_MODEL=gpt-5
FALLBACK_LLM_PROVIDER=gemini
FALLBACK_VISION_MODEL=gemini-2.5-pro
```

Fallback behavior:

- primary provider/model is attempted first
- provider quota/auth/model/timeout/schema failures are normalized
- fallback provider/model is attempted next
- repeated primary failures open an in-process circuit for a cooldown period
- trace output includes `model_used`, `fallback_used`, and `primary_error`

---

## 9. Document Vision Contract

The first vision call returns a list of logical documents, because one uploaded file can contain multiple documents.

```python
class DocumentVisionListOutput(BaseModel):
    documents: list[DocumentVisionOutput]

class DocumentVisionOutput(BaseModel):
    document_type: Literal[
        "PRESCRIPTION", "HOSPITAL_BILL", "LAB_REPORT", "PHARMACY_BILL",
        "DENTAL_REPORT", "DISCHARGE_SUMMARY", "UNKNOWN"
    ]
    confidence: float
    readability: float
    patient_name_raw: str | None
    quality_flags: list[str]
    transcript: str
    source_file_name: str | None
    source_page_range: str | None
```

For a PDF containing a prescription on page 1 and a hospital bill on page 2, the model returns two items in `documents`. `VisionReaderStage` flattens logical documents across uploads before gating.

`source_page_range` accepts model outputs like `[1]` and coerces them to strings such as `"1"`.

---

## 10. Workflow Stage Responsibilities

### VisionReaderStage

- Runs per uploaded page/image.
- Uses `asyncio.gather()` for parallel classification/reading.
- Enforces max 5 prepared images per claim in backend.
- Calls `ai_platform.get_llm_response`.
- Parses raw LLM output into `DocumentVisionListOutput`.
- Writes raw output into trace artifacts if validation fails.

### DocumentGatingStage

- Consumes flattened `DocumentVisionOutput` rows.
- Loads required document types from `policy_terms.json`.
- Checks missing/wrong document types.
- Checks readability threshold `< 0.4`.
- Checks patient-name consistency using normalized edit distance.
- Writes `gating_errors` and sets claim to `GATING_FAILED` on failure.

### EntityExtractionStage

- Consumes transcripts from vision output.
- Uses text LLM to produce `StructuredExtractionOutput`.
- Extracts patient, doctor, diagnosis, date, hospital, line items, total amount, field confidences, and missing fields.

### AmountReconciliationStage

- Pure Python.
- Compares claimed amount, extracted total, and line-item sum.
- Emits discrepancy flags such as `TOTAL_MISMATCH` and `CLAIMED_AMOUNT_MISMATCH`.
- Emits fraud indicators for alteration/correction signals where available.

### ClaimMergeStage

- Merges entity and reconciliation results.
- Computes final extraction confidence from:
  - document confidence/readability
  - entity field confidence
  - reconciliation confidence
  - failed-stage penalties
  - discrepancy/fraud penalties

Current confidence formula:

```text
final = document_confidence * 0.35
      + entity_confidence * 0.45
      + reconciliation_confidence * 0.20
      - penalties
```

If confidence is below `0.65`, ingestion routes to `MANUAL_REVIEW`.

### PolicyEngine

- Pure Python.
- Uses cached `policy_terms.json` DTO via `get_policy()`.
- Applies member eligibility, policy window, minimum amount, waiting periods, exclusions, coverage, dental partial filtering, pre-auth checks, fraud hook, per-claim limit, network discount, and copay.
- Copay is read from policy config, not hardcoded.

### DecisionSynthesisStage

- LLM writes only `member_message` and `ops_summary`.
- It cannot change decision or amounts.
- Falls back to policy-engine template message if LLM fails.

---

## 11. Trace And Polling

Trace spans are stored in `trace_spans` and are the source of truth for the UI and eval report.

Span fields include:

```text
span_id
claim_id
agent_name
stage_order
started_at
ended_at
elapsed_ms
status
input_summary
output_summary
confidence_delta
errors
model_used
```

When a span finishes, the same data is written as JSON under `intermediate_outputs`.

The frontend polls every 1.5 seconds. Polling is used instead of WebSockets to keep the assignment demo simple and debuggable.

---

## 12. Policy Rules

Implemented policy rules include:

| Rule | Status |
|---|---|
| Member eligibility | Implemented |
| Policy active date window | Implemented |
| Minimum claim amount | Implemented |
| Initial waiting period | Implemented |
| Condition-specific waiting period | Implemented |
| Exclusion check | Implemented |
| Coverage category check | Implemented |
| Dental line-item filtering | Implemented |
| Pre-auth check | Implemented |
| Same-day fraud hook | Implemented as input hook |
| Per-claim limit | Implemented |
| Annual limit | Present but skipped unless YTD input is provided |
| Network discount | Implemented |
| Copay application | Implemented from policy config |

Smoke-tested outcomes:

```text
Clean consultation -> APPROVED 1350.00
Diabetes waiting period -> REJECTED WAITING_PERIOD
Dental mixed line items -> PARTIAL 8000.00
Per-claim exceeded -> REJECTED PER_CLAIM_EXCEEDED
Network hospital -> APPROVED 3240.00
```

---

## 13. Technology Stack

| Layer | Current implementation |
|---|---|
| Frontend | Next.js + TypeScript |
| Backend | FastAPI |
| Async execution | FastAPI `BackgroundTasks` |
| Database | SQLite + SQLAlchemy async |
| Policy/member seed | `policy_terms.json` -> SQLite tables |
| LLM providers | OpenAI primary, Gemini fallback, stub for tests |
| PDF preprocessing | PyMuPDF -> PNG page images |
| File storage | Local `backend/common/claims` |
| Trace storage | SQLite `trace_spans` + JSON artifacts |
| Validation | Pydantic |

---

## 14. Current Gaps

The implementation is end-to-end but not fully final. Remaining gaps:

- Eval runner for all 12 test cases is not implemented yet.
- TC011 simulated component failure is not wired into API/eval flow yet.
- Same-day claim count and YTD claim amount are not computed from DB claim history yet.
- Annual limit currently skips unless YTD input is supplied.
- UI does not yet expose local artifact file paths.
- Some old provider/reference scaffolding can be cleaned before final submission.

---

## 15. Scale Considerations

The current implementation is intentionally demo-friendly:

- SQLite is sufficient for local/single-user assignment demo.
- FastAPI background tasks are sufficient for short-running demo claims.
- Local filesystem storage is sufficient for local review.

At higher scale:

- replace background tasks with a queue or event stream
- move SQLite to PostgreSQL
- move local files to S3-compatible object storage
- add claim-history aggregation for fraud/YTD tracking
- add rate limiting and provider-level budget controls
- consider self-hosted OCR/VLM models for high-volume document processing

---

## 16. Conscious Trade-Offs

- Skipped LangChain/Agno for the core pipeline to keep claims processing deterministic and testable.
- Kept `trace_spans` as the audit source of truth rather than LangSmith.
- Used direct provider SDKs through `ai_platform` to retain control over JSON parsing, fallback, and trace metadata.
- Used local SQLite/local file storage for assignment speed.
- Kept deterministic policy engine separate from LLM outputs.
- Supported multi-logical-document uploads by returning `documents: [...]` from the vision contract.

---