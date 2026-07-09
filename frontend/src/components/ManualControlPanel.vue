<script setup lang="ts">
import { AlertTriangle, BatteryCharging, RadioTower, ShieldAlert } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { LINK_KEYS, MODE_LABELS, NODES } from '../constants'
import type {
  ConnectionStatus,
  ManualControlCommand,
  ManualControlPayload,
  ManualControlResponse,
  ManualPendingOperation,
  OperatingMode,
} from '../types'

const props = defineProps<{
  elapsed: number
  manualControl: ManualControlPayload
  response: ManualControlResponse | null
  status: ConnectionStatus
}>()

const emit = defineEmits<{
  (event: 'manual-command', command: ManualControlCommand): void
}>()

const linkKey = ref(LINK_KEYS[0])
const linkDuration = ref(20)
const storageDuration = ref(15)
const securityNode = ref(3)
const securityKind = ref<'forged' | 'anomalous' | 'control'>('forged')
const forcedMode = ref<OperatingMode>('autonomous')
const forcedModeDuration = ref(30)
const nowMs = ref(Date.now())

let timer = 0

const pending = computed(() => props.manualControl.pending)
const activeInterventions = computed(() => props.manualControl.active_interventions)

function selectLinkFault() {
  emit('manual-command', {
    action: 'select',
    operation: 'link_fault',
    target: {
      link_key: linkKey.value,
      duration_s: Number(linkDuration.value),
    },
  })
}

function selectStorageCharge() {
  emit('manual-command', {
    action: 'select',
    operation: 'storage_charge_test',
    target: {
      duration_s: Number(storageDuration.value),
    },
  })
}

function selectSecurityIncident() {
  emit('manual-command', {
    action: 'select',
    operation: 'security_incident',
    target: {
      node: Number(securityNode.value),
      kind: securityKind.value,
    },
  })
}

function selectForceMode() {
  emit('manual-command', {
    action: 'select',
    operation: 'force_mode',
    target: {
      mode: forcedMode.value,
      duration_s: Number(forcedModeDuration.value),
    },
  })
}

function operate(item: ManualPendingOperation) {
  emit('manual-command', { action: 'operate', request_id: item.request_id })
}

function cancel(item: ManualPendingOperation) {
  emit('manual-command', { action: 'cancel', request_id: item.request_id })
}

function remainingText(item: ManualPendingOperation) {
  return `${Math.ceil(Math.max(0, item.expires_at_epoch_ms - nowMs.value) / 1000)}s`
}

function activeRemaining(expiresAtElapsed: number) {
  return `${Math.max(0, expiresAtElapsed - props.elapsed).toFixed(0)}s`
}

function operationLabel(item: ManualPendingOperation) {
  if (item.operation === 'link_fault') {
    return `注入链路 ${item.target.link_key ?? ''} 故障`
  }
  if (item.operation === 'storage_charge_test') {
    return '触发储能优先充电测试'
  }
  if (item.operation === 'security_incident') {
    return `模拟 Node${item.target.node ?? ''} 安全事件`
  }
  if (item.operation === 'force_mode') {
    return `强制切换到 ${MODE_LABELS[item.target.mode as OperatingMode] ?? item.target.mode}`
  }
  return item.operation
}

function responseClass() {
  if (!props.response) {
    return 'manual-response'
  }
  return props.response.ok ? 'manual-response manual-response--ok' : 'manual-response manual-response--bad'
}

onMounted(() => {
  timer = window.setInterval(() => {
    nowMs.value = Date.now()
  }, 500)
})

onUnmounted(() => {
  window.clearInterval(timer)
})
</script>

<template>
  <div class="manual-console">
    <div class="manual-console__banner">
      <span :class="['manual-console__dot', { 'manual-console__dot--live': status === 'live' }]"></span>
      <strong>IEC 61850 Select-Cancel-Operate</strong>
      <em>运行时人工干预，30s确认窗口</em>
    </div>

    <div class="manual-console__grid">
      <section class="manual-card">
        <div class="manual-card__title">
          <RadioTower :size="16" />
          <span>注入链路故障</span>
        </div>
        <div class="manual-card__controls">
          <select v-model="linkKey" aria-label="选择链路">
            <option v-for="key in LINK_KEYS" :key="key" :value="key">{{ key }}</option>
          </select>
          <input v-model.number="linkDuration" min="3" max="120" step="1" type="number" aria-label="故障时长" />
          <button type="button" @click="selectLinkFault">选定</button>
        </div>
      </section>

      <section class="manual-card">
        <div class="manual-card__title">
          <BatteryCharging :size="16" />
          <span>储能优先充电</span>
        </div>
        <div class="manual-card__controls">
          <input v-model.number="storageDuration" min="3" max="120" step="1" type="number" aria-label="测试时长" />
          <button type="button" @click="selectStorageCharge">选定</button>
        </div>
      </section>

      <section class="manual-card">
        <div class="manual-card__title">
          <ShieldAlert :size="16" />
          <span>模拟安全事件</span>
        </div>
        <div class="manual-card__controls">
          <select v-model.number="securityNode" aria-label="选择节点">
            <option v-for="node in NODES" :key="node.id" :value="node.id">{{ node.key }}</option>
          </select>
          <select v-model="securityKind" aria-label="选择事件类型">
            <option value="forged">伪造身份</option>
            <option value="anomalous">异常出力</option>
            <option value="control">越权控制</option>
          </select>
          <button type="button" @click="selectSecurityIncident">选定</button>
        </div>
      </section>

      <section class="manual-card">
        <div class="manual-card__title">
          <AlertTriangle :size="16" />
          <span>强制状态切换</span>
        </div>
        <div class="manual-card__controls">
          <select v-model="forcedMode" aria-label="选择强制状态">
            <option value="global_cooperative">全局协同</option>
            <option value="local_cluster">局部聚类</option>
            <option value="autonomous">完全自治</option>
          </select>
          <input v-model.number="forcedModeDuration" min="3" max="120" step="1" type="number" aria-label="强制时长" />
          <button type="button" @click="selectForceMode">选定</button>
        </div>
      </section>
    </div>

    <div class="manual-console__lower">
      <div class="manual-pending">
        <header>
          <span>待确认操作</span>
          <strong>{{ pending.length }}</strong>
        </header>
        <div v-if="pending.length === 0" class="manual-empty">没有待确认操作</div>
        <div v-for="item in pending" :key="item.request_id" class="manual-pending__item">
          <div>
            <strong>{{ operationLabel(item) }}</strong>
            <span>剩余 {{ remainingText(item) }}</span>
          </div>
          <button class="manual-button manual-button--confirm" type="button" @click="operate(item)">确认执行</button>
          <button class="manual-button manual-button--cancel" type="button" @click="cancel(item)">取消</button>
        </div>
      </div>

      <div class="manual-status">
        <div :class="responseClass()">
          {{ response?.message ?? '等待操作员选定控制对象' }}
        </div>
        <div class="manual-active">
          <span v-if="activeInterventions.length === 0">无活动人工干预</span>
          <span v-for="item in activeInterventions" :key="item.target_key">
            {{ item.label }} · {{ activeRemaining(item.expires_at_elapsed_s) }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
