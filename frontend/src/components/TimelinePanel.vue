<script setup lang="ts">
import { computed } from 'vue'
import { MODE_COLORS, MODE_LABELS } from '../constants'
import type { TransitionRecord } from '../types'

const props = defineProps<{
  liveTransitions: TransitionRecord[]
  staticTransitions: TransitionRecord[]
}>()

const emit = defineEmits<{
  transitionSelected: [record: TransitionRecord]
}>()

const records = computed(() =>
  (props.liveTransitions.length > 0 ? props.liveTransitions : props.staticTransitions).slice(-6),
)
</script>

<template>
  <ol class="timeline">
    <li
      v-for="record in records"
      :key="`${record.elapsed_s}-${record.from}-${record.to}`"
      class="timeline__item"
      role="button"
      tabindex="0"
      @click="emit('transitionSelected', record)"
      @keydown.enter.prevent="emit('transitionSelected', record)"
    >
      <span class="timeline__dot" :style="{ background: MODE_COLORS[record.to] }"></span>
      <div class="timeline__main">
        <strong>{{ record.elapsed_s.toFixed(1) }}s</strong>
        <span>{{ MODE_LABELS[record.from] }} → {{ MODE_LABELS[record.to] }}</span>
        <em>{{ record.reason }}</em>
      </div>
      <div class="timeline__metric">
        {{ record.delay_ms.toFixed(1) }}ms / {{ (record.loss_rate * 100).toFixed(1) }}%
      </div>
    </li>
  </ol>
</template>
