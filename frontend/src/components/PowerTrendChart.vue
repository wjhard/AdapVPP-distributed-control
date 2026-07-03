<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import { MODE_LABELS, NODES } from '../constants'
import type { OperatingMode, TelemetrySnapshot } from '../types'

const props = defineProps<{
  estimatedLoad: number
  history: TelemetrySnapshot[]
  mode: OperatingMode
}>()

const showDetails = ref(false)

const latestTotal = computed(() => {
  const latest = props.history.at(-1)
  if (!latest) {
    return 0
  }
  return latest.command_mw.reduce((sum, value) => sum + value, 0)
})

const latestLoad = computed(() => props.estimatedLoad)
const balanceGap = computed(() => latestTotal.value - latestLoad.value)

const balanceStatus = computed(() => {
  const gap = balanceGap.value
  if (Math.abs(gap) <= 1) {
    return {
      label: '供需平衡',
      value: Math.abs(gap),
      className: 'status-balanced',
    }
  }
  if (gap < 0) {
    return {
      label: `供给不足 ${Math.abs(gap).toFixed(1)}MW`,
      value: Math.abs(gap),
      className: 'status-shortage',
    }
  }
  return {
    label: `供给富余 ${gap.toFixed(1)}MW`,
    value: gap,
    className: 'status-surplus',
  }
})

const modeImpactText = computed(() => {
  if (props.mode === 'autonomous') {
    return '当前完全自治：各节点独立按本地策略运行，调度指令以无扰动平滑过渡为主。'
  }
  if (props.mode === 'local_cluster') {
    return '当前局部聚类：组内协同分担负荷，组间减少直接依赖。'
  }
  return '当前全局协同：所有节点统一参与分布式优化，优先维持供需平衡。'
})

const option = computed<EChartsOption>(() => {
  const rows = props.history.length > 0 ? props.history : []
  const xAxis = rows.map((item) => `${item.elapsed_s.toFixed(0)}s`)
  const total = rows.map((item) =>
    Number(item.command_mw.reduce((sum, value) => sum + value, 0).toFixed(3)),
  )
  const load = rows.map((item) => Number(estimateLoad(item, props.estimatedLoad).toFixed(3)))

  const nodeSeries = showDetails.value
    ? NODES.map((node, index) => ({
        name: node.key,
        type: 'line' as const,
        smooth: true,
        symbol: 'none',
        z: 1,
        emphasis: { disabled: true },
        lineStyle: {
          width: 1.2,
          opacity: 0.42,
          color: ['#68818d', '#7c919c', '#6f8fa1', '#7797a8', '#86a09a'][index],
        },
        data: rows.map((item) => Number((item.command_mw[index] ?? 0).toFixed(3))),
      }))
    : []

  return {
    color: ['#38f3ff', '#ff6b6b'],
    tooltip: { trigger: 'axis', confine: true },
    legend: {
      top: 4,
      left: 110,
      textStyle: { color: '#b8d7e8', fontSize: 10 },
      itemWidth: 14,
      itemHeight: 7,
      selectedMode: false,
    },
    grid: { left: 44, right: 18, top: 50, bottom: 46 },
    xAxis: {
      type: 'category',
      data: xAxis,
      boundaryGap: false,
      axisLabel: { color: '#7fa7ba', fontSize: 10 },
      axisLine: { lineStyle: { color: '#24536a' } },
    },
    yAxis: {
      type: 'value',
      name: 'MW',
      nameTextStyle: { color: '#7fa7ba' },
      axisLabel: { color: '#7fa7ba' },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.12)' } },
    },
    series: [
      ...nodeSeries,
      {
        name: '总出力',
        type: 'line',
        smooth: true,
        symbol: 'none',
        z: 5,
        lineStyle: { width: 4.2, color: '#38f3ff' },
        areaStyle: { color: 'rgba(56, 243, 255, 0.06)' },
        data: total,
      },
      {
        name: '负荷需求',
        type: 'line',
        smooth: true,
        symbol: 'none',
        z: 6,
        lineStyle: { width: 3.5, type: 'dashed', color: '#ff6b6b' },
        data: load,
      },
    ],
  }
})

function estimateLoad(item: TelemetrySnapshot, latestLoadValue: number) {
  const match = item.note.match(/demand=([0-9.]+)/)
  return match ? Number(match[1]) : latestLoadValue
}
</script>

<template>
  <div class="power-trend">
    <div class="power-trend__toolbar">
      <label class="detail-toggle">
        <input v-model="showDetails" type="checkbox" />
        <span>节点明细</span>
      </label>
      <div class="balance-chip" :class="balanceStatus.className">
        {{ balanceStatus.label }}
      </div>
    </div>

    <VChart class="chart power-trend__chart" :option="option" autoresize />

    <div class="power-trend__note">
      <span>{{ MODE_LABELS[mode] }}</span>
      {{ modeImpactText }}
    </div>
  </div>
</template>

<style scoped>
.power-trend {
  position: relative;
  height: 100%;
  min-height: 0;
}

.power-trend__toolbar {
  position: absolute;
  z-index: 2;
  top: 3px;
  left: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  pointer-events: none;
}

.detail-toggle {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 8px;
  border: 1px solid rgba(126, 169, 184, 0.32);
  border-radius: 5px;
  color: #9bb9c4;
  background: rgba(7, 30, 37, 0.78);
  font-size: 12px;
}

.detail-toggle input {
  width: 13px;
  height: 13px;
  accent-color: #38f3ff;
}

.balance-chip {
  min-width: 116px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 10px;
  border: 1px solid currentColor;
  border-radius: 5px;
  font-family: Consolas, "Roboto Mono", monospace;
  font-size: 13px;
  font-weight: 800;
  background: rgba(7, 30, 37, 0.86);
}

.status-balanced {
  color: #29e6bb;
}

.status-shortage {
  color: #ff6b6b;
}

.status-surplus {
  color: #f5c84c;
}

.power-trend__chart {
  height: calc(100% - 30px);
}

.power-trend__note {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 0;
  min-height: 28px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #8fb6c3;
  font-size: 12px;
  line-height: 1.25;
}

.power-trend__note span {
  flex: 0 0 auto;
  padding: 2px 6px;
  border: 1px solid rgba(56, 243, 255, 0.28);
  border-radius: 4px;
  color: #dffcff;
  background: rgba(56, 243, 255, 0.08);
}
</style>
