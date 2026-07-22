<script setup lang="ts">
import { MessageSquareText, SendHorizontal, Sparkles } from '@lucide/vue'
import type { AIQueryResponse } from '../types/api'

defineProps<{
  workspaceName: string
  input: string
  busy: boolean
  result: AIQueryResponse | null
  suggested: string[]
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'update:input', value: string): void
  (e: 'submit', value?: string): void
}>()
</script>

<template>
  <div class="panel ask-panel">
    <div class="panel-heading ask-panel__header">
      <h2 class="panel-heading__title">
        <MessageSquareText :size="14" />
        Ask the codebase
      </h2>
      <span class="panel-heading__meta">Grounded in the indexed graph</span>
    </div>

    <div class="ask-panel__messages">
      <div v-if="!result && !busy" class="ask-panel__empty">
        <Sparkles :size="20" class="ask-panel__empty-icon" />
        <p>Ask anything about {{ workspaceName }}.</p>
        <span>TestForge walks the dependency graph to answer.</span>
      </div>
      <div v-else-if="busy" class="ask-panel__empty">
        <p>Processing...</p>
      </div>
      <div v-else class="ask-panel__response">
        <pre>{{ result?.markdown }}</pre>
      </div>
    </div>

    <div v-if="!result" class="chip-row ask-panel__suggested">
      <button v-for="item in suggested" :key="item" class="chip chip--button" type="button" @click="emit('submit', item)">
        {{ item }}
      </button>
    </div>

    <div class="ask-panel__composer">
      <input
        class="input"
        :value="input"
        placeholder="Ask about the payment flow, webhooks, retry..."
        @input="emit('update:input', ($event.target as HTMLInputElement).value)"
        @keydown.enter.prevent="emit('submit')"
      >
      <button class="btn btn-primary" type="button" :disabled="busy || !input.trim()" @click="emit('submit')">
        <SendHorizontal :size="14" />
        Ask
      </button>
    </div>

    <p v-if="error" class="error-text ask-panel__error">{{ error }}</p>
  </div>
</template>
