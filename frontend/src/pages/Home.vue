<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import Landing from '../components/Landing.vue'
import Sidebar from '../components/Sidebar.vue'
import WorkspaceView from '../components/WorkspaceView.vue'
import { useWorkspaceStore } from '../stores/workspace'

const workspaceStore = useWorkspaceStore()

let workspaceRefreshTimer: number | null = null

onMounted(() => {
  workspaceStore.loadWorkspaces()
  workspaceRefreshTimer = window.setInterval(() => {
    workspaceStore.loadWorkspaces(false)
  }, 2000)
})

onUnmounted(() => {
  if (workspaceRefreshTimer !== null) {
    window.clearInterval(workspaceRefreshTimer)
  }
})
</script>

<template>
  <div class="app-shell">
    <Sidebar
      :workspaces="workspaceStore.workspaces"
      :active-id="workspaceStore.activeId"
      :loading="workspaceStore.loadingList"
      :removing-ids="workspaceStore.removingIds"
      @select="workspaceStore.selectWorkspace"
      @remove="workspaceStore.removeWorkspace"
      @new="workspaceStore.startNewWorkspace"
    />

    <main class="app-main scrollbar-thin">
      <WorkspaceView
        v-if="workspaceStore.activeWorkspace"
        :workspace="workspaceStore.activeWorkspace"
        :metadata="workspaceStore.metadata"
        :framework-label="workspaceStore.frameworkLabel"
        :stages="workspaceStore.pipelineStages"
        :target-options="workspaceStore.targetOptions"
      />

      <Landing
        v-else
        :repo-url="workspaceStore.repositoryUrl"
        :docs="workspaceStore.projectDocuments"
        :busy="workspaceStore.busy"
        :error="workspaceStore.error"
        @update:repo-url="workspaceStore.setRepositoryUrl"
        @update:docs="workspaceStore.setProjectDocuments"
        @create="workspaceStore.createWorkspace"
      />
    </main>
  </div>
</template>
