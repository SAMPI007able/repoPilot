<script setup lang="ts">
import { AlertTriangle, FlaskConical, GitBranch, GitCompare, LoaderCircle, MessageSquareText, MonitorPlay, Network, RefreshCw } from '@lucide/vue'
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import BuildPipeline from './BuildPipeline.vue'
import FullscreenButton from './FullscreenButton.vue'
import DependencyGraph from './DependencyGraph.vue'
import RepoStatsPanel from './RepoStatsPanel.vue'
import { useGenerationStore } from '../stores/generation'
import { useFeatureFlagStore } from '../stores/features'
import type { GraphData, GraphLayoutInput } from '../services/graphLayout'
import type { RepositoryMetadata } from '../types/api'
import { useFullscreen } from '../composables/useFullscreen'
import { smoothScrollToElement } from '../utils/scroll'
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
const AskPanel = defineAsyncComponent(() => import('./AskPanel.vue'))
const ImpactPanel = defineAsyncComponent(() => import('./ImpactPanel.vue'))
const InsightsPanel = defineAsyncComponent(() => import('./InsightsPanel.vue'))
const RealtimePreviewLab = defineAsyncComponent(() => import('./RealtimePreviewLab.vue'))
const TestGenPanel = defineAsyncComponent(() => import('./TestGenPanel.vue'))

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
const graph = shallowRef<GraphData>({ nodes: [], edges: [] })
const graphLoading = ref(false)
let graphWorker: Worker | null = null
let graphRequestId = 0

function calculateGraph() {
  const requestId = ++graphRequestId
  const metadata: GraphLayoutInput = {
    parsedFiles: repositoryMetadata.value.parsedFiles.map(({ path }) => ({ path })),
    relationships: repositoryMetadata.value.relationships.map(({ source, target, module }) => ({
      source,
      target,
      module,
    })),
  }
  graphLoading.value = true
  if (typeof Worker === 'undefined') {
    window.setTimeout(() => {
      if (requestId !== graphRequestId) return
      graph.value = createGraphData(repositoryMetadata.value)
      graphLoading.value = false
    })
    return
  }
  if (!graphWorker) {
    graphWorker = new Worker(new URL('../workers/graphLayout.worker.ts', import.meta.url), { type: 'module' })
    graphWorker.onmessage = ({ data }: MessageEvent<{ id: number; graph: GraphData }>) => {
      if (data.id !== graphRequestId) return
      graph.value = data.graph
      graphLoading.value = false
    }
    graphWorker.onerror = () => {
      graphWorker?.terminate()
      graphWorker = null
      graph.value = createGraphData(repositoryMetadata.value)
      graphLoading.value = false
    }
  }
  graphWorker.postMessage({ id: requestId, metadata })
}

watch(
  () => [repositoryMetadata.value.parsedFiles, repositoryMetadata.value.relationships],
  calculateGraph,
  { immediate: true },
)
onBeforeUnmount(() => graphWorker?.terminate())
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

// Only the tab bar is pinned while scrolling; switching tools scrolls gently to the active panel.
const tabsRef = ref<HTMLElement | null>(null)
const tabPanelRef = ref<HTMLElement | null>(null)
const dependencyPanelRef = ref<HTMLElement | null>(null)
const tabsStuck = ref(false)
const { isFullscreen: graphFullscreen, toggle: toggleGraphFullscreen } = useFullscreen(dependencyPanelRef)
let stuckFrame = 0

function updateTabsStuck() {
  cancelAnimationFrame(stuckFrame)
  stuckFrame = requestAnimationFrame(() => {
    const tabs = tabsRef.value
    tabsStuck.value = Boolean(tabs && window.scrollY > 0 && tabs.getBoundingClientRect().top <= 1)
  })
}

// Tab panels are async components, so the wrapper is empty until the chunk loads and renders.
// Scrolling before that measures an empty panel at the end of a too-short page and stops at the graph.
function waitForPanelContent(panel: HTMLElement, timeoutMs = 2000) {
  return new Promise<void>((resolve) => {
    if (panel.offsetHeight > 0) return resolve()
    const observer = new ResizeObserver(() => {
      if (panel.offsetHeight > 0) finish()
    })
    const timer = window.setTimeout(finish, timeoutMs)
    function finish() {
      observer.disconnect()
      window.clearTimeout(timer)
      resolve()
    }
    observer.observe(panel)
  })
}

let tabScrollRequest = 0

async function selectTab(id: Parameters<typeof generationStore.setTab>[0]) {
  const request = ++tabScrollRequest
  generationStore.setTab(id)
  await nextTick()
  const panel = tabPanelRef.value
  if (!panel) return
  await waitForPanelContent(panel)
  // Let the freshly rendered panel finish layout before measuring its position.
  await new Promise(requestAnimationFrame)
  if (request !== tabScrollRequest) return
  smoothScrollToElement(panel, (tabsRef.value?.offsetHeight ?? 0) + 12)
}

// When a build or re-index finishes successfully, move the user from the pipeline to the chat.
watch(
  () => [props.workspace.id, props.workspace.status] as const,
  ([id, status], [previousId, previousStatus]) => {
    const succeeded = props.stages.length > 0 && props.stages.every((stage) => stage.status === 'done')
    if (id === previousId && previousStatus !== 'ready' && status === 'ready' && succeeded) {
      void selectTab('ask')
    }
  },
)

onMounted(() => {
  window.addEventListener('scroll', updateTabsStuck, { passive: true })
  updateTabsStuck()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(stuckFrame)
  window.removeEventListener('scroll', updateTabsStuck)
})
</script>

<template>
  <div class="workspace-view">
    <header class="workspace-view__header">
      <div class="workspace-view__title-block">
        <div class="workspace-view__title">{{ workspace.repoName }}</div>
        <div class="workspace-view__subtitle-row">
          <div class="workspace-view__subtitle">{{ workspace.repoUrl }}</div>
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
            class="workspace-branch-control__reindex"
            type="button"
            :disabled="workspace.status !== 'ready' || reindexing"
            :aria-label="reindexing ? 'Re-indexing repository' : 'Re-index selected branch'"
            :title="reindexing ? 'Re-indexing…' : 'Re-index selected branch'"
            @click="emit('reindex', selectedBranch || undefined)"
          >
            <LoaderCircle v-if="reindexing" class="spin" :size="15" aria-hidden="true" />
            <RefreshCw v-else :size="15" aria-hidden="true" />
          </button>
          <span v-if="loadingBranches" class="workspace-branch-control__loading">Loading branches…</span>
        </div>
      </div>
    </header>

    <nav ref="tabsRef" class="workspace-tabs" :class="{ 'workspace-tabs--stuck': tabsStuck }" aria-label="Workspace tools">
      <button
        v-for="item in generationStore.tabs"
        :key="item.id"
        class="workspace-tabs__item"
        :class="{ 'workspace-tabs__item--active': generationStore.tab === item.id }"
        type="button"
        :aria-current="generationStore.tab === item.id ? 'page' : undefined"
        @click="selectTab(item.id)"
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

    <section ref="dependencyPanelRef" class="panel panel-pad dependency-panel fullscreen-panel">
      <div class="panel-heading dependency-panel__heading">
        <h2><Network :size="17" />Dependency graph</h2>
        <div class="panel-heading__actions">
          <span class="panel-heading__meta">{{ graph.nodes.length }} nodes · {{ graph.edges.length }} edges</span>
          <FullscreenButton :active="graphFullscreen" label="Dependency graph" @toggle="toggleGraphFullscreen" />
        </div>
      </div>
      <DependencyGraph v-if="graph.nodes.length" :nodes="graph.nodes" :edges="graph.edges" />
      <div v-else class="empty-state-box">
        {{ graphLoading ? 'Laying out the dependency graph…' : 'Graph preview will appear as soon as repository relationships finish loading.' }}
      </div>
    </section>

    <div ref="tabPanelRef" class="workspace-tab-panel">
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
      const levelPaths = pathsByLevel.get(level)
      if (levelPaths) levelPaths.push(path)
      else pathsByLevel.set(level, [path])
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
    let minX = Number.POSITIVE_INFINITY
    let maxX = Number.NEGATIVE_INFINITY
    let minY = Number.POSITIVE_INFINITY
    let maxY = Number.NEGATIVE_INFINITY
    for (const { x, y } of local.values()) {
      minX = Math.min(minX, x)
      maxX = Math.max(maxX, x)
      minY = Math.min(minY, y)
      maxY = Math.max(maxY, y)
    }
    minX -= 90
    maxX += 90
    minY -= 90
    maxY += 90
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
  const fileName = normalized.split('/').pop() ?? normalized
  if (
    normalized.includes('.test.')
    || normalized.includes('.spec.')
    || normalized.includes('/tests/')
    || normalized.includes('/src/test/')
    || fileName.startsWith('test_')
    || fileName.endsWith('_test.py')
    || fileName.endsWith('test.java')
  ) {
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
