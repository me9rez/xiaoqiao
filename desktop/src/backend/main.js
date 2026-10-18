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
    }
  },

  /** Open the folder holding logs and the sqlite database. */
  async openDataDir() {
    if (!appRef) throw new Error('app not initialised')
    const paths = await appRef.paths()
    if (paths?.userData) appRef.shell.open(paths.userData)
    return paths?.userData || null
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
      try {
        app.push('engine-status', status)
      } catch {
        // Window already gone; nothing to report to.
      }
    },
  })

  void app.paths().then((paths) => engine.start(paths))

  // Give the window its title before the page boots, so the taskbar never
  // flashes the default.
  app.setTitle('小巧')
}
