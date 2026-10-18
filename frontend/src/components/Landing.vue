<script setup lang="ts">
import {
  AlertTriangle,
  CirclePause,
  CirclePlay,
  FileText,
  FlaskConical,
  GitBranch,
  GitCompare,
  MessageSquareText,
  Network,
  FolderGit2,
  ArrowRight,
  ShieldCheck,
} from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

defineProps<{
  repoUrl: string
  docs: File[]
  busy: boolean
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'update:repoUrl', value: string): void
  (e: 'update:docs', value: File[]): void
  (e: 'create'): void
  (e: 'browse-repositories'): void
}>()

const suggested = [
  'https://github.com/stripe/stripe-node',
  'https://github.com/vercel/next.js',
]

const cards = [
  { icon: Network, title: 'Build the workspace', body: 'Indexing, graph construction, and repository statistics — the foundation every later answer draws from.' },
  { icon: MessageSquareText, title: 'Ask the codebase', body: '"Explain the payment flow." RepoPilot walks the dependency graph and answers in plain English.' },
  { icon: FlaskConical, title: 'Generate integration tests', body: '"A customer retries payment after a timeout." Scenario-driven tests wired to the real modules they exercise.' },
  { icon: AlertTriangle, title: 'Code-quality insights', body: 'Highly coupled services, god functions, duplicated retry logic — with an explanation of why it matters.' },
  { icon: GitCompare, title: 'Impact analysis', body: 'Modify a file and see impacted components plus the recommended tests to rerun.' },
  { icon: ShieldCheck, title: 'Context-aware, not boilerplate', body: 'Every test and answer is grounded in the indexed graph — not a generic template.' },
]

const demoVideo = ref<HTMLVideoElement | null>(null)
const isDemoVisible = ref(false)
const isDemoPlaying = ref(false)
const prefersReducedMotion = ref(
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
)
const playbackRequested = ref(!prefersReducedMotion.value)
const demoControlLabel = computed(() => isDemoPlaying.value ? 'Pause product walkthrough' : 'Play product walkthrough')

let demoObserver: IntersectionObserver | null = null
let motionPreference: MediaQueryList | null = null

function syncDemoPlayback() {
  const video = demoVideo.value
  if (!video) return

  const shouldPlay = playbackRequested.value
    && isDemoVisible.value
    && document.visibilityState === 'visible'

  if (!shouldPlay) {
    video.pause()
    return
  }

  void video.play().catch(() => {
    // Autoplay can still be rejected by a browser policy. Leave an explicit
    // play control rather than repeatedly retrying in the background.
    playbackRequested.value = false
    isDemoPlaying.value = false
  })
}

function toggleDemoPlayback() {
  playbackRequested.value = !isDemoPlaying.value
  syncDemoPlayback()
}

function handleMotionPreference(event: MediaQueryListEvent) {
  prefersReducedMotion.value = event.matches
  playbackRequested.value = !event.matches
}

function handleDocumentVisibility() {
  syncDemoPlayback()
}

watch([playbackRequested, isDemoVisible], syncDemoPlayback)

onMounted(() => {
  motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)')
  prefersReducedMotion.value = motionPreference.matches
  playbackRequested.value = !motionPreference.matches
  motionPreference.addEventListener('change', handleMotionPreference)

  if ('IntersectionObserver' in window && demoVideo.value) {
    demoObserver = new IntersectionObserver(([entry]) => {
      isDemoVisible.value = Boolean(entry?.isIntersecting)
    })
    demoObserver.observe(demoVideo.value)
  } else {
    isDemoVisible.value = true
  }

  document.addEventListener('visibilitychange', handleDocumentVisibility)
})

onUnmounted(() => {
  demoObserver?.disconnect()
  motionPreference?.removeEventListener('change', handleMotionPreference)
  document.removeEventListener('visibilitychange', handleDocumentVisibility)
})
</script>

<template>
  <div class="landing">
    <section class="landing__hero">
      <div class="landing__badge">Understand, run and validate any codebase</div>
      <h1 class="landing__title">Repo<span>Pilot</span></h1>
      <p class="landing__copy">
        Paste a repository and RepoPilot indexes the codebase, builds a dependency graph, answers engineering
        questions, surfaces code-quality insights, and generates context-aware integration tests.
      </p>

      <div class="panel landing__form">
        <div class="field-stack">
          <label class="section-title">
            <GitBranch class="h-2 w-2" :size="12" />
            Repository URL
          </label>
          <div class="landing__form-row">
            <input
              class="input"
              :value="repoUrl"
              placeholder="https://github.com/owner/repo"
              @input="emit('update:repoUrl', ($event.target as HTMLInputElement).value)"
              @keydown.enter.prevent="!busy && emit('create')"
            >
            <button class="btn btn-primary" type="button" :disabled="busy" @click="emit('create')">
              {{ busy ? 'Building...' : 'Build workspace' }}
            </button>
          </div>
        </div>

        <div class="field-stack">
          <div class="landing__docs-row">
            <div class="section-title">
              <FileText class="h-3.5 w-3.5" :size="12" />
              Architecture / design docs (optional)
            </div>
            <label class="upload-trigger" for="project-docs-upload">
              <FileText class="h-3 w-3" :size="12" />
              Upload
            </label>
            <input
              id="project-docs-upload"
              class="hidden-input"
              type="file"
              multiple
              @change="emit('update:docs', Array.from(($event.target as HTMLInputElement).files ?? []))"
            >
          </div>

          <div v-if="docs.length" class="landing__docs">
            <span v-for="file in docs" :key="file.name" class="chip">{{ file.name }}</span>
          </div>
        </div>

        <div class="landing__suggested">
          <button
            v-for="item in suggested"
            :key="item"
            class="chip chip--button"
            type="button"
            @click="emit('update:repoUrl', item)"
          >
            <GitBranch class="h-3 w-3" :size="12" />
            {{ item.replace('https://github.com/', '') }}
          </button>
        </div>

        <p v-if="error" class="error-text">{{ error }}</p>
      </div>

      <button class="repository-callout" type="button" @click="emit('browse-repositories')">
        <span class="repository-callout__icon"><FolderGit2 aria-hidden="true" /></span>
        <span class="repository-callout__copy">
          <strong>Browse your repositories</strong>
          <span>Connect GitHub, GitLab, or Bitbucket — or upload a local zip — and build a workspace from any repo.</span>
        </span>
        <ArrowRight class="repository-callout__arrow" aria-hidden="true" />
      </button>
    </section>

    <section class="landing__cards">
      <article v-for="card in cards" :key="card.title" class="panel panel-hover feature-card">
        <div class="feature-card__icon">
          <span class="glyph glyph--feature">
            <component :is="card.icon" :size="20" />
          </span>
        </div>
        <h3>{{ card.title }}</h3>
        <p>{{ card.body }}</p>
      </article>
    </section>

    <section class="demo-section" aria-label="RepoPilot product walkthrough">
        <div class="demo-frame">
          <video
            ref="demoVideo"
            :autoplay="!prefersReducedMotion"
            muted
            loop
            playsinline
            preload="metadata"
            poster="/images/repopilot-demo-poster.webp"
            aria-label="RepoPilot product walkthrough"
            @play="isDemoPlaying = true"
            @pause="isDemoPlaying = false"
          >
            <source src="/videos/repopilot-demo.webm" type="video/webm">
            <source src="/videos/repopilot-demo.mp4" type="video/mp4">
            Your browser does not support embedded video.
          </video>
          <button
            class="demo-control"
            type="button"
            :aria-label="demoControlLabel"
            :aria-pressed="isDemoPlaying"
            @click="toggleDemoPlayback"
          >
            <CirclePause v-if="isDemoPlaying" aria-hidden="true" />
            <CirclePlay v-else aria-hidden="true" />
            <span>{{ isDemoPlaying ? 'Pause' : 'Play' }}</span>
          </button>
          <p v-if="prefersReducedMotion && !playbackRequested" class="demo-motion-note">
            Autoplay is off because reduced motion is enabled.
          </p>
        </div>
      </section>
  </div>
</template>

<style scoped>
.demo-section {
  position: relative;
  z-index: 1;
  width: min(70rem, 100%);
  margin: 2rem auto 1.5rem;
}

.demo-frame {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(58, 74, 114, 0.55);
  border-radius: 16px;
  background: #071019;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.24);
}

.demo-frame video {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: contain;
  background: #071019;
}

.demo-control {
  position: absolute;
  right: 0.85rem;
  bottom: 0.85rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 999px;
  background: rgba(7, 16, 25, 0.88);
  color: #f8fafc;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 650;
  cursor: pointer;
  backdrop-filter: blur(10px);
}

.demo-control:hover {
  background: rgba(18, 29, 49, 0.96);
}

.demo-control:focus-visible {
  outline: 2px solid var(--brand-400);
  outline-offset: 3px;
}

.demo-control svg {
  width: 1rem;
  height: 1rem;
}

.demo-motion-note {
  position: absolute;
  left: 0.85rem;
  bottom: 0.85rem;
  max-width: calc(100% - 8rem);
  margin: 0;
  padding: 0.45rem 0.65rem;
  border-radius: 0.55rem;
  background: rgba(7, 16, 25, 0.84);
  color: #cbd5e1;
  font-size: 0.72rem;
  text-align: left;
  backdrop-filter: blur(10px);
}

@media (max-width: 640px) {
  .demo-section {
    margin-top: 1.5rem;
  }

  .demo-control span {
    display: none;
  }

  .demo-control {
    width: 2.5rem;
    justify-content: center;
    padding: 0;
  }

  .demo-motion-note {
    max-width: calc(100% - 4.75rem);
  }
}

@media (prefers-reduced-motion: reduce) {
  .demo-control,
  .demo-motion-note {
    backdrop-filter: none;
  }
}

:global(:root[data-theme='light']) .demo-frame {
  border-color: rgba(79, 70, 229, 0.24);
  box-shadow: 0 18px 45px rgba(51, 65, 85, 0.16);
}
</style>
