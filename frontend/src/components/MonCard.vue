<template>
  <div class="mon-card">
    <div class="mon-card-inner">
      <div class="mon-card-top">
        <div class="mon-card-img-wrap">
          <img
            v-if="item.avatar"
            class="mon-card-img"
            :src="item.avatar"
            alt=""
            @error="onImgError"
          />
        </div>
        <div class="mon-card-info">
          <div class="mon-card-name">{{ item.name || '' }}</div>
          <div class="mon-title-blocks">
            <span class="mon-tb1">{{ tb.block1 }}</span>
            <span class="mon-tb2">{{ tb.block2 }}</span>
            <span class="mon-tb3">{{ tb.block3 }}</span>
          </div>
        </div>
        <a
          class="mon-open-btn"
          :href="item.url || '#'"
          target="_blank"
          title="在 YouTube 打开"
          @click.stop
        >
          <!-- YouTube 图标：使用主题渐变色 -->
          <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient :id="gradId" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" :style="`stop-color:var(--icon-grad-a)`"/>
                <stop offset="100%" :style="`stop-color:var(--icon-grad-b)`"/>
              </linearGradient>
            </defs>
            <path :fill="`url(#${gradId})`" d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
          </svg>
        </a>
      </div>
      <div class="mon-card-bottom">
        <span class="mon-live-badge">
          <span class="mon-live-dot"></span>
          LIVE <span style="color:rgba(255,255,255,.85);font-weight:400;margin-left:0.15rem">直播中</span>
        </span>
        <button class="mon-send-btn" type="button" @click.stop="$emit('send', item)">
          <span class="mon-send-label">窗口播放</span>
          <span class="mon-send-arrow" aria-hidden="true"></span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { parseLiveTitleBlocks } from '../composables/useDomUtils.js'

const props = defineProps({
  item: { type: Object, required: true },
})
const emit = defineEmits(['send', 'avatar-error'])

function onImgError(e) {
  e.target.style.display = 'none'
  emit('avatar-error', props.item)
}

const gradId = `ytgrad-${Math.random().toString(36).slice(2, 8)}`
const tb = computed(() => parseLiveTitleBlocks(props.item.title || ''))
</script>
