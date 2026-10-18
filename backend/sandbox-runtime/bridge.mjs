import { Sandbox } from 'railway'

const input = JSON.parse(await readStdin())

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`)
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'"'"'`)}'`
}

function sdkOptions() {
  return {
    token: process.env.RAILWAY_API_TOKEN,
    environmentId: process.env.RAILWAY_SANDBOX_ENVIRONMENT_ID,
  }
}

async function execChecked(sandbox, command, stage, options = {}) {
  emit({ type: 'transition', status: stage.status, message: stage.message, state: stage.state })
  const result = await sandbox.exec(command, {
    ...options,
    maxOutputBytes: 262144,
    onStdout: (text) => emit({ type: 'log', text }),
    onStderr: (text) => emit({ type: 'log', text }),
  })
  if (result.exitCode !== 0 || result.timedOut) {
    throw new Error(`${stage.status} command failed with exit code ${result.exitCode}.`)
  }
  return result
}

async function deploy() {
  const service = input.manifest.services.find((item) => item.public)
  if (!service) throw new Error('The manifest has no public service.')
  const idleTimeoutMinutes = Math.max(
    1,
    Math.min(input.manifest.lifecycle.idleTimeoutMinutes, Number(process.env.PREVIEW_RAILWAY_MAX_IDLE_MINUTES || 5)),
  )
  const memoryGB = Math.min(memoryGBFromLimit(input.manifest.resources.memoryLimit), 2)
  const cpu = Math.min(cpuFromLimit(input.manifest.resources.cpuLimit), 2)
  let sandbox
  try {
    sandbox = await Sandbox.create({
      ...sdkOptions(),
      idleTimeoutMinutes,
      resources: { cpu, memoryGB },
      networkIsolation: 'PRIVATE',
      domains: [{ port: service.port }],
      env: {
        ...input.environment,
        PORT: String(service.port),
        HOST: '0.0.0.0',
        NODE_ENV: 'development',
      },
    })
    const state = {
      sandboxId: sandbox.id,
      environmentId: sandbox.environmentId,
      region: sandbox.region,
    }
    await execChecked(
      sandbox,
      `git clone --no-checkout --filter=blob:none -- ${shellQuote(input.repositoryUrl)} /workspace/repo`,
      { status: 'cloning', message: 'Cloning the immutable repository commit.', state },
      { timeoutSec: 600, env: gitAuthorizationEnvironment(input.repositoryUrl, input.repositoryAuthorization) },
    )
    await execChecked(
      sandbox,
      `git -C /workspace/repo checkout --detach ${shellQuote(input.commitSha)}`,
      { status: 'cloning', message: 'Checking out the indexed commit.', state },
      { timeoutSec: 120 },
    )
    await execChecked(
      sandbox,
      'corepack enable >/dev/null 2>&1 || true',
      { status: 'installing', message: 'Preparing the package manager.', state },
      { timeoutSec: 60, cwd: '/workspace/repo' },
    )
    await execChecked(
      sandbox,
      input.manifest.install.command,
      { status: 'installing', message: 'Installing locked dependencies in the isolated sandbox.', state },
      { timeoutSec: 900, cwd: '/workspace/repo' },
    )
    await execChecked(
      sandbox,
      input.manifest.build.command,
      { status: 'building', message: 'Building the web application in the isolated sandbox.', state },
      { timeoutSec: 900, cwd: '/workspace/repo' },
    )
    emit({ type: 'transition', status: 'starting', message: 'Starting the preview service.', state })
    const maximumLifetimeMinutes = Math.max(
      10,
      Math.min(
        input.manifest.lifecycle.maximumLifetimeMinutes,
        Number(process.env.PREVIEW_RAILWAY_MAX_LIFETIME_MINUTES || 60),
      ),
    )
    const runtimeCommand = `timeout --signal=TERM --kill-after=10s ${maximumLifetimeMinutes * 60}s ${service.command}`
    const handle = sandbox.exec(runtimeCommand, {
      cwd: '/workspace/repo',
      captureOutput: false,
      onStdout: (text) => emit({ type: 'log', text }),
      onStderr: (text) => emit({ type: 'log', text }),
    })
    state.sessionName = await handle.sessionName
    await handle.detach()
    const domain = sandbox.domains.find((item) => item.port === service.port)?.domain
    if (!domain) throw new Error('Railway did not assign a public sandbox domain.')
    const previewUrl = `https://${domain}`
    emit({ type: 'transition', status: 'health_checking', message: 'Waiting for the public preview health check.', state })
    await waitForHealth(`${previewUrl}${service.healthcheck.path}`, service.healthcheck.timeoutSeconds)
    emit({
      type: 'result',
      previewUrl,
      internalUrl: previewUrl,
      providerState: state,
    })
  } catch (error) {
    if (sandbox) {
      try { await sandbox.destroy() } catch {}
    }
    throw error
  }
}

async function cleanup() {
  const sandboxId = input.providerState?.sandboxId
  if (!sandboxId) {
    emit({ type: 'result' })
    return
  }
  try {
    const sandbox = await Sandbox.connect(sandboxId, sdkOptions())
    await sandbox.destroy()
  } catch (error) {
    if (!String(error?.name || '').includes('NotFound')) throw error
  }
  emit({ type: 'result' })
}

async function waitForHealth(url, timeoutSeconds) {
  const deadline = Date.now() + timeoutSeconds * 1000
  let lastError = 'not ready'
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(3000), redirect: 'manual' })
      if (response.status < 500) return
      lastError = `HTTP ${response.status}`
    } catch (error) {
      lastError = String(error?.message || error)
    }
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  throw new Error(`Preview health check timed out: ${lastError}`)
}

function memoryGBFromLimit(value) {
  if (value.endsWith('Gi')) return Number(value.slice(0, -2))
  if (value.endsWith('Mi')) return Number(value.slice(0, -2)) / 1024
  throw new Error('Unsupported memory limit.')
}

function cpuFromLimit(value) {
  if (value.endsWith('m')) return Number(value.slice(0, -1)) / 1000
  return Number(value)
}

function gitAuthorizationEnvironment(repositoryUrl, token) {
  if (!token) return {}
  const url = new URL(repositoryUrl)
  const usernameByHost = {
    'github.com': 'x-access-token',
    'www.github.com': 'x-access-token',
    'gitlab.com': 'oauth2',
    'bitbucket.org': 'x-token-auth',
  }
  const username = usernameByHost[url.hostname.toLowerCase()]
  if (!username) throw new Error('Authenticated preview cloning is not supported for this Git host.')
  const credentials = Buffer.from(`${username}:${token}`, 'utf8').toString('base64')
  return {
    GIT_TERMINAL_PROMPT: '0',
    GIT_CONFIG_COUNT: '1',
    GIT_CONFIG_KEY_0: `http.${url.protocol}//${url.host}/.extraHeader`,
    GIT_CONFIG_VALUE_0: `Authorization: Basic ${credentials}`,
  }
}

async function readStdin() {
  let value = ''
  for await (const chunk of process.stdin) value += chunk
  return value
}

let exitCode = 0
try {
  if (input.action === 'deploy') await deploy()
  else if (input.action === 'cleanup') await cleanup()
  else throw new Error(`Unsupported bridge action: ${input.action}`)
} catch (error) {
  emit({ type: 'error', message: String(error?.message || error) })
  exitCode = 1
}

await new Promise((resolve) => process.stdout.write('', resolve))
process.exit(exitCode)
