<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    await auth.completeSignIn()
    await router.replace('/')
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Sign-in callback failed.'
  }
})
</script>

<template>
  <main class="auth-page"><section class="auth-card">
    <h1>{{ error ? 'Unable to sign in' : 'Completing sign-in…' }}</h1>
    <p v-if="error" class="error-banner">{{ error }}</p>
  </section></main>
</template>
