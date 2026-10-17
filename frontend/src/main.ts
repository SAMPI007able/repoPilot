import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useFeatureFlagStore } from './stores/features'
import { useThemeStore } from './stores/theme'
import { initializeTelemetry } from './services/telemetry'
// import { inject } from '@vercel/analytics'
import './style.css'

const app = createApp(App)
const pinia = createPinia()
const auth = useAuthStore(pinia)
const featureFlags = useFeatureFlagStore(pinia)
const theme = useThemeStore(pinia)
theme.initialize()

app.use(pinia)
app.use(router)
router.beforeEach(async (to) => {
  const mustKnowAuthentication = Boolean(to.meta.requiresAuth) || to.name === 'sign-in' || to.name === 'auth-callback'
  if (mustKnowAuthentication) {
    await auth.initialize()
  } else if (!auth.initialized) {
    const restoreSession = () => {
      void auth.initialize().then(() => {
        if (auth.authenticated && auth.user?.emailVerified) void featureFlags.load()
      })
    }
    if (window.requestIdleCallback) window.requestIdleCallback(restoreSession, { timeout: 1500 })
    else window.setTimeout(restoreSession)
  }
  if (auth.authenticated && auth.user?.emailVerified) void featureFlags.load()
  if (to.meta.requiresAuth && !auth.authenticated) return { name: 'sign-in' }
  if (to.name === 'sign-in' && auth.authenticated) return { name: 'home' }
  return true
})
app.mount('#app')
initializeTelemetry()
// Initialize Vercel Analytics
// inject()
