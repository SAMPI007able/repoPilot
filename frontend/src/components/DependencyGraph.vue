<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  nodes: Array<{ id: string; label: string; short: string; kind: string; x: string; y: string }>
  edges: Array<{ id: string; source: string; target: string; strength: 'normal' | 'strong' }>
}>()

const nodesById = computed(() =>
  Object.fromEntries(props.nodes.map((node) => [node.id, node])),
)

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
</script>

<template>
  <div class="graph-grid">
    <svg class="graph-grid__edges" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <line
        v-for="edge in renderedEdges"
        :key="edge.id"
        class="graph-edge"
        :class="{ 'graph-edge--strong': edge.strength === 'strong' }"
        :x1="edge.x1"
        :y1="edge.y1"
        :x2="edge.x2"
        :y2="edge.y2"
      />
    </svg>

    <div
      v-for="node in nodes"
      :key="node.id"
      class="graph-node"
      :class="`graph-node--${node.kind}`"
      :style="{ left: node.x, top: node.y }"
    >
      <span class="graph-node__dot">{{ node.short }}</span>
      <small>{{ node.label }}</small>
    </div>

    <div class="graph-legend">
      <span><i class="graph-legend__dot graph-legend__dot--service" />service</span>
      <span><i class="graph-legend__dot graph-legend__dot--module" />module</span>
      <span><i class="graph-legend__dot graph-legend__dot--test" />test</span>
      <span><i class="graph-legend__dot graph-legend__dot--config" />config</span>
    </div>
  </div>
</template>
