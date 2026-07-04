<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { CostGapRow, MonteCarloRow, ScenarioResult } from '../types'

const props = defineProps<{
  costGap: CostGapRow[]
  monteCarlo: MonteCarloRow[]
  scenarios: Record<string, ScenarioResult>
}>()

const gapImageUrl = '/data/optimality_gap_convergence.png'

const convergenceOption = computed<EChartsOption>(() => {
  const items = [
    { key: 'scenario2', name: 'ET-ADMM 轻度', color: '#29e6bb' },
    { key: 'scenario2b', name: '标准ADMM 轻度', color: '#ff9b70' },
    { key: 'scenario3', name: 'ET-ADMM 重度', color: '#5bd8ff' },
    { key: 'scenario3b', name: '标准ADMM 重度', color: '#ff6b6b' },
  ]

  return {
    color: items.map((item) => item.color),
    tooltip: { trigger: 'axis', confine: true },
    legend: {
      top: 0,
      textStyle: { color: '#b8d7e8', fontSize: 11 },
      itemWidth: 12,
      itemHeight: 7,
    },
    grid: { top: 42, left: 58, right: 18, bottom: 34 },
    xAxis: {
      type: 'value',
      name: '迭代',
      nameTextStyle: { color: '#7fa7ba' },
      axisLabel: { color: '#7fa7ba' },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
    },
    yAxis: {
      type: 'log',
      name: '残差',
      min: 1e-8,
      nameTextStyle: { color: '#7fa7ba' },
      axisLabel: { color: '#7fa7ba' },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
    },
    series: items.map((item) => ({
      name: item.name,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: {
        width: item.key.endsWith('b') ? 2 : 3,
        type: item.key.endsWith('b') ? 'dashed' : 'solid',
      },
      data: toPairs(props.scenarios[item.key]?.conv ?? []),
    })),
  }
})

const robustRows = computed(() =>
  props.monteCarlo.filter((row) => row.Method.toLowerCase().includes('et-admm')),
)
const standardRows = computed(() =>
  props.monteCarlo.filter((row) => row.Method.toLowerCase().includes('standard')),
)
const robustSuccess = computed(() =>
  average(robustRows.value.map((row) => Number(row.ConvergenceSuccessRate))),
)
const standardSuccess = computed(() =>
  average(standardRows.value.map((row) => Number(row.ConvergenceSuccessRate))),
)
const robustCommSaving = computed(() =>
  average(robustRows.value.map((row) => Number(row.CommSavingMean))),
)
const heavyLoss = computed(() =>
  Number(props.costGap[1]?.AnnualizedLoss ?? props.costGap[0]?.AnnualizedLoss ?? 0),
)
const heavyGap = computed(() =>
  Number(props.costGap[1]?.PercentGap ?? props.costGap[0]?.PercentGap ?? 0),
)

function toPairs(values: number[]) {
  return values.map((value, index) => [index + 1, Math.max(Number(value), 1e-8)])
}

function average(values: number[]) {
  const valid = values.filter((value) => Number.isFinite(value))
  if (valid.length === 0) {
    return 0
  }
  return valid.reduce((sum, value) => sum + value, 0) / valid.length
}

function money(value: number) {
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}
</script>

<template>
  <div class="algorithm-board">
    <div class="algorithm-board__chart">
      <VChart class="chart" :option="convergenceOption" autoresize />
    </div>

    <div class="algorithm-board__gap-panel">
      <div class="gap-panel__title">
        <span>最优性间隙收敛曲线</span>
        <em>optimality gap</em>
      </div>
      <img class="gap-panel__image" :src="gapImageUrl" alt="最优性间隙收敛曲线" />
      <p class="algorithm-board__methodology">
        本方案采用与国际主流分布式优化文献一致的最优性验证方法：将分布式ADMM迭代过程中每一步的解，与通过独立凸优化求解器计算得到的理论最优解进行逐次比对，追踪最优性间隙的完整收敛轨迹，而非仅比较最终结果，确保收敛过程本身具备数学上的可验证性。
      </p>
    </div>

    <div class="algorithm-board__cards">
      <div class="algo-card algo-card--success">
        <span>本方案收敛成功率</span>
        <strong>{{ robustSuccess.toFixed(0) }}%</strong>
        <em>30次蒙特卡洛</em>
      </div>
      <div class="algo-card algo-card--danger">
        <span>传统方法成功率</span>
        <strong>{{ standardSuccess.toFixed(0) }}%</strong>
        <em>弱通信下发散</em>
      </div>
      <div class="algo-card algo-card--saving">
        <span>通信量节省</span>
        <strong>{{ robustCommSaving.toFixed(2) }}%</strong>
        <em>事件触发机制</em>
      </div>
      <div class="algo-card algo-card--money">
        <span>重度弱通信年化损失</span>
        <strong>{{ money(heavyLoss) }} 元</strong>
        <em>较最优高 {{ heavyGap.toFixed(2) }}%</em>
      </div>
    </div>
  </div>
</template>
