"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Activity, ArrowLeft, BarChart3, Clock, Cpu, Gauge, RefreshCw } from "lucide-react";
import ThemeToggle from "@/components/ThemeToggle";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type MetricsSummary = {
  total_calls: number;
  successful_calls: number;
  failed_calls: number;
  fallback_calls: number;
  success_rate: number;
  fallback_rate: number;
  avg_latency_ms: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  by_provider: Record<string, number>;
  by_agent: Record<string, number>;
  tokens_by_provider: Record<string, TokenBreakdown>;
  tokens_by_agent: Record<string, TokenBreakdown>;
  by_error: Record<string, number>;
};

type TokenBreakdown = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
};

type LLMMetric = {
  metric_id: string;
  claim_id: string | null;
  agent_name: string;
  stage_name?: string | null;
  provider: string;
  model: string;
  is_fallback: boolean;
  primary_error: string | null;
  latency_ms: number | null;
  status: string;
  error_category: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  created_at: string;
};

const emptySummary: MetricsSummary = {
  total_calls: 0,
  successful_calls: 0,
  failed_calls: 0,
  fallback_calls: 0,
  success_rate: 0,
  fallback_rate: 0,
  avg_latency_ms: 0,
  total_input_tokens: 0,
  total_output_tokens: 0,
  total_tokens: 0,
  by_provider: {},
  by_agent: {},
  tokens_by_provider: {},
  tokens_by_agent: {},
  by_error: {},
};

export default function LLMMetricsPage() {
  const [summary, setSummary] = useState<MetricsSummary>(emptySummary);
  const [metrics, setMetrics] = useState<LLMMetric[]>([]);
  const [loading, setLoading] = useState(true);

  const loadMetrics = async () => {
    setLoading(true);
    try {
      const [summaryResponse, recentResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/claims/llm-metrics/summary`),
        fetch(`${API_BASE_URL}/api/claims/llm-metrics/recent?limit=30`),
      ]);
      if (summaryResponse.ok) {
        setSummary(await summaryResponse.json());
      }
      if (recentResponse.ok) {
        const payload = await recentResponse.json();
        setMetrics(payload.metrics ?? []);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMetrics();
  }, []);

  const maxProvider = useMemo(() => Math.max(1, ...Object.values(summary.by_provider)), [summary.by_provider]);
  const maxStage = useMemo(() => Math.max(1, ...Object.values(summary.by_agent)), [summary.by_agent]);
  const totalTokenDenominator = Math.max(summary.total_tokens, 1);

  return (
    <main className="app-shell">
      <div className="app-frame space-y-5">
        <header className="glass-panel rounded-[24px] px-5 py-4">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <span className="brand-mark"><Activity className="h-5 w-5" /></span>
              <div>
                <p className="text-xs font-black uppercase tracking-[0.24em] text-muted">Plum Claims</p>
                <h1 className="text-xl font-black tracking-tight sm:text-2xl">LLM Metrics</h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggle />
              <button type="button" className="secondary-button" onClick={loadMetrics}>
                <RefreshCw className="h-4 w-4" /> Refresh
              </button>
              <Link href="/" className="secondary-button"><ArrowLeft className="h-4 w-4" /> Dashboard</Link>
            </div>
          </div>
        </header>

        <section className="grid gap-4 md:grid-cols-4">
          <MetricCard icon={Cpu} label="Total Calls" value={summary.total_calls.toString()} note={`${summary.successful_calls} successful`} />
          <MetricCard icon={Gauge} label="Success Rate" value={`${Math.round(summary.success_rate * 100)}%`} note={`${summary.failed_calls} failed`} />
          <MetricCard icon={BarChart3} label="Input Tokens" value={formatTokens(summary.total_input_tokens)} note={`${Math.round((summary.total_input_tokens / totalTokenDenominator) * 100)}% of total`} />
          <MetricCard icon={BarChart3} label="Output Tokens" value={formatTokens(summary.total_output_tokens)} note={`${Math.round((summary.total_output_tokens / totalTokenDenominator) * 100)}% of total`} />
          <MetricCard icon={Clock} label="Avg Latency" value={`${summary.avg_latency_ms}ms`} note="successful calls only" />
          <MetricCard icon={Gauge} label="Fallback Rate" value={`${Math.round(summary.fallback_rate * 100)}%`} note={`${summary.fallback_calls} fallback calls`} />
        </section>

        <section className="grid gap-5 lg:grid-cols-2">
          <ChartCard title="Calls by Provider" data={summary.by_provider} max={maxProvider} />
          <ChartCard title="Calls by Stage" data={summary.by_agent} max={maxStage} />
        </section>

        <section className="grid gap-5 lg:grid-cols-2">
          <TokenChartCard title="Tokens by Provider" data={summary.tokens_by_provider} />
          <TokenChartCard title="Tokens by Stage" data={summary.tokens_by_agent} />
        </section>

        <section className="glass-panel rounded-[24px] p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-black">Recent LLM Calls</h2>
              <p className="text-sm text-muted">Latest provider calls recorded by the backend platform layer</p>
            </div>
            {loading && <span className="status-pill">Loading</span>}
          </div>
          <div className="overflow-hidden rounded-2xl border hairline">
            <div className="hidden grid-cols-[1fr_0.8fr_0.9fr_0.7fr_0.7fr_0.7fr_0.7fr] gap-3 bg-[var(--surface-muted)] px-4 py-3 text-xs font-black uppercase tracking-[0.12em] text-muted md:grid">
              <div>Claim</div>
              <div>Stage</div>
              <div>Provider</div>
              <div>Status</div>
              <div>Input</div>
              <div>Output</div>
              <div>Latency</div>
            </div>
            {metrics.length === 0 && !loading && <div className="p-5 text-sm text-muted">No LLM metrics recorded yet.</div>}
            {metrics.map((metric) => (
              <div key={metric.metric_id} className="grid gap-3 border-t hairline px-4 py-4 md:grid-cols-[1fr_0.8fr_0.9fr_0.7fr_0.7fr_0.7fr_0.7fr] md:items-center">
                <div className="min-w-0 text-sm font-bold">{metric.claim_id ?? "-"}</div>
                <div className="text-sm text-muted">{metric.stage_name ?? metric.agent_name}</div>
                <div className="text-sm text-muted">{metric.provider}:{metric.model}</div>
                <div><span className={`status-pill ${metric.status === "SUCCESS" ? "text-[var(--success)]" : "text-[var(--danger)]"}`}>{metric.status}</span></div>
                <div className="text-sm text-muted">{formatTokens(metric.input_tokens)}</div>
                <div className="text-sm text-muted">{formatTokens(metric.output_tokens)}</div>
                <div className="text-sm text-muted">{metric.latency_ms ?? "-"}ms</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

function formatTokens(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value ?? 0);
}

function MetricCard({ icon: Icon, label, value, note }: { icon: typeof Cpu; label: string; value: string; note: string }) {
  return (
    <div className="glass-card rounded-2xl p-4">
      <Icon className="mb-3 h-5 w-5 text-[var(--brand-strong)]" />
      <div className="text-2xl font-black">{value}</div>
      <div className="mt-1 text-sm font-bold">{label}</div>
      <div className="mt-1 text-xs text-muted">{note}</div>
    </div>
  );
}

function ChartCard({ title, data, max }: { title: string; data: Record<string, number>; max: number }) {
  const entries = Object.entries(data);
  return (
    <div className="glass-panel rounded-[24px] p-5">
      <h2 className="mb-4 text-lg font-black">{title}</h2>
      {entries.length === 0 && <div className="text-sm text-muted">No data yet.</div>}
      <div className="space-y-3">
        {entries.map(([label, value]) => (
          <div key={label}>
            <div className="mb-1 flex justify-between text-sm">
              <span className="font-bold">{label}</span>
              <span className="text-muted">{value}</span>
            </div>
            <div className="h-3 overflow-hidden rounded-full bg-[var(--surface-muted)]">
              <div className="h-full rounded-full bg-[var(--brand)]" style={{ width: `${Math.max((value / max) * 100, 4)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TokenChartCard({ title, data }: { title: string; data: Record<string, TokenBreakdown> }) {
  const entries = Object.entries(data);
  const max = Math.max(1, ...entries.map(([, value]) => value.total_tokens));
  return (
    <div className="glass-panel rounded-[24px] p-5">
      <h2 className="mb-4 text-lg font-black">{title}</h2>
      {entries.length === 0 && <div className="text-sm text-muted">No token data yet.</div>}
      <div className="space-y-4">
        {entries.map(([label, value]) => (
          <div key={label}>
            <div className="mb-1 flex justify-between text-sm">
              <span className="font-bold">{label}</span>
              <span className="text-muted">{formatTokens(value.total_tokens)}</span>
            </div>
            <div className="flex h-3 overflow-hidden rounded-full bg-[var(--surface-muted)]">
              <div className="h-full bg-slate-400" style={{ width: `${Math.max((value.input_tokens / max) * 100, 2)}%` }} />
              <div className="h-full bg-[var(--brand)]" style={{ width: `${Math.max((value.output_tokens / max) * 100, 2)}%` }} />
            </div>
            <div className="mt-1 flex gap-3 text-xs text-muted">
              <span>Input {formatTokens(value.input_tokens)}</span>
              <span>Output {formatTokens(value.output_tokens)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
