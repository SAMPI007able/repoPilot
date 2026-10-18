import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { captureTelemetry } from '../services/telemetry'
import {
  analyzeImpact, extractAPIError, generateTests, getChatSession, getLatestChatSession, getTestGeneration,
  listChatSessions, listTestGenerations, streamChatQuery,
} from '../services/api'
import { useWorkspaceStore } from './workspace'
import { useFeatureFlagStore } from './features'
import type {
  AIQueryResponse, ChatMessage, ChatSessionSummary, DatedHistoryGroup,
  ImpactAnalysisResponse, TestGenerationRecord, TestGenerationSummary,
} from '../types/api'

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
  const chatBusy = ref(false)
  const scenarioBusy = ref(false)
  const fileBusy = ref(false)
  const historyBusy = ref(false)
  const error = ref<string | null>(null)
  const scenarioResult = ref<AIQueryResponse | null>(null)
  const fileResult = ref<AIQueryResponse | null>(null)
  const result = computed(() => mode.value === 'scenario' ? scenarioResult.value : fileResult.value)
  const chatSessionId = ref<string | null>(null)
  const chatMessages = ref<ChatMessage[]>([])
  const chatSessions = ref<ChatSessionSummary[]>([])
  const testGenerations = ref<TestGenerationSummary[]>([])
  const chatHistoryGroups = computed(() => groupByAge(chatSessions.value, (item) => item.updatedAt))
  const generationHistoryGroups = computed(() => groupByAge(testGenerations.value, (item) => item.createdAt))

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

    chatBusy.value = true
    error.value = null
    genericQuery.value = ''
    const pendingId = `pending-${crypto.randomUUID()}`
    const assistantId = `assistant-${crypto.randomUUID()}`
    chatMessages.value.push({
      id: pendingId,
      role: 'user',
      content: queryText,
      createdAt: new Date().toISOString(),
    })

    try {
      captureTelemetry('chat_message', {
        workspace_id: workspaceId,
        query_length: queryText.length,
      })
      let assistantStarted = false
      const streamed = await streamChatQuery(
        {
          type: 'chat',
          workspaceId,
          query: queryText,
          sessionId: chatSessionId.value,
        },
        (delta) => {
          if (!assistantStarted) {
            assistantStarted = true
            chatMessages.value.push({
              id: assistantId,
              role: 'assistant',
              content: '',
              createdAt: new Date().toISOString(),
            })
          }
          const message = chatMessages.value.find((item) => item.id === assistantId)
          if (message) message.content += delta
        },
        (sessionId) => { chatSessionId.value = sessionId },
      )
      chatSessionId.value = streamed.sessionId || chatSessionId.value
      const response: AIQueryResponse = {
        type: 'chat',
        workspaceId,
        prompt: '',
        markdown: streamed.markdown,
        sessionId: chatSessionId.value,
      }
      return response
    } catch (caughtError) {
      chatMessages.value = chatMessages.value.filter(
        (message) => message.id !== pendingId && message.id !== assistantId,
      )
      error.value = extractMessage(caughtError, 'Failed to run query.')
      return null
    } finally {
      chatBusy.value = false
      void refreshChatSessions(workspaceId).catch(() => undefined)
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

  async function refreshChatSessions(workspaceId: string) {
    const sessions = await listChatSessions(workspaceId)
    if (workspaceStore.currentWorkspaceId === workspaceId) chatSessions.value = sessions
  }

  async function refreshTestGenerations(workspaceId: string) {
    const generations = await listTestGenerations(workspaceId)
    if (workspaceStore.currentWorkspaceId === workspaceId) testGenerations.value = generations
  }

  async function loadHistory(workspaceId: string | null) {
    chatSessions.value = []
    testGenerations.value = []
    if (!workspaceId) return
    historyBusy.value = true
    try {
      await Promise.all([refreshChatSessions(workspaceId), refreshTestGenerations(workspaceId)])
    } catch (caughtError) {
      if (workspaceStore.currentWorkspaceId === workspaceId) {
        error.value = extractMessage(caughtError, 'Failed to load saved activity.')
      }
    } finally {
      if (workspaceStore.currentWorkspaceId === workspaceId) historyBusy.value = false
    }
  }

  async function openChatSession(sessionId: string) {
    const workspaceId = workspaceStore.currentWorkspaceId
    if (!workspaceId || chatBusy.value) return
    historyBusy.value = true
    error.value = null
    try {
      const session = await getChatSession(workspaceId, sessionId)
      if (workspaceStore.currentWorkspaceId !== workspaceId) return
      chatSessionId.value = session.id
      chatMessages.value = session.messages
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to open the saved chat.')
    } finally {
      historyBusy.value = false
    }
  }

  async function openTestGeneration(item: TestGenerationSummary) {
    const workspaceId = workspaceStore.currentWorkspaceId
    if (!workspaceId) return
    historyBusy.value = true
    error.value = null
    try {
      const generation: TestGenerationRecord = await getTestGeneration(workspaceId, item.id)
      if (workspaceStore.currentWorkspaceId !== workspaceId) return
      mode.value = generation.mode
      testType.value = generation.testType === 'e2e' ? 'integration' : generation.testType
      scenario.value = generation.scenario ?? ''
      selectedFile.value = generation.target ?? ''
      const restored: AIQueryResponse = {
        type: 'test_generation', workspaceId: generation.workspaceId, prompt: '',
        markdown: generation.markdown, target: generation.target ?? generation.scenario ?? undefined,
        testType: generation.testType,
      }
      if (generation.mode === 'scenario') scenarioResult.value = restored
      else fileResult.value = restored
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to open the saved generation.')
    } finally {
      historyBusy.value = false
    }
  }

  function startNewChat() {
    chatSessionId.value = null
    chatMessages.value = []
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

    scenarioBusy.value = true
    error.value = null
    scenarioResult.value = null
    scenario.value = nextScenario

    try {
      const response = await generateTests({
        workspaceId,
        mode: 'scenario',
        scenario: nextScenario,
        type: testType.value,
      })
      scenarioResult.value = response
      void refreshTestGenerations(workspaceId).catch(() => undefined)
      return response
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to generate tests.')
      return null
    } finally {
      scenarioBusy.value = false
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
    fileBusy.value = true
    error.value = null
    fileResult.value = null

    try {
      const response = await generateTests({
        workspaceId,
        mode: 'file',
        target: target.value,
        type: testType.value,
      })
      fileResult.value = response
      void refreshTestGenerations(workspaceId).catch(() => undefined)
      return response
    } catch (caughtError) {
      error.value = extractMessage(caughtError, 'Failed to generate tests.')
      return null
    } finally {
      fileBusy.value = false
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
    (workspaceId) => {
      void loadLatestChat(workspaceId)
      void loadHistory(workspaceId)
      scenarioResult.value = null
      fileResult.value = null
    },
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
    chatBusy,
    scenarioBusy,
    fileBusy,
    historyBusy,
    error,
    result,
    chatSessionId,
    chatMessages,
    chatSessions,
    testGenerations,
    chatHistoryGroups,
    generationHistoryGroups,
    suggestedQuestions,
    suggestedScenarios,
    fileOptions,
    filteredFiles,
    runQuery,
    startNewChat,
    openChatSession,
    openTestGeneration,
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

function groupByAge<T>(items: T[], dateOf: (item: T) => string): DatedHistoryGroup<T>[] {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const sevenDaysAgo = startOfToday - 6 * 24 * 60 * 60 * 1000
  const groups: DatedHistoryGroup<T>[] = [
    { key: 'today', label: 'Today', items: [] },
    { key: 'last7Days', label: 'Last 7 days', items: [] },
    { key: 'older', label: 'More than 7 days ago', items: [] },
  ]
  for (const item of items) {
    const timestamp = new Date(dateOf(item)).getTime()
    groups[timestamp >= startOfToday ? 0 : timestamp >= sevenDaysAgo ? 1 : 2].items.push(item)
  }
  return groups.filter((group) => group.items.length)
}
