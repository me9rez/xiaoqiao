import '@unocss/reset/tailwind.css'
import 'virtual:uno.css'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import './styles/tokens.css'
import './style.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { gatewayService } from './services/gateway'
import { useChatStore } from './stores/chat'
import { useWorkspaceStore } from './stores/workspace'
import { initTheme } from './theme'

initTheme()

const app = createApp(App)

app.use(createPinia())
app.use(router)

const chatStore = useChatStore()
chatStore.setupEventListeners()

const workspaceStore = useWorkspaceStore()
workspaceStore.setupEventListeners()

gatewayService.connect()

app.mount('#app')
