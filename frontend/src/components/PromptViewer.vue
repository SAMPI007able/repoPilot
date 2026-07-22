<script setup lang="ts">
defineProps<{
  prompt: string
}>()
</script>

<template>
  <article class="viewer-panel">
    <div class="viewer-panel__header">
      <h3>Prompt summary</h3>
    </div>

    <pre class="viewer-panel__body viewer-panel__body--prompt">{{ prompt }}</pre>
  </article>
</template>
