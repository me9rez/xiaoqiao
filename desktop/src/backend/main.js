// 小巧 desktop shell backend.
//
// Responsibilities are deliberately small: own the engine process, expose the
// few things the page cannot do itself (endpoint discovery, native paths,
// window/notification helpers). All agent logic stays in Python.

import { createEngine } from './engine.js'

/** @type {ReturnType<typeof createEngine> | null} */
let engine = null
/** @type {any} */
let appRef = null
let trayVisible = false

const TRAY_MENU = [
  { id: 'show', label: '显示窗口' },
  { separator: true },
  { id: 'restart', label: '重启本地引擎' },
  { id: 'datadir', label: '打开数据目录' },
  { separator: true },
  { id: 'quit', label: '退出小巧' },
]

function traySpec(title) {
  return {
    title: title || '小巧',
    // 'sf:' on macOS, an emoji silhouette on Windows. Linux trays need an
    // extra system library, so the tray is skipped there (see setupTray).
    icon: tjs.env.OS === 'Windows_NT' ? 'emoji:✳' : 'sf:sparkles',
    menu: TRAY_MENU,
  }
}

/**
 * Keep the app alive in the tray: closing the window hides it and the engine
 * keeps working (runs, routines, channels). Without a tray there would be no
 * way back, so `setHideOnClose` is only enabled once the icon is up.
 */
async function setupTray(app) {
  if (tjs.env.OS === 'Linux') return
  try {
    app.tray.set(traySpec())
    await app.setHideOnClose(true)
    trayVisible = true
    console.log('[shell] tray ready; closing the window now hides the app')
  } catch (error) {
    console.log('[shell] tray unavailable, closing the window will quit:', String(error))
  }
}

function updateTrayTitle(status) {
  if (!trayVisible || !appRef) return
  const suffix =
    status.state === 'ready' ? '' : status.restarts > 0 ? '（引擎重启中）' : '（引擎启动中）'
  try {
    appRef.tray.set(traySpec(`小巧${suffix}`))
  } catch {
    // tray went away; nothing to update
  }
}

export const api = {
  /**
   * The page's entry point: resolves once the engine is listening.
   * @returns {Promise<{url: string, token: string}>}
   */
  async gateway() {
    if (!engine) throw new Error('engine not initialised')
    return engine.endpoint()
  },

  async engineStatus() {
    return engine ? engine.status() : { state: 'stopped', endpoint: null }
  },

  async restartEngine() {
    if (!engine) throw new Error('engine not initialised')
    await engine.restart()
    return engine.endpoint()
  },

  async appInfo() {
    return {
      name: '小巧',
      version: '0.1.0',
      tinyjs: tjs.version,
      platform: tjs.env.OS,
      pid: tjs.pid,
      logPath: engine ? engine.logPath() : null,
    }
  },

  /** Open the folder holding logs and the sqlite database. */
  async openDataDir() {
    if (!appRef) throw new Error('app not initialised')
    const paths = await appRef.paths()
    const target = paths?.data || paths?.logs
    if (target) appRef.shell.open(target)
    return target || null
  },
}

/**
 * Called once the window is up.
 * @param {any} app
 */
export function init(app) {
  appRef = app
  engine = createEngine({
    onStatus: (status) => {
      updateTrayTitle(status)
      try {
        app.push('engine-status', status)
      } catch {
        // Window already gone; nothing to report to.
      }
    },
  })

  void app.paths().then((paths) => engine.start(paths))
  void setupTray(app)

  // Give the window its title before the page boots, so the taskbar never
  // flashes the default.
  app.setTitle('小巧')
}

/**
 * Tray menu clicks.
 * @param {string | null} id
 * @param {any} app
 */
export function onTray(id, app) {
  if (id === 'show') {
    app.show()
  } else if (id === 'restart') {
    void engine?.restart()
  } else if (id === 'datadir') {
    void api.openDataDir()
  } else if (id === 'quit') {
    app.quit()
  }
}
