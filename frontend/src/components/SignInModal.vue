<script setup lang="ts">
import { GitBranch, Mail, X } from '@lucide/vue'
import type { SignInMethod } from '../stores/auth'

defineProps<{ busy: boolean; error: string | null }>()
const emit = defineEmits<{
  close: []
  'sign-in': [method: SignInMethod]
}>()
</script>

<template>
  <div class="auth-modal" role="presentation" @mousedown.self="emit('close')">
    <section class="auth-modal__card" role="dialog" aria-modal="true" aria-labelledby="sign-in-title">
      <button class="auth-modal__close" type="button" aria-label="Close sign-in" @click="emit('close')">
        <X :size="18" />
      </button>
      <p class="eyebrow">TestForge AI</p>
      <h2 id="sign-in-title">Sign in to build your workspace</h2>
      <p class="auth-modal__copy">
        Your home page stays public. Authentication is only required when TestForge starts processing a repository.
      </p>
      <p v-if="error" class="error-text">{{ error }}</p>
      <div class="auth-options">
        <button class="auth-option" type="button" :disabled="busy" @click="emit('sign-in', 'github')">
          <GitBranch :size="19" /> Continue with GitHub
        </button>
        <button class="auth-option" type="button" :disabled="busy" @click="emit('sign-in', 'google')">
          <span class="auth-option__google" aria-hidden="true">G</span> Continue with Google
        </button>
        <button class="auth-option" type="button" :disabled="busy" @click="emit('sign-in', 'email')">
          <Mail :size="19" /> Continue with email
        </button>
      </div>
      <p class="auth-modal__security">
        Email and password are entered on the secure identity-provider page; TestForge never receives or stores your password.
      </p>
    </section>
  </div>
</template>
