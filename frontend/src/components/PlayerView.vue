<template>
  <div id="view-player" class="view" :class="{ active: active }">
    <!-- Toolbar -->
    <div class="player-toolbar">
      <!-- Layout buttons -->
      <div class="layout-btns">
        <button
          v-for="c in [1,2,3]"
          :key="c"
          :id="`btn-col${c}`"
          class="layout-btn"
          :class="{ active: layoutCols === c }"
          @click="setLayoutCols(c)"
        >
          <template v-if="c === 1">
            <div style="display:grid;grid-template-columns:1fr;gap:2px">
              <div class="dot"></div>
            </div>
          </template>
          <template v-else-if="c === 2">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px">
              <div class="dot"></div><div class="dot"></div>
            </div>
          </template>
          <template v-else>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px">
              <div class="dot"></div><div class="dot"></div><div class="dot"></div>
            </div>
          </template>
        </button>
      </div>

      <button id="addBtn" class="add-btn" :disabled="layout.length >= MAX_PLAYERS" @click="addPlayer()">
        ＋ 添加窗口
      </button>
      <button id="btnRefreshAll" class="tb-secondary" @click="refreshAll">全域刷新</button>
      <span id="countBadge" class="count-badge">{{ layout.length }} / {{ MAX_PLAYERS }} 个窗口</span>
    </div>

    <!-- Desk -->
    <div id="desk" ref="deskEl">
      <div id="empty-hint" :style="{ display: layout.length === 0 ? 'block' : 'none' }">
        <strong>系统待命 SYSTEM READY</strong>
        请添加播放窗口或在「频道信号」中发送直播到播放器
      </div>

      <!-- Windows (shell only, iframes rendered separately) -->
      <PlayerCard
        v-for="(id, idx) in layout"
        :key="id"
        :id="id"
        :ref="el => cardRefs[id] = el"
        :slot="slots[idx] || null"
        @remove="removePlayer"
        @drag-swap="onDragStart"
        @load-video="onLoadVideo"
      />

      <!-- Iframes rendered at desk level to enable proper transform -->
      <iframe
        v-for="id in layout"
        :key="'ifr-' + id"
        :id="`iframe-${id}`"
        class="wm-iframe-layer"
        :src="iframeSrcs[id] || 'about:blank'"
        :style="iframeStyles[id] || {}"
        allow="autoplay; fullscreen"
        referrerpolicy="origin"
        allowfullscreen
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import PlayerCard from './PlayerCard.vue'

const props = defineProps({ active: Boolean })
const emit = defineEmits(['toast'])

const MAX_PLAYERS = 6
const GAP = 6
const PAD = 8
const BASE_W = 1440
const BASE_FS = 16

const layoutCols = ref(1)
const layout = ref([])   // ordered array of player IDs
const cardCount = ref(0)
const cardRefs = reactive({})
const iframeSrcs = reactive({})
const iframeStyles = reactive({})
const ratioModes = reactive({})

const deskEl = ref(null)
const slots = ref([])

// Expose addPlayer for parent
function addPlayer(initUrl) {
  if (layout.value.length >= MAX_PLAYERS) return null
  const id = ++cardCount.value
  ratioModes[id] = 'landscape'
  iframeSrcs[id] = 'about:blank'
  iframeStyles[id] = {}
  layout.value.push(id)
  nextTick(() => {
    relayout()
    if (initUrl && cardRefs[id]) {
      cardRefs[id].setUrl(initUrl)
    }
  })
  return id
}

function removePlayer(id) {
  const idx = layout.value.indexOf(id)
  if (idx !== -1) layout.value.splice(idx, 1)
  delete cardRefs[id]
  delete iframeSrcs[id]
  delete iframeStyles[id]
  delete ratioModes[id]
  nextTick(relayout)
}

function setLayoutCols(c) {
  layoutCols.value = c
  nextTick(relayout)
}

function calcSlots(n, cols, deskW, deskH) {
  if (n === 0) return []
  const rows = Math.ceil(n / cols)
  const w = (deskW - PAD * 2 - GAP * (cols - 1)) / cols
  const h = (deskH - PAD * 2 - GAP * (rows - 1)) / rows
  return Array.from({ length: n }, (_, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    return { left: PAD + col * (w + GAP), top: PAD + row * (h + GAP), width: w, height: h }
  })
}

function relayout() {
  if (!deskEl.value) return
  const dW = deskEl.value.clientWidth
  const dH = deskEl.value.clientHeight
  const n = layout.value.length
  const cols = Math.min(layoutCols.value, n) || 1
  slots.value = calcSlots(n, cols, dW, dH)

  // Compute iframe transforms
  const titleH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--title-h'))
    * parseFloat(getComputedStyle(document.documentElement).fontSize)
  const ctrlH = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--ctrl-h'))
    * parseFloat(getComputedStyle(document.documentElement).fontSize)

  layout.value.forEach((id, i) => {
    const s = slots.value[i]
    if (!s) return
    const rm = ratioModes[id] || 'landscape'
    const baseW = rm === 'portrait' ? 720 : 1280
    const baseH = rm === 'portrait' ? 1280 : 720
    const viewportH = Math.max(40, s.height - titleH - ctrlH)
    const scale = Math.min(s.width / baseW, viewportH / baseH)
    const realW = baseW * scale
    const realH = baseH * scale
    const offsetX = s.left + (s.width - realW) / 2
    const offsetY = s.top + titleH + (viewportH - realH) / 2

    iframeStyles[id] = {
      width: baseW + 'px',
      height: baseH + 'px',
      transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
    }
  })
}

function onLoadVideo({ id, src, refresh, volume, relayout: doRelayout, ratioMode }) {
  if (volume !== undefined) {
    // Send postMessage to iframe
    const ifr = document.getElementById(`iframe-${id}`)
    if (ifr && ifr.src && ifr.src !== 'about:blank') {
      try {
        ifr.contentWindow.postMessage(
          JSON.stringify({ event: 'command', func: 'setVolume', args: [volume] }), '*'
        )
      } catch (_) {}
    }
    return
  }
  if (ratioMode) ratioModes[id] = ratioMode
  if (refresh) {
    const oldSrc = iframeSrcs[id]
    if (!oldSrc || oldSrc === 'about:blank') return
    iframeSrcs[id] = 'about:blank'
    nextTick(() => nextTick(() => { iframeSrcs[id] = oldSrc }))
  } else if (src) {
    iframeSrcs[id] = src
  }
  if (doRelayout) nextTick(relayout)
  nextTick(relayout)
}

function onDragStart({ id, startX, startY }) {
  const fromIndex = layout.value.indexOf(id)
  if (fromIndex === -1) return
  function onMouseUp(ev) {
    document.removeEventListener('mouseup', onMouseUp)
    if (!deskEl.value) return
    const deskRect = deskEl.value.getBoundingClientRect()
    const x = ev.clientX - deskRect.left
    const y = ev.clientY - deskRect.top
    const total = layout.value.length
    const cols = Math.min(layoutCols.value, total) || 1
    const sl = calcSlots(total, cols, deskEl.value.clientWidth, deskEl.value.clientHeight)
    let targetIndex = fromIndex
    for (let i = 0; i < sl.length; i++) {
      const s = sl[i]
      if (x >= s.left && x <= s.left + s.width && y >= s.top && y <= s.top + s.height) {
        targetIndex = i; break
      }
    }
    if (targetIndex !== fromIndex) {
      const moved = layout.value.splice(fromIndex, 1)[0]
      layout.value.splice(targetIndex, 0, moved)
      nextTick(relayout)
    }
  }
  document.addEventListener('mouseup', onMouseUp)
}

function refreshAll() {
  if (!layout.value.length) { emit('toast', '没有播放窗口'); return }
  layout.value.forEach((id, i) => {
    setTimeout(() => {
      const oldSrc = iframeSrcs[id]
      if (!oldSrc || oldSrc === 'about:blank') return
      iframeSrcs[id] = 'about:blank'
      nextTick(() => nextTick(() => { iframeSrcs[id] = oldSrc }))
    }, i * 300)
  })
  emit('toast', '正在刷新全部窗口…')
}

onMounted(() => {
  window.addEventListener('resize', relayout)
  relayout()
})

onUnmounted(() => {
  window.removeEventListener('resize', relayout)
})

watch(() => props.active, val => { if (val) nextTick(relayout) })

defineExpose({ addPlayer, layout, MAX_PLAYERS })
</script>
