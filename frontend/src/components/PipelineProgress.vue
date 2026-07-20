<script setup lang="ts">
defineProps<{
  title: string
  subtitle: string
  stages: Array<{ id: string; label: string; status: 'idle' | 'active' | 'done' }>
}>()
</script>

<template>
  <article class="card stack-md">
    <div class="stack-sm">
      <p class="eyebrow">Pipeline</p>
      <h2 class="section-title">{{ title }}</h2>
      <p class="muted">{{ subtitle }}</p>
    </div>

    <div class="pipeline">
      <div
        v-for="(stage, index) in stages"
        :key="stage.id"
        class="pipeline__stage"
        :class="{
          'pipeline__stage--active': stage.status === 'active',
          'pipeline__stage--done': stage.status === 'done',
        }"
      >
        <span class="pipeline__index">{{ index + 1 }}</span>
        <span class="pipeline__label">{{ stage.label }}</span>
      </div>
    </div>
  </article>
</template>
