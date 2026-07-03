<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { NODES } from '../constants'
import type { TelemetrySnapshot } from '../types'

const props = defineProps<{
  estimatedLoad: number
  history: TelemetrySnapshot[]
}>()

const option = computed<EChartsOption>(() => {
  const rows = props.history.length > 0 ? props.history : []
  const xAxis = rows.map((item) => `${item.elapsed_s.toFixed(0)}s`)
  const nodeSeries = NODES.map((node, index) => ({
    name: node.key,
    type: 'line' as const,
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 2 },
    data: rows.map((item) => Number((item.command_mw[index] ?? 0).toFixed(3))),
  }))
  const total = rows.map((item) =>
    Number(item.command_mw.reduce((sum, value) => sum + value, 0).toFixed(3)),
  )
  const load = rows.map((item) => Number(estimateLoad(item, props.estimatedLoad).toFixed(3)))

  return {
    color: ['#ffd166', '#f8b95d', '#5bd8ff', '#49a8ff', '#a4ff7a', '#ffffff', '#ff8e8e'],
    tooltip: { trigger: 'axis', confine: true },
    legend: {
      top: 2,
      right: 6,
      textStyle: { color: '#b8d7e8', fontSize: 10 },
      itemWidth: 12,
      itemHeight: 7,
    },
    grid: { left: 44, right: 20, top: 38, bottom: 28 },
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
        lineStyle: { width: 4 },
        data: total,
      },
      {
        name: '负荷需求',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 3, type: 'dashed' },
        data: load,
      },
    ],
  }
})

function estimateLoad(item: TelemetrySnapshot, latestLoad: number) {
  const match = item.note.match(/demand=([0-9.]+)/)
  return match ? Number(match[1]) : latestLoad
}
</script>

<template>
  <VChart class="chart" :option="option" autoresize />
</template>
