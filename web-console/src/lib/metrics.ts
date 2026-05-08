import type { RequestLogEntry } from '@/types'

export interface ModelDistributionItem {
  name: string
  value: number
}

export function buildModelDistribution(logs: RequestLogEntry[]): ModelDistributionItem[] {
  const counts = new Map<string, number>()

  for (const log of logs) {
    counts.set(log.model_name, (counts.get(log.model_name) ?? 0) + 1)
  }

  return [...counts.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((left, right) => right.value - left.value || left.name.localeCompare(right.name))
}
