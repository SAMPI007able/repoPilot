<!-- components/SimpleIcon.vue -->
<template>
  <svg
    role="img"
    viewBox="0 0 24 24"
    xmlns="http://www.w3.org/2000/svg"
    :width="size"
    :height="size"
    :fill="color || `#${icon.hex}`"
  >
    <title>{{ icon.title }}</title>
    <path :d="icon.path" />
  </svg>
</template>

<script setup>
import * as icons from 'simple-icons/icons'

const props = defineProps({
  name: { type: String, required: true }, // e.g. 'siGithub'
  size: { type: [Number, String], default: 24 },
  color: { type: String, default: null }
})

const icon = icons[props.name]
</script>