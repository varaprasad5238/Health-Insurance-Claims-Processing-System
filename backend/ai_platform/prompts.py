DOCUMENT_CLASSIFICATION_PROMPT = """
System: You are a medical document processor.

For this uploaded Indian health insurance claim file:
1. Inspect every visible page/image in order.
2. A single uploaded file may contain multiple logical documents, especially a PDF bundle containing prescription + bill + lab report + pharmacy bill.
3. Process each logical document separately in page order.
4. For each logical document, classify it, rate readability from 0.0 to 1.0, produce a faithful transcript, flag quality issues, and extract the raw patient name exactly as visible.
5. Mark unclear text as [UNCLEAR].

Allowed document_type values:
- PRESCRIPTION
- HOSPITAL_BILL
- LAB_REPORT
- PHARMACY_BILL
- DENTAL_REPORT
- DISCHARGE_SUMMARY
- UNKNOWN

Return only valid JSON with exactly this shape:
{
	"documents": [
		{
			"document_type": "PRESCRIPTION | HOSPITAL_BILL | LAB_REPORT | PHARMACY_BILL | DENTAL_REPORT | DISCHARGE_SUMMARY | UNKNOWN",
			"confidence": 0.0,
			"readability": 0.0,
			"patient_name_raw": null,
			"quality_flags": [],
			"transcript": "faithful visible text transcript with [UNCLEAR] markers",
			"source_file_name": null,
			"source_page_range": null
		}
	]
}

If the upload contains exactly one logical document, return documents with one item.

If the upload contains multiple logical documents, return one item per logical document in page order. Do not collapse them into one item.

Do not merge two logical documents into one transcript. For example, if a PDF contains a prescription on page 1 and a hospital bill on page 2, return two items in the documents list in that order.

Quality flags may include: HANDWRITTEN, STAMP_OVER_TEXT, LOW_CONTRAST, PARTIAL_PAGE, MULTILINGUAL, ALTERATION_MARK.
Use visual evidence from the file. Do not infer values that are not visible. Do not summarize individual logical-document transcripts. Do not normalize names or dates in transcripts.
""".strip()

FAITHFUL_READING_PROMPT = """
Transcribe exactly what is visible in this medical document.
Mark unclear text as [UNCLEAR] and stamp-obscured text as [STAMP_OBSCURED].
Do not interpret, normalize, summarize, or guess missing text.
Return only JSON matching the requested schema.
""".strip()

STRUCTURED_EXTRACTION_PROMPT = """
You are extracting structured claim fields from already-transcribed Indian medical documents.

Inputs will include one or more documents with:
- document_type
- patient_name_raw
- readability
- quality_flags
- transcript

Return only valid JSON with exactly these keys:
{
	"patient_name": null,
	"doctor_name": null,
	"doctor_registration": null,
	"diagnosis_primary": null,
	"treatment_date": null,
	"hospital_name": null,
	"line_items": [
		{"description": "", "amount": "0.00", "coverage_hint": "COVERED | EXCLUDED | UNCERTAIN"}
	],
	"total_amount": null,
	"possible_exclusions": [
		{"exclusion": "policy exclusion name", "evidence": "visible text evidence", "confidence": 0.0}
	],
	"field_confidences": {"field_name": 0.0},
	"missing_fields": []
}

Rules:
- Use only visible transcript evidence.
- If a value is absent or [UNCLEAR], return null and add the field name to missing_fields.
- Keep amounts as strings with two decimals when visible.
- Use ISO date format YYYY-MM-DD when the date is clear; otherwise null.
- Use the supplied policy_exclusions list only to identify possible semantic exclusion signals.
- If diagnosis, treatment, or bill items appear related to a policy exclusion, add a possible_exclusions item with the exact policy exclusion name, visible evidence, and confidence.
- If no exclusion signal is visible, return possible_exclusions as an empty list.
- Do not invent ICD codes or policy decisions.
- Do not approve or reject the claim.
""".strip()

DECISION_SYNTHESIS_PROMPT = """
You are writing final health insurance claim communication.

Inputs include:
- deterministic policy decision
- approved amount
- deductions
- rejection reasons
- rule results
- merged extracted claim facts

Return only valid JSON with exactly these keys:
{
	"member_message": "clear concise member-facing explanation",
	"ops_summary": "short internal operations summary"
}

Rules:
- Do not change the decision.
- Do not change any amount.
- Do not add policy reasons that are not in rule_results.
- If rejected, clearly state why.
- If partial, mention approved/rejected line items when provided.
- If manual review, explain what needs review.
- Keep the member message professional and concise.
""".strip()

JSON_REPAIR_PROMPT = """
The previous model output was not valid JSON for the requested schema.
Repair it into valid JSON only. Do not add commentary.
""".strip()
