import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  // One local environment contract lives at the repository root. Vercel still
  // injects VITE_* values during its build, so no production .env file is needed.
  envDir: '..',
  plugins: [vue()],
})
