<script setup lang="ts">
defineProps<{
  prompt: string
}>()
</script>

<template>
  <article class="card stack-md viewer-card">
    <div class="stack-sm">
      <p class="eyebrow">Prompt Summary</p>
      <h2 class="section-title">Prompt Builder Output</h2>
    </div>

    <pre class="viewer-pre viewer-pre--prompt">{{ prompt }}</pre>
  </article>
</template>
