<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import PipelineProgress from '../components/PipelineProgress.vue'
import WorkspaceSummary from '../components/WorkspaceSummary.vue'
import { useWorkspaceStore } from '../stores/workspace'

const workspaceStore = useWorkspaceStore()

const hasWorkspace = computed(() => Boolean(workspaceStore.metadata))
</script>

<template>
  <section v-if="hasWorkspace && workspaceStore.metadata" class="stack-xl">
    <WorkspaceSummary
      :metadata="workspaceStore.metadata"
      :framework-label="workspaceStore.frameworkLabel"
      :stats="workspaceStore.dashboardStats"
    />

    <section class="page-grid">
      <PipelineProgress
        title="Repository Pipeline"
        subtitle="This pipeline stays visible so the knowledge graph and indexing work remain legible."
        :stages="workspaceStore.stages"
      />

      <article class="card stack-md">
        <p class="eyebrow">Next Step</p>
        <h2 class="section-title">Move to generation</h2>
        <p class="muted">
          Your workspace is live. Pick a target and generate tests with the detected framework and repository context.
        </p>
        <RouterLink class="primary-button primary-button--link" to="/generate">
          Open Generate Tests
        </RouterLink>
      </article>
    </section>
  </section>

  <section v-else class="card stack-md empty-state">
    <p class="eyebrow">Workspace Required</p>
    <h2 class="section-title">Build a workspace first</h2>
    <p class="muted">Index a repository from the home screen to unlock the overview dashboard.</p>
    <RouterLink class="primary-button primary-button--link" to="/">
      Back to Workspace
    </RouterLink>
  </section>
</template>
