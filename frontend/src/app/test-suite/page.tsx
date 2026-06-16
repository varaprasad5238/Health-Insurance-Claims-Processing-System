"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, CheckCircle2, ClipboardList, Loader2, Play, XCircle } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const RUN_STATE_STORAGE_KEY = "plum.claims.testSuite.runStates.v1";

type SuiteCase = {
  case_id: string;
  case_name: string;
  description: string;
  member_id: string;
  claim_category: string;
  claimed_amount: number;
  expected_decision: string | null;
  expected_approved_amount: number | null;
  documents: string[];
  test_context: Record<string, unknown>;
  api_mode_note: string;
};

type RunState = {
  claimId?: string;
  status: "idle" | "submitting" | "processing" | "complete" | "error";
  claimStatus?: string;
  decision?: string | null;
  expectedDecision?: string | null;
  error?: string;
};

type ClaimStatus = {
  claim_id: string;
  status: string;
  decision: { decision: string } | null;
  gating_error: { error_code: string } | null;
};

export default function TestSuitePage() {
  const [cases, setCases] = useState<SuiteCase[]>([]);
  const [runStates, setRunStates] = useState<Record<string, RunState>>({});
  const [loading, setLoading] = useState(true);
  const [runningAll, setRunningAll] = useState(false);
  const [storageReady, setStorageReady] = useState(false);

  const pollClaim = async (caseId: string, claimId: string, expectedDecision: string | null) => {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const response = await fetch(`${API_BASE_URL}/api/claims/${encodeURIComponent(claimId)}/status`);
      if (response.ok) {
        const payload: ClaimStatus = await response.json();
        const done = ["DECIDED", "MANUAL_REVIEW", "GATING_FAILED"].includes(payload.status);
        setRunStates((current) => ({
          ...current,
          [caseId]: {
            ...current[caseId],
            claimId,
            status: done ? "complete" : "processing",
            claimStatus: payload.status,
            decision: payload.decision?.decision ?? null,
            expectedDecision,
          },
        }));
        if (done) return;
      }
      await delay(1500);
    }

    setRunStates((current) => ({
      ...current,
      [caseId]: {
        ...current[caseId],
        claimId,
        status: "error",
        expectedDecision,
        error: "Timed out waiting for claim processing.",
      },
    }));
  };

  useEffect(() => {
    const loadCases = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/claims/test-suite`);
        if (!response.ok) throw new Error(`Failed to load suite: ${response.status}`);
        const payload = await response.json();
        setCases(payload.cases ?? []);
      } catch (error) {
        console.error(error);
        setCases([]);
      } finally {
        setLoading(false);
      }
    };
    loadCases();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const stored = window.localStorage.getItem(RUN_STATE_STORAGE_KEY);
      if (!stored) {
        setStorageReady(true);
        return;
      }
      try {
        const parsed = JSON.parse(stored) as Record<string, RunState>;
        setRunStates(parsed);
        setStorageReady(true);
        for (const [caseId, state] of Object.entries(parsed)) {
          if (state.claimId && state.status !== "complete") {
            void pollClaim(caseId, state.claimId, state.expectedDecision ?? null);
          }
        }
      } catch {
        window.localStorage.removeItem(RUN_STATE_STORAGE_KEY);
        setStorageReady(true);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!storageReady) return;
    window.localStorage.setItem(RUN_STATE_STORAGE_KEY, JSON.stringify(runStates));
  }, [runStates, storageReady]);

  const summary = useMemo(() => {
    const states = Object.values(runStates);
    return {
      total: cases.length,
      submitted: states.filter((state) => state.claimId).length,
      complete: states.filter((state) => state.status === "complete").length,
      errors: states.filter((state) => state.status === "error").length,
    };
  }, [cases.length, runStates]);

  const runCase = async (suiteCase: SuiteCase) => {
    if (runStates[suiteCase.case_id]?.claimId) {
      return;
    }

    setRunStates((current) => ({
      ...current,
      [suiteCase.case_id]: {
        status: "submitting",
        expectedDecision: suiteCase.expected_decision,
      },
    }));

    try {
      const response = await fetch(`${API_BASE_URL}/api/claims/test-suite/${encodeURIComponent(suiteCase.case_id)}/run`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok || !payload.claim_id) {
        throw new Error(payload.detail || "Suite case submission failed.");
      }

      setRunStates((current) => ({
        ...current,
        [suiteCase.case_id]: {
          status: "processing",
          claimId: payload.claim_id,
          claimStatus: payload.status,
          expectedDecision: suiteCase.expected_decision,
        },
      }));

      await pollClaim(suiteCase.case_id, payload.claim_id, suiteCase.expected_decision);
    } catch (error) {
      setRunStates((current) => ({
        ...current,
        [suiteCase.case_id]: {
          status: "error",
          expectedDecision: suiteCase.expected_decision,
          error: error instanceof Error ? error.message : "Unknown error",
        },
      }));
    }
  };

  const runAll = async () => {
    setRunningAll(true);
    for (const suiteCase of cases) {
      if (runStates[suiteCase.case_id]?.claimId) {
        continue;
      }
      await runCase(suiteCase);
    }
    setRunningAll(false);
  };

  return (
    <main className="app-shell">
      <div className="app-frame space-y-5">
        <header className="glass-panel rounded-[24px] px-5 py-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <span className="brand-mark">
                <ClipboardList className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.24em] text-muted">Plum Claims</p>
                <h1 className="text-xl font-black tracking-tight sm:text-2xl">Test Suite Runner</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggle />
              <Link href="/" className="secondary-button">
                <ArrowLeft className="h-4 w-4" /> Dashboard
              </Link>
              <button type="button" className="primary-button" onClick={runAll} disabled={loading || runningAll || cases.length === 0 || summary.submitted === cases.length}>
                {runningAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {runningAll ? "Running" : summary.submitted === cases.length ? "All Submitted" : "Run All"}
              </button>
            </div>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-4">
          <StatCard label="Cases" value={summary.total} />
          <StatCard label="Submitted" value={summary.submitted} />
          <StatCard label="Complete" value={summary.complete} />
          <StatCard label="Errors" value={summary.errors} tone={summary.errors > 0 ? "danger" : "normal"} />
        </section>

        <section className="glass-panel rounded-[24px] p-5">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-black">Assignment Cases</h2>
              <p className="text-sm text-muted">Run cases sequentially through backend API mode, then open the generated claim trace.</p>
            </div>
            <span className="status-pill">
              <Activity className="h-3.5 w-3.5" /> API Mode
            </span>
          </div>

          <div className="overflow-hidden rounded-2xl border hairline">
            <div className="hidden grid-cols-[0.65fr_1.3fr_0.8fr_0.75fr_0.85fr_0.8fr] gap-3 bg-[var(--surface-muted)] px-4 py-3 text-xs font-black uppercase tracking-[0.12em] text-muted lg:grid">
              <div>Case</div>
              <div>Scenario</div>
              <div>Category</div>
              <div>Expected</div>
              <div>Run Status</div>
              <div>Action</div>
            </div>

            {loading && <div className="p-5 text-sm text-muted">Loading test cases...</div>}
            {!loading && cases.length === 0 && <div className="p-5 text-sm text-muted">No test cases found.</div>}
            {!loading && cases.map((suiteCase) => (
              <SuiteCaseRow
                key={suiteCase.case_id}
                suiteCase={suiteCase}
                state={runStates[suiteCase.case_id] ?? { status: "idle", expectedDecision: suiteCase.expected_decision }}
                disabled={runningAll}
                onRun={() => runCase(suiteCase)}
              />
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function SuiteCaseRow({ suiteCase, state, disabled, onRun }: { suiteCase: SuiteCase; state: RunState; disabled: boolean; onRun: () => void }) {
  const router = useRouter();
  const statusLabel = state.claimStatus ?? state.status;
  const decisionMatched = state.status === "complete" && state.expectedDecision === state.decision;
  const expected = suiteCase.expected_decision ?? "Gate stop";

  return (
    <div
      className={`grid gap-3 border-t hairline px-4 py-4 transition hover:bg-[var(--surface-muted)] lg:grid-cols-[0.65fr_1.3fr_0.8fr_0.75fr_0.85fr_0.8fr] lg:items-center ${state.claimId ? "cursor-pointer" : ""}`}
      role={state.claimId ? "link" : undefined}
      tabIndex={state.claimId ? 0 : undefined}
      onClick={() => state.claimId && router.push(`/claims/${state.claimId}`)}
      onKeyDown={(event) => {
        if (state.claimId && (event.key === "Enter" || event.key === " ")) {
          router.push(`/claims/${state.claimId}`);
        }
      }}
    >
      <div>
        <div className="font-black">{suiteCase.case_id}</div>
        <div className="text-xs text-muted">{suiteCase.member_id} · ₹{suiteCase.claimed_amount}</div>
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-black">{suiteCase.case_name}</div>
        <div className="mt-1 line-clamp-2 text-xs leading-5 text-muted">{suiteCase.description}</div>
      </div>
      <div className="text-sm font-bold">{suiteCase.claim_category.replace("_", " ")}</div>
      <div>
        <span className="status-pill">{expected}</span>
      </div>
      <div className="space-y-1">
        <span className={`status-pill ${stateTone(state.status)}`}>{statusLabel.replace("_", " ")}</span>
        {state.claimId && <div className="truncate text-xs text-muted">{state.claimId}</div>}
        {state.status === "complete" && state.expectedDecision && (
          <div className={`flex items-center gap-1 text-xs font-bold ${decisionMatched ? "text-[var(--success)]" : "text-[var(--warning)]"}`}>
            {decisionMatched ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
            Actual {state.decision ?? "none"}
          </div>
        )}
        {state.error && <div className="text-xs font-bold text-[var(--danger)]">{state.error}</div>}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className="secondary-button min-w-24" onClick={(event) => { event.stopPropagation(); onRun(); }} disabled={disabled || Boolean(state.claimId) || state.status === "submitting" || state.status === "processing"}>
          {state.status === "submitting" || state.status === "processing" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {state.claimId ? "Locked" : "Run"}
        </button>
        {state.claimId && (
          <span className="primary-button min-w-24">
            Trace <ArrowRight className="h-4 w-4" />
          </span>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, tone = "normal" }: { label: string; value: number; tone?: "normal" | "danger" }) {
  return (
    <div className="glass-card rounded-2xl p-4">
      <div className={`text-2xl font-black ${tone === "danger" ? "text-[var(--danger)]" : ""}`}>{value}</div>
      <div className="mt-1 text-sm font-bold text-muted">{label}</div>
    </div>
  );
}

function stateTone(status: RunState["status"]) {
  if (status === "complete") return "text-[var(--success)]";
  if (status === "submitting" || status === "processing") return "text-[var(--brand-strong)]";
  if (status === "error") return "text-[var(--danger)]";
  return "text-muted";
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}