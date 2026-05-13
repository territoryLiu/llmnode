import {describe, expect, it} from 'vitest';
import {mapAgentStatus, mapRequestStatus, translate} from './i18n';

describe('i18n helpers', () => {
  it('interpolates Chinese template values', () => {
    expect(translate('zh', 'overview.recentSamples', {count: 3})).toBe('最近 3 个采样点');
  });

  it('maps request and agent statuses in English', () => {
    expect(mapRequestStatus('en', 'ok')).toBe('Success');
    expect(mapAgentStatus('en', 'recovering')).toBe('Recovering');
  });
});
