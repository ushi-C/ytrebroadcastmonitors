<template>
  <div id="view-monitor" class="view" :class="{ active: active }">
    <!-- Toolbar -->


    <div class="network-status-bar">

      <button
        class="mon-action-btn"
        :disabled="isChecking"
        @click="checkNetwork(true)"
      >
        检测 YouTube 连接性
      </button>

      <div class="network-status">
        <span
          class="status-dot"
          :class="{
            checking: isChecking,
            online: !isChecking && networkState.youtube_available,
            blocked: !isChecking && !networkState.youtube_available
          }"
        ></span>

        <span class="status-text">
          <template v-if="isChecking">
            检测中...
          </template>

          <template v-else-if="networkState.youtube_available">
            当前线路可用
          </template>

          <template v-else>
            当前线路被 YouTube 风控
          </template>
        </span>
      </div>

    </div>

    <div class="monitor-toolbar" ref="toolbarEl">
      <button id="mon-btn" class="mon-action-btn" :disabled="scanRunning || isChecking || !networkState.youtube_available" @click="startScan">
        {{ scanRunning ? '扫描中…' : '同步序列' }}
      </button>
      <span id="mon-progress">{{ statusText }}</span>

      <!-- Search -->
      <div class="search-wrap" id="search-wrap" ref="searchWrapEl">
        <svg class="search-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="9" cy="9" r="6"/><path d="M15 15l3 3"/>
        </svg>
        <input
          class="search-input"
          id="search-input"
          ref="searchInputEl"
          v-model="searchQuery"
          placeholder="频道检索…"
          @input="onSearchInput"
          @keydown.esc="closeDropdown"
          @focus="onSearchFocus"
        />
        <button
          class="search-clear"
          :class="{ visible: searchQuery.length > 0 }"
          @click="clearSearch"
        >✕</button>
      </div>
    </div>


    <!-- Search dropdown (absolutely positioned inside view) -->
    <SearchDropdown
      :visible="dropdownVisible"
      :query="searchQuery"
      :hits="searchHits"
      @send="$emit('send-to-player', $event)"
      @live-found="onLiveFound"
      @close="closeDropdown"
    />

    <!-- Card grid -->
    <div class="monitor-body">
      <div id="mon-grid">
        <MonCard
          v-for="item in monItems"
          :key="item._key || item.url || item.id"
          :item="item"
          @send="$emit('send-to-player', $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import Fuse from 'fuse.js'
import MonCard from './MonCard.vue'
import SearchDropdown from './SearchDropdown.vue'
import { useApiClient } from '../composables/useApiClient.js'
import { useNetworkProbe } from '../composables/useNetworkProbe.js'
import { appState } from '../stores/appState.js'
import { monItemKey, extractHandleFromUrl } from '../composables/useDomUtils.js'

const props = defineProps({ active: Boolean })
const emit = defineEmits(['send-to-player'])

const { refreshScan, getStatus, getChannels } = useApiClient()
const { isChecking, networkState, runProbe, loadStatus } = useNetworkProbe()

const scanRunning = ref(false)
const statusText = ref('')
const monItems = ref([])
const searchQuery = ref('')
const dropdownVisible = ref(false)
const searchHits = ref([])
let fuse = null
let pollTimer = null
let searchTimer = null

// Pending avatar retry tracking
const pendingAvatarIds = new Set()
const renderedKeys = new Set()

async function checkNetwork(force = false) {
  await runProbe(force)
}

// --- Scan ---

async function startScan() {
  if (!networkState.value.youtube_available) {
    statusText.value = '网络不可用，无法扫描'
    return
  }

  clearInterval(pollTimer)
  pollTimer = null
  renderedKeys.clear()
  pendingAvatarIds.clear()
  monItems.value = []
  appState.scanRenderedKeys = new Set()
  appState.searchRenderedKeys = new Set()

  scanRunning.value = true
  statusText.value = '正在启动扫描…'

  try {
    await refreshScan()
  } catch (e) {
    statusText.value = '后端未连接 (需启动 uvicorn)'
    scanRunning.value = false
    return
  }

  setTimeout(() => {
    pollTimer = setInterval(checkStatus, 2000)
    checkStatus()
  }, 800)
}

async function checkStatus() {
  try {
    const state = await getStatus()
    const list = state.results || []
    const latestKeys = new Set(list.map(item => monItemKey(item)))

    // Remove cards that are no longer present in backend results
    monItems.value = monItems.value.filter(item => latestKeys.has(monItemKey(item)))
    renderedKeys.clear()
    for (const item of monItems.value) renderedKeys.add(monItemKey(item))

    // Incremental render
    for (const item of list) {
      const key = monItemKey(item)
      if (!renderedKeys.has(key)) {
        renderedKeys.add(key)
        item._key = key
        monItems.value.push(item)
      }
    }

    syncAvatarsFromList(list)

    if (state.is_running) {
      scanRunning.value = true
      statusText.value = `检测中: ${state.progress} / ${state.total}`
    } else {
      scanRunning.value = false
      const n = list.length
      if (state.is_monitoring) {
        statusText.value = n ? `监测中 (当前 ${n} 个直播)` : '监测结束: 0 个直播'
      } else {
        statusText.value = n ? `检测完成 (共 ${n} 个直播)` : '上次: 0 个直播'
      }
    }
    reconcileStatusPolling(state)
  } catch (e) {
    statusText.value = '后端未连接 (需启动 uvicorn)'
    clearInterval(pollTimer)
    pollTimer = null
    scanRunning.value = false
  }
}

function syncAvatarsFromList(list) {
  const byId = new Map(list.filter(i => i.id).map(i => [i.id, i]))
  for (const item of list) updateAvatar(item)
  // 已渲染卡片可能来自较早轮次，需对照最新 status 再同步一次
  for (const card of monItems.value) {
    if (!card.id) continue
    const latest = byId.get(card.id)
    if (latest) updateAvatar(latest)
  }
}

function reconcileStatusPolling(state) {
  const shouldPoll = !!(
    state.is_running ||
    state.is_monitoring ||
    pendingAvatarIds.size > 0
  )
  if (shouldPoll) {
    if (!pollTimer) pollTimer = setInterval(checkStatus, 2000)
  } else if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function updateAvatar(item) {
  if (!item || !item.id) return
  if (!item.avatar) {
    pendingAvatarIds.add(item.id)
    return
  }
  let found = monItems.value.find(i => i.id === item.id)
  if (!found) {
    const key = monItemKey(item)
    found = monItems.value.find(i => monItemKey(i) === key)
  }
  if (found) found.avatar = item.avatar
  pendingAvatarIds.delete(item.id)
}

// --- Search ---

onMounted(async () => {
  await loadStatus()
  await checkNetwork(false)

  // Load initial status
  try {
    const state = await getStatus()
    const list = state.results || []
    for (const item of list) {
      const key = monItemKey(item)
      if (!renderedKeys.has(key)) {
        renderedKeys.add(key)
        item._key = key
        monItems.value.push(item)
      }
    }
    syncAvatarsFromList(list)
    reconcileStatusPolling(state)
    if (list.length) statusText.value = `上次结果: ${list.length} 个直播`
  } catch (_) {}

  // Load channels for search
  try {
    const data = await getChannels()
    appState.csvChannels = (data.channels || []).map(r => ({
      id: r.id || '',
      url: r.url || '',
      title: r.title || '',
      handle: extractHandleFromUrl(r.url || ''),
    }))
    if (appState.csvChannels.length) {
      fuse = new Fuse(appState.csvChannels, {
        keys: ['title'],
        threshold: 0.5,
        includeScore: true,
        minMatchCharLength: 1,
      })
    }
  } catch (_) {}

  document.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  document.removeEventListener('click', onDocClick)
})

const searchWrapEl = ref(null)

function onDocClick(e) {
  if (searchWrapEl.value && !searchWrapEl.value.contains(e.target)) {
    closeDropdown()
  }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) { closeDropdown(); return }
  searchTimer = setTimeout(() => runSearch(searchQuery.value.trim()), 120)
}

function onSearchFocus() {
  if (searchQuery.value.trim()) onSearchInput()
}

function clearSearch() {
  searchQuery.value = ''
  closeDropdown()
}

function closeDropdown() {
  dropdownVisible.value = false
  searchHits.value = []
}

function runSearch(q) {
  if (!appState.csvChannels.length) {
    searchHits.value = []
    dropdownVisible.value = true
    return
  }
  let hits
  if (fuse) {
    hits = fuse.search(q).slice(0, 8).map(r => r.item)
  } else {
    const kw = q.toLowerCase()
    hits = appState.csvChannels.filter(ch =>
      (ch.title || '').toLowerCase().includes(kw) ||
      (ch.id || '').toLowerCase().includes(kw) ||
      (ch.url || '').toLowerCase().includes(kw)
    ).slice(0, 8)
  }
  searchHits.value = hits
  dropdownVisible.value = true
}

function onLiveFound(result) {
  // Add live card from search result to top of grid
  const key = monItemKey(result)
  if (!appState.searchRenderedKeys.has(key) && !renderedKeys.has(key)) {
    appState.searchRenderedKeys.add(key)
    result._key = key
    monItems.value.unshift(result)
    updateAvatar(result)
    if (pendingAvatarIds.size > 0) {
      reconcileStatusPolling({ is_running: false, is_monitoring: false })
    }
  }
}
</script>

<style scoped>
.network-status-bar {
  display: flex;
  align-items: center;
  gap: 0.9rem;

  padding: 0.7rem 1.2rem;

  background:
    linear-gradient(
      90deg,
      rgba(20,10,40,.92),
      rgba(12,8,28,.92)
    );

  border-bottom: 1px solid rgba(120,80,200,.18);

  font-size: 0.82rem;
}

.network-status {
  display: flex;
  align-items: center;
  gap: 0.55rem;

  min-width: 12rem;
}

.status-text {
  font-size: 0.8rem;
  font-weight: 500;
  letter-spacing: 0.02em;

  color: #d8cff7;

  font-family:
    "Inter",
    "PingFang SC",
    sans-serif;
}

.status-dot {
  width: 0.55rem;
  height: 0.55rem;

  border-radius: 50%;

  flex-shrink: 0;

  position: relative;
}

.status-dot.online {
  background: #52ffb8;

  box-shadow:
    0 0 8px rgba(82,255,184,.8),
    0 0 16px rgba(82,255,184,.35);
}

.status-dot.blocked {
  background: #ff4d6d;

  box-shadow:
    0 0 8px rgba(255,77,109,.75),
    0 0 16px rgba(255,77,109,.3);
}

.status-dot.checking {
  background: #ffd166;

  animation: pulse-status 1.2s ease-in-out infinite;

  box-shadow:
    0 0 10px rgba(255,209,102,.7);
}

@keyframes pulse-status {
  0% {
    transform: scale(1);
    opacity: 1;
  }

  50% {
    transform: scale(1.4);
    opacity: .6;
  }

  100% {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
