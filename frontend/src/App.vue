<template>
  <div style="height:100%;display:flex;flex-direction:column">
    <!-- Tab Bar -->
    <div class="tab-bar">
      <h1>YVmonitor</h1>
      <button id="tab-monitor" class="tab-btn" :class="{ active: activeTab === 'monitor' }" @click="switchTab('monitor')">
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 2a8 8 0 100 16A8 8 0 0010 2zm0 14a6 6 0 110-12 6 6 0 010 12z" opacity=".3"/>
          <circle cx="10" cy="10" r="3"/>
        </svg>
        频道信号
      </button>
      <button id="tab-player" class="tab-btn" :class="{ active: activeTab === 'player' }" @click="switchTab('player')">
        <svg viewBox="0 0 20 20" fill="currentColor">
          <rect x="2" y="3" width="16" height="11" rx="2" opacity=".3"/>
          <path d="M8 7l5 3-5 3V7z"/>
        </svg>
        播放阵列
      </button>
    </div>

    <!-- Views -->
    <MonitorView
      :active="activeTab === 'monitor'"
      @send-to-player="sendToPlayer"
    />
    <PlayerView
      ref="playerViewEl"
      :active="activeTab === 'player'"
      @toast="showToast"
    />

    <!-- Toast -->
    <div id="toast" class="toast" :class="{ show: toastVisible }">{{ toastMsg }}</div>

    <!-- Scale tip -->
    <div id="scale-tip" :class="{ show: scaleVisible }">{{ scalePct }}%</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import MonitorView from './components/MonitorView.vue'
import PlayerView from './components/PlayerView.vue'

const activeTab = ref('monitor')
const playerViewEl = ref(null)

const toastMsg = ref('')
const toastVisible = ref(false)
let toastTimer = null

const scalePct = ref(100)
const scaleVisible = ref(false)
let scaleTimer = null

const BASE_W = 1440
const BASE_FS = 16

function applyScale() {
  const fs = Math.min(20, Math.max(10, (window.innerWidth / BASE_W) * BASE_FS))
  document.documentElement.style.fontSize = fs.toFixed(3) + 'px'
  scalePct.value = Math.round((fs / BASE_FS) * 100)
  scaleVisible.value = true
  clearTimeout(scaleTimer)
  scaleTimer = setTimeout(() => { scaleVisible.value = false }, 1200)
}

function switchTab(name) {
  activeTab.value = name
}

function showToast(msg) {
  toastMsg.value = msg
  toastVisible.value = true
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastVisible.value = false }, 2200)
}

function sendToPlayer(result) {
  if (!playerViewEl.value) return
  const { layout, MAX_PLAYERS } = playerViewEl.value
  if (layout.length >= MAX_PLAYERS) {
    showToast(`播放器已满 (最多 ${MAX_PLAYERS} 个窗口)`)
    return
  }
  playerViewEl.value.addPlayer(result.url)
  switchTab('player')
  showToast('已添加: ' + (result.name || result.url))
}

function onResize() {
  applyScale()
}

onMounted(() => {
  applyScale()
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  clearTimeout(toastTimer)
  clearTimeout(scaleTimer)
})
</script>
