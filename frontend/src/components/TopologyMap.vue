<script setup lang="ts">
import { BatteryCharging, Sun, Wind } from '@lucide/vue'
import { computed } from 'vue'
import { LINK_KEYS, NODE_COLORS, NODES } from '../constants'
import type { NodeInfo, OperatingMode, TelemetrySnapshot } from '../types'

const props = defineProps<{
  snapshot: TelemetrySnapshot
}>()

const emit = defineEmits<{
  nodeSelected: [nodeId: number]
  linkSelected: [linkKey: string]
}>()

const iconByKind = {
  pv: Sun,
  wind: Wind,
  bess: BatteryCharging,
}

const nodeById = computed(() =>
  Object.fromEntries(NODES.map((node) => [node.id, node])) as Record<number, NodeInfo>,
)

const lines = computed(() =>
  LINK_KEYS.map((key) => {
    const [src, dst] = key.split('-').map(Number)
    const start = nodeById.value[src]
    const end = nodeById.value[dst]
    const link = props.snapshot.links[key]
    const sameCluster = props.snapshot.clusters.some(
      (cluster) => cluster.includes(src) && cluster.includes(dst),
    )
    return {
      key,
      start,
      end,
      link,
      sameCluster,
      visible: lineVisible(props.snapshot.mode, sameCluster, link?.available ?? false),
      color: linkColor(link?.delay_ms ?? 0, link?.loss_rate ?? 0),
      opacity: lineOpacity(props.snapshot.mode, sameCluster, link?.available ?? false),
      tooltip: linkTooltip(key, link),
    }
  }),
)

const clusterBoxes = computed(() => {
  if (props.snapshot.mode !== 'local_cluster') {
    return []
  }
  return props.snapshot.clusters
    .filter((cluster) => cluster.length > 1)
    .map((cluster, index) => {
      const nodes = cluster.map((id) => nodeById.value[id]).filter(Boolean)
      const xs = nodes.map((node) => node.x)
      const ys = nodes.map((node) => node.y)
      return {
        key: `${cluster.join('-')}-${index}`,
        label: `Cluster ${index + 1}`,
        left: Math.min(...xs) - 86,
        top: Math.min(...ys) - 72,
        width: Math.max(...xs) - Math.min(...xs) + 172,
        height: Math.max(...ys) - Math.min(...ys) + 152,
      }
    })
})

function commandFor(index: number) {
  return props.snapshot.command_mw[index] ?? 0
}

function utilization(node: NodeInfo, index: number) {
  return Math.max(0, Math.min(100, (Math.abs(commandFor(index)) / node.capacity) * 100))
}

function lineVisible(mode: OperatingMode, sameCluster: boolean, available: boolean) {
  if (mode === 'autonomous') {
    return false
  }
  if (mode === 'global_cooperative') {
    return true
  }
  return sameCluster && available
}

function lineOpacity(mode: OperatingMode, sameCluster: boolean, available: boolean) {
  if (mode === 'autonomous') {
    return 0
  }
  if (mode === 'global_cooperative') {
    return available ? 0.88 : 0.3
  }
  return sameCluster && available ? 0.92 : 0.1
}

function linkColor(delayMs: number, lossRate: number) {
  const score = delayMs / 340 + lossRate / 0.48
  if (score > 1.45) {
    return '#ff6b6b'
  }
  if (score > 0.78) {
    return '#f5c84c'
  }
  return '#29e6bb'
}

function linkTooltip(key: string, link: TelemetrySnapshot['links'][string] | undefined) {
  const configuredDelay = link?.configured_delay_ms ?? link?.delay_ms ?? 0
  const measuredRtt = link?.measured_rtt_ms ?? link?.delay_ms ?? 0
  const configuredLoss = link?.configured_loss_rate ?? link?.loss_rate ?? 0
  const measuredLoss = link?.loss_rate ?? 0
  const source = props.snapshot.real_network_measurement ? '真实Toxiproxy网络测量' : '公式仿真数据'
  return [
    `${key} ${source}`,
    `configured_delay: ${configuredDelay.toFixed(1)} ms`,
    `measured_rtt: ${measuredRtt.toFixed(1)} ms`,
    `configured_loss: ${(configuredLoss * 100).toFixed(1)}%`,
    `measured_loss: ${(measuredLoss * 100).toFixed(1)}%`,
  ].join('\n')
}
</script>

<template>
  <div class="topology">
    <div
      v-for="box in clusterBoxes"
      :key="box.key"
      class="cluster-box"
      :style="{
        left: `${box.left}px`,
        top: `${box.top}px`,
        width: `${box.width}px`,
        height: `${box.height}px`,
      }"
    >
      <span>{{ box.label }}</span>
    </div>

    <svg class="topology__links" viewBox="0 0 820 500" aria-hidden="true">
      <defs>
        <filter id="line-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.8" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <g v-for="line in lines" :key="line.key">
        <title>{{ line.tooltip }}</title>
        <line
          class="topology-line-hit"
          :x1="line.start.x"
          :y1="line.start.y"
          :x2="line.end.x"
          :y2="line.end.y"
          @click="emit('linkSelected', line.key)"
        />
        <line
          class="topology-line"
          :class="{ 'topology-line--flow': line.visible }"
          :x1="line.start.x"
          :y1="line.start.y"
          :x2="line.end.x"
          :y2="line.end.y"
          :stroke="line.color"
          :stroke-opacity="line.opacity"
          filter="url(#line-glow)"
          @click="emit('linkSelected', line.key)"
        />
      </g>
    </svg>

    <article
      v-for="(node, index) in NODES"
      :key="node.id"
      class="vpp-node"
      :class="[`vpp-node--${node.kind}`, { 'vpp-node--isolated': snapshot.mode === 'autonomous' }]"
      :style="{ left: `${node.x}px`, top: `${node.y}px`, '--node-color': NODE_COLORS[node.kind] }"
      role="button"
      tabindex="0"
      @click="emit('nodeSelected', node.id)"
      @keydown.enter.prevent="emit('nodeSelected', node.id)"
    >
      <div class="vpp-node__icon" :title="node.kind">
        <component :is="iconByKind[node.kind]" :size="30" />
      </div>
      <div class="vpp-node__main">
        <strong>{{ node.key }}</strong>
        <span>{{ commandFor(index).toFixed(2) }} MW</span>
      </div>
      <div class="vpp-node__bar">
        <i :style="{ width: `${utilization(node, index)}%` }"></i>
      </div>
    </article>
  </div>
</template>
