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
        offsetCenter: [0, '4%'],
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
    <div class="efficiency__gauge-wrap">
      <VChart class="efficiency__gauge" :option="option" autoresize />
      <span class="metric-badge metric-badge--history">历史统计均值</span>
    </div>
    <div class="efficiency__stats">
      <div>
        <span>事件触发通信节省 <em>历史统计均值</em></span>
        <strong>{{ savingRate.toFixed(2) }}%</strong>
      </div>
      <div>
        <span>当前平滑步长 <em class="metric-badge--live">实时</em></span>
        <strong>{{ liveDelta.toFixed(3) }} MW</strong>
      </div>
    </div>
  </div>
</template>

<style scoped>
.efficiency__gauge-wrap {
  position: relative;
  height: 100%;
  min-height: 0;
}

.metric-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 20px;
  padding: 0 7px;
  border: 1px solid currentColor;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1;
  font-style: normal;
}

.efficiency__gauge-wrap .metric-badge {
  position: absolute;
  left: 50%;
  top: 60%;
  transform: translateX(-50%);
}

.metric-badge--history {
  color: #a9c8d1;
  background: rgba(126, 169, 184, 0.1);
}

.metric-badge--live {
  color: #29e6bb;
  background: rgba(41, 230, 187, 0.08);
}

.efficiency__stats span em {
  margin-left: 6px;
}
</style>
