<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

import type { MetricPoint } from '@/types'

const props = defineProps<{
  title: string
  color: string
  field: 'queueLength' | 'failureCount'
  points: MetricPoint[]
}>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const option = computed(() => ({
  backgroundColor: 'transparent',
  textStyle: { fontFamily: '"IBM Plex Sans", "Noto Sans SC", sans-serif', color: '#153047' },
  grid: { left: 12, right: 12, top: 36, bottom: 18, containLabel: true },
  xAxis: {
    type: 'category',
    data: props.points.map((item) => item.label),
    boundaryGap: false,
    axisLine: { lineStyle: { color: 'rgba(20, 40, 64, 0.12)' } },
    axisLabel: { color: 'rgba(21, 48, 71, 0.66)', fontSize: 10 },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: 'rgba(20, 40, 64, 0.08)' } },
    axisLabel: { color: 'rgba(21, 48, 71, 0.66)', fontSize: 10 },
  },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#ffffff',
    borderColor: 'rgba(20, 40, 64, 0.12)',
    textStyle: { color: '#153047' },
  },
  series: [
    {
      name: props.title,
      type: 'line',
      smooth: true,
      showSymbol: false,
      lineStyle: { width: 3, color: props.color },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: `${props.color}66` },
          { offset: 1, color: `${props.color}05` },
        ]),
      },
      data: props.points.map((item) => item[props.field]),
    },
  ],
}))

function render() {
  if (!chartEl.value) {
    return
  }
  chart ??= echarts.init(chartEl.value)
  chart.setOption(option.value)
}

onMounted(() => {
  render()
  window.addEventListener('resize', render)
})

watch(option, () => render(), { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', render)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="metric-chart">
    <div class="metric-chart__head">
      <span>{{ title }}</span>
    </div>
    <div ref="chartEl" class="metric-chart__canvas"></div>
  </div>
</template>
