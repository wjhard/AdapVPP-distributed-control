<script setup lang="ts">
defineProps<{
  title: string
  accent?: string
}>()
</script>

<template>
  <section class="panel" :style="{ '--accent': accent ?? '#36d7ff' }">
    <div class="panel__header">
      <span class="panel__beam"></span>
      <h2>{{ title }}</h2>
      <slot name="meta"></slot>
    </div>
    <div class="panel__body">
      <slot></slot>
    </div>
  </section>
</template>
