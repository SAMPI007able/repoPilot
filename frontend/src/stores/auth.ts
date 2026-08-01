import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'
import { getCurrentUser, setAccessTokenProvider } from '../services/api'
import type { CurrentUser } from '../types/api'

const mode = import.meta.env.VITE_AUTH_MODE || 'oidc'
const developmentToken = import.meta.env.VITE_AUTH_DEVELOPMENT_TOKEN || ''
let manager: UserManager | null = null

function oidcManager() {
  if (manager) return manager
  const authority = import.meta.env.VITE_OIDC_AUTHORITY
  const clientId = import.meta.env.VITE_OIDC_CLIENT_ID
  if (!authority || !clientId) throw new Error('OIDC frontend configuration is incomplete.')
  manager = new UserManager({
    authority,
    client_id: clientId,
    redirect_uri: import.meta.env.VITE_OIDC_REDIRECT_URI || `${window.location.origin}/auth/callback`,
    post_logout_redirect_uri: window.location.origin,
    response_type: 'code',
    scope: import.meta.env.VITE_OIDC_SCOPE || 'openid profile email',
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  })
  return manager
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const oidcUser = ref<User | null>(null)
  const initialized = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const authenticated = computed(() => user.value !== null)

  async function accessToken() {
    if (mode === 'development') return developmentToken || null
    return oidcUser.value?.expired ? null : oidcUser.value?.access_token ?? null
  }

  async function initialize() {
    if (initialized.value) return
    loading.value = true
    setAccessTokenProvider(accessToken)
    try {
      if (mode !== 'development') oidcUser.value = await oidcManager().getUser()
      if (await accessToken()) user.value = await getCurrentUser()
    } catch (caught) {
      user.value = null
      error.value = caught instanceof Error ? caught.message : 'Authentication failed.'
    } finally {
      initialized.value = true
      loading.value = false
    }
  }

  async function signIn() {
    error.value = null
    if (mode === 'development') {
      await initialize()
      return
    }
    await oidcManager().signinRedirect()
  }

  async function completeSignIn() {
    loading.value = true
    try {
      oidcUser.value = await oidcManager().signinRedirectCallback()
      user.value = await getCurrentUser()
    } finally {
      initialized.value = true
      loading.value = false
    }
  }

  async function signOut() {
    user.value = null
    if (mode !== 'development') await oidcManager().signoutRedirect()
  }

  return { user, initialized, loading, error, authenticated, initialize, signIn, completeSignIn, signOut, accessToken }
})
