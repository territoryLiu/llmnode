import { describe, expect, it } from 'vitest'

import { parseSSEChunk } from './sse'

describe('parseSSEChunk', () => {
  it('parses snapshot events from SSE payload', () => {
    const events = parseSSEChunk('event: snapshot\ndata: {"backend_type":"vllm"}\n\n')

    expect(events).toHaveLength(1)
    expect(events[0]).toEqual({
      event: 'snapshot',
      data: '{"backend_type":"vllm"}',
    })
  })
})
