import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { buildWorkspace } from '../services/api'
import type { RepositoryMetadata } from '../types/api'

type WorkspaceStageId = 'clone' | 'index' | 'classes' | 'graph'
type WorkspaceStageStatus = 'idle' | 'active' | 'done'

export interface WorkspaceStage {
  id: WorkspaceStageId
  label: string
  detail: string
  status: WorkspaceStageStatus
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export const useWorkspaceStore = defineStore('workspace', () => {
  const repositoryUrl = ref('')
  const metadata = ref<RepositoryMetadata | null>(null)
  const isBuilding = ref(false)
  const error = ref<string | null>(null)
  const currentWorkspaceId = ref<string | null>(null)

  const stages = ref<WorkspaceStage[]>([
    { id: 'clone', label: 'Repository Cloned', detail: 'Connecting to Git and pulling source.', status: 'idle' },
    { id: 'index', label: 'Files Indexed', detail: 'Scanning supported files and metadata.', status: 'idle' },
    { id: 'classes', label: 'Symbols Counted', detail: 'Summarizing classes and methods.', status: 'idle' },
    { id: 'graph', label: 'Knowledge Graph Built', detail: 'Linking imports, tests, docs, and packages.', status: 'idle' },
  ])

  const frameworkLabel = computed(() => {
    if (!metadata.value) {
      return 'Not indexed yet'
    }

    const framework = metadata.value.packageInfo?.vueVersion
      ? `Vue ${metadata.value.packageInfo.vueVersion}`
      : metadata.value.packageInfo?.reactVersion
        ? `React ${metadata.value.packageInfo.reactVersion}`
        : 'JavaScript'

    return metadata.value.testFramework
      ? `${framework} + ${capitalize(metadata.value.testFramework)}`
      : framework
  })

  const dashboardStats = computed(() => {
    if (!metadata.value) {
      return []
    }

    const classCount = metadata.value.parsedFiles.reduce((sum, file) => sum + file.classes, 0)
    const methodCount = metadata.value.parsedFiles.reduce((sum, file) => sum + file.functions, 0)
    const importCount = metadata.value.parsedFiles.reduce((sum, file) => sum + file.imports, 0)
    const graphNodes = metadata.value.statistics.files + classCount
    const graphEdges = importCount

    return [
      { label: 'Classes', value: classCount },
      { label: 'Methods', value: methodCount },
      { label: 'Imports', value: importCount },
      { label: 'Graph Nodes', value: graphNodes },
      { label: 'Graph Edges', value: graphEdges },
    ]
  })

  const targetOptions = computed(() => {
    if (!metadata.value) {
      return []
    }

    return metadata.value.parsedFiles
      .filter((file) => !file.path.includes('.test.') && !file.path.includes('.spec.'))
      .map((file) => {
        const segments = file.path.split('/')
        const fileName = segments[segments.length - 1]
        const label = fileName.replace(/\.[^.]+$/, '')
        return {
          label,
          value: label,
          path: file.path,
        }
      })
  })

  async function createWorkspace() {
    if (!repositoryUrl.value.trim()) {
      error.value = 'Add a GitHub repository URL to build a workspace.'
      return null
    }

    isBuilding.value = true
    error.value = null
    metadata.value = null
    currentWorkspaceId.value = null
    resetStages()

    try {
      setStageStatus('clone', 'active')
      const nextMetadata = await buildWorkspace(repositoryUrl.value.trim())
      setStageStatus('clone', 'done')

      await wait(250)
      setStageStatus('index', 'active')
      await wait(280)
      setStageStatus('index', 'done')

      await wait(180)
      setStageStatus('classes', 'active')
      await wait(220)
      setStageStatus('classes', 'done')

      await wait(160)
      setStageStatus('graph', 'active')
      await wait(240)
      setStageStatus('graph', 'done')

      metadata.value = nextMetadata
      currentWorkspaceId.value = nextMetadata.repository
      return nextMetadata
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to build workspace.')
      resetStages()
      return null
    } finally {
      isBuilding.value = false
    }
  }

  function setRepositoryUrl(value: string) {
    repositoryUrl.value = value
  }

  function resetStages() {
    stages.value = stages.value.map((stage) => ({
      ...stage,
      status: 'idle',
    }))
  }

  function setStageStatus(id: WorkspaceStageId, status: WorkspaceStageStatus) {
    stages.value = stages.value.map((stage) => ({
      ...stage,
      status: stage.id === id ? status : stage.status === 'active' && status === 'active' ? 'done' : stage.status,
    }))
  }

  return {
    repositoryUrl,
    metadata,
    isBuilding,
    error,
    stages,
    currentWorkspaceId,
    frameworkLabel,
    dashboardStats,
    targetOptions,
    createWorkspace,
    setRepositoryUrl,
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

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1)
}
