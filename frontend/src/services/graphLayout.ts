import type { GraphRelationship, ParsedFileSummary } from '../types/api'

export type GraphNodeView = {
  id: string
  label: string
  short: string
  kind: string
  x: number
  y: number
}

export type GraphEdgeView = {
  id: string
  source: string
  target: string
  strength: 'normal' | 'strong'
}

export type GraphData = { nodes: GraphNodeView[]; edges: GraphEdgeView[] }
export type GraphLayoutInput = {
  parsedFiles: Array<Pick<ParsedFileSummary, 'path'>>
  relationships: Array<Pick<GraphRelationship, 'source' | 'target' | 'module'>>
}

export function createGraphData(metadata: GraphLayoutInput): GraphData {
  const allPaths = new Set(metadata.parsedFiles.map((file) => file.path))
  for (const relationship of metadata.relationships) {
    allPaths.add(relationship.source)
    allPaths.add(relationship.target)
  }
  if (!allPaths.size) return { nodes: [], edges: [] }

  const degreeByPath = new Map<string, number>()
  const neighborsByPath = new Map([...allPaths].map((path) => [path, new Set<string>()]))
  for (const relationship of metadata.relationships) {
    degreeByPath.set(relationship.source, (degreeByPath.get(relationship.source) ?? 0) + 1)
    degreeByPath.set(relationship.target, (degreeByPath.get(relationship.target) ?? 0) + 1)
    neighborsByPath.get(relationship.source)?.add(relationship.target)
    neighborsByPath.get(relationship.target)?.add(relationship.source)
  }

  const positions = layoutGraph([...allPaths], neighborsByPath, degreeByPath)
  const nodes = [...allPaths].map((path) => ({
    id: path,
    label: shortenLabel(path),
    short: buildShortLabel(path),
    kind: inferKind(path),
    x: positions.get(path)?.x ?? 0,
    y: positions.get(path)?.y ?? 0,
  }))
  const edges = metadata.relationships.map((relationship, index) => ({
    id: `${relationship.source}->${relationship.target}:${relationship.module}:${index}`,
    source: relationship.source,
    target: relationship.target,
    strength: (((degreeByPath.get(relationship.source) ?? 0) + (degreeByPath.get(relationship.target) ?? 0)) >= 5
      ? 'strong'
      : 'normal') as GraphEdgeView['strength'],
  }))
  return { nodes, edges }
}

function layoutGraph(paths: string[], neighborsByPath: Map<string, Set<string>>, degreeByPath: Map<string, number>) {
  const unseen = new Set(paths)
  const components: string[][] = []
  while (unseen.size) {
    const start = unseen.values().next().value as string
    const component: string[] = []
    const stack = [start]
    unseen.delete(start)
    while (stack.length) {
      const path = stack.pop() as string
      component.push(path)
      for (const neighbor of neighborsByPath.get(path) ?? []) {
        if (unseen.delete(neighbor)) stack.push(neighbor)
      }
    }
    components.push(component)
  }
  components.sort((left, right) => right.length - left.length)

  const layouts = components.map((component) => {
    const root = [...component].sort((left, right) =>
      (degreeByPath.get(right) ?? 0) - (degreeByPath.get(left) ?? 0) || left.localeCompare(right),
    )[0]
    const levels = new Map<string, number>([[root, 0]])
    const queue = [root]
    for (let index = 0; index < queue.length; index += 1) {
      const path = queue[index]
      for (const neighbor of neighborsByPath.get(path) ?? []) {
        if (!levels.has(neighbor)) {
          levels.set(neighbor, (levels.get(path) ?? 0) + 1)
          queue.push(neighbor)
        }
      }
    }

    const pathsByLevel = new Map<number, string[]>()
    for (const path of component) {
      const level = levels.get(path) ?? 0
      const levelPaths = pathsByLevel.get(level)
      if (levelPaths) levelPaths.push(path)
      else pathsByLevel.set(level, [path])
    }
    const local = new Map<string, { x: number; y: number }>()
    for (const [level, levelPaths] of pathsByLevel) {
      levelPaths.sort((left, right) =>
        (degreeByPath.get(right) ?? 0) - (degreeByPath.get(left) ?? 0) || left.localeCompare(right),
      )
      if (level === 0) {
        local.set(levelPaths[0], { x: 0, y: 0 })
        continue
      }
      const radius = Math.max(level * 150, (levelPaths.length * 62) / (2 * Math.PI))
      levelPaths.forEach((path, index) => {
        const angle = ((Math.PI * 2 * index) / levelPaths.length) - Math.PI / 2 + level * 0.3
        local.set(path, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius })
      })
    }
    let minX = Number.POSITIVE_INFINITY
    let maxX = Number.NEGATIVE_INFINITY
    let minY = Number.POSITIVE_INFINITY
    let maxY = Number.NEGATIVE_INFINITY
    for (const { x, y } of local.values()) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x)
      minY = Math.min(minY, y); maxY = Math.max(maxY, y)
    }
    minX -= 90; maxX += 90; minY -= 90; maxY += 90
    return { local, minX, minY, width: maxX - minX, height: maxY - minY }
  })

  const targetRowWidth = Math.max(900, Math.sqrt(paths.length) * 240)
  const positions = new Map<string, { x: number; y: number }>()
  let cursorX = 40
  let cursorY = 40
  let rowHeight = 0
  for (const layout of layouts) {
    if (cursorX > 40 && cursorX + layout.width > targetRowWidth) {
      cursorX = 40; cursorY += rowHeight + 50; rowHeight = 0
    }
    for (const [path, point] of layout.local) {
      positions.set(path, { x: cursorX + point.x - layout.minX, y: cursorY + point.y - layout.minY })
    }
    cursorX += layout.width + 50
    rowHeight = Math.max(rowHeight, layout.height)
  }
  return positions
}

function shortenLabel(path: string) {
  return path.split('/').pop()?.replace(/\.[^.]+$/, '') ?? path
}

function buildShortLabel(path: string) {
  return shortenLabel(path).replace(/[^A-Za-z0-9]/g, '').slice(0, 2) || 'na'
}

function inferKind(path: string) {
  const normalized = path.toLowerCase()
  const fileName = normalized.split('/').pop() ?? normalized
  if (normalized.includes('.test.') || normalized.includes('.spec.') || normalized.includes('/tests/')
    || normalized.includes('/src/test/') || fileName.startsWith('test_') || fileName.endsWith('_test.py')
    || fileName.endsWith('test.java')) return 'test'
  if (normalized.includes('config') || normalized.endsWith('.json')) return 'config'
  if (normalized.includes('service') || normalized.includes('controller') || normalized.includes('gateway')) return 'service'
  return 'module'
}
