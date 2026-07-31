<script setup lang="ts">
import { computed, watch } from 'vue'
import { CheckCircle2, FlaskConical, Info, ShieldAlert, Sparkles } from '@lucide/vue'
import { usePreviewStore } from '../stores/preview'

const props = defineProps<{ workspaceId: string }>()
const previewStore = usePreviewStore()
const draft = computed(() => previewStore.draft)
const record = computed(() => previewStore.record)
const dirty = computed(() => Boolean(
  draft.value
  && record.value
  && JSON.stringify(draft.value) !== JSON.stringify(record.value.manifest),
))
const requiredEnvironment = computed({
  get: () => draft.value?.environment.required.join(', ') ?? '',
  set: (value: string) => {
    if (draft.value) draft.value.environment.required = parseEnvironmentNames(value)
  },
})
const optionalEnvironment = computed({
  get: () => draft.value?.environment.optional.join(', ') ?? '',
  set: (value: string) => {
    if (draft.value) draft.value.environment.optional = parseEnvironmentNames(value)
  },
})

watch(() => props.workspaceId, (workspaceId) => previewStore.load(workspaceId), { immediate: true })

function parseEnvironmentNames(value: string) {
  return [...new Set(value.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean))]
}
</script>

<template>
  <section class="panel panel-pad preview-lab">
    <div class="panel-heading">
      <div>
        <h2><FlaskConical :size="17" /> Realtime Preview Lab</h2>
        <p class="preview-lab__subtitle">Analyze and approve a safe runtime manifest before any execution.</p>
      </div>
      <span class="preview-lab__phase">Phase 1 · configuration only</span>
    </div>

    <div class="preview-lab__notice">
      <ShieldAlert :size="17" aria-hidden="true" />
      <span>No repository commands run during analysis. Preview execution remains disabled until a later sandbox phase.</span>
    </div>

    <div class="preview-lab__analyze">
      <label class="scenario-field">
        <span class="scenario-field__label">Optional install or run instructions</span>
        <textarea
          class="input preview-lab__instructions"
          :value="previewStore.instructions"
          placeholder="Example: use the dev script and configured Vite port. Do not include secrets."
          @input="previewStore.setInstructions(($event.target as HTMLTextAreaElement).value)"
        />
      </label>
      <button class="btn btn-primary" type="button" :disabled="previewStore.loading" @click="previewStore.analyze">
        <Sparkles :size="15" aria-hidden="true" />
        {{ record ? 'Analyze again' : 'Analyze runtime' }}
      </button>
    </div>

    <div v-if="previewStore.loading" class="empty-state-box">Inspecting deterministic repository signals...</div>
    <p v-if="previewStore.error" class="error-text">{{ previewStore.error }}</p>

    <template v-if="record && draft && !previewStore.loading">
      <div class="preview-lab__summary">
        <div><span>Framework</span><strong>{{ record.summary.framework }}</strong></div>
        <div><span>Runtime</span><strong>Node {{ draft.runtime.version }}</strong></div>
        <div><span>Package manager</span><strong>{{ record.summary.packageManager }}</strong></div>
        <div><span>Confidence</span><strong>{{ Math.round(record.summary.confidence * 100) }}%</strong></div>
      </div>

      <div v-if="record.unsupportedReasons.length" class="preview-lab__issues preview-lab__issues--error">
        <strong>Action required</strong>
        <ul><li v-for="reason in record.unsupportedReasons" :key="reason">{{ reason }}</li></ul>
      </div>
      <div v-if="record.warnings.length" class="preview-lab__issues">
        <strong>Review warnings</strong>
        <ul><li v-for="warning in record.warnings" :key="warning">{{ warning }}</li></ul>
      </div>

      <div class="preview-lab__form-grid">
        <label><span>Node version</span><select v-model="draft.runtime.version" class="input"><option value="22">22</option><option value="20">20</option></select></label>
        <label><span>Branch</span><input v-model="draft.repository.branch" class="input" maxlength="255"></label>
        <label class="preview-lab__form-wide"><span>Install command</span><input v-model="draft.install.command" class="input input--mono" maxlength="240"></label>
        <label class="preview-lab__form-wide"><span>Build command</span><input v-model="draft.build.command" class="input input--mono" maxlength="240"></label>
        <label class="preview-lab__form-wide"><span>Start command</span><input v-model="draft.services[0]!.command" class="input input--mono" maxlength="240"></label>
        <label><span>Public port</span><input v-model.number="draft.services[0]!.port" class="input" type="number" min="1024" max="65535"></label>
        <label><span>Health-check path</span><input v-model="draft.services[0]!.healthcheck.path" class="input input--mono" placeholder="/"></label>
        <label class="preview-lab__form-wide">
          <span>Required environment names</span>
          <input v-model="requiredEnvironment" class="input input--mono" placeholder="VITE_API_URL, PUBLIC_API_KEY">
          <small>Names only. Secret values are never stored in this manifest.</small>
        </label>
        <label class="preview-lab__form-wide"><span>Optional environment names</span><input v-model="optionalEnvironment" class="input input--mono" placeholder="VITE_ANALYTICS_ID"></label>
        <label><span>CPU limit</span><select v-model="draft.resources.cpuLimit" class="input"><option value="500m">500m</option><option value="1">1 CPU</option><option value="2">2 CPU</option></select></label>
        <label><span>Memory limit</span><select v-model="draft.resources.memoryLimit" class="input"><option value="512Mi">512 MiB</option><option value="1Gi">1 GiB</option><option value="2Gi">2 GiB</option></select></label>
        <label><span>Idle timeout (minutes)</span><input v-model.number="draft.lifecycle.idleTimeoutMinutes" class="input" type="number" min="5" max="60"></label>
        <label><span>Maximum lifetime (minutes)</span><input v-model.number="draft.lifecycle.maximumLifetimeMinutes" class="input" type="number" min="10" max="240"></label>
      </div>

      <div class="preview-lab__actions">
        <button class="btn btn-ghost" type="button" :disabled="!dirty || previewStore.saving" @click="previewStore.save">{{ previewStore.saving ? 'Saving...' : 'Save configuration' }}</button>
        <button class="btn btn-primary" type="button" :disabled="dirty || !record.supported || record.approved || previewStore.approving" @click="previewStore.approve">
          <CheckCircle2 :size="15" aria-hidden="true" />
          {{ record.approved ? 'Manifest approved' : previewStore.approving ? 'Approving...' : 'Approve manifest' }}
        </button>
      </div>

      <div v-if="record.approved" class="preview-lab__approved"><CheckCircle2 :size="17" aria-hidden="true" /> Manifest revision {{ record.revision }} is approved. No preview has been started.</div>

      <details class="preview-lab__evidence">
        <summary><Info :size="15" aria-hidden="true" /> Analysis evidence</summary>
        <div v-for="item in record.evidence" :key="`${item.field}-${item.source}`" class="preview-lab__evidence-row">
          <div><strong>{{ item.field }}</strong> · {{ Math.round(item.confidence * 100) }}%</div>
          <div>{{ item.source }} — {{ item.detail }}</div>
        </div>
      </details>
    </template>

    <div v-else-if="!previewStore.loading" class="empty-state-box">Analyze this workspace to create a deterministic runtime proposal for review.</div>
  </section>
</template>
