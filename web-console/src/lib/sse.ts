export interface SSEEvent {
  event: string
  data: string
}

export function parseSSEChunk(chunk: string): SSEEvent[] {
  return chunk
    .split('\n\n')
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map((entry) => {
      const lines = entry.split('\n')
      let event = 'message'
      const data: string[] = []

      for (const line of lines) {
        if (line.startsWith('event:')) {
          event = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          data.push(line.slice(5).trim())
        }
      }

      return {
        event,
        data: data.join('\n'),
      }
    })
}

export async function consumeSSEStream(
  response: Response,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  if (!response.body) {
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const boundary = buffer.lastIndexOf('\n\n')
    if (boundary === -1) {
      continue
    }

    const complete = buffer.slice(0, boundary)
    buffer = buffer.slice(boundary + 2)

    for (const event of parseSSEChunk(complete)) {
      onEvent(event)
    }
  }

  if (buffer.trim()) {
    for (const event of parseSSEChunk(buffer)) {
      onEvent(event)
    }
  }
}
