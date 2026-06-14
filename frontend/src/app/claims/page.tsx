"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowLeft, ChevronLeft, ChevronRight, Filter, Search } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

const STATUSES = ["", "PENDING", "PROCESSING", "DECIDED", "MANUAL_REVIEW", "GATING_FAILED"];

const MONTHS = [
  ["", "All months"],
  ["1", "January"],
  ["2", "February"],
  ["3", "March"],
  ["4", "April"],
  ["5", "May"],
  ["6", "June"],
  ["7", "July"],
  ["8", "August"],
  ["9", "September"],
  ["10", "October"],
  ["11", "November"],
  ["12", "December"],
];

type ClaimSummary = {
  claim_id: string;
  member_id: string;
  claim_category: string;
  claimed_amount: string;
  status: string;
  current_stage: string | null;
  updated_at: string;
  created_at: string;
  decision: string | null;
  approved_amount: string | null;
  confidence_score: number | null;
};

type ClaimsResponse = {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  claims: ClaimSummary[];
};

export default function ClaimsHistoryPage() {
  const currentYear = new Date().getFullYear();
  const [claims, setClaims] = useState<ClaimSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [date, setDate] = useState("");
  const [month, setMonth] = useState("");
  const [year, setYear] = useState(String(currentYear));

  const query = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: "10" });
    if (status) params.set("status", status);
    if (date) params.set("date", date);
    if (!date && month) params.set("month", month);
    if (!date && year) params.set("year", year);
    return params.toString();
  }, [page, status, date, month, year]);

  useEffect(() => {
    const fetchClaims = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/claims/?${query}`);
        if (!response.ok) {
          setClaims([]);
          return;
        }
        const payload: ClaimsResponse = await response.json();
        setClaims(payload.claims ?? []);
        setTotalPages(payload.total_pages ?? 1);
        setTotal(payload.total ?? 0);
      } catch {
        setClaims([]);
      } finally {
        setLoading(false);
      }
    };
    fetchClaims();
  }, [query]);

  const resetFilters = () => {
    setStatus("");
    setDate("");
    setMonth("");
    setYear(String(currentYear));
    setPage(1);
  };

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
                <p className="text-xs font-black uppercase tracking-[0.24em] text-muted">Plum Claims</p>
                <h1 className="text-xl font-black tracking-tight sm:text-2xl">Claims History</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggle />
              <Link href="/" className="secondary-button">
                <ArrowLeft className="h-4 w-4" /> Dashboard
              </Link>
              <Link href="/submit" className="primary-button">New Claim</Link>
            </div>
          </div>
        </header>

        <section className="glass-panel rounded-[24px] p-5">
          <div className="mb-4 flex items-center gap-2">
            <Filter className="h-4 w-4 text-[var(--brand-strong)]" />
            <h2 className="text-lg font-black">Filters</h2>
          </div>
          <div className="grid gap-3 md:grid-cols-5">
            <label className="space-y-2">
              <span className="text-sm font-bold">Status</span>
              <select className="input-surface" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
                {STATUSES.map((value) => <option key={value} value={value}>{value ? value.replace("_", " ") : "All statuses"}</option>)}
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-bold">Exact date</span>
              <input className="input-surface" type="date" value={date} onChange={(event) => { setDate(event.target.value); setPage(1); }} />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-bold">Month</span>
              <select className="input-surface" value={month} disabled={Boolean(date)} onChange={(event) => { setMonth(event.target.value); setPage(1); }}>
                {MONTHS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-bold">Year</span>
              <input className="input-surface" type="number" min="2000" max="2100" value={year} disabled={Boolean(date)} onChange={(event) => { setYear(event.target.value); setPage(1); }} />
            </label>
            <div className="flex items-end gap-2">
              <button type="button" className="secondary-button w-full" onClick={resetFilters}>
                Reset
              </button>
            </div>
          </div>
        </section>

        <section className="glass-panel rounded-[24px] p-5">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-lg font-black">All Claims</h2>
              <p className="text-sm text-muted">{total} claim{total === 1 ? "" : "s"} found</p>
            </div>
            <span className="status-pill"><Search className="h-3.5 w-3.5" /> Page {page} of {totalPages}</span>
          </div>

          <div className="overflow-hidden rounded-2xl border hairline">
            <div className="hidden grid-cols-[1.3fr_0.8fr_0.9fr_0.8fr_0.8fr_0.7fr] gap-3 bg-[var(--surface-muted)] px-4 py-3 text-xs font-black uppercase tracking-[0.12em] text-muted md:grid">
              <div>Claim</div>
              <div>Member</div>
              <div>Category</div>
              <div>Amount</div>
              <div>Status</div>
              <div>Updated</div>
            </div>

            {loading && <div className="p-5 text-sm text-muted">Loading claims...</div>}
            {!loading && claims.length === 0 && <div className="p-5 text-sm text-muted">No claims match the selected filters.</div>}
            {!loading && claims.map((claim) => (
              <Link key={claim.claim_id} href={`/claims/${claim.claim_id}`} className="grid gap-3 border-t hairline px-4 py-4 transition hover:bg-[var(--surface-muted)] md:grid-cols-[1.3fr_0.8fr_0.9fr_0.8fr_0.8fr_0.7fr] md:items-center">
                <div>
                  <div className="font-black">{claim.claim_id}</div>
                  {claim.decision && <div className="text-xs text-muted">{claim.decision} · Approved ₹{claim.approved_amount ?? "0"}</div>}
                </div>
                <div className="text-sm font-bold">{claim.member_id}</div>
                <div className="text-sm text-muted">{claim.claim_category.replace("_", " ")}</div>
                <div className="text-sm font-bold">₹{claim.claimed_amount}</div>
                <div><span className={`status-pill ${statusTone(claim.status)}`}>{claim.status.replace("_", " ")}</span></div>
                <div className="text-xs text-muted">{new Date(claim.updated_at).toLocaleDateString()}</div>
              </Link>
            ))}
          </div>

          <div className="mt-5 flex items-center justify-between gap-3">
            <button className="secondary-button" type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(value - 1, 1))}>
              <ChevronLeft className="h-4 w-4" /> Previous
            </button>
            <button className="secondary-button" type="button" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(value + 1, totalPages))}>
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
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
