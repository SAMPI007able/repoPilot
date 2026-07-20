import axios from 'axios'
import type { GenerateTestsRequest, GenerateTestsResponse, RepositoryMetadata } from '../types/api'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ,
  headers: {
    'Content-Type': 'application/json',
  },
})

export async function buildWorkspace(githubUrl: string): Promise<RepositoryMetadata> {
  const response = await api.post<RepositoryMetadata>('/workspaces/index', {
    githubUrl,
  })

  return response.data
}

export async function generateTests(payload: GenerateTestsRequest): Promise<GenerateTestsResponse> {
  const response = await api.post<GenerateTestsResponse>('/ai/generate-tests', payload)
  return response.data
}
