import { computed, onMounted, onUnmounted, ref } from 'vue'
import { LINK_KEYS, MODE_LABELS } from '../constants'
import type {
  ConnectionStatus,
  ControllerTraceEntry,
  LinkMap,
  ManualControlCommand,
  ManualControlPayload,
  ManualControlResponse,
  OperatingMode,
  ForecastPayload,
  NodeDispatchSource,
  SecurityPayload,
  TelemetryPayload,
  TelemetrySnapshot,
  TransitionRecord,
} from '../types'

const WS_URL = 'ws://127.0.0.1:8765'
const HISTORY_LIMIT = 150

export function useTelemetry() {
  const status = ref<ConnectionStatus>('connecting')
  const sourceLabel = ref('WebSocket 连接中')
  const current = ref<TelemetrySnapshot>(makeSyntheticSnapshot(0))
  const history = ref<TelemetrySnapshot[]>([])
  const transitions = ref<TransitionRecord[]>([])
  const fallbackFrames = ref<TelemetrySnapshot[]>([])
  const manualResponse = ref<ManualControlResponse | null>(null)

  let socket: WebSocket | null = null
  let fallbackTimer = 0
  let fallbackIndex = 0

  const totalCommand = computed(() =>
    current.value.command_mw.reduce((sum, value) => sum + value, 0),
  )

  const estimatedLoad = computed(() => {
    const note = current.value.note.match(/demand=([0-9.]+)/)
    if (note) {
      return Number(note[1])
    }
    return Math.max(42, totalCommand.value + 8 + Math.sin(current.value.elapsed_s / 12) * 5)
  })

  function start() {
    void loadFallbackFrames()
    connectWebSocket()
    fallbackTimer = window.setInterval(() => {
      if (status.value !== 'live') {
        status.value = 'fallback'
        sourceLabel.value = '离线演示数据'
        pushSnapshot(nextFallbackFrame())
      }
    }, 1000)
  }

  function stop() {
    if (socket) {
      socket.close()
      socket = null
    }
    window.clearInterval(fallbackTimer)
  }

  function connectWebSocket() {
    try {
      socket = new WebSocket(WS_URL)
    } catch {
      status.value = 'fallback'
      sourceLabel.value = '离线演示数据'
      return
    }

    socket.onopen = () => {
      status.value = 'live'
      sourceLabel.value = 'Python WebSocket 实时流'
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string) as
          | TelemetryPayload
          | ManualControlResponse
        if (isManualControlResponse(payload)) {
          manualResponse.value = payload
          if (payload.manual_control) {
            current.value = {
              ...current.value,
              manual_control: normalizeManualControl(payload.manual_control),
            }
          }
          return
        }
        pushSnapshot(normalizePayload(payload))
      } catch {
        status.value = 'fallback'
        sourceLabel.value = '实时数据解析失败，已切换演示数据'
      }
    }

    socket.onerror = () => {
      status.value = 'fallback'
      sourceLabel.value = 'WebSocket 未连接，使用演示数据'
    }

    socket.onclose = () => {
      if (status.value === 'live') {
        sourceLabel.value = '实时连接已断开，使用演示数据'
      }
      status.value = 'fallback'
    }
  }

  async function loadFallbackFrames() {
    try {
      const response = await fetch('/data/demo_telemetry.jsonl')
      const text = await response.text()
      const frames = text
        .split(/\r?\n/)
        .filter(Boolean)
        .map((line) => normalizeSnapshot(JSON.parse(line) as Partial<TelemetrySnapshot>))
      fallbackFrames.value = frames.length > 0 ? frames : buildSyntheticFrames()
    } catch {
      fallbackFrames.value = buildSyntheticFrames()
    }
  }

  function nextFallbackFrame() {
    const frames = fallbackFrames.value.length > 0 ? fallbackFrames.value : buildSyntheticFrames()
    const frame = frames[fallbackIndex % frames.length]
    fallbackIndex += 1
    return frame
  }

  function pushSnapshot(snapshot: TelemetrySnapshot) {
    const previous = history.value.at(-1)
    if (previous && previous.mode !== snapshot.mode) {
      transitions.value = [
        ...transitions.value,
        {
          elapsed_s: snapshot.elapsed_s,
          from: previous.mode,
          to: snapshot.mode,
          delay_ms: snapshot.average_delay_ms,
          loss_rate: snapshot.max_loss_rate,
          reason: inferReason(previous.mode, snapshot.mode),
          before_mw: [...previous.command_mw],
          after_mw: [...snapshot.command_mw],
        },
      ].slice(-12)
    }
    current.value = snapshot
    history.value = [...history.value, snapshot].slice(-HISTORY_LIMIT)
  }

  function sendManualControl(command: ManualControlCommand) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      manualResponse.value = {
        message_type: 'manual_control_response',
        ok: false,
        status: 'offline',
        message: 'WebSocket 未连接，手动操作未发送',
        manual_control: current.value.manual_control,
      }
      return
    }
    socket.send(JSON.stringify({ message_type: 'manual_control', ...command }))
  }

  onMounted(start)
  onUnmounted(stop)

  return {
    current,
    estimatedLoad,
    history,
    manualResponse,
    sourceLabel,
    status,
    sendManualControl,
    totalCommand,
    transitions,
  }
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

function isManualControlResponse(
  payload: TelemetryPayload | ManualControlResponse,
): payload is ManualControlResponse {
  return 'message_type' in payload && payload.message_type === 'manual_control_response'
}

function normalizePayload(payload: TelemetryPayload): TelemetrySnapshot {
  return normalizeSnapshot({
    ...payload,
    target_mw: payload.dispatch.target_mw,
    command_mw: payload.dispatch.command_mw,
    max_delta_mw: payload.dispatch.max_delta_mw,
    backend: payload.dispatch.backend,
    note: payload.dispatch.note,
    active_controllers: payload.dispatch.active_controllers,
    controller_trace: payload.dispatch.controller_trace,
    dispatch_sources: payload.dispatch.dispatch_sources,
  })
}

function normalizeSnapshot(raw: Partial<TelemetrySnapshot>): TelemetrySnapshot {
  const mode = (raw.mode ?? 'global_cooperative') as OperatingMode
  return {
    elapsed_s: Number(raw.elapsed_s ?? 0),
    mode,
    mode_label: raw.mode_label ?? MODE_LABELS[mode],
    average_delay_ms: Number(raw.average_delay_ms ?? 45),
    max_loss_rate: Number(raw.max_loss_rate ?? 0.02),
    real_network_measurement: Boolean(raw.real_network_measurement ?? false),
    links: normalizeLinks(raw.links),
    clusters: raw.clusters ?? [[1, 2, 3, 4, 5]],
    forecast: normalizeForecast(raw.forecast, raw),
    security: normalizeSecurity(raw.security, Number(raw.elapsed_s ?? 0)),
    manual_control: normalizeManualControl(raw.manual_control),
    target_mw: toFive(raw.target_mw),
    command_mw: toFive(raw.command_mw),
    max_delta_mw: Number(raw.max_delta_mw ?? 0),
    backend: raw.backend ?? 'local demo',
    note: raw.note ?? '',
    active_controllers: normalizeControllers(raw.active_controllers, mode),
    controller_trace: normalizeControllerTrace(raw.controller_trace, mode),
    dispatch_sources: normalizeDispatchSources(raw.dispatch_sources, mode),
  }
}

function normalizeManualControl(raw?: Partial<ManualControlPayload>): ManualControlPayload {
  return {
    select_timeout_s: Number(raw?.select_timeout_s ?? 30),
    pending: Array.isArray(raw?.pending)
      ? raw.pending.map((item) => ({
          request_id: String(item.request_id ?? ''),
          operation: String(item.operation ?? ''),
          target_key: String(item.target_key ?? ''),
          target: item.target ?? {},
          selected_at_epoch_ms: Number(item.selected_at_epoch_ms ?? 0),
          expires_at_epoch_ms: Number(item.expires_at_epoch_ms ?? 0),
        }))
      : [],
    active_interventions: Array.isArray(raw?.active_interventions)
      ? raw.active_interventions.map((item) => ({
          kind: String(item.kind ?? ''),
          target_key: String(item.target_key ?? ''),
          label: String(item.label ?? ''),
          started_at_elapsed_s: Number(item.started_at_elapsed_s ?? 0),
          expires_at_elapsed_s: Number(item.expires_at_elapsed_s ?? 0),
          metadata: item.metadata ?? {},
        }))
      : [],
    recent_events: Array.isArray(raw?.recent_events)
      ? raw.recent_events.map((event) => ({
          event_type: String(event.event_type ?? ''),
          operation: String(event.operation ?? ''),
          target_key: String(event.target_key ?? ''),
          reason: String(event.reason ?? ''),
          timestamp_ms: Number(event.timestamp_ms ?? 0),
        }))
      : [],
  }
}

function normalizeSecurity(raw?: Partial<SecurityPayload>, elapsed = 0): SecurityPayload {
  if (!raw) {
    return makeSyntheticSecurity(elapsed)
  }
  return {
    zero_trust_enabled: Boolean(raw.zero_trust_enabled ?? true),
    low_trust_threshold: Number(raw.low_trust_threshold ?? 60),
    audit_log_path: raw.audit_log_path ?? '',
    audit_jsonl_path: raw.audit_jsonl_path ?? '',
    nodes: Array.from({ length: 5 }, (_, index) => {
      const node = index + 1
      const source = raw.nodes?.find((item) => Number(item.node) === node)
      return {
        node,
        identity: String(source?.identity ?? `node-${node}`),
        authentication_status: String(source?.authentication_status ?? '正常'),
        trust_score: Number(source?.trust_score ?? 100),
        low_trust: Boolean(source?.low_trust ?? false),
        accepted_messages: Number(source?.accepted_messages ?? 0),
        auth_failures: Number(source?.auth_failures ?? 0),
        invalid_reports: Number(source?.invalid_reports ?? 0),
        jump_alerts: Number(source?.jump_alerts ?? 0),
        recent_alerts: Array.isArray(source?.recent_alerts)
          ? source.recent_alerts.map(String)
          : [],
      }
    }),
    recent_events: Array.isArray(raw.recent_events)
      ? raw.recent_events.map((event) => ({
          timestamp: String(event.timestamp ?? ''),
          event_type: String(event.event_type ?? ''),
          severity: String(event.severity ?? 'INFO'),
          node:
            event.node === null || event.node === undefined
              ? null
              : Number(event.node),
          reason: String(event.reason ?? ''),
          metadata: event.metadata ?? {},
        }))
      : [],
  }
}

function makeSyntheticSecurity(elapsed: number): SecurityPayload {
  const alertActive = elapsed > 70 && elapsed < 92
  return {
    zero_trust_enabled: true,
    low_trust_threshold: 60,
    audit_log_path: 'logs/security_audit/security_audit_demo.log',
    audit_jsonl_path: 'logs/security_audit/security_audit_demo.jsonl',
    nodes: Array.from({ length: 5 }, (_, index) => {
      const node = index + 1
      const isAlertNode = alertActive && node === 3
      return {
        node,
        identity: `node-${node}-${node <= 2 ? 'pv' : node <= 4 ? 'wind' : 'bess'}`,
        authentication_status: isAlertNode ? '异常' : '正常',
        trust_score: isAlertNode ? 56 : 98,
        low_trust: isAlertNode,
        accepted_messages: Math.max(0, Math.floor(elapsed / 2)),
        auth_failures: isAlertNode ? 2 : 0,
        invalid_reports: isAlertNode ? 1 : 0,
        jump_alerts: 0,
        recent_alerts: isAlertNode
          ? ['HMAC签名验证失败，消息可能被伪造或篡改', '节点信任评分低于阈值']
          : [],
      }
    }),
    recent_events: alertActive
      ? [
          {
            timestamp: 'demo',
            event_type: 'AUTHENTICATION_FAILED',
            severity: 'HIGH',
            node: 3,
            reason: '离线演示：伪造身份消息被拒绝',
            metadata: {},
          },
        ]
      : [],
  }
}

function normalizeControllers(raw: string[] | undefined, mode: OperatingMode) {
  if (Array.isArray(raw) && raw.length > 0) {
    return raw.map(String)
  }
  return [baseControllerName(mode)]
}

function normalizeControllerTrace(
  raw: ControllerTraceEntry[] | undefined,
  mode: OperatingMode,
): ControllerTraceEntry[] {
  if (Array.isArray(raw) && raw.length > 0) {
    return raw.map((entry) => ({
      controller: String(entry.controller ?? baseControllerName(mode)),
      controller_key: String(entry.controller_key ?? baseControllerKey(mode)),
      priority: Number(entry.priority ?? 10),
      action: String(entry.action ?? 'set'),
      reason: String(entry.reason ?? 'legacy telemetry'),
      nodes: Array.isArray(entry.nodes) ? entry.nodes.map(Number) : [1, 2, 3, 4, 5],
    }))
  }
  return [
    {
      controller: baseControllerName(mode),
      controller_key: baseControllerKey(mode),
      priority: 10,
      action: 'set',
      reason: 'offline or legacy telemetry fallback',
      nodes: [1, 2, 3, 4, 5],
    },
  ]
}

function normalizeDispatchSources(
  raw: NodeDispatchSource[] | undefined,
  mode: OperatingMode,
): NodeDispatchSource[] {
  if (Array.isArray(raw) && raw.length > 0) {
    return Array.from({ length: 5 }, (_, index) => {
      const source = raw.find((item) => Number(item.node) === index + 1) ?? raw[index]
      return normalizeDispatchSource(source, index + 1, mode)
    })
  }
  return Array.from({ length: 5 }, (_, index) =>
    normalizeDispatchSource(undefined, index + 1, mode),
  )
}

function normalizeDispatchSource(
  raw: Partial<NodeDispatchSource> | undefined,
  node: number,
  mode: OperatingMode,
): NodeDispatchSource {
  return {
    node,
    controller: String(raw?.controller ?? baseControllerName(mode)),
    controller_key: String(raw?.controller_key ?? baseControllerKey(mode)),
    priority: Number(raw?.priority ?? 10),
    reason: String(raw?.reason ?? 'legacy telemetry fallback'),
    overridden: Boolean(raw?.overridden ?? false),
    previous_controller: raw?.previous_controller ?? null,
    previous_value_mw:
      raw?.previous_value_mw === null || raw?.previous_value_mw === undefined
        ? null
        : Number(raw.previous_value_mw),
    override_reason: raw?.override_reason ?? null,
  }
}

function baseControllerName(mode: OperatingMode) {
  if (mode === 'global_cooperative') {
    return '经济调度控制器'
  }
  if (mode === 'local_cluster') {
    return '局部聚类协调控制器'
  }
  return '应急保守控制器'
}

function baseControllerKey(mode: OperatingMode) {
  if (mode === 'global_cooperative') {
    return 'economic_dispatch'
  }
  if (mode === 'local_cluster') {
    return 'local_cluster_coordination'
  }
  return 'emergency_conservative'
}

function normalizeLinks(raw?: LinkMap): LinkMap {
  const links: LinkMap = {}
  LINK_KEYS.forEach((key, index) => {
    const baseDelay = 42 + index * 4
    const item = raw?.[key]
    links[key] = {
      delay_ms: Number(item?.delay_ms ?? baseDelay),
      loss_rate: Number(item?.loss_rate ?? 0.012 + index * 0.002),
      available: Boolean(item?.available ?? true),
      configured_delay_ms:
        item?.configured_delay_ms === null || item?.configured_delay_ms === undefined
          ? null
          : Number(item.configured_delay_ms),
      configured_loss_rate:
        item?.configured_loss_rate === null || item?.configured_loss_rate === undefined
          ? null
          : Number(item.configured_loss_rate),
      measured_rtt_ms:
        item?.measured_rtt_ms === null || item?.measured_rtt_ms === undefined
          ? null
          : Number(item.measured_rtt_ms),
    }
  })
  return links
}

function normalizeForecast(
  raw?: Partial<ForecastPayload>,
  source?: Partial<TelemetrySnapshot>,
): ForecastPayload {
  if (!raw) {
    const elapsed = Number(source?.elapsed_s ?? 0)
    const actual = toFour(source?.target_mw ?? source?.command_mw)
    const forecast = actual.map((value, index) =>
      Math.max(0, value + Math.sin(elapsed / 8 + index) * (index < 2 ? 1.2 : 2.4)),
    )
    return {
      method: 'persistence_trend_ar1_error',
      horizon_minutes: 15,
      horizon_steps: 1,
      dispatch_uses_forecast: true,
      actual_mw: actual,
      forecast_mw: forecast,
      verified_forecast_mw: forecast,
      rmse_mw: 2.4,
      mape_percent: 12.6,
      per_node_rmse_mw: [1.2, 1.0, 2.9, 2.5],
      per_node_mape_percent: [10.4, 11.2, 14.3, 13.8],
      sample_count: Math.max(0, Math.floor(elapsed)) * 4,
      history_path: 'logs/forecast_accuracy/renewable_forecast_accuracy_demo.csv',
    }
  }
  return {
    method: raw?.method ?? 'persistence_trend_ar1_error',
    horizon_minutes: Number(raw?.horizon_minutes ?? 15),
    horizon_steps: Number(raw?.horizon_steps ?? 5),
    dispatch_uses_forecast: Boolean(raw?.dispatch_uses_forecast ?? true),
    actual_mw: toFour(raw?.actual_mw),
    forecast_mw: toFour(raw?.forecast_mw),
    verified_forecast_mw: raw?.verified_forecast_mw ? toFour(raw.verified_forecast_mw) : null,
    rmse_mw: Number(raw?.rmse_mw ?? 0),
    mape_percent: Number(raw?.mape_percent ?? 0),
    per_node_rmse_mw: toFour(raw?.per_node_rmse_mw),
    per_node_mape_percent: toFour(raw?.per_node_mape_percent),
    sample_count: Number(raw?.sample_count ?? 0),
    history_path: raw?.history_path ?? '',
  }
}

function toFive(values?: number[]) {
  const safeValues = Array.isArray(values) ? values : []
  return Array.from({ length: 5 }, (_, index) => Number(safeValues[index] ?? 0))
}

function toFour(values?: number[] | null) {
  const safeValues = Array.isArray(values) ? values : []
  return Array.from({ length: 4 }, (_, index) => Number(safeValues[index] ?? 0))
}

function buildSyntheticFrames() {
  return Array.from({ length: 121 }, (_, index) => makeSyntheticSnapshot(index))
}

function makeSyntheticSnapshot(elapsed: number): TelemetrySnapshot {
  const severity = syntheticSeverity(elapsed)
  const mode: OperatingMode =
    severity > 0.82 ? 'autonomous' : severity > 0.28 ? 'local_cluster' : 'global_cooperative'
  const delay = 42 + severity * 370
  const loss = 0.018 + severity * 0.48
  const links: LinkMap = {}

  LINK_KEYS.forEach((key, index) => {
    const wave = Math.sin(elapsed / 8 + index * 0.7) * 0.04
    const linkLoss = Math.max(0, Math.min(0.95, loss + wave))
    links[key] = {
      delay_ms: Math.max(25, delay + Math.sin(elapsed / 7 + index) * 18 + index * 3),
      loss_rate: linkLoss,
      available: linkLoss < 0.35,
    }
  })

  const solar = Math.max(0, Math.sin((elapsed / 120) * Math.PI) * 16)
  const wind = 13 + Math.sin(elapsed / 9) * 5 + severity * 3
  const bess = mode === 'autonomous' ? Math.max(0, 10 - (elapsed - 53) * 0.24) : 3 - severity * 5
  const actualRenewable = [solar, solar * 0.78, wind, wind * 0.82]
  const forecastRenewable = actualRenewable.map((value, index) =>
    Math.max(0, value + Math.sin(elapsed / 9 + index) * (index < 2 ? 1.4 : 2.2)),
  )

  return {
    elapsed_s: elapsed,
    mode,
    mode_label: MODE_LABELS[mode],
    average_delay_ms: delay,
    max_loss_rate: loss,
    real_network_measurement: false,
    links,
    clusters: mode === 'autonomous' ? [[1], [2], [3], [4], [5]] : [[1, 2, 3, 4, 5]],
    forecast: {
      method: 'persistence_trend_ar1_error',
      horizon_minutes: 15,
      horizon_steps: 5,
      dispatch_uses_forecast: true,
      actual_mw: actualRenewable,
      forecast_mw: forecastRenewable,
      verified_forecast_mw: forecastRenewable,
      rmse_mw: 2.4,
      mape_percent: 11.8,
      per_node_rmse_mw: [1.5, 1.2, 2.9, 2.6],
      per_node_mape_percent: [10.2, 11.1, 13.4, 12.6],
      sample_count: Math.max(0, elapsed - 5) * 4,
      history_path: 'logs/forecast_accuracy/renewable_forecast_accuracy.csv',
    },
    security: makeSyntheticSecurity(elapsed),
    manual_control: normalizeManualControl(),
    target_mw: [solar, solar * 0.78, wind, wind * 0.82, bess],
    command_mw: [solar, solar * 0.78, wind, wind * 0.82, bess],
    max_delta_mw: 2.5,
    backend: 'offline demo',
    note: `demand=${(58 + Math.sin(elapsed / 11) * 8).toFixed(2)}MW`,
    active_controllers:
      elapsed > 34 && elapsed < 58
        ? [baseControllerName(mode), '储能优先充电控制器']
        : [baseControllerName(mode)],
    controller_trace: [
      {
        controller: baseControllerName(mode),
        controller_key: baseControllerKey(mode),
        priority: 10,
        action: 'set',
        reason: 'offline demo base controller',
        nodes: [1, 2, 3, 4, 5],
      },
      ...(elapsed > 34 && elapsed < 58
        ? [
            {
              controller: '储能优先充电控制器',
              controller_key: 'storage_priority_charge',
              priority: 90,
              action: 'override',
              reason: 'offline demo renewable surplus charges BESS',
              nodes: [5],
            },
          ]
        : []),
    ],
    dispatch_sources: Array.from({ length: 5 }, (_, index) => ({
      node: index + 1,
      controller:
        index === 4 && elapsed > 34 && elapsed < 58
          ? '储能优先充电控制器'
          : baseControllerName(mode),
      controller_key:
        index === 4 && elapsed > 34 && elapsed < 58
          ? 'storage_priority_charge'
          : baseControllerKey(mode),
      priority: index === 4 && elapsed > 34 && elapsed < 58 ? 90 : 10,
      reason:
        index === 4 && elapsed > 34 && elapsed < 58
          ? '供大于求且SOC低于目标，覆盖BESS为充电'
          : 'offline demo base controller',
      overridden: index === 4 && elapsed > 34 && elapsed < 58,
      previous_controller:
        index === 4 && elapsed > 34 && elapsed < 58 ? baseControllerName(mode) : null,
      previous_value_mw: index === 4 && elapsed > 34 && elapsed < 58 ? bess : null,
      override_reason:
        index === 4 && elapsed > 34 && elapsed < 58
          ? '储能优先充电控制器覆盖基础调度'
          : null,
    })),
  }
}

function syntheticSeverity(elapsed: number) {
  if (elapsed < 25) {
    return (elapsed / 25) * 0.22
  }
  if (elapsed < 52) {
    return 0.22 + ((elapsed - 25) / 27) * 0.66
  }
  if (elapsed < 88) {
    return 0.92
  }
  if (elapsed < 112) {
    return 0.92 - ((elapsed - 88) / 24) * 0.72
  }
  return 0.2 - Math.min(0.18, ((elapsed - 112) / 8) * 0.18)
}
