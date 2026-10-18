<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { AlertTriangle, Info, X } from '@lucide/vue'
import { useDialogStore } from '../stores/dialog'

const dialog = useDialogStore()
const confirmButton = ref<HTMLButtonElement | null>(null)
let returnFocus: HTMLElement | null = null

watch(() => dialog.current?.id, async (id, previousId) => {
  if (id && !previousId) returnFocus = document.activeElement as HTMLElement | null
  if (id) {
    await nextTick()
    confirmButton.value?.focus()
  } else {
    returnFocus?.focus?.()
    returnFocus = null
  }
})

function onKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && dialog.current) {
    event.preventDefault()
    dialog.settle(false)
  }
}

onMounted(() => document.addEventListener('keydown', onKeyDown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <Teleport to="body">
    <Transition name="app-dialog">
      <div
        v-if="dialog.current"
        :key="dialog.current.id"
        class="auth-modal app-dialog"
        role="presentation"
        @mousedown.self="dialog.settle(false)"
      >
        <section
          class="auth-modal__card app-dialog__card"
          :class="`app-dialog__card--${dialog.current.tone}`"
          :role="dialog.current.kind === 'confirm' ? 'alertdialog' : 'dialog'"
          aria-modal="true"
          aria-labelledby="app-dialog-title"
          aria-describedby="app-dialog-message"
        >
          <button class="auth-modal__close" type="button" aria-label="Close" @click="dialog.settle(false)">
            <X :size="18" />
          </button>
          <span class="app-dialog__icon" aria-hidden="true">
            <AlertTriangle v-if="dialog.current.tone === 'danger'" :size="20" />
            <Info v-else :size="20" />
          </span>
          <h2 id="app-dialog-title">{{ dialog.current.title }}</h2>
          <p id="app-dialog-message" class="auth-modal__copy">{{ dialog.current.message }}</p>
          <div class="app-dialog__actions">
            <button
              v-if="dialog.current.kind === 'confirm'"
              class="btn btn-ghost"
              type="button"
              @click="dialog.settle(false)"
            >
              {{ dialog.current.cancelLabel }}
            </button>
            <button
              ref="confirmButton"
              class="btn"
              :class="dialog.current.tone === 'danger' ? 'btn-danger-solid' : 'btn-primary'"
              type="button"
              @click="dialog.settle(true)"
            >
              {{ dialog.current.confirmLabel }}
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
