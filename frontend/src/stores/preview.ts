import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  analyzeRuntimeManifest,
  approveRuntimeManifest,
  getRuntimeManifest,
  updateRuntimeManifest,
} from '../services/api'
import type { PreviewErrorEnvelope, RuntimeManifest, RuntimeManifestRecord } from '../types/api'

export const usePreviewStore = defineStore('preview', () => {
  const workspaceId = ref<string | null>(null)
  const instructions = ref('')
  const record = ref<RuntimeManifestRecord | null>(null)
  const draft = ref<RuntimeManifest | null>(null)
  const loading = ref(false)
  const saving = ref(false)
  const approving = ref(false)
  const error = ref<string | null>(null)

  async function load(nextWorkspaceId: string) {
    workspaceId.value = nextWorkspaceId
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

  function setInstructions(value: string) {
    instructions.value = value
  }

  function setRecord(nextRecord: RuntimeManifestRecord) {
    record.value = nextRecord
    draft.value = structuredClone(nextRecord.manifest)
  }

  return {
    workspaceId,
    instructions,
    record,
    draft,
    loading,
    saving,
    approving,
    error,
    load,
    analyze,
    save,
    approve,
    setInstructions,
  }
})

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
      return response.data.message
    }
  }
  return error instanceof Error ? error.message : fallback
}
