<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ArrowLeft, ChevronDown, RefreshCw, Search, ShieldAlert } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'
import {
  deleteAdminUser, getAdminDashboard, listAdminBrowserSessions, listAdminFeatureFlags,
  listAdminLogs, listAdminPreviews, listAdminUsage, listAdminUsers, setAdminUserSuspended,
  terminateAdminBrowserSession, terminateAdminPreview, updateAdminFeatureFlag,
  extractAPIError, listAdminSupportTickets, updateAdminSupportTicketStatus,
} from '../services/api'
import { supportCategoryLabels, supportStatusLabels } from '../support/labels'
import type {
  AdminBrowserSession, AdminDashboard, AdminFeatureFlag, AdminLog, AdminPreview, AdminSupportTicket, AdminUsage,
  AdminUser, SupportTicketStatus,
} from '../types/api'

const auth = useAuthStore()
const dashboard = ref<AdminDashboard | null>(null)
const users = ref<AdminUser[]>([])
const previews = ref<AdminPreview[]>([])
const sessions = ref<AdminBrowserSession[]>([])
const usage = ref<AdminUsage[]>([])
const flags = ref<AdminFeatureFlag[]>([])
const logs = ref<AdminLog[]>([])
const supportTickets = ref<AdminSupportTicket[]>([])
const supportFilter = ref<SupportTicketStatus | 'ALL'>('ALL')
const expandedTicketId = ref<string | null>(null)
const updatingTicketId = ref<string | null>(null)
const supportError = ref('')
const supportFilters: { value: SupportTicketStatus | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All' },
  { value: 'OPEN', label: 'Open' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'COMPLETED', label: 'Completed' },
]
const filteredSupportTickets = computed(() => supportFilter.value === 'ALL'
  ? supportTickets.value
  : supportTickets.value.filter((ticket) => ticket.status === supportFilter.value))
const openTicketCount = computed(() => supportTickets.value.filter((ticket) => ticket.status !== 'COMPLETED').length)
const query = ref('')
const loading = ref(false)
const error = ref('')
const isAdmin = computed(() => auth.user?.role === 'ADMIN')
const killSwitches = computed(() => flags.value.filter((flag) => ['preview', 'ai_generation', 'uploads'].includes(flag.key)))

function formatDate(value: string | null) { return value ? new Date(value).toLocaleString() : 'Never' }
function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 ** 2).toFixed(1)} MB`
}
function shortId(value: string) { return value.slice(0, 8) }

async function loadAll() {
  if (!isAdmin.value) return
  loading.value = true
  error.value = ''
  try {
    const [summary, nextUsers, nextPreviews, nextSessions, nextUsage, nextFlags, nextLogs, nextTickets] = await Promise.all([
      getAdminDashboard(), listAdminUsers(query.value), listAdminPreviews(), listAdminBrowserSessions(),
      listAdminUsage(), listAdminFeatureFlags(), listAdminLogs(), listAdminSupportTickets(),
    ])
    dashboard.value = summary; users.value = nextUsers; previews.value = nextPreviews
    sessions.value = nextSessions; usage.value = nextUsage; flags.value = nextFlags; logs.value = nextLogs
    supportTickets.value = nextTickets
  } catch (caught) { error.value = caught instanceof Error ? caught.message : 'Could not load admin data.' }
  finally { loading.value = false }
}

async function searchUsers() { users.value = await listAdminUsers(query.value) }
async function toggleUser(user: AdminUser) {
  const updated = await setAdminUserSuspended(user.id, user.status !== 'SUSPENDED')
  users.value = users.value.map((item) => item.id === updated.id ? updated : item)
}
async function removeUser(user: AdminUser) {
  if (!window.confirm(`Delete ${user.primaryEmail}? This cannot be undone.`)) return
  await deleteAdminUser(user.id); await loadAll()
}
async function stopPreview(id: string) { await terminateAdminPreview(id); await loadAll() }
async function stopSession(id: string) { await terminateAdminBrowserSession(id); await loadAll() }
async function toggleFlag(flag: AdminFeatureFlag) {
  const updated = await updateAdminFeatureFlag(flag.key, !flag.enabled)
  flags.value = flags.value.map((item) => item.key === updated.key ? updated : item)
}
async function setTicketStatus(ticket: AdminSupportTicket, status: Exclude<SupportTicketStatus, 'OPEN'>) {
  if (status === 'COMPLETED' && !window.confirm(`Mark "${ticket.subject}" as completed? The requester will be emailed.`)) return
  updatingTicketId.value = ticket.id
  supportError.value = ''
  try {
    const updated = await updateAdminSupportTicketStatus(ticket.id, status)
    supportTickets.value = supportTickets.value.map((item) => item.id === updated.id ? updated : item)
  } catch (caught) {
    supportError.value = extractAPIError(caught, 'Could not update the ticket.').message
  } finally {
    updatingTicketId.value = null
  }
}
function toggleTicket(id: string) { expandedTicketId.value = expandedTicketId.value === id ? null : id }

onMounted(loadAll)
watch(isAdmin, (allowed) => { if (allowed && !dashboard.value) void loadAll() })
</script>

<template>
  <main class="admin-shell">
    <header class="admin-header">
      <div><RouterLink class="admin-back" to="/"><ArrowLeft :size="16" /> Back to TestForge</RouterLink><h1>Admin control plane</h1><p>Users, live infrastructure, usage, and emergency controls.</p></div>
      <button class="btn btn-ghost" :disabled="loading" @click="loadAll"><RefreshCw :size="16" :class="{ spin: loading }" /> Refresh</button>
    </header>

    <div v-if="!isAdmin" class="admin-denied"><ShieldAlert /><h2>Administrator access required</h2><p>This area is only available to accounts with the ADMIN role.</p></div>
    <template v-else>
      <p v-if="error" class="error-text">{{ error }}</p>
      <section class="admin-metrics">
        <article><span>Total users</span><strong>{{ dashboard?.totalUsers ?? '—' }}</strong></article>
        <article><span>Active previews</span><strong>{{ dashboard?.activePreviews ?? '—' }}</strong></article>
        <article><span>Browser sessions</span><strong>{{ dashboard?.activeBrowserSessions ?? '—' }}</strong></article>
      </section>

      <section class="admin-card">
        <div class="admin-card__heading"><div><h2>Kill switches</h2><p>Changes take effect on new requests immediately.</p></div></div>
        <div class="admin-flags">
          <label v-for="flag in killSwitches" :key="flag.key"><span><strong>{{ flag.key.replace('_', ' ') }}</strong><small>{{ flag.description }}</small></span><input type="checkbox" :checked="flag.enabled" @change="toggleFlag(flag)"></label>
        </div>
      </section>

      <section id="support" class="admin-card">
        <div class="admin-card__heading">
          <div><h2>Support tickets</h2><p>{{ openTicketCount }} awaiting resolution · {{ supportTickets.length }} total</p></div>
          <div class="support-filters" role="tablist" aria-label="Filter tickets by status">
            <button v-for="filter in supportFilters" :key="filter.value" type="button" role="tab" :aria-selected="supportFilter === filter.value" :class="{ 'is-active': supportFilter === filter.value }" @click="supportFilter = filter.value">{{ filter.label }}</button>
          </div>
        </div>
        <p v-if="supportError" class="error-text">{{ supportError }}</p>
        <div v-if="!filteredSupportTickets.length" class="admin-empty">No support tickets{{ supportFilter === 'ALL' ? '' : ` with status ${supportStatusLabels[supportFilter]}` }}.</div>
        <article v-for="ticket in filteredSupportTickets" :key="ticket.id" class="support-ticket" :class="{ 'is-open': expandedTicketId === ticket.id }">
          <button class="support-ticket__summary" type="button" :aria-expanded="expandedTicketId === ticket.id" @click="toggleTicket(ticket.id)">
            <span class="support-ticket__title">
              <strong>{{ ticket.subject }}</strong>
              <small>{{ supportCategoryLabels[ticket.category] }} · {{ ticket.userDisplayName || ticket.userEmail }} · {{ formatDate(ticket.createdAt) }}</small>
            </span>
            <span class="admin-status support-status" :class="`is-${ticket.status.toLowerCase()}`">{{ supportStatusLabels[ticket.status] }}</span>
            <ChevronDown :size="16" class="support-ticket__chevron" aria-hidden="true" />
          </button>
          <div v-if="expandedTicketId === ticket.id" class="support-ticket__details">
            <p class="support-ticket__meta">From <a :href="`mailto:${ticket.userEmail}`">{{ ticket.userEmail }}</a> · Ticket {{ shortId(ticket.id) }}<template v-if="ticket.inProgressAt"> · In progress {{ formatDate(ticket.inProgressAt) }}</template><template v-if="ticket.completedAt"> · Completed {{ formatDate(ticket.completedAt) }}</template></p>
            <!-- descriptionHtml is sanitized server-side with an allowlist before it is stored. -->
            <div class="support-content" v-html="ticket.descriptionHtml" />
            <div v-if="ticket.status !== 'COMPLETED'" class="admin-actions support-ticket__actions">
              <button v-if="ticket.status === 'OPEN'" class="btn btn-ghost" :disabled="updatingTicketId === ticket.id" @click="setTicketStatus(ticket, 'IN_PROGRESS')">Mark in progress</button>
              <button class="btn btn-primary" :disabled="updatingTicketId === ticket.id" @click="setTicketStatus(ticket, 'COMPLETED')">Mark completed</button>
            </div>
          </div>
        </article>
      </section>

      <section class="admin-card">
        <div class="admin-card__heading"><div><h2>User management</h2><p>{{ users.length }} matching accounts</p></div><form class="admin-search" @submit.prevent="searchUsers"><Search :size="16" /><input v-model="query" aria-label="Search users" placeholder="Search email or name"><button class="btn btn-ghost">Search</button></form></div>
        <div class="admin-table-wrap"><table><thead><tr><th>User</th><th>Status</th><th>Role</th><th>Last login</th><th></th></tr></thead><tbody><tr v-for="user in users" :key="user.id"><td><strong>{{ user.displayName || user.primaryEmail }}</strong><small>{{ user.primaryEmail }}</small></td><td><span class="admin-status" :class="`is-${user.status.toLowerCase()}`">{{ user.status }}</span></td><td>{{ user.role }}</td><td>{{ formatDate(user.lastLoginAt) }}</td><td class="admin-actions"><button class="btn btn-ghost" :disabled="user.id === auth.user?.id" @click="toggleUser(user)">{{ user.status === 'SUSPENDED' ? 'Unsuspend' : 'Suspend' }}</button><button class="btn btn-danger" :disabled="user.id === auth.user?.id" @click="removeUser(user)">Delete</button></td></tr></tbody></table></div>
      </section>

      <section class="admin-grid">
        <article class="admin-card"><div class="admin-card__heading"><div><h2>Active previews</h2><p>{{ previews.length }} running</p></div></div><div v-if="!previews.length" class="admin-empty">No active previews.</div><div v-for="preview in previews" :key="preview.id" class="admin-resource"><div><strong>{{ preview.userEmail || 'Deleted user' }}</strong><span>{{ preview.status }} · {{ preview.provider }} · {{ shortId(preview.id) }}</span></div><button class="btn btn-danger" @click="stopPreview(preview.id)">Terminate</button></div></article>
        <article class="admin-card"><div class="admin-card__heading"><div><h2>Browser sessions</h2><p>{{ sessions.length }} running</p></div></div><div v-if="!sessions.length" class="admin-empty">No active browser sessions.</div><div v-for="session in sessions" :key="session.id" class="admin-resource"><div><strong>{{ session.userEmail || 'Deleted user' }}</strong><span>{{ session.status }} · {{ session.provider }} · {{ shortId(session.id) }}</span></div><button class="btn btn-danger" @click="stopSession(session.id)">Terminate</button></div></article>
      </section>

      <section class="admin-card"><div class="admin-card__heading"><div><h2>Usage &amp; cost signals</h2><p>Lifetime application usage by user.</p></div></div><div class="admin-table-wrap"><table><thead><tr><th>User</th><th>AI requests</th><th>Previews</th><th>Preview minutes</th><th>Storage</th></tr></thead><tbody><tr v-for="item in usage" :key="item.userId"><td>{{ item.primaryEmail }}</td><td>{{ item.aiRequests }}</td><td>{{ item.previewCount }}</td><td>{{ item.previewMinutes }}</td><td>{{ formatBytes(item.storageBytes) }}</td></tr></tbody></table></div></section>

      <section class="admin-card"><div class="admin-card__heading"><div><h2>Operational logs</h2><p>Authentication, failed builds, and runtime failures.</p></div></div><div v-if="!logs.length" class="admin-empty">No failures recorded.</div><div v-for="log in logs" :key="log.id" class="admin-log"><time>{{ formatDate(log.createdAt) }}</time><span class="admin-status is-error">{{ log.category }}</span><code>{{ log.code || 'ERROR' }}</code><p>{{ log.message }}</p></div></section>
    </template>
  </main>
</template>
