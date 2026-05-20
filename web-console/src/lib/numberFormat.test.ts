import {describe, expect, it} from 'vitest';

import {formatCompactNumber, formatGroupedNumber} from './numberFormat';

describe('number formatting', () => {
  it('adds grouping separators for values below one million', () => {
    expect(formatCompactNumber(12345)).toBe('12,345');
    expect(formatGroupedNumber(987654)).toBe('987,654');
  });

  it('formats millions with two decimals and M suffix', () => {
    expect(formatCompactNumber(12345678)).toBe('12.35M');
    expect(formatCompactNumber(1000000)).toBe('1.00M');
  });

  it('formats billions with two decimals and B suffix', () => {
    expect(formatCompactNumber(3456789123)).toBe('3.46B');
    expect(formatCompactNumber(1000000000)).toBe('1.00B');
  });

  it('preserves sign and fallback tokens', () => {
    expect(formatCompactNumber(-1234567)).toBe('-1.23M');
    expect(formatCompactNumber(null)).toBe('-');
  });
});
