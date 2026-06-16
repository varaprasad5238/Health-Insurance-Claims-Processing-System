# Engineering Reasoning - Decision Log

**Plum Claims Processing System**

---

## Phase 1 - Problem Decomposition

### Why structured workflow, not autonomous agents or monolithic LLM

```text
Option A: Single LLM prompt                    Option B: Autonomous agents
"Here are docs + policy -> decide"             Each agent decides what to do next

x 0 intermediate checkpoints                   x Non-deterministic control flow
x No way to isolate extraction                  x Trace becomes a graph with cycles
  failure from rule failure                     x Framework overhead (LangGraph/CrewAI)
x LLM does date arithmetic,                       for a fixed-sequence problem
  set membership - unreliable                   x Harder to explain in technical review
x Fails 30% design + 20% observability

Option C: Structured workflow  <- CHOSEN
Fixed sequence, typed contracts, independent failure

+ Each stage testable in isolation
+ Trace is linear - trivially reconstructible
+ Deterministic tasks stay in code
+ ~80 lines of orchestration (no framework)
+ Still qualifies as multi-agent (7 agents, independent contracts)
```

**Why claims processing is not an exploratory task:**

- Every claim follows the same path: validate -> extract -> reconcile -> rules -> decide.
- Zero scenarios where an agent needs to go back or decide what to do next.
- One branch point: gating pass/fail.
- One conditional skip: low confidence -> skip rules.
- Fixed control flow means linear trace and trivial reconstruction for the ops team.

---

## Phase 2 - LLM Call Optimisation

### Problem: redundant vision calls

```text
BEFORE (7 calls per 2-doc claim)              AFTER (4 calls per 2-doc claim)
-------------------------------              -----------------------------
Doc 1 -> Vision call #1 (classify)            Doc 1 -> Vision call #1
Doc 1 -> Vision call #2 (transcript)                   (classify + transcript)
Doc 2 -> Vision call #3 (classify)            Doc 2 -> Vision call #2
Doc 2 -> Vision call #4 (transcript)                   (classify + transcript)
All   -> Text LLM #1 (entity extract)         All   -> Text LLM #3 (entity extract)
All   -> Text LLM #2 (amount reconcile)       -- amount reconciler is now CODE --
      -> Text LLM #3 (decision synthesis)             -> Text LLM #4 (decision synthesis)

7 calls (4 vision + 3 text)                   4 calls (2 vision + 2 text)
```

### Three insights, each with a specific reason

| Insight | Before | After | Why |
|---|---|---|---|
| Classify + transcript see the same image | 2 vision calls per doc | 1 vision call per doc | Single prompt returns both classification and transcript in one JSON response. If gating fails, transcript is discarded; cost is 1 call, not 2. |
| Entity extraction works from text, not images | Vision model call | Text-only model call | Transcript already exists from the vision step. Text models are cheaper than vision models. Entity extractor only sees what the vision reader produced. |
| Amount reconciliation is arithmetic | Text LLM call | Pure Python code | `sum(line_items) == bill_total` does not need language understanding. LLM arithmetic is less reliable than code arithmetic. Alteration flags are already captured by vision quality flags. |

### Cost impact per 2-document claim

| Call | Model | Est. cost | Before | After |
|---|---|---:|---:|---:|
| Vision (classify + transcript) | Gemini 2.5 Pro | ~$0.015/doc | 4 calls | 2 calls |
| Text (entity extraction) | Gemini Flash | ~$0.003 | 1 call | 1 call |
| Text (amount reconciliation) | Gemini Flash | ~$0.003 | 1 call | 0 (code) |
| Text (decision synthesis) | Gemini Flash | ~$0.003 | 1 call | 1 call |
| **Total** | | | **~$0.069** | **~$0.036** |

Approximate cost reduction: **~48% per claim, without reducing traceability.**

### Key architectural insight

```text
AGENT BOUNDARIES  !=  LLM CALL BOUNDARIES

7 logical agents                    4 LLM calls
(for contracts, traces,             (for cost, latency)
failure isolation, testability)

Gating agent  --\                   /-- Vision call #1
Vision reader --/ share one call     \-- returns both outputs

Amount reconciler ---- no LLM call at all; still an agent with contract + trace span
Policy engine ------- no LLM call at all; still an agent with contract + trace span
```

---

## Phase 3 - Document Input Edge Cases

### The assumption that broke

```text
ASSUMED: 1 uploaded file = 1 document = 1 image -> 1 vision call

REALITY:
- Single PDF with 4 documents: Rx on page 1, lab on page 2, bill on page 3, discharge on page 4.
- Text-based PDFs: e-bills from hospitals; extractable via PyMuPDF, no vision needed.
- Image-based PDFs: scanned or photographed; need rendering to PNG first.
- Multi-page bills: page 1 header/items, page 2 more items/total.
- GPT-5 rejects application/pdf as image MIME type.
```

### Preprocessing decision tree

```text
uploaded_file
    |
    |-- image/* (JPEG/PNG)
    |     -> pass through as-is
    |     -> vision call
    |
    `-- application/pdf
          -> PyMuPDF split into pages
              |
              |-- page.get_text() > 40 chars?
              |     YES -> TEXT PATH (future optimization)
              |            -> text-only LLM for classify + extract
              |            -> cheaper per page
              |
              `-- NO  -> IMAGE PATH
                         -> render to PNG at 200 DPI
                         -> standard vision call
```

Current implementation renders PDFs to PNG page images before vision calls to stay provider-agnostic.

### Upload limits derived from policy constraints

| Limit | Value | Source of truth / rationale |
|---|---:|---|
| Max files | 4 | `document_requirements` in `policy_terms.json`: diagnostic needs 3 required + 1 optional. |
| Per-file size | 3 MB | Phone screenshots and test images should fit; extra resolution gives little model-visible detail. |
| Total upload | 8 MB | Four files with realistic compression plus headroom. |

### GPT-5 MIME rejection

```text
LLM attempt failed: provider=openai model=gpt-5 error_code=PROVIDER_UNSUPPORTED_MIME

GPT-5 image input accepts image types such as image/png and image/jpeg.
GPT-5 image input rejects application/pdf in the current path.
Gemini can accept PDFs natively, but provider-agnostic preprocessing is safer.
PDF -> PNG via PyMuPDF makes the pipeline consistent across providers.
```

This confirmed preprocessing is mandatory, not optional.

---

## Phase 4 - Vision Model Limits and Single-Shot Decision

### Operating range per call

| Call type | Content | Estimated tokens |
|---|---|---:|
| Vision call per page/image | System prompt + 1 image + schema | ~1,000-2,000 |
| Entity extraction | All transcripts + instructions + schema | ~2,000-4,000 |
| Decision synthesis | Rule results + member message template | ~1,500-2,500 |

### Research findings on context-length degradation

| Finding | Source | Implication |
|---|---|---|
| Accuracy drops as context grows from 32K to 128K tokens across large-model benchmarks. | Long-context benchmark research | Our calls stay far below the degradation zone. |
| Relational reasoning can drift as context grows. | Graph/reconstruction style benchmarks | Cross-document checks such as name and amount matching are code, not LLM. |
| U-shaped attention can miss middle context. | Long-context attention studies | Keep prompts compact and structured. |
| Fabrication rises in very long contexts. | Long-context hallucination studies | Keep per-call scope small. |

### Decision: per-document vision, combined entity extraction

```text
Context size per call
|
|  OUR RANGE              DEGRADATION ZONE
|  1K-4K tokens           >32K tokens
|  [safe]                 [accuracy/fabrication risk]
|
0       2K       8K       32K      128K      200K
```

Cross-document checks stay in code to avoid relying on fragile long-context relational reasoning.

### Provider input limits

| Constraint | Gemini 2.5 Pro | GPT-5/OpenAI vision path | Our limit / handling |
|---|---|---|---|
| PDF native support | Yes | No in current path | Render PDF pages to PNG first. |
| Per-image size | Large enough for demo docs | Image types only | Frontend max 3 MB/file, 8 MB total. |
| Images per request | High | Sufficient for demo | Backend prepares max 5 images per claim. |

---

## Phase 5 - Scaling Path

| Metric | Current demo | Higher-scale direction |
|---|---|---|
| Claims/day | Local demo/single user | Queue or event stream per stage |
| Vision API calls | Per uploaded page/image | Connection pooling, rate limiting, batch controls |
| Database | SQLite WAL | PostgreSQL via SQLAlchemy connection swap |
| Task execution | FastAPI BackgroundTasks | Celery/Redis or Kafka-style stage topics |
| File storage | Local `backend/common` | S3-compatible object storage |
| Fraud detection | Hooked input / future DB query | Dedicated rolling-window service |
| Policy loading | Cached JSON DTO | Policy store + tenant cache |
| LLM providers | OpenAI primary, Gemini fallback | Provider abstraction allows swap to self-hosted OCR/VLM |

### Cost at scale

Cloud API calls are acceptable for the assignment and early prototype. At higher volume, self-hosted OCR/VLM models may become cost-effective, but only after operational overhead is justified.

---

## Phase 6 - Observability Beyond Traces

### Two layers, different questions

```text
LAYER 1: TRACE SPANS (per claim)       LAYER 2: LLM METRICS (aggregate, future)
--------------------------------       -------------------------------------
What happened to CLM-...?              How is the system performing overall?

agent_name, status, elapsed_ms         provider error rate
input_summary, output_summary          fallback trigger rate
confidence_delta, errors               median/p95 latency
                                       cost per claim
                                       manual review rate
```

Trace spans are already implemented. Aggregate LLM metrics are a future improvement.

### Future LLM metrics schema

```sql
llm_metrics
├── claim_id
├── agent_name
├── provider
├── model
├── is_fallback
├── input_tokens
├── output_tokens
├── latency_ms
├── estimated_cost
├── status
└── error_category
```

### Retry logic: transient vs permanent errors

| Error type | Action | Reason |
|---|---|---|
| Rate limit 429 | Retry or fallback depending on policy | Usually transient. |
| Timeout | Retry or fallback | Usually transient. |
| Server error 5xx | Retry | Usually transient. |
| MIME unsupported | Skip to fallback or preprocess | Permanent for same provider/input. |
| Auth failure | Fallback or fail fast | Configuration issue. |
| Malformed request | Fail fast | Code bug, not retryable. |

The GPT-5 PDF MIME failure showed that permanent errors should not be retried repeatedly with identical input.

---

## Decision Chain Summary

```text
Phase 1                 Phase 2                Phase 3
Decompose               Optimize calls          Handle edge cases
----------------        ----------------        ----------------
7 agents                Combine classify        PyMuPDF preprocessing
structured workflow     + transcript            PDF/text/image branching
code for deterministic  Entity = text-only      upload limits from policy
tasks                   Reconciler = code       provider-agnostic input
linear trace            fewer LLM calls

Phase 4                 Phase 5                Phase 6
Validate limits         Scale path              Observe + measure
----------------        ----------------        ----------------
small context windows   SQLite -> PostgreSQL    trace spans per claim
cross-doc checks code   BackgroundTasks -> queue LLM metrics future
provider limits mapped  local files -> S3       confidence calibration
```

---

*End of Document*
