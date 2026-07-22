<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: string
  busy: boolean
  error: string | null
  projectDocuments: File[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:projectDocuments': [files: File[]]
  submit: []
}>()

const isDisabled = computed(() => props.busy || !props.modelValue.trim())

function updateProjectDocuments(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files ? Array.from(input.files) : []
  emit('update:projectDocuments', files)
}

const projectDocumentNames = computed(() => props.projectDocuments.map((file) => file.name).join(', '))
</script>

<template>
  <form class="card stack-lg" @submit.prevent="emit('submit')">
    <div class="stack-sm">
      <p class="eyebrow">Page 1</p>
      <h2 class="section-title">Workspace</h2>
      <p class="muted">
        Point TestForge AI at a GitHub repository and let it build a repository-aware workspace.
      </p>
    </div>

    <label class="field">
      <span class="field__label">GitHub Repository URL</span>
      <input
        :value="modelValue"
        class="field__input"
        type="url"
        placeholder="https://github.com/org/repo"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      >
    </label>

    <label class="field">
      <span class="field__label">Project Documents (optional)</span>
      <input
        class="field__input"
        type="file"
        multiple
        accept=".md,.pdf,.docx,.pptx,.txt,.yaml,.yml,.json,.csv,.rst,.xml"
        @change="updateProjectDocuments"
      />
      <p class="muted" v-if="projectDocumentNames">Selected: {{ projectDocumentNames }}</p>
      <p class="muted" v-else>Upload README, design docs, API specs, or other project documentation.</p>
    </label>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <button class="primary-button" type="submit" :disabled="isDisabled">
      {{ busy ? 'Building Workspace...' : 'Build Workspace' }}
    </button>
  </form>
</template>
