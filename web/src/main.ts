import '@unocss/reset/tailwind.css'
import 'virtual:uno.css'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
// Self-hosted fonts: the desktop shell runs offline, so no CDN <link> tags.
import '@fontsource-variable/schibsted-grotesk'
import '@fontsource-variable/jetbrains-mono'
import './styles/tokens.css'
import './style.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { resolveGatewayEndpoint } from './services/endpoint'
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

app.mount('#app')

// Mount first so the window paints immediately: in the desktop shell this
// await only resolves once the engine is listening on its port.
void resolveGatewayEndpoint().then((endpoint) => {
  gatewayService.connect(endpoint)
})
