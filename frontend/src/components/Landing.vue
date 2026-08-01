<script setup lang="ts">
import {
  AlertTriangle,
  FileText,
  FlaskConical,
  GitBranch,
  GitCompare,
  MessageSquareText,
  Network,
  ShieldCheck,
} from '@lucide/vue'
import RepositoryConnections from './RepositoryConnections.vue'

defineProps<{
  repoUrl: string
  docs: File[]
  busy: boolean
  error: string | null
  authenticated: boolean
}>()

const emit = defineEmits<{
  (e: 'update:repoUrl', value: string): void
  (e: 'update:docs', value: File[]): void
  (e: 'create'): void
}>()

const suggested = [
  'https://github.com/stripe/stripe-node',
  'https://github.com/vercel/next.js',
]

const cards = [
  { icon: Network, title: 'Build the workspace', body: 'Indexing, graph construction, and repository statistics — the foundation every later answer draws from.' },
  { icon: MessageSquareText, title: 'Ask the codebase', body: '"Explain the payment flow." TestForge walks the dependency graph and answers in plain English.' },
  { icon: FlaskConical, title: 'Generate integration tests', body: '"A customer retries payment after a timeout." Scenario-driven tests wired to the real modules they exercise.' },
  { icon: AlertTriangle, title: 'Code-quality insights', body: 'Highly coupled services, god functions, duplicated retry logic — with an explanation of why it matters.' },
  { icon: GitCompare, title: 'Impact analysis', body: 'Modify a file and see impacted components plus the recommended tests to rerun.' },
  { icon: ShieldCheck, title: 'Context-aware, not boilerplate', body: 'Every test and answer is grounded in the indexed graph — not a generic template.' },
]
</script>

<template>
  <div class="landing">
    <section class="landing__hero">
      <div class="landing__badge">Understand. Answer. Test.</div>
      <h1 class="landing__title">TestForge <span>AI</span></h1>
      <p class="landing__copy">
        Paste a repository and TestForge indexes the codebase, builds a dependency graph, answers engineering
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

      <RepositoryConnections v-if="authenticated" />
      <p v-else class="landing__footnote">
        Sign in when you are ready to build, or connect a source-control provider to browse private repositories.
      </p>
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
  </div>
</template>
