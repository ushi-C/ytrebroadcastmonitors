<template>
  <div class="app-shell">
    <div class="bg-base"></div>
    <div class="bg-overlay" :style="bgOverlayStyle"></div>
    <div class="app-content">
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
        <div class="bg-menu-wrap">
          <button class="icon-btn" :class="{ loading: bgSaving }" title="背景设置" @click.stop="toggleBgMenu">
            <!-- 上传中显示 spinner，否则显示上传图标 -->
            <svg v-if="bgSaving" class="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V8"/>
              <path d="M8.5 11.5 12 8l3.5 3.5"/>
              <path d="M21 16.5v2a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5v-2"/>
            </svg>
          </button>
          <div v-if="bgMenuOpen" class="bg-menu" @click.stop>
            <div v-if="appState.userBackgroundUrl" class="bg-preview-wrap">
              <img class="bg-preview" :src="appState.userBackgroundUrl" alt="当前背景" />
            </div>
            <button class="bg-menu-item" :disabled="bgSaving" @click="handleUploadClick">
              {{ appState.userBackgroundUrl ? '更换背景' : '上传背景' }}
            </button>
            <button
              v-if="appState.userBackgroundUrl"
              class="bg-menu-item danger"
              :disabled="bgSaving"
              @click="handleClearClick"
            >
              清除背景
            </button>
          </div>
        </div>
        <button class="icon-btn" title="全屏" @click="toggleFullscreen">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3H3v5"/><path d="M16 3h5v5"/><path d="M21 16v5h-5"/><path d="M3 16v5h5"/>
          </svg>
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
    <input ref="bgInputEl" type="file" accept="image/*" class="hidden-input" @change="onBackgroundSelected" />
    <div class="bottom-art-line" aria-hidden="true"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import MonitorView from './components/MonitorView.vue'
import PlayerView from './components/PlayerView.vue'
import { appState } from './stores/appState'
import { useTheme } from './composables/useTheme'
import { useBackground } from './composables/useBackground'

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
const bgInputEl = ref(null)
const bgMenuOpen = ref(false)

// theme
const { currentTheme, themeList, setTheme } = useTheme()

// background persistence
const { saving: bgSaving, error: bgError, restoreBackground, saveBackground, clearBackground } = useBackground()

const bgOverlayStyle = computed(() => {
  if (!appState.userBackgroundUrl) {
    return { opacity: 0 }
  }
  return {
    backgroundImage: `url(${appState.userBackgroundUrl})`,
    opacity: 0.38,
  }
})

function triggerBackgroundUpload() {
  bgInputEl.value?.click()
}

function toggleBgMenu() {
  bgMenuOpen.value = !bgMenuOpen.value
}

function handleUploadClick() {
  bgMenuOpen.value = false
  triggerBackgroundUpload()
}

async function handleClearClick() {
  bgMenuOpen.value = false
  await clearBackground()
  showToast('背景已清除')
}

async function onBackgroundSelected(event) {
  const file = event.target.files?.[0]
  if (!file) return

  // Reset input early so same file can be re-selected later
  event.target.value = ''

  const ok = await saveBackground(file)
  if (ok) {
    showToast('背景已保存')
  } else {
    showToast(bgError.value || '背景保存失败')
  }
}

async function toggleFullscreen() {
  try {
    if (window.pywebview?.api?.toggle_native_fullscreen) {
      await window.pywebview.api.toggle_native_fullscreen()
      return
    }
  } catch (_error) {
    // fallback to browser fullscreen below
  }

  if (!document.fullscreenElement) {
    await document.documentElement.requestFullscreen()
  } else {
    await document.exitFullscreen()
  }
}

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

function onGlobalClick() {
  bgMenuOpen.value = false
}

onMounted(async () => {
  applyScale()
  window.addEventListener('resize', onResize)
  window.addEventListener('click', onGlobalClick)
  // 恢复持久化背景
  await restoreBackground()
  if (typeof window.__notifyPywebviewReady === 'function') {
    await window.__notifyPywebviewReady()
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('click', onGlobalClick)
  clearTimeout(toastTimer)
  clearTimeout(scaleTimer)
})
</script>

<style scoped>
.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.bg-base,
.bg-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.bg-base {
  background:
    radial-gradient(70% 80% at 0% 0%, color-mix(in srgb, var(--primary2) 14%, transparent), transparent 75%),
    radial-gradient(60% 70% at 100% 100%, color-mix(in srgb, var(--primary) 14%, transparent), transparent 72%);
}

.bg-overlay {
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  mix-blend-mode: screen;
  transition: opacity .25s ease;
}

.app-content {
  position: relative;
  z-index: 2;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.icon-btn {
  border: none;
  background: transparent;
  color: var(--muted);
  padding: 0.3rem;
  border-radius: 8px;
  display: inline-flex;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}

.icon-btn svg { width: 16px; height: 16px; }
.icon-btn:hover { color: var(--text); background: rgba(255,255,255,0.08); }
.icon-btn.loading { color: var(--primary); cursor: default; }

@keyframes spin {
  to { transform: rotate(360deg); }
}
.spin { animation: spin 0.8s linear infinite; }

.bg-menu-wrap {
  position: relative;
}

.bg-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  min-width: 120px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 80;
}

/* 缩略图预览 */
.bg-preview-wrap {
  padding: 4px 4px 2px;
}
.bg-preview {
  width: 100%;
  height: 60px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--border);
  display: block;
}

.bg-menu-item {
  border: none;
  background: transparent;
  color: var(--text);
  text-align: left;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}

.bg-menu-item:hover:not(:disabled) { background: rgba(255,255,255,0.08); }
.bg-menu-item:disabled { opacity: 0.4; cursor: default; }
.bg-menu-item.danger { color: #ff9fae; }

.hidden-input { display: none; }

.bottom-art-line {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 2px;
  background: linear-gradient(90deg,
    transparent 0%,
    color-mix(in srgb, var(--primary2) 55%, transparent) 18%,
    color-mix(in srgb, var(--primary) 75%, transparent) 50%,
    color-mix(in srgb, var(--primary2) 55%, transparent) 82%,
    transparent 100%);
  box-shadow:
    0 0 10px color-mix(in srgb, var(--primary2) 35%, transparent),
    0 -1px 10px color-mix(in srgb, var(--primary) 20%, transparent);
  z-index: 5;
}
/* ── Tab Bar 优化 ── */
.tab-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0.5rem 1rem;
  background: var(--surface);
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
