<script setup lang="ts">
import { computed } from 'vue'
import type { RepositoryMetadata } from '../types/api'

const props = defineProps<{
  metadata: RepositoryMetadata
  frameworkLabel: string
  stats: Array<{ label: string; value: number }>
}>()

const headlineStats = computed(() => {
  const classes = props.stats.find((item) => item.label === 'Classes')?.value ?? 0
  const methods = props.stats.find((item) => item.label === 'Methods')?.value ?? 0
  return { classes, methods }
})
</script>

<template>
  <section class="workspace-grid">
    <article class="card stack-md">
      <div class="stack-sm">
        <p class="eyebrow">Page 2</p>
        <h2 class="section-title">Repository Overview</h2>
        <p class="muted">
          Immediate confidence that the system understood the repository, not just the URL.
        </p>
      </div>

      <div class="metric-grid">
        <div v-for="item in stats" :key="item.label" class="metric-card">
          <span class="metric-card__label">{{ item.label }}</span>
          <strong class="metric-card__value">{{ item.value }}</strong>
        </div>
      </div>

      <div class="badge-row">
        <span class="pill">{{ frameworkLabel }}</span>
        <span class="pill pill--muted">{{ metadata.testFramework ?? 'Framework detection pending' }}</span>
        <span class="pill pill--muted">{{ metadata.documentation.length }} docs indexed</span>
      </div>
    </article>

    <article class="card stack-md">
      <div class="stack-sm">
        <p class="eyebrow">Workspace Signal</p>
        <h3 class="subheading">{{ metadata.repository }}</h3>
      </div>

      <ul class="confidence-list">
        <li>✓ Repository Cloned</li>
        <li>✓ {{ metadata.statistics.files }} Files Indexed</li>
        <li>✓ {{ headlineStats.classes }} Classes</li>
        <li>✓ {{ headlineStats.methods }} Methods</li>
        <li>✓ Knowledge Graph Built</li>
      </ul>
    </article>
  </section>
</template>
