import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import posthog from 'posthog-js'
import { analyzeImpact, extractAPIError, generateTests, getLatestChatSession, queryAI } from '../services/api'
import { useWorkspaceStore } from './workspace'
import { useFeatureFlagStore } from './features'
import type { AIQueryResponse, ChatMessage, ImpactAnalysisResponse } from '../types/api'

export type TabId = 'ask' | 'tests' | 'preview' | 'insights' | 'impact'
export type TestMode = 'scenario' | 'file'

export const useGenerationStore = defineStore('generation', () => {
  const workspaceStore = useWorkspaceStore()
  const featureFlags = useFeatureFlagStore()
  const tab = ref<TabId>('ask')
  const mode = ref<TestMode>('scenario')
  const target = ref('')
  const testType = ref<'unit' | 'integration'>('integration')
  const genericQuery = ref('')
  const scenario = ref('')
  const fileQuery = ref('')
  const selectedFile = ref('')
  const fileMenuOpen = ref(false)
  const impactFile = ref('')
  const impactBusy = ref(false)
  const impactError = ref<string | null>(null)
  const impactResult = ref<ImpactAnalysisResponse | null>(null)
  const busy = ref(false)
  const error = ref<string | null>(null)
  const result = ref<AIQueryResponse | null>(null)
  const chatSessionId = ref<string | null>(null)
  const chatMessages = ref<ChatMessage[]>([])

  const tabs = computed(() => [
    { id: 'ask' as TabId, label: 'Ask the codebase' },
    { id: 'tests' as TabId, label: 'Generate tests' },
    ...(featureFlags.previewEnabled ? [{ id: 'preview' as TabId, label: 'Realtime preview' }] : []),
    ...(featureFlags.codeQualityEnabled ? [{ id: 'insights' as TabId, label: 'Code quality' }] : []),
    { id: 'impact' as TabId, label: 'Impact analysis' },
  ])

  const suggestedQuestions = computed(() => [
    'Explain the payment flow in this project',
    'How do webhooks verify signatures?',
    'How does retry & idempotency work?',
  ])

  const suggestedScenarios = computed(() => [
    'A customer retries payment after a timeout',
    'A webhook is delivered twice for the same intent',
    'A refund is issued for a partially captured payment',
  ])

  const fileOptions = computed(() => workspaceStore.targetOptions.map((item) => item.path))
  const filteredFiles = computed(() => {
    const query = fileQuery.value.trim().toLowerCase()
    if (!query) {
      return fileOptions.value
    }

    return fileOptions.value.filter((file) => file.toLowerCase().includes(query))
  })

  async function runQuery(text?: string) {
    const workspaceId = workspaceStore.currentWorkspaceId
    const queryText = (text ?? genericQuery.value).trim()
    if (!workspaceId) {
      error.value = 'Build a workspace before asking a query.'
      return null
    }
    if (!queryText) {
      error.value = 'Ask a question about the current workspace.'
      return null
    }

    busy.value = true
    error.value = null
    result.value = null
    genericQuery.value = ''
    const pendingId = `pending-${crypto.randomUUID()}`
    chatMessages.value.push({
      id: pendingId,
      role: 'user',
      content: queryText,
      createdAt: new Date().toISOString(),
    })

    try {
      if (typeof posthog?.capture === 'function') posthog.capture('chat_message', {
        workspace_id: workspaceId,
        query_length: queryText.length,
      })
      const response = await queryAI({
        type: 'chat',
        workspaceId,
        query: queryText,
        sessionId: chatSessionId.value,
      })
      chatSessionId.value = response.sessionId || chatSessionId.value
      chatMessages.value.push({
        id: `assistant-${crypto.randomUUID()}`,
        role: 'assistant',
        content: response.markdown,
        createdAt: new Date().toISOString(),
      })
      result.value = response
      return response
    } catch (caughtError) {
      chatMessages.value = chatMessages.value.filter((message) => message.id !== pendingId)
      error.value = extractMessage(caughtError, 'Failed to run query.')
      return null
    } finally {
      busy.value = false
    }
  }

  async function loadLatestChat(workspaceId: string | null) {
    chatSessionId.value = null
    chatMessages.value = []
    if (!workspaceId) return
    try {
      const session = await getLatestChatSession(workspaceId)
      if (workspaceStore.currentWorkspaceId !== workspaceId || !session) return
      chatSessionId.value = session.id
      chatMessages.value = session.messages
    } catch (caughtError) {
      if (workspaceStore.currentWorkspaceId === workspaceId) {
        error.value = extractMessage(caughtError, 'Failed to load the latest chat.')
      }
    }
  }

  function startNewChat() {
    chatSessionId.value = null
    chatMessages.value = []
    result.value = null
    error.value = null
    genericQuery.value = ''
  }

  async function runGenerationFromScenario(text?: string) {
    const workspaceId = workspaceStore.currentWorkspaceId
    const nextScenario = (text ?? scenario.value).trim()
    if (!workspaceId) {
      error.value = 'Build a workspace before generating tests.'
      return null
    }
    if (!nextScenario) {
      error.value = 'Describe a scenario first.'
      return null
    }

    busy.value = true
    error.value = null
    result.value = null
    scenario.value = nextScenario

    try {
      const response = await generateTests({
        workspaceId,
        mode: 'scenario',
        scenario: nextScenario,
        type: testType.value,
      })
      result.value = response
      return response
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to generate tests.')
      return null
    } finally {
      busy.value = false
    }
  }

  async function runGenerationFromFile(file?: string) {
    const workspaceId = workspaceStore.currentWorkspaceId
    const nextFile = (file ?? selectedFile.value).trim()
    if (!workspaceId) {
      error.value = 'Build a workspace before generating tests.'
      return null
    }
    if (!nextFile) {
      error.value = 'Select a file first.'
      return null
    }

    const matchingTarget = workspaceStore.targetOptions.find((option) => option.path === nextFile)
    target.value = matchingTarget?.value ?? nextFile
    selectedFile.value = nextFile
    fileMenuOpen.value = false
    busy.value = true
    error.value = null
    result.value = null

    try {
      const response = await generateTests({
        workspaceId,
        mode: 'file',
        target: target.value,
        type: testType.value,
      })
      result.value = response
      return response
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to generate tests.')
      return null
    } finally {
      busy.value = false
    }
  }

  async function runImpactAnalysis(file?: string) {
    const workspaceId = workspaceStore.currentWorkspaceId
    const nextFile = (file ?? impactFile.value).trim()
    if (!workspaceId) {
      impactError.value = 'Build a workspace before running impact analysis.'
      return null
    }
    if (!nextFile) {
      impactError.value = 'Select a file to analyze.'
      return null
    }

    impactBusy.value = true
    impactError.value = null
    impactResult.value = null
    impactFile.value = nextFile

    try {
      const response = await analyzeImpact({
        workspaceId,
        target: nextFile,
      })
      impactResult.value = response
      return response
    } catch (caughtError) {
      impactError.value = extractMessage(caughtError, 'Failed to analyze impact.')
      return null
    } finally {
      impactBusy.value = false
    }
  }

  function setTab(value: TabId) {
    if (tabs.value.some((item) => item.id === value)) tab.value = value
  }

  function setMode(value: TestMode) {
    mode.value = value
  }

  function setTarget(value: string) {
    target.value = value
  }

  function setTestType(value: 'unit' | 'integration') {
    testType.value = value
  }

  function setGenericQuery(value: string) {
    genericQuery.value = value
  }

  function setScenario(value: string) {
    scenario.value = value
  }

  function setFileQuery(value: string) {
    fileQuery.value = value
  }

  function setSelectedFile(value: string) {
    selectedFile.value = value
  }

  function setFileMenuOpen(value: boolean) {
    fileMenuOpen.value = value
  }

  function setImpactFile(value: string) {
    impactFile.value = value
  }

  watch(
    () => workspaceStore.currentWorkspaceId,
    (workspaceId) => { void loadLatestChat(workspaceId) },
    { immediate: true },
  )

  return {
    tab,
    tabs,
    mode,
    target,
    testType,
    genericQuery,
    scenario,
    fileQuery,
    selectedFile,
    fileMenuOpen,
    impactFile,
    impactBusy,
    impactError,
    impactResult,
    busy,
    error,
    result,
    chatSessionId,
    chatMessages,
    suggestedQuestions,
    suggestedScenarios,
    fileOptions,
    filteredFiles,
    runQuery,
    startNewChat,
    runGenerationFromScenario,
    runGenerationFromFile,
    runImpactAnalysis,
    setTab,
    setMode,
    setTarget,
    setTestType,
    setGenericQuery,
    setScenario,
    setFileQuery,
    setSelectedFile,
    setFileMenuOpen,
    setImpactFile,
  }
})

function extractMessage(error: unknown, fallback: string) {
  return extractAPIError(error, fallback).message
}
