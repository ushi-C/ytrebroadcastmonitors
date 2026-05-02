<template>
  <div class="search-dropdown" v-show="visible" ref="dropdownEl">
    <!-- Results list -->
    <div class="sd-section-header" v-if="hits.length">
      找到 {{ hits.length }} 个频道，点击检测直播状态
    </div>
    <div class="sd-empty" v-else-if="query">没有匹配的频道</div>

    <div
      v-for="ch in hits"
      :key="ch.id || ch.url"
      class="sd-item"
      @click="openUrl(checkCacheResult(ch))"
    >
      <div class="sd-avatar-placeholder" v-show="!avatarLoaded(ch)">▶</div>
      <img
        class="sd-avatar"
        :class="{ loaded: avatarLoaded(ch) }"
        :src="avatarSrc(ch)"
        alt=""
        @error="e => e.target.style.display='none'"
      />
      <div class="sd-info">
        <div class="sd-name">{{ displayName(ch) }}</div>
        <div class="sd-meta">{{ ch.id || ch.url || '' }}</div>
      </div>
      <span class="sd-badge" :class="badgeClass(ch)">{{ badgeText(ch) }}</span>
      <button class="sd-check-btn" type="button" @click.stop="checkChannel(ch)">开始检测</button>
      <button
        class="sd-send-btn"
        v-if="checkCacheResult(ch)"
        style="display:flex"
        title="窗口播放"
        @click.stop="sendToPlayer(checkCacheResult(ch))"
      >
        <svg viewBox="0 0 800 800" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient :id="`grad-sd-${ch.id || ch.url}`" x1="50%" y1="0%" x2="50%" y2="100%">
              <stop offset="45%" stop-color="hsl(184,74%,44%)"/>
              <stop offset="100%" stop-color="hsl(332,87%,70%)"/>
            </linearGradient>
          </defs>
          <g stroke-width="40" :stroke="`url(#grad-sd-${ch.id || ch.url})`" fill="none">
            <circle cx="400" cy="400" r="340.5"/>
            <circle cx="400" cy="400" r="215.5"/>
            <circle cx="400" cy="400" r="90.5"/>
            <circle cx="400" cy="400" r="373" opacity="0.3"/>
            <circle cx="400" cy="400" r="248" opacity="0.3"/>
            <circle cx="400" cy="400" r="123" opacity="0.3"/>
          </g>
        </svg>
      </button>
    </div>

    <!-- Direct check item always last -->
    <div class="sd-item" style="opacity:0.75" v-if="query">
      <div class="sd-avatar-placeholder">🔍</div>
      <div class="sd-info">
        <div class="sd-name">直接检测: {{ query }}</div>
        <div class="sd-meta">将 "{{ query }}" 作为 URL 或 ID 检测直播状态</div>
      </div>
      <span class="sd-badge offline">未检测</span>
      <button class="sd-check-btn" type="button" @click.stop="checkChannel({ id: query, url: query, title: '' })">开始检测</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useApiClient } from '../composables/useApiClient.js'
import { appState } from '../stores/appState.js'

const props = defineProps({
  visible: Boolean,
  query: String,
  hits: Array,
  dropdownTop: String,
})
const emit = defineEmits(['send', 'live-found', 'close'])

const { checkChannel: apiCheckChannel } = useApiClient()
const dropdownEl = ref(null)

// Local state for badge/avatar per channel key
const badgeStates = ref({})  // key -> 'unchecked'|'checking'|'live'|'offline'
const avatarSrcs = ref({})
const cachedNames = ref({})
const cachedTitles = ref({})

function chKey(ch) {
  return (ch.id && ch.id !== '') ? ch.id : ch.url
}

function displayName(ch) {
  const k = chKey(ch)
  return cachedNames.value[k] || ch.title || ch.handle || ch.id
}

function avatarLoaded(ch) {
  return !!avatarSrcs.value[chKey(ch)]
}

function avatarSrc(ch) {
  return avatarSrcs.value[chKey(ch)] || ''
}

function checkCacheResult(ch) {
  const k = chKey(ch)
  const cached = appState.checkCache.get(k)
  return cached ? cached.result : null
}

function badgeClass(ch) {
  const k = chKey(ch)
  const s = badgeStates.value[k] || 'unchecked'
  if (s === 'live') return 'live'
  if (s === 'checking') return 'checking'
  return 'offline'
}

function badgeText(ch) {
  const k = chKey(ch)
  const s = badgeStates.value[k] || 'unchecked'
  if (s === 'live') return '🔴 直播中'
  if (s === 'checking') return '检测中…'
  if (s === 'offline') return '未直播'
  return '未检测'
}

function openUrl(result) {
  if (result && result.url) window.open(result.url, '_blank')
}

function sendToPlayer(result) {
  if (result) {
    emit('send', result)
    emit('close')
  }
}

async function checkChannel(ch) {
  const key = chKey(ch)
  const cached = appState.checkCache.get(key)
  if (cached && (Date.now() - cached.ts < 5 * 60 * 1000)) {
    applyResult(ch, cached.result)
    return
  }
  if (appState.checking.has(key)) return
  appState.checking.add(key)
  badgeStates.value[key] = 'checking'

  const query = (ch.id && ch.id.startsWith('UC')) ? ch.id : (ch.url || ch.id)
  try {
    const data = await apiCheckChannel(query, ch.title || '')
    const result = data.result || null
    appState.checkCache.set(key, { result, ts: Date.now() })
    applyResult(ch, result)
  } catch (e) {
    badgeStates.value[key] = 'offline'
  } finally {
    appState.checking.delete(key)
  }
}

function applyResult(ch, result) {
  const key = chKey(ch)
  if (result) {
    badgeStates.value[key] = 'live'
    if (result.avatar) avatarSrcs.value[key] = result.avatar
    if (result.name) cachedNames.value[key] = result.name
    if (result.title) cachedTitles.value[key] = result.title
    emit('live-found', result)
  } else {
    badgeStates.value[key] = 'offline'
  }
}
</script>
