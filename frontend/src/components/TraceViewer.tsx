import React from 'react';

export default function TraceViewer({ traceId }: { traceId: string }) {
  return (
    <div className="glass-card mt-4 rounded-2xl p-4">
      <h3 className="text-lg font-black">Trace Viewer</h3>
      <p className="text-sm text-muted">Trace ID: {traceId}</p>
      <ul className="mt-3 space-y-1 font-mono text-sm text-muted">
        <li>[SUCCESS] Document Gating - 150ms</li>
        <li>[SUCCESS] Entity Extraction - 420ms</li>
        <li>[SUCCESS] Amount Reconciler - 20ms</li>
        <li>[SUCCESS] Policy Engine - 10ms</li>
      </ul>
    </div>
  );
}
