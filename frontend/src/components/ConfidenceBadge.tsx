import React from 'react';

export default function ConfidenceBadge({ score }: { score: number }) {
  const color = score > 0.85 ? 'text-[var(--success)]' : 
                score > 0.65 ? 'text-[var(--warning)]' : 'text-[var(--danger)]';
  return (
    <span className={`status-pill ${color}`}>
      Confidence: {Math.round(score * 100)}%
    </span>
  );
}
