<script setup lang="ts">
defineProps<{
  targets: Array<{ label: string; value: string; path: string }>
  target: string
  testType: 'unit' | 'integration'
  busy: boolean
  framework: string
  disabled: boolean
}>()

const emit = defineEmits<{
  'update:target': [value: string]
  'update:testType': [value: 'unit' | 'integration']
  submit: []
}>()
</script>

<template>
  <form class="card stack-lg" @submit.prevent="emit('submit')">
    <div class="stack-sm">
      <p class="eyebrow">Page 3</p>
      <h2 class="section-title">Generate Tests</h2>
      <p class="muted">
        Choose a repository target, keep the framework grounded, and let the pipeline explain each stage.
      </p>
    </div>

    <div class="stack-md">
      <label class="field">
        <span class="field__label">Target</span>
        <select
          class="field__input field__select"
          :value="target"
          @change="emit('update:target', ($event.target as HTMLSelectElement).value)"
        >
          <option disabled value="">Select a service or module</option>
          <option v-for="option in targets" :key="option.path" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>

      <div class="stack-sm">
        <span class="field__label">Test Type</span>
        <div class="segmented">
          <button
            class="segmented__option"
            :class="{ 'segmented__option--active': testType === 'unit' }"
            type="button"
            @click="emit('update:testType', 'unit')"
          >
            Unit
          </button>
          <button
            class="segmented__option"
            :class="{ 'segmented__option--active': testType === 'integration' }"
            type="button"
            @click="emit('update:testType', 'integration')"
          >
            Integration
          </button>
        </div>
      </div>
    </div>

    <div class="badge-row">
      <span class="pill">Detected Framework: {{ framework }}</span>
    </div>

    <button class="primary-button" type="submit" :disabled="disabled || busy">
      {{ busy ? 'Generating...' : 'Generate' }}
    </button>
  </form>
</template>
