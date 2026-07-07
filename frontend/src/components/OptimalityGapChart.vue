<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed, ref } from 'vue'
import VChart from 'vue-echarts'
import type { OptimalityGapRow } from '../types'

const props = defineProps<{
  rows: OptimalityGapRow[]
}>()

const ALL_SCENARIOS = '全部场景'

const selectedScenario = ref<string | null>(null)
const tableOpen = ref(false)
const tableScenario = ref(ALL_SCENARIOS)

const scenarioColors = ['#38f3ff', '#29e6bb', '#f5c84c', '#b38cff']

const groupedRows = computed(() => {
  const groups = new Map<string, OptimalityGapRow[]>()
  props.rows.forEach((row) => {
    if (!row.Scenario) {
      return
    }
    const list = groups.get(row.Scenario) ?? []
    list.push(row)
    groups.set(row.Scenario, list)
  })
  return [...groups.entries()]
})

const scenarios = computed(() => groupedRows.value.map(([scenario]) => scenario))

const visibleGroups = computed(() => {
  if (!selectedScenario.value) {
    return groupedRows.value
  }
  return groupedRows.value.filter(([scenario]) => scenario === selectedScenario.value)
})

const tableRows = computed(() => {
  const source =
    tableScenario.value === ALL_SCENARIOS
      ? props.rows
      : props.rows.filter((row) => row.Scenario === tableScenario.value)
  return source.slice(0, 220)
})

const option = computed<EChartsOption>(() => ({
  color: scenarioColors,
  tooltip: {
    trigger: 'axis',
    confine: true,
    formatter(params: any) {
      const items = Array.isArray(params) ? params : [params]
      return items
        .map((item: any) => {
          const raw = item.data?.raw as OptimalityGapRow | undefined
          if (!raw) {
            return ''
          }
          return [
            `<strong>${raw.Scenario}</strong>`,
            `迭代 k=${raw.Iteration}`,
            `距离理论最优解 ${formatNumber(raw.DistanceToPStarMW)} MW`,
            `optimality gap ${formatNumber(raw.OptimalityGap)}`,
          ].join('<br/>')
        })
        .join('<br/><br/>')
    },
  },
  legend: {
    top: 0,
    textStyle: { color: '#b8d7e8', fontSize: 10 },
    itemWidth: 12,
    itemHeight: 7,
  },
  grid: { left: 54, right: 14, top: 34, bottom: 34 },
  xAxis: {
    type: 'value',
    name: '迭代',
    nameTextStyle: { color: '#7fa7ba' },
    axisLabel: { color: '#7fa7ba', fontSize: 10 },
    splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
  },
  yAxis: {
    type: 'log',
    name: 'optimality gap',
    min: 1e-12,
    nameTextStyle: { color: '#7fa7ba' },
    axisLabel: { color: '#7fa7ba', fontSize: 10 },
    splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
  },
  series: visibleGroups.value.map(([scenario, rows], index) => ({
    name: scenario,
    type: 'line',
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 2.4, color: scenarioColors[index % scenarioColors.length] },
    emphasis: { focus: 'series' },
    data: rows.map((row) => ({
      value: [Number(row.Iteration), Math.max(Number(row.OptimalityGapForLog), 1e-12)],
      raw: row,
    })),
  })),
}))

function handleChartClick(params: any) {
  const name = String(params?.seriesName ?? '')
  if (!name) {
    return
  }
  selectedScenario.value = selectedScenario.value === name ? null : name
  tableScenario.value = selectedScenario.value ?? ALL_SCENARIOS
}

function setScenario(scenario: string | null) {
  selectedScenario.value = scenario
  tableScenario.value = scenario ?? ALL_SCENARIOS
}

function formatNumber(value: string | number) {
  const num = Number(value)
  if (!Number.isFinite(num)) {
    return '--'
  }
  if (Math.abs(num) >= 100 || Math.abs(num) < 0.001) {
    return num.toExponential(3)
  }
  return num.toFixed(6)
}
</script>

<template>
  <div class="optimality-gap">
    <div class="gap-panel__title">
      <span>最优性间隙收敛曲线</span>
      <em>点击曲线聚焦</em>
    </div>

    <div class="optimality-gap__toolbar">
      <button
        v-for="scenario in scenarios"
        :key="scenario"
        :class="{ 'is-active': selectedScenario === scenario }"
        type="button"
        @click="setScenario(selectedScenario === scenario ? null : scenario)"
      >
        {{ scenario }}
      </button>
      <button type="button" @click="setScenario(null)">全部</button>
    </div>

    <VChart class="chart optimality-gap__chart" :option="option" autoresize @click="handleChartClick" />

    <button class="optimality-gap__table-toggle" type="button" @click="tableOpen = !tableOpen">
      {{ tableOpen ? '收起原始数据表' : '展开原始数据表' }}
    </button>

    <div v-if="tableOpen" class="optimality-gap__table-wrap">
      <label>
        场景筛选
        <select v-model="tableScenario">
          <option>{{ ALL_SCENARIOS }}</option>
          <option v-for="scenario in scenarios" :key="scenario">{{ scenario }}</option>
        </select>
      </label>
      <table>
        <thead>
          <tr>
            <th>场景</th>
            <th>迭代</th>
            <th>距离/MW</th>
            <th>Gap</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="`${row.Scenario}-${row.Iteration}`">
            <td>{{ row.Scenario }}</td>
            <td>{{ row.Iteration }}</td>
            <td>{{ formatNumber(row.DistanceToPStarMW) }}</td>
            <td>{{ formatNumber(row.OptimalityGap) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
