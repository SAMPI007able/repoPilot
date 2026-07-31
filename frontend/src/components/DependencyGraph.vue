<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  nodes: Array<{ id: string; label: string; short: string; kind: string; x: string; y: string }>
  edges: Array<{ id: string; source: string; target: string; strength: 'normal' | 'strong' }>
}>()

const nodesById = computed(() =>
  Object.fromEntries(props.nodes.map((node) => [node.id, node])),
)

const activeNodeId = ref<string | null>(null)

const renderedEdges = computed(() =>
  props.edges
    .map((edge) => {
      const source = nodesById.value[edge.source]
      const target = nodesById.value[edge.target]
      if (!source || !target) {
        return null
      }

      return {
        ...edge,
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
      }
    })
    .filter((edge): edge is NonNullable<typeof edge> => edge !== null),
)

const connectionsByNode = computed(() => {
  const connections = Object.fromEntries(props.nodes.map((node) => [node.id, 0]))
  for (const edge of renderedEdges.value) {
    connections[edge.source] = (connections[edge.source] ?? 0) + 1
    connections[edge.target] = (connections[edge.target] ?? 0) + 1
  }
  return connections
})

const connectedNodeIds = computed(() => {
  if (!activeNodeId.value) {
    return new Set<string>()
  }

  const connected = new Set<string>([activeNodeId.value])
  for (const edge of renderedEdges.value) {
    if (edge.source === activeNodeId.value) {
      connected.add(edge.target)
    }
    if (edge.target === activeNodeId.value) {
      connected.add(edge.source)
    }
  }
  return connected
})

const activeNode = computed(() =>
  activeNodeId.value ? nodesById.value[activeNodeId.value] : null,
)

const tooltipStyle = computed(() => {
  if (!activeNode.value) {
    return {}
  }

  const x = Number.parseFloat(activeNode.value.x)
  const y = Number.parseFloat(activeNode.value.y)
  return {
    left: activeNode.value.x,
    top: activeNode.value.y,
    '--tooltip-x': x > 82 ? 'calc(-100% - 1rem)' : '1rem',
    '--tooltip-y': y > 78 ? 'calc(-100% - 1rem)' : '0.5rem',
  }
})

function isConnectedEdge(source: string, target: string) {
  return activeNodeId.value === source || activeNodeId.value === target
}

function connectionLabel(count: number) {
  return `${count} ${count === 1 ? 'connection' : 'connections'}`
}
</script>

<template>
  <div class="graph-grid">
    <svg class="graph-grid__edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <line
        v-for="edge in renderedEdges"
        :key="edge.id"
        class="graph-edge"
        :class="{
          'graph-edge--strong': edge.strength === 'strong',
          'graph-edge--connected': activeNodeId && isConnectedEdge(edge.source, edge.target),
          'graph-edge--muted': activeNodeId && !isConnectedEdge(edge.source, edge.target),
        }"
        :x1="edge.x1"
        :y1="edge.y1"
        :x2="edge.x2"
        :y2="edge.y2"
      />
    </svg>

    <button
      v-for="node in nodes"
      :key="node.id"
      type="button"
      class="graph-node"
      :class="[
        `graph-node--${node.kind}`,
        {
          'graph-node--selected': activeNodeId === node.id,
          'graph-node--muted': activeNodeId && !connectedNodeIds.has(node.id),
        },
      ]"
      :style="{ left: node.x, top: node.y }"
      :aria-label="`${node.label}, ${connectionLabel(connectionsByNode[node.id] ?? 0)}`"
      @mouseenter="activeNodeId = node.id"
      @mouseleave="activeNodeId = null"
      @focus="activeNodeId = node.id"
      @blur="activeNodeId = null"
    >
      <span class="graph-node__dot">{{ node.short }}</span>
      <small>{{ node.label }}</small>
    </button>

    <div
      v-if="activeNode"
      class="graph-tooltip"
      :style="tooltipStyle"
      role="status"
    >
      <strong>{{ activeNode.label }}</strong>
      <span>·</span>
      <span>{{ connectionLabel(connectionsByNode[activeNode.id] ?? 0) }}</span>
    </div>

    <div class="graph-legend">
      <span><i class="graph-legend__dot graph-legend__dot--service" />service</span>
      <span><i class="graph-legend__dot graph-legend__dot--module" />module</span>
      <span><i class="graph-legend__dot graph-legend__dot--test" />test</span>
      <span><i class="graph-legend__dot graph-legend__dot--config" />config</span>
    </div>
  </div>
</template>
