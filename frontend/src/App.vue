<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { label: 'Workspace', to: '/' },
  { label: 'Overview', to: '/workspace' },
  { label: 'Generate', to: '/generate' },
]
</script>

<template>
  <div class="shell">
    <header class="shell__header">
      <div>
        <p class="eyebrow">Repository to reasoning pipeline</p>
        <h1 class="brand">TestForge AI</h1>
      </div>

      <nav class="shell__nav" aria-label="Primary">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="shell__nav-link"
          :class="{ 'shell__nav-link--active': route.path === item.to }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </header>

    <main class="shell__main">
      <RouterView />
    </main>
  </div>
</template>
