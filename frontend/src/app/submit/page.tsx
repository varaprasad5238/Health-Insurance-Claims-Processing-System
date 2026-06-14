"use client";
import React, { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Activity, ArrowLeft, FileUp, Loader2, ShieldCheck } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const members = [
  ["EMP001", "Rajesh Kumar"],
  ["EMP002", "Priya Singh"],
  ["EMP003", "Amit Verma"],
  ["EMP004", "Sneha Reddy"],
  ["EMP005", "Vikram Joshi"],
  ["EMP006", "Kavita Nair"],
  ["EMP007", "Suresh Patil"],
  ["EMP008", "Ravi Menon"],
  ["EMP009", "Anita Desai"],
  ["EMP010", "Deepak Shah"],
];

const categories = [
  "CONSULTATION",
  "DIAGNOSTIC",
  "PHARMACY",
  "DENTAL",
  "VISION",
  "ALTERNATIVE_MEDICINE",
];

export default function SubmitClaim() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);

    const formData = new FormData(e.currentTarget);
    try {
      const res = await fetch("http://localhost:8000/api/claims/", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (data.claim_id) {
        router.push(`/claims/${data.claim_id}`);
      } else {
        alert("Submission failed.");
        setLoading(false);
      }
    } catch (err) {
      console.error(err);
      alert("Error submitting claim.");
      setLoading(false);
    }
  };

  return (
    <main className="app-shell">
      <div className="app-frame max-w-4xl space-y-5">
        <header className="glass-panel rounded-[24px] px-5 py-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <span className="brand-mark">
                <Activity className="h-5 w-5" />
              </span>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.22em] text-muted">Plum Claims</p>
                <h1 className="text-2xl font-black tracking-tight">Submit OPD Claim</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggle />
              <Link href="/" className="secondary-button w-fit">
                <ArrowLeft className="h-4 w-4" /> Dashboard
              </Link>
            </div>
          </div>
        </header>

        <section className="grid gap-5 lg:grid-cols-[0.72fr_0.28fr]">
          <form onSubmit={handleSubmit} className="glass-panel rounded-[28px] p-5 sm:p-6">
            <div className="mb-5 flex items-center gap-2 text-sm font-bold text-[var(--brand-strong)]">
              <ShieldCheck className="h-4 w-4" /> Documents are gated before claim decisioning
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-bold">Member</span>
                <select name="member_id" className="input-surface">
                  {members.map(([id, name]) => (
                    <option key={id} value={id}>{name} ({id})</option>
                  ))}
                </select>
              </label>

              <label className="space-y-2">
                <span className="text-sm font-bold">Claim Category</span>
                <select name="claim_category" className="input-surface">
                  {categories.map((category) => (
                    <option key={category} value={category}>{category.replace("_", " ")}</option>
                  ))}
                </select>
              </label>

              <label className="space-y-2">
                <span className="text-sm font-bold">Treatment Date</span>
                <input type="date" name="treatment_date" required className="input-surface" />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-bold">Claimed Amount</span>
                <input type="number" step="0.01" name="claimed_amount" required placeholder="1500.00" className="input-surface" />
              </label>
            </div>

            <label className="mt-4 block space-y-2">
              <span className="text-sm font-bold">Upload Documents</span>
              <div className="muted-panel rounded-2xl p-4">
                <div className="mb-3 flex items-center gap-3 text-sm text-muted">
                  <FileUp className="h-5 w-5 text-[var(--brand-strong)]" />
                  Upload prescriptions, bills, reports, or PDFs for document gating and extraction.
                </div>
                <input
                  type="file"
                  name="documents"
                  multiple
                  required
                  accept="image/*,application/pdf"
                  className="block w-full text-sm text-muted file:mr-4 file:rounded-xl file:border-0 file:bg-[var(--brand-soft)] file:px-4 file:py-2 file:text-sm file:font-black file:text-[var(--brand-strong)] hover:file:brightness-95"
                />
              </div>
            </label>

            <button type="submit" disabled={loading} className="primary-button mt-5 w-full">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />}
              {loading ? "Submitting Claim" : "Submit Claim"}
            </button>
          </form>

          <aside className="glass-card rounded-[28px] p-5">
            <h2 className="text-lg font-black">Document Checklist</h2>
            <div className="mt-4 space-y-3 text-sm">
              <div className="muted-panel rounded-2xl p-3">
                <div className="font-black">Consultation</div>
                <div className="text-xs text-muted">Prescription + hospital bill</div>
              </div>
              <div className="muted-panel rounded-2xl p-3">
                <div className="font-black">Diagnostic</div>
                <div className="text-xs text-muted">Prescription + lab report + bill</div>
              </div>
              <div className="muted-panel rounded-2xl p-3">
                <div className="font-black">Pharmacy</div>
                <div className="text-xs text-muted">Prescription + pharmacy bill</div>
              </div>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
