<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

import { buildModelDistribution } from '@/lib/metrics'
import type { RequestLogEntry } from '@/types'

const props = defineProps<{
  logs: RequestLogEntry[]
}>()

const chartEl = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const data = computed(() => buildModelDistribution(props.logs))

const option = computed(() => ({
  backgroundColor: 'transparent',
  textStyle: { fontFamily: '"IBM Plex Sans", "Noto Sans SC", sans-serif', color: '#132235' },
  tooltip: {
    trigger: 'item',
    backgroundColor: '#ffffff',
    borderColor: 'rgba(19, 34, 53, 0.1)',
    textStyle: { color: '#132235' },
  },
  legend: {
    bottom: 4,
    icon: 'circle',
    itemWidth: 10,
    itemHeight: 10,
    textStyle: { color: '#5a687a' },
  },
  series: [
    {
      name: '模型分布',
      type: 'pie',
      radius: ['58%', '80%'],
      center: ['40%', '48%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 12, borderColor: '#f7fbff', borderWidth: 3 },
      label: {
        show: false,
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 14,
          fontWeight: 700,
        },
      },
      data: data.value.length
        ? data.value.map((item, index) => ({
            name: item.name,
            value: item.value,
            itemStyle: {
              color: ['#4f7cff', '#38c7b6', '#ff9f68', '#a971ff', '#34c759'][index % 5],
            },
          }))
        : [{ name: '暂无数据', value: 1, itemStyle: { color: '#dbe5f5' } }],
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
  <div class="surface-card chart-card">
    <div class="chart-card__head">
      <div>
        <p class="chart-card__eyebrow">模型分布</p>
        <h3>按逻辑模型统计请求量</h3>
      </div>
      <span>{{ data.length }} models</span>
    </div>
    <div ref="chartEl" class="chart-card__canvas chart-card__canvas--donut"></div>
  </div>
</template>
