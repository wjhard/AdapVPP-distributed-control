<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { DELAY_THRESHOLDS, LOSS_THRESHOLDS } from '../constants'
import type { TelemetrySnapshot } from '../types'

const props = defineProps<{
  history: TelemetrySnapshot[]
}>()

const option = computed<EChartsOption>(() => {
  const rows = props.history
  return {
    color: ['#5bd8ff', '#ff8e8e'],
    tooltip: { trigger: 'axis', confine: true },
    legend: {
      top: 0,
      right: 8,
      textStyle: { color: '#b8d7e8', fontSize: 11 },
      itemWidth: 12,
      itemHeight: 7,
    },
    grid: { left: 48, right: 46, top: 38, bottom: 30 },
    xAxis: {
      type: 'category',
      data: rows.map((item) => `${item.elapsed_s.toFixed(0)}s`),
      boundaryGap: false,
      axisLabel: { color: '#7fa7ba', fontSize: 10 },
      axisLine: { lineStyle: { color: '#24536a' } },
    },
    yAxis: [
      {
        type: 'value',
        name: 'ms',
        min: 0,
        max: 520,
        nameTextStyle: { color: '#7fa7ba' },
        axisLabel: { color: '#7fa7ba' },
        splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.12)' } },
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 70,
        nameTextStyle: { color: '#7fa7ba' },
        axisLabel: { color: '#7fa7ba', formatter: '{value}' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '平均时延',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: rows.map((item) => item.average_delay_ms),
        markLine: {
          symbol: 'none',
          label: { color: '#d8f7ff', fontSize: 10 },
          lineStyle: { type: 'dashed', width: 1 },
          data: [
            { yAxis: DELAY_THRESHOLDS.clusterToGlobal, name: '恢复全局' },
            { yAxis: DELAY_THRESHOLDS.globalToCluster, name: '进入聚类' },
            { yAxis: DELAY_THRESHOLDS.clusterToAuto, name: '进入自治' },
          ],
        },
      },
      {
        name: '最大丢包率',
        type: 'line',
        smooth: true,
        symbol: 'none',
        yAxisIndex: 1,
        data: rows.map((item) => Number((item.max_loss_rate * 100).toFixed(2))),
        markLine: {
          symbol: 'none',
          label: { color: '#ffd4d4', fontSize: 10 },
          lineStyle: { type: 'dotted', width: 1 },
          data: [
            { yAxis: LOSS_THRESHOLDS.clusterToGlobal * 100, name: '8%' },
            { yAxis: LOSS_THRESHOLDS.globalToCluster * 100, name: '15%' },
            { yAxis: LOSS_THRESHOLDS.clusterToAuto * 100, name: '48%' },
          ],
        },
      },
    ],
  }
})
</script>

<template>
  <VChart class="chart" :option="option" autoresize />
</template>
