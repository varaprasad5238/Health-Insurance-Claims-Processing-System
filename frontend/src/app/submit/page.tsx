"use client";
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Activity, ArrowLeft, FileUp, Loader2, ShieldCheck, X } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const MIN_CLAIM_AMOUNT = 500;
const MAX_CLAIM_AMOUNT = 50000;
const MAX_DOCUMENTS = 4;
const MAX_FILE_SIZE_MB = 3;
const MAX_TOTAL_UPLOAD_SIZE_MB = 8;
const BYTES_PER_MB = 1024 * 1024;

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
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [networkHospitals, setNetworkHospitals] = useState<string[]>([]);
  const [fileMessage, setFileMessage] = useState<string>("");

  useEffect(() => {
    const loadPolicyOptions = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/claims/policy-options`);
        if (!response.ok) return;
        const payload = await response.json();
        setNetworkHospitals(payload.network_hospitals ?? []);
      } catch {
        setNetworkHospitals([]);
      }
    };
    loadPolicyOptions();
  }, []);

  const addFiles = (files: FileList | null) => {
    if (!files) {
      return;
    }

    const nextFiles = [...selectedFiles];
    const messages: string[] = [];
    let addedCount = 0;

    for (const file of Array.from(files)) {
      if (file.size > MAX_FILE_SIZE_MB * BYTES_PER_MB) {
        messages.push(`${file.name} was skipped because it is ${formatFileSize(file.size)}. Max per file is ${MAX_FILE_SIZE_MB} MB.`);
        continue;
      }

      if (nextFiles.length >= MAX_DOCUMENTS) {
        messages.push(`Only ${MAX_DOCUMENTS} files can be uploaded per claim.`);
        break;
      }

      const alreadySelected = nextFiles.some(
        (existingFile) =>
          existingFile.name === file.name &&
          existingFile.size === file.size &&
          existingFile.lastModified === file.lastModified,
      );

      if (alreadySelected) {
        messages.push(`${file.name} is already selected.`);
        continue;
      }

      const nextTotalSize = nextFiles.reduce((total, selectedFile) => total + selectedFile.size, 0) + file.size;
      if (nextTotalSize > MAX_TOTAL_UPLOAD_SIZE_MB * BYTES_PER_MB) {
        messages.push(`Total upload size would exceed ${MAX_TOTAL_UPLOAD_SIZE_MB} MB. ${file.name} was not added.`);
        break;
      }

      nextFiles.push(file);
      addedCount += 1;
    }

    if (addedCount > 0) {
      messages.unshift(`${addedCount} file${addedCount === 1 ? "" : "s"} added.`);
    }
    if (messages.length === 0) {
      messages.push("No new files were added. Please choose PDF, PNG, JPG, JPEG, WEBP, or GIF files within the size limits.");
    }

    setSelectedFiles(nextFiles);
    setFileMessage(messages.join(" "));
  };

  const removeFile = (fileToRemove: File) => {
    setSelectedFiles((currentFiles) => currentFiles.filter((file) => file !== fileToRemove));
    setFileMessage(`${fileToRemove.name} removed.`);
  };

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (selectedFiles.length === 0) {
      alert("Please upload at least one claim document.");
      return;
    }
    if (selectedFiles.length > MAX_DOCUMENTS) {
      alert(`You can upload a maximum of ${MAX_DOCUMENTS} documents per claim.`);
      return;
    }
    if (selectedFiles.some((file) => file.size > MAX_FILE_SIZE_MB * BYTES_PER_MB)) {
      alert(`Each file must be ${MAX_FILE_SIZE_MB} MB or smaller.`);
      return;
    }
    const totalUploadSize = selectedFiles.reduce((total, file) => total + file.size, 0);
    if (totalUploadSize > MAX_TOTAL_UPLOAD_SIZE_MB * BYTES_PER_MB) {
      alert(`Total upload size cannot exceed ${MAX_TOTAL_UPLOAD_SIZE_MB} MB.`);
      return;
    }

    const formData = new FormData(e.currentTarget);
    const claimedAmount = Number(formData.get("claimed_amount"));
    if (!Number.isFinite(claimedAmount) || claimedAmount < MIN_CLAIM_AMOUNT || claimedAmount > MAX_CLAIM_AMOUNT) {
      alert(`Claimed amount must be between ₹${MIN_CLAIM_AMOUNT} and ₹${MAX_CLAIM_AMOUNT}.`);
      return;
    }

    setLoading(true);

    formData.delete("documents");
    selectedFiles.forEach((file) => formData.append("documents", file));
    try {
      const res = await fetch(`${API_BASE_URL}/api/claims/`, {
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
                <input type="number" min={MIN_CLAIM_AMOUNT} max={MAX_CLAIM_AMOUNT} step="0.01" name="claimed_amount" required placeholder="1500.00" className="input-surface" />
                <span className="block text-xs text-muted">Allowed range: ₹{MIN_CLAIM_AMOUNT} to ₹{MAX_CLAIM_AMOUNT}</span>
              </label>

              <label className="space-y-2">
                <span className="text-sm font-bold">YTD Claims Amount</span>
                <input type="number" min="0" step="0.01" name="ytd_claims_amount" placeholder="Optional" className="input-surface" />
                <span className="block text-xs text-muted">Optional current-year claimed amount</span>
              </label>

              <label className="space-y-2">
                <span className="text-sm font-bold">Hospital</span>
                <select name="hospital_name" className="input-surface" defaultValue="">
                  <option value="">Not selected / non-network</option>
                  {networkHospitals.map((hospital) => (
                    <option key={hospital} value={hospital}>{hospital}</option>
                  ))}
                </select>
                <span className="block text-xs text-muted">Optional network hospital selection</span>
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
                  accept="image/*,application/pdf"
                  onChange={(event) => {
                    addFiles(event.currentTarget.files);
                    event.currentTarget.value = "";
                  }}
                  className="block w-full text-sm text-muted file:mr-4 file:rounded-xl file:border-0 file:bg-[var(--brand-soft)] file:px-4 file:py-2 file:text-sm file:font-black file:text-[var(--brand-strong)] hover:file:brightness-95"
                />
                <p className="mt-3 text-xs text-muted">
                  You can select multiple files at once or add them one by one. Maximum {MAX_DOCUMENTS} files, {MAX_FILE_SIZE_MB} MB per file, {MAX_TOTAL_UPLOAD_SIZE_MB} MB total. A single PDF can contain all claim documents.
                </p>
                {fileMessage && (
                  <div className="mt-3 rounded-xl border border-[var(--border)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-bold text-muted">
                    {fileMessage}
                  </div>
                )}
                <div className="mt-3 text-xs text-muted">
                  Current total: {formatFileSize(selectedFiles.reduce((total, file) => total + file.size, 0))} / {MAX_TOTAL_UPLOAD_SIZE_MB} MB
                </div>
                {selectedFiles.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <div className="text-xs font-black uppercase tracking-[0.18em] text-muted">
                      {selectedFiles.length} document{selectedFiles.length === 1 ? "" : "s"} selected
                    </div>
                    <div className="space-y-2">
                      {selectedFiles.map((file) => (
                        <div key={`${file.name}-${file.size}-${file.lastModified}`} className="flex items-center justify-between gap-3 rounded-xl bg-[var(--surface-strong)] px-3 py-2 text-sm">
                          <div className="min-w-0">
                            <div className="truncate font-bold">{file.name}</div>
                            <div className="text-xs text-muted">{Math.max(file.size / 1024, 1).toFixed(1)} KB</div>
                          </div>
                          <button
                            type="button"
                            onClick={() => removeFile(file)}
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-[var(--brand-soft)] hover:text-[var(--brand-strong)]"
                            aria-label={`Remove ${file.name}`}
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
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

function formatFileSize(bytes: number) {
  if (bytes >= BYTES_PER_MB) {
    return `${(bytes / BYTES_PER_MB).toFixed(2)} MB`;
  }
  return `${Math.max(bytes / 1024, 1).toFixed(1)} KB`;
}
