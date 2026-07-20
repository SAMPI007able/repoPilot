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

export interface RepositoryMetadata {
  repository: string
  statistics: RepositoryStatistics
  testFramework: string | null
  packageInfo: PackageInfo | null
  documentation: DocumentationAsset[]
  parsedFiles: ParsedFileSummary[]
}

export interface GenerateTestsRequest {
  workspaceId: string
  target: string
  type: 'unit' | 'integration'
}

export interface GenerateTestsResponse {
  workspaceId: string
  target: string
  type: string
  prompt: string
  markdown: string
}
