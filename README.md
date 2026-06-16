# Health Insurance Claims Processing System

AI-powered OPD health insurance claims processing system with a FastAPI backend, a Next.js frontend, deterministic policy rules, document processing, trace reconstruction, and LLM-backed extraction/synthesis stages.

## Deployed App

The fully functional deployed application is available at:

https://main.d3lqcxg9qxiznv.amplifyapp.com/

## Project Structure

```text
assignment/      Policy terms, assignment test cases, sample document guide
backend/         FastAPI API, workflow pipeline, policy engine, database models
frontend/        Next.js application for claim submission, claims, traces, metrics
docs/            Architecture, design, research, evaluation notes
test_suite/      Local assignment test-suite documents and inputs
```

## Local Backend Setup

Run these commands from the repository root unless stated otherwise.

1. Create or select a Python environment.

	This project expects Python 3.13 or newer. If you already have the repo virtual environment, use it:

	```powershell
	.\.venv\Scripts\Activate.ps1
	```

2. Install backend dependencies.

	```powershell
	pip install -r backend/requirements.txt
	```

	Or, if you use `uv`:

	```powershell
	cd backend
	uv sync --all-extras
	cd ..
	```

3. Configure backend environment variables.

	```powershell
	Copy-Item backend\.env.example backend\.env
	```

	For a no-key local demo, keep:

	```dotenv
	LLM_PROVIDER=stub
	USE_STUB_LLM=true
	```

	For a real LLM provider, set `USE_STUB_LLM=false` and provide the matching provider API key in `backend/.env`.

	For local SQLite, no `DATABASE_URL` is required. For PostgreSQL, add a SQLAlchemy async URL:

	```dotenv
	DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB_NAME
	```

4. Start the backend API.

	```powershell
	python backend/main.py --reload
	```

	The API runs at:

	```text
	http://127.0.0.1:8000
	```

5. Check backend health.

	```powershell
	Invoke-RestMethod http://127.0.0.1:8000/health
	```

## Local Frontend Setup

1. Install frontend dependencies.

	```powershell
	cd frontend
	npm install
	```

2. Configure the frontend API URL.

	The frontend defaults to `http://localhost:8000`. To set it explicitly, create `frontend/.env.local`:

	```dotenv
	NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
	```

3. Start the frontend.

	```powershell
	npm run dev
	```

	Open:

	```text
	http://localhost:3000
	```

## Useful Commands

Stored coverage reports are available in [docs/test_coverage](docs/test_coverage):

- Backend HTML report: [docs/test_coverage/Backend_test_coverage.html](docs/test_coverage/Backend_test_coverage.html)
- Backend screenshot: [docs/test_coverage/Backend_test_coverage.png](docs/test_coverage/Backend_test_coverage.png)
- Frontend HTML report: [docs/test_coverage/frontend_test_coverage.html](docs/test_coverage/frontend_test_coverage.html)
- Frontend screenshot: [docs/test_coverage/frontend_test_coverage.png](docs/test_coverage/frontend_test_coverage.png)
- Evaluation report: [docs/test_coverage/eval_report.md](docs/test_coverage/eval_report.md)

Run backend tests with coverage:

```powershell
python -m pytest --cov-report=term
```

Generate an HTML backend coverage report:

```powershell
python -m pytest --cov-report=html
Start-Process .\htmlcov\index.html
```

Run frontend linting:

```powershell
cd frontend
npm run lint
```

Run frontend tests:

```powershell
cd frontend
npm test
```

Build frontend production bundle:

```powershell
cd frontend
npm run build
```

## Main Local URLs

```text
Frontend: http://localhost:3000
Backend:  http://127.0.0.1:8000
Health:   http://127.0.0.1:8000/health
```

## Notes

- Do not commit real `.env` files or API keys.
- `backend/.env.example` is safe to commit and should be used as the template.
- The backend can run with stub LLM responses for repeatable local demos.
- PostgreSQL is supported through `DATABASE_URL`; SQLite remains the zero-config local default.