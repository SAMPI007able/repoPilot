<script setup lang="ts">
import { Check, LoaderCircle } from '@lucide/vue'
import { computed } from 'vue'
import type { WorkspaceStage } from '../stores/workspace'

const props = defineProps<{
  stages: WorkspaceStage[]
}>()

const normalizedStages = computed(() => {
  const allBeforeReadyDone = props.stages
    .filter((stage) => stage.id !== 'ready')
    .every((stage) => stage.status === 'done')

  return props.stages.map((stage) => ({
    ...stage,
    status: stage.id === 'ready' && allBeforeReadyDone ? 'done' : stage.status,
  }))
})

const isComplete = computed(() => normalizedStages.value.every((stage) => stage.status === 'done'))
</script>

<template>
  <div class="panel panel-pad">
    <div class="panel-heading">
      <div>
        <h2>Build pipeline</h2>
      </div>
      <span class="panel-heading__meta">{{ isComplete ? 'Complete' : 'In progress' }}</span>
    </div>

    <div class="pipeline-list">
      <div
        v-for="(stage, index) in normalizedStages"
        :key="stage.id"
        class="pipeline-row"
        :class="`pipeline-row--${stage.status}`"
      >
        <div class="pipeline-row__info">
          <span class="pipeline-row__dot">
            <Check v-if="stage.status === 'done'" :size="14" />
            <LoaderCircle v-else-if="stage.status === 'active'" :size="14" class="pipeline-row__spinner" />
            <span v-else class="pipeline-row__number">{{ index + 1 }}</span>
          </span>
          <div>
            <div class="pipeline-row__label">{{ stage.label }}</div>
            <div class="pipeline-row__detail">{{ stage.detail }}</div>
          </div>
        </div>
        <div class="pipeline-row__track">
          <span v-if="stage.status !== 'upcoming'" class="pipeline-row__fill" />
        </div>
      </div>
    </div>
  </div>
</template>
