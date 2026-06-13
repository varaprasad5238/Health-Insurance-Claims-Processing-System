# Research Overview

- Document processing has moved beyond plain OCR into layout-aware document intelligence.
- Traditional OCR works well for clean printed text, but it struggles with the document quality expected in this assignment:
	- phone-captured bills
	- handwritten prescriptions
	- stamps over text
	- mixed layouts and tables
	- inconsistent medical document formats
- Modern OCR benchmarks and 2025 model comparisons show that multimodal vision-language models are better suited for these inputs because they can:
	- read the full document image
	- preserve document structure and reading order
	- reason over visual context
	- return structured outputs such as JSON, Markdown, or HTML

## Key Findings

- Self-hosted OCR and VLM models can provide strong accuracy, lower long-term cost, and better data control at high document volumes.
- Relevant self-hosted/open-source models include:
	- PaddleOCR-VL
	- DeepSeek-OCR
	- olmOCR
	- dots.ocr
	- Nanonets OCR
	- Chandra
	- LightOn OCR
- The E2E Networks guide is useful because it compares open-source OCR models across:
	- accuracy
	- throughput
	- GPU cost
	- deployment mode
	- production readiness
- The trade-off is that self-hosting requires reliable GPU infrastructure, vLLM-style model serving, benchmarking, monitoring, and tuning.
- Cloud document services such as AWS Textract, Azure Document Intelligence, and Google Document AI provide mature OCR APIs, but they may still need additional LLM reasoning for:
	- claim-specific validation
	- policy checks
	- explainable decision generation

## Assignment Direction

- The assignment requires more than text extraction. The system must also:
	- classify uploaded documents
	- extract medical and billing fields
	- detect missing or incorrect documents early
	- generate an explainable claim decision
	- handle low-confidence or failed extraction gracefully
- Due to time, local GPU, and infrastructure constraints, I am choosing an API-based vision-language model approach instead of self-hosting OCR models.
- The primary extraction and document-understanding layer will use a strong multimodal model such as Gemini 2.5 Pro.
- The model layer will be designed behind an interface so it can later be swapped with GPT-4o, Claude, Azure Document Intelligence, AWS Textract, or a self-hosted OCR/VLM model.
- This keeps the implementation focused on the assignment's highest-value engineering areas:
	- robust component contracts
	- schema-validated extraction
	- graceful failure handling
	- confidence scoring
	- traceability
	- policy-rule evaluation from `policy_terms.json`
- PyMuPDF will still be useful as a lightweight preprocessing layer for PDF handling, page rendering, metadata extraction, and converting PDFs into images before sending them to the vision model.

## Decision

- Use a hybrid document-processing pipeline.
- Use PyMuPDF for PDF loading, page splitting, rendering, and basic metadata extraction.
- Use a vision-language model, primarily Gemini 2.5 Pro, for document classification and structured field extraction.
- Validate model outputs against strict JSON schemas before using them in claim decisions.
- Route low-confidence, incomplete, or contradictory results to `MANUAL_REVIEW` instead of forcing an unsafe decision.
- Keep the model provider behind an interface so the system can later move to Azure Document Intelligence, AWS Textract, PaddleOCR-VL, DeepSeek-OCR, or another self-hosted model without changing the rest of the claims pipeline.

## Sources Reviewed

1. https://aimultiple.com/ocr-accuracy
2. https://arxiv.org/pdf/2503.15195
3. https://www.e2enetworks.com/blog/complete-guide-open-source-ocr-models-2025
4. https://atul4u.medium.com/beyond-text-extraction-the-2025-open-ocr-revolution-powered-by-vision-language-models-89ad33d36bbf
5. https://www.kevinherbas.com/blog/llm-data-extraction-complete-guide
6. https://pymupdf.readthedocs.io/en/latest/
7. https://www.sciencedirect.com/science/article/pii/S1877050924007786
8. https://www.marktechpost.com/2025/11/02/comparing-the-top-6-ocr-optical-character-recognition-models-systems-in-2025/
9. https://www.e2enetworks.com/blog/complete-guide-open-source-ocr-models-2025