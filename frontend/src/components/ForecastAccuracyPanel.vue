<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { NODES } from '../constants'
import type { TelemetrySnapshot } from '../types'

const props = defineProps<{
  history: TelemetrySnapshot[]
}>()

const renewableNodes = NODES.slice(0, 4)
const colors = ['#ffd166', '#f6b35f', '#5bd8ff', '#7ebdff']

const latest = computed(() => props.history.at(-1))
const latestForecast = computed(() => latest.value?.forecast)

const option = computed<EChartsOption>(() => {
  const rows = props.history
  const xAxis = rows.map((item) => `${item.elapsed_s.toFixed(0)}s`)
  const series = renewableNodes.flatMap((node, index) => [
    {
      name: `${node.key} 实际`,
      type: 'line' as const,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2.3, color: colors[index] },
      data: rows.map((item) => Number((item.forecast.actual_mw[index] ?? 0).toFixed(3))),
    },
    {
      name: `${node.key} 预测`,
      type: 'line' as const,
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 1.8, type: 'dashed' as const, color: colors[index], opacity: 0.72 },
      data: rows.map((item) =>
        Number(((item.forecast.verified_forecast_mw ?? item.forecast.forecast_mw)[index] ?? 0).toFixed(3)),
      ),
    },
  ])

  return {
    color: colors,
    tooltip: { trigger: 'axis', confine: true },
    legend: {
      top: 0,
      type: 'scroll',
      textStyle: { color: '#b8d7e8', fontSize: 10 },
      itemWidth: 12,
      itemHeight: 7,
    },
    grid: { left: 42, right: 12, top: 44, bottom: 34 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: xAxis,
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
    series,
  }
})

function metric(value?: number, digits = 2) {
  return Number(value ?? 0).toFixed(digits)
}
</script>

<template>
  <div class="forecast-panel">
    <div class="forecast-panel__metrics">
      <div>
        <span>RMSE</span>
        <strong>{{ metric(latestForecast?.rmse_mw) }} MW</strong>
      </div>
      <div>
        <span>MAPE</span>
        <strong>{{ metric(latestForecast?.mape_percent) }}%</strong>
      </div>
      <div>
        <span>预测提前量</span>
        <strong>{{ metric(latestForecast?.horizon_minutes, 0) }} min</strong>
      </div>
    </div>

    <VChart class="chart forecast-panel__chart" :option="option" autoresize />

    <p class="forecast-panel__note">
      调度使用持续性预测+近期趋势外推，并叠加带时间相关性的预测误差。光伏误差按约8%-15%模拟，风电按约10%-20%模拟，且随预测提前量放大；该范围对应公开短期预测文献中风电误差常见10%-40%、光伏预测平均绝对误差约19%的量级。
    </p>
  </div>
</template>
