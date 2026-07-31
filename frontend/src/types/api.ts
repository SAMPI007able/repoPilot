export interface ParsedFileSummary {
  path: string
  classes: number
  functions: number
  imports: number
  existing_tests: number
}

export interface RepositoryStatistics {
  files: number
  typescript: number
  javascript: number
}

export interface PackageInfo {
  testFramework: string | null
  dependencies: Record<string, string>
  devDependencies: Record<string, string>
  scripts: Record<string, string>
  typescriptVersion: string | null
  reactVersion: string | null
  vueVersion: string | null
}

export interface DocumentationAsset {
  path: string
  source: string
}

export interface GraphRelationship {
  source: string
  target: string
  module: string
  kind: string
}

export interface RepositoryMetadata {
  repository: string
  statistics: RepositoryStatistics
  testFramework: string | null
  packageInfo: PackageInfo | null
  documentation: DocumentationAsset[]
  parsedFiles: ParsedFileSummary[]
  relationships: GraphRelationship[]
}

export type WorkspaceBuildStageStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface WorkspaceBuildStage {
  id: string
  label: string
  detail: string
  status: WorkspaceBuildStageStatus
}

export interface WorkspaceBuildJob {
  jobId: string
  workspaceId: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stages: WorkspaceBuildStage[]
  metadata: RepositoryMetadata | null
  error: string | null
}

export interface PersistedWorkspaceSummary {
  id: string
  jobId: string | null
  repoUrl: string
  repoName: string
  status: 'queued' | 'running' | 'ready' | 'failed'
  statistics: RepositoryStatistics
  stages: WorkspaceBuildStage[]
  error: string | null
  createdAt: string
  updatedAt: string
}

export interface PersistedWorkspaceDetail extends PersistedWorkspaceSummary {
  metadata: RepositoryMetadata
}

export interface ImpactedComponent {
  name: string
  path: string
  reason: string
}

export interface ImpactAnalysisRequest {
  workspaceId: string
  target: string
}

export interface ImpactAnalysisResponse {
  workspaceId: string
  target: string
  affectedComponents: ImpactedComponent[]
  potentiallyAffectedTests: string[]
  risk: 'low' | 'medium' | 'high'
  summary: string
}

export type AIQueryType = 'chat' | 'test_generation'

export interface AIQueryRequest {
  type: AIQueryType
  workspaceId: string
  query?: string
  target?: string
  scenario?: string
  generationMode?: 'file' | 'scenario'
  testType?: 'unit' | 'integration' | 'e2e'
}

export interface AIQueryResponse {
  type: string
  workspaceId: string
  prompt: string
  markdown: string
  target?: string
  testType?: string
}

export interface GenerateTestsRequest {
  workspaceId: string
  mode: 'file' | 'scenario'
  target?: string
  scenario?: string
  type: 'unit' | 'integration'
}

export interface GenerateTestsResponse {
  workspaceId: string
  target: string
  type: string
  prompt: string
  markdown: string
}
