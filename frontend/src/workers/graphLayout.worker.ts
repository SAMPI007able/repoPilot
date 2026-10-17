import { createGraphData } from '../services/graphLayout'
import type { GraphLayoutInput } from '../services/graphLayout'

type Request = {
  id: number
  metadata: GraphLayoutInput
}

self.onmessage = ({ data }: MessageEvent<Request>) => {
  self.postMessage({ id: data.id, graph: createGraphData(data.metadata) })
}
