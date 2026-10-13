import axios from 'axios'
import type {
  AIQueryRequest,
  AIQueryResponse,
  GenerateTestsRequest,
  ImpactAnalysisRequest,
  ImpactAnalysisResponse,
  PersistedWorkspaceDetail,
  PersistedWorkspaceSummary,
  PreviewEnvironment,
  PreviewLogs,
  RuntimeManifest,
  RuntimeManifestRecord,
  WorkspaceBuildJob,
  CurrentUser,
  ProviderConnection,
  ProviderRepository,
  SourceControlProvider,
  FeatureFlagsResponse,
  ChatSession,
  AdminBrowserSession,
  AdminDashboard,
  AdminFeatureFlag,
  AdminLog,
  AdminPreview,
  AdminUsage,
  AdminUser,
} from '../types/api'

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const api = axios.create({ baseURL: apiBaseUrl })
let accessTokenProvider: () => Promise<string | null> = async () => null
let authenticationFailureHandler: () => Promise<void> = async () => undefined

export interface APIErrorEnvelope {
  code?: string
  message?: string
  details?: { resetAt?: string; [key: string]: unknown }
}

export function extractAPIError(error: unknown, fallback: string): { message: string; code?: string; status?: number } {
  if (typeof error === 'object' && error && 'response' in error) {
    const response = (error as { response?: { status?: number; data?: APIErrorEnvelope | { detail?: string } } }).response
    const data = response?.data
    if (data && 'message' in data && data.message) {
      const resetAt = data.details?.resetAt
      const resetMessage = resetAt
        ? ` Resets ${new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(resetAt))}.`
        : ''
      return { message: `${data.message}${resetMessage}`, code: data.code, status: response?.status }
    }
    if (data && 'detail' in data && typeof data.detail === 'string') {
      return { message: data.detail, status: response?.status }
    }
    return { message: fallback, status: response?.status }
  }
  return { message: error instanceof Error ? error.message : fallback }
}

export function setAccessTokenProvider(provider: () => Promise<string | null>) {
  accessTokenProvider = provider
}

export function setAuthenticationFailureHandler(handler: () => Promise<void>) {
  authenticationFailureHandler = handler
}

api.interceptors.request.use(async (config) => {
  const token = await accessTokenProvider()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    const status = typeof error === 'object' && error && 'response' in error
      ? (error as { response?: { status?: number } }).response?.status
      : undefined
    if (status === 401) await authenticationFailureHandler()
    return Promise.reject(error)
  },
)

export async function getCurrentUser(): Promise<CurrentUser> {
  return (await api.get<CurrentUser>('/me')).data
}

export async function getFeatureFlags(): Promise<FeatureFlagsResponse> {
  return (await api.get<FeatureFlagsResponse>('/feature-flags')).data
}

export async function listProviderConnections(): Promise<ProviderConnection[]> {
  return (await api.get<ProviderConnection[]>('/integrations')).data
}

export async function connectProvider(provider: SourceControlProvider): Promise<string> {
  return (await api.get<{ authorizationUrl: string }>(`/integrations/${provider}/connect`)).data.authorizationUrl
}

export async function disconnectProvider(provider: SourceControlProvider): Promise<void> {
  await api.delete(`/integrations/${provider}`)
}

export async function listProviderRepositories(provider: SourceControlProvider): Promise<ProviderRepository[]> {
  return (await api.get<ProviderRepository[]>(`/integrations/${provider}/repos`, {
    params: { refresh: Date.now() },
  })).data
}

export async function listProviderBranches(repository: ProviderRepository): Promise<string[]> {
  return (await api.get<string[]>(`/integrations/${repository.provider}/branches`, {
    params: { owner: repository.owner, repo: repository.name },
  })).data
}

export async function importProviderRepository(
  repository: ProviderRepository,
  branch?: string,
): Promise<WorkspaceBuildJob> {
  return (await api.post<WorkspaceBuildJob>(`/integrations/${repository.provider}/repos/import`, {
    owner: repository.owner,
    repo: repository.name,
    ...(branch ? { branch } : {}),
  })).data
}

export async function getAccessToken(): Promise<string | null> {
  return accessTokenProvider()
}

export async function startWorkspaceBuild(
  githubUrl: string,
  projectDocuments: File[] = [],
): Promise<WorkspaceBuildJob> {
  const formData = new FormData()
  formData.append('githubUrl', githubUrl)

  projectDocuments.forEach((file) => {
    formData.append('project_docs', file)
  })

  const response = await api.post<WorkspaceBuildJob>('/workspaces/index', formData)
  return response.data
}

export async function getWorkspaceBuild(jobId: string): Promise<WorkspaceBuildJob> {
  const response = await api.get<WorkspaceBuildJob>(`/workspaces/index/${jobId}`)
  return response.data
}

export async function listPersistedWorkspaces(): Promise<PersistedWorkspaceSummary[]> {
  const response = await api.get<PersistedWorkspaceSummary[]>('/workspaces')
  return response.data
}

export async function getPersistedWorkspace(workspaceId: string): Promise<PersistedWorkspaceDetail> {
  const response = await api.get<PersistedWorkspaceDetail>(`/workspaces/${workspaceId}`)
  return response.data
}

export async function deletePersistedWorkspace(workspaceId: string): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}`)
}

export async function analyzeRuntimeManifest(
  workspaceId: string,
  instructions: string,
): Promise<RuntimeManifestRecord> {
  const response = await api.post<RuntimeManifestRecord>(
    `/workspaces/${workspaceId}/runtime-manifest/analyze`,
    { instructions: instructions.trim() || null },
  )
  return response.data
}

export async function getRuntimeManifest(workspaceId: string): Promise<RuntimeManifestRecord> {
  const response = await api.get<RuntimeManifestRecord>(
    `/workspaces/${workspaceId}/runtime-manifest`,
  )
  return response.data
}

export async function updateRuntimeManifest(
  workspaceId: string,
  manifest: RuntimeManifest,
  expectedRevision: number,
): Promise<RuntimeManifestRecord> {
  const response = await api.put<RuntimeManifestRecord>(
    `/workspaces/${workspaceId}/runtime-manifest`,
    { manifest, expectedRevision },
  )
  return response.data
}

export async function approveRuntimeManifest(
  workspaceId: string,
  expectedRevision: number,
): Promise<RuntimeManifestRecord> {
  const response = await api.post<RuntimeManifestRecord>(
    `/workspaces/${workspaceId}/runtime-manifest/approve`,
    { expectedRevision },
  )
  return response.data
}

export async function createPreview(
  workspaceId: string,
  environment: Record<string, string>,
  idempotencyKey: string,
): Promise<PreviewEnvironment> {
  const response = await api.post<PreviewEnvironment>(
    `/workspaces/${workspaceId}/previews`,
    { environment },
    { headers: { 'Idempotency-Key': idempotencyKey } },
  )
  return response.data
}

export async function getLatestPreview(workspaceId: string): Promise<PreviewEnvironment> {
  return (await api.get<PreviewEnvironment>(`/workspaces/${workspaceId}/previews/latest`)).data
}

export async function getPreview(previewId: string): Promise<PreviewEnvironment> {
  return (await api.get<PreviewEnvironment>(`/previews/${previewId}`)).data
}

export async function getPreviewLogs(previewId: string): Promise<PreviewLogs> {
  return (await api.get<PreviewLogs>(`/previews/${previewId}/logs`)).data
}

export async function stopPreview(previewId: string): Promise<PreviewEnvironment> {
  return (await api.post<PreviewEnvironment>(
    `/previews/${previewId}/stop`, {},
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  )).data
}

export async function extendPreview(previewId: string, minutes = 30): Promise<PreviewEnvironment> {
  return (await api.post<PreviewEnvironment>(
    `/previews/${previewId}/extend`, { minutes },
    { headers: { 'Idempotency-Key': crypto.randomUUID() } },
  )).data
}

export async function queryAI(payload: AIQueryRequest): Promise<AIQueryResponse> {
  const response = await api.post<AIQueryResponse>('/ai/query', payload)
  return response.data
}

export interface ChatStreamResult {
  sessionId: string | null
  markdown: string
}

interface ChatStreamEvent {
  type: 'metadata' | 'delta' | 'done' | 'error'
  sessionId?: string
  text?: string
  message?: string
}

export async function streamChatQuery(
  payload: AIQueryRequest,
  onDelta: (text: string) => void,
  onSession: (sessionId: string) => void,
): Promise<ChatStreamResult> {
  const token = await accessTokenProvider()
  const response = await fetch(`${apiBaseUrl}/ai/query/stream`, {
    method: 'POST',
    headers: {
      Accept: 'application/x-ndjson',
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    if (response.status === 401) await authenticationFailureHandler()
    let message = `Chat request failed with status ${response.status}.`
    try {
      const body = await response.json() as APIErrorEnvelope & { detail?: string }
      message = body.message || body.detail || message
    } catch {
      // Preserve the status-based message when the response is not JSON.
    }
    throw new Error(message)
  }
  if (!response.body) throw new Error('The browser did not receive a streaming response body.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let markdown = ''
  let sessionId: string | null = null
  let completed = false

  const consume = (line: string) => {
    if (!line.trim()) return
    const event = JSON.parse(line) as ChatStreamEvent
    if (event.sessionId) {
      sessionId = event.sessionId
      onSession(event.sessionId)
    }
    if (event.type === 'delta' && event.text) {
      markdown += event.text
      onDelta(event.text)
    } else if (event.type === 'error') {
      throw new Error(event.message || 'The AI response was interrupted.')
    } else if (event.type === 'done') {
      completed = true
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    let newline = buffer.indexOf('\n')
    while (newline >= 0) {
      consume(buffer.slice(0, newline))
      buffer = buffer.slice(newline + 1)
      newline = buffer.indexOf('\n')
    }
    if (done) break
  }
  if (buffer.trim()) consume(buffer)
  if (!completed) throw new Error('The AI response ended before completion.')

  return { sessionId, markdown }
}

export async function getLatestChatSession(workspaceId: string): Promise<ChatSession | null> {
  try {
    return (await api.get<ChatSession>(`/workspaces/${workspaceId}/chat-sessions/latest`)).data
  } catch (error) {
    if (extractAPIError(error, '').status === 404) return null
    throw error
  }
}

export async function generateTests(payload: GenerateTestsRequest): Promise<AIQueryResponse> {
  const response = await queryAI({
    type: 'test_generation',
    workspaceId: payload.workspaceId,
    generationMode: payload.mode,
    target: payload.target,
    scenario: payload.scenario,
    testType: payload.type,
  })
  return response
}

export async function analyzeImpact(payload: ImpactAnalysisRequest): Promise<ImpactAnalysisResponse> {
  const response = await api.post<ImpactAnalysisResponse>('/workspaces/impact-analysis', payload)
  return response.data
}

export async function getAdminDashboard(): Promise<AdminDashboard> { return (await api.get('/admin/dashboard')).data }
export async function listAdminUsers(query = ''): Promise<AdminUser[]> { return (await api.get('/admin/users', { params: { q: query } })).data }
export async function setAdminUserSuspended(userId: string, suspended: boolean): Promise<AdminUser> { return (await api.put(`/admin/users/${userId}/status`, { suspended })).data }
export async function deleteAdminUser(userId: string): Promise<void> { await api.delete(`/admin/users/${userId}`) }
export async function listAdminPreviews(): Promise<AdminPreview[]> { return (await api.get('/admin/previews')).data }
export async function terminateAdminPreview(previewId: string): Promise<void> { await api.post(`/admin/previews/${previewId}/terminate`) }
export async function listAdminBrowserSessions(): Promise<AdminBrowserSession[]> { return (await api.get('/admin/browser-sessions')).data }
export async function terminateAdminBrowserSession(sessionId: string): Promise<void> { await api.post(`/admin/browser-sessions/${sessionId}/terminate`) }
export async function listAdminUsage(): Promise<AdminUsage[]> { return (await api.get('/admin/usage')).data }
export async function listAdminFeatureFlags(): Promise<AdminFeatureFlag[]> { return (await api.get('/admin/feature-flags')).data }
export async function updateAdminFeatureFlag(key: string, enabled: boolean): Promise<AdminFeatureFlag> { return (await api.put(`/admin/feature-flags/${key}`, { enabled })).data }
export async function listAdminLogs(): Promise<AdminLog[]> { return (await api.get('/admin/logs')).data }
