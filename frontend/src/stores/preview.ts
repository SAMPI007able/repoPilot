import { ref } from 'vue'
import { defineStore } from 'pinia'
import { captureTelemetry } from '../services/telemetry'
import {
  apiBaseUrl,
  extractAPIError,
  getAccessToken,
  analyzeRuntimeManifest,
  approveRuntimeManifest,
  createPreview,
  extendPreview,
  getLatestPreview,
  getPreview,
  getPreviewLogs,
  getRuntimeManifest,
  stopPreview,
  updateRuntimeManifest,
} from '../services/api'
import type {
  PreviewEnvironment, PreviewErrorEnvelope, PreviewEvent, RuntimeManifest, RuntimeManifestRecord,
} from '../types/api'

export const usePreviewStore = defineStore('preview', () => {
  const workspaceId = ref<string | null>(null)
  const instructions = ref('')
  const record = ref<RuntimeManifestRecord | null>(null)
  const draft = ref<RuntimeManifest | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const approving = ref(false)
  const starting = ref(false)
  const stopping = ref(false)
  const extending = ref(false)
  const activePreview = ref<PreviewEnvironment | null>(null)
  const environment = ref<Record<string, string>>({})
  const events = ref<PreviewEvent[]>([])
  const logs = ref('')
  const remainingSeconds = ref(0)
  const error = ref<string | null>(null)
  const concurrencyBlocked = ref(false)
  let eventAbortController: AbortController | null = null
  let countdownTimer: number | null = null
  let refreshTimer: number | null = null
  let refreshInFlight = false

  async function load(nextWorkspaceId: string) {
    disconnectEvents()
    workspaceId.value = nextWorkspaceId
    activePreview.value = null
    events.value = []
    logs.value = ''
    loading.value = true
    error.value = null
    try {
      setRecord(await getRuntimeManifest(nextWorkspaceId))
    } catch (caughtError) {
      if (extractStatus(caughtError) === 404) {
        record.value = null
        draft.value = null
      } else {
        error.value = extractPreviewError(caughtError, 'Failed to load runtime manifest.')
      }
    } finally {
      loading.value = false
    }
    await loadLatest(nextWorkspaceId)
  }

  async function analyze() {
    if (!workspaceId.value) {
      return
    }
    loading.value = true
    error.value = null
    try {
      setRecord(await analyzeRuntimeManifest(workspaceId.value, instructions.value))
    } catch (caughtError) {
      error.value = extractPreviewError(caughtError, 'Runtime analysis failed.')
    } finally {
      loading.value = false
    }
  }

  async function save() {
    if (!workspaceId.value || !record.value || !draft.value) {
      return
    }
    saving.value = true
    error.value = null
    try {
      setRecord(
        await updateRuntimeManifest(
          workspaceId.value,
          draft.value,
          record.value.revision,
        ),
      )
    } catch (caughtError) {
      error.value = extractPreviewError(caughtError, 'Failed to save runtime manifest.')
    } finally {
      saving.value = false
    }
  }

  async function approve() {
    if (!workspaceId.value || !record.value) {
      return
    }
    approving.value = true
    error.value = null
    try {
      setRecord(await approveRuntimeManifest(workspaceId.value, record.value.revision))
    } catch (caughtError) {
      error.value = extractPreviewError(caughtError, 'Failed to approve runtime manifest.')
    } finally {
      approving.value = false
    }
  }

  async function loadLatest(nextWorkspaceId: string) {
    try {
      activePreview.value = await getLatestPreview(nextWorkspaceId)
      initializeEnvironment()
      await refreshLogs()
      if (!isTerminal(activePreview.value.status)) {
        connectEvents(activePreview.value.id)
        startCountdown()
      } else {
        stopCountdown()
        updateCountdown()
      }
    } catch (caughtError) {
      if (extractStatus(caughtError) !== 404) {
        error.value = extractPreviewError(caughtError, 'Failed to restore the latest preview.')
      }
    }
  }

  async function start() {
    if (!workspaceId.value || !record.value?.approved) return
    starting.value = true
    error.value = null
    try {
      concurrencyBlocked.value = false
      stopCountdown()
      activePreview.value = await createPreview(
        workspaceId.value, environment.value, crypto.randomUUID(),
      )
      captureTelemetry('preview_started', {
        workspace_id: workspaceId.value,
        preview_id: activePreview.value.id,
      })
      events.value = []
      logs.value = ''
      connectEvents(activePreview.value.id)
      startCountdown()
    } catch (caughtError) {
      error.value = extractPreviewError(caughtError, 'Failed to start the preview.')
      concurrencyBlocked.value = extractAPIError(caughtError, '').code === 'CONCURRENCY_LIMIT_EXCEEDED'
      if (concurrencyBlocked.value && workspaceId.value) await loadLatest(workspaceId.value)
    } finally {
      starting.value = false
    }
  }

  async function stop() {
    if (!activePreview.value) return
    stopping.value = true
    error.value = null
    try {
      activePreview.value = await stopPreview(activePreview.value.id)
      captureTelemetry('preview_completed', {
        preview_id: activePreview.value.id,
        status: activePreview.value.status,
      })
      concurrencyBlocked.value = false
      disconnectEvents()
      stopCountdown()
    } catch (caughtError) {
      error.value = extractPreviewError(caughtError, 'Failed to stop the preview.')
    } finally {
      stopping.value = false
    }
  }

  async function extend() {
    if (!activePreview.value) return
    extending.value = true
    error.value = null
    try {
      activePreview.value = await extendPreview(activePreview.value.id)
      captureTelemetry('preview_started', {
        preview_id: activePreview.value.id,
        extended: true,
      })
      updateCountdown()
    } catch (caughtError) {
      error.value = extractPreviewError(caughtError, 'Failed to extend the preview.')
    } finally {
      extending.value = false
    }
  }

  function initializeEnvironment() {
    if (!record.value) return
    const names = [...record.value.manifest.environment.required, ...record.value.manifest.environment.optional]
    environment.value = Object.fromEntries(names.map((name) => [name, environment.value[name] ?? '']))
  }

  function setEnvironment(name: string, value: string) {
    environment.value[name] = value
  }

  function connectEvents(previewId: string) {
    disconnectEvents()
    eventAbortController = new AbortController()
    void streamEvents(previewId, eventAbortController.signal)
  }

  async function streamEvents(previewId: string, signal: AbortSignal) {
    try {
      const token = await getAccessToken()
      const response = await fetch(`${apiBaseUrl}/previews/${previewId}/events`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, signal,
      })
      if (!response.ok || !response.body) throw new Error('Preview event stream is unavailable.')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!signal.aborted) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        let boundary = buffer.indexOf('\n\n')
        while (boundary >= 0) {
          const block = buffer.slice(0, boundary)
          buffer = buffer.slice(boundary + 2)
          const data = block.split('\n').find((line) => line.startsWith('data: '))?.slice(6)
          if (data) {
            const event = JSON.parse(data) as PreviewEvent
            if (!events.value.some((item) => item.id === event.id)) {
              events.value = [...events.value.slice(-199), event]
            }
            scheduleRefresh(previewId)
          }
          boundary = buffer.indexOf('\n\n')
        }
      }
    } catch (caught) {
      if (!signal.aborted) error.value = caught instanceof Error ? caught.message : 'Preview event stream failed.'
    }
  }

  async function refreshLogs() {
    if (!activePreview.value) return
    try {
      logs.value = (await getPreviewLogs(activePreview.value.id)).content
    } catch {
      // Logs are auxiliary; lifecycle state remains authoritative.
    }
  }

  function scheduleRefresh(previewId: string) {
    if (refreshTimer !== null || refreshInFlight) return
    refreshTimer = window.setTimeout(async () => {
      refreshTimer = null
      refreshInFlight = true
      try {
        if (activePreview.value?.id !== previewId) return
        const refreshedPreview = await getPreview(previewId)
        if (activePreview.value?.id !== previewId) return
        activePreview.value = refreshedPreview
        await refreshLogs()
        updateCountdown()
        if (activePreview.value && isTerminal(activePreview.value.status)) {
          disconnectEvents()
          stopCountdown()
        }
      } finally {
        refreshInFlight = false
      }
    }, 750)
  }

  function startCountdown() {
    stopCountdown()
    updateCountdown()
    countdownTimer = window.setInterval(updateCountdown, 1000)
  }

  function stopCountdown() {
    if (countdownTimer !== null) window.clearInterval(countdownTimer)
    countdownTimer = null
  }

  function updateCountdown() {
    remainingSeconds.value = activePreview.value
      ? Math.max(0, Math.floor((new Date(activePreview.value.expiresAt).getTime() - Date.now()) / 1000))
      : 0
  }

  function disconnectEvents() {
    eventAbortController?.abort()
    eventAbortController = null
    if (refreshTimer !== null) window.clearTimeout(refreshTimer)
    refreshTimer = null
  }

  function clearSession() {
    disconnectEvents()
    stopCountdown()
    workspaceId.value = null
    instructions.value = ''
    record.value = null
    draft.value = null
    activePreview.value = null
    environment.value = {}
    events.value = []
    logs.value = ''
    remainingSeconds.value = 0
    error.value = null
    concurrencyBlocked.value = false
  }

  function setInstructions(value: string) {
    instructions.value = value
  }

  function setRecord(nextRecord: RuntimeManifestRecord) {
    record.value = nextRecord
    draft.value = structuredClone(nextRecord.manifest)
    initializeEnvironment()
  }

  return {
    workspaceId,
    instructions,
    record,
    draft,
    loading,
    saving,
    approving,
    starting,
    stopping,
    extending,
    activePreview,
    environment,
    events,
    logs,
    remainingSeconds,
    error,
    concurrencyBlocked,
    load,
    analyze,
    save,
    approve,
    start,
    stop,
    extend,
    setEnvironment,
    setInstructions,
    clearSession,
  }
})

function isTerminal(status: string) {
  return ['stopped', 'expired', 'failed'].includes(status)
}

function extractStatus(error: unknown) {
  if (typeof error === 'object' && error && 'response' in error) {
    return (error as { response?: { status?: number } }).response?.status
  }
  return undefined
}

function extractPreviewError(error: unknown, fallback: string) {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as { response?: { data?: PreviewErrorEnvelope } }).response
    if (response?.data?.message) {
      const violations = response.data.details?.violations
      if (Array.isArray(violations) && violations.length) {
        return `${response.data.message} ${violations.join(' ')}`
      }
      return extractAPIError(error, fallback).message
    }
  }
  return extractAPIError(error, fallback).message
}
