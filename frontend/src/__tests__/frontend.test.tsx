import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClaimsHistoryPage from "@/app/claims/page";
import ClaimDetail from "@/app/claims/[id]/page";
import Home from "@/app/page";
import LLMMetricsPage from "@/app/llm-metrics/page";
import SubmitClaim from "@/app/submit/page";
import TestSuitePage from "@/app/test-suite/page";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import ThemeToggle from "@/components/ThemeToggle";
import TraceViewer from "@/components/TraceViewer";

type FetchMock = ReturnType<typeof vi.fn>;

declare global {
  var __mockRouter: { push: ReturnType<typeof vi.fn> };
  var __setMockParams: (params: Record<string, string>) => void;
}

const claimSummary = {
  claim_id: "CLM-1",
  member_id: "EMP001",
  claim_category: "DENTAL",
  claimed_amount: "2500",
  status: "DECIDED",
  current_stage: null,
  updated_at: "2026-06-16T10:00:00Z",
  created_at: "2026-06-16T09:00:00Z",
  decision: "APPROVED",
  approved_amount: "2200",
  confidence_score: 0.91,
};

function jsonResponse(payload: unknown, ok = true) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(payload),
  } as Response);
}

function mockFetch(implementation: Parameters<typeof vi.fn>[0]) {
  global.fetch = vi.fn(implementation) as unknown as typeof fetch;
  return global.fetch as unknown as FetchMock;
}

function makeFile(name: string, size: number, type = "application/pdf") {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function fillRequiredSubmitFields(container: HTMLElement) {
  fireEvent.change(screen.getByLabelText(/treatment date/i), { target: { value: "2026-06-16" } });
  fireEvent.change(container.querySelector('input[name="claimed_amount"]') as HTMLInputElement, { target: { value: "1500" } });
}

describe("shared components", () => {
  it("renders confidence, trace output, and toggles persisted theme", async () => {
    render(
      <>
        <ConfidenceBadge score={0.9} />
        <TraceViewer traceId="trace-42" />
        <ThemeToggle />
      </>,
    );

    expect(screen.getByText("Confidence: 90%")).toBeInTheDocument();
    expect(screen.getByText("Trace ID: trace-42")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /switch to dark theme/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /switch to dark theme/i }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("plum-theme")).toBe("dark");
  });
});

describe("home page", () => {
  beforeEach(() => {
    mockFetch(() => jsonResponse({ claims: [claimSummary] }));
  });

  it("loads recent claims and renders dashboard navigation", async () => {
    render(<Home />);

    expect(screen.getByRole("heading", { name: /claims processing system/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /new claim/i })[0]).toHaveAttribute("href", "/submit");
    expect(await screen.findByText("CLM-1")).toBeInTheDocument();
    expect(screen.getByText(/EMP001 · DENTAL · ₹2500/)).toBeInTheDocument();
  });

  it("shows an empty worklist when the API fails", async () => {
    mockFetch(() => jsonResponse({}, false));

    render(<Home />);

    expect(await screen.findByText(/no claims submitted yet/i)).toBeInTheDocument();
  });
});

describe("submit claim page", () => {
  beforeEach(() => {
    mockFetch((url: string, init?: RequestInit) => {
      if (!init) return jsonResponse({ network_hospitals: ["Apollo Hospital"] });
      return jsonResponse({ claim_id: "CLM-99" });
    });
    vi.spyOn(window, "alert").mockImplementation(() => undefined);
  });

  it("loads policy options, accepts documents, submits, and navigates", async () => {
    const { container } = render(<SubmitClaim />);

    expect(await screen.findByRole("option", { name: "Apollo Hospital" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/upload documents/i), {
      target: { files: [makeFile("bill.pdf", 1024)] },
    });
    expect(await screen.findByText("bill.pdf")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/treatment date/i), { target: { value: "2026-06-16" } });
    fireEvent.change(container.querySelector('input[name="claimed_amount"]') as HTMLInputElement, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^submit claim$/i }));

    await waitFor(() => expect(global.__mockRouter.push).toHaveBeenCalledWith("/claims/CLM-99"));
  });

  it("guards missing and oversized uploads", async () => {
    const { container } = render(<SubmitClaim />);

    fillRequiredSubmitFields(container);
    fireEvent.click(screen.getByRole("button", { name: /^submit claim$/i }));
    expect(window.alert).toHaveBeenCalledWith("Please upload at least one claim document.");

    fireEvent.change(screen.getByLabelText(/upload documents/i), {
      target: { files: [makeFile("giant.pdf", 4 * 1024 * 1024)] },
    });

    expect(await screen.findByText(/giant.pdf was skipped/i)).toBeInTheDocument();
  });

  it("handles duplicate files, removal, invalid amounts, and failed submissions", async () => {
    const file = makeFile("bill.pdf", 1024);
    const { container } = render(<SubmitClaim />);

    fireEvent.change(screen.getByLabelText(/upload documents/i), { target: { files: [file] } });
    expect(await screen.findByText("bill.pdf")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/upload documents/i), { target: { files: [file] } });
    expect(await screen.findByText(/bill.pdf is already selected/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /remove bill.pdf/i }));
    expect(await screen.findByText("bill.pdf removed.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/upload documents/i), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText(/treatment date/i), { target: { value: "2026-06-16" } });
    fireEvent.change(container.querySelector('input[name="claimed_amount"]') as HTMLInputElement, { target: { value: "100" } });
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    expect(window.alert).toHaveBeenCalledWith("Claimed amount must be between ₹500 and ₹50000.");

    mockFetch((url: string, init?: RequestInit) => {
      if (!init) return jsonResponse({ network_hospitals: [] });
      return jsonResponse({});
    });
    fireEvent.change(container.querySelector('input[name="claimed_amount"]') as HTMLInputElement, { target: { value: "1500" } });
    fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    await waitFor(() => expect(window.alert).toHaveBeenCalledWith("Submission failed."));
  });
});

describe("claims history page", () => {
  beforeEach(() => {
    mockFetch(() => jsonResponse({ page: 1, page_size: 10, total: 1, total_pages: 2, claims: [claimSummary] }));
  });

  it("loads claims, applies filters, and paginates", async () => {
    render(<ClaimsHistoryPage />);

    expect(await screen.findByText("CLM-1")).toBeInTheDocument();
    expect(screen.getByText("1 claim found")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: "DECIDED" } });
    fireEvent.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect((global.fetch as unknown as FetchMock).mock.calls.at(-1)?.[0]).toContain("page=2");
    });

    fireEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(screen.getByLabelText(/status/i)).toHaveValue("");
  });
});

describe("claim detail page", () => {
  it("renders a decided claim trace and expands span details", async () => {
    global.__setMockParams({ id: "CLM-1" });
    mockFetch(() => jsonResponse({
      ...claimSummary,
      spans: [
        {
          span_id: "s1",
          agent_name: "gating",
          stage_order: 2,
          status: "SUCCESS",
          elapsed_ms: 15,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { rules_evaluated: 2 },
          confidence_delta: 0.1,
          errors: [],
          model_used: "rules",
        },
      ],
      decision: {
        decision: "APPROVED",
        approved_amount: "2200",
        copay_deducted: "200",
        network_discount_applied: "100",
        member_message: "Approved for payment.",
        confidence_score: 0.92,
        ops_summary: "Clean approval.",
        manual_review_note: null,
      },
      gating_error: null,
    }));

    render(<ClaimDetail />);

    expect(await screen.findByRole("heading", { name: /decision review/i })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Document gating"));
    expect(await screen.findByText(/model used/i)).toBeInTheDocument();
    expect(screen.getByText("Approved for payment.")).toBeInTheDocument();
  });

  it("handles missing params and gating failures", async () => {
    global.__setMockParams({});
    const { unmount } = render(<ClaimDetail />);
    expect(screen.getByText(/claim id missing/i)).toBeInTheDocument();
    unmount();

    global.__setMockParams({ id: "CLM-2" });
    mockFetch(() => jsonResponse({
      ...claimSummary,
      claim_id: "CLM-2",
      status: "GATING_FAILED",
      spans: [],
      decision: null,
      gating_error: { human_message: "Prescription is missing." },
    }));

    render(<ClaimDetail />);
    expect(await screen.findByText("Prescription is missing.")).toBeInTheDocument();
  });

  it("renders varied pipeline span summaries and null decisions", async () => {
    global.__setMockParams({ id: "CLM-3" });
    mockFetch(() => jsonResponse({
      ...claimSummary,
      claim_id: "CLM-3",
      status: "PROCESSING",
      spans: [
        {
          span_id: "v1",
          agent_name: "vision_read_doc_1",
          stage_order: 1,
          status: "SUCCESS",
          elapsed_ms: 30,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { document_type: "bill", readability: "high", quality_flags: ["clear"] },
          confidence_delta: null,
          errors: [],
          model_used: "vision",
        },
        {
          span_id: "e1",
          agent_name: "entity_extraction",
          stage_order: 3,
          status: "SUCCESS",
          elapsed_ms: 40,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { fields_extracted: 6, confidence: 0.84 },
          confidence_delta: 0.2,
          errors: [],
          model_used: "extractor",
        },
        {
          span_id: "a1",
          agent_name: "amount_reconciler",
          stage_order: 4,
          status: "ERROR",
          elapsed_ms: 12,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { discrepancies: 1, fraud_indicators: 0 },
          confidence_delta: null,
          errors: ["Amount mismatch"],
          model_used: "rules",
        },
        {
          span_id: "o1",
          agent_name: "orchestrator",
          stage_order: 5,
          status: "SKIPPED",
          elapsed_ms: 0,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { merged_confidence: 0.5, failed_agents: ["amount"] },
          confidence_delta: null,
          errors: ["Waiting for clean inputs"],
          model_used: "none",
        },
        {
          span_id: "p1",
          agent_name: "policy_engine",
          stage_order: 6,
          status: "RUNNING",
          elapsed_ms: null,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: null,
          output_summary: { rules_evaluated: 4, rules_failed: 1, rules_skipped: 2 },
          confidence_delta: null,
          errors: [],
          model_used: "rules",
        },
        {
          span_id: "d1",
          agent_name: "decision_synthesis",
          stage_order: 7,
          status: "TIMEOUT",
          elapsed_ms: 1000,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { decision: "MANUAL_REVIEW", approved_amount: 0 },
          confidence_delta: null,
          errors: ["Timed out"],
          model_used: "llm",
        },
        {
          span_id: "f1",
          agent_name: "final",
          stage_order: 8,
          status: "SUCCESS",
          elapsed_ms: 2,
          started_at: "2026-06-16T09:00:00Z",
          ended_at: "2026-06-16T09:00:01Z",
          output_summary: { decision: "pending" },
          confidence_delta: null,
          errors: [],
          model_used: "rules",
        },
      ],
      decision: null,
      gating_error: null,
    }));

    render(<ClaimDetail />);

    expect(await screen.findByText(/Type: bill · Readability high/i)).toBeInTheDocument();
    expect(screen.getByText(/6 fields extracted · confidence 0.84/i)).toBeInTheDocument();
    expect(screen.getByText("Amount mismatch")).toBeInTheDocument();
    expect(screen.getByText("Waiting for clean inputs")).toBeInTheDocument();
    expect(screen.getByText(/4 rules evaluated · 1 failed · 2 skipped/i)).toBeInTheDocument();
    expect(screen.getByText("Timed out")).toBeInTheDocument();
    expect(screen.getByText("Claim pending")).toBeInTheDocument();
  });
});

describe("llm metrics page", () => {
  beforeEach(() => {
    mockFetch((url: string) => {
      if (url.includes("summary")) {
        return jsonResponse({
          total_calls: 10,
          successful_calls: 8,
          failed_calls: 2,
          fallback_calls: 1,
          success_rate: 0.8,
          fallback_rate: 0.1,
          avg_latency_ms: 123,
          total_input_tokens: 1500,
          total_output_tokens: 500,
          total_tokens: 2000,
          by_provider: { openai: 7 },
          by_agent: { extraction: 5 },
          tokens_by_provider: { openai: { input_tokens: 1000, output_tokens: 300, total_tokens: 1300 } },
          tokens_by_agent: { extraction: { input_tokens: 900, output_tokens: 250, total_tokens: 1150 } },
          by_error: { rate_limit: 1 },
        });
      }
      return jsonResponse({ metrics: [{
        metric_id: "m1",
        claim_id: "CLM-1",
        agent_name: "extractor",
        stage_name: "Extraction",
        provider: "openai",
        model: "gpt",
        is_fallback: false,
        primary_error: null,
        latency_ms: 123,
        status: "SUCCESS",
        error_category: null,
        input_tokens: 100,
        output_tokens: 40,
        total_tokens: 140,
        created_at: "2026-06-16T09:00:00Z",
      }] });
    });
  });

  it("renders summary charts and recent metrics", async () => {
    render(<LLMMetricsPage />);

    expect(await screen.findByText("80%")).toBeInTheDocument();
    expect(screen.getByText("openai:gpt")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    await waitFor(() => expect((global.fetch as unknown as FetchMock).mock.calls.length).toBeGreaterThan(2));
  });
});

describe("test suite page", () => {
  const suiteCase = {
    case_id: "CASE-1",
    case_name: "Dental approval",
    description: "Clean dental bill",
    member_id: "EMP001",
    claim_category: "DENTAL",
    claimed_amount: 1000,
    expected_decision: "APPROVED",
    expected_approved_amount: 900,
    documents: ["bill.pdf"],
    test_context: {},
    api_mode_note: "ok",
  };

  beforeEach(() => {
    mockFetch((url: string, init?: RequestInit) => {
      if (String(url).endsWith("/api/claims/test-suite")) return jsonResponse({ cases: [suiteCase] });
      if (init?.method === "POST") return jsonResponse({ claim_id: "CLM-TS", status: "PROCESSING" });
      return jsonResponse({ claim_id: "CLM-TS", status: "DECIDED", decision: { decision: "APPROVED" }, gating_error: null });
    });
  });

  it("loads assignment cases and runs one through completion", async () => {
    render(<TestSuitePage />);

    expect(await screen.findByText("Dental approval")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^run$/i }));

    await waitFor(() => expect(screen.getByText("CLM-TS")).toBeInTheDocument());
    expect(screen.getByText(/Actual APPROVED/i)).toBeInTheDocument();
    fireEvent.keyDown(screen.getByText("CLM-TS").closest('[role="link"]') as HTMLElement, { key: "Enter" });
    expect(global.__mockRouter.push).toHaveBeenCalledWith("/claims/CLM-TS");
  });

  it("restores persisted run states", async () => {
    window.localStorage.setItem("plum.claims.testSuite.runStates.v1", JSON.stringify({
      "CASE-1": { claimId: "CLM-CACHED", status: "complete", decision: "APPROVED", expectedDecision: "APPROVED" },
    }));

    render(<TestSuitePage />);

    expect(await screen.findByText("CLM-CACHED")).toBeInTheDocument();
  });
});
