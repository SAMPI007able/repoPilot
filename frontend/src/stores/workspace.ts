import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  deletePersistedWorkspace,
  getPersistedWorkspace,
  getWorkspaceBuild,
  listPersistedWorkspaces,
  startWorkspaceBuild,
} from '../services/api'
import type {
  PersistedWorkspaceSummary,
  RepositoryMetadata,
  WorkspaceBuildStage,
} from '../types/api'

export type WorkspaceStatus = 'pending' | 'building' | 'ready' | 'failed'

export interface WorkspaceListItem {
  id: string
  repoName: string
  repoUrl: string
  status: WorkspaceStatus
  docs: string[]
  metadata: RepositoryMetadata | null
  jobId: string | null
  stages: WorkspaceStage[]
}

export interface WorkspaceStage {
  id: string
  label: string
  detail: string
  status: 'upcoming' | 'active' | 'done' | 'failed'
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
  const removingIds = ref<string[]>([])
  const error = ref<string | null>(null)
  const removedWorkspaceIds = new Set<string>()

  const activeWorkspace = computed(() => workspaces.value.find((workspace) => workspace.id === activeId.value) ?? null)
  const metadata = computed(() => activeWorkspace.value?.metadata ?? null)
  const currentWorkspaceId = computed(() =>
    activeWorkspace.value?.status === 'ready' ? activeWorkspace.value.id : null,
  )

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
    return activeWorkspace.value?.stages ?? initialStages()
  })

  async function loadWorkspaces(showLoading = true) {
    if (showLoading) {
      loadingList.value = true
    }
    error.value = null
    try {
      const persistedWorkspaces = await listPersistedWorkspaces()
      const existingById = new Map(workspaces.value.map((workspace) => [workspace.id, workspace]))
      const refreshed = persistedWorkspaces
        .filter((workspace) => !removedWorkspaceIds.has(workspace.id))
        .map((persistedWorkspace) => {
          const mapped = mapPersistedWorkspace(persistedWorkspace)
          const existing = existingById.get(mapped.id)
          return existing
            ? {
                ...mapped,
                docs: existing.docs,
                metadata: existing.metadata,
              }
            : mapped
        })
      const pendingLocalWorkspaces = workspaces.value.filter((workspace) => workspace.id.startsWith('pending-'))
      workspaces.value = [...pendingLocalWorkspaces, ...refreshed]
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to load persisted workspaces.')
    } finally {
      if (showLoading) {
        loadingList.value = false
      }
    }
  }

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

    let workspaceId = `pending-${slugify(repositoryUrl.value)}-${Date.now()}`
    const nextWorkspace: WorkspaceListItem = {
      id: workspaceId,
      repoName: extractRepoName(repositoryUrl.value),
      repoUrl: repositoryUrl.value.trim(),
      status: 'pending',
      docs: projectDocuments.value.map((file) => file.name),
      metadata: null,
      jobId: null,
      stages: initialStages(),
    }

    upsertWorkspace(nextWorkspace)
    activeId.value = workspaceId

    try {
      let buildJob = await startWorkspaceBuild(repositoryUrl.value.trim(), projectDocuments.value)
      const persistedWorkspaceId = buildJob.workspaceId
      replaceWorkspaceId(workspaceId, persistedWorkspaceId, buildJob.jobId)
      workspaceId = persistedWorkspaceId
      patchWorkspace(workspaceId, {
        status: 'building',
        jobId: buildJob.jobId,
        stages: mapBuildStages(buildJob.stages),
      })

      while (buildJob.status === 'queued' || buildJob.status === 'running') {
        await wait(400)
        buildJob = await getWorkspaceBuild(buildJob.jobId)
        patchWorkspace(workspaceId, {
          status: buildJob.status === 'failed' ? 'failed' : 'building',
          stages: mapBuildStages(buildJob.stages),
        })
      }

      if (buildJob.status === 'failed') {
        throw new Error(buildJob.error ?? 'Workspace build failed.')
      }
      if (!buildJob.metadata) {
        throw new Error('Workspace build completed without repository metadata.')
      }

      const nextMetadata = buildJob.metadata
      patchWorkspace(workspaceId, {
        repoName: nextMetadata.repository,
        status: 'ready',
        metadata: nextMetadata,
        stages: mapBuildStages(buildJob.stages),
      })

      repositoryUrl.value = ''
      projectDocuments.value = []
      return nextMetadata
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to build workspace.')
      patchWorkspace(workspaceId, { status: 'failed' })
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

  async function selectWorkspace(id: string) {
    activeId.value = id
    const workspace = workspaces.value.find((item) => item.id === id)
    if (!workspace || workspace.metadata || workspace.status !== 'ready') {
      return
    }

    loadingList.value = true
    error.value = null
    try {
      const persistedWorkspace = await getPersistedWorkspace(id)
      patchWorkspace(id, {
        repoName: persistedWorkspace.repoName,
        repoUrl: persistedWorkspace.repoUrl,
        status: 'ready',
        metadata: persistedWorkspace.metadata,
        stages: mapBuildStages(persistedWorkspace.stages),
      })
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to load workspace.')
    } finally {
      loadingList.value = false
    }
  }

  async function removeWorkspace(id: string) {
    const workspace = workspaces.value.find((item) => item.id === id)
    if (!workspace || removingIds.value.includes(id)) {
      return
    }
    if (workspace.status === 'pending' || workspace.status === 'building') {
      error.value = 'Wait for the workspace build to finish before removing it.'
      return
    }
    if (!window.confirm(`Remove "${workspace.repoName}" from TestForge AI? This cannot be undone.`)) {
      return
    }

    error.value = null
    removedWorkspaceIds.add(id)
    removingIds.value = [...removingIds.value, id]
    try {
      await deletePersistedWorkspace(id)
      workspaces.value = workspaces.value.filter((item) => item.id !== id)
      if (activeId.value === id) {
        activeId.value = null
      }
    } catch (caughtError) {
      removedWorkspaceIds.delete(id)
      error.value = extractMessage(caughtError, 'Failed to remove workspace.')
      window.alert(error.value)
    } finally {
      removingIds.value = removingIds.value.filter((workspaceId) => workspaceId !== id)
    }
  }

  function startNewWorkspace() {
    activeId.value = null
    error.value = null
  }

  function clearSession() {
    repositoryUrl.value = ''
    projectDocuments.value = []
    workspaces.value = []
    activeId.value = null
    loadingList.value = false
    busy.value = false
    removingIds.value = []
    error.value = null
    removedWorkspaceIds.clear()
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

  function replaceWorkspaceId(oldId: string, newId: string, jobId: string) {
    const workspace = workspaces.value.find((item) => item.id === oldId)
    if (!workspace) {
      return
    }
    upsertWorkspace({ ...workspace, id: newId, jobId })
    workspaces.value = workspaces.value.filter((item) => item.id !== oldId)
    activeId.value = newId
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
    removingIds,
    error,
    frameworkLabel,
    pipelineStages,
    targetOptions,
    loadWorkspaces,
    createWorkspace,
    setRepositoryUrl,
    setProjectDocuments,
    selectWorkspace,
    removeWorkspace,
    startNewWorkspace,
    clearSession,
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

function mapBuildStages(stages: WorkspaceBuildStage[]): WorkspaceStage[] {
  const statusMap: Record<WorkspaceBuildStage['status'], WorkspaceStage['status']> = {
    pending: 'upcoming',
    running: 'active',
    completed: 'done',
    failed: 'failed',
  }
  return stages.map((stage) => ({
    id: stage.id,
    label: stage.label,
    detail: stage.detail,
    status: statusMap[stage.status],
  }))
}

function initialStages(): WorkspaceStage[] {
  return [
    {
      id: 'clone',
      label: 'Repository clone',
      detail: 'Waiting for the build worker',
      status: 'upcoming',
    },
  ]
}

function mapPersistedWorkspace(workspace: PersistedWorkspaceSummary): WorkspaceListItem {
  const statusMap: Record<PersistedWorkspaceSummary['status'], WorkspaceStatus> = {
    queued: 'pending',
    running: 'building',
    ready: 'ready',
    failed: 'failed',
  }
  return {
    id: workspace.id,
    repoName: workspace.repoName,
    repoUrl: workspace.repoUrl,
    status: statusMap[workspace.status],
    docs: [],
    metadata: null,
    jobId: workspace.jobId,
    stages: mapBuildStages(workspace.stages),
  }
}
