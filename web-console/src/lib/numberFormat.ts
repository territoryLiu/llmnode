function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function formatWithGrouping(value: number) {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatGroupedNumber(value: number | null | undefined, fallback = '-') {
  if (!isFiniteNumber(value)) {
    return fallback;
  }
  return formatWithGrouping(value);
}

export function formatCompactNumber(value: number | null | undefined, fallback = '-') {
  if (!isFiniteNumber(value)) {
    return fallback;
  }
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  return formatWithGrouping(value);
}
