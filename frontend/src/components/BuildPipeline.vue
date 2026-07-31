<script setup lang="ts">
import { Check, CircleX, LoaderCircle } from '@lucide/vue'
import { computed } from 'vue'
import type { WorkspaceStage } from '../stores/workspace'

const props = defineProps<{
  stages: WorkspaceStage[]
}>()

const isComplete = computed(() => props.stages.length > 0 && props.stages.every((stage) => stage.status === 'done'))
const hasFailed = computed(() => props.stages.some((stage) => stage.status === 'failed'))
</script>

<template>
  <div class="panel panel-pad">
    <div class="panel-heading">
      <div>
        <h2>Build pipeline</h2>
      </div>
      <span class="panel-heading__meta">{{ hasFailed ? 'Failed' : isComplete ? 'Complete' : 'In progress' }}</span>
    </div>

    <div class="pipeline-list">
      <div
        v-for="(stage, index) in stages"
        :key="stage.id"
        class="pipeline-row"
        :class="`pipeline-row--${stage.status}`"
      >
        <div class="pipeline-row__info">
          <span class="pipeline-row__dot">
            <Check v-if="stage.status === 'done'" :size="14" />
            <CircleX v-else-if="stage.status === 'failed'" :size="14" />
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
