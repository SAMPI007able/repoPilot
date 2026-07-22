<script setup lang="ts">
import type { WorkspaceListItem } from '../stores/workspace'
import { GitBranch } from '@lucide/vue'
defineProps<{
  workspaces: WorkspaceListItem[]
  activeId: string | null
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'new'): void
}>()

const statusMap = {
  pending: { label: 'Pending', className: 'status-pill status-pill--pending' },
  indexing: { label: 'Indexing', className: 'status-pill status-pill--indexing' },
  graphing: { label: 'Graphing', className: 'status-pill status-pill--graphing' },
  analyzing: { label: 'Analyzing', className: 'status-pill status-pill--analyzing' },
  ready: { label: 'Ready', className: 'status-pill status-pill--ready' },
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand-block">
      <div class="brand-block__icon">
        <span class="glyph glyph--brand">TF</span>
      </div>
      <div>
        <div class="brand-block__title">TestForge AI</div>
        <div class="brand-block__subtitle">Understand. Answer. Test.</div>
      </div>
    </div>

    <div class="sidebar__actions">
      <button class="btn btn-ghost btn-full" type="button" @click="emit('new')">
        <span class="glyph glyph--button">+</span>
        <span>New workspace</span>
      </button>
    </div>

    <div class="sidebar__section">
      <div class="section-title">Workspaces</div>
    </div>

    <div class="sidebar__list scrollbar-thin">
      <div v-if="loading" class="sidebar__empty">Loading...</div>
      <div v-else-if="workspaces.length === 0" class="sidebar__empty">No workspaces yet.</div>
      <button
        v-for="workspace in workspaces"
        :key="workspace.id"
        class="workspace-row"
        :class="{ 'workspace-row--active': workspace.id === activeId }"
        type="button"
        @click="emit('select', workspace.id)"
      >
        <div class="workspace-row__title"><GitBranch class="h-3.5 w-3.5 shrink-0 text-slate-500" />{{ workspace.repoName }}</div>
        <div class="workspace-row__url">{{ workspace.repoUrl }}</div>
        <span :class="statusMap[workspace.status].className">
          <span class="status-pill__dot" />
          {{ statusMap[workspace.status].label }}
        </span>
      </button>
    </div>
  </aside>
</template>
