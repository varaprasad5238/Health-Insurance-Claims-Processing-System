# Frontend Setup

Next.js frontend for the claims processing system. It provides claim submission, claim listing, claim detail/trace view, assignment test-suite execution, and LLM metrics screens.

## Deployed App

https://main.d3lqcxg9qxiznv.amplifyapp.com/

## Requirements

- Node.js 20+
- npm
- Backend API running locally at `http://localhost:8000` or a deployed backend API URL

## Install Dependencies

From the `frontend` directory:

```powershell
npm install
```

## Environment Variables

The frontend reads the backend API base URL from `NEXT_PUBLIC_API_BASE_URL`.

For local backend development, create `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

If this variable is omitted, the app defaults to `http://localhost:8000`.

## Run Locally

```powershell
npm run dev
```

Open:

```text
http://localhost:3000
```

## Scripts

```powershell
npm run dev            # start local development server
npm run build          # create production build
npm run start          # run production build locally
npm run lint           # run ESLint
npm test               # run Vitest tests
npm run test:coverage  # run Vitest coverage
```

## Coverage Reports

Stored frontend coverage artifacts:

- HTML report: [../docs/test_coverage/frontend_test_coverage.html](../docs/test_coverage/frontend_test_coverage.html)
- Screenshot: [../docs/test_coverage/frontend_test_coverage.png](../docs/test_coverage/frontend_test_coverage.png)

## Main Pages

```text
/                 Dashboard/home
/submit           Submit a new claim
/claims           Claim list
/claims/[id]      Claim status, decision, and trace detail
/test-suite       Run assignment test-suite cases
/llm-metrics      Inspect LLM usage and fallback metrics
```

## Local Development Flow

1. Start the backend first.
2. Confirm backend health at `http://localhost:8000/health`.
3. Start the frontend with `npm run dev`.
4. Open `http://localhost:3000`.
