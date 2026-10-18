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
import { useBootStore } from './stores/boot'
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

const bootStore = useBootStore()

app.mount('#app')

// Mount first so the window paints immediately. In a browser this connects in
// the same tick; in the desktop shell it waits for the engine and shows the
// boot overlay (or its error state) meanwhile.
void bootStore.start()
