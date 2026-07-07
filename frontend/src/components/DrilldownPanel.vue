<script setup lang="ts">
import type { EChartsOption } from 'echarts'
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { DELAY_THRESHOLDS, LINK_KEYS, MODE_COLORS, MODE_LABELS, NODES } from '../constants'
import type { DrilldownView, LinkMetric, ScenarioResult, TelemetrySnapshot } from '../types'

const props = defineProps<{
  view: DrilldownView | null
  current: TelemetrySnapshot
  history: TelemetrySnapshot[]
  scenarios: Record<string, ScenarioResult>
}>()

const emit = defineEmits<{
  close: []
}>()

const title = computed(() => {
  if (!props.view) {
    return ''
  }
  if (props.view.type === 'node') {
    return `${nodeById(props.view.nodeId)?.name ?? `节点${props.view.nodeId}`} 详情`
  }
  if (props.view.type === 'link') {
    return `${linkLabel(props.view.linkKey)} 链路诊断`
  }
  return `${props.view.record.elapsed_s.toFixed(1)}s 状态切换详情`
})

const activeNode = computed(() => {
  if (props.view?.type !== 'node') {
    return null
  }
  return nodeById(props.view.nodeId)
})

const activeLink = computed(() => {
  if (props.view?.type !== 'link') {
    return null
  }
  return props.view.linkKey
})

const activeTransition = computed(() => (props.view?.type === 'transition' ? props.view.record : null))

const relatedLinks = computed(() => {
  const node = activeNode.value
  if (!node) {
    return []
  }
  return LINK_KEYS.filter((key) => key.split('-').map(Number).includes(node.id)).map((key) => ({
    key,
    label: linkLabel(key),
    metric: props.current.links[key],
  }))
})

const nodeTrendOption = computed<EChartsOption>(() => {
  const node = activeNode.value
  if (!node) {
    return {}
  }
  const index = node.id - 1
  return makeLineOption({
    title: '近期出力变化',
    yName: 'MW',
    series: [
      {
        name: node.key,
        color: '#38f3ff',
        data: props.history.map((snapshot) => [
          snapshot.elapsed_s,
          Number(snapshot.command_mw[index] ?? 0),
        ]),
      },
    ],
  })
})

const admmTraceOption = computed<EChartsOption>(() => {
  const node = activeNode.value
  if (!node) {
    return {}
  }
  const scenario = preferredScenario(props.scenarios, props.current.mode)
  const residuals = scenario?.conv?.length ? scenario.conv : [1, 0.5, 0.2, 0.08, 0.02, 0.005]
  const finalValue =
    Number(scenario?.P?.[node.id - 1]) ||
    Number(props.current.target_mw[node.id - 1]) ||
    Number(props.current.command_mw[node.id - 1]) ||
    0
  const initialValue = Number(props.history[0]?.command_mw[node.id - 1] ?? finalValue * 0.72)
  const firstResidual = Math.max(Math.abs(Number(residuals[0])), 1e-9)
  const data = residuals.map((value, index) => {
    const scale = Math.min(1, Math.max(0, Math.abs(Number(value)) / firstResidual))
    return [index + 1, finalValue + (initialValue - finalValue) * scale]
  })

  return makeLineOption({
    title: 'ADMM节点出力收敛轨迹',
    xName: '迭代',
    yName: 'MW',
    series: [{ name: node.key, color: '#f5c84c', data }],
  })
})

const linkHistoryOption = computed<EChartsOption>(() => {
  const key = activeLink.value
  if (!key) {
    return {}
  }
  return makeDualAxisOption(key)
})

const transitionRows = computed(() => {
  const record = activeTransition.value
  if (!record) {
    return []
  }
  const nearestBefore = nearestSnapshot(record.elapsed_s - 0.1, 'before')
  const nearestAfter = nearestSnapshot(record.elapsed_s + 0.1, 'after')
  const before = record.before_mw ?? nearestBefore?.command_mw ?? []
  const after = record.after_mw ?? nearestAfter?.command_mw ?? props.current.command_mw

  return NODES.map((node, index) => {
    const beforeValue = Number(before[index] ?? 0)
    const afterValue = Number(after[index] ?? 0)
    return {
      key: node.key,
      name: node.name,
      before: beforeValue,
      after: afterValue,
      delta: afterValue - beforeValue,
    }
  })
})

const transitionLinks = computed(() => {
  const record = activeTransition.value
  if (!record) {
    return []
  }
  const snapshot = nearestSnapshot(record.elapsed_s, 'nearest') ?? props.current
  const links = LINK_KEYS.map((key) => ({
    key,
    label: linkLabel(key),
    metric: snapshot.links[key],
    score: linkScore(snapshot.links[key]),
  })).sort((a, b) => b.score - a.score)

  const degraded = links.filter((item) => item.score >= 1 || item.metric?.available === false)
  return (degraded.length > 0 ? degraded : links).slice(0, 5)
})

const linkDetailMetric = computed(() => {
  const key = activeLink.value
  return key ? props.current.links[key] : undefined
})

function makeDualAxisOption(key: string): EChartsOption {
  return {
    tooltip: {
      trigger: 'axis',
      confine: true,
      formatter(params: any) {
        const items = Array.isArray(params) ? params : [params]
        return items
          .map((item: any) => {
            const unit = item.seriesName.includes('丢包') ? '%' : 'ms'
            return `${item.marker}${item.seriesName}: ${Number(item.value[1]).toFixed(2)}${unit}`
          })
          .join('<br/>')
      },
    },
    legend: {
      top: 0,
      textStyle: { color: '#b8d7e8' },
    },
    grid: { left: 52, right: 54, top: 36, bottom: 34 },
    xAxis: {
      type: 'value',
      name: 's',
      nameTextStyle: { color: '#7fa7ba' },
      axisLabel: { color: '#7fa7ba' },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
    },
    yAxis: [
      {
        type: 'value',
        name: '时延 ms',
        nameTextStyle: { color: '#7fa7ba' },
        axisLabel: { color: '#7fa7ba' },
        splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
      },
      {
        type: 'value',
        name: '丢包 %',
        min: 0,
        max: 100,
        nameTextStyle: { color: '#7fa7ba' },
        axisLabel: { color: '#7fa7ba' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: `${linkLabel(key)} 时延`,
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2.6, color: '#5bd8ff' },
        data: props.history.map((snapshot) => [
          snapshot.elapsed_s,
          Number(snapshot.links[key]?.delay_ms ?? 0),
        ]),
      },
      {
        name: `${linkLabel(key)} 丢包`,
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2.4, color: '#ff8e8e' },
        data: props.history.map((snapshot) => [
          snapshot.elapsed_s,
          Number(snapshot.links[key]?.loss_rate ?? 0) * 100,
        ]),
      },
    ],
  }
}

function makeLineOption(config: {
  title: string
  xName?: string
  yName: string
  series: Array<{ name: string; color: string; data: number[][] }>
}): EChartsOption {
  return {
    tooltip: { trigger: 'axis', confine: true },
    grid: { left: 52, right: 22, top: 24, bottom: 34 },
    xAxis: {
      type: 'value',
      name: config.xName ?? 's',
      nameTextStyle: { color: '#7fa7ba' },
      axisLabel: { color: '#7fa7ba' },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
    },
    yAxis: {
      type: 'value',
      name: config.yName,
      nameTextStyle: { color: '#7fa7ba' },
      axisLabel: { color: '#7fa7ba' },
      splitLine: { lineStyle: { color: 'rgba(102, 214, 255, 0.1)' } },
    },
    series: config.series.map((series) => ({
      name: series.name,
      type: 'line',
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2.8, color: series.color },
      areaStyle: { color: `${series.color}18` },
      data: series.data,
    })),
  }
}

function nearestSnapshot(elapsed: number, mode: 'before' | 'after' | 'nearest') {
  if (props.history.length === 0) {
    return null
  }
  if (mode === 'before') {
    return [...props.history].reverse().find((snapshot) => snapshot.elapsed_s <= elapsed) ?? null
  }
  if (mode === 'after') {
    return props.history.find((snapshot) => snapshot.elapsed_s >= elapsed) ?? null
  }
  return props.history.reduce((best, snapshot) =>
    Math.abs(snapshot.elapsed_s - elapsed) < Math.abs(best.elapsed_s - elapsed) ? snapshot : best,
  )
}

function preferredScenario(scenarios: Record<string, ScenarioResult>, mode: TelemetrySnapshot['mode']) {
  if (mode === 'global_cooperative') {
    return scenarios.scenario1 ?? firstScenario(scenarios)
  }
  if (mode === 'autonomous') {
    return scenarios.scenario4 ?? scenarios.scenario3 ?? firstScenario(scenarios)
  }
  return scenarios.scenario2 ?? firstScenario(scenarios)
}

function firstScenario(scenarios: Record<string, ScenarioResult>) {
  return Object.values(scenarios)[0]
}

function nodeById(id: number) {
  return NODES.find((node) => node.id === id)
}

function linkLabel(key: string) {
  return key
    .split('-')
    .map((id) => nodeById(Number(id))?.key ?? id)
    .join(' ↔ ')
}

function linkScore(metric?: LinkMetric) {
  if (!metric) {
    return 0
  }
  return metric.delay_ms / DELAY_THRESHOLDS.clusterToAuto + metric.loss_rate / 0.48
}

function formatPower(value: number) {
  return `${value.toFixed(2)} MW`
}

function formatLoss(value?: number) {
  return `${((value ?? 0) * 100).toFixed(1)}%`
}

function formatDelay(value?: number) {
  return `${(value ?? 0).toFixed(1)} ms`
}
</script>

<template>
  <Teleport to="body">
    <div v-if="view" class="drilldown-backdrop">
      <section class="drilldown-panel" aria-modal="true" role="dialog">
        <header class="drilldown-header">
          <div>
            <div class="breadcrumb">
              <button type="button" @click="emit('close')">总览</button>
              <span>/</span>
              <strong>详情层</strong>
            </div>
            <h2>{{ title }}</h2>
          </div>
          <button class="drilldown-close" type="button" @click="emit('close')">返回总览</button>
        </header>

        <div v-if="activeNode" class="drilldown-body drilldown-body--node">
          <div class="drilldown-card drilldown-card--chart">
            <h3>{{ activeNode.name }} 独立趋势</h3>
            <VChart class="chart" :option="nodeTrendOption" autoresize />
          </div>
          <div class="drilldown-card drilldown-card--chart">
            <h3>{{ activeNode.key }} ADMM收敛轨迹</h3>
            <VChart class="chart" :option="admmTraceOption" autoresize />
          </div>
          <div class="drilldown-card">
            <h3>相关链路质量</h3>
            <table class="drilldown-table">
              <thead>
                <tr>
                  <th>链路</th>
                  <th>状态</th>
                  <th>时延</th>
                  <th>丢包率</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in relatedLinks" :key="item.key">
                  <td>{{ item.label }}</td>
                  <td :class="item.metric?.available ? 'state-good' : 'state-bad'">
                    {{ item.metric?.available ? '可用' : '受损' }}
                  </td>
                  <td>{{ formatDelay(item.metric?.delay_ms) }}</td>
                  <td>{{ formatLoss(item.metric?.loss_rate) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-else-if="activeLink" class="drilldown-body drilldown-body--link">
          <div class="drilldown-card drilldown-card--chart drilldown-card--wide">
            <h3>{{ linkLabel(activeLink) }} 历史时延 / 丢包</h3>
            <VChart class="chart" :option="linkHistoryOption" autoresize />
          </div>
          <div class="drilldown-card">
            <h3>当前链路状态</h3>
            <div class="metric-stack">
              <div>
                <span>真实测得时延</span>
                <strong>{{ formatDelay(linkDetailMetric?.delay_ms) }}</strong>
              </div>
              <div>
                <span>真实测得丢包率</span>
                <strong>{{ formatLoss(linkDetailMetric?.loss_rate) }}</strong>
              </div>
              <div>
                <span>链路判定</span>
                <strong :style="{ color: linkDetailMetric?.available ? '#29e6bb' : '#ff6b6b' }">
                  {{ linkDetailMetric?.available ? '可用于协同' : '通信受损' }}
                </strong>
              </div>
            </div>
          </div>
        </div>

        <div v-else-if="activeTransition" class="drilldown-body drilldown-body--transition">
          <div class="drilldown-card drilldown-card--wide">
            <h3>
              {{ MODE_LABELS[activeTransition.from] }} → {{ MODE_LABELS[activeTransition.to] }}
            </h3>
            <div class="transition-summary">
              <span :style="{ color: MODE_COLORS[activeTransition.to] }">
                {{ activeTransition.elapsed_s.toFixed(1) }}s
              </span>
              <span>{{ formatDelay(activeTransition.delay_ms) }}</span>
              <span>{{ formatLoss(activeTransition.loss_rate) }}</span>
              <span>{{ activeTransition.reason }}</span>
            </div>
            <table class="drilldown-table">
              <thead>
                <tr>
                  <th>节点</th>
                  <th>切换前</th>
                  <th>切换后</th>
                  <th>变化量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in transitionRows" :key="row.key">
                  <td>{{ row.name }}</td>
                  <td>{{ formatPower(row.before) }}</td>
                  <td>{{ formatPower(row.after) }}</td>
                  <td :class="Math.abs(row.delta) <= 2.6 ? 'state-good' : 'state-bad'">
                    {{ formatPower(row.delta) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="drilldown-card">
            <h3>触发链路</h3>
            <table class="drilldown-table">
              <thead>
                <tr>
                  <th>链路</th>
                  <th>时延</th>
                  <th>丢包</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in transitionLinks" :key="item.key">
                  <td>{{ item.label }}</td>
                  <td>{{ formatDelay(item.metric?.delay_ms) }}</td>
                  <td>{{ formatLoss(item.metric?.loss_rate) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>
