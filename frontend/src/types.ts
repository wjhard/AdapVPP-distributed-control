export type OperatingMode = 'global_cooperative' | 'local_cluster' | 'autonomous'

export type LinkMetric = {
  delay_ms: number
  loss_rate: number
  available: boolean
  configured_delay_ms?: number | null
  configured_loss_rate?: number | null
  measured_rtt_ms?: number | null
}

export type LinkMap = Record<string, LinkMetric>

export type DispatchPayload = {
  target_mw: number[]
  command_mw: number[]
  max_delta_mw: number
  backend: string
  note: string
  active_controllers?: string[]
  controller_trace?: ControllerTraceEntry[]
  dispatch_sources?: NodeDispatchSource[]
}

export type ControllerTraceEntry = {
  controller: string
  controller_key: string
  priority: number
  action: string
  reason: string
  nodes: number[]
}

export type NodeDispatchSource = {
  node: number
  controller: string
  controller_key: string
  priority: number
  reason: string
  overridden: boolean
  previous_controller?: string | null
  previous_value_mw?: number | null
  override_reason?: string | null
}

export type ForecastPayload = {
  method: string
  horizon_minutes: number
  horizon_steps: number
  dispatch_uses_forecast: boolean
  actual_mw: number[]
  forecast_mw: number[]
  verified_forecast_mw?: number[] | null
  rmse_mw: number
  mape_percent: number
  per_node_rmse_mw: number[]
  per_node_mape_percent: number[]
  sample_count: number
  history_path: string
}

export type TelemetryPayload = {
  elapsed_s: number
  mode: OperatingMode
  mode_label: string
  average_delay_ms: number
  max_loss_rate: number
  real_network_measurement?: boolean
  links: LinkMap
  clusters: number[][]
  forecast?: ForecastPayload
  dispatch: DispatchPayload
}

export type TelemetrySnapshot = {
  elapsed_s: number
  mode: OperatingMode
  mode_label: string
  average_delay_ms: number
  max_loss_rate: number
  real_network_measurement: boolean
  links: LinkMap
  clusters: number[][]
  forecast: ForecastPayload
  target_mw: number[]
  command_mw: number[]
  max_delta_mw: number
  backend: string
  note: string
  active_controllers: string[]
  controller_trace: ControllerTraceEntry[]
  dispatch_sources: NodeDispatchSource[]
}

export type NodeInfo = {
  id: number
  key: string
  name: string
  kind: 'pv' | 'wind' | 'bess'
  capacity: number
  x: number
  y: number
}

export type TransitionRecord = {
  elapsed_s: number
  from: OperatingMode
  to: OperatingMode
  delay_ms: number
  loss_rate: number
  reason?: string
  before_mw?: number[]
  after_mw?: number[]
}

export type ScenarioResult = {
  name: string
  method: string
  conv: number[]
  iter: number
  comm: number
  comm_saving: number
  diverged: boolean
  total_cost: number
  power_balance_error: number
  P: number[]
}

export type MonteCarloRow = {
  Condition: string
  Method: string
  IterationMean: string
  IterationStd: string
  CommSavingMean: string
  CommSavingStd: string
  DivergedCases: string
  ConvergenceSuccessRate: string
}

export type CostGapRow = {
  Condition: string
  ETCost: string
  StandardCost: string
  HourlyCostGap: string
  AnnualizedLoss: string
  PercentGap: string
}

export type OptimalityGapRow = {
  Scenario: string
  Iteration: string
  DistanceToPStarMW: string
  OptimalityGap: string
  OptimalityGapForLog: string
}

export type StaticVerificationData = {
  scenarios: Record<string, ScenarioResult>
  monteCarlo: MonteCarloRow[]
  costGap: CostGapRow[]
  optimalityGap: OptimalityGapRow[]
  transitions: TransitionRecord[]
}

export type DrilldownView =
  | { type: 'node'; nodeId: number }
  | { type: 'link'; linkKey: string }
  | { type: 'transition'; record: TransitionRecord }

export type ConnectionStatus = 'connecting' | 'live' | 'fallback'
