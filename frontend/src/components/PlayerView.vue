<template>
  <div id="view-player" class="view" :class="{ active: active }">

    <!-- Toolbar -->
    <div class="player-toolbar">

      <!-- Left: layout buttons + add -->
      <div class="toolbar-left">
        <div class="layout-btns">
          <!-- 单窗 1格 -->
          <button
            id="btn-col1"
            class="layout-btn"
            :class="{ active: layoutCols === 1 }"
            title="单窗 1格"
            @click="setLayoutCols(1)"
          >
            <svg class="layout-svg" viewBox="0 0 14 11" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="0" y="0" width="14" height="11" rx="1.5" fill="currentColor"/>
            </svg>
          </button>

          <!-- 四宫 4格 -->
          <button
            id="btn-col2"
            class="layout-btn"
            :class="{ active: layoutCols === 2 }"
            title="四宫 4格"
            @click="setLayoutCols(2)"
          >
            <svg class="layout-svg" viewBox="0 0 14 11" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="0" y="0" width="6" height="5" rx="1" fill="currentColor"/>
              <rect x="8" y="0" width="6" height="5" rx="1" fill="currentColor"/>
              <rect x="0" y="6" width="6" height="5" rx="1" fill="currentColor"/>
              <rect x="8" y="6" width="6" height="5" rx="1" fill="currentColor"/>
            </svg>
          </button>

          <!-- 六宫 6格 -->
          <button
            id="btn-col3"
            class="layout-btn"
            :class="{ active: layoutCols === 3 }"
            title="六宫 6格"
            @click="setLayoutCols(3)"
          >
            <svg class="layout-svg" viewBox="0 0 14 11" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="0"  y="0" width="4" height="5" rx="1" fill="currentColor"/>
              <rect x="5"  y="0" width="4" height="5" rx="1" fill="currentColor"/>
              <rect x="10" y="0" width="4" height="5" rx="1" fill="currentColor"/>
              <rect x="0"  y="6" width="4" height="5" rx="1" fill="currentColor"/>
              <rect x="5"  y="6" width="4" height="5" rx="1" fill="currentColor"/>
              <rect x="10" y="6" width="4" height="5" rx="1" fill="currentColor"/>
            </svg>
          </button>
        </div>

        <button
          id="addBtn"
          class="add-btn"
          :disabled="layout.length >= MAX_PLAYERS"
          @click="addPlayer()"
        >
          ＋ 添加窗口
        </button>
      </div>

      <!-- Right: actions + badge -->
      <div class="toolbar-right">
        <button id="btnRefreshAll" class="tb-secondary" @click="refreshAll">
          全域刷新
        </button>
        <span id="countBadge" class="count-badge">
          {{ layout.length }} / {{ MAX_PLAYERS }} 个窗口
        </span>
      </div>

    </div>
    <!-- /Toolbar -->

    <!-- Desk -->
    <div id="desk" ref="deskEl">

      <div id="empty-hint" :style="{ display: layout.length === 0 ? 'block' : 'none' }">
        <strong>系统待命 SYSTEM READY</strong>
        请添加播放窗口或在「频道信号」中发送直播到播放器
      </div>

      <!-- Player cards -->
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

      <!-- Iframe layers -->
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
    <!-- /Desk -->

  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, onUnmounted, watch } from 'vue'
import PlayerCard from './PlayerCard.vue'

// ─── Props / Emits ────────────────────────────────────────────────────────────
const props = defineProps({ active: Boolean })
const emit  = defineEmits(['toast'])

// ─── Constants ────────────────────────────────────────────────────────────────
const MAX_PLAYERS = 6
const GAP   = 6
const PAD   = 8

// ─── State ────────────────────────────────────────────────────────────────────
const layoutCols  = ref(2)
const layout      = ref([])
const cardCount   = ref(0)
const cardRefs    = reactive({})
const iframeSrcs  = reactive({})
const iframeStyles = reactive({})
const ratioModes  = reactive({})

const deskEl = ref(null)
const slots  = ref([])

// ─── Layout helpers ───────────────────────────────────────────────────────────
function calcSlots(n, cols, deskW, deskH) {
  if (n === 0) return []
  const rows = Math.ceil(n / cols)
  const w = (deskW - PAD * 2 - GAP * (cols - 1)) / cols
  const h = (deskH - PAD * 2 - GAP * (rows - 1)) / rows

  return Array.from({ length: n }, (_, i) => ({
    left:   PAD + (i % cols)              * (w + GAP),
    top:    PAD + Math.floor(i / cols)    * (h + GAP),
    width:  w,
    height: h,
  }))
}

function relayout() {
  if (!deskEl.value) return

  const dW   = deskEl.value.clientWidth
  const dH   = deskEl.value.clientHeight
  const n    = layout.value.length
  const cols = Math.min(layoutCols.value, n) || 1

  slots.value = calcSlots(n, cols, dW, dH)

  const rootStyle = getComputedStyle(document.documentElement)
  const rootFs    = parseFloat(rootStyle.fontSize)
  const titleH    = parseFloat(rootStyle.getPropertyValue('--title-h')) * rootFs
  const ctrlH     = parseFloat(rootStyle.getPropertyValue('--ctrl-h'))  * rootFs

  layout.value.forEach((id, i) => {
    const s = slots.value[i]
    if (!s) return

    const isPortrait = (ratioModes[id] || 'landscape') === 'portrait'
    const baseW = isPortrait ? 720  : 1280
    const baseH = isPortrait ? 1280 : 720

    const viewportH = Math.max(40, s.height - titleH - ctrlH)
    const scale     = Math.min(s.width / baseW, viewportH / baseH)

    const offsetX = s.left + (s.width   - baseW * scale) / 2
    const offsetY = s.top  + titleH + (viewportH - baseH * scale) / 2

    iframeStyles[id] = {
      width:     baseW + 'px',
      height:    baseH + 'px',
      transform: `translate(${offsetX}px, ${offsetY}px) scale(${scale})`,
    }
  })
}

// ─── Player management ────────────────────────────────────────────────────────
function addPlayer(initUrl) {
  if (layout.value.length >= MAX_PLAYERS) return null

  const id = ++cardCount.value
  ratioModes[id]   = 'landscape'
  iframeSrcs[id]   = 'about:blank'
  iframeStyles[id] = {}
  layout.value.push(id)

  nextTick(() => {
    relayout()
    if (initUrl && cardRefs[id]) cardRefs[id].setUrl(initUrl)
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

// ─── Video loading ────────────────────────────────────────────────────────────
function onLoadVideo({ id, src, refresh, volume, relayout: doRelayout, ratioMode }) {
  // Volume-only command — post to iframe and bail early
  if (volume !== undefined) {
    const ifr = document.getElementById(`iframe-${id}`)
    if (ifr?.src && ifr.src !== 'about:blank') {
      try {
        ifr.contentWindow.postMessage(
          JSON.stringify({ event: 'command', func: 'setVolume', args: [volume] }),
          '*'
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

  // doRelayout flag or always relayout after src change
  if (doRelayout || src || refresh) nextTick(relayout)
}

// ─── Drag-to-swap ─────────────────────────────────────────────────────────────
function onDragStart({ id }) {
  const fromIndex = layout.value.indexOf(id)
  if (fromIndex === -1) return

  function onMouseUp(ev) {
    document.removeEventListener('mouseup', onMouseUp)
    if (!deskEl.value) return

    const rect  = deskEl.value.getBoundingClientRect()
    const x     = ev.clientX - rect.left
    const y     = ev.clientY - rect.top
    const total = layout.value.length
    const cols  = Math.min(layoutCols.value, total) || 1
    const sl    = calcSlots(total, cols, deskEl.value.clientWidth, deskEl.value.clientHeight)

    let targetIndex = fromIndex
    for (let i = 0; i < sl.length; i++) {
      const s = sl[i]
      if (x >= s.left && x <= s.left + s.width && y >= s.top && y <= s.top + s.height) {
        targetIndex = i
        break
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

// ─── Refresh all ──────────────────────────────────────────────────────────────
function refreshAll() {
  if (!layout.value.length) {
    emit('toast', '没有播放窗口')
    return
  }

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

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  window.addEventListener('resize', relayout)
  relayout()
})

onUnmounted(() => {
  window.removeEventListener('resize', relayout)
})

watch(() => props.active, val => {
  if (val) nextTick(relayout)
})

// ─── Expose ───────────────────────────────────────────────────────────────────
defineExpose({ addPlayer, layout, MAX_PLAYERS })
</script>

<style scoped>
/* 只保留此组件独有的布局规则，其余交由 global style.css 控制 */

#desk {
  position: relative;
  width: 100%;
  height: calc(100% - 2.8rem);
}

.wm-iframe-layer {
  position: absolute;
  top: 0;
  left: 0;
  border: none;
}
</style>
