import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const args = process.argv.slice(2)
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const viteEntry = path.join(projectRoot, 'node_modules', 'vite', 'bin', 'vite.js')
const informationalCommand = args.some((argument) => ['--help', '-h', '--version', '-v'].includes(argument))

function optionValue(name) {
  const assigned = args.find((argument) => argument.startsWith(`${name}=`))
  if (assigned) return assigned.slice(name.length + 1)

  const index = args.indexOf(name)
  const following = index >= 0 ? args[index + 1] : undefined
  return following && !following.startsWith('-') ? following : undefined
}

const portText = optionValue('--port') ?? process.env.PORT ?? '8443'
const port = Number(portText)
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  console.error(`[medtwin] Invalid Vite port: ${JSON.stringify(portText)}`)
  process.exit(1)
}

const configuredHost = optionValue('--host') ?? process.env.FIGMA_DEV_SERVER_HOST ?? '0.0.0.0'
const probeHost = ['0.0.0.0', '::', 'true'].includes(configuredHost) ? '127.0.0.1' : configuredHost

function hasListener(host, targetPort) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port: targetPort })
    let settled = false

    const finish = (result) => {
      if (settled) return
      settled = true
      socket.destroy()
      resolve(result)
    }

    socket.setTimeout(750)
    socket.once('connect', () => finish(true))
    socket.once('timeout', () => finish(false))
    socket.once('error', () => finish(false))
  })
}

async function inspectMedTwinViteServer(host, targetPort) {
  const displayHost = host.includes(':') ? `[${host}]` : host
  try {
    const response = await fetch(`http://${displayHost}:${targetPort}/`, {
      signal: AbortSignal.timeout(10_000),
    })
    const html = await response.text()
    const sameProject =
      response.ok &&
      html.includes('/@vite/client') &&
      html.includes('<title>MedTwin Research Workspace</title>')
    if (!sameProject) {
      return { runnable: false, sameProject: false, reason: 'the root document did not identify MedTwin' }
    }

    const mainResponse = await fetch(`http://${displayHost}:${targetPort}/src/main.tsx`, {
      signal: AbortSignal.timeout(10_000),
    })
    if (!mainResponse.ok) {
      return {
        runnable: false,
        sameProject: true,
        reason: `/src/main.tsx returned HTTP ${mainResponse.status}`,
      }
    }

    const mainModule = await mainResponse.text()
    const rawCommonJsReact = /from\s+["']\/node_modules\/(?:react|react-dom)\//.test(mainModule)
    const optimizedReact = /\/node_modules\/\.vite\/deps\/(?:react|react-dom)/.test(mainModule)
    if (rawCommonJsReact || !optimizedReact) {
      return {
        runnable: false,
        sameProject: true,
        reason: 'React is not dependency-optimized, so the browser would receive CommonJS modules',
      }
    }

    return { runnable: true, sameProject: true, reason: '' }
  } catch (error) {
    return {
      runnable: false,
      sameProject: false,
      reason: error instanceof Error ? error.message : String(error),
    }
  }
}

if (!informationalCommand && (await hasListener(probeHost, port))) {
  const inspection = await inspectMedTwinViteServer(probeHost, port)
  if (inspection.runnable) {
    console.log(`[medtwin] Dev server is already running at http://${probeHost}:${port}; reusing it.`)
    process.exit(0)
  }

  if (inspection.sameProject) {
    console.error(`[medtwin] MedTwin is listening on port ${port}, but its runtime health check failed.`)
    console.error(`[medtwin] ${inspection.reason}.`)
    console.error('[medtwin] Stop the stale Vite process, then run npm run dev again.')
    process.exit(1)
  }

  console.error(`[medtwin] Port ${port} is occupied by a service that could not be verified as MedTwin.`)
  console.error(`[medtwin] Probe detail: ${inspection.reason}.`)
  console.error('[medtwin] Choose a free port, for example: $env:PORT = "8444"; npm run dev')
  process.exit(1)
}

if (!existsSync(viteEntry)) {
  console.error(`[medtwin] Local Vite entry point is missing: ${viteEntry}`)
  console.error('[medtwin] Run npm install before starting the development server.')
  process.exit(1)
}

const child = spawn(process.execPath, [viteEntry, ...args], {
  cwd: projectRoot,
  env: process.env,
  stdio: 'inherit',
})

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.once(signal, () => {
    if (child.exitCode === null && child.signalCode === null) child.kill(signal)
  })
}

child.once('error', (error) => {
  console.error(`[medtwin] Could not start Vite: ${error.message}`)
  process.exitCode = 1
})

child.once('exit', (code, signal) => {
  if (code !== null) {
    process.exitCode = code
    return
  }
  process.exitCode = signal === 'SIGINT' ? 130 : 1
})
