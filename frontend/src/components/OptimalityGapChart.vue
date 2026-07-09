<script setup lang="ts">
import { Maximize2, X } from '@lucide/vue'
import type { EChartsOption } from 'echarts'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import VChart from 'vue-echarts'
import type { OptimalityGapRow } from '../types'

const props = defineProps<{
  rows: OptimalityGapRow[]
}>()

const ALL_SCENARIOS = '全部场景'
const scenarioColors = ['#38f3ff', '#29e6bb', '#f5c84c', '#b38cff']

const detailOpen = ref(false)
const selectedScenario = ref<string | null>(null)
const tableOpen = ref(false)
const tableScenario = ref(ALL_SCENARIOS)

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
  return source.slice(0, 600)
})

const overviewOption = computed<EChartsOption>(() => ({
  color: scenarioColors,
  animation: false,
  grid: { left: 8, right: 8, top: 8, bottom: 8 },
  xAxis: {
    type: 'value',
    show: false,
  },
  yAxis: {
    type: 'log',
    min: 1e-12,
    show: false,
  },
  series: groupedRows.value.map(([scenario, rows], index) => ({
    name: scenario,
    type: 'line',
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 2, color: scenarioColors[index % scenarioColors.length] },
    data: rows.map((row) => [
      Number(row.Iteration),
      Math.max(Number(row.OptimalityGapForLog), 1e-12),
    ]),
  })),
}))

const detailOption = computed<EChartsOption>(() => ({
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
            `iteration k=${raw.Iteration}`,
            `distance to P*: ${formatNumber(raw.DistanceToPStarMW)} MW`,
            `optimality gap: ${formatNumber(raw.OptimalityGap)}`,
          ].join('<br/>')
        })
        .join('<br/><br/>')
    },
  },
  legend: {
    top: 0,
    textStyle: { color: '#c9e7f2', fontSize: 13 },
    itemWidth: 16,
    itemHeight: 8,
  },
  grid: { left: 76, right: 24, top: 48, bottom: 54 },
  xAxis: {
    type: 'value',
    name: 'Iteration',
    nameTextStyle: { color: '#9ec4d0', fontSize: 13 },
    axisLabel: { color: '#a8cbd8', fontSize: 12 },
    splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
  },
  yAxis: {
    type: 'log',
    name: 'Optimality gap',
    min: 1e-12,
    nameTextStyle: { color: '#9ec4d0', fontSize: 13 },
    axisLabel: { color: '#a8cbd8', fontSize: 12 },
    splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
  },
  series: visibleGroups.value.map(([scenario, rows], index) => ({
    name: scenario,
    type: 'line',
    smooth: true,
    symbol: 'none',
    lineStyle: { width: 3, color: scenarioColors[index % scenarioColors.length] },
    emphasis: { focus: 'series' },
    data: rows.map((row) => ({
      value: [Number(row.Iteration), Math.max(Number(row.OptimalityGapForLog), 1e-12)],
      raw: row,
    })),
  })),
}))

function openDetail() {
  detailOpen.value = true
}

function closeDetail() {
  detailOpen.value = false
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

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && detailOpen.value) {
    closeDetail()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="optimality-gap-overview">
    <button class="optimality-gap-overview__hit" type="button" @click="openDetail">
      <VChart class="chart optimality-gap-overview__chart" :option="overviewOption" autoresize />
      <span class="optimality-gap-overview__cta">
        <Maximize2 :size="14" />
        查看详情
      </span>
    </button>
    <p>四场景均收敛至理论最优，点击查看完整轨迹。</p>
  </div>

  <Teleport to="body">
    <div v-if="detailOpen" class="optimality-gap-modal" role="dialog" aria-modal="true">
      <div class="optimality-gap-modal__panel">
        <header class="optimality-gap-modal__header">
          <div>
            <strong>最优性间隙收敛详情</strong>
            <span>Overview first, zoom and filter, then details on demand.</span>
          </div>
          <button type="button" class="optimality-gap-modal__close" @click="closeDetail">
            <X :size="20" />
            返回总览
          </button>
        </header>

        <div class="optimality-gap-modal__toolbar">
          <button
            :class="{ 'is-active': selectedScenario === null }"
            type="button"
            @click="setScenario(null)"
          >
            全部场景
          </button>
          <button
            v-for="scenario in scenarios"
            :key="scenario"
            :class="{ 'is-active': selectedScenario === scenario }"
            type="button"
            @click="setScenario(selectedScenario === scenario ? null : scenario)"
          >
            {{ scenario }}
          </button>
        </div>

        <VChart class="chart optimality-gap-modal__chart" :option="detailOption" autoresize />

        <section class="optimality-gap-modal__table">
          <button type="button" @click="tableOpen = !tableOpen">
            {{ tableOpen ? '收起原始数据表' : '展开原始数据表' }}
          </button>
          <div v-if="tableOpen" class="optimality-gap-modal__table-wrap">
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
                  <th>距离 P*/MW</th>
                  <th>Optimality gap</th>
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
        </section>
      </div>
    </div>
  </Teleport>
</template>
