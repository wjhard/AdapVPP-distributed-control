<script setup lang="ts">
import { Activity, Network, RadioTower, ShieldCheck } from '@lucide/vue'
import { computed } from 'vue'
import { MODE_CLASS, MODE_COLORS, MODE_LABELS } from '../constants'
import type { ConnectionStatus, OperatingMode } from '../types'

const props = defineProps<{
  activeControllers: string[]
  averageDelay: number
  backend: string
  lossRate: number
  mode: OperatingMode
  realNetworkMeasurement: boolean
  source: string
  status: ConnectionStatus
  totalPower: number
}>()

const statusText = computed(() => {
  if (props.status !== 'live') {
    return 'DEMO'
  }
  return props.realNetworkMeasurement ? 'LIVE·真实网络' : 'LIVE·仿真'
})
const modeColor = computed(() => MODE_COLORS[props.mode])
</script>

<template>
  <header class="topbar" :class="MODE_CLASS[mode]">
    <div class="brand">
      <div class="brand__mark">
        <Network :size="30" />
      </div>
      <div>
        <div class="brand__title">弱通信自适应虚拟电厂数字孪生监控平台</div>
        <div class="brand__sub">{{ source }} · {{ backend }}</div>
        <div class="controller-tags" aria-label="当前生效控制器">
          <span v-for="controller in activeControllers" :key="controller">
            {{ controller }}
          </span>
        </div>
      </div>
    </div>

    <div class="mode-pill" :style="{ '--mode-color': modeColor }">
      <span class="mode-pill__lamp"></span>
      <span>{{ MODE_LABELS[mode] }}</span>
    </div>

    <div class="top-metrics">
      <div class="top-metric">
        <RadioTower :size="22" />
        <span>平均时延</span>
        <strong>{{ averageDelay.toFixed(1) }}</strong>
        <em>ms</em>
      </div>
      <div class="top-metric">
        <Activity :size="22" />
        <span>最大丢包率</span>
        <strong>{{ (lossRate * 100).toFixed(1) }}</strong>
        <em>%</em>
      </div>
      <div class="top-metric">
        <ShieldCheck :size="22" />
        <span>总出力指令</span>
        <strong>{{ totalPower.toFixed(1) }}</strong>
        <em>MW</em>
      </div>
      <div
        class="status-chip"
        :class="{
          'status-chip--live': status === 'live',
          'status-chip--real': status === 'live' && realNetworkMeasurement,
        }"
      >
        {{ statusText }}
      </div>
    </div>
  </header>
</template>
