<template>
  <!-- Window shell (absolutely positioned, sized by parent via style prop) -->
  <div class="wm-window" :id="`card-${id}`" :style="windowStyle">
    <div class="wm-titlebar" :id="`titlebar-${id}`" :style="titleStyle">
      <span class="wm-drag-handle" title="换位" @mousedown.prevent="onDragStart">⠿</span>
      <span class="wm-title-text">监测窗口 #{{ id }}{{ statusMsg ? '  · ' + statusMsg : '' }}</span>
    </div>
    <div class="wm-viewport">
      <div :id="`placeholder-${id}`" class="video-placeholder" :class="{ hidden: iframeSrc !== 'about:blank' }">
        <svg width="40" height="40" viewBox="0 0 24 24">
          <rect width="24" height="24" rx="4" fill="#ff0000"/>
          <polygon points="10,8 16,12 10,16" fill="#fff"/>
        </svg>
        <span>YouTube Live</span>
      </div>
    </div>
    <div class="card-controls">
      <input
        class="url-input"
        :id="`url-${id}`"
        v-model="urlInput"
        type="text"
        placeholder="输入 YouTube 直播链接…"
        @keydown.enter="loadVideo"
      />
      <button class="c-btn play" type="button" @click="loadVideo">播放</button>
      <button class="c-btn ref" type="button" title="刷新本窗" @click="refreshOne">↻</button>
      <button class="c-btn ratio" type="button" title="横竖切换" @click="toggleRatio">{{ ratioLabel }}</button>
      <div class="vol-wrap">
        <span class="vol-icon" :id="`vol-icon-${id}`">{{ volIcon }}</span>
        <input class="vol-slider" type="range" min="0" max="100" v-model="volume" @input="onVolumeChange" />
      </div>
      <button class="c-btn cls" type="button" title="关闭" @click="$emit('remove', id)">✕</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { extractVideoID } from '../composables/useDomUtils.js'

const props = defineProps({
  id: { type: Number, required: true },
  slot: { type: Object, default: null }, // { left, top, width, height }
  iframeEl: { type: Object, default: null }, // ref to iframe DOM managed by parent
})

const emit = defineEmits(['remove', 'drag-swap', 'load-video', 'status'])

const urlInput = ref('')
const statusMsg = ref('')
const isError = ref(false)
const volume = ref(100)
const ratioMode = ref('landscape') // 'landscape' | 'portrait'

const iframeSrc = ref('about:blank')

const windowStyle = computed(() => {
  if (!props.slot) return { left: '100%', top: '100%', width: '0', height: '0' }
  return {
    left: props.slot.left + 'px',
    top: props.slot.top + 'px',
    width: props.slot.width + 'px',
    height: props.slot.height + 'px',
  }
})

const titleStyle = computed(() => ({
  color: isError.value ? '#ff6666' : '',
}))

const volIcon = computed(() => {
  const v = Number(volume.value)
  return v === 0 ? '🔇' : v < 50 ? '🔉' : '🔊'
})

const ratioLabel = computed(() => ratioMode.value === 'portrait' ? '横' : '纵')

function setStatus(msg, err = false) {
  statusMsg.value = msg
  isError.value = err
}

function loadVideo() {
  const vid = extractVideoID(urlInput.value)
  if (!vid) { setStatus('无效链接', true); return }
  const host = props.id % 2 === 0 ? 'https://www.youtube-nocookie.com' : 'https://www.youtube.com'
  const src = `${host}/embed/${vid}?autoplay=1&enablejsapi=1&playsinline=1`
  iframeSrc.value = src
  emit('load-video', { id: props.id, src, ratioMode: ratioMode.value })
  setStatus('播放中')
}

function refreshOne() {
  emit('load-video', { id: props.id, src: iframeSrc.value, refresh: true, ratioMode: ratioMode.value })
  setStatus('已刷新')
}

function toggleRatio() {
  ratioMode.value = ratioMode.value === 'portrait' ? 'landscape' : 'portrait'
  setStatus(ratioMode.value === 'portrait' ? '竖屏模式' : '横屏模式')
  emit('load-video', { id: props.id, src: iframeSrc.value, ratioMode: ratioMode.value, relayout: true })
}

function onVolumeChange() {
  emit('load-video', { id: props.id, volume: Number(volume.value) })
}

function onDragStart(e) {
  emit('drag-swap', { id: props.id, startX: e.clientX, startY: e.clientY })
}

function setUrl(url) {
  urlInput.value = url
  loadVideo()
}

defineExpose({ setStatus, setUrl, iframeSrc, ratioMode })
</script>
