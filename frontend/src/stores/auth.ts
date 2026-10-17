import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { captureTelemetry, identifyTelemetry, resetTelemetry } from '../services/telemetry'
import type { User, UserManager } from 'oidc-client-ts'
import {
  getCurrentUser,
  setAccessTokenProvider,
  setAuthenticationFailureHandler,
} from '../services/api'
import type { CurrentUser } from '../types/api'

const mode = import.meta.env.VITE_AUTH_MODE || 'oidc'
const developmentToken = import.meta.env.VITE_AUTH_DEVELOPMENT_TOKEN || ''
const developmentSignedOutKey = 'testforge.developmentSignedOut'
const oidcAudience = import.meta.env.VITE_OIDC_AUDIENCE || ''
export type SignInMethod = 'github' | 'google' | 'email'
let manager: UserManager | null = null
let oidcModule: Promise<typeof import('oidc-client-ts')> | null = null
let signInCompletion: Promise<void> | null = null
let initialization: Promise<void> | null = null

async function oidcManager() {
  if (manager) return manager
  oidcModule ??= import('oidc-client-ts')
  const { UserManager, WebStorageStateStore } = await oidcModule
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
    extraQueryParams: oidcAudience ? { audience: oidcAudience } : undefined,
    stateStore: new WebStorageStateStore({ store: window.localStorage }),
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
  const redirectSignIn = mode !== 'development'
  let oidcEventsBound = false
  let handlingAuthenticationFailure = false

  function captureEvent(eventName: string, properties: Record<string, unknown> = {}) {
    captureTelemetry(eventName, user.value?.id ? { ...properties, $user_id: user.value.id } : properties)
  }

  function identifyUser(nextUser: CurrentUser | null) {
    if (!nextUser?.id) {
      resetTelemetry()
      return
    }
    identifyTelemetry(nextUser.id, {
      email: nextUser.primaryEmail,
      display_name: nextUser.displayName,
    })
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
    } finally {
      handlingAuthenticationFailure = false
    }
  }

  function bindOidcEvents(oidc: UserManager) {
    if (mode === 'development' || oidcEventsBound) return
    oidc.events.addUserLoaded(async (nextUser) => {
      oidcUser.value = nextUser
      user.value = await getCurrentUser()
      identifyUser(user.value)
      captureEvent('user_registered', { source: 'oidc_loaded' })
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
    if (initialization) return initialization
    initialization = (async () => {
      loading.value = true
      setAccessTokenProvider(accessToken)
      setAuthenticationFailureHandler(handleAuthenticationFailure)
      try {
        if (mode !== 'development') {
          const oidc = await oidcManager()
          bindOidcEvents(oidc)
          oidcUser.value = await oidc.getUser()
        }
        if (await accessToken()) {
          user.value = await getCurrentUser()
          identifyUser(user.value)
        }
      } catch (caught) {
        user.value = null
        error.value = caught instanceof Error ? caught.message : 'Authentication failed.'
      } finally {
        initialized.value = true
        loading.value = false
      }
    })()
    try {
      await initialization
    } finally {
      initialization = null
    }
  }

  async function signIn(method: SignInMethod = 'email') {
    error.value = null
    if (mode === 'development') {
      loading.value = true
      try {
        developmentSignedIn.value = true
        window.sessionStorage.removeItem(developmentSignedOutKey)
        user.value = await getCurrentUser()
        identifyUser(user.value)
        captureEvent('user_registered', { source: 'development_signin' })
        initialized.value = true
      } finally {
        loading.value = false
      }
      return
    }
    const connectionByMethod: Record<SignInMethod, string> = {
      github: import.meta.env.VITE_OIDC_GITHUB_CONNECTION || '',
      google: import.meta.env.VITE_OIDC_GOOGLE_CONNECTION || '',
      email: import.meta.env.VITE_OIDC_EMAIL_CONNECTION || '',
    }
    const connection = connectionByMethod[method]
    const parameter = import.meta.env.VITE_OIDC_CONNECTION_PARAMETER || 'connection'
    const extraQueryParams: Record<string, string> = {}
    if (oidcAudience) extraQueryParams.audience = oidcAudience
    if (connection) extraQueryParams[parameter] = connection
    await (await oidcManager()).signinRedirect(
      Object.keys(extraQueryParams).length ? { extraQueryParams } : undefined,
    )
  }

  async function completeSignIn() {
    if (signInCompletion) return signInCompletion
    signInCompletion = (async () => {
      loading.value = true
      try {
        const oidc = await oidcManager()
        let completedUser: User | null
        try {
          completedUser = await oidc.signinRedirectCallback()
        } catch (caught) {
          const missingState = caught instanceof Error && caught.message.includes('No matching state found')
          completedUser = missingState ? await oidc.getUser() : null
          if (!completedUser || completedUser.expired) throw caught
        }
        oidcUser.value = completedUser
        window.history.replaceState({}, document.title, '/')
        user.value = await getCurrentUser()
        identifyUser(user.value)
        captureEvent('user_registered', { source: 'oidc_callback' })
        error.value = null
      } finally {
        initialized.value = true
        loading.value = false
      }
    })()
    try {
      await signInCompletion
    } finally {
      signInCompletion = null
    }
  }

  async function refreshUser() {
    loading.value = true
    error.value = null
    try {
      if (mode !== 'development') {
        try {
          oidcUser.value = await (await oidcManager()).signinSilent()
        } catch {
          await (await oidcManager()).signinRedirect({ prompt: 'none' })
          return false
        }
      }
      user.value = await getCurrentUser()
      identifyUser(user.value)
      return true
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : 'Unable to refresh your verification status.'
      throw caught
    } finally {
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
    const oidc = await oidcManager()
    handlingAuthenticationFailure = true
    try {
      await oidc.removeUser()
    } finally {
      handlingAuthenticationFailure = false
    }
    await oidc.signoutRedirect()
  }

  return {
    user,
    initialized,
    loading,
    error,
    authenticated,
    redirectSignIn,
    initialize,
    signIn,
    completeSignIn,
    refreshUser,
    signOut,
    accessToken,
  }
})
