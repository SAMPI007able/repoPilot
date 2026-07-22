import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { buildWorkspace } from '../services/api'
import type { RepositoryMetadata } from '../types/api'

export type WorkspaceStatus = 'pending' | 'indexing' | 'graphing' | 'analyzing' | 'ready'

export interface WorkspaceListItem {
  id: string
  repoName: string
  repoUrl: string
  status: WorkspaceStatus
  docs: string[]
  metadata: RepositoryMetadata | null
}

export interface WorkspaceStage {
  id: 'pending' | 'indexing' | 'graphing' | 'analyzing' | 'ready'
  label: string
  detail: string
  status: 'upcoming' | 'active' | 'done'
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const repositoryUrl = ref('')
  const projectDocuments = ref<File[]>([])
  const workspaces = ref<WorkspaceListItem[]>([])
  const activeId = ref<string | null>(null)
  const loadingList = ref(false)
  const busy = ref(false)
  const error = ref<string | null>(null)

  const activeWorkspace = computed(() => workspaces.value.find((workspace) => workspace.id === activeId.value) ?? null)
  const metadata = computed(() => activeWorkspace.value?.metadata ?? null)
  const currentWorkspaceId = computed(() => activeWorkspace.value?.metadata?.repository ?? null)

  const frameworkLabel = computed(() => {
    const value = metadata.value
    if (!value) {
      return 'Framework pending'
    }

    const appFramework = value.packageInfo?.vueVersion
      ? `Vue ${cleanVersion(value.packageInfo.vueVersion)}`
      : value.packageInfo?.reactVersion
        ? `React ${cleanVersion(value.packageInfo.reactVersion)}`
        : 'JavaScript'

    return value.testFramework ? `${appFramework} + ${capitalize(value.testFramework)}` : appFramework
  })

  const pipelineStages = computed<WorkspaceStage[]>(() => {
    const order: WorkspaceStage['id'][] = ['pending', 'indexing', 'graphing', 'analyzing', 'ready']
    const labels: Record<WorkspaceStage['id'], Omit<WorkspaceStage, 'status'>> = {
      pending: { id: 'pending', label: 'Repository clone', detail: 'Cloning workspace source' },
      indexing: { id: 'indexing', label: 'Indexing', detail: 'Parsing files & symbols' },
      graphing: { id: 'graphing', label: 'Graph construction', detail: 'Resolving dependencies' },
      analyzing: { id: 'analyzing', label: 'Repository analysis', detail: 'Coupling, complexity, coverage' },
      ready: { id: 'ready', label: 'Ready', detail: 'Workspace built' },
    }

    const workspaceStatus = activeWorkspace.value?.status ?? 'pending'
    const activeIndex = order.indexOf(workspaceStatus)

    return order.map((id, index) => ({
      ...labels[id],
      status: workspaceStatus === 'ready'
        ? 'done'
        : index < activeIndex
          ? 'done'
          : index === activeIndex
            ? 'active'
            : 'upcoming',
    }))
  })

  const targetOptions = computed(() => {
    if (!metadata.value) {
      return []
    }

    return metadata.value.parsedFiles
      .filter((file) => !file.path.includes('.test.') && !file.path.includes('.spec.'))
      .map((file) => {
        const fileName = file.path.split('/').pop() ?? file.path
        return {
          label: fileName.replace(/\.[^.]+$/, ''),
          value: fileName.replace(/\.[^.]+$/, ''),
          path: file.path,
        }
      })
  })

  async function createWorkspace() {
    if (!repositoryUrl.value.trim()) {
      error.value = 'Paste a repository URL to begin.'
      return null
    }

    busy.value = true
    error.value = null

    const workspaceId = slugify(repositoryUrl.value)
    const nextWorkspace: WorkspaceListItem = {
      id: workspaceId,
      repoName: extractRepoName(repositoryUrl.value),
      repoUrl: repositoryUrl.value.trim(),
      status: 'pending',
      docs: projectDocuments.value.map((file) => file.name),
      metadata: null,
    }

    upsertWorkspace(nextWorkspace)
    activeId.value = workspaceId

    try {
      const indexPromise = buildWorkspace(repositoryUrl.value.trim(), projectDocuments.value)

      await wait(200)
      patchWorkspace(workspaceId, { status: 'indexing' })
      await wait(600)
      patchWorkspace(workspaceId, { status: 'graphing' })
      await wait(700)
      patchWorkspace(workspaceId, { status: 'analyzing' })

      const nextMetadata = await indexPromise
      patchWorkspace(workspaceId, {
        repoName: nextMetadata.repository,
        status: 'ready',
        metadata: nextMetadata,
      })

      repositoryUrl.value = ''
      projectDocuments.value = []
      return nextMetadata
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to build workspace.')
      workspaces.value = workspaces.value.filter((workspace) => workspace.id !== workspaceId)
      if (activeId.value === workspaceId) {
        activeId.value = workspaces.value[0]?.id ?? null
      }
      return null
    } finally {
      busy.value = false
    }
  }

  function setRepositoryUrl(value: string) {
    repositoryUrl.value = value
  }

  function setProjectDocuments(files: File[]) {
    projectDocuments.value = files
  }

  function selectWorkspace(id: string) {
    activeId.value = id
  }

  function startNewWorkspace() {
    activeId.value = null
    error.value = null
  }

  function upsertWorkspace(workspace: WorkspaceListItem) {
    const index = workspaces.value.findIndex((item) => item.id === workspace.id)
    if (index === -1) {
      workspaces.value = [workspace, ...workspaces.value]
      return
    }

    workspaces.value[index] = workspace
    workspaces.value = [...workspaces.value]
  }

  function patchWorkspace(id: string, patch: Partial<WorkspaceListItem>) {
    const existing = workspaces.value.find((workspace) => workspace.id === id)
    if (!existing) {
      return
    }

    upsertWorkspace({ ...existing, ...patch })
  }

  return {
    repositoryUrl,
    projectDocuments,
    workspaces,
    activeId,
    activeWorkspace,
    metadata,
    currentWorkspaceId,
    loadingList,
    busy,
    error,
    frameworkLabel,
    pipelineStages,
    targetOptions,
    createWorkspace,
    setRepositoryUrl,
    setProjectDocuments,
    selectWorkspace,
    startNewWorkspace,
  }
})

function extractMessage(error: unknown, fallback: string) {
  if (typeof error === 'object' && error && 'response' in error) {
    const maybeResponse = error as { response?: { data?: { detail?: string } } }
    return maybeResponse.response?.data?.detail ?? fallback
  }

  if (error instanceof Error) {
    return error.message
  }

  return fallback
}

function extractRepoName(url: string) {
  return url.replace(/\/+$/, '').split('/').slice(-2).join('/')
}

function slugify(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function cleanVersion(value: string) {
  return value.replace(/^[~^]/, '')
}
