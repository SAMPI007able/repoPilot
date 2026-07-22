<script setup lang="ts">
defineProps<{
  title: string
  subtitle: string
  stages: Array<{ id: string; label: string; status: 'idle' | 'active' | 'done' }>
}>()
</script>

<template>
  <article class="insight-card">
    <div class="insight-card__header">
      <div>
        <h3>{{ title }}</h3>
        <p>{{ subtitle }}</p>
      </div>
      <span class="insight-card__status">Complete</span>
    </div>

    <div class="pipeline-list">
      <div
        v-for="stage in stages"
        :key="stage.id"
        class="pipeline-list__item"
        :class="{
          'pipeline-list__item--active': stage.status === 'active',
          'pipeline-list__item--done': stage.status === 'done',
        }"
      >
        <div class="pipeline-list__meta">
          <span class="pipeline-list__dot" />
          <div>
            <strong>{{ stage.label }}</strong>
          </div>
        </div>
        <div class="pipeline-list__track">
          <span class="pipeline-list__bar" />
        </div>
      </div>
    </div>
  </article>
</template>
