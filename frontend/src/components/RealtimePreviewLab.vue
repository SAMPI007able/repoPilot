<script setup lang="ts">
import { computed, watch } from 'vue'
import posthog from 'posthog-js'
import { CheckCircle2, Clock3, ExternalLink, FlaskConical, Info, ShieldAlert, Sparkles, Square, Terminal } from '@lucide/vue'
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
const pipeline = ['queued', 'cloning', 'installing', 'building', 'starting', 'health_checking', 'ready']
const currentStage = computed(() => previewStore.activePreview?.status ?? '')
const canStart = computed(() => record.value?.approved && (!previewStore.activePreview || ['stopped', 'expired', 'failed'].includes(previewStore.activePreview.status)))
const canStop = computed(() => previewStore.activePreview && !['stopping', 'stopped', 'expired', 'failed'].includes(previewStore.activePreview.status))
const formattedRemaining = computed(() => {
  const minutes = Math.floor(previewStore.remainingSeconds / 60)
  return `${minutes}:${String(previewStore.remainingSeconds % 60).padStart(2, '0')}`
})

watch(() => props.workspaceId, (workspaceId) => previewStore.load(workspaceId), { immediate: true })

function parseEnvironmentNames(value: string) {
  return [...new Set(value.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean))]
}

function captureBrowserOpened(source: string) {
  if (typeof posthog?.capture === 'function') {
    posthog.capture('browser_opened', { source })
  }
}
</script>

<template>
  <section class="panel panel-pad preview-lab">
    <div class="panel-heading">
      <div>
        <h2><FlaskConical :size="17" /> Realtime Preview Lab</h2>
        <p class="preview-lab__subtitle">Analyze, approve, and execute a temporary web preview outside the API process.</p>
      </div>
      <span class="preview-lab__phase">Phase 2 · trusted local execution</span>
    </div>

    <div class="preview-lab__notice">
      <ShieldAlert :size="17" aria-hidden="true" />
      <span>Docker execution is for trusted development repositories only. Production hostile-repository isolation requires the Kubernetes/gVisor phase.</span>
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

      <div v-if="record.approved" class="preview-lab__approved"><CheckCircle2 :size="17" aria-hidden="true" /> Manifest revision {{ record.revision }} is approved for preview execution.</div>

      <div v-if="record.approved" class="preview-runtime">
        <div class="preview-runtime__header">
          <div><h3>Preview execution</h3><p>Runs at immutable commit <code>{{ previewStore.activePreview?.commitSha.slice(0, 10) ?? 'from workspace' }}</code>.</p></div>
          <span v-if="previewStore.activePreview" class="preview-runtime__status" :data-status="previewStore.activePreview.status">{{ previewStore.activePreview.status.replace('_', ' ') }}</span>
        </div>

        <div v-if="record.manifest.environment.required.length || record.manifest.environment.optional.length" class="preview-runtime__environment">
          <label v-for="name in [...record.manifest.environment.required, ...record.manifest.environment.optional]" :key="name">
            <span>{{ name }} {{ record.manifest.environment.required.includes(name) ? '· required' : '· optional' }}</span>
            <input class="input input--mono" type="password" autocomplete="off"
              :disabled="Boolean(previewStore.activePreview && !['stopped', 'expired', 'failed'].includes(previewStore.activePreview.status))"
              :value="previewStore.environment[name]" placeholder="Injected once; never persisted"
              @input="previewStore.setEnvironment(name, ($event.target as HTMLInputElement).value)">
          </label>
        </div>

        <div class="preview-runtime__actions">
          <button class="btn btn-primary" type="button" :disabled="!canStart || previewStore.starting || previewStore.concurrencyBlocked" @click="previewStore.start">{{ previewStore.starting ? 'Queuing...' : 'Start preview' }}</button>
          <a v-if="previewStore.activePreview?.previewUrl" class="btn btn-ghost" :href="previewStore.activePreview.previewUrl" target="_blank" rel="noopener noreferrer" @click="captureBrowserOpened('preview')"><ExternalLink :size="15" /> Open preview</a>
          <button v-if="previewStore.activePreview?.status === 'ready'" class="btn btn-ghost" type="button" :disabled="previewStore.extending" @click="previewStore.extend"><Clock3 :size="15" /> {{ previewStore.extending ? 'Extending...' : `Extend · ${formattedRemaining}` }}</button>
          <button v-if="canStop" class="btn btn-danger" type="button" :disabled="previewStore.stopping" @click="previewStore.stop"><Square :size="14" /> {{ previewStore.stopping ? 'Stopping...' : 'Stop' }}</button>
        </div>

        <div v-if="previewStore.activePreview" class="preview-runtime__pipeline" aria-label="Preview lifecycle">
          <div v-for="(stage, index) in pipeline" :key="stage" class="preview-runtime__stage" :class="{
            'preview-runtime__stage--active': currentStage === stage,
            'preview-runtime__stage--done': pipeline.indexOf(currentStage) > index || currentStage === 'ready',
          }"><span></span><small>{{ stage.replace('_', ' ') }}</small></div>
        </div>

        <p v-if="previewStore.activePreview?.errorMessage" class="error-text">{{ previewStore.activePreview.errorCode }} · {{ previewStore.activePreview.errorMessage }}</p>
        <iframe v-if="previewStore.activePreview?.status === 'ready' && previewStore.activePreview.previewUrl"
          class="preview-runtime__frame" :src="previewStore.activePreview.previewUrl" title="Repository preview"
          sandbox="allow-forms allow-modals allow-popups allow-same-origin allow-scripts" />

        <details v-if="previewStore.logs || previewStore.events.length" class="preview-runtime__console" open>
          <summary><Terminal :size="15" /> Execution output</summary>
          <ol v-if="previewStore.events.length" class="preview-runtime__events">
            <li v-for="event in previewStore.events" :key="event.id"><time>{{ new Date(event.createdAt).toLocaleTimeString() }}</time>{{ event.message }}</li>
          </ol>
          <pre v-if="previewStore.logs">{{ previewStore.logs }}</pre>
        </details>
      </div>

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
