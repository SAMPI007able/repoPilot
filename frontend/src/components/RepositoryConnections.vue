<script setup lang="ts">
import { Cloud, Code2, GitBranch } from '@lucide/vue'

const providers = [
  {
    id: 'github',
    name: 'GitHub',
    icon: GitBranch,
    connectUrl: import.meta.env.VITE_GITHUB_CONNECT_URL || '',
  },
  {
    id: 'gitlab',
    name: 'GitLab',
    icon: Code2,
    connectUrl: import.meta.env.VITE_GITLAB_CONNECT_URL || '',
  },
  {
    id: 'bitbucket',
    name: 'Bitbucket',
    icon: Cloud,
    connectUrl: import.meta.env.VITE_BITBUCKET_CONNECT_URL || '',
  },
]

function connect(connectUrl: string) {
  if (connectUrl) window.location.assign(connectUrl)
}
</script>

<template>
  <section class="repository-connections" aria-labelledby="repository-connections-title">
    <div class="repository-connections__heading">
      <div>
        <p class="eyebrow">Your repositories</p>
        <h2 id="repository-connections-title">Connect a source-control provider</h2>
      </div>
      <p>Choose a provider to grant access to selected projects only.</p>
    </div>
    <div class="provider-grid">
      <article v-for="provider in providers" :key="provider.id" class="provider-card">
        <component :is="provider.icon" :size="22" />
        <div>
          <strong>{{ provider.name }}</strong>
          <span>{{ provider.connectUrl ? 'Ready to connect' : 'Administrator setup required' }}</span>
        </div>
        <button class="btn" type="button" :disabled="!provider.connectUrl" @click="connect(provider.connectUrl)">
          Connect
        </button>
      </article>
    </div>
    <div class="repository-empty">
      Authorized projects will appear here as repository cards after a provider is connected.
    </div>
  </section>
</template>
