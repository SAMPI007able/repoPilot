import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type DialogTone = 'default' | 'danger'

export interface DialogOptions {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: DialogTone
}

interface DialogRequest extends Required<Omit<DialogOptions, 'cancelLabel'>> {
  id: number
  kind: 'confirm' | 'alert'
  cancelLabel: string
  resolve: (confirmed: boolean) => void
}

/** App-wide replacement for window.confirm / window.alert, rendered by AppDialog.vue. */
export const useDialogStore = defineStore('dialog', () => {
  const queue = ref<DialogRequest[]>([])
  const current = computed(() => queue.value[0] ?? null)
  let nextId = 0

  function open(kind: DialogRequest['kind'], options: DialogOptions): Promise<boolean> {
    return new Promise((resolve) => {
      queue.value = [...queue.value, {
        id: ++nextId,
        kind,
        title: options.title,
        message: options.message,
        confirmLabel: options.confirmLabel ?? (kind === 'confirm' ? 'Confirm' : 'OK'),
        cancelLabel: options.cancelLabel ?? 'Cancel',
        tone: options.tone ?? 'default',
        resolve,
      }]
    })
  }

  function confirm(options: DialogOptions) {
    return open('confirm', options)
  }

  async function alert(options: DialogOptions) {
    await open('alert', options)
  }

  function settle(confirmed: boolean) {
    const request = current.value
    if (!request) return
    queue.value = queue.value.slice(1)
    request.resolve(request.kind === 'alert' ? true : confirmed)
  }

  return { current, confirm, alert, settle }
})
