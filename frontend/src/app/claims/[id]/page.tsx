"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, ArrowLeft, CheckCircle, Loader2, CircleDashed, AlertTriangle, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

type Span = {
  span_id: string;
  agent_name: string;
  stage_order: number;
  status: string;
  elapsed_ms: number | null;
  started_at: string;
  ended_at: string | null;
  output_summary: any;
  confidence_delta: number | null;
  errors: string[];
  model_used: string;
};

type ClaimData = {
  claim_id: string;
  status: string;
  current_stage: string | null;
  updated_at: string;
  spans: Span[];
  decision: any;
  gating_error: any;
};

const STAGES = [
  { order: 1, label: "Vision read — document(s)" },
  { order: 2, label: "Document gating" },
  { order: 3, label: "Entity extraction" },
  { order: 4, label: "Amount reconciliation" },
  { order: 5, label: "Merging results" },
  { order: 6, label: "Policy rule evaluation" },
  { order: 7, label: "Decision synthesis" },
  { order: 8, label: "Final decision" },
];

export default function ClaimDetail({ params }: { params: { id: string } }) {
  const [data, setData] = useState<ClaimData | null>(null);
  const [polling, setPolling] = useState(true);

  useEffect(() => {
    let timeoutId: NodeJS.Timeout;

    const fetchData = async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/claims/${params.id}/status`);
        if (res.ok) {
          const json: ClaimData = await res.json();
          setData(json);

          if (["DECIDED", "MANUAL_REVIEW", "GATING_FAILED"].includes(json.status)) {
            setPolling(false);
          } else {
            timeoutId = setTimeout(fetchData, 1500);
          }
        } else {
          timeoutId = setTimeout(fetchData, 1500);
        }
      } catch (e) {
        console.error(e);
        timeoutId = setTimeout(fetchData, 1500);
      }
    };

    if (polling) {
      fetchData();
    }

    return () => clearTimeout(timeoutId);
  }, [params.id, polling]);

  if (!data) {
    return (
      <main className="app-shell">
        <div className="app-frame max-w-4xl">
          <div className="glass-panel rounded-[24px] p-6 text-muted">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" /> Loading claim...
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <div className="app-frame max-w-5xl space-y-5">
        <header className="glass-panel rounded-[24px] px-5 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="brand-mark">
                <Activity className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.22em] text-muted">Plum Claims</p>
                <h1 className="text-2xl font-black tracking-tight">Decision Review</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggle />
              <Link href="/submit" className="secondary-button w-fit">
                <ArrowLeft className="h-4 w-4" /> Submit Another
              </Link>
            </div>
          </div>
        </header>
        <HeaderCard data={data} />
        <PipelineCard data={data} />
        <DecisionCard data={data} />
      </div>
    </main>
  );
}

function HeaderCard({ data }: { data: ClaimData }) {
  const getBadgeColor = () => {
    switch (data.status) {
      case "PENDING": return "bg-gray-100 text-gray-800 border-gray-200";
      case "PROCESSING": return "bg-blue-100 text-blue-800 border-blue-200";
      case "DECIDED": return "bg-green-100 text-green-800 border-green-200";
      case "MANUAL_REVIEW": return "bg-yellow-100 text-yellow-800 border-yellow-200";
      case "GATING_FAILED": return "bg-red-100 text-red-800 border-red-200";
      default: return "bg-gray-100 text-gray-800 border-gray-200";
    }
  };

  return (
    <div className="glass-card rounded-[24px] p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
          <h2 className="text-2xl font-black tracking-tight">{data.claim_id}</h2>
          <p className="mt-1 text-sm text-muted">Status as of {new Date(data.updated_at).toLocaleTimeString()}</p>
      </div>
        <span className={`status-pill ${getBadgeColor()}`}>
        {data.status.replace("_", " ")}
      </span>
      </div>
    </div>
  );
}

function PipelineCard({ data }: { data: ClaimData }) {
  const rows: { label: string; span?: Span; isPending: boolean }[] = [];

  const stage1Spans = data.spans.filter((s) => s.stage_order === 1);
  if (stage1Spans.length > 0) {
    stage1Spans.forEach((span, i) => {
      rows.push({ label: `Vision read — document ${i + 1}`, span, isPending: false });
    });
  } else {
    rows.push({ label: STAGES[0].label, isPending: true });
  }

  for (let i = 2; i <= 8; i++) {
    const span = data.spans.find((s) => s.stage_order === i);
    rows.push({
      label: STAGES.find((s) => s.order === i)?.label || `Stage ${i}`,
      span,
      isPending: !span,
    });
  }

  const completed = data.spans.filter(s => s.status === 'SUCCESS' || s.status === 'SKIPPED').length;
  const total = rows.length;
  const progress = Math.min((completed / total) * 100, 100);

  return (
    <div className="glass-panel rounded-[24px] p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-black">Pipeline Progress</h2>
          <p className="text-sm text-muted">Trace spans emitted by each processing stage</p>
        </div>
        <span className="status-pill">{Math.round(progress)}%</span>
      </div>
      <div className="mb-6 h-2.5 w-full overflow-hidden rounded-full muted-panel">
        <div className="h-2.5 rounded-full bg-[var(--brand)] transition-all duration-500" style={{ width: `${progress}%` }}></div>
      </div>

      <div className="space-y-2">
        {rows.map((row, idx) => (
          <PipelineRow key={idx} label={row.label} span={row.span} isPending={row.isPending} />
        ))}
      </div>
    </div>
  );
}

function PipelineRow({ label, span, isPending }: { label: string; span?: Span; isPending: boolean }) {
  const [expanded, setExpanded] = useState(false);

  if (isPending || !span) {
    return (
      <div className="muted-panel flex items-center rounded-2xl p-3 opacity-60">
        <CircleDashed className="mr-3 h-5 w-5 text-muted" />
        <span className="flex-1 text-sm font-bold">{label}</span>
        <span className="text-xs font-bold text-muted">Waiting...</span>
      </div>
    );
  }

  const getIcon = () => {
    switch (span.status) {
      case "SUCCESS": return <CheckCircle className="w-5 h-5 text-[var(--success)] mr-3" />;
      case "RUNNING": return <Loader2 className="w-5 h-5 text-[var(--brand)] mr-3 animate-spin" />;
      case "SKIPPED": return <CircleDashed className="w-5 h-5 text-muted mr-3" />;
      case "TIMEOUT":
      case "ERROR": return <AlertTriangle className="w-5 h-5 text-[var(--danger)] mr-3" />;
      default: return <CircleDashed className="w-5 h-5 text-muted mr-3" />;
    }
  };

  const getSummaryLine = () => {
    if (span.status === "ERROR" || span.status === "TIMEOUT") return span.errors.join(", ");
    if (span.status === "SKIPPED") return span.errors[0] || "Skipped";
    if (!span.output_summary) return "";
    
    const s = span.output_summary;
    switch (span.agent_name) {
      case "gating": return `Required docs present · passed`;
      case "entity_extraction": return `${s.fields_extracted} fields extracted · confidence ${s.confidence}`;
      case "amount_reconciler": return `${s.discrepancies} discrepancy(ies) · ${s.fraud_indicators} fraud indicator(s)`;
      case "orchestrator": return `Merged confidence ${s.merged_confidence} · ${s.failed_agents?.length || 0} failed agent(s)`;
      case "policy_engine": return `${s.rules_evaluated} rules evaluated · ${s.rules_failed} failed · ${s.rules_skipped} skipped`;
      case "decision_synthesis": return `Decision: ${s.decision} · Approved ₹${s.approved_amount}`;
      case "final": return `Claim ${s.decision}`;
      default:
        if (span.agent_name.startsWith("vision_read_doc_")) {
          return `Type: ${s.document_type} · Readability ${s.readability} · ${s.quality_flags?.length || 0} quality flag(s)`;
        }
        return JSON.stringify(s);
    }
  };

  const isClickable = span.status !== "RUNNING";

  return (
    <div className={`overflow-hidden rounded-2xl border transition-colors ${span.status === "RUNNING" ? "border-[var(--brand)] bg-[var(--brand-soft)]" : "hairline bg-[var(--surface-strong)]"}`}>
      <div 
        className={`flex items-center p-3 ${isClickable ? "cursor-pointer hover:bg-[var(--surface-muted)]" : ""}`}
        onClick={() => isClickable && setExpanded(!expanded)}
      >
        {getIcon()}
        <div className="flex-1">
          <div className="text-sm font-black">{label}</div>
          <div className="truncate text-xs text-muted">{getSummaryLine()}</div>
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-muted">
            {span.status === "RUNNING" ? "running" : `${span.elapsed_ms}ms`}
          </span>
          {isClickable && (expanded ? <ChevronUp className="w-4 h-4 text-muted" /> : <ChevronDown className="w-4 h-4 text-muted" />)}
        </div>
      </div>
      
      {expanded && (
        <div className="border-t hairline bg-[var(--surface-muted)] p-4 text-sm">
          <div className="mb-3 grid gap-4 text-muted sm:grid-cols-2">
            <div><strong>Status:</strong> <span className="font-mono">{span.status}</span></div>
            {span.confidence_delta !== null && <div><strong>Confidence Delta:</strong> <span className="font-mono">{span.confidence_delta}</span></div>}
            <div><strong>Model Used:</strong> <span className="rounded bg-[var(--surface-strong)] px-1 py-0.5 font-mono">{span.model_used}</span></div>
          </div>
          {span.output_summary && (
            <div className="mt-2">
              <strong className="mb-1 block">Output Summary JSON:</strong>
              <pre className="overflow-x-auto rounded-xl bg-[#111816] p-3 font-mono text-xs text-[#eaf7f1] shadow-inner">
                {JSON.stringify(span.output_summary, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DecisionCard({ data }: { data: ClaimData }) {
  if (data.status === "GATING_FAILED" && data.gating_error) {
    return (
      <div className="glass-card rounded-[24px] border-[color:var(--danger)] p-6">
        <div className="flex items-center gap-3 mb-4">
          <XCircle className="w-6 h-6 text-[var(--danger)]" />
          <h2 className="text-xl font-black">Document Gating Failed</h2>
        </div>
        <p className="font-bold">{data.gating_error.human_message}</p>
        <p className="mt-2 text-sm text-muted">Please return to the submit page and upload the correct documents.</p>
        <Link href="/submit" className="primary-button mt-4 w-fit">Upload Again</Link>
      </div>
    );
  }

  if (["DECIDED", "MANUAL_REVIEW"].includes(data.status) && data.decision) {
    const d = data.decision;
    const badgeColor = d.decision === "APPROVED" ? "text-[var(--success)]" :
                       d.decision === "PARTIAL" ? "text-[var(--warning)]" :
                       d.decision === "MANUAL_REVIEW" ? "text-[var(--accent)]" : "text-[var(--danger)]";
    return (
      <div className="glass-panel rounded-[24px] p-6">
        <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="mb-2 text-xs font-black uppercase tracking-[0.22em] text-muted">Final Decision</h2>
            <span className={`status-pill ${badgeColor}`}>{d.decision}</span>
          </div>
          <div className="sm:text-right">
            <div className="text-4xl font-black tracking-tight">₹{d.approved_amount}</div>
            <div className="text-sm font-bold text-muted">Approved Amount</div>
          </div>
        </div>

        <div className="muted-panel mb-4 rounded-2xl p-3 font-mono text-sm text-muted">
          Claimed ₹1500 → Copay −₹{d.copay_deducted} → Discount −₹{d.network_discount_applied} → Approved ₹{d.approved_amount}
        </div>

        <p className="mb-6 text-lg font-bold leading-7">{d.member_message}</p>

        <details className="muted-panel rounded-2xl text-sm text-muted">
          <summary className="cursor-pointer p-3 font-black transition hover:bg-[var(--surface-strong)]">Ops Details & Confidence</summary>
          <div className="space-y-3 border-t hairline p-4">
            <p><strong>Confidence Score:</strong> <span className="rounded bg-[var(--surface-strong)] px-1 font-mono">{d.confidence_score}</span></p>
            <p><strong>Ops Summary:</strong> {d.ops_summary}</p>
            {d.manual_review_note && <p><strong>Review Note:</strong> {d.manual_review_note}</p>}
          </div>
        </details>
      </div>
    );
  }

  return null;
}
