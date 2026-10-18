<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { marked, type Tokens } from 'marked'
import hljs from 'highlight.js'

const props = defineProps<{ content: string }>()

// ── Renderer ────────────────────────────────────────────────────────────────
// We collect code blocks separately so we can attach copy handlers via refs.
interface CodeBlock { id: string; raw: string }
const codeBlocks = ref<CodeBlock[]>([])

function buildRenderer() {
  const renderer = new marked.Renderer()
  const blocks: CodeBlock[] = []

  renderer.code = ({ text, lang }: Tokens.Code) => {
    const id = `cb-${Math.random().toString(36).slice(2)}`
    const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
    const highlighted = hljs.highlight(text, { language }).value
    blocks.push({ id, raw: text })
    return `
      <div class="md-code-block" data-cb-id="${id}">
        <div class="md-code-block__header">
          <span class="md-code-block__lang">${language}</span>
          <button class="md-code-block__copy" data-cb-id="${id}" type="button">Copy</button>
        </div>
        <pre class="md-code-block__pre"><code class="hljs language-${language}">${highlighted}</code></pre>
      </div>`
  }

  // Inline code
  renderer.codespan = ({ text }: Tokens.Codespan) =>
    `<code class="md-inline-code">${text}</code>`

  return { renderer, blocks }
}

const html = computed(() => {
  if (!props.content) return ''
  const { renderer, blocks } = buildRenderer()
  marked.setOptions({ renderer })
  const result = marked.parse(props.content) as string
  // Schedule updating refs after render
  nextTick(() => { codeBlocks.value = blocks })
  return result
})

// ── Copy handler ─────────────────────────────────────────────────────────────
// const root = ref<HTMLElement | null>(null)
const copiedId = ref<string | null>(null)
let copyTimer: ReturnType<typeof setTimeout> | null = null

function handleClick(e: MouseEvent) {
  const btn = (e.target as HTMLElement).closest<HTMLButtonElement>('.md-code-block__copy')
  if (!btn) return
  const id = btn.dataset.cbId
  const block = codeBlocks.value.find(b => b.id === id)
  if (!block) return
  navigator.clipboard.writeText(block.raw).then(() => {
    copiedId.value = id ?? null
    btn.textContent = 'Copied!'
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copiedId.value = null
      btn.textContent = 'Copy'
    }, 1500)
  })
}

watch(html, () => {
  // re-bind after content changes (handled via delegation, nothing extra needed)
})
</script>

<template>
  <!-- eslint-disable-next-line vue/no-v-html -->
  <div ref="root" class="md-body" v-html="html" @click="handleClick" />
</template>

<style scoped>
/* ── Prose base ─────────────────────────────────────────────────────────── */
.md-body {
  color: var(--text);
  font-size: 0.875rem;
  line-height: 1.75;
  overflow-wrap: break-word;
}

/* Headings */
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3),
.md-body :deep(h4) {
  margin: 1.4em 0 0.45em;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.25;
}
.md-body :deep(h1) { font-size: 1.35rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3em; }
.md-body :deep(h2) { font-size: 1.1rem; color: var(--brand-400); }
.md-body :deep(h3) { font-size: 0.97rem; color: var(--accent-400); }
.md-body :deep(h4) { font-size: 0.9rem; }

/* Paragraphs */
.md-body :deep(p) {
  margin: 0.55em 0;
}

/* Lists */
.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 0.55em 0;
  padding-left: 1.4em;
}
.md-body :deep(li) {
  margin: 0.3em 0;
}
.md-body :deep(li > p) {
  margin: 0;
}
.md-body :deep(li::marker) {
  color: var(--brand-500);
}

/* Bold / italic */
.md-body :deep(strong) {
  font-weight: 700;
  color: var(--text);
}
.md-body :deep(em) {
  color: var(--muted);
  font-style: italic;
}

/* Inline code */
.md-body :deep(.md-inline-code) {
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  font-size: 0.8em;
  background: rgba(34, 211, 238, 0.1);
  color: var(--brand-300);
  border: 1px solid rgba(34, 211, 238, 0.18);
  border-radius: 4px;
  padding: 0.1em 0.4em;
}

/* Blockquote */
.md-body :deep(blockquote) {
  border-left: 3px solid var(--brand-500);
  margin: 0.75em 0;
  padding: 0.4em 1em;
  background: rgba(34, 211, 238, 0.05);
  border-radius: 0 6px 6px 0;
  color: var(--muted);
}

/* Horizontal rule */
.md-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.2em 0;
}

/* ── Code block ──────────────────────────────────────────────────────────── */
.md-body :deep(.md-code-block) {
  margin: 0.9em 0;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: rgba(7, 16, 25, 0.85);
  overflow: hidden;
}

.md-body :deep(.md-code-block__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.45rem 0.85rem;
  background: rgba(18, 29, 49, 0.9);
  border-bottom: 1px solid rgba(58, 74, 114, 0.4);
}

.md-body :deep(.md-code-block__lang) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.7rem;
  color: var(--brand-400);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.md-body :deep(.md-code-block__copy) {
  font-size: 0.72rem;
  padding: 0.2rem 0.65rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(34, 211, 238, 0.07);
  color: var(--brand-300);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  font-family: inherit;
}
.md-body :deep(.md-code-block__copy:hover) {
  background: rgba(34, 211, 238, 0.18);
  color: var(--brand-400);
}

.md-body :deep(.md-code-block__pre) {
  margin: 0;
  padding: 1rem 1.1rem;
  overflow-x: auto;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  font-size: 0.78rem;
  line-height: 1.65;
  white-space: pre;
}

.md-body :deep(.md-code-block__pre code) {
  background: transparent;
  padding: 0;
  border: none;
  font-size: inherit;
  color: #cdd6f4;
}

/* ── highlight.js token colours (dark theme subset) ─────────────────────── */
.md-body :deep(.hljs-keyword)   { color: #cba6f7; }
.md-body :deep(.hljs-string)    { color: #a6e3a1; }
.md-body :deep(.hljs-comment)   { color: #6c7086; font-style: italic; }
.md-body :deep(.hljs-number)    { color: #fab387; }
.md-body :deep(.hljs-type),
.md-body :deep(.hljs-class)     { color: #89dceb; }
.md-body :deep(.hljs-title)     { color: #89b4fa; }
.md-body :deep(.hljs-built_in)  { color: #f38ba8; }
.md-body :deep(.hljs-attr),
.md-body :deep(.hljs-attribute) { color: #f9e2af; }
.md-body :deep(.hljs-variable)  { color: #cdd6f4; }
.md-body :deep(.hljs-meta)      { color: #74c7ec; }
.md-body :deep(.hljs-literal)   { color: #fab387; }
.md-body :deep(.hljs-operator)  { color: #89dceb; }
.md-body :deep(.hljs-punctuation){ color: #cdd6f4; }
.md-body :deep(.hljs-tag)       { color: #f38ba8; }

/* Light-theme overrides */
:root[data-theme='light'] .md-body :deep(.md-inline-code) {
  /* background: rgba(79, 70, 229, 0.08); */
  color: var(--brand-300);
  border-color: rgba(79, 70, 229, 0.2);
}
:root[data-theme='light'] .md-body :deep(.md-code-block) {
  background: #1e1e2e;
}
:root[data-theme='light'] .md-body :deep(.md-code-block__header) {
  background: #181825;
}
:root[data-theme='light'] .md-body :deep(.md-code-block__copy) {
  border-color: rgba(79, 70, 229, 0.3);
  color: #818cf8;
  background: rgba(79, 70, 229, 0.07);
}
:root[data-theme='light'] .md-body :deep(.md-code-block__copy:hover) {
  background: rgba(79, 70, 229, 0.15);
}
</style>
