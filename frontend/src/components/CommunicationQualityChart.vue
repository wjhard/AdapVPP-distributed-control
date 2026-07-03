<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { DELAY_THRESHOLDS, LOSS_THRESHOLDS, MODE_LABELS } from '../constants'
import type { OperatingMode, TelemetrySnapshot } from '../types'

const props = defineProps<{
  history: TelemetrySnapshot[]
}>()

const latest = computed(() => props.history.at(-1))

const delayRisk = computed(() =>
  latest.value ? Math.min(115, (latest.value.average_delay_ms / DELAY_THRESHOLDS.clusterToAuto) * 100) : 0,
)

const lossRisk = computed(() =>
  latest.value ? Math.min(115, (latest.value.max_loss_rate / LOSS_THRESHOLDS.clusterToAuto) * 100) : 0,
)

const currentRisk = computed(() => Math.max(delayRisk.value, lossRisk.value))

const qualityState = computed(() => {
  const mode = latest.value?.mode ?? 'global_cooperative'
  if (mode === 'autonomous' || currentRisk.value >= 100) {
    return {
      label: '通信质量：严重降级，已切换至自治模式',
      className: 'quality-danger',
    }
  }
  if (mode === 'local_cluster' || currentRisk.value >= 35) {
    return {
      label: '通信质量：中度降级，采用局部聚类协同',
      className: 'quality-warning',
    }
  }
  return {
    label: '通信质量：良好，可支持全局协同',
    className: 'quality-safe',
  }
})

const option = computed<EChartsOption>(() => {
  const rows = props.history
  return {
    color: ['#8bb2c0', '#b78d92'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter: (params) => formatTooltip(params),
    },
    legend: {
      show: false,
    },
    grid: { left: 46, right: 18, top: 56, bottom: 30 },
    xAxis: {
      type: 'category',
      data: rows.map((item) => `${item.elapsed_s.toFixed(0)}s`),
      boundaryGap: false,
      axisLabel: { color: '#7fa7ba', fontSize: 10 },
      axisLine: { lineStyle: { color: '#24536a' } },
    },
    yAxis: {
      type: 'value',
      name: '通信状态指数',
      min: 0,
      max: 115,
      nameTextStyle: { color: '#7fa7ba', fontSize: 10 },
      axisLabel: {
        color: '#7fa7ba',
        formatter: (value: number) => {
          if (value === 20) return '正常'
          if (value === 65) return '降级'
          if (value === 105) return '自治'
          return ''
        },
      },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
    },
    series: [
      {
        name: '安全区',
        type: 'line',
        data: [],
        markArea: {
          silent: true,
          itemStyle: { opacity: 0.18 },
          label: {
            color: '#d8f7ff',
            fontSize: 11,
            position: 'insideLeft',
          },
          data: [
            [
              { yAxis: 0, itemStyle: { color: '#29e6bb' }, name: '全局协同安全区' },
              { yAxis: 35 },
            ],
            [
              { yAxis: 35, itemStyle: { color: '#f5c84c' }, name: '局部聚类区' },
              { yAxis: 100 },
            ],
            [
              { yAxis: 100, itemStyle: { color: '#ff6b6b' }, name: '自治触发区' },
              { yAxis: 115 },
            ],
          ],
        },
      },
      {
        name: '时延风险',
        type: 'line',
        smooth: true,
        symbol: 'none',
        z: 4,
        lineStyle: { width: 2, color: '#8bb2c0', opacity: 0.86 },
        data: rows.map((item) => riskFromDelay(item.average_delay_ms)),
      },
      {
        name: '丢包风险',
        type: 'line',
        smooth: true,
        symbol: 'none',
        z: 5,
        lineStyle: { width: 2.4, color: '#ff8e8e', opacity: 0.92 },
        data: rows.map((item) => riskFromLoss(item.max_loss_rate)),
      },
    ],
  }
})

function riskFromDelay(delayMs: number) {
  return Math.min(115, (delayMs / DELAY_THRESHOLDS.clusterToAuto) * 100)
}

function riskFromLoss(lossRate: number) {
  return Math.min(115, (lossRate / LOSS_THRESHOLDS.clusterToAuto) * 100)
}

function formatTooltip(params: unknown) {
  const items = Array.isArray(params) ? params : []
  const lines = items
    .filter((item) => item && typeof item === 'object' && 'seriesName' in item)
    .map((item) => {
      const typed = item as { marker: string; seriesName: string; value: number }
      return `${typed.marker}${typed.seriesName}: ${Number(typed.value).toFixed(1)}`
    })
  return lines.join('<br/>')
}

function rawModeLabel(mode?: OperatingMode) {
  return MODE_LABELS[mode ?? 'global_cooperative']
}
</script>

<template>
  <div class="quality-chart">
    <div class="quality-chart__summary" :class="qualityState.className">
      {{ qualityState.label }}
    </div>

    <div class="quality-chart__raw">
      <span>模式 {{ rawModeLabel(latest?.mode) }}</span>
      <span>时延 {{ latest?.average_delay_ms.toFixed(1) ?? '0.0' }} ms</span>
      <span>丢包 {{ (((latest?.max_loss_rate ?? 0) * 100)).toFixed(1) }}%</span>
    </div>

    <VChart class="chart quality-chart__plot" :option="option" autoresize />
  </div>
</template>

<style scoped>
.quality-chart {
  position: relative;
  height: 100%;
  min-height: 0;
}

.quality-chart__summary {
  position: absolute;
  z-index: 2;
  top: 2px;
  left: 8px;
  right: 8px;
  height: 26px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid currentColor;
  border-radius: 5px;
  font-size: 13px;
  font-weight: 800;
  background: rgba(7, 30, 37, 0.86);
}

.quality-safe {
  color: #29e6bb;
}

.quality-warning {
  color: #f5c84c;
}

.quality-danger {
  color: #ff6b6b;
}

.quality-chart__raw {
  position: absolute;
  z-index: 2;
  top: 32px;
  right: 10px;
  display: flex;
  gap: 8px;
  color: #86aab7;
  font-family: Consolas, "Roboto Mono", monospace;
  font-size: 10px;
}

.quality-chart__raw span {
  padding: 2px 5px;
  border: 1px solid rgba(126, 169, 184, 0.18);
  border-radius: 4px;
  background: rgba(5, 24, 30, 0.72);
}

.quality-chart__plot {
  height: 100%;
}
</style>
