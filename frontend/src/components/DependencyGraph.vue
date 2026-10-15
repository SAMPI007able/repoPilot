<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'

type GraphNode = { id: string; label: string; short: string; kind: string; x: number; y: number }
type GraphEdge = { id: string; source: string; target: string; strength: 'normal' | 'strong' }

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
}>()

const svgElement = ref<SVGSVGElement | null>(null)
const searchQuery = ref('')
const kindFilter = ref('all')
const activeNodeId = ref<string | null>(null)
const viewBox = ref({ x: 0, y: 0, width: 1000, height: 600 })
let dragState: { pointerId: number; x: number; y: number } | null = null

const filteredNodes = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return props.nodes.filter((node) =>
    (kindFilter.value === 'all' || node.kind === kindFilter.value) &&
    (!query || node.id.toLowerCase().includes(query) || node.label.toLowerCase().includes(query)),
  )
})

const filteredNodeIds = computed(() => new Set(filteredNodes.value.map((node) => node.id)))
const nodesById = computed(() => new Map(props.nodes.map((node) => [node.id, node])))
const renderedEdges = computed(() => props.edges.filter((edge) =>
  filteredNodeIds.value.has(edge.source) && filteredNodeIds.value.has(edge.target),
))
const connectedNodeIds = computed(() => {
  if (!activeNodeId.value) return new Set<string>()
  const connected = new Set<string>([activeNodeId.value])
  for (const edge of renderedEdges.value) {
    if (edge.source === activeNodeId.value) connected.add(edge.target)
    if (edge.target === activeNodeId.value) connected.add(edge.source)
  }
  return connected
})
const connectionsByNode = computed(() => {
  const result = new Map<string, number>()
  for (const edge of renderedEdges.value) {
    result.set(edge.source, (result.get(edge.source) ?? 0) + 1)
    result.set(edge.target, (result.get(edge.target) ?? 0) + 1)
  }
  return result
})
const activeNode = computed(() => activeNodeId.value ? nodesById.value.get(activeNodeId.value) : null)
const kindOptions = computed(() => ['all', ...new Set(props.nodes.map((node) => node.kind))])
const viewBoxValue = computed(() => {
  const { x, y, width, height } = viewBox.value
  return `${x} ${y} ${width} ${height}`
})

function fitGraph() {
  const nodes = filteredNodes.value
  if (!nodes.length) return
  const padding = 100
  const minX = Math.min(...nodes.map((node) => node.x)) - padding
  const maxX = Math.max(...nodes.map((node) => node.x)) + padding
  const minY = Math.min(...nodes.map((node) => node.y)) - padding
  const maxY = Math.max(...nodes.map((node) => node.y)) + padding
  viewBox.value = {
    x: minX,
    y: minY,
    width: Math.max(maxX - minX, 320),
    height: Math.max(maxY - minY, 220),
  }
}

function zoom(factor: number, clientX?: number, clientY?: number) {
  const current = viewBox.value
  const rect = svgElement.value?.getBoundingClientRect()
  const ratioX = rect && clientX !== undefined ? (clientX - rect.left) / rect.width : 0.5
  const ratioY = rect && clientY !== undefined ? (clientY - rect.top) / rect.height : 0.5
  const width = Math.min(Math.max(current.width * factor, 180), 12000)
  const height = Math.min(Math.max(current.height * factor, 120), 8000)
  viewBox.value = {
    x: current.x + (current.width - width) * ratioX,
    y: current.y + (current.height - height) * ratioY,
    width,
    height,
  }
}

function handleWheel(event: WheelEvent) {
  zoom(event.deltaY > 0 ? 1.12 : 0.88, event.clientX, event.clientY)
}

function startPan(event: PointerEvent) {
  if ((event.target as Element).closest('.graph-node')) return
  dragState = { pointerId: event.pointerId, x: event.clientX, y: event.clientY }
  svgElement.value?.setPointerCapture(event.pointerId)
}

function pan(event: PointerEvent) {
  if (!dragState || dragState.pointerId !== event.pointerId || !svgElement.value) return
  const rect = svgElement.value.getBoundingClientRect()
  const deltaX = ((event.clientX - dragState.x) / rect.width) * viewBox.value.width
  const deltaY = ((event.clientY - dragState.y) / rect.height) * viewBox.value.height
  viewBox.value = { ...viewBox.value, x: viewBox.value.x - deltaX, y: viewBox.value.y - deltaY }
  dragState = { ...dragState, x: event.clientX, y: event.clientY }
}

function stopPan(event: PointerEvent) {
  if (dragState?.pointerId === event.pointerId) dragState = null
}

function connectionLabel(count: number) {
  return `${count} ${count === 1 ? 'connection' : 'connections'}`
}

watch([filteredNodes, renderedEdges], () => {
  if (activeNodeId.value && !filteredNodeIds.value.has(activeNodeId.value)) activeNodeId.value = null
  void nextTick(fitGraph)
})
onMounted(fitGraph)
</script>

<template>
  <div class="graph-grid">
    <div class="graph-controls">
      <input v-model="searchQuery" type="search" placeholder="Filter by path…" aria-label="Filter graph nodes by path">
      <select v-model="kindFilter" aria-label="Filter graph nodes by type">
        <option v-for="kind in kindOptions" :key="kind" :value="kind">
          {{ kind === 'all' ? 'All types' : kind }}
        </option>
      </select>
      <span>{{ filteredNodes.length }}/{{ nodes.length }} nodes</span>
      <button type="button" aria-label="Zoom in" @click="zoom(0.8)">+</button>
      <button type="button" aria-label="Zoom out" @click="zoom(1.25)">−</button>
      <button type="button" @click="fitGraph">Fit</button>
    </div>

    <svg
      ref="svgElement"
      class="graph-canvas"
      :viewBox="viewBoxValue"
      role="img"
      :aria-label="`Dependency graph with ${filteredNodes.length} visible nodes and ${renderedEdges.length} visible edges`"
      @wheel.prevent="handleWheel"
      @pointerdown="startPan"
      @pointermove="pan"
      @pointerup="stopPan"
      @pointercancel="stopPan"
    >
      <defs>
        <marker id="graph-arrow" viewBox="0 0 10 10" refX="18" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" />
        </marker>
      </defs>
      <line
        v-for="edge in renderedEdges"
        :key="edge.id"
        class="graph-edge"
        :class="{
          'graph-edge--strong': edge.strength === 'strong',
          'graph-edge--connected': activeNodeId && (edge.source === activeNodeId || edge.target === activeNodeId),
          'graph-edge--muted': activeNodeId && edge.source !== activeNodeId && edge.target !== activeNodeId,
        }"
        :x1="nodesById.get(edge.source)?.x"
        :y1="nodesById.get(edge.source)?.y"
        :x2="nodesById.get(edge.target)?.x"
        :y2="nodesById.get(edge.target)?.y"
        marker-end="url(#graph-arrow)"
      />
      <g
        v-for="node in filteredNodes"
        :key="node.id"
        class="graph-node"
        :class="[
          `graph-node--${node.kind}`,
          {
            'graph-node--selected': activeNodeId === node.id,
            'graph-node--muted': activeNodeId && !connectedNodeIds.has(node.id),
          },
        ]"
        :transform="`translate(${node.x} ${node.y})`"
        role="button"
        tabindex="0"
        :aria-label="`${node.id}, ${connectionLabel(connectionsByNode.get(node.id) ?? 0)}`"
        @mouseenter="activeNodeId = node.id"
        @mouseleave="activeNodeId = null"
        @focus="activeNodeId = node.id"
        @blur="activeNodeId = null"
      >
        <circle r="18" />
        <text class="graph-node__short" text-anchor="middle" dominant-baseline="central">{{ node.short }}</text>
        <text class="graph-node__label" text-anchor="middle" y="32">{{ node.label }}</text>
        <title>{{ node.id }} · {{ connectionLabel(connectionsByNode.get(node.id) ?? 0) }}</title>
      </g>
    </svg>

    <div v-if="filteredNodes.length === 0" class="graph-empty">No nodes match the current filters.</div>
    <div class="graph-legend">
      <span><i class="graph-legend__dot graph-legend__dot--service" />service</span>
      <span><i class="graph-legend__dot graph-legend__dot--module" />module</span>
      <span><i class="graph-legend__dot graph-legend__dot--test" />test</span>
      <span><i class="graph-legend__dot graph-legend__dot--config" />config</span>
    </div>
    <div v-if="activeNode" class="graph-tooltip" role="status">
      <strong>{{ activeNode.id }}</strong>
      <span>· {{ connectionLabel(connectionsByNode.get(activeNode.id) ?? 0) }}</span>
    </div>
  </div>
</template>
