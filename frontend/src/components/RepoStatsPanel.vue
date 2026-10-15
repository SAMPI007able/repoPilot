<script setup lang="ts">
import { Binary, FileCode2, FlaskConical, Hash } from '@lucide/vue'
import { computed } from 'vue'
import type { RepositoryMetadata } from '../types/api'

const props = defineProps<{
  metadata: RepositoryMetadata | null
  linesCount: number
  testCount: number
  hotspots: Array<{ path: string; score: number }>
}>()

const stats = computed(() => ({
  files: props.metadata?.statistics.files ?? 0,
  lines: props.linesCount,
  tests: props.testCount,
  typescript: props.metadata?.statistics.typescript ?? 0,
  javascript: props.metadata?.statistics.javascript ?? 0,
  python: props.metadata?.statistics.python ?? 0,
  java: props.metadata?.statistics.java ?? 0,
}))

const otherCount = computed(() => Math.max(
  stats.value.files - stats.value.typescript - stats.value.javascript - stats.value.python - stats.value.java,
  0,
))
const languageTotal = computed(() => Math.max(stats.value.files, 1))

const languageSegments = computed(() => [
  { label: 'TypeScript', count: stats.value.typescript, className: 'language-bar__ts' },
  { label: 'JavaScript', count: stats.value.javascript, className: 'language-bar__js' },
  { label: 'Python', count: stats.value.python, className: 'language-bar__python' },
  { label: 'Java', count: stats.value.java, className: 'language-bar__java' },
  { label: 'Other', count: otherCount.value, className: 'language-bar__other' },
])

function asPercent(value: number) {
  return Math.round((value / languageTotal.value) * 100)
}
</script>

<template>
  <div class="panel panel-pad">
    <div class="panel-heading">
      <h2>Repository statistics</h2>
    </div>

    <div class="stats-grid">
      <div class="stats-card">
        <span class="stats-card__icon"><FileCode2 :size="14" /></span>
        <strong>{{ stats.files.toLocaleString() }}</strong>
        <span>Files</span>
      </div>
      <div class="stats-card">
        <span class="stats-card__icon"><Hash :size="14" /></span>
        <strong>{{ stats.lines.toLocaleString() }}</strong>
        <span>Lines</span>
      </div>
      <div class="stats-card">
        <span class="stats-card__icon"><FlaskConical :size="14" /></span>
        <strong>{{ stats.tests.toLocaleString() }}</strong>
        <span>Tests</span>
      </div>
    </div>

    <div class="stats-section">
      <div class="section-title">Languages</div>
      <div class="language-bar">
        <span
          v-for="segment in languageSegments"
          :key="segment.label"
          :class="segment.className"
          :style="{ flexGrow: Math.max(segment.count, 1) }"
        />
      </div>
      <div class="language-legend">
        <span v-for="segment in languageSegments" :key="segment.label">
          <Binary :size="10" />
          {{ segment.label }} {{ asPercent(segment.count) }}%
        </span>
      </div>
    </div>

    <div class="stats-section">
      <div class="section-title">
        Hotspots by complexity
        <span
          class="metric-help"
          title="Aggregate McCabe complexity: one base path for the module and each function, plus one for every branch, loop, catch, switch case, ternary, and short-circuit logical operator."
        >How CC is calculated</span>
      </div>
      <div class="hotspots-list">
        <div v-for="item in hotspots" :key="item.path" class="hotspot-item">
          <span>{{ item.path }}</span>
          <strong>CC {{ item.score }}</strong>
        </div>
        <div v-if="hotspots.length === 0" class="hotspot-item hotspot-item--empty">
          <span>Hotspots will appear after indexing completes.</span>
        </div>
      </div>
    </div>
  </div>
</template>
