import type { NodeInfo, OperatingMode } from './types'

export const NODES: NodeInfo[] = [
  { id: 1, key: 'PV1', name: 'PV1 光伏', kind: 'pv', capacity: 50, x: 245, y: 96 },
  { id: 2, key: 'PV2', name: 'PV2 光伏', kind: 'pv', capacity: 40, x: 576, y: 126 },
  { id: 3, key: 'Wind3', name: 'Wind3 风电', kind: 'wind', capacity: 60, x: 642, y: 330 },
  { id: 4, key: 'Wind4', name: 'Wind4 风电', kind: 'wind', capacity: 55, x: 320, y: 386 },
  { id: 5, key: 'BESS5', name: 'BESS5 储能', kind: 'bess', capacity: 30, x: 438, y: 242 },
]

export const MODE_LABELS: Record<OperatingMode, string> = {
  global_cooperative: '全局协同',
  local_cluster: '局部聚类',
  autonomous: '完全自治',
}

export const MODE_CLASS: Record<OperatingMode, string> = {
  global_cooperative: 'mode-global',
  local_cluster: 'mode-cluster',
  autonomous: 'mode-auto',
}

export const MODE_COLORS: Record<OperatingMode, string> = {
  global_cooperative: '#23d7a7',
  local_cluster: '#f5c84c',
  autonomous: '#ff6b6b',
}

export const NODE_COLORS: Record<NodeInfo['kind'], string> = {
  pv: '#ffd166',
  wind: '#5bd8ff',
  bess: '#a4ff7a',
}

export const LINK_KEYS = [
  '1-2',
  '1-3',
  '1-4',
  '1-5',
  '2-3',
  '2-4',
  '2-5',
  '3-4',
  '3-5',
  '4-5',
]

export const DELAY_THRESHOLDS = {
  globalToCluster: 120,
  clusterToAuto: 340,
  autoToCluster: 260,
  clusterToGlobal: 90,
}

export const LOSS_THRESHOLDS = {
  globalToCluster: 0.15,
  clusterToAuto: 0.48,
  autoToCluster: 0.35,
  clusterToGlobal: 0.08,
}
