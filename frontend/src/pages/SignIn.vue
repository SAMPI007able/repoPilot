<script setup lang="ts">
import { GitBranch, Mail } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import type { SignInMethod } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

async function signIn(method: SignInMethod) {
  await auth.signIn(method)
  if (auth.authenticated) await router.replace('/')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <p class="eyebrow">TestForge AI</p>
      <h1>Sign in to continue</h1>
      <p>Choose a secure sign-in method to access workspaces and previews.</p>
      <p v-if="auth.error" class="error-banner">{{ auth.error }}</p>
      <div class="auth-options">
        <button class="auth-option" type="button" :disabled="auth.loading" @click="signIn('github')">
          <GitBranch :size="19" /> Continue with GitHub
        </button>
        <button class="auth-option" type="button" :disabled="auth.loading" @click="signIn('google')">
          <span class="auth-option__google" aria-hidden="true">G</span> Continue with Google
        </button>
        <button class="auth-option" type="button" :disabled="auth.loading" @click="signIn('email')">
          <Mail :size="19" /> Continue with email
        </button>
      </div>
      <p class="auth-modal__security">Passwords are handled by the configured identity provider, not TestForge.</p>
    </section>
  </main>
</template>
