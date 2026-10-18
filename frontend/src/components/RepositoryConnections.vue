<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Archive,
  ArrowRight,
  Check,
  GitBranch,
  Globe2,
  LoaderCircle,
  LockKeyhole,
  Plus,
  RefreshCw,
  Search,
  Star,
  Unplug,
  Upload,
  GitFork,
  Boxes,
  FolderGit2
} from '@lucide/vue'

import {
  connectProvider,
  disconnectProvider,
  listProviderBranches,
  listProviderConnections,
  listProviderRepositories,
} from '../services/api'
import type { ProviderConnection, ProviderRepository, SourceControlProvider } from '../types/api'
import { useDialogStore } from '../stores/dialog'

defineProps<{ busy: boolean }>()
const emit = defineEmits<{
  import: [repository: ProviderRepository, branch?: string]
}>()

const connections = ref<ProviderConnection[]>([])
const repositories = ref<ProviderRepository[]>([])
const loadingConnections = ref(true)
const loadingRepositories = ref(false)
const pendingProvider = ref<SourceControlProvider | null>(null)
const activeProvider = ref<SourceControlProvider | null>(null)
const filter = ref('')
const error = ref<string | null>(null)
const selectedZip = ref<File | null>(null)
const branchesByRepository = ref<Record<string, string[]>>({})
const selectedBranches = ref<Record<string, string>>({})
const loadingBranchIds = ref<Set<string>>(new Set())
const branchErrors = ref<Record<string, string>>({})
const visibleLimit = ref(50)

const providerMeta: Record<SourceControlProvider, {
  icon: typeof GitBranch
  description: string
}> = {
  github: { icon: FolderGit2, description: 'Connect to index any public or private repository you have access to.' },
  gitlab: { icon: GitFork, description: 'Pull repositories from GitLab.com or your self-hosted GitLab instance.' },
  bitbucket: { icon: Boxes, description: 'Connect Bitbucket Cloud to browse your team repositories.' },
}

const connectedProviders = computed(() => connections.value.filter((connection) => connection.connected))
const activeConnection = computed(() => connections.value.find((item) => item.provider === activeProvider.value) ?? null)
const filteredRepositories = computed(() => {
  const query = filter.value.trim().toLocaleLowerCase()
  if (!query) return repositories.value
  return repositories.value.filter((repository) =>
    `${repository.fullName} ${repository.description ?? ''} ${repository.defaultBranch}`.toLocaleLowerCase().includes(query),
  )
})
const visibleRepositories = computed(() => filteredRepositories.value.slice(0, visibleLimit.value))
watch([filter, activeProvider], () => { visibleLimit.value = 50 })

async function loadConnections() {
  loadingConnections.value = true
  error.value = null
  try {
    connections.value = await listProviderConnections()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Unable to load repository connections.'
  } finally {
    loadingConnections.value = false
  }
}

async function selectProvider(provider: SourceControlProvider, force = false) {
  if (!force && activeProvider.value === provider && repositories.value.length) return
  activeProvider.value = provider
  filter.value = ''
  repositories.value = []
  branchesByRepository.value = {}
  selectedBranches.value = {}
  branchErrors.value = {}
  loadingRepositories.value = true
  error.value = null
  try {
    repositories.value = (await listProviderRepositories(provider, force))
      .sort((left, right) => (right.updatedAt || '').localeCompare(left.updatedAt || ''))
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : `Unable to load ${provider} repositories.`
  } finally {
    loadingRepositories.value = false
  }
}

async function loadBranches(repository: ProviderRepository) {
  if (branchesByRepository.value[repository.id] || loadingBranchIds.value.has(repository.id)) return
  loadingBranchIds.value = new Set(loadingBranchIds.value).add(repository.id)
  const nextErrors = { ...branchErrors.value }
  delete nextErrors[repository.id]
  branchErrors.value = nextErrors
  try {
    branchesByRepository.value = {
      ...branchesByRepository.value,
      [repository.id]: await listProviderBranches(repository),
    }
  } catch (caught) {
    branchErrors.value = {
      ...branchErrors.value,
      [repository.id]: caught instanceof Error ? caught.message : 'Unable to load branches.',
    }
  } finally {
    const nextLoading = new Set(loadingBranchIds.value)
    nextLoading.delete(repository.id)
    loadingBranchIds.value = nextLoading
  }
}

function importRepository(repository: ProviderRepository) {
  emit('import', repository, selectedBranches.value[repository.id] || undefined)
}

async function connect(provider: SourceControlProvider) {
  pendingProvider.value = provider
  error.value = null
  try {
    window.location.assign(await connectProvider(provider))
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Unable to start provider connection.'
    pendingProvider.value = null
  }
}

async function disconnect(provider: SourceControlProvider) {
  const confirmed = await useDialogStore().confirm({
    title: `Disconnect ${provider}?`,
    message: 'Existing workspaces will remain available, but you will not be able to import new repositories from this provider until you reconnect.',
    confirmLabel: 'Disconnect',
    tone: 'danger',
  })
  if (!confirmed) return
  pendingProvider.value = provider
  error.value = null
  try {
    await disconnectProvider(provider)
    if (activeProvider.value === provider) {
      activeProvider.value = null
      repositories.value = []
    }
    await loadConnections()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : `Unable to disconnect ${provider}.`
  } finally {
    pendingProvider.value = null
  }
}

function chooseZip(event: Event) {
  selectedZip.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

function formatDate(value: string | null) {
  if (!value) return 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

onMounted(loadConnections)
</script>

<template>
  <section class="repository-browser" aria-labelledby="repository-connections-title">
    <div class="repository-browser__intro">
      <h1 id="repository-connections-title">Connect a source-control provider</h1>
      <p>Connect GitHub, GitLab, or Bitbucket to browse your repositories and build a RepoPilot workspace from any of them — public or private. Or upload a local zip.</p>
    </div>

    <p v-if="error" class="error-text repository-browser__error">{{ error }}</p>

    <div v-if="loadingConnections" class="repository-browser__loading">
      <LoaderCircle class="spin" aria-hidden="true" /> Loading connections…
    </div>

    <div v-else class="provider-grid provider-grid--detailed">
      <article
        v-for="connection in connections"
        :key="connection.provider"
        class="provider-card provider-card--detailed"
        :class="[`provider-card--${connection.provider}`, { 'provider-card--connected': connection.connected }]"
      >
        <div class="provider-card__topline">
          <span class="provider-card__icon">
            <component :is="providerMeta[connection.provider].icon" aria-hidden="true" />
          </span>
          <span v-if="connection.connected" class="provider-card__connected"><Check aria-hidden="true" /> Connected</span>
        </div>
        <strong>{{ connection.name }}</strong>
        <p>{{ providerMeta[connection.provider].description }}</p>

        <div v-if="connection.connected" class="provider-card__account">
          <span class="provider-card__avatar">
            <img v-if="connection.avatarUrl" :src="connection.avatarUrl" alt="" loading="lazy" decoding="async" fetchpriority="low" referrerpolicy="no-referrer">
            <span v-else>{{ (connection.accountName || connection.name).charAt(0).toUpperCase() }}</span>
          </span>
          <span>{{ connection.accountName || 'Connected account' }}</span>
          <button
            type="button"
            :disabled="pendingProvider === connection.provider"
            :aria-label="`Disconnect ${connection.name}`"
            :title="`Disconnect ${connection.name}`"
            @click="disconnect(connection.provider)"
          ><Unplug aria-hidden="true" /></button>
        </div>
        <button
          v-else
          class="provider-card__connect"
          type="button"
          :disabled="!connection.configured || pendingProvider === connection.provider"
          @click="connect(connection.provider)"
        >
          <LoaderCircle v-if="pendingProvider === connection.provider" class="spin" aria-hidden="true" />
          <Plus v-else aria-hidden="true" />
          {{ connection.configured ? `Connect ${connection.name}` : 'Administrator setup required' }}
        </button>
      </article>
    </div>

    <section class="zip-upload-card" aria-labelledby="zip-upload-title">
      <span class="zip-upload-card__icon"><Archive aria-hidden="true" /></span>
      <span class="zip-upload-card__copy">
        <strong id="zip-upload-title">Upload a local repository</strong>
        <span>{{ selectedZip ? selectedZip.name : 'No provider? Upload a zip of your codebase and RepoPilot will index it locally.' }}</span>
      </span>
      <label class="zip-upload-card__choose" for="repository-zip-upload">
        <Upload aria-hidden="true" /> Choose zip
      </label>
      <input id="repository-zip-upload" class="hidden-input" type="file" accept=".zip,application/zip" @change="chooseZip">
      <button class="zip-upload-card__build" type="button" disabled title="ZIP workspace builds will be enabled in the next stage">
        <ArrowRight aria-hidden="true" /> Build
      </button>
    </section>

    <section class="repository-results" aria-labelledby="browse-repositories-title">
      <div class="repository-results__heading">
        <div>
          <h2 id="browse-repositories-title">Browse repositories</h2>
          <span v-if="activeConnection">{{ repositories.length }} from {{ activeConnection.name }}</span>
          <span v-else>Select a provider, then load its repositories</span>
        </div>
        <button
          v-if="activeProvider"
          class="repository-results__refresh"
          type="button"
          :disabled="loadingRepositories"
          @click="selectProvider(activeProvider, true)"
        ><RefreshCw :class="{ spin: loadingRepositories }" aria-hidden="true" /> Refresh</button>
      </div>

      <div v-if="connectedProviders.length" class="provider-tabs" role="tablist" aria-label="Connected source-control providers">
        <button
          v-for="connection in connectedProviders"
          :key="connection.provider"
          class="provider-tab"
          :class="[`provider-tab--${connection.provider}`, { 'provider-tab--active': activeProvider === connection.provider }]"
          type="button"
          role="tab"
          :aria-selected="activeProvider === connection.provider"
          @click="selectProvider(connection.provider)"
        >
          <component :is="providerMeta[connection.provider].icon" aria-hidden="true" />
          {{ connection.name }}
        </button>
      </div>
      <div v-else-if="!loadingConnections" class="repository-results__empty">Connect a provider above to browse repositories.</div>

      <label v-if="activeProvider && !loadingRepositories" class="repository-filter">
        <Search aria-hidden="true" />
        <input v-model="filter" type="search" :placeholder="`Filter ${activeConnection?.name ?? ''} repositories…`">
      </label>

      <div v-if="loadingRepositories" class="repository-results__empty">
        <LoaderCircle class="spin" aria-hidden="true" /> Loading {{ activeConnection?.name }} repositories…
      </div>
      <div v-else-if="activeProvider && !filteredRepositories.length" class="repository-results__empty">
        {{ repositories.length ? 'No repositories match your filter.' : 'No repositories were returned for this account.' }}
      </div>
      <div v-else-if="activeProvider" class="repository-list">
        <article v-for="repository in visibleRepositories" :key="repository.id" class="repository-list__item">
          <div class="repository-list__main">
            <div class="repository-list__title">
              <component :is="providerMeta[repository.provider].icon" aria-hidden="true" />
              <strong>{{ repository.fullName }}</strong>
              <span :class="repository.private ? 'visibility-badge visibility-badge--private' : 'visibility-badge'">
                <LockKeyhole v-if="repository.private" aria-hidden="true" />
                <Globe2 v-else aria-hidden="true" />
                {{ repository.private ? 'Private' : 'Public' }}
              </span>
            </div>
            <p>{{ repository.description || 'No description provided.' }}</p>
            <div class="repository-list__meta">
              <span><Star aria-hidden="true" /> {{ repository.stars ?? 0 }}</span>
              <span><GitBranch aria-hidden="true" /> {{ repository.defaultBranch }}</span>
              <span>Updated {{ formatDate(repository.updatedAt) }}</span>
            </div>
          </div>
          <div class="repository-list__actions">
            <label class="repository-list__branch">
              <!-- <span class="sr-only">Branch for {{ repository.fullName }}</span> -->
              <GitBranch aria-hidden="true" />
              <select
                v-model="selectedBranches[repository.id]"
                :disabled="busy"
                :aria-describedby="branchErrors[repository.id] ? `branch-error-${repository.id}` : undefined"
                @focus="loadBranches(repository)"
                @pointerdown="loadBranches(repository)"
              >
                <option value="">Default ({{ repository.defaultBranch }})</option>
                <option v-if="loadingBranchIds.has(repository.id)" disabled>Loading branches…</option>
                <option
                  v-for="branch in branchesByRepository[repository.id] ?? []"
                  :key="branch"
                  :value="branch"
                >{{ branch }}</option>
              </select>
            </label>
            <span
              v-if="branchErrors[repository.id]"
              :id="`branch-error-${repository.id}`"
              class="repository-list__branch-error"
              role="status"
            >{{ branchErrors[repository.id] }}</span>
            <button class="repository-list__build" type="button" :disabled="busy" @click="importRepository(repository)">
              <ArrowRight aria-hidden="true" /> {{ busy ? 'Building…' : 'Build' }}
            </button>
          </div>
        </article>
        <button
          v-if="visibleRepositories.length < filteredRepositories.length"
          class="repository-results__refresh"
          type="button"
          @click="visibleLimit += 50"
        >Show 50 more</button>
      </div>
    </section>
  </section>
</template>
