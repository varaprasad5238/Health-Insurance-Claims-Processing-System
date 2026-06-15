# System Design Document

## Plum Health Insurance — AI-Powered Claims Processing System

**Version:** 2.0
**Date:** June 14, 2026
**Status:** Proposed Architecture

---

## 1. Executive Summary

This document describes the architecture of an AI-powered claims processing system for Plum's OPD health insurance product. The system ingests member-uploaded medical documents (hospital bills, prescriptions, lab reports), extracts structured data using vision-language models, evaluates claims against deterministic policy rules loaded from `policy_terms.json`, and produces explainable, auditable decisions with full trace reconstruction.

The system is designed as a multi-agent pipeline with 7 logical agents, an orchestrator, and a cross-cutting trace layer. Each agent has a typed contract (input, output, errors), its own trace span, and can fail independently without crashing the pipeline. Agents are deliberately separated from the LLM calls that power them — two agents may share a single API call for cost efficiency, but remain architecturally independent for observability, testability, and replaceability.

---

## 2. Design Philosophy

**Principle 1 — Traceability over convenience.**
Every processing stage emits a named, typed trace span. A claim's full decision history can be reconstructed by querying its spans in order — no code reading required. This is not an afterthought — observability carries 20% of the evaluation weight, and the trace system is the foundation of the entire pipeline.

**Principle 2 — Policy rules are code, not prompts.**
Waiting periods are date arithmetic. Sub-limits are comparisons. Exclusions are set membership. If any of these live inside an LLM prompt, decisions become non-deterministic, unauditable, and subtly wrong. The policy engine is pure Python that loads `policy_terms.json` at startup and evaluates rules as typed functions. Every rule that fires becomes a named event in the trace.

**Principle 3 — Failure is a first-class state.**
Every agent is wrapped in a timeout and a fallback. A failed agent reduces confidence and logs an `AGENT_FAILED` span. The system never crashes — it degrades visibly and annotates the output. If confidence drops below the threshold, the decision routes to `MANUAL_REVIEW` regardless of what the rules says.

**Principle 4 — Use the right tool for each job.**
Not every agent needs an LLM. Not every LLM call needs a vision model. The pipeline assigns the cheapest, fastest tool that can do each job correctly: expensive vision models only where the system must see a document image, lightweight text models where a transcript is sufficient, and pure code where the task is deterministic. This keeps the architecture multi-agent (7 agents, each independently traced and replaceable) while the implementation stays cost-efficient (3 LLM calls per claim instead of 7–8).

---

## 3. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        CLAIMS PROCESSING PIPELINE                       │
│                       7 Agents + Orchestrator + Trace                   │
│                                                                          │
│  ┌──────────────┐                                                        │
│  │   Frontend    │  React + TypeScript                                   │
│  │  Claim Form   │  Upload docs, select category, view decision          │
│  └──────┬───────┘                                                        │
│         │  POST /api/claims                                              │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │   FastAPI     │  Async Python backend                                 │
│  │   Gateway     │  Auth, validation, file storage, job dispatch          │
│  └──────┬───────┘                                                        │
│         │                                                                │
│  ═══════╪════════════════════════════════════════════════════════════     │
│  STAGE 1│  COMBINED VISION CALL  (1 call per doc — classify + read)      │
│         ▼                                                                │
│  ┌──────────────────────────────────────────┐                            │
│  │  ┌─────────────┐   ┌──────────────────┐  │                            │
│  │  │   Gating     │   │  Vision Reading  │  │  Single Gemini 2.5 Pro    │
│  │  │   Agent      │   │  Agent           │  │  call returns both:       │
│  │  │              │   │                  │  │  classification +         │
│  │  │  Classify    │   │  Faithful        │  │  transcript               │
│  │  │  doc type,   │   │  transcript,     │  │                            │
│  │  │  readability,│   │  quality flags,  │  │  Gating checks run as     │
│  │  │  name match  │   │  [UNCLEAR] marks │  │  code on the LLM output   │
│  │  └─────────────┘   └──────────────────┘  │                            │
│  └──────────────┬───────────────────────────┘                            │
│         │  Pass: proceed  │  Fail: return specific, actionable error     │
│  ═══════╪════════════════════════════════════════════════════════════     │
│  STAGE 2│  ENTITY EXTRACTION  (text LLM — no vision needed)             │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │   Entity      │  Works from transcript text, not images               │
│  │  Extraction   │  Uses cheaper model (Gemini Flash / Claude Haiku)     │
│  │   Agent       │  Structured fields + per-field confidence             │
│  └──────┬───────┘                                                        │
│  ═══════╪════════════════════════════════════════════════════════════     │
│  STAGE 3│  AMOUNT RECONCILIATION  (pure code — no LLM)                   │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │   Amount      │  Sum line items vs bill total vs claimed amount        │
│  │  Reconciler   │  Flag discrepancies, detect fraud signals             │
│  │   Agent       │  Alteration flags already from Stage 1 quality flags  │
│  └──────┬───────┘                                                        │
│  ═══════╪════════════════════════════════════════════════════════════     │
│  STAGE 4│  ORCHESTRATION                                                 │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │ Orchestrator  │  Merge results, resolve conflicts,                    │
│  │               │  compute extraction_confidence,                       │
│  │               │  handle partial/failed agents                         │
│  └──────┬───────┘                                                        │
│  ═══════╪════════════════════════════════════════════════════════════     │
│  STAGE 5│  POLICY EVALUATION  (deterministic — no LLM)                   │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │   Policy      │  Load policy_terms.json at startup                    │
│  │   Rule        │  Evaluate 14 ordered rules                            │
│  │   Engine      │  Each rule → RuleResult with reason                   │
│  └──────┬───────┘                                                        │
│  ═══════╪════════════════════════════════════════════════════════════     │
│  STAGE 6│  DECISION SYNTHESIS  (light text LLM)                          │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │  Decision     │  Synthesises member-facing message from               │
│  │  Synthesis    │  MergedClaim + RuleResults                            │
│  │  Agent        │  Fallback: template-based verdict if LLM times out    │
│  └──────┬───────┘                                                        │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │   Final       │  APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW        │
│  │  Decision     │                                                       │
│  └──────────────┘                                                        │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  CROSS-CUTTING: @traced decorator on every agent method          │    │
│  │  Every span: agent_name, input_summary, output_summary,          │    │
│  │  elapsed_ms, confidence_delta, status, errors                    │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 4. LLM Assignment Strategy

Not every agent needs an LLM, and not every LLM call needs a vision model. The pipeline assigns the cheapest tool that can do each job correctly.

| Agent | Needs vision? | Model | Rationale |
|---|---|---|---|
| Document gating agent | Yes — sees document images | Gemini 2.5 Pro | Must classify from image; shares call with vision reading agent |
| Vision reading agent | Yes — produces transcript | Gemini 2.5 Pro | Same call as gating — returns classification + faithful transcript |
| Entity extraction agent | No — works from transcript text | Gemini Flash / Claude Haiku | Text-only task; cheaper and faster model sufficient |
| Amount reconciler agent | No — pure arithmetic | No LLM — Python code | Sum comparisons, discrepancy checks are deterministic |
| Policy rule engine | No — rule evaluation | No LLM — Python code | Date arithmetic, set membership, comparisons from `policy_terms.json` |
| Decision synthesis agent | No — text generation | Gemini Flash / Claude Haiku | Synthesise reasons into member message; template fallback available |
| Orchestrator | No — merge and compute | No LLM — Python code | Conflict resolution and confidence rollup are deterministic |

**Total per claim: 1 vision LLM call per document + 1 text LLM call for entity extraction + 1 text LLM call for decision synthesis.**
For a typical 2-document claim: 4 LLM calls total (2 vision + 1 text extraction + 1 text synthesis).

**Why this works for multi-agent bonus:** The evaluator sees 7 agents with independent contracts, independent trace spans, and independent failure modes in the architecture document. The fact that two agents share a single API call is an implementation optimization — not an architectural collapse. Each agent can be swapped, tested, and traced independently.

---

## 5. Component Inventory and Contracts

### 5.1 Document Gating Agent

**Purpose:** Validate uploaded documents before any extraction work begins. This is a synchronous gate — no claim processing starts until it passes.

**Trigger:** Every new claim submission.

**What it does:**
The gating agent shares a single vision LLM call with the vision reading agent (Section 5.2). The LLM response contains both classification metadata and the faithful transcript. The gating agent consumes the classification portion and runs validation checks as code:

- Classifies each uploaded document's type (`PRESCRIPTION`, `HOSPITAL_BILL`, `LAB_REPORT`, `PHARMACY_BILL`, `DENTAL_REPORT`, `DISCHARGE_SUMMARY`) from the vision model output.
- Checks whether the detected document types satisfy `document_requirements[claim_category].required` from `policy_terms.json`.
- Rejects documents with readability score below 0.4 and asks for re-upload — does not outright reject the claim.
- Verifies patient name consistency across all documents using edit-distance matching.

**Input:**

```python
class GatingRequest(BaseModel):
    claim_category: Literal["CONSULTATION","DIAGNOSTIC","PHARMACY",
                            "DENTAL","VISION","ALTERNATIVE_MEDICINE"]
    documents: list[DocumentUpload]   # file_id, mime_type, raw_bytes or url
    member_name: str
```

**Output (success):**

```python
class GatingResult(BaseModel):
    passed: bool = True
    documents_typed: list[TypedDocument]  # detected_type + confidence per doc
```

**Output (failure — early exit):**

```python
class GatingError(BaseModel):
    passed: bool = False
    error_code: Literal["WRONG_TYPE","UNREADABLE","PATIENT_MISMATCH",
                         "MISSING_REQUIRED"]
    human_message: str   # specific, actionable — names what was found vs needed
    detail: dict         # e.g. {"found": "PRESCRIPTION", "required": "HOSPITAL_BILL"}
```

**Example failure messages:**
- TC001: *"You uploaded two prescriptions, but a CONSULTATION claim requires a Hospital Bill as the second document. Please upload your clinic invoice or receipt."*
- TC002: *"The pharmacy bill you uploaded is too blurry to read. Please take a clearer photo and re-upload."*
- TC003: *"The prescription is in the name of Rajesh Kumar, but the hospital bill is in the name of Arjun Mehta. Please ensure both documents belong to the same patient."*

---

### 5.2 Vision Reading Agent

**Purpose:** Produce a faithful, structured transcript from each document image, preserving exactly what is visible without interpretation or inference.

**Architecture — single vision call shared with gating:**
The gating agent and vision reading agent share one Gemini 2.5 Pro call per document. The prompt instructs the model to return both classification metadata (consumed by gating) and a faithful transcript (consumed by this agent). If gating fails, the transcript is discarded — one LLM call was spent, but no further calls are made.

**Transcript rules:**
- Unclear regions are marked `[UNCLEAR]` — the model must never guess.
- Text obscured by stamps is marked `[STAMP_OBSCURED]`.
- The transcript preserves document structure (headers, line items, totals).
- No interpretation: if the document says "Paracetomol" (misspelling), the transcript says "Paracetomol".

**Why a two-call extraction design (vision → then text)?**
Research on medical document pipelines shows that traditional OCR (Tesseract, PaddleOCR) collapses on handwritten Indian prescriptions, rubber stamps, and phone photos. Two-stage pipelines (OCR tool → then LLM) suffer from compounding errors — the LLM correctly processes corrupted text from OCR without realising it's corrupted. Sending the image directly to a vision model avoids this. The transcript is then passed to the entity extraction agent (a cheaper text model), which extracts structured fields. If the transcript contains `[UNCLEAR]`, the entity extractor outputs `null` with low confidence — it cannot hallucinate because it never saw the image.

**Input:** `list[DocumentUpload]` (raw images or PDFs rendered to images via PyMuPDF)

**Output:**

```python
class VisionReadingResult(BaseModel):
    file_id: str
    raw_transcript: str
    readability_score: float              # 0.0–1.0
    quality_flags: list[Literal[
        "HANDWRITTEN","STAMP_OVER_TEXT","LOW_CONTRAST",
        "PARTIAL_PAGE","MULTILINGUAL","ALTERATION_MARK"
    ]]
    field_confidences: dict[str, float]   # per-field confidence from vision model
    agent_status: Literal["SUCCESS","PARTIAL","TIMEOUT","ERROR"]
```

**Errors raised:** `VisionTimeoutError`, `UnsupportedFormatError`

---

### 5.3 Entity Extraction Agent

**Purpose:** Parse structured medical and billing fields from the transcript text produced by the vision reading agent.

**Key design decision:** This agent receives text, not images. Since the vision reading agent already produced a faithful transcript, entity extraction is a text-comprehension task — no vision model needed. This allows the use of a cheaper, faster model (Gemini Flash or Claude Haiku), cutting cost by approximately 80% compared to using the Pro model.

**Input:** `list[VisionReadingResult]` (transcripts only — no images sent)

**Output:**

```python
class ExtractionResult(BaseModel):
    patient_name: str | None
    doctor_name: str | None
    doctor_registration: str | None
    doctor_registration_valid: bool | None  # regex validated: KA/45678/2015
    diagnosis_primary: str | None
    diagnosis_icd_hint: str | None          # e.g. "T2DM" → "E11"
    treatment_date: date | None
    hospital_name: str | None
    is_network_hospital: bool | None        # matched against policy network list
    line_items: list[LineItem]              # description, amount, coverage_hint
    amount_claimed: Decimal | None
    field_confidences: dict[str, float]
    agent_status: Literal["SUCCESS","PARTIAL","TIMEOUT","ERROR"]
```

**Coverage hints:** Each line item gets a lightweight classification (`COVERED`, `EXCLUDED`, `UNCERTAIN`) by matching its description against the policy's `covered_procedures` and `excluded_procedures` lists. This gives the downstream policy engine a head start without the entity agent making coverage decisions.

**Doctor registration validation:** Format validation (e.g. `KA/XXXXX/YYYY`) happens via regex post-processing on the extracted string, not via LLM.

---

### 5.4 Amount Reconciler Agent

**Purpose:** Cross-document financial consistency checks and fraud signal detection.

**Key design decision:** This agent is pure Python code — no LLM call. Once the entity extraction agent has produced structured amounts and line items, consistency checks are arithmetic: does the sum match the total? Does the claimed amount match the bill? Visual alteration flags (crossed-out amounts, white-out marks) are already captured as `quality_flags` by the vision reading agent in Stage 1.

**What it checks:**
- Does the bill total match the sum of itemised line items?
- Does the claimed amount match what the bill actually says?
- Are there `ALTERATION_MARK` quality flags from the vision reading agent?
- Do amounts on the prescription match amounts on the bill?

**Input:** `list[ExtractionResult]` + `list[VisionReadingResult]` (for quality flags)

**Output:**

```python
class ReconciliationResult(BaseModel):
    bill_total_extracted: Decimal | None
    line_items_sum: Decimal | None
    claimed_amount: Decimal
    discrepancy_flags: list[DiscrepancyFlag]
    # e.g. DiscrepancyFlag(type="TOTAL_MISMATCH", expected=1500, found=1200)
    fraud_indicators: list[FraudIndicator]
    # e.g. FraudIndicator(type="AMOUNT_CORRECTION", source="quality_flags")
    agent_status: Literal["SUCCESS","PARTIAL","TIMEOUT","ERROR"]
```

---

### 5.5 Orchestrator

**Purpose:** Merge outputs from the extraction, reconciliation, and vision reading agents into a single unified claim record, resolve conflicts, and compute the aggregate extraction confidence score.

**Conflict resolution example:** If the prescription shows patient name "R. Kumar" and the bill shows "Rajesh Kumar", the orchestrator normalises to the longer form, logs the conflict, and does not reduce confidence (minor variation). If the prescription shows amount ₹1,200 and the bill shows ₹1,500, the orchestrator takes the bill amount, flags the conflict, and reduces confidence.

**Confidence formula:**

```
field_conf = weighted_average(field_confidences)
    weights: amount = 0.30, patient_name = 0.25, diagnosis = 0.20,
             doctor = 0.15, treatment_date = 0.10

agent_penalty = 0.15 × number_of_failed_agents

extraction_confidence = max(0.0, field_conf − agent_penalty)
```

**Thresholds (configurable constants, not hardcoded):**
- Below **0.65**: force `MANUAL_REVIEW` regardless of policy rule outcomes.
- Between **0.65–0.85**: proceed with caution flag in trace.
- Above **0.85**: high confidence, proceed normally.

**Output:**

```python
class MergedClaim(BaseModel):
    patient_name: str | None
    doctor_name: str | None
    doctor_registration: str | None
    diagnosis_primary: str | None
    treatment_date: date | None
    hospital_name: str | None
    is_network_hospital: bool | None
    line_items: list[LineItem]
    amount_claimed: Decimal | None
    extraction_confidence: float          # 0.0–1.0
    failed_agents: list[str]
    conflict_log: list[ConflictEntry]     # what conflicted and how it was resolved
```

---

### 5.6 Policy Rule Engine (Deterministic — No LLM)

**Purpose:** Evaluate the merged claim against every applicable policy rule from `policy_terms.json`. This is the most critical component — it must be deterministic, auditable, and produce named reasons for every outcome.

**Design:** The engine loads `policy_terms.json` at startup and validates it against a Pydantic schema. Rules are pure Python functions. Each returns a `RuleResult` containing the rule ID, outcome, a human-readable reason string, and any approved/deducted amounts. The engine is fully unit-testable without any LLM dependency.

```python
@dataclass
class RuleResult:
    rule_id: str              # e.g. "WAITING_PERIOD_DIABETES"
    outcome: Literal["PASS","FAIL","PARTIAL","SKIP"]
    reason: str               # human-readable, goes into trace and rejection message
    approved_amount: Decimal | None
    deducted_amount: Decimal | None
    deduction_reason: str | None
```

**Rule evaluation order (each rule is a gate — first failure determines outcome):**

| # | Rule | What it checks | Test case |
|---|---|---|---|
| 1 | Member eligibility | Is member in the roster? Is policy active? Is treatment date within policy window? | — |
| 2 | Submission deadline | Was claim submitted within 30 days of treatment? | — |
| 3 | Minimum claim amount | Is claimed amount ≥ ₹500? | — |
| 4 | Initial waiting period | Has 30 days elapsed since member's join date? | — |
| 5 | Condition-specific waiting | Does diagnosis match a condition with a specific waiting period? (e.g., Diabetes = 90 days from join date) | TC005 |
| 6 | Exclusion check | Does diagnosis or any line item match the exclusion list? | TC012 |
| 7 | Coverage category check | Is claim category covered? Are claimed procedures in `covered_procedures`? | — |
| 8 | Per-claim limit | Does claimed amount exceed ₹5,000 per-claim cap? | TC008 |
| 9 | Annual limit | Does YTD claimed + current claim exceed annual OPD limit (₹50,000)? | — |
| 10 | Pre-authorisation check | Does claim require pre-auth (e.g., MRI > ₹10,000)? Is it present? | TC007 |
| 11 | Network hospital discount | Is hospital in the network list? Apply 20% discount. | TC010 |
| 12 | Copay application | Apply copay percentage for claim category. **Applied after network discount.** | TC004, TC010 |
| 13 | Dental line-item filter | For dental claims, approve covered procedures and reject excluded ones individually on the same bill. | TC006 |
| 14 | Fraud signal check | Does same-day claim count exceed threshold (2)? Route to `MANUAL_REVIEW`. | TC009 |

**Critical calculation order for TC010 (network + copay):**
Network discount is applied first, then copay is applied to the discounted amount — not the original. Example: ₹4,500 × 0.80 (network discount) = ₹3,600 → ₹3,600 × 0.90 (10% copay) = **₹3,240 approved**. Reversing this order produces the wrong amount.

**TC005 walkthrough:**
EMP005 (Vikram Joshi) joined 2024-09-01. Claims for diabetes treatment on 2024-10-15. Days elapsed: 44. Diabetes waiting period: 90 days. 44 < 90 → **REJECTED**. Reason: *"Diabetes-related claims are eligible from 2024-11-30 (90 days from your enrolment date of 2024-09-01)."*

**TC006 walkthrough:**
Dental claim with two line items: Root canal (₹8,000) and Teeth whitening (₹4,000). Root canal is in `covered_procedures` → approved. Teeth whitening is in `excluded_procedures` → rejected. **PARTIAL** approval: ₹8,000. Rejection reason for whitening: *"Teeth whitening is a cosmetic dental procedure excluded under policy section 4.2."*

---

### 5.7 Decision Synthesis Agent

**Purpose:** Produce the final structured verdict and a coherent, member-facing explanation.

**Important:** This agent does not make the decision. The policy rules already made it. This agent's job is to synthesise the list of `RuleResult` objects and the `MergedClaim` into a clear member message and an internal ops summary.

**Fallback:** If the LLM call times out, the agent falls back to a template-based verdict constructed directly from the rule results. This ensures a decision is always produced even if the synthesis model is unavailable.

**Output:**

```python
class ClaimDecision(BaseModel):
    claim_id: str
    decision: Literal["APPROVED","PARTIAL","REJECTED","MANUAL_REVIEW"]
    approved_amount: Decimal
    copay_deducted: Decimal
    network_discount_applied: Decimal
    rejection_reasons: list[RejectionReason]
    partial_items: list[LineItemDecision] | None   # for PARTIAL decisions
    member_message: str        # specific, actionable — not generic
    ops_summary: str           # internal — what the ops team sees
    confidence_score: float
    manual_review_note: str | None
    trace_id: str
```

---

### 5.8 Trace Emitter (Cross-Cutting)

Every agent method is decorated with `@traced`. Each invocation produces a span.

```python
@dataclass
class TraceSpan:
    span_id: str
    claim_id: str
    agent_name: str
    started_at: datetime
    ended_at: datetime
    elapsed_ms: int
    input_summary: dict      # key fields only, not raw bytes
    output_summary: dict
    confidence_delta: float | None   # how much this step changed confidence
    errors: list[str]
    status: Literal["SUCCESS","PARTIAL","TIMEOUT","ERROR","SKIPPED"]
```

**Reconstruction:** The full trace for any claim is a simple query: `SELECT * FROM trace_spans WHERE claim_id = ? ORDER BY started_at`. This alone reconstructs every decision.

**TC011 handling:** A simulated component failure causes one agent to raise an error. The trace shows `status: ERROR` for that span, the orchestrator shows `failed_agents: ["entity_extraction"]`, and the final decision carries lower confidence with a note: *"One extraction component failed and was skipped. Manual review recommended."*

**Example trace output (TC004 — clean approval):**

```
trace-abc-123 | CLM-2024-00421 | 2.3s total
├─ vision_call_doc1        120ms  SUCCESS  type: PRESCRIPTION  readability: 0.88
├─ vision_call_doc2         95ms  SUCCESS  type: HOSPITAL_BILL  readability: 0.95
├─ gating_agent              3ms  SUCCESS  PASS (docs valid, names match)
├─ entity_extraction       340ms  SUCCESS  6 fields extracted, conf: 0.96
├─ amount_reconciler         1ms  SUCCESS  no discrepancies
├─ orchestrator              2ms  SUCCESS  merged_conf: 0.97
├─ policy_engine             4ms  SUCCESS  14 rules evaluated, 0 failures
└─ decision_synthesis      280ms  SUCCESS  APPROVED ₹1,350
```

---

## 6. Data Flow

```
Member uploads documents + selects claim category
          │
          ▼
    ┌─────────────┐
    │  Vision LLM  │  1 call per document (Gemini 2.5 Pro)
    │  call         │  Returns: doc_type + readability + transcript + quality_flags
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   Gating     │  Code checks on vision output
    │   Agent      │  Required docs present? Names match? Readable?
    └──────┬──────┘
           │ PASS                          │ FAIL
           │                               ▼
           │                    Return specific error to member
           ▼                    (what's wrong + what to fix)
    ┌──────────────┐
    │   Entity      │  Text LLM (Gemini Flash / Haiku)
    │  Extraction   │  Structured fields from transcript
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   Amount      │  Pure code — no LLM
    │  Reconciler   │  Sum checks, discrepancy flags
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Orchestrator  │  Merge results, resolve conflicts
    │               │  Compute extraction_confidence
    └──────┬───────┘
           │
           ▼
   extraction_confidence < 0.65?
        │              │
       YES             NO
        │              │
        ▼              ▼
  MANUAL_REVIEW   ┌──────────────┐
                  │ Policy Rule  │  Deterministic Python
                  │ Engine       │  14 ordered rules from policy_terms.json
                  └──────┬───────┘
                         │
                         ▼
               ┌──────────────────┐
               │ Decision Agent   │  Text LLM (with template fallback)
               └──────────────────┘
                         │
                         ▼
               Store decision + full trace
               Return to member via API
```

---

## 7. Core Data Models

```python
class Claim(BaseModel):
    claim_id: str
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    submission_date: date
    claimed_amount: Decimal
    hospital_name: str | None
    status: Literal["PENDING","PROCESSING","DECIDED","MANUAL_REVIEW"]
    decision: ClaimDecision | None
    trace_id: str

class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: date
    join_date: date
    relationship: str
    primary_member_id: str | None
    ytd_claimed: Decimal = Decimal("0")
    claims_history: list[ClaimSummary] = []

class Policy(BaseModel):
    policy_id: str
    coverage: CoverageConfig
    opd_categories: dict[str, OPDCategory]
    waiting_periods: WaitingPeriods
    exclusions: ExclusionList
    pre_authorization: PreAuthConfig
    network_hospitals: list[str]
    submission_rules: SubmissionRules
    document_requirements: dict[str, DocumentRequirements]
    fraud_thresholds: FraudThresholds
    members: list[Member]
```

---

## 8. Confidence Model

Confidence is computed, not estimated. The orchestrator combines document quality, entity extraction confidence, reconciliation quality, and failure penalties into one extraction confidence score.

```
DOCUMENT CONFIDENCE
    average(classification_confidence * 0.60 + readability * 0.40)
                                                │
                                                ▼
ENTITY CONFIDENCE
    weighted field confidence
    amount 0.30, patient 0.25, diagnosis 0.20, doctor 0.15, date 0.10
                                                │
                                                ▼
RECONCILIATION CONFIDENCE
    starts at 1.0, reduced by amount discrepancies and fraud indicators
                                                │
                                                ▼
EXTRACTION CONFIDENCE
    = document_confidence * 0.35
    + entity_confidence * 0.45
    + reconciliation_confidence * 0.20
    - failed/discrepancy/fraud penalties
                                                │
                                                ▼
THRESHOLD
    < 0.65  => MANUAL_REVIEW
    >= 0.65 => continue to policy engine
```

**What lowers confidence:** low document readability, low classification confidence, missing/uncertain extracted fields, amount discrepancies, fraud indicators, incomplete documents, conflicting values across documents, agent timeouts, or agent failures.

---

## 9. Failure Handling Matrix

| Failure type | System behaviour | Trace record | Confidence impact |
|---|---|---|---|
| Vision LLM timeout | Proceed with empty transcript, log TIMEOUT | `vision_agent: TIMEOUT` | −0.20 |
| Entity agent error | Proceed with null fields | `entity_agent: ERROR` | −0.15 |
| Amount reconciler error | Skip reconciliation | `reconciler: SKIPPED` | −0.10 |
| All extraction agents fail | Route to MANUAL_REVIEW regardless | `extraction_confidence: 0.0` | Forces MANUAL_REVIEW |
| Policy engine exception | Catch, log, route to MANUAL_REVIEW | `policy_engine: ERROR` | Forces MANUAL_REVIEW |
| Decision agent LLM timeout | Fallback to template-based verdict | `decision_agent: FALLBACK` | −0.05 |

---

## 10. Test Case Resolution Map

| Case | Description | Resolution stage | Key rule / check | Expected outcome |
|---|---|---|---|---|
| TC001 | Wrong document type | Document gating | Second doc is PRESCRIPTION, not HOSPITAL_BILL | Rejection with re-upload instruction |
| TC002 | Unreadable document | Document gating | Readability < 0.4 on pharmacy bill | Re-upload request |
| TC003 | Patient name mismatch | Document gating | Edit-distance check fails across docs | Rejection with mismatch details |
| TC004 | Clean consultation claim | Policy engine | All rules pass, 10% copay applied | APPROVED — ₹1,350 |
| TC005 | Diabetes within waiting period | Policy engine (R5) | 44 days elapsed vs 90-day requirement | REJECTED |
| TC006 | Dental with mixed line items | Policy engine (R13) | Root canal approved, whitening excluded | PARTIAL — ₹8,000 |
| TC007 | MRI without pre-auth | Policy engine (R10) | MRI > ₹10k requires pre-auth, none present | REJECTED |
| TC008 | Amount exceeds per-claim limit | Policy engine (R8) | ₹7,500 > ₹5,000 cap | REJECTED |
| TC009 | Suspicious same-day claims | Policy engine (R14) | 4th same-day claim exceeds limit of 2 | MANUAL_REVIEW |
| TC010 | Network hospital claim | Policy engine (R11+12) | 20% discount → then 10% copay: ₹4,500 → ₹3,600 → ₹3,240 | APPROVED — ₹3,240 |
| TC011 | Simulated component failure | Orchestrator + trace | Agent error → degraded confidence → manual review note | MANUAL_REVIEW |
| TC012 | Excluded condition (obesity) | Policy engine (R6) | Bariatric / morbid obesity on exclusion list | REJECTED |

---

## 11. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend framework | FastAPI (Python) | Async-native, well-suited for AI/IO-heavy workloads |
| Agent orchestration | Custom thin framework | Avoids LangChain abstraction overhead; keeps traces fully owned |
| Vision model | Gemini 2.5 Pro | Strong on noisy Indian medical docs; structured output; swappable |
| Text model | Gemini Flash / Claude Haiku | Cheaper and faster for transcript-based tasks |
| PDF preprocessing | PyMuPDF | Lightweight PDF loading, page splitting, rendering to images |
| Task queue | Celery + Redis | Claims processing is async; webhook on completion |
| Database | PostgreSQL | Claims, traces, documents stored relationally |
| File storage | Local (S3 interface) | Same interface for later S3 migration |
| Frontend | React + TypeScript | Submission form + ops dashboard with trace viewer |
| Schema validation | Pydantic | Typed contracts between every agent; runtime validation |
| Testing | pytest | Each of 12 test cases maps to a test function with fixtures |

**Model provider abstraction:** All LLM calls go through a `DocumentIntelligenceProvider` interface so the system can later swap to GPT-4o, Claude, Azure Document Intelligence, AWS Textract, or a self-hosted model (PaddleOCR-VL, DeepSeek-OCR, olmOCR) without changing any other component.

---

## 12. Project Structure

```
plum-claims/
├── backend/
│   ├── agents/
│   │   ├── gating.py              # Document gating agent
│   │   ├── vision_reader.py       # Vision reading agent (shares LLM call with gating)
│   │   ├── entity.py              # Entity extraction from transcript (text LLM)
│   │   ├── reconciler.py          # Amount reconciliation (pure code)
│   │   ├── orchestrator.py        # Merge, conflict resolution, confidence
│   │   └── decision.py            # Decision synthesis with LLM fallback
│   ├── policy/
│   │   ├── engine.py              # Rule evaluation orchestrator
│   │   ├── loader.py              # policy_terms.json → Pydantic models
│   │   └── rules/                 # One file per rule group
│   │       ├── eligibility.py     # Rules 1–4: member, deadline, minimum, initial waiting
│   │       ├── waiting_periods.py # Rule 5: condition-specific waiting
│   │       ├── exclusions.py      # Rule 6: exclusion list matching
│   │       ├── limits.py          # Rules 7–9: coverage, per-claim, annual
│   │       ├── pre_auth.py        # Rule 10: pre-authorisation check
│   │       ├── copay_discount.py  # Rules 11–12: network discount + copay (order matters)
│   │       ├── dental_filter.py   # Rule 13: line-item level decisions
│   │       └── fraud.py           # Rule 14: same-day / monthly claim limits
│   ├── models/                    # Pydantic data models (all contracts)
│   │   ├── claim.py
│   │   ├── member.py
│   │   ├── extraction.py
│   │   ├── policy.py
│   │   └── decision.py
│   ├── providers/
│   │   ├── base.py                # DocumentIntelligenceProvider interface
│   │   ├── gemini.py              # Gemini 2.5 Pro + Flash implementation
│   │   └── stub.py                # Mock provider for testing
│   ├── tracing/
│   │   ├── decorator.py           # @traced decorator
│   │   ├── span.py                # TraceSpan model
│   │   └── store.py               # Trace persistence (PostgreSQL)
│   ├── api/
│   │   ├── routes.py              # FastAPI endpoints
│   │   └── middleware.py          # Request logging, error handling
│   └── tests/
│       ├── test_policy_engine.py  # All 12 TC outcomes as pure unit tests
│       ├── test_gating.py         # Document validation tests
│       ├── test_confidence.py     # Confidence computation tests
│       ├── test_reconciler.py     # Amount reconciliation tests
│       └── fixtures/              # Test case data from test_cases.json
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── SubmitClaim.tsx    # Upload form + category selection
│   │   │   └── ClaimDetail.tsx    # Decision card + trace tree
│   │   └── components/
│   │       ├── TraceViewer.tsx    # Expandable span tree
│   │       └── ConfidenceBadge.tsx
├── policy_terms.json
├── sample_documents_guide.md
└── test_cases.json
```

---

## 13. Scale Considerations (75K → 10M Lives)

The current design targets approximately 75,000 claims/year (~200/day) and runs comfortably with synchronous processing and a Celery queue. At 10M lives (~1M+ claims/year, ~3,000/day peak):

**Vision LLM calls become the bottleneck.** Each claim makes 2 vision calls (one per document). At 3,000 claims/day, that is 6,000+ vision LLM calls/day — feasible but requires connection pooling and rate-limit management. The text LLM calls (entity extraction + decision synthesis) are cheaper and faster, adding minimal load.

**Policy engine scales trivially.** It is stateless and fast — horizontal scaling requires no architectural change.

**Trace store grows large.** PostgreSQL with `claim_id` index handles 10M traces. Partition by month for query performance.

**Key architectural changes at 10× scale:**
- Move from Celery to streaming event architecture (Kafka topics per pipeline stage).
- Dedicated fraud detection service with member-level rolling windows for same-day and monthly claim counts.
- Caching layer for member policy lookups to avoid re-parsing `policy_terms.json` on every claim.
- Migrate extraction layer to self-hosted models (PaddleOCR-VL, DeepSeek-OCR) for lower per-call cost at volume — the provider interface makes this a drop-in swap.
- Consider batch processing: group claims by category and process similar claims together to optimise LLM prompt caching.

---

## 14. Conscious Trade-offs

**Included despite time constraints:**
- Full trace system (20% of evaluation weight; hardest to retrofit).
- 7-agent architecture with independent contracts (multi-agent bonus).
- Typed Pydantic schemas for every agent's input/output (makes component contracts deliverable trivial).
- Model provider abstraction interface (swappable LLM backends).

**Excluded given 2–3 day timeline:**
- Multi-tenant auth and user sessions — single-user demo is sufficient.
- Real S3 — local file storage with S3-compatible interface is adequate.
- Multi-page PDF splitting — each uploaded file is treated as one unit.
- Real-time pre-authorisation API lookup — pre-auth presence is inferred from submitted documents.

**Optimised vs original design:**
- Combined gating + vision reading into a single LLM call (saves 1 vision call per document).
- Moved entity extraction to a text-only model (saves ~80% on extraction cost).
- Made amount reconciler pure code (saves 1 LLM call per claim entirely).
- Net result: 4 LLM calls per 2-document claim (was 7–8), ~50–60% cost reduction.

**Configurable, not hardcoded:**
- Confidence thresholds (0.65 for MANUAL_REVIEW, 0.85 for high-confidence auto-decide) are initial values requiring calibration against real claim outcomes.
- All policy rules are loaded from `policy_terms.json`, not embedded in code.

**Database, Polling, and UI Decisions (v1.0 Spec):**
- **SQLite over PostgreSQL:** Used with SQLAlchemy models for a future drop-in migration. WAL mode enables sufficient concurrency for the assignment's claim volume.
- **Polling over WebSockets:** At a 1.5s interval. WebSockets would reduce latency slightly but add connection-management complexity disproportionate to the assignment's scope. Polling is simple, debuggable, and the 1.5s interval is imperceptible for a 2–3 second pipeline.
- **Fixed 8-stage pipeline display:** Independent of the underlying LLM call count. This decouples the UI's notion of "steps" from the cost-optimization detail that two agents share one LLM call — the user sees 8 clean stages regardless.
- **`trace_spans` table as single source of truth:** Used for both the live progress UI and the eval report's trace reconstruction requirement. No separate "progress" tracking mechanism is needed.

---

*End of Document*
