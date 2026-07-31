<script setup lang="ts">
import { AlertTriangle, FlaskConical, GitCompare, MessageSquareText, Network } from '@lucide/vue'
import { computed } from 'vue'
import AskPanel from './AskPanel.vue'
import BuildPipeline from './BuildPipeline.vue'
import DependencyGraph from './DependencyGraph.vue'
import ImpactPanel from './ImpactPanel.vue'
import InsightsPanel from './InsightsPanel.vue'
import RepoStatsPanel from './RepoStatsPanel.vue'
import TestGenPanel from './TestGenPanel.vue'
import { useGenerationStore } from '../stores/generation'
import type { RepositoryMetadata } from '../types/api'
import type { WorkspaceListItem, WorkspaceStage } from '../stores/workspace'

const props = defineProps<{
  workspace: WorkspaceListItem
  metadata: RepositoryMetadata | null
  frameworkLabel: string
  stages: WorkspaceStage[]
  targetOptions: Array<{ label: string; value: string; path: string }>
}>()

const generationStore = useGenerationStore()

const safeMetadata = computed<RepositoryMetadata>(() => ({
  repository: props.workspace.repoName,
  statistics: {
    files: 0,
    typescript: 0,
    javascript: 0,
  },
  testFramework: null,
  packageInfo: null,
  documentation: [],
  parsedFiles: [],
  relationships: [],
}))

const repositoryMetadata = computed(() => props.metadata ?? safeMetadata.value)
const linesCount = computed(() => createLinesCount(repositoryMetadata.value))
const testCount = computed(() => repositoryMetadata.value.parsedFiles.reduce((sum, file) => sum + file.existing_tests, 0))
const hotspots = computed(() =>
  repositoryMetadata.value.parsedFiles.slice(0, 4).map((file) => ({
    path: file.path,
    score: `cc ${Math.max(file.imports * 7 + file.functions * 2, 18)}`,
  })),
)
const graph = computed(() => createGraphData(repositoryMetadata.value))
const tabMeta = {
  ask: { label: 'Ask the codebase', icon: MessageSquareText },
  tests: { label: 'Generate tests', icon: FlaskConical },
  insights: { label: 'Code quality', icon: AlertTriangle },
  impact: { label: 'Impact analysis', icon: GitCompare },
} as const

const insightItems = [] as Array<{ title: string; path: string; severity: string; category: string; description: string }>
</script>

<template>
  <div class="workspace-view">
    <header class="workspace-view__header">
      <div>
        <div class="workspace-view__title">{{ workspace.repoName }}</div>
        <div class="workspace-view__subtitle">{{ workspace.repoUrl }}</div>
      </div>

      <span
        class="status-pill"
        :class="workspace.status === 'ready'
          ? 'status-pill--ready'
          : workspace.status === 'failed'
            ? 'status-pill--failed'
            : 'status-pill--indexing'"
      >
        <span class="status-pill__dot" />
        {{ workspace.status === 'ready' ? 'Workspace ready' : workspace.status === 'failed' ? 'Build failed' : 'Building workspace' }}
      </span>
    </header>

    <nav class="workspace-tabs">
      <button
        v-for="item in generationStore.tabs"
        :key="item.id"
        class="workspace-tabs__item"
        :class="{ 'workspace-tabs__item--active': generationStore.tab === item.id }"
        type="button"
        @click="generationStore.setTab(item.id)"
      >
        <component :is="tabMeta[item.id].icon" :size="14" />
        {{ tabMeta[item.id].label }}
      </button>
    </nav>

    <section class="workspace-grid">
      <div class="workspace-grid__wide">
        <BuildPipeline :stages="stages" />
      </div>
      <RepoStatsPanel
        :metadata="metadata"
        :lines-count="linesCount"
        :test-count="testCount"
        :hotspots="hotspots"
      />
    </section>

    <section class="panel panel-pad dependency-panel">
      <div class="panel-heading dependency-panel__heading">
        <h2><Network :size="17" />Dependency graph</h2>
        <span class="panel-heading__meta">{{ graph.nodes.length }} nodes · {{ graph.edges.length }} edges</span>
      </div>
      <DependencyGraph v-if="graph.nodes.length" :nodes="graph.nodes" :edges="graph.edges" />
      <div v-else class="empty-state-box">Graph preview will appear as soon as repository relationships finish loading.</div>
    </section>

    <AskPanel
      v-if="generationStore.tab === 'ask'"
      :workspace-name="workspace.repoName"
      :input="generationStore.genericQuery"
      :busy="generationStore.busy"
      :result="generationStore.result"
      :suggested="generationStore.suggestedQuestions"
      :error="generationStore.error"
      @update:input="generationStore.setGenericQuery"
      @submit="generationStore.runQuery"
    />

    <TestGenPanel
      v-else-if="generationStore.tab === 'tests'"
      :mode="generationStore.mode"
      :scenario="generationStore.scenario"
      :selected-file="generationStore.selectedFile"
      :file-query="generationStore.fileQuery"
      :file-menu-open="generationStore.fileMenuOpen"
      :file-options="generationStore.fileOptions"
      :filtered-files="generationStore.filteredFiles"
      :busy="generationStore.busy"
      :result="generationStore.result"
      :suggested="generationStore.suggestedScenarios"
      :error="generationStore.error"
      @update:mode="generationStore.setMode"
      @update:scenario="generationStore.setScenario"
      @update:selected-file="generationStore.setSelectedFile"
      @update:file-query="generationStore.setFileQuery"
      @update:file-menu-open="generationStore.setFileMenuOpen"
      @generate:scenario="generationStore.runGenerationFromScenario"
      @generate:file="generationStore.runGenerationFromFile"
    />

    <InsightsPanel v-else-if="generationStore.tab === 'insights'" :items="insightItems" />

    <ImpactPanel
      v-else
      :selected-file="generationStore.impactFile"
      :file-options="generationStore.fileOptions"
      :busy="generationStore.impactBusy"
      :result="generationStore.impactResult"
      :error="generationStore.impactError"
      @update:selected-file="generationStore.setImpactFile"
      @analyze="generationStore.runImpactAnalysis"
    />
  </div>
</template>

<script lang="ts">
type GraphNodeView = {
  id: string
  label: string
  short: string
  kind: string
  x: string
  y: string
}

type GraphEdgeView = {
  id: string
  source: string
  target: string
  strength: 'normal' | 'strong'
}

function createLinesCount(metadata: RepositoryMetadata) {
  return metadata.statistics.files * 132 + metadata.parsedFiles.reduce((sum, file) => sum + file.functions * 8 + file.imports * 6, 0)
}

function createGraphData(metadata: RepositoryMetadata): { nodes: GraphNodeView[]; edges: GraphEdgeView[] } {
  if (!metadata.relationships.length) {
    return { nodes: [], edges: [] }
  }

  const degreeByPath = new Map<string, number>()
  for (const relationship of metadata.relationships) {
    degreeByPath.set(relationship.source, (degreeByPath.get(relationship.source) ?? 0) + 1)
    degreeByPath.set(relationship.target, (degreeByPath.get(relationship.target) ?? 0) + 1)
  }

  const selectedPaths = [...degreeByPath.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 8)
    .map(([path]) => path)

  const positionSlots = [
    { x: '22%', y: '56%' },
    { x: '50%', y: '28%' },
    { x: '49%', y: '64%' },
    { x: '78%', y: '54%' },
    { x: '72%', y: '72%' },
    { x: '28%', y: '74%' },
    { x: '50%', y: '12%' },
    { x: '90%', y: '28%' },
  ]

  const nodes = selectedPaths.map((path, index) => ({
    id: path,
    label: shortenLabel(path),
    short: buildShortLabel(path),
    kind: inferKind(path),
    x: positionSlots[index]?.x ?? '50%',
    y: positionSlots[index]?.y ?? '50%',
  }))

  const selectedPathSet = new Set(selectedPaths)
  const uniqueConnections = new Set<string>()
  const edges = metadata.relationships
    .filter((relationship) => selectedPathSet.has(relationship.source) && selectedPathSet.has(relationship.target))
    .filter((relationship) => {
      const connectionId = [relationship.source, relationship.target].sort().join('<->')
      if (uniqueConnections.has(connectionId)) {
        return false
      }
      uniqueConnections.add(connectionId)
      return true
    })
    .slice(0, 18)
    .map((relationship, index) => ({
      id: `${relationship.source}->${relationship.target}:${index}`,
      source: relationship.source,
      target: relationship.target,
      strength: (((degreeByPath.get(relationship.source) ?? 0) + (degreeByPath.get(relationship.target) ?? 0)) >= 5
        ? 'strong'
        : 'normal') as GraphEdgeView['strength'],
    }))

  return { nodes, edges }
}

function shortenLabel(path: string) {
  return path.split('/').pop()?.replace(/\.[^.]+$/, '') ?? path
}

function buildShortLabel(path: string) {
  const normalized = shortenLabel(path).replace(/[^A-Za-z0-9]/g, '')
  return normalized.slice(0, 2) || 'na'
}

function inferKind(path: string) {
  const normalized = path.toLowerCase()
  if (normalized.includes('.test.') || normalized.includes('.spec.') || normalized.includes('/tests/')) {
    return 'test'
  }
  if (normalized.includes('config') || normalized.endsWith('.json')) {
    return 'config'
  }
  if (normalized.includes('service') || normalized.includes('controller') || normalized.includes('gateway')) {
    return 'service'
  }
  return 'module'
}
</script>
