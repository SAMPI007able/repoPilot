<script setup lang="ts">
import AppDialog from './components/AppDialog.vue'
import AppFooter from './components/AppFooter.vue'
import ThemeToggle from './components/ThemeToggle.vue'
</script>

<template>
  <div class="app-root">
    <ThemeToggle />
    <RouterView class="app-root__view" />
    <AppFooter />
    <AppDialog />
  </div>
</template>
