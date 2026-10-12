<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Landing from '../components/Landing.vue'
import SignInModal from '../components/SignInModal.vue'
import Sidebar from '../components/Sidebar.vue'
import UserMenu from '../components/UserMenu.vue'
import WorkspaceView from '../components/WorkspaceView.vue'
import RepositoriesPage from './RepositoriesPage.vue'
import { useWorkspaceStore } from '../stores/workspace'
import { useAuthStore } from '../stores/auth'
import { usePreviewStore } from '../stores/preview'
import type { SignInMethod } from '../stores/auth'

const workspaceStore = useWorkspaceStore()
const auth = useAuthStore()
const previewStore = usePreviewStore()
const route = useRoute()
const router = useRouter()
const signInOpen = ref(false)
const repositoriesPage = computed(() => route.name === 'repositories')
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

async function showRepositories() {
  if (!auth.authenticated) {
    signInOpen.value = true
    return
  }
  workspaceStore.startNewWorkspace()
  await router.push({ name: 'repositories' })
}

async function startNewWorkspace() {
  workspaceStore.startNewWorkspace()
  await router.push({ name: 'home' })
}

async function selectWorkspace(id: string) {
  await router.push({ name: 'home' })
  await workspaceStore.selectWorkspace(id)
}

async function importRepository(repository: import('../types/api').ProviderRepository, branch?: string) {
  await router.push({ name: 'home' })
  await workspaceStore.importProviderRepository(repository, branch)
}
</script>

<template>
  <div class="app-shell">
    <UserMenu
      :user="auth.user"
      :loading="auth.loading"
      @sign-in="signInOpen = true"
      @sign-out="signOut"
    />
    <div v-if="auth.user && !auth.user.emailVerified" class="verification-banner">
      Verify your email before creating workspaces, running AI requests, or starting previews.
    </div>
    <Sidebar
      v-if="auth.authenticated"
      :workspaces="workspaceStore.workspaces"
      :active-id="workspaceStore.activeId"
      :loading="workspaceStore.loadingList"
      :removing-ids="workspaceStore.removingIds"
      :active-section="repositoriesPage ? 'repositories' : 'workspace'"
      @select="selectWorkspace"
      @remove="workspaceStore.removeWorkspace"
      @new="startNewWorkspace"
      @repositories="showRepositories"
    />

    <main class="app-main scrollbar-thin">
      <RepositoriesPage
        v-if="repositoriesPage"
        :busy="workspaceStore.busy"
        @back="startNewWorkspace"
        @import="importRepository"
      />

      <WorkspaceView
        v-else-if="workspaceStore.activeWorkspace"
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
        @create="requestWorkspaceBuild"
        @browse-repositories="showRepositories"
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
