<script setup lang="ts">
import { ref } from 'vue'
import FullscreenButton from './FullscreenButton.vue'
import { useFullscreen } from '../composables/useFullscreen'
import type { ImpactAnalysisResponse } from '../types/api'

defineProps<{
  selectedFile: string
  fileOptions: string[]
  busy: boolean
  result: ImpactAnalysisResponse | null
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'update:selectedFile', value: string): void
  (e: 'analyze', value?: string): void
}>()

const panelRef = ref<HTMLElement | null>(null)
const { isFullscreen, toggle: toggleFullscreen } = useFullscreen(panelRef)
</script>

<template>
  <div ref="panelRef" class="panel panel-pad fullscreen-panel">
    <div class="panel-heading">
      <h2>Impact analysis</h2>
      <div class="panel-heading__actions">
        <span class="panel-heading__meta">Modify a file -> see blast radius</span>
        <FullscreenButton :active="isFullscreen" label="Impact analysis" @toggle="toggleFullscreen" />
      </div>
    </div>

    <div class="inline-form">
      <select
        class="input"
        :value="selectedFile"
        @change="emit('update:selectedFile', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">Select a file for impact analysis</option>
        <option v-for="item in fileOptions" :key="item" :value="item">
          {{ item }}
        </option>
      </select>
      <button class="btn btn-primary" type="button" :disabled="busy || !selectedFile" @click="emit('analyze')">
        {{ busy ? 'Analyzing...' : 'Analyze impact' }}
      </button>
    </div>

    <div class="chip-row">
      <button
        v-for="item in fileOptions.slice(0, 3)"
        :key="item"
        class="chip chip--button"
        type="button"
        @click="emit('analyze', item)"
      >
        {{ item }}
      </button>
    </div>

    <div v-if="!result && !busy" class="empty-state-box">
      Select a file to see affected components, tests to rerun, and a computed risk level from the repository graph.
    </div>

    <div v-else-if="busy" class="empty-state-box">Analyzing impact...</div>

    <div v-else-if="result" class="impact-layout">
      <div class="impact-summary">
        <div>
          <div class="section-title">Selected file</div>
          <div class="impact-target">{{ result.target }}</div>
        </div>
        <span class="severity-tag" :class="`severity-tag--${result.risk}`">{{ result.risk }}</span>
      </div>

      <div class="impact-grid">
        <section class="impact-card">
          <div class="section-title">Affected components</div>
          <div v-if="result.affectedComponents.length" class="impact-list">
            <div v-for="component in result.affectedComponents" :key="component.path" class="impact-list__item">
              <strong>{{ component.name }}</strong>
              <span>{{ component.path }}</span>
            </div>
          </div>
          <div v-else class="impact-empty">No direct dependents were found for this file.</div>
        </section>

        <section class="impact-card">
          <div class="section-title">Potentially affected tests</div>
          <div v-if="result.potentiallyAffectedTests.length" class="impact-list">
            <div v-for="testPath in result.potentiallyAffectedTests" :key="testPath" class="impact-list__item">
              <strong>{{ testPath.split('/').pop() }}</strong>
              <span>{{ testPath }}</span>
            </div>
          </div>
          <div v-else class="impact-empty">No existing tests were linked to this blast radius yet.</div>
        </section>
      </div>

      <section class="impact-card">
        <div class="section-title">Why</div>
        <p class="impact-copy">{{ result.summary }}</p>
      </section>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>
  </div>
</template>
