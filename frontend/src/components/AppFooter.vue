<script setup lang="ts">
import { LifeBuoy, Mail } from '@lucide/vue'
import { supportEmail, supportMailto } from '../support/labels'

const year = new Date().getFullYear()
</script>

<template>
  <footer class="app-footer">
    <div class="app-footer__inner">
      <p>&copy; {{ year }} RepoPilot. All rights reserved.</p>
      <nav class="app-footer__links" aria-label="Footer">
        <RouterLink to="/support"><LifeBuoy :size="15" aria-hidden="true" /> Support</RouterLink>
        <a :href="supportMailto" :title="supportEmail"><Mail :size="15" aria-hidden="true" /> Email us</a>
      </nav>
    </div>
  </footer>
</template>
