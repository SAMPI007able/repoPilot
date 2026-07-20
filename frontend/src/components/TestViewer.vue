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
  }, 1500)
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
      fontSize: 14,
      readOnly: true,
      automaticLayout: true,
      roundedSelection: false,
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
  <article class="card stack-md viewer-card">
    <div class="viewer-card__header">
      <div class="stack-sm">
        <p class="eyebrow">Generated Tests</p>
        <h2 class="section-title">Result Viewer</h2>
      </div>

      <button class="secondary-button" type="button" @click="copyCode">
        {{ copied ? 'Copied' : 'Copy Test' }}
      </button>
    </div>

    <div v-if="!useFallback" ref="container" class="monaco-host" />
    <pre v-else class="viewer-pre viewer-pre--code">{{ codeValue }}</pre>
  </article>
</template>
