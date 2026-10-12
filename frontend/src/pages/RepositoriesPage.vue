<script setup lang="ts">
import { ArrowLeft } from '@lucide/vue'
import RepositoryConnections from '../components/RepositoryConnections.vue'
import type { ProviderRepository } from '../types/api'

defineProps<{ busy: boolean }>()

const emit = defineEmits<{
  back: []
  import: [repository: ProviderRepository, branch?: string]
}>()

function importRepository(repository: ProviderRepository, branch?: string) {
  emit('import', repository, branch)
}
</script>

<template>
  <div class="repositories-page">
    <header class="repositories-page__header">
      <button class="repositories-page__back" type="button" @click="$emit('back')">
        <ArrowLeft aria-hidden="true" />
        Back
      </button>
      <strong>Your repositories</strong>
    </header>
    <RepositoryConnections :busy="busy" @import="importRepository" />
  </div>
</template>
