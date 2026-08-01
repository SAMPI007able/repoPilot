<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

async function signIn() {
  await auth.signIn()
  if (auth.authenticated) await router.replace('/')
}
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <p class="eyebrow">TestForge AI</p>
      <h1>Sign in to continue</h1>
      <p>Connect through your organization's identity provider to access workspaces and previews.</p>
      <p v-if="auth.error" class="error-banner">{{ auth.error }}</p>
      <button class="primary-button" :disabled="auth.loading" @click="signIn">
        {{ auth.loading ? 'Signing in…' : 'Sign in' }}
      </button>
    </section>
  </main>
</template>
