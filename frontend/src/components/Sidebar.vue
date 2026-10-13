<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { WorkspaceListItem } from '../stores/workspace'
import { ChevronLeft, ChevronRight, FolderGit2, GitBranch, LoaderCircle, RefreshCw, Trash2 } from '@lucide/vue'

const SIDEBAR_STORAGE_KEY = 'testforge.sidebar.collapsed'

defineProps<{
  workspaces: WorkspaceListItem[]
  activeId: string | null
  loading: boolean
  removingIds: string[]
  activeSection?: 'workspace' | 'repositories'
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'remove', id: string): void
  (e: 'new'): void
  (e: 'repositories'): void
  (e: 'refresh'): void
}>()

const collapsed = ref(false)

onMounted(() => {
  collapsed.value = window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
})

watch(collapsed, (value) => {
  window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(value))
})

const statusMap = {
  pending: { label: 'Pending', className: 'status-pill status-pill--pending' },
  building: { label: 'Building', className: 'status-pill status-pill--indexing' },
  ready: { label: 'Ready', className: 'status-pill status-pill--ready' },
  failed: { label: 'Failed', className: 'status-pill status-pill--failed' },
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': collapsed }">
    <button
      class="sidebar__toggle"
      type="button"
      :aria-label="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      :aria-expanded="!collapsed"
      :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      @click="collapsed = !collapsed"
    >
      <ChevronRight v-if="collapsed" aria-hidden="true" />
      <ChevronLeft v-else aria-hidden="true" />
    </button>

    <div class="brand-block">
      <div class="brand-block__icon">
        <span class="glyph glyph--brand">RP</span>
      </div>
      <div class="brand-block__copy">
        <div class="brand-block__title">RepoPilot</div>
        <div class="brand-block__subtitle">Understand, run and validate any codebase</div>
      </div>
    </div>

    <div class="sidebar__actions">
      <button
        class="btn btn-ghost btn-full"
        type="button"
        aria-label="New workspace"
        title="New workspace"
        @click="emit('new')"
      >
        <span class="glyph glyph--button">+</span>
        <span class="sidebar__action-label">New workspace</span>
      </button>
      <button
        class="btn btn-ghost btn-full sidebar__repository-link"
        :class="{ 'sidebar__repository-link--active': activeSection === 'repositories' }"
        type="button"
        aria-label="Your repositories"
        title="Your repositories"
        @click="emit('repositories')"
      >
        <FolderGit2 aria-hidden="true" />
        <span class="sidebar__action-label">Your repositories</span>
        <ChevronRight class="sidebar__action-arrow" aria-hidden="true" />
      </button>
    </div>

    <div class="sidebar__section">
      <div class="section-title">Workspaces</div>
      <button
        class="sidebar__refresh"
        type="button"
        aria-label="Refresh workspaces"
        title="Refresh workspaces"
        :disabled="loading"
        @click="emit('refresh')"
      >
        <RefreshCw :class="{ 'sidebar__refresh-icon--spinning': loading }" aria-hidden="true" />
      </button>
    </div>

    <div class="sidebar__list scrollbar-thin">
      <div v-if="loading" class="sidebar__empty">Loading...</div>
      <div v-else-if="workspaces.length === 0" class="sidebar__empty">No workspaces yet.</div>
      <div
        v-for="workspace in workspaces"
        :key="workspace.id"
        class="workspace-row-shell"
      >
        <button
          class="workspace-row"
          :class="{ 'workspace-row--active': workspace.id === activeId }"
          type="button"
          :title="collapsed ? `${workspace.repoName} · ${statusMap[workspace.status].label}` : undefined"
          :aria-label="collapsed ? `${workspace.repoName}, ${statusMap[workspace.status].label}` : undefined"
          @click="emit('select', workspace.id)"
        >
          <div class="workspace-row__title">
            <GitBranch class="workspace-row__icon h-3.5 w-3.5 shrink-0 text-slate-500" />
            <span class="workspace-row__name">{{ workspace.repoName }}</span>
          </div>
          <div class="workspace-row__url">{{ workspace.repoUrl }}</div>
          <span :class="statusMap[workspace.status].className">
            <span class="status-pill__dot" />
            <span class="status-pill__label">{{ statusMap[workspace.status].label }}</span>
          </span>
        </button>
        <button
          class="workspace-row__remove"
          type="button"
          :disabled="workspace.status === 'pending' || workspace.status === 'building' || removingIds.includes(workspace.id)"
          :aria-label="`Remove ${workspace.repoName}`"
          :title="workspace.status === 'pending' || workspace.status === 'building' ? 'Available after the build finishes' : `Remove ${workspace.repoName}`"
          @click="emit('remove', workspace.id)"
        >
          <LoaderCircle
            v-if="removingIds.includes(workspace.id)"
            class="workspace-row__remove-spinner"
            aria-hidden="true"
          />
          <Trash2 v-else aria-hidden="true" />
        </button>
      </div>
    </div>
  </aside>
</template>
