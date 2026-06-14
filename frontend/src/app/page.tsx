"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  FileSearch,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const metrics = [
  { label: "Claims Ready", value: "12", note: "assignment cases mapped" },
  { label: "Policy Rules", value: "14", note: "deterministic checks" },
  { label: "Trace Coverage", value: "100%", note: "agent spans visible" },
];

const workflow = [
  { icon: FileSearch, label: "Document gate", text: "Stops wrong, missing, unreadable, or mismatched uploads early." },
  { icon: Sparkles, label: "Vision extraction", text: "Reads messy bills, prescriptions, reports, and phone photos." },
  { icon: ShieldCheck, label: "Policy engine", text: "Runs deterministic checks from policy_terms.json." },
  { icon: ClipboardCheck, label: "Decision trace", text: "Shows what passed, failed, skipped, and why." },
];

type ClaimSummary = {
  claim_id: string;
  member_id: string;
  claim_category: string;
  claimed_amount: string;
  status: string;
  updated_at: string;
  decision: string | null;
  approved_amount: string | null;
  confidence_score: number | null;
};

export default function Home() {
  const [claims, setClaims] = useState<ClaimSummary[]>([]);
  const [loadingClaims, setLoadingClaims] = useState(true);

  useEffect(() => {
    const fetchClaims = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/claims/`);
        if (!response.ok) {
          setClaims([]);
          return;
        }
        const payload = await response.json();
        setClaims(payload.claims ?? []);
      } catch {
        setClaims([]);
      } finally {
        setLoadingClaims(false);
      }
    };
    fetchClaims();
  }, []);

  return (
    <main className="app-shell">
      <div className="app-frame space-y-5">
        <header className="glass-panel rounded-[24px] px-5 py-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <span className="brand-mark">
                <Activity className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.24em] text-muted">Plum Health</p>
                <h1 className="text-xl font-black tracking-tight sm:text-2xl">Claims Processing System</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="status-pill">
                <CheckCircle2 className="h-3.5 w-3.5" /> Local Demo
              </span>
              <ThemeToggle />
              <Link href="/submit" className="primary-button">
                New Claim <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </header>

        <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="glass-panel rounded-[28px] p-5 sm:p-6">
            <div className="mb-6 max-w-2xl">
              <p className="status-pill mb-4 w-fit">
                <ShieldCheck className="h-3.5 w-3.5" /> AI-assisted OPD adjudication
              </p>
              <h2 className="text-3xl font-black leading-tight tracking-tight sm:text-4xl">
                Review health insurance claims with document intelligence and auditable policy checks.
              </h2>
              <p className="mt-4 max-w-xl text-sm leading-6 text-muted sm:text-base">
                Submit documents, catch upload issues before processing, extract structured medical fields, and inspect the complete trace behind every decision.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {metrics.map((metric) => (
                <div key={metric.label} className="muted-panel rounded-2xl p-4">
                  <div className="text-2xl font-black">{metric.value}</div>
                  <div className="mt-1 text-sm font-bold">{metric.label}</div>
                  <div className="mt-1 text-xs text-muted">{metric.note}</div>
                </div>
              ))}
            </div>
          </div>

          <aside className="glass-card rounded-[28px] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-black">Claim Worklist</h3>
                <p className="text-sm text-muted">Previous submitted claims</p>
              </div>
              <TriangleAlert className="h-5 w-5 text-[var(--accent)]" />
            </div>
            <div className="space-y-3">
              {loadingClaims && <div className="muted-panel rounded-2xl p-3 text-sm text-muted">Loading claims...</div>}
              {!loadingClaims && claims.length === 0 && (
                <div className="muted-panel rounded-2xl p-3 text-sm text-muted">
                  No claims submitted yet. Create one to see it here.
                </div>
              )}
              {!loadingClaims && claims.slice(0, 6).map((claim) => (
                <Link key={claim.claim_id} href={`/claims/${claim.claim_id}`} className="muted-panel block rounded-2xl p-3 transition hover:border-[var(--border-strong)] hover:bg-[var(--surface-strong)]">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-black">{claim.claim_id}</div>
                      <div className="text-xs text-muted">{claim.member_id} · {claim.claim_category.replace("_", " ")} · ₹{claim.claimed_amount}</div>
                    </div>
                    <span className={`status-pill ${statusTone(claim.status)}`}>
                      {claim.status.replace("_", " ")}
                    </span>
                  </div>
                  {claim.decision && (
                    <div className="mt-2 text-xs text-muted">
                      {claim.decision} · Approved ₹{claim.approved_amount ?? "0"}
                    </div>
                  )}
                </Link>
              ))}
            </div>
            <Link href="/submit" className="secondary-button mt-5 w-full">
              Submit New Claim
            </Link>
            <Link href="/claims" className="secondary-button mt-3 w-full">
              View All Claims
            </Link>
          </aside>
        </section>

        <section className="grid gap-4 md:grid-cols-4">
          {workflow.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.label} className="glass-card rounded-2xl p-4">
                <Icon className="mb-3 h-5 w-5 text-[var(--brand-strong)]" />
                <h3 className="text-sm font-black">{item.label}</h3>
                <p className="mt-2 text-xs leading-5 text-muted">{item.text}</p>
              </div>
            );
          })}
        </section>
      </div>
    </main>
  );
}

function statusTone(status: string) {
  if (status === "DECIDED") return "text-[var(--success)]";
  if (status === "PROCESSING" || status === "PENDING") return "text-[var(--brand-strong)]";
  if (status === "MANUAL_REVIEW") return "text-[var(--warning)]";
  return "text-[var(--danger)]";
}
