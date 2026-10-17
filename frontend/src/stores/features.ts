import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { getFeatureFlags } from '../services/api'
import type { FeatureFlagKey } from '../types/api'

const safeDefaults: Record<FeatureFlagKey, boolean> = {
  preview: false,
  ai_generation: true,
  uploads: true,
  code_quality: false,
}
let loadingPromise: Promise<void> | null = null

export const useFeatureFlagStore = defineStore('featureFlags', () => {
  const flags = ref<Record<string, boolean>>({ ...safeDefaults })
  const loaded = ref(false)

  const previewEnabled = computed(() => flags.value.preview === true)
  const codeQualityEnabled = computed(() => flags.value.code_quality === true)

  function isEnabled(key: FeatureFlagKey): boolean {
    return flags.value[key] === true
  }

  async function load(force = false): Promise<void> {
    if (loaded.value && !force) return
    if (loadingPromise && !force) return loadingPromise
    loadingPromise = (async () => {
      try {
        const response = await getFeatureFlags()
        flags.value = { ...safeDefaults, ...response.flags }
      } catch {
        flags.value = { ...safeDefaults }
      } finally {
        loaded.value = true
      }
    })()
    try {
      await loadingPromise
    } finally {
      loadingPromise = null
    }
  }

  return { flags, loaded, previewEnabled, codeQualityEnabled, isEnabled, load }
})
