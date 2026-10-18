/**
 * Typed access to the tinyjs desktop shell.
 *
 * Everything here is optional: in a browser (`xiaoqiao --web`) there is no
 * bridge and each helper degrades to a no-op. Keeping every `window.tiny`
 * access in one module means the rest of the app never has to branch on host.
 */

export interface MenuItemSpec {
  id?: string
  label?: string
  key?: string
  enabled?: boolean
  checked?: boolean
  separator?: boolean
  role?: string
  submenu?: MenuItemSpec[]
}

export interface MenuSpec {
  title?: string
  items?: MenuItemSpec[]
  role?: string
}

interface Bridge {
  notify?: (title: string, body?: string, opts?: { id?: string; sound?: boolean }) => Promise<boolean>
  quit?: () => void | Promise<void>
  /** The app menu lives at the top level (`tiny.menu`), not under `tiny.app`. */
  menu?: {
    set?: (menus: MenuSpec[]) => Promise<void>
    on?: (fn: (id: string) => void) => () => void
    get?: (id: string) => Promise<{ exists: boolean; label?: string }>
  }
  win?: {
    onDrop?: (fn: (paths: string[]) => void) => () => void
  }
  theme?: {
    get?: () => Promise<{ dark: boolean } | null>
    on?: (fn: (dark: boolean) => void) => () => void
  }
  dialog?: {
    pickFolder?: () => Promise<string | null>
  }
  api?: {
    call?: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
  }
}

function bridge(): Bridge | null {
  const tiny = (globalThis as unknown as { tiny?: Bridge }).tiny
  return tiny && typeof tiny === 'object' ? tiny : null
}

export function desktopAvailable(): boolean {
  return bridge() !== null
}

/** Call a shell method; resolves to undefined when there is no shell. */
export async function callShell<T = unknown>(method: string, params?: Record<string, unknown>): Promise<T | undefined> {
  const call = bridge()?.api?.call
  if (!call) return undefined
  return call<T>(method, params)
}

/** Native notification. Fire-and-forget: never rejects, false when undelivered. */
export async function notifyDesktop(
  title: string,
  body?: string,
  opts?: { id?: string; sound?: boolean },
): Promise<boolean> {
  const notify = bridge()?.notify
  if (!notify) return false
  try {
    return await notify(title, body, opts)
  } catch {
    return false
  }
}

export async function setAppMenu(menus: MenuSpec[]): Promise<void> {
  try {
    await bridge()?.menu?.set?.(menus)
  } catch {
    // A failed menu install must never break the page.
  }
}

export function onMenuClick(handler: (id: string) => void): () => void {
  const on = bridge()?.menu?.on
  if (!on) return () => {}
  return on(handler)
}

/** Files dropped on the window, as real filesystem paths. */
export function onFilesDropped(handler: (paths: string[]) => void): () => void {
  const onDrop = bridge()?.win?.onDrop
  if (!onDrop) return () => {}
  return onDrop(handler)
}

export async function pickFolder(): Promise<string | null> {
  try {
    return (await bridge()?.dialog?.pickFolder?.()) ?? null
  } catch {
    return null
  }
}

/** Current OS appearance, or null when the host cannot tell us. */
export async function getSystemTheme(): Promise<boolean | null> {
  try {
    const theme = await bridge()?.theme?.get?.()
    return typeof theme?.dark === 'boolean' ? theme.dark : null
  } catch {
    return null
  }
}

export function onSystemTheme(handler: (dark: boolean) => void): () => void {
  const on = bridge()?.theme?.on
  if (!on) return () => {}
  return on(handler)
}

export function quitApp(): void {
  void bridge()?.quit?.()
}
