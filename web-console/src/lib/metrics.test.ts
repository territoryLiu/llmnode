import { describe, expect, it } from 'vitest'

import { buildModelDistribution } from './metrics'

describe('buildModelDistribution', () => {
  it('groups request logs by model name', () => {
    const result = buildModelDistribution([
      { model_name: 'qwen', id: 1, request_id: '1', status: 'ok', protocol: 'openai', created_at: '' },
      { model_name: 'qwen', id: 2, request_id: '2', status: 'ok', protocol: 'anthropic', created_at: '' },
      { model_name: 'gemma', id: 3, request_id: '3', status: 'ok', protocol: 'openai', created_at: '' },
    ])

    expect(result).toEqual([
      { name: 'qwen', value: 2 },
      { name: 'gemma', value: 1 },
    ])
  })
})
