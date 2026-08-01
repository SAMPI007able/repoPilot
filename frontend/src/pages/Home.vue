<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import Landing from '../components/Landing.vue'
import SignInModal from '../components/SignInModal.vue'
import Sidebar from '../components/Sidebar.vue'
import WorkspaceView from '../components/WorkspaceView.vue'
import { useWorkspaceStore } from '../stores/workspace'
import { useAuthStore } from '../stores/auth'
import { usePreviewStore } from '../stores/preview'
import type { SignInMethod } from '../stores/auth'

const workspaceStore = useWorkspaceStore()
const auth = useAuthStore()
const previewStore = usePreviewStore()
const signInOpen = ref(false)
const pendingBuildKey = 'testforge.pendingWorkspaceBuild'

let workspaceRefreshTimer: number | null = null

function startWorkspaceRefresh() {
  if (workspaceRefreshTimer !== null) return
  void workspaceStore.loadWorkspaces()
  workspaceRefreshTimer = window.setInterval(() => {
    void workspaceStore.loadWorkspaces(false)
  }, 2000)
}

function stopWorkspaceRefresh() {
  if (workspaceRefreshTimer === null) return
  window.clearInterval(workspaceRefreshTimer)
  workspaceRefreshTimer = null
}

watch(() => auth.authenticated, async (authenticated) => {
  if (!authenticated) {
    stopWorkspaceRefresh()
    workspaceStore.clearSession()
    return
  }

  startWorkspaceRefresh()
  const pendingRepositoryUrl = window.sessionStorage.getItem(pendingBuildKey)
  if (pendingRepositoryUrl) {
    window.sessionStorage.removeItem(pendingBuildKey)
    workspaceStore.setRepositoryUrl(pendingRepositoryUrl)
    await workspaceStore.createWorkspace()
  }
}, { immediate: true })

onUnmounted(() => {
  stopWorkspaceRefresh()
})

async function signOut() {
  workspaceStore.clearSession()
  previewStore.clearSession()
  await auth.signOut()
}

async function requestWorkspaceBuild() {
  if (!workspaceStore.repositoryUrl.trim()) {
    await workspaceStore.createWorkspace()
    return
  }
  if (!auth.authenticated) {
    signInOpen.value = true
    return
  }
  await workspaceStore.createWorkspace()
}

async function signIn(method: SignInMethod) {
  const canResumeBuild = workspaceStore.projectDocuments.length === 0 && Boolean(workspaceStore.repositoryUrl.trim())
  if (canResumeBuild && auth.redirectSignIn) {
    window.sessionStorage.setItem(pendingBuildKey, workspaceStore.repositoryUrl.trim())
  }
  await auth.signIn(method)
  if (auth.authenticated) {
    signInOpen.value = false
    window.sessionStorage.removeItem(pendingBuildKey)
    if (workspaceStore.repositoryUrl.trim()) await workspaceStore.createWorkspace()
  }
}
</script>

<template>
  <div class="app-shell">
    <button class="session-button" :title="auth.user?.primaryEmail" @click="auth.authenticated ? signOut() : (signInOpen = true)">
      {{ auth.authenticated ? 'Sign out' : 'Sign in' }}
    </button>
    <div v-if="auth.user && !auth.user.emailVerified" class="verification-banner">
      Verify your email before creating workspaces, running AI requests, or starting previews.
    </div>
    <Sidebar
      v-if="auth.authenticated"
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
        :authenticated="auth.authenticated"
        @update:repo-url="workspaceStore.setRepositoryUrl"
        @update:docs="workspaceStore.setProjectDocuments"
        @create="requestWorkspaceBuild"
      />
    </main>
    <SignInModal
      v-if="signInOpen"
      :busy="auth.loading"
      :error="auth.error"
      @close="signInOpen = false"
      @sign-in="signIn"
    />
  </div>
</template>
