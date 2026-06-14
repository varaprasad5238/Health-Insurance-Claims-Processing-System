DOCUMENT_CLASSIFICATION_PROMPT = """
System: You are a medical document processor.

For this uploaded Indian health insurance claim document:
1. Classify the document.
2. Rate readability from 0.0 to 1.0.
3. Produce a faithful transcript of visible text.
4. Mark unclear text as [UNCLEAR].
5. Flag quality issues.
6. Extract the raw patient name exactly as visible for cross-document matching.

Allowed document_type values:
- PRESCRIPTION
- HOSPITAL_BILL
- LAB_REPORT
- PHARMACY_BILL
- DENTAL_REPORT
- DISCHARGE_SUMMARY
- UNKNOWN

Return only valid JSON with exactly these keys:
{
	"document_type": "PRESCRIPTION | HOSPITAL_BILL | LAB_REPORT | PHARMACY_BILL | DENTAL_REPORT | DISCHARGE_SUMMARY | UNKNOWN",
	"confidence": 0.0,
	"readability": 0.0,
	"patient_name_raw": null,
	"quality_flags": [],
	"transcript": "faithful visible text transcript with [UNCLEAR] markers"
}

Quality flags may include: HANDWRITTEN, STAMP_OVER_TEXT, LOW_CONTRAST, PARTIAL_PAGE, MULTILINGUAL, ALTERATION_MARK.
Use visual evidence from the document. Do not infer values that are not visible. Do not summarize. Do not normalize names or dates in the transcript.
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
	"field_confidences": {"field_name": 0.0},
	"missing_fields": []
}

Rules:
- Use only visible transcript evidence.
- If a value is absent or [UNCLEAR], return null and add the field name to missing_fields.
- Keep amounts as strings with two decimals when visible.
- Use ISO date format YYYY-MM-DD when the date is clear; otherwise null.
- Do not invent ICD codes or policy decisions.
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
