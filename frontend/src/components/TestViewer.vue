<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  code: string
}>()

const copied = ref(false)
const useFallback = ref(false)
const container = ref<HTMLElement | null>(null)
const editor = ref<any>(null)

const codeValue = computed(() => props.code || '# Generated tests will appear here.')

async function copyCode() {
  await navigator.clipboard.writeText(codeValue.value)
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1400)
}

onMounted(async () => {
  try {
    const dynamicImport = new Function('specifier', 'return import(specifier)')
    const monaco = await dynamicImport('monaco-editor')

    if (!container.value) {
      return
    }

    editor.value = monaco.editor.create(container.value, {
      value: codeValue.value,
      language: 'typescript',
      theme: 'vs-dark',
      minimap: { enabled: false },
      fontSize: 13,
      readOnly: true,
      automaticLayout: true,
      scrollBeyondLastLine: false,
    })
  } catch {
    useFallback.value = true
  }
})

watch(codeValue, (nextValue) => {
  if (editor.value) {
    editor.value.setValue(nextValue)
  }
})
</script>

<template>
  <article class="viewer-panel">
    <div class="viewer-panel__header">
      <h3>Generated tests</h3>
      <button class="ghost-button" type="button" @click="copyCode">
        {{ copied ? 'Copied' : 'Copy test' }}
      </button>
    </div>

    <div v-if="!useFallback" ref="container" class="viewer-panel__editor" />
    <pre v-else class="viewer-panel__body viewer-panel__body--code">{{ codeValue }}</pre>
  </article>
</template>
