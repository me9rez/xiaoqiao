/**
 * Desktop-only integration: native menu, drag & drop, notifications.
 *
 * Called once from `main.ts`. In a browser every helper is a no-op, so this
 * module never needs a host check of its own beyond the early return.
 */

import type { Router } from 'vue-router'

import { insertIntoComposer } from './composer'
import {
  callShell,
  desktopAvailable,
  notifyDesktop,
  onFilesDropped,
  onMenuClick,
  quitApp,
  setAppMenu,
  type MenuSpec,
} from './desktop'
import { gatewayService } from './gateway'
import { isApprovalRequestedEvent } from '@/types/gateway'
import { getColorScheme, setColorScheme } from '@/theme'

const MENUS: MenuSpec[] = [
  {
    title: '文件',
    items: [
      { id: 'new-session', label: '新建会话', key: 'n' },
      { separator: true },
      { id: 'open-settings', label: '设置…', key: ',' },
      { id: 'open-data-dir', label: '打开数据目录' },
      { separator: true },
      { id: 'quit', label: '退出小巧', key: 'q' },
    ],
  },
  { title: '编辑', role: 'edit' },
  {
    title: '视图',
    items: [
      { id: 'reload', label: '重新加载界面', key: 'r' },
      { id: 'toggle-theme', label: '切换深浅色' },
    ],
  },
]

function handleMenu(id: string, router: Router): void {
  switch (id) {
    case 'new-session':
      void router.push('/')
      break
    case 'open-settings':
      void router.push('/settings')
      break
    case 'open-data-dir':
      void callShell('openDataDir')
      break
    case 'reload':
      location.reload()
      break
    case 'toggle-theme':
      setColorScheme(getColorScheme() === 'dark' ? 'light' : 'dark')
      break
    case 'quit':
      quitApp()
      break
    default:
      break
  }
}

/**
 * Notify only when the window is in the background — a banner for something
 * already on screen is noise, not help.
 */
function setupNotifications(): () => void {
  let lastApprovalId = ''

  const offApproval = gatewayService.on('approval_requested', (event) => {
    if (!isApprovalRequestedEvent(event)) return
    if (!document.hidden) return
    if (event.approvalId === lastApprovalId) return
    lastApprovalId = event.approvalId
    void notifyDesktop('需要审批', `${event.tool} 正在等你确认`, { id: event.approvalId })
  })

  const offDone = gatewayService.on('done', () => {
    if (!document.hidden) return
    void notifyDesktop('任务完成', '小巧已经跑完这一轮', { id: 'turn-done' })
  })

  return () => {
    offApproval()
    offDone()
  }
}

/** Wire the desktop integrations; returns a teardown for tests. */
export function setupDesktopShell(router: Router): () => void {
  if (!desktopAvailable()) return () => {}

  void setAppMenu(MENUS)

  const offMenu = onMenuClick((id) => handleMenu(id, router))
  const offDrop = onFilesDropped((paths) => {
    insertIntoComposer(paths.join('\n'))
  })
  const offNotifications = setupNotifications()

  return () => {
    offMenu()
    offDrop()
    offNotifications()
  }
}
