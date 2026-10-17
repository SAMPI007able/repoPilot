<script setup lang="ts">
import { Moon, Sun } from '@lucide/vue'
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
</script>

<template>
  <button
    class="theme-toggle"
    type="button"
    :aria-label="`Switch to ${theme.isDark ? 'light' : 'dark'} theme`"
    :title="`Switch to ${theme.isDark ? 'light' : 'dark'} theme`"
    @click="theme.toggle"
  >
    <Sun v-if="theme.isDark" aria-hidden="true" />
    <Moon v-else aria-hidden="true" />
    <span>{{ theme.isDark ? 'Light' : 'Dark' }}</span>
  </button>
</template>
