import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './style.css'

const app = createApp(App)
const pinia = createPinia()
const auth = useAuthStore(pinia)

app.use(pinia)
app.use(router)
router.beforeEach(async (to) => {
  await auth.initialize()
  if (to.meta.requiresAuth && !auth.authenticated) return { name: 'sign-in' }
  if (to.name === 'sign-in' && auth.authenticated) return { name: 'home' }
  return true
})
app.mount('#app')
