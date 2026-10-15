<script setup lang="ts">
import { AlertTriangle, FlaskConical, GitBranch, GitCompare, LoaderCircle, MessageSquareText, MonitorPlay, Network, RefreshCw } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import AskPanel from './AskPanel.vue'
import BuildPipeline from './BuildPipeline.vue'
import DependencyGraph from './DependencyGraph.vue'
import ImpactPanel from './ImpactPanel.vue'
import InsightsPanel from './InsightsPanel.vue'
import RepoStatsPanel from './RepoStatsPanel.vue'
import RealtimePreviewLab from './RealtimePreviewLab.vue'
import TestGenPanel from './TestGenPanel.vue'
import { useGenerationStore } from '../stores/generation'
import { useFeatureFlagStore } from '../stores/features'
import type { RepositoryMetadata } from '../types/api'
import type { WorkspaceListItem, WorkspaceStage } from '../stores/workspace'

const props = defineProps<{
  workspace: WorkspaceListItem
  metadata: RepositoryMetadata | null
  frameworkLabel: string
  stages: WorkspaceStage[]
  targetOptions: Array<{ label: string; value: string; path: string }>
  branchOptions: string[]
  loadingBranches: boolean
  reindexing: boolean
}>()

const emit = defineEmits<{
  loadBranches: []
  reindex: [branch?: string]
}>()

const generationStore = useGenerationStore()
const featureFlags = useFeatureFlagStore()

const safeMetadata = computed<RepositoryMetadata>(() => ({
  repository: props.workspace.repoName,
  statistics: {
    files: 0,
    typescript: 0,
    javascript: 0,
    python: 0,
    java: 0,
  },
  testFramework: null,
  packageInfo: null,
  documentation: [],
  parsedFiles: [],
  relationships: [],
  repositoryFiles: [],
}))

const repositoryMetadata = computed(() => props.metadata ?? safeMetadata.value)
const linesCount = computed(() => createLinesCount(repositoryMetadata.value))
const testCount = computed(() => repositoryMetadata.value.parsedFiles.reduce((sum, file) => sum + file.existing_tests, 0))
const HOTSPOT_LIMIT = 5
const hotspots = computed(() =>
  [...repositoryMetadata.value.parsedFiles]
    .sort((left, right) => right.complexity - left.complexity || left.path.localeCompare(right.path))
    .slice(0, HOTSPOT_LIMIT)
    .map((file) => ({ path: file.path, score: file.complexity })),
)
const graph = computed(() => createGraphData(repositoryMetadata.value))
const selectedBranch = ref(props.workspace.indexedBranch ?? '')
const availableBranches = computed(() => [...new Set([
  ...(props.workspace.indexedBranch ? [props.workspace.indexedBranch] : []),
  ...props.branchOptions,
])])
watch(
  () => [props.workspace.id, props.workspace.indexedBranch] as const,
  () => { selectedBranch.value = props.workspace.indexedBranch ?? '' },
)
const tabMeta = {
  ask: { label: 'Ask the codebase', icon: MessageSquareText },
  tests: { label: 'Generate tests', icon: FlaskConical },
  preview: { label: 'Realtime preview', icon: MonitorPlay },
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

      <div class="workspace-view__actions">
        <div class="workspace-branch-control">
          <span class="workspace-branch-control__current">
            <GitBranch :size="13" aria-hidden="true" />
            Indexed branch: <strong>{{ workspace.indexedBranch || 'Unknown' }}</strong>
          </span>
          <select
            v-model="selectedBranch"
            aria-label="Branch to index"
            :disabled="workspace.status !== 'ready' || reindexing"
            @focus="emit('loadBranches')"
            @pointerdown="emit('loadBranches')"
          >
            <option v-if="!availableBranches.length" value="">Current/default branch</option>
            <option v-for="branch in availableBranches" :key="branch" :value="branch">{{ branch }}</option>
          </select>
          <button
            type="button"
            :disabled="workspace.status !== 'ready' || reindexing"
            @click="emit('reindex', selectedBranch || undefined)"
          >
            <LoaderCircle v-if="reindexing" class="spin" :size="14" aria-hidden="true" />
            <RefreshCw v-else :size="14" aria-hidden="true" />
            {{ reindexing ? 'Re-indexing…' : 'Re-index' }}
          </button>
          <span v-if="loadingBranches" class="workspace-branch-control__loading">Loading branches…</span>
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
      </div>
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
      :messages="generationStore.chatMessages"
      :suggested="generationStore.suggestedQuestions"
      :error="generationStore.error"
      @update:input="generationStore.setGenericQuery"
      @submit="generationStore.runQuery"
      @new-chat="generationStore.startNewChat"
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

    <RealtimePreviewLab
      v-else-if="generationStore.tab === 'preview' && featureFlags.previewEnabled"
      :workspace-id="workspace.id"
    />

    <InsightsPanel
      v-else-if="generationStore.tab === 'insights' && featureFlags.codeQualityEnabled"
      :items="insightItems"
    />

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
  x: number
  y: number
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
  const allPaths = new Set(metadata.parsedFiles.map((file) => file.path))
  for (const relationship of metadata.relationships) {
    allPaths.add(relationship.source)
    allPaths.add(relationship.target)
  }

  if (!allPaths.size) {
    return { nodes: [], edges: [] }
  }

  const degreeByPath = new Map<string, number>()
  const neighborsByPath = new Map([...allPaths].map((path) => [path, new Set<string>()]))
  for (const relationship of metadata.relationships) {
    degreeByPath.set(relationship.source, (degreeByPath.get(relationship.source) ?? 0) + 1)
    degreeByPath.set(relationship.target, (degreeByPath.get(relationship.target) ?? 0) + 1)
    neighborsByPath.get(relationship.source)?.add(relationship.target)
    neighborsByPath.get(relationship.target)?.add(relationship.source)
  }

  const positions = layoutGraph([...allPaths], neighborsByPath, degreeByPath)
  const nodes = [...allPaths].map((path) => ({
    id: path,
    label: shortenLabel(path),
    short: buildShortLabel(path),
    kind: inferKind(path),
    x: positions.get(path)?.x ?? 0,
    y: positions.get(path)?.y ?? 0,
  }))

  const edges = metadata.relationships
    .map((relationship, index) => ({
      id: `${relationship.source}->${relationship.target}:${relationship.module}:${index}`,
      source: relationship.source,
      target: relationship.target,
      strength: (((degreeByPath.get(relationship.source) ?? 0) + (degreeByPath.get(relationship.target) ?? 0)) >= 5
        ? 'strong'
        : 'normal') as GraphEdgeView['strength'],
    }))

  return { nodes, edges }
}

function layoutGraph(
  paths: string[],
  neighborsByPath: Map<string, Set<string>>,
  degreeByPath: Map<string, number>,
) {
  const unseen = new Set(paths)
  const components: string[][] = []
  while (unseen.size) {
    const start = unseen.values().next().value as string
    const component: string[] = []
    const stack = [start]
    unseen.delete(start)
    while (stack.length) {
      const path = stack.pop() as string
      component.push(path)
      for (const neighbor of neighborsByPath.get(path) ?? []) {
        if (unseen.delete(neighbor)) stack.push(neighbor)
      }
    }
    components.push(component)
  }
  components.sort((left, right) => right.length - left.length)

  const layouts = components.map((component) => {
    const root = [...component].sort((left, right) =>
      (degreeByPath.get(right) ?? 0) - (degreeByPath.get(left) ?? 0) || left.localeCompare(right),
    )[0]
    const levels = new Map<string, number>([[root, 0]])
    const queue = [root]
    for (let index = 0; index < queue.length; index += 1) {
      const path = queue[index]
      for (const neighbor of neighborsByPath.get(path) ?? []) {
        if (!levels.has(neighbor)) {
          levels.set(neighbor, (levels.get(path) ?? 0) + 1)
          queue.push(neighbor)
        }
      }
    }

    const pathsByLevel = new Map<number, string[]>()
    for (const path of component) {
      const level = levels.get(path) ?? 0
      pathsByLevel.set(level, [...(pathsByLevel.get(level) ?? []), path])
    }
    const local = new Map<string, { x: number; y: number }>()
    for (const [level, levelPaths] of pathsByLevel) {
      levelPaths.sort((left, right) =>
        (degreeByPath.get(right) ?? 0) - (degreeByPath.get(left) ?? 0) || left.localeCompare(right),
      )
      if (level === 0) {
        local.set(levelPaths[0], { x: 0, y: 0 })
        continue
      }
      const radius = Math.max(level * 150, (levelPaths.length * 62) / (2 * Math.PI))
      levelPaths.forEach((path, index) => {
        const angle = ((Math.PI * 2 * index) / levelPaths.length) - Math.PI / 2 + level * 0.3
        local.set(path, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius })
      })
    }
    const values = [...local.values()]
    const minX = Math.min(...values.map(({ x }) => x)) - 90
    const maxX = Math.max(...values.map(({ x }) => x)) + 90
    const minY = Math.min(...values.map(({ y }) => y)) - 90
    const maxY = Math.max(...values.map(({ y }) => y)) + 90
    return { local, minX, minY, width: maxX - minX, height: maxY - minY }
  })

  const targetRowWidth = Math.max(900, Math.sqrt(paths.length) * 240)
  const positions = new Map<string, { x: number; y: number }>()
  let cursorX = 40
  let cursorY = 40
  let rowHeight = 0
  for (const layout of layouts) {
    if (cursorX > 40 && cursorX + layout.width > targetRowWidth) {
      cursorX = 40
      cursorY += rowHeight + 50
      rowHeight = 0
    }
    for (const [path, point] of layout.local) {
      positions.set(path, {
        x: cursorX + point.x - layout.minX,
        y: cursorY + point.y - layout.minY,
      })
    }
    cursorX += layout.width + 50
    rowHeight = Math.max(rowHeight, layout.height)
  }
  return positions
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
