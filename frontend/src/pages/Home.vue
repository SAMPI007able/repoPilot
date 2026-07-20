<script setup lang="ts">
import { useRouter } from 'vue-router'
import PipelineProgress from '../components/PipelineProgress.vue'
import RepositoryForm from '../components/RepositoryForm.vue'
import { useWorkspaceStore } from '../stores/workspace'

const router = useRouter()
const workspaceStore = useWorkspaceStore()

async function handleSubmit() {
  const metadata = await workspaceStore.createWorkspace()
  if (metadata) {
    router.push('/workspace')
  }
}
</script>

<template>
  <section class="page-grid page-grid--hero">
    <div class="stack-lg">
      <RepositoryForm
        :model-value="workspaceStore.repositoryUrl"
        :busy="workspaceStore.isBuilding"
        :error="workspaceStore.error"
        @update:model-value="workspaceStore.setRepositoryUrl"
        @submit="handleSubmit"
      />
    </div>

    <div class="stack-lg">
      <PipelineProgress
        title="Workspace Intelligence"
        subtitle="Each stage becomes visible so the demo reads like a system, not a black box."
        :stages="workspaceStore.stages"
      />

      <!-- <article class="card stack-md">
        <p class="eyebrow">Why it lands</p>
        <h2 class="section-title">Not just a chat box</h2>
        <p class="muted">
          Judges see the repository flow immediately: clone, index, graph, context, prompt, model, output.
        </p>
      </article> -->
    </div>
  </section>
</template>
