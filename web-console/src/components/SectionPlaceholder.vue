<script setup lang="ts">
defineProps<{
  title: string
  description: string
  bullets: string[]
}>()
</script>

<template>
  <section class="placeholder-grid">
    <article class="surface-card placeholder-card">
      <p class="placeholder-card__eyebrow">V2 </p>
      <h2>{{ title }}</h2>
      <p class="placeholder-card__desc">{{ description }}</p>
      <ul class="placeholder-list">
        <li v-for="bullet in bullets" :key="bullet">{{ bullet }}</li>
      </ul>
    </article>

    <article class="surface-card placeholder-card placeholder-card--accent">
      <h3>当前状态</h3>
      <p>
        这些页面已经在路由里预留，后端数据模型也已对齐。后续只需要把
        `POST/GET` 的管理接口补齐，就能直接接上。
      </p>
    </article>
  </section>
</template>
