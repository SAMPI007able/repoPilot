<script setup lang="ts">
defineProps<{
  items: Array<{ title: string; path: string; severity: string; category: string; description: string }>
}>()
</script>

<template>
  <div class="panel panel-pad">
    <div class="panel-heading">
      <h2>Code-quality insights</h2>
      <span class="panel-heading__meta">{{ items.length }} findings</span>
    </div>

    <div v-if="items.length === 0" class="empty-state-box">
      Code quality insights will appear here once the backend starts returning findings.
    </div>

    <article v-for="item in items" :key="item.title + item.path" class="insight-row">
      <div class="insight-row__header">
        <div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.path }}</p>
        </div>
        <span class="severity-tag" :class="`severity-tag--${item.severity}`">{{ item.severity }}</span>
      </div>
      <div class="chip-row">
        <span class="chip">{{ item.category }}</span>
      </div>
      <p class="insight-row__copy">{{ item.description }}</p>
    </article>
  </div>
</template>
