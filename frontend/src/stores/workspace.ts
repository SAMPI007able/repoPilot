import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { captureTelemetry } from '../services/telemetry'
import { useDialogStore } from './dialog'
import {
  deletePersistedWorkspace,
  extractAPIError,
  getPersistedWorkspace,
  getWorkspaceBuild,
  listWorkspaceBranches,
  listPersistedWorkspaces,
  reindexPersistedWorkspace,
  startWorkspaceBuild,
  importProviderRepository as startProviderRepositoryImport,
} from '../services/api'
import type {
  PersistedWorkspaceSummary,
  RepositoryMetadata,
  WorkspaceBuildStage,
  ProviderRepository,
} from '../types/api'

export type WorkspaceStatus = 'pending' | 'building' | 'ready' | 'failed'

export interface WorkspaceListItem {
  id: string
  repoName: string
  repoUrl: string
  indexedBranch: string | null
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

function pollDelay(attempt: number) {
  if (document.hidden) return 5000
  return Math.min(600 * (1.35 ** attempt), 2000)
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const repositoryUrl = ref('')
  const projectDocuments = ref<File[]>([])
  const workspaces = ref<WorkspaceListItem[]>([])
  const activeId = ref<string | null>(null)
  const loadingList = ref(false)
  const busy = ref(false)
  const removingIds = ref<string[]>([])
  const reindexingIds = ref<string[]>([])
  const loadingBranchIds = ref<string[]>([])
  const branchesByWorkspace = ref<Record<string, string[]>>({})
  const error = ref<string | null>(null)
  const removedWorkspaceIds = new Set<string>()
  let workspaceLoadPromise: Promise<void> | null = null
  let workspaceRequestId = 0
  let lastWorkspaceLoadAt = 0

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
    if (workspaceLoadPromise) {
      if (showLoading) {
        loadingList.value = true
      }
      return workspaceLoadPromise
    }

    if (showLoading) {
      loadingList.value = true
    }
    error.value = null
    const requestId = ++workspaceRequestId
    workspaceLoadPromise = (async () => {
      try {
        const persistedWorkspaces = await listPersistedWorkspaces()
        if (requestId !== workspaceRequestId) {
          return
        }
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
        lastWorkspaceLoadAt = Date.now()
      } catch (caughtError) {
        if (requestId === workspaceRequestId) {
          error.value = extractMessage(caughtError, 'Failed to load persisted workspaces.')
        }
      } finally {
        if (requestId === workspaceRequestId) {
          loadingList.value = false
          workspaceLoadPromise = null
        }
      }
    })()
    return workspaceLoadPromise
  }

  async function refreshWorkspacesIfStale() {
    if (Date.now() - lastWorkspaceLoadAt >= 30_000) {
      await loadWorkspaces(false)
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
      indexedBranch: null,
      status: 'pending',
      docs: projectDocuments.value.map((file) => file.name),
      metadata: null,
      jobId: null,
      stages: initialStages(),
    }

    upsertWorkspace(nextWorkspace)
    activeId.value = workspaceId

    try {
      const captureProperties = { repository_url: repositoryUrl.value.trim(), document_count: projectDocuments.value.length }
      if (projectDocuments.value.length > 0) {
        captureTelemetry('document_uploaded', {
          source: 'workspace_index',
          repository_url: repositoryUrl.value.trim(),
          document_count: projectDocuments.value.length,
        })
      }
      let buildJob = await startWorkspaceBuild(repositoryUrl.value.trim(), projectDocuments.value)
      captureTelemetry('repo_connected', captureProperties)
      captureTelemetry('repo_indexed', { workspace_id: buildJob.workspaceId, ...captureProperties })
      const persistedWorkspaceId = buildJob.workspaceId
      replaceWorkspaceId(workspaceId, persistedWorkspaceId, buildJob.jobId)
      workspaceId = persistedWorkspaceId
      patchWorkspace(workspaceId, {
        status: 'building',
        jobId: buildJob.jobId,
        stages: mapBuildStages(buildJob.stages),
      })

      let pollAttempt = 0
      while (buildJob.status === 'queued' || buildJob.status === 'running') {
        await wait(pollDelay(pollAttempt++))
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
      await loadWorkspaces(false)

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

  async function importProviderRepository(repository: ProviderRepository, branch?: string) {
    busy.value = true
    error.value = null
    let workspaceId = `pending-${slugify(repository.fullName)}-${Date.now()}`
    upsertWorkspace({
      id: workspaceId,
      repoName: repository.fullName,
      repoUrl: repository.webUrl,
      indexedBranch: branch || repository.defaultBranch,
      status: 'pending', docs: [], metadata: null, jobId: null, stages: initialStages(),
    })
    activeId.value = workspaceId
    try {
      const captureProperties = {
        provider: repository.provider,
        repository_name: repository.fullName,
        branch: branch || repository.defaultBranch,
      }
      let buildJob = await startProviderRepositoryImport(repository, branch)
      captureTelemetry('repo_connected', captureProperties)
      captureTelemetry('repo_indexed', { workspace_id: buildJob.workspaceId, ...captureProperties })
      replaceWorkspaceId(workspaceId, buildJob.workspaceId, buildJob.jobId)
      workspaceId = buildJob.workspaceId
      patchWorkspace(workspaceId, { status: 'building', jobId: buildJob.jobId, stages: mapBuildStages(buildJob.stages) })
      let pollAttempt = 0
      while (buildJob.status === 'queued' || buildJob.status === 'running') {
        await wait(pollDelay(pollAttempt++))
        buildJob = await getWorkspaceBuild(buildJob.jobId)
        patchWorkspace(workspaceId, { status: buildJob.status === 'failed' ? 'failed' : 'building', stages: mapBuildStages(buildJob.stages) })
      }
      if (buildJob.status === 'failed') throw new Error(buildJob.error ?? 'Workspace build failed.')
      if (!buildJob.metadata) throw new Error('Workspace build completed without repository metadata.')
      patchWorkspace(workspaceId, {
        repoName: buildJob.metadata.repository, status: 'ready', metadata: buildJob.metadata,
        stages: mapBuildStages(buildJob.stages),
      })
      await loadWorkspaces(false)
      return buildJob.metadata
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to import repository.')
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
        indexedBranch: persistedWorkspace.indexedBranch,
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
    const confirmed = await useDialogStore().confirm({
      title: 'Remove workspace?',
      message: `"${workspace.repoName}" and its index, chat history, and previews will be removed from RepoPilot. This cannot be undone.`,
      confirmLabel: 'Remove workspace',
      tone: 'danger',
    })
    if (!confirmed) return

    error.value = null
    removedWorkspaceIds.add(id)
    removingIds.value = [...removingIds.value, id]
    try {
      await deletePersistedWorkspace(id)
      workspaces.value = workspaces.value.filter((item) => item.id !== id)
      if (activeId.value === id) {
        activeId.value = null
      }
      await loadWorkspaces(false)
    } catch (caughtError) {
      removedWorkspaceIds.delete(id)
      error.value = extractMessage(caughtError, 'Failed to remove workspace.')
      void useDialogStore().alert({ title: 'Could not remove workspace', message: error.value, tone: 'danger' })
    } finally {
      removingIds.value = removingIds.value.filter((workspaceId) => workspaceId !== id)
    }
  }

  async function loadWorkspaceBranches(id: string, force = false) {
    if ((!force && branchesByWorkspace.value[id]) || loadingBranchIds.value.includes(id)) return
    loadingBranchIds.value = [...loadingBranchIds.value, id]
    try {
      branchesByWorkspace.value = {
        ...branchesByWorkspace.value,
        [id]: await listWorkspaceBranches(id),
      }
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to load repository branches.')
    } finally {
      loadingBranchIds.value = loadingBranchIds.value.filter((workspaceId) => workspaceId !== id)
    }
  }

  async function reindexWorkspace(id: string, branch?: string) {
    const workspace = workspaces.value.find((item) => item.id === id)
    if (!workspace || reindexingIds.value.includes(id)) return null
    const selectedBranch = branch || workspace.indexedBranch || undefined
    const branchDescription = selectedBranch ? ` from branch “${selectedBranch}”` : ''
    const confirmed = await useDialogStore().confirm({
      title: 'Re-index repository?',
      message: `RepoPilot will pull the latest code for ${workspace.repoName}${branchDescription} and rebuild its index. AI tools stay unavailable until the build finishes.`,
      confirmLabel: 'Re-index',
    })
    if (!confirmed) return null

    error.value = null
    reindexingIds.value = [...reindexingIds.value, id]
    const previousBranch = workspace.indexedBranch
    try {
      let buildJob = await reindexPersistedWorkspace(id, selectedBranch)
      patchWorkspace(id, {
        status: 'building',
        indexedBranch: selectedBranch ?? previousBranch,
        jobId: buildJob.jobId,
        stages: mapBuildStages(buildJob.stages),
      })
      let pollAttempt = 0
      while (buildJob.status === 'queued' || buildJob.status === 'running') {
        await wait(pollDelay(pollAttempt++))
        buildJob = await getWorkspaceBuild(buildJob.jobId)
        patchWorkspace(id, {
          status: buildJob.status === 'failed' ? 'ready' : 'building',
          stages: mapBuildStages(buildJob.stages),
        })
      }
      if (buildJob.status === 'failed') throw new Error(buildJob.error ?? 'Re-index failed.')
      if (!buildJob.metadata) throw new Error('Re-index completed without repository metadata.')
      patchWorkspace(id, {
        status: 'ready',
        metadata: buildJob.metadata,
        indexedBranch: selectedBranch ?? previousBranch,
        stages: mapBuildStages(buildJob.stages),
      })
      await loadWorkspaces(false)
      return buildJob.metadata
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to re-index workspace.')
      patchWorkspace(id, { status: 'ready', indexedBranch: previousBranch })
      void useDialogStore().alert({ title: 'Re-index failed', message: error.value, tone: 'danger' })
      return null
    } finally {
      reindexingIds.value = reindexingIds.value.filter((workspaceId) => workspaceId !== id)
    }
  }

  function startNewWorkspace() {
    activeId.value = null
    error.value = null
  }

  function clearSession() {
    workspaceRequestId += 1
    workspaceLoadPromise = null
    lastWorkspaceLoadAt = 0
    repositoryUrl.value = ''
    projectDocuments.value = []
    workspaces.value = []
    activeId.value = null
    loadingList.value = false
    busy.value = false
    removingIds.value = []
    reindexingIds.value = []
    loadingBranchIds.value = []
    branchesByWorkspace.value = {}
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
    reindexingIds,
    loadingBranchIds,
    branchesByWorkspace,
    error,
    frameworkLabel,
    pipelineStages,
    targetOptions,
    loadWorkspaces,
    refreshWorkspacesIfStale,
    createWorkspace,
    importProviderRepository,
    setRepositoryUrl,
    setProjectDocuments,
    selectWorkspace,
    removeWorkspace,
    loadWorkspaceBranches,
    reindexWorkspace,
    startNewWorkspace,
    clearSession,
  }
})

function extractMessage(error: unknown, fallback: string) {
  return extractAPIError(error, fallback).message
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
    indexedBranch: workspace.indexedBranch,
    status: statusMap[workspace.status],
    docs: [],
    metadata: null,
    jobId: workspace.jobId,
    stages: mapBuildStages(workspace.stages),
  }
}
