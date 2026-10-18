<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { MailCheck, RefreshCw } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import Landing from '../components/Landing.vue'
import Sidebar from '../components/Sidebar.vue'
import UserMenu from '../components/UserMenu.vue'
import { useWorkspaceStore } from '../stores/workspace'
import { useAuthStore } from '../stores/auth'
import type { SignInMethod } from '../stores/auth'
import { extractAPIError, resendVerificationEmail } from '../services/api'

const workspaceStore = useWorkspaceStore()
const auth = useAuthStore()
const SignInModal = defineAsyncComponent(() => import('../components/SignInModal.vue'))
const WorkspaceView = defineAsyncComponent(() => import('../components/WorkspaceView.vue'))
const RepositoriesPage = defineAsyncComponent(() => import('./RepositoriesPage.vue'))
const route = useRoute()
const router = useRouter()
const signInOpen = ref(false)
const verificationError = ref<string | null>(null)
const verificationMessage = ref<string | null>(null)
const resendBusy = ref(false)
const resendCooldown = ref(0)
const repositoriesPage = computed(() => route.name === 'repositories')
const verificationRequired = computed(() => Boolean(auth.user && !auth.user.emailVerified))
const pendingBuildKey = 'testforge.pendingWorkspaceBuild'
let resendCooldownTimer: number | null = null

function refreshWorkspacesIfStale() {
  if (auth.authenticated && !verificationRequired.value && document.visibilityState === 'visible') {
    void workspaceStore.refreshWorkspacesIfStale()
  }
}

watch([() => auth.authenticated, () => auth.user?.emailVerified], async ([authenticated, emailVerified]) => {
  if (!authenticated) {
    workspaceStore.clearSession()
    return
  }
  if (!emailVerified) return

  void workspaceStore.loadWorkspaces()
  const pendingRepositoryUrl = window.sessionStorage.getItem(pendingBuildKey)
  if (pendingRepositoryUrl) {
    window.sessionStorage.removeItem(pendingBuildKey)
    workspaceStore.setRepositoryUrl(pendingRepositoryUrl)
    await workspaceStore.createWorkspace()
  }
}, { immediate: true })

onMounted(() => {
  window.addEventListener('focus', refreshWorkspacesIfStale)
  document.addEventListener('visibilitychange', refreshWorkspacesIfStale)
})

onUnmounted(() => {
  window.removeEventListener('focus', refreshWorkspacesIfStale)
  document.removeEventListener('visibilitychange', refreshWorkspacesIfStale)
  if (resendCooldownTimer !== null) window.clearInterval(resendCooldownTimer)
})

async function signOut() {
  workspaceStore.clearSession()
  const { usePreviewStore } = await import('../stores/preview')
  usePreviewStore().clearSession()
  await auth.signOut()
}

async function requestWorkspaceBuild() {
  if (verificationRequired.value) return
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
    if (auth.user?.emailVerified) {
      window.sessionStorage.removeItem(pendingBuildKey)
      if (workspaceStore.repositoryUrl.trim()) await workspaceStore.createWorkspace()
    } else if (workspaceStore.repositoryUrl.trim()) {
      window.sessionStorage.setItem(pendingBuildKey, workspaceStore.repositoryUrl.trim())
    }
  }
}

async function showRepositories() {
  if (verificationRequired.value) return
  if (!auth.authenticated) {
    signInOpen.value = true
    return
  }
  workspaceStore.startNewWorkspace()
  await router.push({ name: 'repositories' })
}

async function startNewWorkspace() {
  if (verificationRequired.value) return
  workspaceStore.startNewWorkspace()
  await router.push({ name: 'home' })
}

async function selectWorkspace(id: string) {
  if (verificationRequired.value) return
  await router.push({ name: 'home' })
  await workspaceStore.selectWorkspace(id)
}

async function importRepository(repository: import('../types/api').ProviderRepository, branch?: string) {
  if (verificationRequired.value) return
  await router.push({ name: 'home' })
  await workspaceStore.importProviderRepository(repository, branch)
}

async function refreshVerification() {
  verificationError.value = null
  verificationMessage.value = null
  try {
    const refreshed = await auth.refreshUser()
    if (!refreshed) return
    if (!auth.user?.emailVerified) {
      verificationError.value = 'Verification is not visible yet. Finish the email verification, then try again.'
    }
  } catch {
    verificationError.value = auth.error || 'Unable to refresh your verification status. Please try again.'
  }
}

function startResendCooldown(seconds: number) {
  resendCooldown.value = Math.max(1, seconds)
  if (resendCooldownTimer !== null) window.clearInterval(resendCooldownTimer)
  resendCooldownTimer = window.setInterval(() => {
    resendCooldown.value = Math.max(0, resendCooldown.value - 1)
    if (resendCooldown.value === 0 && resendCooldownTimer !== null) {
      window.clearInterval(resendCooldownTimer)
      resendCooldownTimer = null
    }
  }, 1000)
}

async function resendVerification() {
  if (resendBusy.value || resendCooldown.value > 0) return
  verificationError.value = null
  verificationMessage.value = null
  resendBusy.value = true
  try {
    const result = await resendVerificationEmail()
    verificationMessage.value = result.message
    startResendCooldown(result.retryAfterSeconds)
  } catch (error) {
    verificationError.value = extractAPIError(error, 'Unable to resend the verification email.').message
  } finally {
    resendBusy.value = false
  }
}

watch(verificationRequired, (required) => {
  if (!required) {
    verificationError.value = null
    verificationMessage.value = null
  }
})
</script>

<template>
  <div class="app-shell">
    <UserMenu
      :user="auth.user"
      :loading="auth.loading"
      :inert="verificationRequired"
      :aria-hidden="verificationRequired"
      @sign-in="signInOpen = true"
      @sign-out="signOut"
    />
    <Sidebar
      v-if="auth.authenticated"
      :inert="verificationRequired"
      :aria-hidden="verificationRequired"
      :workspaces="workspaceStore.workspaces"
      :active-id="workspaceStore.activeId"
      :loading="workspaceStore.loadingList"
      :removing-ids="workspaceStore.removingIds"
      :active-section="repositoriesPage ? 'repositories' : 'workspace'"
      @select="selectWorkspace"
      @remove="workspaceStore.removeWorkspace"
      @refresh="workspaceStore.loadWorkspaces()"
      @new="startNewWorkspace"
      @repositories="showRepositories"
    />

    <main class="app-main scrollbar-thin" :inert="verificationRequired" :aria-hidden="verificationRequired">
      <Landing
        v-if="verificationRequired"
        :repo-url="workspaceStore.repositoryUrl"
        :docs="workspaceStore.projectDocuments"
        :busy="false"
        :error="null"
        @update:repo-url="workspaceStore.setRepositoryUrl"
        @update:docs="workspaceStore.setProjectDocuments"
        @create="requestWorkspaceBuild"
        @browse-repositories="showRepositories"
      />

      <RepositoriesPage
        v-else-if="repositoriesPage"
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
        :branch-options="workspaceStore.branchesByWorkspace[workspaceStore.activeWorkspace.id] ?? []"
        :loading-branches="workspaceStore.loadingBranchIds.includes(workspaceStore.activeWorkspace.id)"
        :reindexing="workspaceStore.reindexingIds.includes(workspaceStore.activeWorkspace.id)"
        @load-branches="workspaceStore.loadWorkspaceBranches(workspaceStore.activeWorkspace.id)"
        @reindex="(branch) => workspaceStore.reindexWorkspace(workspaceStore.activeWorkspace!.id, branch)"
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
    <div
      v-if="verificationRequired"
      class="verification-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="verification-title"
      aria-describedby="verification-description"
    >
      <section class="verification-card">
        <div class="verification-card__icon" aria-hidden="true"><MailCheck /></div>
        <p class="verification-card__eyebrow">One step remaining</p>
        <h1 id="verification-title">Verify your email to continue</h1>
        <p id="verification-description">
          Check <strong>{{ auth.user?.primaryEmail }}</strong> for the verification email. Workspaces, AI requests,
          repository connections, and previews stay paused until your address is verified.
        </p>
        <div class="verification-card__actions">
          <button
            class="verification-card__refresh"
            type="button"
            :disabled="auth.loading || resendBusy"
            @click="refreshVerification"
          >
            <RefreshCw :class="{ spin: auth.loading }" aria-hidden="true" />
            {{ auth.loading ? 'Checking verification…' : 'I’ve verified — refresh' }}
          </button>
          <button
            class="verification-card__refresh verification-card__resend"
            type="button"
            :disabled="resendBusy || auth.loading || resendCooldown > 0"
            @click="resendVerification"
          >
            <MailCheck aria-hidden="true" />
            {{
              resendBusy
                ? 'Sending…'
                : resendCooldown > 0
                  ? `Resend available in ${resendCooldown}s`
                  : 'Resend verification email'
            }}
          </button>
        </div>
        <p v-if="verificationMessage" class="verification-card__success" role="status">
          {{ verificationMessage }}
        </p>
        <p v-if="verificationError" class="verification-card__error" role="alert">{{ verificationError }}</p>
      </section>
    </div>
    <SignInModal
      v-if="signInOpen"
      :busy="auth.loading"
      :error="auth.error"
      @close="signInOpen = false"
      @sign-in="signIn"
    />
  </div>
</template>
