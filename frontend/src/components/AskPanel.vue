<script setup lang="ts">
import { MessageSquareText, Plus, SendHorizontal, Sparkles } from '@lucide/vue'
import { nextTick, ref, watch } from 'vue'
import type { ChatMessage } from '../types/api'
import FullscreenButton from './FullscreenButton.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import { useFullscreen } from '../composables/useFullscreen'

const props = defineProps<{
  workspaceName: string
  input: string
  busy: boolean
  messages: ChatMessage[]
  suggested: string[]
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'update:input', value: string): void
  (e: 'submit', value?: string): void
  (e: 'new-chat'): void
}>()

const messageList = ref<HTMLElement | null>(null)

watch(
  () => [
    props.messages.length,
    props.messages[props.messages.length - 1]?.content.length ?? 0,
    props.busy,
  ],
  async () => {
    await nextTick()
    if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
  },
  { flush: 'post' },
)

const panelRef = ref<HTMLElement | null>(null)
const { isFullscreen, toggle: toggleFullscreen } = useFullscreen(panelRef)
</script>

<template>
  <div ref="panelRef" class="panel ask-panel fullscreen-panel">
    <div class="panel-heading ask-panel__header">
      <h2 class="panel-heading__title">
        <MessageSquareText :size="14" />
        Ask the codebase
      </h2>
      <div class="ask-panel__header-actions">
        <span class="panel-heading__meta">Grounded in this workspace</span>
        <button v-if="messages.length" class="btn btn-ghost ask-panel__new" type="button" :disabled="busy" @click="emit('new-chat')">
          <Plus :size="13" /> New chat
        </button>
        <FullscreenButton :active="isFullscreen" label="Ask the codebase" @toggle="toggleFullscreen" />
      </div>
    </div>

    <div ref="messageList" class="ask-panel__messages" aria-live="polite">
      <div v-if="!messages.length && !busy" class="ask-panel__empty">
        <Sparkles :size="20" class="ask-panel__empty-icon" />
        <p>Ask anything about {{ workspaceName }}.</p>
        <span>Follow-up questions will remember this conversation.</span>
      </div>
      <div v-for="message in messages" :key="message.id" class="ask-panel__message" :class="`ask-panel__message--${message.role}`">
        <span class="ask-panel__role">{{ message.role === 'user' ? 'You' : 'RepoPilot' }}</span>
        <MarkdownRenderer v-if="message.role === 'assistant'" :content="message.content" />
        <pre v-else class="ask-panel__user-text">{{ message.content }}</pre>
      </div>
      <div
        v-if="busy && (!messages.length || messages[messages.length - 1]?.role !== 'assistant')"
        class="ask-panel__message ask-panel__message--assistant ask-panel__message--thinking"
      >
        <span class="ask-panel__role">RepoPilot</span>
        <p>Thinking in context…</p>
      </div>
    </div>

    <div v-if="!messages.length" class="chip-row ask-panel__suggested">
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
