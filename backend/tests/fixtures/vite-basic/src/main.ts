const root = document.querySelector<HTMLDivElement>('#app')

if (import.meta.env.FAIL_STARTUP === 'true') {
  throw new Error('Intentional fixture startup failure')
}

console.info('testforge-preview-fixture-ready')
fetch(`${import.meta.env.VITE_API_URL}/health`).catch(() => undefined)

if (root) root.textContent = 'TestForge preview fixture is healthy'
