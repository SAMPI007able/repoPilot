<script setup lang="ts">
import type { AIQueryResponse } from '../types/api'

defineProps<{
  mode: 'scenario' | 'file'
  scenario: string
  selectedFile: string
  fileQuery: string
  fileMenuOpen: boolean
  fileOptions: string[]
  filteredFiles: string[]
  busy: boolean
  result: AIQueryResponse | null
  suggested: string[]
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'update:mode', value: 'scenario' | 'file'): void
  (e: 'update:scenario', value: string): void
  (e: 'update:selectedFile', value: string): void
  (e: 'update:fileQuery', value: string): void
  (e: 'update:fileMenuOpen', value: boolean): void
  (e: 'generate:scenario', value?: string): void
  (e: 'generate:file', value?: string): void
}>()
</script>

<template>
  <div class="panel panel-pad">
    <div class="panel-heading">
      <h2>Generate integration tests</h2>
      <span class="panel-heading__meta">{{ mode === 'scenario' ? 'Requirement -> cross-module tests' : 'File -> all scenarios' }}</span>
    </div>

    <div class="mode-switch">
      <button
        class="mode-switch__button"
        :class="{ 'mode-switch__button--active': mode === 'scenario' }"
        type="button"
        @click="emit('update:mode', 'scenario')"
      >
        From scenario
      </button>
      <button
        class="mode-switch__button"
        :class="{ 'mode-switch__button--active': mode === 'file' }"
        type="button"
        @click="emit('update:mode', 'file')"
      >
        From file
      </button>
    </div>

    <div v-if="mode === 'scenario'">
      <label class="scenario-field">
        <span class="scenario-field__label">Requirement or end-to-end behavior</span>
        <textarea
          class="input scenario-field__input"
          :value="scenario"
          placeholder="Describe the behavior to verify, e.g. a customer retries a payment after a timeout and receives exactly one successful charge."
          @input="emit('update:scenario', ($event.target as HTMLTextAreaElement).value)"
          @keydown.ctrl.enter.prevent="emit('generate:scenario')"
          @keydown.meta.enter.prevent="emit('generate:scenario')"
        />
      </label>
      <div class="scenario-actions">
        <p class="helper-text">
          No file selection is needed. RepoPilot discovers the related modules and follows their dependency boundaries.
        </p>
        <button class="btn btn-primary" type="button" :disabled="busy || !scenario.trim()" @click="emit('generate:scenario')">
          Generate from requirement
        </button>
      </div>

      <div class="chip-row">
        <button
          v-for="item in suggested"
          :key="item"
          class="chip chip--button"
          type="button"
          @click="emit('generate:scenario', item)"
        >
          {{ item }}
        </button>
      </div>
    </div>

    <div v-else>
      <div class="inline-form">
        <div class="dropdown-shell">
          <button class="input dropdown-shell__button" type="button" @click="emit('update:fileMenuOpen', !fileMenuOpen)">
            <span :class="selectedFile ? 'text-strong' : 'text-muted'">
              {{ selectedFile || 'Select a file to generate tests around...' }}
            </span>
            <span class="dropdown-shell__chevron">></span>
          </button>

          <div v-if="fileMenuOpen" class="dropdown-shell__menu">
            <div class="dropdown-shell__search">
              <input
                class="input input--dense"
                :value="fileQuery"
                placeholder="Filter files..."
                @input="emit('update:fileQuery', ($event.target as HTMLInputElement).value)"
              >
            </div>
            <div class="dropdown-shell__items scrollbar-thin">
              <button
                v-for="file in filteredFiles"
                :key="file"
                class="dropdown-shell__item"
                type="button"
                @click="emit('generate:file', file)"
              >
                {{ file }}
              </button>
              <div v-if="filteredFiles.length === 0" class="dropdown-shell__empty">No files match.</div>
            </div>
          </div>
        </div>

        <button class="btn btn-primary" type="button" :disabled="busy || !selectedFile.trim()" @click="emit('generate:file')">
          Generate all scenarios
        </button>
      </div>

      <p class="helper-text">
        RepoPilot reads the selected file, infers its public API and edge cases, and produces a battery of scenario tests.
      </p>
    </div>

    <div class="results-area">
      <div v-if="!result && !busy" class="empty-state-box">
        Generated tests will appear here. Each is wired to the modules it exercises.
      </div>
      <div v-else-if="busy" class="empty-state-box">Generating...</div>
      <pre v-else class="result-code">{{ result?.markdown }}</pre>
    </div>

    <p v-if="error" class="error-text">{{ error }}</p>
  </div>
</template>
