<script setup lang="ts">
import { LifeBuoy } from '@lucide/vue'

const year = new Date().getFullYear()
</script>

<template>
  <footer class="app-footer">
    <div class="app-footer__inner">
      <p>&copy; {{ year }} RepoPilot. All rights reserved.</p>
      <nav class="app-footer__links" aria-label="Footer">
        <RouterLink to="/support"><LifeBuoy :size="15" aria-hidden="true" /> Support</RouterLink>
      </nav>
    </div>
  </footer>
</template>
