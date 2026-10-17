import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type Theme = 'light' | 'dark'

const storageKey = 'repopilot.theme'

function preferredTheme(): Theme {
  const stored = window.localStorage.getItem(storageKey)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export const useThemeStore = defineStore('theme', () => {
  const current = ref<Theme>(preferredTheme())
  const isDark = computed(() => current.value === 'dark')

  function apply(theme: Theme) {
    current.value = theme
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    window.localStorage.setItem(storageKey, theme)
  }

  function initialize() {
    apply(current.value)
  }

  function toggle() {
    apply(isDark.value ? 'light' : 'dark')
  }

  return { current, isDark, initialize, toggle }
})
