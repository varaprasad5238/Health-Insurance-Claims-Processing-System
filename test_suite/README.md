# Test Suite

This folder contains the assignment PDF artifacts arranged by test case.

Each case folder has this shape:

```text
TC001/
  input.json
  documents/
    TC001.pdf
```

The lightweight `input.json` files identify the case and document artifacts. The authoritative test metadata, expected decisions, and synthetic document content stay in `../assignment/test_cases.json` to avoid duplicating case definitions.

Run the Phase 1 component eval from the repository root:

```bash
c:/Users/ganprasa2/Health-Insurance-Claims-Processing-System/.venv/Scripts/python.exe backend/scripts/run_eval_suite.py --mode component
```

The runner writes:

```text
docs/eval_report.json
docs/eval_report.md
```