<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'

const props = defineProps<{
  savingRate: number
  liveDelta: number
}>()

const option = computed<EChartsOption>(() => ({
  series: [
    {
      type: 'gauge',
      startAngle: 210,
      endAngle: -30,
      min: 0,
      max: 100,
      radius: '92%',
      progress: {
        show: true,
        width: 18,
        itemStyle: { color: '#29e6bb' },
      },
      axisLine: {
        lineStyle: {
          width: 18,
          color: [
            [0.6, 'rgba(255, 107, 107, 0.45)'],
            [0.9, 'rgba(245, 200, 76, 0.45)'],
            [1, 'rgba(41, 230, 187, 0.45)'],
          ],
        },
      },
      pointer: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: { show: false },
      anchor: { show: false },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, '0%'],
        fontSize: 34,
        fontFamily: 'Consolas, monospace',
        color: '#eaffff',
        formatter: '{value}%',
      },
      data: [{ value: Number(props.savingRate.toFixed(1)) }],
    },
  ],
}))
</script>

<template>
  <div class="efficiency">
    <VChart class="efficiency__gauge" :option="option" autoresize />
    <div class="efficiency__stats">
      <div>
        <span>事件触发通信节省</span>
        <strong>{{ savingRate.toFixed(2) }}%</strong>
      </div>
      <div>
        <span>当前平滑步长</span>
        <strong>{{ liveDelta.toFixed(3) }} MW</strong>
      </div>
    </div>
  </div>
</template>
