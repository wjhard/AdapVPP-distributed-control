import Papa from 'papaparse'
import { onMounted, ref } from 'vue'
import type {
  CostGapRow,
  MonteCarloRow,
  OperatingMode,
  OptimalityGapRow,
  ScenarioResult,
  StaticVerificationData,
  TransitionRecord,
} from '../types'

const EMPTY_DATA: StaticVerificationData = {
  scenarios: {},
  monteCarlo: [],
  costGap: [],
  optimalityGap: [],
  transitions: [],
}

export function useVerificationData() {
  const data = ref<StaticVerificationData>(EMPTY_DATA)
  const ready = ref(false)

  async function load() {
    const [scenarios, monteCarlo, costGap, optimalityGap, demoLog] = await Promise.all([
      fetchJson<Record<string, ScenarioResult>>('/data/scenario_results.json', {}),
      fetchCsv<MonteCarloRow>('/data/monte_carlo_summary.csv'),
      fetchCsv<CostGapRow>('/data/cost_gap_analysis.csv'),
      fetchCsv<OptimalityGapRow>('/data/optimality_gap_trace.csv'),
      fetchText('/data/demo_run_log.txt'),
    ])

    data.value = {
      scenarios,
      monteCarlo,
      costGap,
      optimalityGap,
      transitions: parseTransitions(demoLog),
    }
    ready.value = true
  }

  onMounted(() => {
    void load()
  })

  return { data, ready }
}

async function fetchJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(url)
    return (await response.json()) as T
  } catch {
    return fallback
  }
}

async function fetchText(url: string): Promise<string> {
  try {
    const response = await fetch(url)
    return await response.text()
  } catch {
    return ''
  }
}

async function fetchCsv<T>(url: string): Promise<T[]> {
  const text = await fetchText(url)
  const parsed = Papa.parse<T>(text, {
    header: true,
    skipEmptyLines: true,
  })
  return parsed.data
}

function parseTransitions(text: string): TransitionRecord[] {
  const rawTransitions = parseRawTransitionLines(text)
  if (rawTransitions.length > 0) {
    return rawTransitions
  }

  const modeMap: Record<string, OperatingMode> = {
    global_cooperative: 'global_cooperative',
    local_cluster: 'local_cluster',
    autonomous: 'autonomous',
  }

  return text
    .split(/\r?\n/)
    .map((line): TransitionRecord | null => {
      const match = line.match(
        /^\s*([0-9.]+)\s+\|\s+([a-z_]+)\s+->\s+([a-z_]+)\s+\|\s+([0-9.]+)\s+\|\s+([0-9.]+)/,
      )
      if (!match) {
        return null
      }
      const [, elapsed, from, to, delay, loss] = match
      return {
        elapsed_s: Number(elapsed),
        from: modeMap[from],
        to: modeMap[to],
        delay_ms: Number(delay),
        loss_rate: Number(loss),
        reason: inferReason(modeMap[from], modeMap[to]),
      }
    })
    .filter(isTransitionRecord)
}

function parseRawTransitionLines(text: string): TransitionRecord[] {
  const modeMap: Record<string, OperatingMode> = {
    GLOBAL: 'global_cooperative',
    CLUSTER: 'local_cluster',
    AUTONOMOUS: 'autonomous',
  }

  return text
    .split(/\r?\n/)
    .map((line): TransitionRecord | null => {
      const match = line.match(
        /TRANSITION t=([0-9.]+)s ([A-Z]+)->([A-Z]+) avg_delay=([0-9.]+)ms max_loss=([0-9.]+) reason=([^ ]+)/,
      )
      if (!match) {
        return null
      }
      const [, elapsed, from, to, delay, loss, reason] = match
      const beforeRaw = line.match(/before=\[([^\]]*)\]/)?.[1]
      const afterRaw = line.match(/after=\[([^\]]*)\]/)?.[1]

      return {
        elapsed_s: Number(elapsed),
        from: modeMap[from],
        to: modeMap[to],
        delay_ms: Number(delay),
        loss_rate: Number(loss),
        reason: reasonLabel(reason),
        before_mw: parseVector(beforeRaw),
        after_mw: parseVector(afterRaw),
      }
    })
    .filter(isTransitionRecord)
}

function parseVector(raw?: string) {
  if (!raw) {
    return undefined
  }
  return raw
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isFinite(value))
}

function isTransitionRecord(item: TransitionRecord | null): item is TransitionRecord {
  return item !== null
}

function inferReason(from: OperatingMode, to: OperatingMode) {
  if (from === 'global_cooperative' && to === 'local_cluster') {
    return '通信降级，进入局部协同'
  }
  if (from === 'local_cluster' && to === 'autonomous') {
    return '严重弱通信，切换自治'
  }
  if (from === 'autonomous' && to === 'local_cluster') {
    return '链路恢复，重建聚类'
  }
  if (from === 'local_cluster' && to === 'global_cooperative') {
    return '质量恢复，回到全局'
  }
  return '状态滞回切换'
}

function reasonLabel(reason: string) {
  const labels: Record<string, string> = {
    degraded_to_cluster: '通信降级，进入局部协同',
    severe_to_autonomous: '严重弱通信，切换自治',
    partial_recovery_to_cluster: '链路恢复，重建聚类',
    recovered_to_global: '质量恢复，回到全局',
  }
  return labels[reason] ?? reason
}
