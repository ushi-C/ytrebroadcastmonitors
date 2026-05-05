<template>
  <div style="height:100%;display:flex;flex-direction:column">
    <!-- Tab Bar -->
    <div class="tab-bar">
      <h1>Y-VISION TERMINAL</h1>

      <button
        id="tab-monitor"
        class="tab-btn"
        :class="{ active: activeTab === 'monitor' }"
        @click="switchTab('monitor')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 12a7 7 0 0 1 14 0" opacity="0.4"/>
          <path d="M8.5 12a3.5 3.5 0 0 1 7 0" />
          <circle cx="12" cy="12" r="1" fill="currentColor"/>
        </svg>
        频道信号
      </button>

      <button
        id="tab-player"
        class="tab-btn"
        :class="{ active: activeTab === 'player' }"
        @click="switchTab('player')"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1"/>
          <rect x="14" y="3" width="7" height="7" rx="1" opacity="0.4"/>
          <rect x="3" y="14" width="7" height="7" rx="1" opacity="0.4"/>
         <rect x="14" y="14" width="7" height="7" rx="1"/>
        </svg>
        播放阵列
      </button>

      <!-- Spacer to push theme switcher to right -->
      <div class="tab-spacer"></div>

      <!-- 主题切换器 -->
      <div class="theme-switcher" v-if="appState.themeInitialized">
        <button
          v-for="t in themeList"
          :key="t.id"
          class="theme-pill"
          :class="{ active: currentTheme === t.id }"
          :title="t.label"
          @click="setTheme(t.id)"
        >
          <span
            class="theme-dot"
            :style="{
              background: `linear-gradient(135deg, ${t.accent[0]} 50%, ${t.accent[1]} 50%)`
            }"
          ></span>
          <span class="theme-label" :style="{ color: t.accent[0] }">
            {{ t.label }}
          </span>
        </button>
      </div>
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
    <div id="toast" class="toast" :class="{ show: toastVisible }">
      {{ toastMsg }}
    </div>

    <!-- Scale tip -->
    <div id="scale-tip" :class="{ show: scaleVisible }">
      {{ scalePct }}%
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import MonitorView from './components/MonitorView.vue'
import PlayerView from './components/PlayerView.vue'
import { appState } from './stores/appState'
import { useTheme } from './composables/useTheme'

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

// theme
const { currentTheme, themeList, setTheme } = useTheme()

function applyScale() {
  const fs = Math.min(20, Math.max(10, (window.innerWidth / BASE_W) * BASE_FS))
  document.documentElement.style.fontSize = fs.toFixed(3) + 'px'
  scalePct.value = Math.round((fs / BASE_FS) * 100)

  scaleVisible.value = true
  clearTimeout(scaleTimer)
  scaleTimer = setTimeout(() => {
    scaleVisible.value = false
  }, 1200)
}

function switchTab(name) {
  activeTab.value = name
}

function showToast(msg) {
  toastMsg.value = msg
  toastVisible.value = true

  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastVisible.value = false
  }, 2200)
}

function sendToPlayer(result) {
  if (!playerViewEl.value) return

  const { layout, MAX_PLAYERS } = playerViewEl.value

  if (layout.length >= MAX_PLAYERS) {
    showToast(`播放器limit (最多 ${MAX_PLAYERS} 个窗口)`)
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

<style scoped>
/* ── Tab Bar 优化 ── */
.tab-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0.5rem 1rem;
  background: var(--surface); /* 确保背景色统一 */
  border-bottom: 1px solid var(--border);
}

.tab-bar h1 {
  margin-right: 12px;
  font-size: 1rem;
  font-weight: 800;
  letter-spacing: 1px;
}

/* 选项卡按钮 */
.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0.4rem 0.8rem;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  border-radius: 0.4rem;
  font-size: 0.85rem;
  font-weight: 600;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform;
}

.tab-btn svg {
  width: 16px;
  height: 16px;
}

.tab-btn:hover {
  color: var(--text);
  /* 同样的悬浮上移效果 */
  transform: translateY(-1px);
  background: color-mix(in srgb, var(--primary) 10%, transparent);
}

.tab-btn.active {
  color: var(--primary);
  background: color-mix(in srgb, var(--primary) 15%, transparent);
}

/* ── 主题切换器优化 ── */
.theme-switcher {
  display: flex;
  gap: 6px;
  padding: 4px;
  background: var(--surface2);
  border-radius: 20px;
}

.theme-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: none;
  background: transparent;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.theme-pill:hover {
  /* 药丸按钮 */
  transform: translateY(-0.5px);
  background: rgba(255, 255, 255, 0.05);
}

.theme-pill.active {
  background: var(--surface);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

.theme-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.1);
}

/* ── Toast 提示优化 ── */
.toast {
  position: fixed;
  bottom: 2rem;
  left: 50%;
  transform: translateX(-50%) translateY(10px);
  padding: 0.6rem 1.2rem;
  background: var(--primary);
  color: #fff;
  border-radius: 2rem;
  font-size: 0.85rem;
  font-weight: 600;
  box-shadow: 0 10px 25px rgba(0,0,0,0.3);
  opacity: 0;
  pointer-events: none;
  transition: all 0.3s cubic-bezier(0.18, 0.89, 0.32, 1.28);
}

.toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

#scale-tip {
  position: fixed;
  top: 10px;
  right: 10px;
  opacity: 0;
  transition: 0.3s;
}

#scale-tip.show {
  opacity: 1;
}
</style>