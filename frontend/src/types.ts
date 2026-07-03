export type OperatingMode = 'global_cooperative' | 'local_cluster' | 'autonomous'

export type LinkMetric = {
  delay_ms: number
  loss_rate: number
  available: boolean
}

export type LinkMap = Record<string, LinkMetric>

export type DispatchPayload = {
  target_mw: number[]
  command_mw: number[]
  max_delta_mw: number
  backend: string
  note: string
}

export type TelemetryPayload = {
  elapsed_s: number
  mode: OperatingMode
  mode_label: string
  average_delay_ms: number
  max_loss_rate: number
  links: LinkMap
  clusters: number[][]
  dispatch: DispatchPayload
}

export type TelemetrySnapshot = {
  elapsed_s: number
  mode: OperatingMode
  mode_label: string
  average_delay_ms: number
  max_loss_rate: number
  links: LinkMap
  clusters: number[][]
  target_mw: number[]
  command_mw: number[]
  max_delta_mw: number
  backend: string
  note: string
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

export type StaticVerificationData = {
  scenarios: Record<string, ScenarioResult>
  monteCarlo: MonteCarloRow[]
  costGap: CostGapRow[]
  transitions: TransitionRecord[]
}

export type ConnectionStatus = 'connecting' | 'live' | 'fallback'
