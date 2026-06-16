# Backend Setup

FastAPI backend for the claims processing system. It exposes claim submission, claim status, policy/member lookup, test-suite execution, and LLM metrics APIs.

## Requirements

- Python 3.13+
- `pip` or `uv`
- Optional: PostgreSQL if you do not want to use local SQLite

## Install Dependencies

From the repository root:

```powershell
pip install -r backend/requirements.txt
```

Or with `uv`:

```powershell
cd backend
uv sync --all-extras
```

## Environment Variables

Create a local environment file from the example:

```powershell
Copy-Item backend\.env.example backend\.env
```

For a deterministic local demo without provider keys:

```dotenv
LLM_PROVIDER=stub
USE_STUB_LLM=true
```

For a real provider, set `USE_STUB_LLM=false` and configure the matching provider key. Do not commit real `.env` files or secrets.

Database options:

```dotenv
# Optional. If omitted, the backend uses local SQLite.
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB_NAME

# Optional. If omitted, claim artifacts are written under backend/common/claims.
CLAIMS_STORAGE_ROOT=backend/common/claims
```

If your database password contains special characters, URL-encode it before putting it in `DATABASE_URL`.

## Run Locally

From the repository root:

```powershell
python backend/main.py --reload
```

Backend URL:

```text
http://127.0.0.1:8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Main API Endpoints

```text
GET  /health
GET  /api/claims/policies/members
GET  /api/claims/policy-options
POST /api/claims
GET  /api/claims
GET  /api/claims/{claim_id}/status
GET  /api/claims/test-suite
POST /api/claims/test-suite/{case_id}/run
GET  /api/claims/llm-metrics/summary
GET  /api/claims/llm-metrics/recent
```

## Tests and Coverage

Stored backend coverage artifacts:

- HTML report: [../docs/test_coverage/Backend_test_coverage.html](../docs/test_coverage/Backend_test_coverage.html)
- Screenshot: [../docs/test_coverage/Backend_test_coverage.png](../docs/test_coverage/Backend_test_coverage.png)

Run backend tests with terminal coverage:

```powershell
python -m pytest --cov-report=term
```

Generate an HTML coverage report:

```powershell
python -m pytest --cov-report=html
Start-Process ..\htmlcov\index.html
```

The repository config enforces an 80% backend coverage threshold through `pytest.ini`.
