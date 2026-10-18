import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  callShell,
  desktopAvailable,
  getSystemTheme,
  notifyDesktop,
  onFilesDropped,
  onMenuClick,
  onSystemTheme,
  pickFolder,
  quitApp,
  setAppMenu,
} from '@/services/desktop'

type TinyWindow = { tiny?: Record<string, unknown> }

describe('desktop bridge without a shell', () => {
  afterEach(() => {
    delete (globalThis as unknown as TinyWindow).tiny
  })

  it('reports no shell and degrades every helper', async () => {
    expect(desktopAvailable()).toBe(false)
    await expect(callShell('openDataDir')).resolves.toBeUndefined()
    await expect(notifyDesktop('t', 'b')).resolves.toBe(false)
    await expect(pickFolder()).resolves.toBeNull()
    await expect(getSystemTheme()).resolves.toBeNull()
    expect(() => setAppMenu([])).not.toThrow()
    expect(() => quitApp()).not.toThrow()
    expect(onMenuClick(() => {})()).toBeUndefined()
    expect(onFilesDropped(() => {})()).toBeUndefined()
    expect(onSystemTheme(() => {})()).toBeUndefined()
  })
})

describe('desktop bridge with a shell', () => {
  afterEach(() => {
    delete (globalThis as unknown as TinyWindow).tiny
  })

  it('routes calls, notifications, folders and theme through tiny', async () => {
    const notify = vi.fn().mockResolvedValue(true)
    const call = vi.fn().mockResolvedValue('/data')
    const pick = vi.fn().mockResolvedValue('D:\\work')
    const menuSet = vi.fn().mockResolvedValue(undefined)
    const quit = vi.fn()
    const offMenu = vi.fn()
    const offDrop = vi.fn()
    const offTheme = vi.fn()

    ;(globalThis as unknown as TinyWindow).tiny = {
      notify,
      quit,
      api: { call },
      dialog: { pickFolder: pick },
      theme: { get: vi.fn().mockResolvedValue({ dark: true }), on: vi.fn().mockReturnValue(offTheme) },
      menu: { set: menuSet, on: vi.fn().mockReturnValue(offMenu) },
      win: { onDrop: vi.fn().mockReturnValue(offDrop) },
    }

    expect(desktopAvailable()).toBe(true)
    await expect(callShell<string>('openDataDir')).resolves.toBe('/data')
    expect(call).toHaveBeenCalledWith('openDataDir', undefined)

    await notifyDesktop('标题', '正文', { id: 'x' })
    expect(notify).toHaveBeenCalledWith('标题', '正文', { id: 'x' })

    await expect(pickFolder()).resolves.toBe('D:\\work')
    await expect(getSystemTheme()).resolves.toBe(true)

    await setAppMenu([{ title: '文件' }])
    expect(menuSet).toHaveBeenCalledWith([{ title: '文件' }])

    expect(onMenuClick(() => {})).toBe(offMenu)
    expect(onFilesDropped(() => {})).toBe(offDrop)
    expect(onSystemTheme(() => {})).toBe(offTheme)

    quitApp()
    expect(quit).toHaveBeenCalled()
  })

  it('survives a shell that throws', async () => {
    ;(globalThis as unknown as TinyWindow).tiny = {
      notify: vi.fn().mockRejectedValue(new Error('nope')),
      dialog: {
        pickFolder: vi.fn().mockRejectedValue(new Error('nope')),
      },
      theme: { get: vi.fn().mockRejectedValue(new Error('nope')) },
    }

    await expect(notifyDesktop('t')).resolves.toBe(false)
    await expect(pickFolder()).resolves.toBeNull()
    await expect(getSystemTheme()).resolves.toBeNull()
  })
})

