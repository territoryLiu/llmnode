import {describe, expect, it} from 'vitest';

import {formatUsageChartBucketLabel} from './UsageRecordsView';

describe('formatUsageChartBucketLabel', () => {
  it('formats 12h buckets in local timezone instead of raw utc hour', () => {
    expect(
      formatUsageChartBucketLabel('2026-05-15 08:00', '12h', 'zh'),
    ).toBe('16:00');
  });

  it('formats day buckets in local timezone with local date rollover', () => {
    expect(
      formatUsageChartBucketLabel('2026-05-15 18:00', 'day', 'zh'),
    ).toBe('05/16 02:00');
  });

  it('keeps year buckets stable without timezone shifting', () => {
    expect(
      formatUsageChartBucketLabel('2026-05', 'year', 'zh'),
    ).toBe('2026-05');
  });
});
