import { createApp } from 'vue'
import { createPinia } from 'pinia'
import posthog from 'posthog-js'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useFeatureFlagStore } from './stores/features'
// import { inject } from '@vercel/analytics'
import './style.css'

const app = createApp(App)
const pinia = createPinia()
const auth = useAuthStore(pinia)
const featureFlags = useFeatureFlagStore(pinia)

const posthogApiKey = import.meta.env.VITE_POSTHOG_API_KEY || ''
if (posthogApiKey) {
  posthog.init(posthogApiKey, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
    autocapture: true,
    capture_pageview: true,
    loaded: (ph) => {
      if (import.meta.env.DEV) ph.opt_out_capturing()
    },
  })
}

app.config.globalProperties.$posthog = posthog
app.use(pinia)
app.use(router)
router.beforeEach(async (to) => {
  await auth.initialize()
  await featureFlags.load()
  if (to.meta.requiresAuth && !auth.authenticated) return { name: 'sign-in' }
  if (to.name === 'sign-in' && auth.authenticated) return { name: 'home' }
  return true
})
app.mount('#app')
// Initialize Vercel Analytics
// inject()
