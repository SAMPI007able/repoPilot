import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'
import {
  getCurrentUser,
  setAccessTokenProvider,
  setAuthenticationFailureHandler,
} from '../services/api'
import type { CurrentUser } from '../types/api'

const mode = import.meta.env.VITE_AUTH_MODE || 'oidc'
const developmentToken = import.meta.env.VITE_AUTH_DEVELOPMENT_TOKEN || ''
const developmentSignedOutKey = 'testforge.developmentSignedOut'
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
  const developmentSignedIn = ref(
    mode !== 'development' || window.sessionStorage.getItem(developmentSignedOutKey) !== 'true',
  )
  const authenticated = computed(() => user.value !== null)
  let oidcEventsBound = false
  let handlingAuthenticationFailure = false

  function navigateToSignIn() {
    if (!['/sign-in', '/auth/callback'].includes(window.location.pathname)) {
      window.location.assign('/sign-in')
    }
  }

  async function handleAuthenticationFailure() {
    if (handlingAuthenticationFailure) return
    handlingAuthenticationFailure = true
    try {
      user.value = null
      oidcUser.value = null
      if (mode === 'development') {
        developmentSignedIn.value = false
        window.sessionStorage.setItem(developmentSignedOutKey, 'true')
      } else if (manager) {
        await manager.removeUser().catch(() => undefined)
      }
      navigateToSignIn()
    } finally {
      handlingAuthenticationFailure = false
    }
  }

  function bindOidcEvents() {
    if (mode === 'development' || oidcEventsBound) return
    const oidc = oidcManager()
    oidc.events.addUserLoaded(async (nextUser) => {
      oidcUser.value = nextUser
      user.value = await getCurrentUser()
    })
    oidc.events.addUserUnloaded(() => { void handleAuthenticationFailure() })
    oidc.events.addAccessTokenExpired(() => { void handleAuthenticationFailure() })
    oidcEventsBound = true
  }

  async function accessToken() {
    if (mode === 'development') {
      return developmentSignedIn.value ? developmentToken || null : null
    }
    return oidcUser.value?.expired ? null : oidcUser.value?.access_token ?? null
  }

  async function initialize() {
    if (initialized.value) return
    loading.value = true
    setAccessTokenProvider(accessToken)
    setAuthenticationFailureHandler(handleAuthenticationFailure)
    try {
      if (mode !== 'development') {
        bindOidcEvents()
        oidcUser.value = await oidcManager().getUser()
      }
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
      loading.value = true
      try {
        developmentSignedIn.value = true
        window.sessionStorage.removeItem(developmentSignedOutKey)
        user.value = await getCurrentUser()
        initialized.value = true
      } finally {
        loading.value = false
      }
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
    error.value = null
    if (mode === 'development') {
      developmentSignedIn.value = false
      window.sessionStorage.setItem(developmentSignedOutKey, 'true')
      return
    }
    oidcUser.value = null
    const oidc = oidcManager()
    handlingAuthenticationFailure = true
    try {
      await oidc.removeUser()
    } finally {
      handlingAuthenticationFailure = false
    }
    await oidc.signoutRedirect()
  }

  return { user, initialized, loading, error, authenticated, initialize, signIn, completeSignIn, signOut, accessToken }
})
