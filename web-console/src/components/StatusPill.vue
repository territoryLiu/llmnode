<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  label: string
}>()

const tone = computed(() => {
  const value = props.label.toLowerCase()
  if (value === 'ready' || value === 'healthy') {
    return 'status-pill--good'
  }
  if (value === 'recovering' || value === 'starting') {
    return 'status-pill--warn'
  }
  return 'status-pill--bad'
})
</script>

<template>
  <span class="status-pill" :class="tone">{{ label }}</span>
</template>
