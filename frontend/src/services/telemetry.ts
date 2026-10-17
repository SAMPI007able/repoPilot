type TelemetryProperties = Record<string, unknown>

let clientPromise: Promise<typeof import('posthog-js')['default'] | null> | null = null
let activated = false
const pendingActions: Array<(client: NonNullable<Awaited<ReturnType<typeof loadClient>>>) => void> = []

function loadClient() {
  const apiKey = import.meta.env.VITE_POSTHOG_API_KEY || ''
  if (!apiKey || import.meta.env.DEV) return Promise.resolve(null)
  if (!clientPromise) {
    clientPromise = import('posthog-js').then(({ default: posthog }) => {
      posthog.init(apiKey, {
        api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
        autocapture: true,
        capture_pageview: true,
      })
      return posthog
    }).catch(() => null)
  }
  return clientPromise
}

export function initializeTelemetry() {
  const schedule = window.requestIdleCallback
    ? (callback: () => void) => window.requestIdleCallback(callback, { timeout: 3000 })
    : (callback: () => void) => window.setTimeout(callback, 1500)
  schedule(() => {
    activated = true
    void loadClient().then((client) => {
      const actions = pendingActions.splice(0)
      if (!client) return
      actions.forEach((action) => action(client))
    })
  })
}

export function captureTelemetry(event: string, properties: TelemetryProperties = {}) {
  withClient((client) => client.capture(event, properties))
}

export function identifyTelemetry(id: string, properties: TelemetryProperties = {}) {
  withClient((client) => client.identify(id, properties))
}

export function resetTelemetry() {
  withClient((client) => client.reset())
}

function withClient(action: (client: NonNullable<Awaited<ReturnType<typeof loadClient>>>) => void) {
  if (!activated) {
    pendingActions.push(action)
    return
  }
  void loadClient().then((client) => { if (client) action(client) })
}
