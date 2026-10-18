<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import { ArrowLeft, ChevronDown, LifeBuoy, Mail, RefreshCw, Send, ShieldCheck } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'
import { createSupportTicket, extractAPIError, listMySupportTickets } from '../services/api'
import {
  supportCategoryLabels, supportCategoryOptions, supportEmail, supportMailto, supportStatusLabels,
} from '../support/labels'
import type { SupportCategory, SupportTicket } from '../types/api'

const auth = useAuthStore()
const SupportEditor = defineAsyncComponent(() => import('../components/SupportEditor.vue'))
const category = ref<SupportCategory | ''>('')
const subject = ref('')
const description = ref('')
const richEditorReady = ref(false)
const submitting = ref(false)
const formError = ref('')
const successMessage = ref('')
const tickets = ref<SupportTicket[]>([])
const loadingTickets = ref(false)
const ticketsError = ref('')
const expandedId = ref<string | null>(null)
const isAdmin = computed(() => auth.user?.role === 'ADMIN')

function hasDescription(value: string) {
  const document = new DOMParser().parseFromString(value, 'text/html')
  return Boolean(document.body.textContent?.trim()) || document.querySelector('img') !== null
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : ''
}

async function loadTickets() {
  loadingTickets.value = true
  ticketsError.value = ''
  try {
    tickets.value = await listMySupportTickets()
  } catch (error) {
    ticketsError.value = extractAPIError(error, 'Could not load your support tickets.').message
  } finally {
    loadingTickets.value = false
  }
}

async function submit() {
  formError.value = ''
  successMessage.value = ''
  if (!category.value) { formError.value = 'Choose a category.'; return }
  if (subject.value.trim().length < 3) { formError.value = 'Add a subject of at least 3 characters.'; return }
  if (!hasDescription(description.value)) { formError.value = 'Describe the problem before submitting.'; return }

  submitting.value = true
  try {
    const ticket = await createSupportTicket({
      category: category.value,
      subject: subject.value.trim(),
      descriptionHtml: description.value,
    })
    tickets.value = [ticket, ...tickets.value.filter((item) => item.id !== ticket.id)]
    expandedId.value = ticket.id
    category.value = ''
    subject.value = ''
    description.value = ''
    successMessage.value = 'Your ticket was submitted. We will email you when its status changes.'
  } catch (error) {
    formError.value = extractAPIError(error, 'Could not submit your ticket.').message
  } finally {
    submitting.value = false
  }
}

function toggle(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}

onMounted(loadTickets)
</script>

<template>
  <main class="admin-shell support-shell">
    <header class="admin-header">
      <div>
        <RouterLink class="admin-back" to="/"><ArrowLeft :size="16" /> Back to TestForge</RouterLink>
        <h1>Support</h1>
        <p>Tell us what went wrong or what you need. Our team will follow up by email.</p>
      </div>
      <div class="support-header-actions">
        <a class="btn btn-ghost" :href="supportMailto" :title="supportEmail">
          <Mail :size="16" /> Email us
        </a>
        <RouterLink v-if="isAdmin" class="btn btn-ghost" to="/admin#support">
          <ShieldCheck :size="16" /> Manage all tickets
        </RouterLink>
      </div>
    </header>

    <div class="support-layout">
      <section class="admin-card support-form-card">
        <div class="admin-card__heading">
          <div><h2>New support request</h2><p>Screenshots help — paste or upload images into the description.</p></div>
        </div>
        <form class="support-form" novalidate @submit.prevent="submit">
          <label class="support-field">
            <span>Category</span>
            <select v-model="category" class="input" required :disabled="submitting">
              <option value="" disabled>Select a category</option>
              <option v-for="option in supportCategoryOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="support-field">
            <span>Subject</span>
            <input v-model="subject" class="input" maxlength="200" placeholder="Short summary of the issue" :disabled="submitting" required>
          </label>
          <div class="support-field">
            <span>
              Description
              <button
                v-if="!richEditorReady"
                class="support-editor-enable"
                type="button"
                @click="richEditorReady = true"
              >Enable rich formatting</button>
            </span>
            <SupportEditor
              v-if="richEditorReady"
              v-model="description"
              :disabled="submitting"
              placeholder="Steps to reproduce, what you expected, and what happened…"
            />
            <textarea
              v-else
              v-model="description"
              class="input support-description-fallback"
              :disabled="submitting"
              placeholder="Steps to reproduce, what you expected, and what happened…"
              rows="8"
            />
          </div>
          <p v-if="formError" class="error-text" role="alert">{{ formError }}</p>
          <p v-if="successMessage" class="support-success" role="status">{{ successMessage }}</p>
          <div class="support-form__actions">
            <button class="btn btn-primary" type="submit" :disabled="submitting">
              <Send :size="16" /> {{ submitting ? 'Submitting…' : 'Submit ticket' }}
            </button>
          </div>
        </form>
      </section>

      <section class="admin-card support-tickets-card">
        <div class="admin-card__heading">
          <div><h2>My support tickets</h2><p>{{ tickets.length }} {{ tickets.length === 1 ? 'ticket' : 'tickets' }}</p></div>
          <button class="btn btn-ghost" type="button" :disabled="loadingTickets" @click="loadTickets">
            <RefreshCw :size="16" :class="{ spin: loadingTickets }" /> Refresh
          </button>
        </div>
        <p v-if="ticketsError" class="error-text">{{ ticketsError }}</p>
        <div v-else-if="!tickets.length && !loadingTickets" class="admin-empty">
          <LifeBuoy :size="20" /><br>You haven't submitted any support tickets yet.
        </div>
        <article v-for="ticket in tickets" :key="ticket.id" class="support-ticket" :class="{ 'is-open': expandedId === ticket.id }">
          <button class="support-ticket__summary" type="button" :aria-expanded="expandedId === ticket.id" @click="toggle(ticket.id)">
            <span class="support-ticket__title">
              <strong>{{ ticket.subject }}</strong>
              <small>{{ supportCategoryLabels[ticket.category] }} · {{ formatDate(ticket.createdAt) }}</small>
            </span>
            <span class="admin-status support-status" :class="`is-${ticket.status.toLowerCase()}`">{{ supportStatusLabels[ticket.status] }}</span>
            <ChevronDown :size="16" class="support-ticket__chevron" aria-hidden="true" />
          </button>
          <div v-if="expandedId === ticket.id" class="support-ticket__details">
            <ol class="support-timeline">
              <li>Submitted {{ formatDate(ticket.createdAt) }}</li>
              <li v-if="ticket.inProgressAt">In progress {{ formatDate(ticket.inProgressAt) }}</li>
              <li v-if="ticket.completedAt">Completed {{ formatDate(ticket.completedAt) }}</li>
            </ol>
            <!-- descriptionHtml is sanitized server-side with an allowlist before it is stored. -->
            <div class="support-content" v-html="ticket.descriptionHtml" />
          </div>
        </article>
      </section>
    </div>
  </main>
</template>
