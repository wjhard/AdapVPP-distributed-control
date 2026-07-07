<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AlgorithmBoard from './components/AlgorithmBoard.vue'
import CommunicationQualityChart from './components/CommunicationQualityChart.vue'
import DashboardPanel from './components/DashboardPanel.vue'
import DrilldownPanel from './components/DrilldownPanel.vue'
import EfficiencyGauge from './components/EfficiencyGauge.vue'
import PowerTrendChart from './components/PowerTrendChart.vue'
import TimelinePanel from './components/TimelinePanel.vue'
import TopStatusBar from './components/TopStatusBar.vue'
import TopologyMap from './components/TopologyMap.vue'
import { useTelemetry } from './composables/useTelemetry'
import { useVerificationData } from './composables/useVerificationData'
import { NODES } from './constants'
import type { DrilldownView, TransitionRecord } from './types'

const BASE_WIDTH = 1920
const BASE_HEIGHT = 1080

const telemetry = useTelemetry()
const verification = useVerificationData()
const viewportScale = ref(1)
const drilldown = ref<DrilldownView | null>(null)

const screenStyle = computed(() => ({
  transform: `scale(${viewportScale.value})`,
}))

const viewportStyle = computed(() => ({
  width: `${BASE_WIDTH * viewportScale.value}px`,
  height: `${BASE_HEIGHT * viewportScale.value}px`,
}))

const robustCommSaving = computed(() => {
  const rows = verification.data.value.monteCarlo.filter((row) =>
    row.Method.toLowerCase().includes('et-admm'),
  )
  if (rows.length === 0) {
    return 94.0
  }
  return rows.reduce((sum, row) => sum + Number(row.CommSavingMean || 0), 0) / rows.length
})

const activeLinks = computed(
  () => Object.values(telemetry.current.value.links).filter((link) => link.available).length,
)

function updateScale() {
  viewportScale.value = Math.min(window.innerWidth / BASE_WIDTH, window.innerHeight / BASE_HEIGHT)
}

function openNodeDrilldown(nodeId: number) {
  drilldown.value = { type: 'node', nodeId }
}

function openLinkDrilldown(linkKey: string) {
  drilldown.value = { type: 'link', linkKey }
}

function openTransitionDrilldown(record: TransitionRecord) {
  drilldown.value = { type: 'transition', record }
}

function closeDrilldown() {
  drilldown.value = null
}

onMounted(() => {
  updateScale()
  window.addEventListener('resize', updateScale)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateScale)
})
</script>

<template>
  <main class="dashboard-shell">
    <div class="dashboard-viewport" :style="viewportStyle">
      <div class="dashboard-screen" :style="screenStyle">
        <TopStatusBar
          :average-delay="telemetry.current.value.average_delay_ms"
          :backend="telemetry.current.value.backend"
          :loss-rate="telemetry.current.value.max_loss_rate"
          :mode="telemetry.current.value.mode"
          :source="telemetry.sourceLabel.value"
          :status="telemetry.status.value"
          :total-power="telemetry.totalCommand.value"
        />

        <DashboardPanel class="panel-power" title="实时功率分配" accent="#ffd166">
          <template #meta>
            <span class="panel-meta">负荷 {{ telemetry.estimatedLoad.value.toFixed(1) }} MW</span>
          </template>
          <PowerTrendChart
            :estimated-load="telemetry.estimatedLoad.value"
            :history="telemetry.history.value"
            :mode="telemetry.current.value.mode"
          />
        </DashboardPanel>

        <DashboardPanel class="panel-topology" title="五节点通信拓扑" accent="#29e6bb">
          <template #meta>
            <span class="panel-meta">{{ activeLinks }}/10 链路可用</span>
          </template>
          <TopologyMap
            :snapshot="telemetry.current.value"
            @link-selected="openLinkDrilldown"
            @node-selected="openNodeDrilldown"
          />
          <div class="node-strip">
            <button
              v-for="(node, index) in NODES"
              :key="node.id"
              class="node-strip__item"
              type="button"
              @click="openNodeDrilldown(node.id)"
            >
              <span>{{ node.key }}</span>
              <strong>{{ telemetry.current.value.command_mw[index].toFixed(2) }} MW</strong>
            </button>
          </div>
        </DashboardPanel>

        <DashboardPanel class="panel-comm" title="通信质量监测" accent="#5bd8ff">
          <CommunicationQualityChart :history="telemetry.history.value" />
        </DashboardPanel>

        <DashboardPanel class="panel-timeline" title="状态切换时间轴" accent="#f5c84c">
          <template #meta>
            <span class="evidence-tag evidence-tag--live">实时事件日志</span>
          </template>
          <TimelinePanel
            :live-transitions="telemetry.transitions.value"
            :static-transitions="verification.data.value.transitions"
            @transition-selected="openTransitionDrilldown"
          />
        </DashboardPanel>

        <DashboardPanel class="panel-efficiency" title="通信效率指标" accent="#a4ff7a">
          <template #meta>
            <span class="evidence-tag evidence-tag--mixed">历史统计 / 实时</span>
          </template>
          <EfficiencyGauge
            :live-delta="telemetry.current.value.max_delta_mw"
            :saving-rate="robustCommSaving"
          />
        </DashboardPanel>

        <DashboardPanel class="panel-algo" title="算法效果对比看板" accent="#ff8e8e">
          <template #meta>
            <span class="panel-meta panel-meta--group">
              <span class="evidence-tag evidence-tag--offline">离线验证证据</span>
              <span>MATLAB 验证数据 {{ verification.ready.value ? '已加载' : '加载中' }}</span>
            </span>
          </template>
          <AlgorithmBoard
            :cost-gap="verification.data.value.costGap"
            :monte-carlo="verification.data.value.monteCarlo"
            :optimality-gap="verification.data.value.optimalityGap"
            :scenarios="verification.data.value.scenarios"
          />
        </DashboardPanel>

        <DrilldownPanel
          :current="telemetry.current.value"
          :history="telemetry.history.value"
          :scenarios="verification.data.value.scenarios"
          :view="drilldown"
          @close="closeDrilldown"
        />
      </div>
    </div>
  </main>
</template>
