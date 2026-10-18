// Spawns and supervises the Python engine (the "sidecar").
//
// The page never talks to this module directly: it asks `api.gateway()` for an
// endpoint, which only resolves once the engine has printed its ready line.
//
// Two launches are supported:
//   packaged  -> executables/xiaoqiao-core[.exe] shipped next to the app
//   dev       -> `uv run --project <repo>/python python -m xiaoqiao.main`
//
// The engine receives its handshake token through the environment, so it never
// shows up in a process list.

const IS_WIN = tjs.env.OS === 'Windows_NT'
const READY_PREFIX = 'WS READY '
const MAX_RESTARTS = 3
const LOG_TAIL = 40
const LOG_KEEP = 400

function randomToken() {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

async function fileExists(path) {
  try {
    await tjs.stat(path)
    return true
  } catch {
    return false
  }
}

async function resolveRepoRoot() {
  // Dev runs from `desktop/`, a build runs from `desktop/dist/`. Walk up until
  // the Python package is found so both layouts work without extra config.
  let dir = tjs.cwd.replace(/[\\/]+$/, '')
  for (let depth = 0; depth < 5; depth += 1) {
    if (await fileExists(`${dir}/python/pyproject.toml`)) return dir
    const parent = dir.replace(/[\\/][^\\/]+$/, '')
    if (parent === dir) break
    dir = parent
  }
  return tjs.cwd
}

async function resolveCommand(paths) {
  const exe = paths?.executables ? `${paths.executables}/${IS_WIN ? 'xiaoqiao-core.exe' : 'xiaoqiao-core'}` : null
  if (exe && (await fileExists(exe))) {
    return { argv: [exe], cwd: paths?.data || tjs.cwd, mode: 'packaged' }
  }

  const repo = await resolveRepoRoot()
  return {
    argv: ['uv', 'run', '--project', `${repo}/python`, 'python', '-m', 'xiaoqiao.main'],
    cwd: repo,
    mode: 'dev',
  }
}

/** Read a piped stream line by line (txiki streams have no for-await). */
async function pumpLines(stream, onLine) {
  if (!stream) return
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let index = buffer.indexOf('\n')
    while (index >= 0) {
      onLine(buffer.slice(0, index).replace(/\r$/, ''))
      buffer = buffer.slice(index + 1)
      index = buffer.indexOf('\n')
    }
  }
  if (buffer.trim()) onLine(buffer)
}

export function createEngine({ onStatus } = {}) {
  const token = randomToken()
  /** @type {{url: string, token: string} | null} */
  let endpoint = null
  /** @type {{code: number | null, at: number} | null} */
  let lastExit = null
  /** @type {string[]} */
  const logTail = []
  let proc = null
  let restarts = 0
  let stopping = false
  /** @type {Array<(value: any) => void>} */
  let waiters = []
  /** @type {Array<(error: Error) => void>} */
  let rejecters = []

  function status() {
    return {
      state: endpoint ? 'ready' : proc ? 'starting' : 'stopped',
      endpoint: endpoint ? endpoint.url : null,
      pid: proc ? proc.pid : null,
      restarts,
      lastExit,
      log: logTail.slice(-LOG_TAIL),
    }
  }

  function notify() {
    onStatus?.(status())
    void persistLog()
  }

  /** Append one engine line (timestamped) to the in-memory log. */
  function logLine(line) {
    logTail.push(`${new Date().toISOString()} ${line}`)
    if (logTail.length > LOG_KEEP) logTail.shift()
  }

  function settle(value, error) {
    const pendingResolve = waiters
    const pendingReject = rejecters
    waiters = []
    rejecters = []
    if (error) pendingReject.forEach((fn) => fn(error))
    else pendingResolve.forEach((fn) => fn(value))
  }

  async function start() {
    const { argv, cwd, mode } = await resolveCommand(await safePaths())
    const fullArgs = [...argv, '--desktop', '--ws-port', '0', '--exit-on-stdin-eof']
    if (mode === 'dev') fullArgs.push('--log-level', 'INFO')

    const env = { ...tjs.env, XIAOQIAO_TOKEN: token, PYTHONUNBUFFERED: '1' }
    logLine(`[shell] starting ${mode} engine: ${fullArgs.join(' ')}`)
    console.log(`[shell] starting ${mode} engine (cwd=${cwd})`)

    proc = tjs.spawn(fullArgs, {
      cwd,
      env,
      stdin: 'pipe',
      stdout: 'pipe',
      stderr: 'pipe',
    })

    void pumpLines(proc.stdout, (line) => {
      logLine(line)
      if (line.startsWith(READY_PREFIX)) {
        const url = line.slice(READY_PREFIX.length).trim()
        endpoint = { url, token }
        restarts = 0
        console.log(`[shell] engine ready at ${url}`)
        notify()
        settle(endpoint)
      }
    })
    void pumpLines(proc.stderr, (line) => {
      logLine(line)
      // Keep the dev terminal readable: only lifecycle and error lines.
      // (Python prefixes log lines with "INFO <logger>:", so match anywhere.)
      if (/(WS READY|Client (connected|authenticated)|Rejected unauthenticated|Traceback|ERROR|Shutdown requested)/.test(line)) {
        console.log(`[engine] ${line}`)
      }
      if (line.startsWith(READY_PREFIX)) {
        const url = line.slice(READY_PREFIX.length).trim()
        endpoint = { url, token }
        restarts = 0
        console.log(`[shell] engine ready at ${url}`)
        notify()
        settle(endpoint)
      }
    })

    notify()
    void proc.wait().then((code) => {
      proc = null
      endpoint = null
      lastExit = { code: typeof code === 'number' ? code : null, at: Date.now() }
      console.log(`[shell] engine exited (code=${lastExit.code})`)
      notify()
      if (stopping) return
      if (restarts >= MAX_RESTARTS) {
        settle(null, new Error(`engine exited (${lastExit.code}) and gave up after ${restarts} restarts`))
        return
      }
      restarts += 1
      const delay = 1000 * 2 ** (restarts - 1)
      setTimeout(() => {
        if (!stopping) void start()
      }, delay)
    })
  }

  let paths = null
  async function safePaths() {
    return paths
  }

  /** tinyjs exposes `logs` (and `data`); `userData` does not exist. */
  function logDir() {
    return paths?.logs || paths?.data || null
  }

  /** Keep a copy of the engine's output next to the app's data. */
  async function persistLog() {
    const dir = logDir()
    if (!dir) return
    try {
      // The directory may not exist yet on a first run.
      await tjs.makeDir(dir, { recursive: true })
      await tjs.writeFile(`${dir}/engine.log`, `${logTail.join('\n')}\n`)
    } catch (error) {
      console.log('[shell] engine log write failed:', String(error))
    }
  }

  function logPath() {
    const dir = logDir()
    return dir ? `${dir}/engine.log` : null
  }

  return {
    token,

    async start(userPaths) {
      paths = userPaths || paths
      await start()
    },

    /** Resolve once the engine is listening; rejects if it never comes up. */
    endpoint() {
      if (endpoint) return Promise.resolve(endpoint)
      return new Promise((resolve, reject) => {
        waiters.push(resolve)
        rejecters.push(reject)
        setTimeout(() => {
          const index = rejecters.indexOf(reject)
          if (index >= 0) {
            rejecters.splice(index, 1)
            waiters.splice(index, 1)
            reject(new Error('engine did not report ready in time'))
          }
        }, 30000)
      })
    },

    status,

    logPath,

    async restart() {
      await this.stop()
      stopping = false
      endpoint = null
      start()
    },

    async stop() {
      stopping = true
      if (proc) {
        try {
          proc.kill()
        } catch {
          // already gone
        }
        proc = null
      }
      endpoint = null
      notify()
    },
  }
}
