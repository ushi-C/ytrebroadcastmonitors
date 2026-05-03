<template>
  <div id="view-monitor" class="view" :class="{ active: active }">
    <!-- Toolbar -->
    <div class="monitor-toolbar" ref="toolbarEl">
      <button id="mon-btn" class="mon-action-btn" :disabled="scanRunning" @click="startScan">
        {{ scanRunning ? '扫描中…' : '开始扫描' }}
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
          placeholder="搜索频道…"
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
import { appState } from '../stores/appState.js'
import { monItemKey, extractHandleFromUrl } from '../composables/useDomUtils.js'

const props = defineProps({ active: Boolean })
const emit = defineEmits(['send-to-player'])

const { refreshScan, getStatus, getChannels } = useApiClient()

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
let avatarPollGeneration = 0   // 每次新扫描递增，用于取消过期的 avatar 轮询

// --- Scan ---

async function startScan() {
  clearInterval(pollTimer)
  pollTimer = null
  renderedKeys.clear()
  pendingAvatarIds.clear()
  monItems.value = []
  appState.scanRenderedKeys = new Set()
  appState.searchRenderedKeys = new Set()

  avatarPollGeneration++     // 让旧的 pollPendingAvatars 循环自动停止
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

    // Incremental render
    for (const item of list) {
      const key = monItemKey(item)
      if (!renderedKeys.has(key)) {
        renderedKeys.add(key)
        item._key = key
        monItems.value.push(item)
      }
    }

    // Avatar updates
    const byId = new Map(list.filter(i => i.id).map(i => [i.id, i]))
    for (const item of list) updateAvatar(item, byId)
    if (pendingAvatarIds.size > 0) {
      for (const id of [...pendingAvatarIds]) {
        const it = byId.get(id)
        if (it) updateAvatar(it, byId)
      }
    }

    if (state.is_running) {
      scanRunning.value = true
      statusText.value = `检测中: ${state.progress} / ${state.total}`
      if (!pollTimer) pollTimer = setInterval(checkStatus, 2000)
    } else {
      scanRunning.value = false
      clearInterval(pollTimer)
      pollTimer = null
      const n = list.length
      statusText.value = n ? `检测完成 (共 ${n} 个直播)` : '上次: 0 个直播'
      if (pendingAvatarIds.size > 0) pollPendingAvatars(0, avatarPollGeneration)
    }
  } catch (e) {
    statusText.value = '后端未连接 (需启动 uvicorn)'
    clearInterval(pollTimer)
    pollTimer = null
    scanRunning.value = false
  }
}

function updateAvatar(item, byId) {
  if (!item || !item.id) return
  if (!item.avatar) { pendingAvatarIds.add(item.id); return }
  // Find and update the reactive item
  const found = monItems.value.find(i => i.id === item.id)
  if (found && found.avatar !== item.avatar) {
    found.avatar = item.avatar
  }
  pendingAvatarIds.delete(item.id)
}

function pollPendingAvatars(attempt, generation) {
  if (pendingAvatarIds.size === 0 || attempt >= 10) return
  setTimeout(async () => {
    // 如果已经开始了新扫描，停止此轮询
    if (generation !== avatarPollGeneration) return
    try {
      const state = await getStatus()
      const list = state.results || []
      const byId = new Map(list.filter(i => i.id).map(i => [i.id, i]))
      for (const id of [...pendingAvatarIds]) {
        const it = byId.get(id)
        if (it) updateAvatar(it, byId)
      }
    } catch (_) {}
    pollPendingAvatars(attempt + 1, generation)
  }, 2000)
}

// --- Search ---

onMounted(async () => {
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
  }
}
</script>
