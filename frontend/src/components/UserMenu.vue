<script setup lang="ts">
import { ChevronDown, LogIn, LogOut, Settings, UserRound } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { CurrentUser } from '../types/api'

const props = defineProps<{
  user: CurrentUser | null
  loading?: boolean
}>()

const emit = defineEmits<{
  signIn: []
  signOut: []
}>()

const menuOpen = ref(false)
const imageFailed = ref(false)
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const signOutButton = ref<HTMLButtonElement | null>(null)

const displayName = computed(() => props.user?.displayName?.trim() || props.user?.primaryEmail || 'Account')
const avatarUrl = computed(() => imageFailed.value ? null : props.user?.avatarUrl)
const initials = computed(() => {
  const name = props.user?.displayName?.trim()
  if (name) {
    const words = name.split(/\s+/).filter(Boolean)
    return `${words[0]?.[0] ?? ''}${words.length > 1 ? words.at(-1)?.[0] ?? '' : ''}`.toUpperCase()
  }
  return props.user?.primaryEmail?.[0]?.toUpperCase() || '?'
})

async function toggleMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) {
    await nextTick()
    signOutButton.value?.focus()
  }
}

function closeMenu(restoreFocus = false) {
  menuOpen.value = false
  if (restoreFocus) void nextTick(() => trigger.value?.focus())
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) closeMenu()
}

function onDocumentKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && menuOpen.value) closeMenu(true)
}

function signOut() {
  closeMenu()
  emit('signOut')
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeyDown)
})

watch(() => props.user?.avatarUrl, () => {
  imageFailed.value = false
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeyDown)
})
</script>

<template>
  <div ref="root" class="user-menu">
    <button
      v-if="!user"
      class="sign-in-button"
      type="button"
      :disabled="loading"
      @click="emit('signIn')"
    >
      <LogIn aria-hidden="true" />
      <span>{{ loading ? 'Signing in…' : 'Sign in' }}</span>
    </button>

    <template v-else>
      <button
        ref="trigger"
        class="user-menu__trigger"
        type="button"
        aria-haspopup="menu"
        aria-controls="account-menu"
        :aria-expanded="menuOpen"
        :aria-label="`Open account menu for ${displayName}`"
        @click="toggleMenu"
      >
        <span class="user-avatar" aria-hidden="true">
          <img
            v-if="avatarUrl"
            :src="avatarUrl"
            :alt="`${displayName} avatar`"
            decoding="async"
            fetchpriority="low"
            referrerpolicy="no-referrer"
            @error="imageFailed = true"
          />
          <span v-else>{{ initials }}</span>
        </span>
        <span class="user-menu__name">{{ displayName }}</span>
        <ChevronDown class="user-menu__chevron" :class="{ 'user-menu__chevron--open': menuOpen }" aria-hidden="true" />
      </button>

      <Transition name="account-menu">
        <div v-if="menuOpen" id="account-menu" class="user-menu__popover" role="menu">
          <div class="user-menu__identity">
            <span class="user-menu__identity-icon" aria-hidden="true"><UserRound /></span>
            <span class="user-menu__identity-copy">
              <strong>{{ displayName }}</strong>
              <span>{{ user.primaryEmail }}</span>
            </span>
          </div>
          <div class="user-menu__divider" />
          <RouterLink
            v-if="user.role === 'ADMIN'"
            class="user-menu__action"
            to="/admin"
            role="menuitem"
            @click="closeMenu()"
          >
            <Settings aria-hidden="true" />
            <span>Admin panel</span>
          </RouterLink>
          <button
            ref="signOutButton"
            class="user-menu__action"
            type="button"
            role="menuitem"
            :disabled="loading"
            @click="signOut"
          >
            <LogOut aria-hidden="true" />
            <span>{{ loading ? 'Signing out…' : 'Sign out' }}</span>
          </button>
        </div>
      </Transition>
    </template>
  </div>
</template>
