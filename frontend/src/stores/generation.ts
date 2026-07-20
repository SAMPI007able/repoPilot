import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { generateTests } from '../services/api'
import { useWorkspaceStore } from './workspace'
import type { GenerateTestsResponse } from '../types/api'

type GenerationStageStatus = 'idle' | 'active' | 'done'

export interface GenerationStage {
  id: 'repository' | 'graph' | 'context' | 'prompt' | 'llm' | 'result'
  label: string
  status: GenerationStageStatus
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export const useGenerationStore = defineStore('generation', () => {
  const workspaceStore = useWorkspaceStore()
  const target = ref('')
  const testType = ref<'unit' | 'integration'>('integration')
  const isGenerating = ref(false)
  const error = ref<string | null>(null)
  const result = ref<GenerateTestsResponse | null>(null)

  const stages = ref<GenerationStage[]>([
    { id: 'repository', label: 'Repository', status: 'idle' },
    { id: 'graph', label: 'Knowledge Graph', status: 'idle' },
    { id: 'context', label: 'Context Builder', status: 'idle' },
    { id: 'prompt', label: 'Prompt Builder', status: 'idle' },
    { id: 'llm', label: 'Gemini', status: 'idle' },
    { id: 'result', label: 'Generated Tests', status: 'idle' },
  ])

  const hasResult = computed(() => Boolean(result.value))
  const selectedTargetLabel = computed(() => target.value || 'No target selected')

  async function runGeneration() {
    const workspaceId = workspaceStore.currentWorkspaceId
    if (!workspaceId) {
      error.value = 'Build a workspace before generating tests.'
      return null
    }

    if (!target.value) {
      error.value = 'Pick a target file or service first.'
      return null
    }

    error.value = null
    result.value = null
    isGenerating.value = true
    resetStages()

    try {
      await activateStage('repository', 140)
      await activateStage('graph', 160)
      await activateStage('context', 180)
      await activateStage('prompt', 220)
      setStage('llm', 'active')

      const response = await generateTests({
        workspaceId,
        target: target.value,
        type: testType.value,
      })

      setStage('llm', 'done')
      await activateStage('result', 180)
      result.value = response
      return response
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to generate tests.')
      resetStages()
      return null
    } finally {
      isGenerating.value = false
    }
  }

  function setTarget(value: string) {
    target.value = value
  }

  function setTestType(value: 'unit' | 'integration') {
    testType.value = value
  }

  function resetStages() {
    stages.value = stages.value.map((stage) => ({
      ...stage,
      status: 'idle',
    }))
  }

  async function activateStage(id: GenerationStage['id'], duration: number) {
    setStage(id, 'active')
    await wait(duration)
    setStage(id, 'done')
  }

  function setStage(id: GenerationStage['id'], status: GenerationStageStatus) {
    stages.value = stages.value.map((stage) => ({
      ...stage,
      status: stage.id === id ? status : stage.status,
    }))
  }

  function clearResult() {
    result.value = null
    error.value = null
    resetStages()
  }

  return {
    target,
    testType,
    isGenerating,
    error,
    result,
    stages,
    hasResult,
    selectedTargetLabel,
    runGeneration,
    setTarget,
    setTestType,
    clearResult,
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
