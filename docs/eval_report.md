# Phase 1 Component Eval Report

Generated at: `2026-06-16T06:54:06.699466+00:00`
Mode: `component`

## Summary

Passed 8 of 12 cases.

| Case | Expected | Actual | Match | Notes |
| --- | --- | --- | --- | --- |
| TC001 | None | None | yes | ok |
| TC002 | None | None | yes | ok |
| TC003 | None | None | yes | ok |
| TC004 | APPROVED | APPROVED | yes | ok |
| TC005 | REJECTED | REJECTED | yes | ok |
| TC006 | PARTIAL | PARTIAL | yes | ok |
| TC007 | REJECTED | REJECTED | no | rejection_reasons failed. Current policy order evaluates condition waiting period before pre-authorization; the diagnosis text contains herniation, which matches the hernia waiting-period term. |
| TC008 | REJECTED | REJECTED | no | rejection_reasons failed. Current policy treats the consultation sub-limit as the active cap before the general per-claim limit, so the reason is SUB_LIMIT_EXCEEDED instead of PER_CLAIM_EXCEEDED. |
| TC009 | MANUAL_REVIEW | MANUAL_REVIEW | yes | ok |
| TC010 | APPROVED | REJECTED | no | decision failed; approved_amount failed. Current policy applies the consultation sub-limit before network discount and co-pay, so the claim is rejected before the expected discount calculation can run. |
| TC011 | APPROVED | APPROVED | yes | ok |
| TC012 | REJECTED | REJECTED | no | rejection_reasons failed. Current policy checks obesity-related waiting period before exclusions, so WAITING_PERIOD fires before EXCLUDED_CONDITION. |

## TC001 - Wrong Document Uploaded

### Checks

```json
[
  {
    "name": "decision",
    "expected": null,
    "actual": null,
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "gating",
  "document_artifacts": [
    "documents/TC001.pdf"
  ],
  "gating": {
    "passed": false,
    "error_code": "WRONG_TYPE",
    "human_message": "You uploaded duplicate prescription documents, but a consultation claim requires prescription, hospital bill. Please upload the missing hospital bill.",
    "detail": {
      "required": [
        "PRESCRIPTION",
        "HOSPITAL_BILL"
      ],
      "found": [
        "PRESCRIPTION",
        "PRESCRIPTION"
      ],
      "missing": [
        "HOSPITAL_BILL"
      ],
      "duplicates": [
        "PRESCRIPTION"
      ]
    }
  }
}
```

## TC002 - Unreadable Document

### Checks

```json
[
  {
    "name": "decision",
    "expected": null,
    "actual": null,
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "gating",
  "document_artifacts": [
    "documents/TC002.pdf"
  ],
  "gating": {
    "passed": false,
    "error_code": "UNREADABLE",
    "human_message": "The pharmacy bill is not readable enough to process. Please re-upload a clearer image or PDF of that document.",
    "detail": {
      "document_type": "PHARMACY_BILL",
      "readability": 0.2,
      "threshold": 0.4
    }
  }
}
```

## TC003 - Documents Belong to Different Patients

### Checks

```json
[
  {
    "name": "decision",
    "expected": null,
    "actual": null,
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "gating",
  "document_artifacts": [
    "documents/TC003.pdf"
  ],
  "gating": {
    "passed": false,
    "error_code": "PATIENT_MISMATCH",
    "human_message": "The uploaded documents appear to belong to different patients: Rajesh Kumar and Arjun Mehta. Please upload documents for the same patient.",
    "detail": {
      "patient_names": [
        "Rajesh Kumar",
        "Arjun Mehta"
      ],
      "first": "Rajesh Kumar",
      "second": "Arjun Mehta"
    }
  }
}
```

## TC004 - Clean Consultation — Full Approval

### Checks

```json
[
  {
    "name": "decision",
    "expected": "APPROVED",
    "actual": "APPROVED",
    "passed": true
  },
  {
    "name": "approved_amount",
    "expected": "1350.00",
    "actual": "1350.00",
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC004.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": [
      "Rajesh Kumar",
      "Rajesh Kumar"
    ]
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": "Rajesh Kumar",
    "doctor_name": "Dr. Arun Sharma",
    "doctor_registration": "KA/45678/2015",
    "diagnosis_primary": "Viral Fever",
    "treatment_date": "2024-11-01",
    "hospital_name": "City Clinic, Bengaluru",
    "line_items": [
      {
        "description": "Consultation Fee",
        "amount": "1000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "CBC Test",
        "amount": "300",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Dengue NS1 Test",
        "amount": "200",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "1500",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95,
      "patient_name": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "1500.00",
    "line_items_sum": "1500.00",
    "claimed_amount": "1500.00",
    "payable_basis_amount": "1500.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": "Rajesh Kumar",
    "doctor_name": "Dr. Arun Sharma",
    "doctor_registration": "KA/45678/2015",
    "diagnosis_primary": "Viral Fever",
    "treatment_date": "2024-11-01",
    "hospital_name": "City Clinic, Bengaluru",
    "line_items": [
      {
        "description": "Consultation Fee",
        "amount": "1000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "CBC Test",
        "amount": "300",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Dengue NS1 Test",
        "amount": "200",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "1500",
    "claimed_amount": "1500.00",
    "payable_basis_amount": "1500.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "APPROVED",
    "approved_amount": "1350.00",
    "copay_deducted": "150.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [],
    "partial_items": null,
    "member_message": "Your claim is approved for 1350.00.",
    "ops_summary": "Policy engine completed with decision APPROVED.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "No active condition waiting period applies.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "EXCLUSION_CHECK",
        "outcome": "PASS",
        "reason": "No exclusion matched.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COVERAGE_CATEGORY",
        "outcome": "PASS",
        "reason": "Claim category is covered.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "DENTAL_LINE_ITEM_FILTER",
        "outcome": "SKIP",
        "reason": "Not a dental claim.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "PRE_AUTH_CHECK",
        "outcome": "PASS",
        "reason": "No missing pre-authorization detected.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "FRAUD_SIGNAL_CHECK",
        "outcome": "PASS",
        "reason": "No fraud threshold breach.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "BENEFIT_CAP",
        "outcome": "PASS",
        "reason": "Payable amount is within SUB_LIMIT cap 2000.00.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {
          "cap_source": "SUB_LIMIT",
          "cap_amount": "2000.00"
        }
      },
      {
        "rule_id": "ANNUAL_LIMIT",
        "outcome": "PASS",
        "reason": "YTD claimed amount 5000.00 plus current claim 1500.00 is within annual OPD limit 50000.00.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {
          "ytd_claims_amount": "5000.00",
          "current_claim_amount": "1500.00",
          "projected_total": "6500.00",
          "annual_opd_limit": "50000.00",
          "remaining_after_claim": "43500.00"
        }
      },
      {
        "rule_id": "NETWORK_DISCOUNT",
        "outcome": "SKIP",
        "reason": "No network hospital discount applied.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COPAY_APPLICATION",
        "outcome": "PASS",
        "reason": "Copay applied.",
        "approved_amount": "1350.00",
        "deducted_amount": "150.00",
        "deduction_reason": "COPAY",
        "metadata": {}
      }
    ]
  }
}
```

## TC005 - Waiting Period — Diabetes

### Checks

```json
[
  {
    "name": "decision",
    "expected": "REJECTED",
    "actual": "REJECTED",
    "passed": true
  },
  {
    "name": "rejection_reasons",
    "expected": [
      "WAITING_PERIOD"
    ],
    "actual": [
      "WAITING_PERIOD"
    ],
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC005.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": [
      "Vikram Joshi",
      "Vikram Joshi"
    ]
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": "Vikram Joshi",
    "doctor_name": "Dr. Sunil Mehta",
    "doctor_registration": "GJ/56789/2014",
    "diagnosis_primary": "Type 2 Diabetes Mellitus",
    "treatment_date": "2024-10-15",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Type 2 Diabetes Mellitus",
        "amount": "3000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "3000",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95,
      "patient_name": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "3000.00",
    "line_items_sum": "3000.00",
    "claimed_amount": "3000.00",
    "payable_basis_amount": "3000.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": "Vikram Joshi",
    "doctor_name": "Dr. Sunil Mehta",
    "doctor_registration": "GJ/56789/2014",
    "diagnosis_primary": "Type 2 Diabetes Mellitus",
    "treatment_date": "2024-10-15",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Type 2 Diabetes Mellitus",
        "amount": "3000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "3000",
    "claimed_amount": "3000.00",
    "payable_basis_amount": "3000.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "REJECTED",
    "approved_amount": "0.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [
      {
        "rule_id": "WAITING_PERIOD",
        "reason": "Diabetes related claims are eligible from 2024-11-30."
      }
    ],
    "partial_items": null,
    "member_message": "Diabetes related claims are eligible from 2024-11-30.",
    "ops_summary": "Rejected due to WAITING_PERIOD.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "FAIL",
        "reason": "diabetes waiting period ends on 2024-11-30.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      }
    ]
  }
}
```

## TC006 - Dental Partial Approval — Cosmetic Exclusion

### Checks

```json
[
  {
    "name": "decision",
    "expected": "PARTIAL",
    "actual": "PARTIAL",
    "passed": true
  },
  {
    "name": "approved_amount",
    "expected": "8000.00",
    "actual": "8000.00",
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC006.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 1,
    "patient_name_match": true,
    "required_docs": [
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "HOSPITAL_BILL"
    ],
    "patient_names": [
      "Priya Singh"
    ]
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": "Priya Singh",
    "doctor_name": null,
    "doctor_registration": null,
    "diagnosis_primary": null,
    "treatment_date": "2024-10-15",
    "hospital_name": "Smile Dental Clinic",
    "line_items": [
      {
        "description": "Root Canal Treatment",
        "amount": "8000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Teeth Whitening",
        "amount": "4000",
        "coverage_hint": "EXCLUDED"
      }
    ],
    "total_amount": "12000",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95,
      "patient_name": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "12000.00",
    "line_items_sum": "12000.00",
    "claimed_amount": "12000.00",
    "payable_basis_amount": "12000.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": "Priya Singh",
    "doctor_name": null,
    "doctor_registration": null,
    "diagnosis_primary": null,
    "treatment_date": "2024-10-15",
    "hospital_name": "Smile Dental Clinic",
    "line_items": [
      {
        "description": "Root Canal Treatment",
        "amount": "8000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Teeth Whitening",
        "amount": "4000",
        "coverage_hint": "EXCLUDED"
      }
    ],
    "extracted_total_amount": "12000",
    "claimed_amount": "12000.00",
    "payable_basis_amount": "12000.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "PARTIAL",
    "approved_amount": "8000.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [],
    "partial_items": [
      {
        "description": "Root Canal Treatment",
        "amount": "8000.00",
        "decision": "APPROVED",
        "reason": "Covered dental item."
      },
      {
        "description": "Teeth Whitening",
        "amount": "4000.00",
        "decision": "REJECTED",
        "reason": "Excluded dental item: Teeth Whitening"
      }
    ],
    "member_message": "Your claim is partial for 8000.00.",
    "ops_summary": "Policy engine completed with decision PARTIAL.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "No active condition waiting period applies.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "EXCLUSION_CHECK",
        "outcome": "PASS",
        "reason": "No exclusion matched.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COVERAGE_CATEGORY",
        "outcome": "PASS",
        "reason": "Claim category is covered.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "DENTAL_LINE_ITEM_FILTER",
        "outcome": "PARTIAL",
        "reason": "Dental line items adjudicated.",
        "approved_amount": "8000.00",
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "PRE_AUTH_CHECK",
        "outcome": "PASS",
        "reason": "No missing pre-authorization detected.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "FRAUD_SIGNAL_CHECK",
        "outcome": "PASS",
        "reason": "No fraud threshold breach.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "BENEFIT_CAP",
        "outcome": "PASS",
        "reason": "Payable amount is within SUB_LIMIT cap 10000.00.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {
          "cap_source": "SUB_LIMIT",
          "cap_amount": "10000.00"
        }
      },
      {
        "rule_id": "ANNUAL_LIMIT",
        "outcome": "SKIP",
        "reason": "YTD amount not provided.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "NETWORK_DISCOUNT",
        "outcome": "SKIP",
        "reason": "No network hospital discount applied.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COPAY_APPLICATION",
        "outcome": "PASS",
        "reason": "Copay applied.",
        "approved_amount": "8000.00",
        "deducted_amount": "0.00",
        "deduction_reason": "COPAY",
        "metadata": {}
      }
    ]
  }
}
```

## TC007 - MRI Without Pre-Authorization

### Checks

```json
[
  {
    "name": "decision",
    "expected": "REJECTED",
    "actual": "REJECTED",
    "passed": true
  },
  {
    "name": "rejection_reasons",
    "expected": [
      "PRE_AUTH_MISSING"
    ],
    "actual": [
      "WAITING_PERIOD"
    ],
    "passed": false
  }
]
```

### Notes

Current policy order evaluates condition waiting period before pre-authorization; the diagnosis text contains herniation, which matches the hernia waiting-period term.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC007.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 3,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "LAB_REPORT",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "LAB_REPORT",
      "HOSPITAL_BILL"
    ],
    "patient_names": []
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": null,
    "doctor_name": "Dr. Venkat Rao",
    "doctor_registration": "AP/67890/2017",
    "diagnosis_primary": "Suspected Lumbar Disc Herniation",
    "treatment_date": "2024-11-02",
    "hospital_name": null,
    "line_items": [
      {
        "description": "MRI Lumbar Spine",
        "amount": "15000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "15000",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "15000.00",
    "line_items_sum": "15000.00",
    "claimed_amount": "15000.00",
    "payable_basis_amount": "15000.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": null,
    "doctor_name": "Dr. Venkat Rao",
    "doctor_registration": "AP/67890/2017",
    "diagnosis_primary": "Suspected Lumbar Disc Herniation",
    "treatment_date": "2024-11-02",
    "hospital_name": null,
    "line_items": [
      {
        "description": "MRI Lumbar Spine",
        "amount": "15000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "15000",
    "claimed_amount": "15000.00",
    "payable_basis_amount": "15000.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "REJECTED",
    "approved_amount": "0.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [
      {
        "rule_id": "WAITING_PERIOD",
        "reason": "Hernia related claims are eligible from 2025-04-01."
      }
    ],
    "partial_items": null,
    "member_message": "Hernia related claims are eligible from 2025-04-01.",
    "ops_summary": "Rejected due to WAITING_PERIOD.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "FAIL",
        "reason": "hernia waiting period ends on 2025-04-01.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      }
    ]
  }
}
```

## TC008 - Per-Claim Limit Exceeded

### Checks

```json
[
  {
    "name": "decision",
    "expected": "REJECTED",
    "actual": "REJECTED",
    "passed": true
  },
  {
    "name": "rejection_reasons",
    "expected": [
      "PER_CLAIM_EXCEEDED"
    ],
    "actual": [
      "SUB_LIMIT_EXCEEDED"
    ],
    "passed": false
  }
]
```

### Notes

Current policy treats the consultation sub-limit as the active cap before the general per-claim limit, so the reason is SUB_LIMIT_EXCEEDED instead of PER_CLAIM_EXCEEDED.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC008.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": []
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": null,
    "doctor_name": "Dr. R. Gupta",
    "doctor_registration": "DL/34567/2016",
    "diagnosis_primary": "Gastroenteritis",
    "treatment_date": "2024-10-20",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Consultation Fee",
        "amount": "2000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Medicines",
        "amount": "5500",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "7500",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "7500.00",
    "line_items_sum": "7500.00",
    "claimed_amount": "7500.00",
    "payable_basis_amount": "7500.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": null,
    "doctor_name": "Dr. R. Gupta",
    "doctor_registration": "DL/34567/2016",
    "diagnosis_primary": "Gastroenteritis",
    "treatment_date": "2024-10-20",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Consultation Fee",
        "amount": "2000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Medicines",
        "amount": "5500",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "7500",
    "claimed_amount": "7500.00",
    "payable_basis_amount": "7500.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "REJECTED",
    "approved_amount": "0.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [
      {
        "rule_id": "SUB_LIMIT_EXCEEDED",
        "reason": "The payable amount 7500.00 exceeds the sub limit cap of 2000.00."
      }
    ],
    "partial_items": null,
    "member_message": "The payable amount 7500.00 exceeds the sub limit cap of 2000.00.",
    "ops_summary": "Rejected due to SUB_LIMIT_EXCEEDED.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "No active condition waiting period applies.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "EXCLUSION_CHECK",
        "outcome": "PASS",
        "reason": "No exclusion matched.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COVERAGE_CATEGORY",
        "outcome": "PASS",
        "reason": "Claim category is covered.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "DENTAL_LINE_ITEM_FILTER",
        "outcome": "SKIP",
        "reason": "Not a dental claim.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "PRE_AUTH_CHECK",
        "outcome": "PASS",
        "reason": "No missing pre-authorization detected.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "FRAUD_SIGNAL_CHECK",
        "outcome": "PASS",
        "reason": "No fraud threshold breach.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "BENEFIT_CAP",
        "outcome": "FAIL",
        "reason": "Payable amount 7500.00 exceeds SUB_LIMIT cap 2000.00.",
        "approved_amount": "0.00",
        "deducted_amount": "7500.00",
        "deduction_reason": "SUB_LIMIT",
        "metadata": {
          "cap_source": "SUB_LIMIT",
          "cap_amount": "2000.00",
          "amount": "7500.00"
        }
      }
    ]
  }
}
```

## TC009 - Fraud Signal — Multiple Same-Day Claims

### Checks

```json
[
  {
    "name": "decision",
    "expected": "MANUAL_REVIEW",
    "actual": "MANUAL_REVIEW",
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC009.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": []
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 3,
  "extraction": {
    "patient_name": null,
    "doctor_name": "Dr. S. Khan",
    "doctor_registration": null,
    "diagnosis_primary": "Migraine",
    "treatment_date": "2024-10-30",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Migraine",
        "amount": "4800",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "4800",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "4800.00",
    "line_items_sum": "4800.00",
    "claimed_amount": "4800.00",
    "payable_basis_amount": "4800.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": null,
    "doctor_name": "Dr. S. Khan",
    "doctor_registration": null,
    "diagnosis_primary": "Migraine",
    "treatment_date": "2024-10-30",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Migraine",
        "amount": "4800",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "4800",
    "claimed_amount": "4800.00",
    "payable_basis_amount": "4800.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "MANUAL_REVIEW",
    "approved_amount": "0.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [],
    "partial_items": null,
    "member_message": "Unusual same-day claim pattern detected.",
    "ops_summary": "Manual review required by policy engine.",
    "confidence_score": 0.962,
    "manual_review_note": "Unusual same-day claim pattern detected.",
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "No active condition waiting period applies.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "EXCLUSION_CHECK",
        "outcome": "PASS",
        "reason": "No exclusion matched.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COVERAGE_CATEGORY",
        "outcome": "PASS",
        "reason": "Claim category is covered.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "DENTAL_LINE_ITEM_FILTER",
        "outcome": "SKIP",
        "reason": "Not a dental claim.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "PRE_AUTH_CHECK",
        "outcome": "PASS",
        "reason": "No missing pre-authorization detected.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "FRAUD_SIGNAL_CHECK",
        "outcome": "FAIL",
        "reason": "Same-day claim threshold exceeded.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      }
    ]
  }
}
```

## TC010 - Network Hospital — Discount Applied

### Checks

```json
[
  {
    "name": "decision",
    "expected": "APPROVED",
    "actual": "REJECTED",
    "passed": false
  },
  {
    "name": "approved_amount",
    "expected": "3240.00",
    "actual": "0.00",
    "passed": false
  }
]
```

### Notes

Current policy applies the consultation sub-limit before network discount and co-pay, so the claim is rejected before the expected discount calculation can run.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC010.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": [
      "Deepak Shah",
      "Deepak Shah"
    ]
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": "Deepak Shah",
    "doctor_name": "Dr. S. Iyer",
    "doctor_registration": "TN/56789/2013",
    "diagnosis_primary": "Acute Bronchitis",
    "treatment_date": "2024-11-03",
    "hospital_name": "Apollo Hospitals",
    "line_items": [
      {
        "description": "Consultation Fee",
        "amount": "1500",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Medicines",
        "amount": "3000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "4500",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95,
      "patient_name": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "4500.00",
    "line_items_sum": "4500.00",
    "claimed_amount": "4500.00",
    "payable_basis_amount": "4500.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": "Deepak Shah",
    "doctor_name": "Dr. S. Iyer",
    "doctor_registration": "TN/56789/2013",
    "diagnosis_primary": "Acute Bronchitis",
    "treatment_date": "2024-11-03",
    "hospital_name": "Apollo Hospitals",
    "line_items": [
      {
        "description": "Consultation Fee",
        "amount": "1500",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Medicines",
        "amount": "3000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "4500",
    "claimed_amount": "4500.00",
    "payable_basis_amount": "4500.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "REJECTED",
    "approved_amount": "0.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [
      {
        "rule_id": "SUB_LIMIT_EXCEEDED",
        "reason": "The payable amount 4500.00 exceeds the sub limit cap of 2000.00."
      }
    ],
    "partial_items": null,
    "member_message": "The payable amount 4500.00 exceeds the sub limit cap of 2000.00.",
    "ops_summary": "Rejected due to SUB_LIMIT_EXCEEDED.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "No active condition waiting period applies.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "EXCLUSION_CHECK",
        "outcome": "PASS",
        "reason": "No exclusion matched.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COVERAGE_CATEGORY",
        "outcome": "PASS",
        "reason": "Claim category is covered.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "DENTAL_LINE_ITEM_FILTER",
        "outcome": "SKIP",
        "reason": "Not a dental claim.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "PRE_AUTH_CHECK",
        "outcome": "PASS",
        "reason": "No missing pre-authorization detected.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "FRAUD_SIGNAL_CHECK",
        "outcome": "PASS",
        "reason": "No fraud threshold breach.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "BENEFIT_CAP",
        "outcome": "FAIL",
        "reason": "Payable amount 4500.00 exceeds SUB_LIMIT cap 2000.00.",
        "approved_amount": "0.00",
        "deducted_amount": "4500.00",
        "deduction_reason": "SUB_LIMIT",
        "metadata": {
          "cap_source": "SUB_LIMIT",
          "cap_amount": "2000.00",
          "amount": "4500.00"
        }
      }
    ]
  }
}
```

## TC011 - Component Failure — Graceful Degradation

### Checks

```json
[
  {
    "name": "decision",
    "expected": "APPROVED",
    "actual": "APPROVED",
    "passed": true
  },
  {
    "name": "component_failure_visible",
    "expected": "failed agent visible with reduced confidence and eval review recommendation",
    "actual": {
      "simulated_failure": true,
      "failed_agents": [
        "entity_extraction"
      ],
      "manual_review_recommended": true,
      "note": "Eval harness simulated a component failure without changing the production pipeline."
    },
    "passed": true
  }
]
```

### Notes

No notes.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC011.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": []
  },
  "failed_agents": [
    "entity_extraction"
  ],
  "component_simulation": {
    "simulated_failure": true,
    "failed_agents": [
      "entity_extraction"
    ],
    "manual_review_recommended": true,
    "note": "Eval harness simulated a component failure without changing the production pipeline."
  },
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": null,
    "doctor_name": "Vaidya T. Krishnan",
    "doctor_registration": "AYUR/KL/2345/2019",
    "diagnosis_primary": "Chronic Joint Pain",
    "treatment_date": "2024-10-28",
    "hospital_name": "Ayur Wellness Centre",
    "line_items": [
      {
        "description": "Panchakarma Therapy (5 sessions)",
        "amount": "3000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Consultation",
        "amount": "1000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "total_amount": "4000",
    "field_confidences": {
      "total_amount": 0.82,
      "amount": 0.82,
      "diagnosis_primary": 0.82,
      "treatment_date": 0.82
    },
    "missing_fields": [
      "simulated entity extraction component failure"
    ]
  },
  "reconciliation": {
    "bill_total_extracted": "4000.00",
    "line_items_sum": "4000.00",
    "claimed_amount": "4000.00",
    "payable_basis_amount": "4000.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": null,
    "doctor_name": "Vaidya T. Krishnan",
    "doctor_registration": "AYUR/KL/2345/2019",
    "diagnosis_primary": "Chronic Joint Pain",
    "treatment_date": "2024-10-28",
    "hospital_name": "Ayur Wellness Centre",
    "line_items": [
      {
        "description": "Panchakarma Therapy (5 sessions)",
        "amount": "3000",
        "coverage_hint": "UNCERTAIN"
      },
      {
        "description": "Consultation",
        "amount": "1000",
        "coverage_hint": "UNCERTAIN"
      }
    ],
    "extracted_total_amount": "4000",
    "claimed_amount": "4000.00",
    "payable_basis_amount": "4000.00",
    "extraction_confidence": 0.754,
    "failed_agents": [
      "entity_extraction"
    ],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.82,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "APPROVED",
    "approved_amount": "4000.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [],
    "partial_items": null,
    "member_message": "Your claim is approved for 4000.00.",
    "ops_summary": "Policy engine completed with decision APPROVED.",
    "confidence_score": 0.754,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "No active condition waiting period applies.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "EXCLUSION_CHECK",
        "outcome": "PASS",
        "reason": "No exclusion matched.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COVERAGE_CATEGORY",
        "outcome": "PASS",
        "reason": "Claim category is covered.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "DENTAL_LINE_ITEM_FILTER",
        "outcome": "SKIP",
        "reason": "Not a dental claim.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "PRE_AUTH_CHECK",
        "outcome": "PASS",
        "reason": "No missing pre-authorization detected.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "FRAUD_SIGNAL_CHECK",
        "outcome": "PASS",
        "reason": "No fraud threshold breach.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "BENEFIT_CAP",
        "outcome": "PASS",
        "reason": "Payable amount is within SUB_LIMIT cap 8000.00.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {
          "cap_source": "SUB_LIMIT",
          "cap_amount": "8000.00"
        }
      },
      {
        "rule_id": "ANNUAL_LIMIT",
        "outcome": "SKIP",
        "reason": "YTD amount not provided.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "NETWORK_DISCOUNT",
        "outcome": "SKIP",
        "reason": "No network hospital discount applied.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "COPAY_APPLICATION",
        "outcome": "PASS",
        "reason": "Copay applied.",
        "approved_amount": "4000.00",
        "deducted_amount": "0.00",
        "deduction_reason": "COPAY",
        "metadata": {}
      }
    ]
  }
}
```

## TC012 - Excluded Treatment

### Checks

```json
[
  {
    "name": "decision",
    "expected": "REJECTED",
    "actual": "REJECTED",
    "passed": true
  },
  {
    "name": "rejection_reasons",
    "expected": [
      "EXCLUDED_CONDITION"
    ],
    "actual": [
      "WAITING_PERIOD"
    ],
    "passed": false
  }
]
```

### Notes

Current policy checks obesity-related waiting period before exclusions, so WAITING_PERIOD fires before EXCLUDED_CONDITION.

### Full Decision Output

```json
{
  "stage": "policy_decision",
  "document_artifacts": [
    "documents/TC012.pdf"
  ],
  "gating": {
    "passed": true,
    "docs_validated": 2,
    "patient_name_match": true,
    "required_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "found_docs": [
      "PRESCRIPTION",
      "HOSPITAL_BILL"
    ],
    "patient_names": []
  },
  "failed_agents": [],
  "component_simulation": null,
  "same_day_claim_count": 0,
  "extraction": {
    "patient_name": null,
    "doctor_name": "Dr. P. Banerjee",
    "doctor_registration": "WB/34567/2015",
    "diagnosis_primary": "Morbid Obesity \u2014 BMI 37",
    "treatment_date": "2024-10-18",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Bariatric Consultation",
        "amount": "3000",
        "coverage_hint": "EXCLUDED"
      },
      {
        "description": "Personalised Diet and Nutrition Program",
        "amount": "5000",
        "coverage_hint": "EXCLUDED"
      }
    ],
    "total_amount": "8000",
    "field_confidences": {
      "total_amount": 0.95,
      "amount": 0.95,
      "diagnosis_primary": 0.95,
      "treatment_date": 0.95
    },
    "missing_fields": []
  },
  "reconciliation": {
    "bill_total_extracted": "8000.00",
    "line_items_sum": "8000.00",
    "claimed_amount": "8000.00",
    "payable_basis_amount": "8000.00",
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "agent_status": "SUCCESS"
  },
  "merged_claim": {
    "patient_name": null,
    "doctor_name": "Dr. P. Banerjee",
    "doctor_registration": "WB/34567/2015",
    "diagnosis_primary": "Morbid Obesity \u2014 BMI 37",
    "treatment_date": "2024-10-18",
    "hospital_name": null,
    "line_items": [
      {
        "description": "Bariatric Consultation",
        "amount": "3000",
        "coverage_hint": "EXCLUDED"
      },
      {
        "description": "Personalised Diet and Nutrition Program",
        "amount": "5000",
        "coverage_hint": "EXCLUDED"
      }
    ],
    "extracted_total_amount": "8000",
    "claimed_amount": "8000.00",
    "payable_basis_amount": "8000.00",
    "extraction_confidence": 0.962,
    "failed_agents": [],
    "conflict_log": [],
    "discrepancy_flags": [],
    "fraud_indicators": [],
    "document_confidence": 0.956,
    "entity_confidence": 0.95,
    "reconciliation_confidence": 1.0
  },
  "policy_decision": {
    "decision": "REJECTED",
    "approved_amount": "0.00",
    "copay_deducted": "0.00",
    "network_discount_applied": "0.00",
    "rejection_reasons": [
      {
        "rule_id": "WAITING_PERIOD",
        "reason": "Obesity Treatment related claims are eligible from 2025-04-01."
      }
    ],
    "partial_items": null,
    "member_message": "Obesity Treatment related claims are eligible from 2025-04-01.",
    "ops_summary": "Rejected due to WAITING_PERIOD.",
    "confidence_score": 0.962,
    "manual_review_note": null,
    "rule_results": [
      {
        "rule_id": "MEMBER_ELIGIBILITY",
        "outcome": "PASS",
        "reason": "Member exists in policy roster.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "POLICY_ACTIVE",
        "outcome": "PASS",
        "reason": "Treatment date is within policy period.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "MINIMUM_CLAIM_AMOUNT",
        "outcome": "PASS",
        "reason": "Claim amount meets minimum threshold.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "INITIAL_WAITING_PERIOD",
        "outcome": "PASS",
        "reason": "Initial waiting period completed.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      },
      {
        "rule_id": "CONDITION_WAITING_PERIOD",
        "outcome": "FAIL",
        "reason": "obesity treatment waiting period ends on 2025-04-01.",
        "approved_amount": null,
        "deducted_amount": null,
        "deduction_reason": null,
        "metadata": {}
      }
    ]
  }
}
```
