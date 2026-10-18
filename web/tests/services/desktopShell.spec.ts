import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Router } from 'vue-router'

import { onComposerInsert } from '@/services/composer'
import { setupDesktopShell } from '@/services/desktopShell'
import { gatewayService } from '@/services/gateway'

type Handler = (...args: unknown[]) => void
type TinyWindow = { tiny?: Record<string, unknown> }

function fakeRouter(): Router {
  return { push: vi.fn().mockResolvedValue(undefined) } as unknown as Router
}

describe('setupDesktopShell', () => {
  afterEach(() => {
    delete (globalThis as unknown as TinyWindow).tiny
    vi.restoreAllMocks()
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
  })

  it('is a no-op in a browser', () => {
    const teardown = setupDesktopShell(fakeRouter())
    expect(() => teardown()).not.toThrow()
  })

  it('installs the app menu and routes menu clicks', async () => {
    let menuHandler: Handler = () => {}
    const menuSet = vi.fn().mockResolvedValue(undefined)
    const notify = vi.fn().mockResolvedValue(true)
    ;(globalThis as unknown as TinyWindow).tiny = {
      notify,
      menu: {
        set: menuSet,
        on: vi.fn((fn: Handler) => {
          menuHandler = fn
          return () => {}
        }),
      },
      win: { onDrop: vi.fn(() => () => {}) },
    }
    const router = fakeRouter()

    const teardown = setupDesktopShell(router)
    await Promise.resolve()

    const menus = menuSet.mock.calls[0][0] as { title?: string; role?: string }[]
    expect(menus.map((m) => m.title)).toEqual(['文件', '编辑', '视图'])
    expect(menus[1].role).toBe('edit')

    menuHandler('open-settings')
    expect(router.push).toHaveBeenCalledWith('/settings')

    menuHandler('new-session')
    expect(router.push).toHaveBeenCalledWith('/')

    teardown()
  })

  it('drops file paths into the composer', async () => {
    let dropHandler: Handler = () => {}
    ;(globalThis as unknown as TinyWindow).tiny = {
      menu: { set: vi.fn(), on: vi.fn(() => () => {}) },
      win: {
        onDrop: vi.fn((fn: Handler) => {
          dropHandler = fn
          return () => {}
        }),
      },
    }

    const received: string[] = []
    const off = onComposerInsert((text) => received.push(text))

    const teardown = setupDesktopShell(fakeRouter())
    dropHandler(['D:\\a.txt', 'D:\\b.txt'])

    expect(received).toEqual(['D:\\a.txt\nD:\\b.txt'])
    off()
    teardown()
  })

  it('notifies about approvals only while the window is hidden', async () => {
    const notify = vi.fn().mockResolvedValue(true)
    ;(globalThis as unknown as TinyWindow).tiny = {
      notify,
      menu: { set: vi.fn(), on: vi.fn(() => () => {}) },
      win: { onDrop: vi.fn(() => () => {}) },
    }
    const handlers: Record<string, Handler> = {}
    vi.spyOn(gatewayService, 'on').mockImplementation((event: string, cb: Handler) => {
      handlers[event] = cb
      return () => {}
    })

    const teardown = setupDesktopShell(fakeRouter())
    const approval = {
      type: 'approval_requested',
      approvalId: 'ap1',
      callId: 'c1',
      botId: 'b1',
      groupId: null,
      runId: 'r1',
      tool: 'run_command',
    }

    // Window in the foreground: no banner for something already on screen.
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    handlers.approval_requested(approval)
    expect(notify).not.toHaveBeenCalled()

    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    handlers.approval_requested(approval)
    await Promise.resolve()
    expect(notify).toHaveBeenCalledTimes(1)
    expect(notify.mock.calls[0][0]).toBe('需要审批')
    expect(String(notify.mock.calls[0][1])).toContain('run_command')

    // The same approval must not buzz twice.
    handlers.approval_requested(approval)
    await Promise.resolve()
    expect(notify).toHaveBeenCalledTimes(1)

    teardown()
  })
})


