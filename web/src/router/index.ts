import { createRouter, createWebHashHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import ChatSessionView from '../views/ChatSessionView.vue'
import EmptyStateView from '../views/EmptyStateView.vue'
import SettingsLayout from '../views/settings/SettingsLayout.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      component: ChatView,
      children: [
        {
          path: '',
          name: 'chat-home',
          component: EmptyStateView,
          meta: { keepAliveKey: 'home' },
        },
        {
          path: 'chat/:sessionId',
          name: 'chat-session',
          component: ChatSessionView,
          props: true,
          meta: { keepAliveKey: 'session' },
        },
        {
          path: 'g/:groupId',
          name: 'group',
          component: () => import('../views/groups/GroupView.vue'),
          props: true,
          meta: { keepAliveKey: 'group' },
        },
      ],
    },
    {
      path: '/toolbox',
      component: () => import('../views/toolbox/ToolboxLayout.vue'),
      redirect: '/toolbox/skills',
      children: [
        {
          path: 'skills',
          name: 'toolbox-skills',
          component: () => import('../views/toolbox/SkillsView.vue'),
        },
        {
          path: 'connectors',
          name: 'toolbox-connectors',
          component: () => import('../views/toolbox/ConnectorsView.vue'),
        },
      ],
    },
    {
      path: '/settings',
      component: SettingsLayout,
      redirect: '/settings/usage',
      children: [
        {
          path: 'usage',
          name: 'settings-usage',
          component: () => import('../views/settings/SettingsUsageView.vue'),
        },
        {
          path: 'models',
          name: 'settings-models',
          component: () => import('../views/settings/SettingsModelsView.vue'),
        },
        {
          path: 'channels',
          name: 'settings-channels',
          component: () => import('../views/settings/SettingsChannelsView.vue'),
        },
        {
          path: 'memory',
          name: 'settings-memory',
          component: () => import('../views/settings/SettingsMemoryView.vue'),
        },
        {
          path: 'personality',
          name: 'settings-personality',
          component: () => import('../views/settings/SettingsPersonalityView.vue'),
        },
        {
          path: 'security',
          name: 'settings-security',
          component: () => import('../views/settings/SettingsSecurityView.vue'),
        },
        {
          path: 'preferences',
          name: 'settings-preferences',
          component: () => import('../views/settings/SettingsPreferencesView.vue'),
        },
        {
          path: 'diagnostics',
          name: 'settings-diagnostics',
          component: () => import('../views/settings/SettingsDiagnosticsView.vue'),
        },
        {
          path: 'feedback',
          name: 'settings-feedback',
          component: () => import('../views/settings/SettingsFeedbackView.vue'),
        },
        {
          path: 'version',
          name: 'settings-version',
          component: () => import('../views/settings/SettingsVersionView.vue'),
        },
      ],
    },
    {
      path: '/automation',
      component: () => import('../views/automation/AutomationLayout.vue'),
      redirect: '/automation/tasks',
      children: [
        {
          path: 'tasks',
          name: 'automation-tasks',
          component: () => import('../views/automation/ScheduledTasksView.vue'),
        },
        {
          path: 'listeners',
          name: 'automation-listeners',
          component: () => import('../views/automation/EventListenersView.vue'),
        },
      ],
    },
  ],
})

export default router
