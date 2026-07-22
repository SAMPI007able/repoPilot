import axios from 'axios'
import type {
  AIQueryRequest,
  AIQueryResponse,
  GenerateTestsRequest,
  ImpactAnalysisRequest,
  ImpactAnalysisResponse,
  RepositoryMetadata,
} from '../types/api'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
})

export async function buildWorkspace(
  githubUrl: string,
  projectDocuments: File[] = [],
): Promise<RepositoryMetadata> {
  const formData = new FormData()
  formData.append('githubUrl', githubUrl)

  projectDocuments.forEach((file) => {
    formData.append('project_docs', file)
  })

  const response = await api.post<RepositoryMetadata>('/workspaces/index', formData)
  return response.data
}

export async function queryAI(payload: AIQueryRequest): Promise<AIQueryResponse> {
  const response = await api.post<AIQueryResponse>('/ai/query', payload)
  return response.data
}

export async function generateTests(payload: GenerateTestsRequest): Promise<AIQueryResponse> {
  const response = await queryAI({
    type: 'test_generation',
    workspaceId: payload.workspaceId,
    target: payload.target,
    testType: payload.type,
  })
  return response
}

export async function analyzeImpact(payload: ImpactAnalysisRequest): Promise<ImpactAnalysisResponse> {
  const response = await api.post<ImpactAnalysisResponse>('/workspaces/impact-analysis', payload)
  return response.data
}
