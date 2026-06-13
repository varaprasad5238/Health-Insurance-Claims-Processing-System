# System Design Document

## Plum Health Insurance - AI-Powered Claims Processing System

**Version:** 1.1  
**Date:** June 14, 2026  
**Status:** Proposed Architecture

---

## 1. Executive Summary

This document describes the architecture of an AI-powered claims processing system for Plum's OPD health insurance product. The system ingests member-uploaded medical documents such as hospital bills, prescriptions, lab reports, and pharmacy bills, extracts structured data using vision-language models, evaluates claims against deterministic policy rules, and produces explainable, auditable decisions.

The design optimizes for three outcomes:

- Every claim decision is reconstructible from its trace without reading code.
- Policy rules are evaluated by deterministic code and never by an LLM.
- Failures degrade gracefully into visible, logged states rather than crashes or silent wrong answers.

---

## 2. Design Philosophy

### Principle 1 - Traceability over convenience

- Every processing stage emits a named, typed trace span.
- A claim's full decision history can be reconstructed by querying spans in order.
- The trace system is a core pipeline feature, not an observability layer added later.
- Trace summaries avoid raw document bytes and minimize PHI/PII exposure.

### Principle 2 - Policy rules are code, not prompts

- Waiting periods are date arithmetic.
- Sub-limits and claim limits are numeric comparisons.
- Exclusions are deterministic list and pattern checks.
- If these rules live inside an LLM prompt, decisions become non-deterministic and hard to audit.
- The policy engine is pure Python, loads `policy_terms.json`, and emits a named `RuleResult` for every rule evaluated, skipped, or failed.

### Principle 3 - Failure is a first-class state

- Every agent is wrapped in a timeout and fallback path.
- A failed agent logs a trace span with `ERROR`, `TIMEOUT`, or `SKIPPED` status.
- The pipeline continues with partial data wherever possible.
- Confidence is reduced when components fail.
- If confidence drops below the configured hard threshold, the claim routes to `MANUAL_REVIEW`.
- If confidence remains acceptable, the policy decision can still be returned with a manual-review recommendation note.

---

## 3. High-Level Architecture

The system follows a staged pipeline architecture with six processing agents, a deterministic policy engine, and a cross-cutting trace layer.

```text
Member Upload
    |
    v
Next.js Frontend
    |
    | POST /api/claims
    v
FastAPI Gateway
    |
    v
Document Gating Agent  -- fail --> specific re-upload / correction message
    |
    | pass
    v
PDF/Image Preprocessor
    |
    v
OCR / Vision Extraction Agent
    |
    v
Parallel Structured Processing
    |-- Entity Extraction Agent
    |-- Amount Reconciler Agent
    |
    v
Orchestrator Agent
    |
    | extraction_confidence < hard threshold
    |----> MANUAL_REVIEW
    |
    v
Deterministic Policy Rule Engine
    |
    v
Decision Synthesis Agent
    |
    v
Final Claim Decision + Trace
```

### Processing stages

- **Stage 1 - Claim intake:** Accept member details, claim category, claimed amount, treatment date, and uploaded documents.
- **Stage 2 - Document gating:** Validate document types, readability, required document set, and patient consistency before extraction begins.
- **Stage 3 - Preprocessing:** Use PyMuPDF for PDF loading, page rendering, page splitting, metadata extraction, and image preparation.
- **Stage 4 - OCR / vision extraction:** Use a vision-language model to produce a faithful transcript and structured extraction candidates.
- **Stage 5 - Structured processing:** Entity extraction and amount reconciliation run from the OCR/vision output.
- **Stage 6 - Orchestration:** Merge outputs, resolve conflicts, compute confidence, and prepare a `MergedClaim`.
- **Stage 7 - Policy evaluation:** Run deterministic rules loaded from `policy_terms.json`.
- **Stage 8 - Decision synthesis:** Convert rule results into a member-facing decision and an operations summary.
- **Cross-cutting - Trace emission:** Every agent emits trace spans through a common tracing interface.

---

## 4. Component Inventory

### 4.1 Next.js Frontend

**Purpose:** Provide claim submission, upload progress, decision display, and trace review UI.

**Why Next.js:**

- Supports a production-grade React frontend with clean routing and layouts.
- Makes it easy to build separate member-facing and ops-facing pages.
- Can host lightweight API route proxies if needed, while keeping claim processing in FastAPI.
- Provides a strong structure for demo workflows and future deployment.

**Main screens:**

- `SubmitClaim`: member details, claim category, treatment date, claimed amount, and document upload.
- `ClaimStatus`: processing status and final member-facing decision.
- `ClaimDetail`: decision breakdown, approved amount, rejection reasons, confidence score, and trace ID.
- `TraceViewer`: expandable stage-by-stage trace for operations review.

---

### 4.2 FastAPI Gateway

**Purpose:** Own backend request validation, file handling, and pipeline dispatch.

**Responsibilities:**

- Accept claim submissions from the Next.js frontend.
- Validate required metadata and file formats.
- Store uploaded files behind a storage interface.
- Create a claim record and trace ID.
- Dispatch processing to the claims pipeline.
- Return early gating errors or final decision output.

---

### 4.3 Document Gating Agent

**Purpose:** Validate uploaded documents before claim extraction starts.

**Trigger:** Every new claim submission.

**What it does:**

- Classifies each uploaded document type using a vision model call.
- Checks detected document types against `document_requirements[claim_category].required` from `policy_terms.json`.
- Rejects unreadable documents with a specific re-upload request.
- Verifies patient name consistency across documents using normalized fuzzy matching.
- Stops the pipeline before decisioning when documents are wrong, missing, unreadable, or mismatched.

**Input:**

- Claim category
- Uploaded document files
- Member name
- Member ID

**Output on success:**

- Typed document list with detected type, confidence, readability score, and patient name if found.

**Output on failure:**

- Structured error with:
  - `error_code`: `WRONG_TYPE`, `UNREADABLE`, `PATIENT_MISMATCH`, or `MISSING_REQUIRED`
  - specific member-facing message
  - detected document types
  - required document types
  - affected file IDs

**Example messages:**

- `You uploaded two prescriptions, but a consultation claim requires one prescription and one hospital bill. Please upload your clinic invoice or receipt.`
- `The pharmacy bill image is too blurry to read. Please re-upload a clearer photo of the pharmacy bill.`
- `The prescription is in the name of Rajesh Kumar, but the hospital bill is in the name of Arjun Mehta. Please upload documents for the same patient.`

---

### 4.4 PDF/Image Preprocessor

**Purpose:** Prepare documents for vision-model extraction.

**Responsibilities:**

- Load PDFs and images.
- Render PDF pages to images using PyMuPDF.
- Extract basic metadata such as page count and file type.
- Flag multi-page documents.
- Normalize image orientation and page boundaries where possible.

**Important trade-off:**

- For the assignment demo, multi-page support can be limited, but the interface should support page-level processing so it can be extended later.

---

### 4.5 OCR / Vision Extraction Agent

**Purpose:** Extract raw text and initial structured fields from noisy Indian medical documents.

**Architecture - Two-call pipeline:**

- **Call 1 - Faithful reading:** The model transcribes visible document content. It marks unclear regions as `[UNCLEAR]` and stamp-obscured regions as `[STAMP_OBSCURED]`. It does not infer missing values.
- **Call 2 - Structured extraction:** The model extracts typed fields from the transcript and image context. If a required field is unclear, it returns `null` with low confidence instead of guessing.

**Output:**

- Raw transcript
- Extracted field candidates
- Field-level confidence scores
- Document quality flags:
  - `HANDWRITTEN`
  - `STAMP_OVER_TEXT`
  - `LOW_CONTRAST`
  - `PARTIAL_PAGE`
  - `MULTILINGUAL`
  - `ALTERATION_MARK`

**Why not traditional OCR alone:**

- Traditional OCR tools struggle with handwritten prescriptions, rubber stamps, phone-captured documents, and mixed-language Indian medical documents.
- A vision-language model can use layout and visual context directly instead of relying only on character-level recognition.

---

### 4.6 Entity Extraction Agent

**Purpose:** Parse structured medical and billing fields from the OCR/vision output.

**Dependency:** Runs after the OCR/Vision Extraction Agent. It can run in parallel with Amount Reconciler once the OCR/vision output is available.

**Extracted fields:**

- Patient name
- Doctor name
- Doctor registration number
- Primary diagnosis
- Treatment date
- Hospital or clinic name
- Network hospital candidate
- Itemized line items
- Total claimed amount
- Coverage hints for line items

**Validation examples:**

- Doctor registration regex examples: `KA/45678/2015`, `GJ/56789/2014`, `AYUR/KL/2345/2019`.
- Treatment date should match or be close to the submitted treatment date.
- Patient name should match member/dependent records or previously gated document names.

---

### 4.7 Amount Reconciler Agent

**Purpose:** Check financial consistency and identify amount-related fraud signals.

**Dependency:** Runs after the OCR/Vision Extraction Agent. It can run in parallel with Entity Extraction.

**What it verifies:**

- Bill total equals the sum of itemized line items.
- Claimed amount matches the amount visible on the bill.
- Amount corrections, overwrites, or white-out marks are flagged.
- Multiple bills or duplicate-looking documents are identified when visible.

**Output:**

- Extracted totals
- Reconciliation status
- Discrepancy flags
- Fraud indicators
- Confidence impact

---

### 4.8 Orchestrator Agent

**Purpose:** Merge extraction outputs into a single `MergedClaim`, resolve conflicts, and compute aggregate extraction confidence.

**Responsibilities:**

- Merge OCR, entity, and reconciliation outputs.
- Resolve conflicts with deterministic precedence.
- Produce a conflict log for the trace.
- Compute extraction confidence.
- Decide whether extraction quality is sufficient for policy evaluation.

**Conflict resolution example:**

- If a prescription and bill disagree on amount, the bill amount is preferred.
- The disagreement is logged as a conflict and confidence is reduced.

**Confidence formula:**

```text
field_conf = weighted_average(field_confidences)

weights:
  amount = 0.30
  patient_name = 0.25
  diagnosis = 0.20
  doctor = 0.15
  treatment_date = 0.10

agent_penalty = 0.15 * number_of_failed_agents

extraction_confidence = max(0.0, field_conf - agent_penalty)
```

**Threshold behavior:**

- `< 0.65`: force `MANUAL_REVIEW`.
- `0.65 - 0.85`: continue policy evaluation with a caution flag.
- `> 0.85`: continue policy evaluation as high confidence.

**TC011 behavior:**

- A simulated component failure should not automatically force `MANUAL_REVIEW`.
- If enough information remains and policy rules pass, the system returns `APPROVED` with reduced confidence and a manual-review recommendation note.
- This matches the assignment expectation for graceful degradation.

---

### 4.9 Policy Rule Engine (Deterministic - No LLM)

**Purpose:** Evaluate the merged claim against policy rules from `policy_terms.json`.

**Design:**

- Rules are pure Python functions.
- The engine loads and validates `policy_terms.json` with Pydantic at startup.
- Every rule returns a `RuleResult` with:
  - rule ID
  - outcome: `PASS`, `FAIL`, `PARTIAL`, or `SKIP`
  - reason
  - approved amount impact
  - deduction amount
  - trace metadata

**Evaluation strategy:**

- Rules are evaluated in a deterministic order.
- Terminal failures determine the final decision, but skipped downstream rules still emit `SKIP` results for trace completeness.
- Where possible, non-dependent checks continue so the operations team can see all relevant findings.
- Category-specific adjudication can run before global amount gates when required by expected test-case behavior.

**Policy precedence assumptions for this assignment:**

- `test_cases.json` expected outcomes are treated as the source of truth where policy fields are ambiguous.
- Dental mixed line items are adjudicated at line-item level before applying whole-claim rejection logic.
- For TC006, root canal is approved and teeth whitening is excluded, resulting in `PARTIAL` approval of INR 8,000.
- For TC010, network discount is applied before copay, matching the expected approved amount of INR 3,240.
- Consultation sub-limit handling is interpreted to match the test cases, since TC010 expects approval on a consultation claim above the configured consultation sub-limit.

**Rule evaluation order:**

| # | Rule | What it checks | Related case |
|---|------|----------------|--------------|
| 1 | Member eligibility | Member exists, policy active, treatment date inside policy window | - |
| 2 | Submission deadline | Claim submitted within configured deadline | - |
| 3 | Minimum claim amount | Claimed amount is at least configured minimum | - |
| 4 | Initial waiting period | Initial waiting period elapsed from join date | - |
| 5 | Condition-specific waiting | Diagnosis-specific waiting period, such as diabetes | TC005 |
| 6 | Exclusion check | Diagnosis/treatment/line item is excluded | TC012 |
| 7 | Coverage category check | Claim category is covered | - |
| 8 | Dental line-item filter | Approve covered dental items and reject excluded dental items individually | TC006 |
| 9 | Pre-authorization check | High-value MRI/CT/PET pre-auth present when required | TC007 |
| 10 | Fraud signal check | Same-day claim count and other fraud thresholds | TC009 |
| 11 | Per-claim limit | Claimed/adjudicated amount compared against configured per-claim limit | TC008 |
| 12 | Annual limit | YTD amount plus current approved amount within annual OPD limit | - |
| 13 | Network hospital discount | Apply network discount for configured network hospitals | TC010 |
| 14 | Copay application | Apply category copay after discounts | TC004, TC010 |

**Critical calculation order for TC010:**

```text
INR 4,500 * 0.80 network discount = INR 3,600
INR 3,600 * 0.90 after 10% copay = INR 3,240 approved
```

---

### 4.10 Decision Synthesis Agent

**Purpose:** Produce the final structured verdict, member-facing explanation, and operations summary.

**Important boundary:**

- This agent does not make the claim decision.
- The deterministic policy engine already decided the outcome.
- The synthesis agent only verbalizes `MergedClaim`, `RuleResult`, confidence, and trace data.
- It cannot introduce new facts, amounts, rules, or rejection reasons.

**Output:**

- Decision: `APPROVED`, `PARTIAL`, `REJECTED`, or `MANUAL_REVIEW`
- Approved amount
- Copay deducted
- Network discount applied
- Rejection reasons
- Partial line-item decisions
- Member message
- Operations summary
- Confidence score
- Manual-review note when applicable
- Trace ID

**Fallback:**

- If the LLM call times out or returns invalid output, the system falls back to a template-based verdict constructed directly from rule results.

---

### 4.11 Trace Emitter

**Purpose:** Record every meaningful processing step in a reconstructible audit trail.

**Each `TraceSpan` includes:**

- Span ID
- Claim ID
- Agent name
- Start and end timestamps
- Elapsed milliseconds
- Input summary
- Output summary
- Confidence delta
- Error list
- Status: `SUCCESS`, `PARTIAL`, `TIMEOUT`, `ERROR`, `SKIPPED`, or `FALLBACK`

**Privacy controls:**

- Trace spans store summaries, not raw document bytes.
- Raw OCR text is minimized or stored separately with stricter access controls.
- PHI/PII in trace summaries is reduced to what is needed for explainability.
- For patient mismatch, the trace can store detected names because the mismatch itself must be explainable, but raw full-document content should not be duplicated across spans.

**Reconstruction query:**

```sql
SELECT *
FROM trace_spans
WHERE claim_id = ?
ORDER BY started_at;
```

---

## 5. Core Data Models

```text
Claim
|-- claim_id: str
|-- member_id: str
|-- policy_id: str
|-- claim_category: ClaimCategory
|-- treatment_date: date
|-- submission_date: date
|-- claimed_amount: Decimal
|-- hospital_name: str | None
|-- status: PENDING | PROCESSING | DECIDED | MANUAL_REVIEW
|-- decision: ClaimDecision | None
|-- trace_id: str

ClaimDecision
|-- decision: APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW
|-- approved_amount: Decimal
|-- copay_deducted: Decimal
|-- network_discount_applied: Decimal
|-- rejection_reasons: list[RejectionReason]
|-- partial_items: list[LineItemDecision] | None
|-- member_message: str
|-- ops_summary: str
|-- confidence_score: float
|-- manual_review_note: str | None
|-- trace_id: str

RuleResult
|-- rule_id: str
|-- outcome: PASS | FAIL | PARTIAL | SKIP
|-- reason: str
|-- approved_amount_delta: Decimal | None
|-- deducted_amount: Decimal | None
|-- metadata: dict

TraceSpan
|-- span_id: str
|-- claim_id: str
|-- agent_name: str
|-- started_at: datetime
|-- ended_at: datetime
|-- elapsed_ms: int
|-- input_summary: dict
|-- output_summary: dict
|-- confidence_delta: float | None
|-- errors: list[str]
|-- status: SUCCESS | PARTIAL | TIMEOUT | ERROR | SKIPPED | FALLBACK
```

---

## 6. Component Contracts

### DocumentIntelligenceProvider

**Input:**

- Rendered document image or page image
- Prompt type: `CLASSIFY`, `READ`, or `EXTRACT`
- Expected JSON schema
- Timeout in seconds

**Output:**

- JSON payload matching the requested schema
- Model name
- Latency
- Confidence if available
- Raw provider status

**Errors:**

- `ProviderTimeout`
- `InvalidModelOutput`
- `ProviderUnavailable`
- `UnsupportedFileType`

**Fallback behavior:**

- Retry once for invalid JSON using a schema-repair prompt.
- If retry fails, return partial extraction with reduced confidence.

### PolicyEngine

**Input:**

- `MergedClaim`
- Loaded `PolicyTerms`
- Member record
- Claim history

**Output:**

- Ordered list of `RuleResult`
- Final policy outcome
- Approved amount before final message synthesis

**Errors:**

- `PolicyConfigInvalid`
- `MemberNotFound`
- `RuleEvaluationError`

**Fallback behavior:**

- Configuration errors force `MANUAL_REVIEW` and emit a policy trace span.
- Rule-level errors are captured as failed rule results when possible.

### DecisionSynthesizer

**Input:**

- `MergedClaim`
- `list[RuleResult]`
- Confidence score
- Trace ID

**Output:**

- `ClaimDecision`

**Errors:**

- `DecisionTemplateError`
- `InvalidModelOutput`
- `ProviderTimeout`

**Fallback behavior:**

- Template-based decision generated directly from rule results.

---

## 7. Failure Handling Matrix

| Failure Type | System Behavior | Trace Record | Confidence Impact |
|--------------|-----------------|--------------|-------------------|
| Gating model timeout | Ask member to retry upload validation or route to manual intake | `gating_agent: TIMEOUT` | No decision made |
| OCR agent timeout | Proceed with low-confidence empty OCR result if other structured data exists | `ocr_agent: TIMEOUT` | -0.20 |
| Entity agent error | Proceed with null fields where possible | `entity_agent: ERROR` | -0.15 |
| Amount reconciler timeout | Skip reconciliation | `reconciler: SKIPPED` | -0.10 |
| One extraction agent fails | Continue if required fields remain available | failed agent span + orchestrator span | Reduced confidence |
| All extraction agents fail | Route to `MANUAL_REVIEW` | `extraction_confidence: 0` | Forces manual review |
| Policy engine exception | Catch, log, route to `MANUAL_REVIEW` | `policy_engine: ERROR` | Forces manual review |
| Decision LLM timeout | Use template verdict from rule results | `decision_agent: FALLBACK` | -0.05 |
| Invalid LLM JSON | Retry once, then fallback to partial result | `provider: INVALID_JSON` | -0.05 to -0.15 |

---

## 8. Test Case Resolution Map

| Case | Description | Resolution Stage | Key Check | Expected Outcome |
|------|-------------|------------------|-----------|------------------|
| TC001 | Wrong document type uploaded | Document Gating | Second doc is prescription, not hospital bill | Stop before decision with re-upload instruction |
| TC002 | Unreadable document | Document Gating | Pharmacy bill unreadable | Re-upload request |
| TC003 | Patient name mismatch | Document Gating | Patient names differ across docs | Stop before decision with mismatch details |
| TC004 | Clean consultation claim | Policy Engine | Rules pass, 10% copay applied | `APPROVED` - INR 1,350 |
| TC005 | Diabetes within waiting period | Policy Engine | 90-day diabetes waiting period not complete | `REJECTED` |
| TC006 | Dental mixed line items | Policy Engine | Root canal covered, whitening excluded | `PARTIAL` - INR 8,000 |
| TC007 | MRI without pre-auth | Policy Engine | MRI above threshold requires pre-auth | `REJECTED` |
| TC008 | Per-claim limit exceeded | Policy Engine | INR 7,500 exceeds INR 5,000 limit | `REJECTED` |
| TC009 | Suspicious same-day claims | Policy Engine | Same-day claim pattern exceeds threshold | `MANUAL_REVIEW` |
| TC010 | Network hospital claim | Policy Engine | Discount first, then copay | `APPROVED` - INR 3,240 |
| TC011 | Simulated component failure | Orchestrator + Trace | Continue with reduced confidence | `APPROVED` with manual-review note |
| TC012 | Excluded condition | Policy Engine | Obesity/bariatric treatment excluded | `REJECTED` |

---

## 9. Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Frontend | Next.js + TypeScript | Structured React app, routing, layouts, demo-friendly deployment |
| Backend framework | FastAPI (Python) | Async-native and well-suited for AI/IO-heavy workloads |
| Agent orchestration | Custom thin framework | Keeps traces fully owned and avoids heavy abstraction overhead |
| Vision-language model | Gemini 2.5 Pro | Strong multimodal document understanding; swappable behind provider interface |
| PDF preprocessing | PyMuPDF | Lightweight PDF loading, page splitting, and rendering to images |
| Task queue | Celery + Redis | Async claim processing and retry support |
| Database | PostgreSQL | Claims, traces, documents, and decisions stored relationally |
| File storage | Local S3-compatible interface | Simple local demo with future S3 migration path |
| Schema validation | Pydantic | Typed contracts between agents and runtime validation of model outputs |
| Testing | pytest | Test policy rules, gating, confidence, and all 12 assignment cases |

**Model provider abstraction:** The vision-language model sits behind `DocumentIntelligenceProvider`, so the system can later swap to GPT-4o, Claude, Azure Document Intelligence, AWS Textract, PaddleOCR-VL, DeepSeek-OCR, or olmOCR without changing the rest of the pipeline.

---

## 10. Project Structure

```text
plum-claims/
|-- backend/
|   |-- agents/
|   |   |-- gating.py
|   |   |-- ocr.py
|   |   |-- entity.py
|   |   |-- reconciler.py
|   |   |-- orchestrator.py
|   |   |-- decision.py
|   |-- policy/
|   |   |-- engine.py
|   |   |-- loader.py
|   |   |-- rules/
|   |       |-- eligibility.py
|   |       |-- waiting_periods.py
|   |       |-- limits.py
|   |       |-- exclusions.py
|   |       |-- copay_discount.py
|   |       |-- fraud.py
|   |-- models/
|   |   |-- claim.py
|   |   |-- member.py
|   |   |-- extraction.py
|   |   |-- policy.py
|   |   |-- decision.py
|   |-- providers/
|   |   |-- base.py
|   |   |-- gemini.py
|   |   |-- stub.py
|   |-- tracing/
|   |   |-- decorator.py
|   |   |-- span.py
|   |   |-- store.py
|   |-- api/
|   |   |-- routes.py
|   |   |-- middleware.py
|   |-- tests/
|       |-- test_policy_engine.py
|       |-- test_gating.py
|       |-- test_confidence.py
|       |-- fixtures/
|-- frontend/
|   |-- app/
|   |   |-- page.tsx
|   |   |-- submit/
|   |   |   |-- page.tsx
|   |   |-- claims/
|   |       |-- [claimId]/
|   |           |-- page.tsx
|   |-- components/
|   |   |-- ClaimForm.tsx
|   |   |-- DecisionCard.tsx
|   |   |-- TraceViewer.tsx
|   |   |-- ConfidenceBadge.tsx
|   |-- lib/
|       |-- api.ts
|       |-- types.ts
|-- assignment/
|   |-- policy_terms.json
|   |-- test_cases.json
|   |-- sample_documents_guide.md
|-- docs/
|   |-- research.md
|   |-- system_design.md
```

---

## 11. Scale Considerations

The current assignment version targets a demo-scale system that can process the provided 12 test cases and a small number of uploaded claims. At higher scale, the extraction layer becomes the primary bottleneck.

### Current scale

- FastAPI can handle claim intake and status requests.
- Celery + Redis can process claims asynchronously.
- PostgreSQL is sufficient for claims, decisions, and trace spans.
- Gemini API calls are acceptable for low-volume evaluation.

### 10x and production scale changes

- Add idempotency keys for claim submissions.
- Add queue backpressure and retry limits.
- Add dead-letter queues for failed jobs.
- Partition trace tables by month or claim creation date.
- Cache member and policy lookups.
- Add provider-level rate-limit handling.
- Batch non-urgent extraction work where possible.
- Consider self-hosted OCR/VLM models such as PaddleOCR-VL, DeepSeek-OCR, or olmOCR once volume justifies GPU infrastructure.
- Move from Celery to Kafka or another event-streaming model when each pipeline stage needs independent scaling.

---

## 12. Conscious Trade-offs

### Included despite time constraints

- Full trace system, because observability is central to evaluation.
- Deterministic policy engine, because claim decisions must be auditable.
- Typed schemas for component boundaries.
- Early document gating for incorrect, missing, unreadable, or mismatched documents.
- Vision-language model integration behind a swappable provider interface.

### Excluded for the 2-3 day assignment timeline

- Full production auth and multi-tenant access controls.
- Real S3 deployment, replaced by local storage behind an S3-compatible interface.
- Complete multi-page PDF aggregation, though the preprocessor contract supports it.
- Real pre-authorization lookup API, inferred from uploaded documents for the assignment.
- Self-hosted OCR/VLM deployment, due to local GPU and infrastructure constraints.

### Configurable, not hardcoded

- Confidence thresholds.
- Provider timeouts.
- Retry counts.
- Document readability threshold.
- Policy-rule behavior loaded from `policy_terms.json` where possible.

---

## 13. Final Notes

This architecture intentionally uses LLMs where they are strongest: visual document understanding, extraction, and explanation. It keeps policy adjudication in deterministic code, keeps failures visible, and keeps the frontend implementation practical with Next.js.
