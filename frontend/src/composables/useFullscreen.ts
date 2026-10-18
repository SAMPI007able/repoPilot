import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * Toggles fullscreen for a panel. Uses the Fullscreen API where available and falls back to a
 * fixed full-viewport overlay (`.is-maximized`) on browsers without it, such as iOS Safari.
 */
export function useFullscreen(target: Ref<HTMLElement | null>) {
  const isFullscreen = ref(false)
  const nativeSupported = typeof document !== 'undefined' && document.fullscreenEnabled

  function syncNativeState() {
    isFullscreen.value = Boolean(target.value && document.fullscreenElement === target.value)
  }

  function setFallback(active: boolean) {
    target.value?.classList.toggle('is-maximized', active)
    document.documentElement.classList.toggle('has-maximized-panel', active)
    isFullscreen.value = active
  }

  async function toggle() {
    const element = target.value
    if (!element) return
    if (!nativeSupported) {
      setFallback(!isFullscreen.value)
      return
    }
    try {
      if (document.fullscreenElement === element) await document.exitFullscreen()
      else await element.requestFullscreen()
    } catch {
      setFallback(!isFullscreen.value)
    }
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape' && isFullscreen.value && !document.fullscreenElement) setFallback(false)
  }

  onMounted(() => {
    document.addEventListener('fullscreenchange', syncNativeState)
    document.addEventListener('keydown', onKeyDown)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('fullscreenchange', syncNativeState)
    document.removeEventListener('keydown', onKeyDown)
    if (document.fullscreenElement === target.value) void document.exitFullscreen()
    if (target.value?.classList.contains('is-maximized')) setFallback(false)
  })

  return { isFullscreen, toggle }
}
