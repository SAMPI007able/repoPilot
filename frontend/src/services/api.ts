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
} from '../types/api'

export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const api = axios.create({ baseURL: apiBaseUrl })

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
