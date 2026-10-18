let activeAnimation = 0

function easeInOutCubic(progress: number) {
  return progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2
}

/**
 * Scrolls the window so `element` sits `offset` px below the viewport top. Slower and gentler than
 * native smooth scrolling; respects prefers-reduced-motion and is cancelled by a newer call.
 */
export function smoothScrollToElement(element: HTMLElement, offset = 0, duration = 750) {
  cancelAnimationFrame(activeAnimation)
  const start = window.scrollY
  const maxScroll = document.documentElement.scrollHeight - window.innerHeight
  const target = Math.min(Math.max(element.getBoundingClientRect().top + start - offset, 0), maxScroll)
  const distance = target - start
  if (Math.abs(distance) < 2) return

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    window.scrollTo(0, target)
    return
  }

  const startedAt = performance.now()
  const step = (now: number) => {
    const progress = Math.min((now - startedAt) / duration, 1)
    window.scrollTo(0, start + distance * easeInOutCubic(progress))
    if (progress < 1) activeAnimation = requestAnimationFrame(step)
  }
  activeAnimation = requestAnimationFrame(step)
}
