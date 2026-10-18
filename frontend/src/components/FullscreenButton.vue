<script setup lang="ts">
import { Maximize2, Minimize2 } from '@lucide/vue'

const props = defineProps<{ active: boolean; label: string }>()
const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <button
    class="panel-icon-button"
    type="button"
    :aria-label="props.active ? `Exit full screen: ${props.label}` : `Full screen: ${props.label}`"
    :title="props.active ? 'Exit full screen (Esc)' : 'Full screen'"
    :aria-pressed="props.active"
    @click="emit('toggle')"
  >
    <Minimize2 v-if="props.active" :size="15" aria-hidden="true" />
    <Maximize2 v-else :size="15" aria-hidden="true" />
  </button>
</template>
