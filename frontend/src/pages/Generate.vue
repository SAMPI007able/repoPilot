<script setup lang="ts">
import { computed } from 'vue'
import GenerateForm from '../components/GenerateForm.vue'
import PipelineProgress from '../components/PipelineProgress.vue'
import PromptViewer from '../components/PromptViewer.vue'
import TestViewer from '../components/TestViewer.vue'
import { useGenerationStore } from '../stores/generation'
import { useWorkspaceStore } from '../stores/workspace'

const workspaceStore = useWorkspaceStore()
const generationStore = useGenerationStore()

const hasWorkspace = computed(() => Boolean(workspaceStore.metadata))
const framework = computed(() => workspaceStore.metadata?.testFramework ?? workspaceStore.frameworkLabel)
</script>

<template>
  <section v-if="hasWorkspace" class="stack-xl">
    <section class="page-grid">
      <GenerateForm
        :targets="workspaceStore.targetOptions"
        :target="generationStore.target"
        :test-type="generationStore.testType"
        :busy="generationStore.isGenerating"
        :framework="framework"
        :disabled="workspaceStore.targetOptions.length === 0"
        @update:target="generationStore.setTarget"
        @update:test-type="generationStore.setTestType"
        @submit="generationStore.runGeneration"
      />

      <PipelineProgress
        title="Visible Reasoning Pipeline"
        subtitle="Repository → Knowledge Graph → Context Builder → Prompt Builder → Gemini → Generated Tests."
        :stages="generationStore.stages"
      />
    </section>

    <p v-if="generationStore.error" class="error-banner">{{ generationStore.error }}</p>

    <section v-if="generationStore.hasResult && generationStore.result" class="results-grid">
      <PromptViewer :prompt="generationStore.result.prompt" />
      <TestViewer :code="generationStore.result.markdown" />
      <article class="card stack-md viewer-card">
        <div class="stack-sm">
          <p class="eyebrow">Why these tests?</p>
          <h2 class="section-title">Reasoning Highlights</h2>
        </div>

        <ul class="reason-list">
          <li>Grounded in {{ framework }} because the repository framework is detected automatically.</li>
          <li>Targeted at {{ generationStore.selectedTargetLabel }} with repository-level context instead of a generic prompt.</li>
          <li>Shaped by graph-linked dependencies and any existing tests attached during indexing.</li>
        </ul>
      </article>
    </section>
  </section>

  <section v-else class="card stack-md empty-state">
    <p class="eyebrow">Generation Locked</p>
    <h2 class="section-title">No workspace available</h2>
    <p class="muted">Index a repository first so TestForge AI has something real to reason over.</p>
  </section>
</template>
